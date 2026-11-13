import asyncio
import hashlib
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from importlib.metadata import version
from urllib.parse import quote

import httpx

from ..library import normalize, parse_pdf
from ..errors import AppError


def canonical(text):
    return ''.join(c for c in text.casefold() if c.isalnum())


def correspondence(record, first_page):
    present = re.findall(r'arXiv:\s*(\d{4}\.\d{4,5}(?:v\d+)?)', first_page, re.I)
    expected = record.get('arxiv_id')
    if expected and present and all(p.split('v')[0] != expected.split('v')[0] for p in present):
        return 'mismatch'
    header = canonical(first_page[:4000])
    title = canonical(record['title'])
    authors = record.get('authors') or []
    author_match = any(canonical(a.split()[-1]) in header for a in authors if a.split())
    # Conservative: a real identifier elsewhere in a PDF is not enough.
    if title and title in header and author_match:
        expected = record.get('arxiv_id')
        present = re.findall(r'arXiv:\s*(\d{4}\.\d{4,5}(?:v\d+)?)', first_page, re.I)
        if expected and present and expected not in present:
            return 'mismatch'
        return 'matched'
    return 'unresolved'


class AcademicSources:
    def __init__(self, config, workspace, meter, transport=None):
        self.config, self.workspace, self.meter = config, workspace, meter
        self.transport = transport

    async def request(self, url, params=None, limit=4_000_000):
        for attempt in range(3):
            self.meter.charge('tool', 'academic_http')
            try:
                async with httpx.AsyncClient(timeout=30, transport=self.transport, follow_redirects=False) as client:
                    async with client.stream('GET', url, params=params, headers={'User-Agent': 'AcademicReviewCourseProject/1.0'}) as r:
                        if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                            await asyncio.sleep(3 * (attempt+1))
                            continue
                        if r.status_code != 200:
                            return {'status': 'error', 'data': None, 'error': {'code': f'HTTP_{r.status_code}', 'retryable': False, 'attempts': attempt+1}}
                        data = bytearray()
                        async for part in r.aiter_bytes():
                            data.extend(part)
                            if len(data) > limit:
                                return {'status': 'error', 'data': None, 'error': {'code': 'CONTENT_TOO_LARGE', 'retryable': False, 'attempts': attempt+1}}
                        return {'status': 'ok', 'data': bytes(data), 'error': None}
            except httpx.RequestError:
                if attempt < 2:
                    await asyncio.sleep(3 * (attempt+1))
                    continue
                return {'status': 'error', 'data': None, 'error': {'code': 'SERVICE_UNAVAILABLE', 'retryable': True, 'attempts': 3}}

    async def discover(self, query, mode):
        if mode not in ('online', 'hybrid'):
            raise PermissionError('Local mode cannot discover online papers')
        result = await self.request('https://export.arxiv.org/api/query',
                                    {'search_query': query, 'max_results': min(self.meter.limit.documents, 5)})
        if result['status'] != 'ok':
            self.workspace.save('source_query', {'query': query, **result})
            return [], [result['error']['code']]
        raw = result['data'].decode('utf-8')
        self.workspace.save('authority_response', {'source': 'arxiv', 'query': query, 'retrieved_at': time.time(), 'raw': raw})
        try:
            feed = ET.fromstring(raw)
        except ET.ParseError:
            return [], ['AUTHORITY_RESPONSE_INVALID']
        ns = {'a': 'http://www.w3.org/2005/Atom'}
        candidates = []
        for entry in feed.findall('a:entry', ns):
            record_url = entry.findtext('a:id', '', ns)
            match = re.fullmatch(r'https?://arxiv.org/abs/(\d{4}\.\d{4,5}v\d+)', record_url)
            if not match:
                continue
            version_id = match[1]
            paper = {'paper_id': 'arxiv-' + version_id.split('v')[0], 'source': 'online',
                     'title': normalize(entry.findtext('a:title', '', ns)),
                     'authors': [a.findtext('a:name', '', ns) for a in entry.findall('a:author', ns)],
                     'year': int(entry.findtext('a:published', '0000', ns)[:4]) or None,
                     'arxiv_id': version_id, 'identity_status': 'candidate', 'publication_status': 'preprint',
                     'source_record': record_url, 'version': version_id}
            # Exact authoritative object lookup, distinct from discovery.
            await asyncio.sleep(3)
            identity = await self.request('https://export.arxiv.org/api/query', {'id_list': version_id})
            status = 'unresolved'
            if identity['status'] == 'ok':
                try:
                    obj = ET.fromstring(identity['data']).find('a:entry', ns)
                    if obj is not None:
                        matched = obj.findtext('a:id', '', ns).endswith('/'+version_id)
                        title = normalize(obj.findtext('a:title', '', ns))
                        names = [a.findtext('a:name', '', ns) for a in obj.findall('a:author', ns)]
                        status = 'verified' if matched and canonical(title) == canonical(paper['title']) and names == paper['authors'] else 'conflict'
                except ET.ParseError:
                    pass
            paper['identity_status'] = status
            self.workspace.save('identity_check', {'paper_id': paper['paper_id'], 'status': status,
                'source': 'arxiv', 'retrieved_at': time.time(),
                'raw': identity['data'].decode('utf-8') if identity['status'] == 'ok' else identity['error']})
            candidates.append(paper)
        self.workspace.save('source_query', {'query': query, 'status': 'ok' if candidates else 'empty',
                                             'candidates': candidates})
        return candidates, []

    async def fetch(self, paper):
        if paper['identity_status'] != 'verified':
            return None, 'IDENTITY_NOT_VERIFIED'
        result = await self.request('https://arxiv.org/pdf/' + paper['arxiv_id'], limit=self.config.max_pdf_bytes)
        if result['status'] != 'ok':
            return None, 'FULL_TEXT_UNAVAILABLE:' + result['error']['code']
        data = result['data']
        if not data.startswith(b'%PDF'):
            return None, 'CONTENT_NOT_PDF'
        digest = hashlib.sha256(data).hexdigest()
        folder = self.config.runtime_dir / 'originals' / hashlib.sha256(self.workspace.project.encode()).hexdigest()
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (digest + '.pdf')
        if not path.exists():
            path.write_bytes(data)
        try:
            parsed = await parse_pdf(path, self.config)
        except AppError as error:
            self.workspace.save('content_fetch', {'paper_id':paper['paper_id'],'status':'error','code':error.code})
            return None,error.code
        status = correspondence(paper, parsed['pages'][0])
        document = {'document_id': 'document-'+hashlib.sha256((digest+paper['paper_id']+version('pypdf')).encode()).hexdigest(), 'paper_id': paper['paper_id'],
                    'content_hash': digest, 'path': str(path), 'source': 'https://arxiv.org/pdf/'+paper['arxiv_id'],
                    'version': paper['version'], 'parser_version': 'pypdf:'+version('pypdf')+';chunks-v1', 'content_scope': 'full_text',
                    'correspondence': status, 'pages': parsed['pages']}
        self.workspace.save('document', document, document['document_id'])
        return document, None if status == 'matched' else 'DOCUMENT_CORRESPONDENCE_UNRESOLVED'

    async def lookup_local(self, header, allowed):
        if not allowed:
            raise PermissionError('Local metadata lookup disabled')
        identifiers = re.findall(r'10\.\d{4,9}/[^\s<>"\]]+', header[:1500])
        if not identifiers:
            return {'identity_status': 'unresolved', 'reason': 'No header DOI; identity remains unknown'}
        doi = identifiers[0].rstrip('.,;)')
        response = await self.request('https://api.crossref.org/works/' + quote(doi, safe=''))
        if response['status'] != 'ok':
            return {'identity_status': 'unresolved', 'reason': response['error']['code']}
        import json
        try:
            raw = json.loads(response['data'])['message']
            record = {'title': raw.get('title', [''])[0], 'authors': [a.get('family', '') for a in raw.get('author', [])]}
            matched = correspondence(record, header) == 'matched'
            result = {'identity_status': 'verified' if matched else 'conflict', 'doi': doi, 'record': raw}
        except (ValueError, KeyError, TypeError):
            result = {'identity_status': 'unresolved', 'reason': 'Invalid registry record'}
        self.workspace.save('local_metadata_check', result)
        return result
