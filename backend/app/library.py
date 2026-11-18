import asyncio
import hashlib
import json
import math
import re
import sys
import subprocess
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import zip_longest
from pathlib import Path

from .config import Settings
from .errors import AppError
from .schemas import Project
from .store import Store
from .metadata import bibliography, metadata_fingerprint


def contained(path: Path, roots: list[Path]) -> bool:
    return any(path.is_relative_to(root.expanduser().resolve()) for root in roots)


def digest_file(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def file_fingerprint(path, max_bytes):
    stat = path.stat()
    if stat.st_size > max_bytes:
        raise AppError('PDF_TOO_LARGE', 'PDF 超过单文件大小限制，请缩小文献集。')
    return ':'.join(map(str, (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, metadata_fingerprint(path))))


def normalize(text):
    return ' '.join(text.split())


def content_regions(pages):
    """Identify explicit bibliography boundaries; never discard appendix evidence."""
    back=False
    for text in pages:
        if re.search(r'(?im)^\s*(?:references|bibliography)\s*$',text):
            back=True
        yield 'back_matter' if back else 'body'


def tokens(text):
    stop = {'the', 'and', 'for', 'with', 'that', 'this', 'from', 'are', 'how', 'what', 'does', '研究', '文献'}
    # Retrieval-only normalization: never change stored quotations or anchor offsets.
    text = unicodedata.normalize('NFKC', text).replace('\u00ad', '')
    lowered=text.lower()
    words = re.findall(r'[a-z0-9]{2,}', lowered)
    # Add the joined spelling while retaining original tokens for genuine compounds.
    words.extend(a+b for a,b in re.findall(r'([a-z]{2,})-\s+([a-z]{2,})',lowered))
    for span in re.findall(r'[\u3400-\u9fff]+', text):
        words.extend(span[i:i+2] for i in range(len(span)-1))
    return [w for w in words if w not in stop]


@dataclass(frozen=True)
class Scope:
    id: str
    workdir: Path
    libraries: list[Path]


def resolve_project(project: Project, config: Settings) -> Scope:
    try:
        work = Path(project.workingDirectory).expanduser()
        if not work.is_absolute():
            work = config.workspace_root / work
        work = work.resolve(strict=True)
        if not work.is_dir() or not contained(work, config.allowed_roots):
            raise ValueError()
        libraries = []
        for value in project.knowledgePaths:
            path = Path(value).expanduser()
            if not path.is_absolute():
                path = work / path
            path = path.resolve(strict=True)
            if not path.is_dir() or not contained(path, config.allowed_roots):
                raise ValueError()
            if path not in libraries:
                libraries.append(path)
    except (OSError, ValueError, RuntimeError):
        raise AppError('INVALID_KNOWLEDGE_PATH', '工作目录或知识库不存在，或超出 ALLOWED_ROOTS 配置范围。') from None
    key = json.dumps([project.id, str(work), sorted(map(str, libraries))], ensure_ascii=False)
    return Scope(hashlib.sha256(key.encode()).hexdigest(), work, libraries)


def list_folders(config: Settings, path: str | None):
    roots = sorted({root.expanduser().resolve() for root in config.allowed_roots if root.expanduser().is_dir()})
    current = parent = None
    truncated = False
    try:
        if path is None:
            folders = roots
        else:
            current = (config.workspace_root / Path(path).expanduser()).resolve(strict=True)
            if not current.is_dir() or not contained(current, roots):
                raise ValueError()
            parent = current.parent if current.parent != current and contained(current.parent, roots) else None
            folders = []
            for entry in current.iterdir():
                if entry.is_dir() and not entry.is_symlink() and contained(entry.resolve(), roots):
                    if len(folders) == 250:
                        truncated = True
                        break
                    folders.append(entry)
    except (OSError, ValueError, RuntimeError):
        raise AppError('INVALID_KNOWLEDGE_PATH', '目录不存在或超出 ALLOWED_ROOTS 配置范围。') from None
    return {'current': str(current) if current else None, 'parent': str(parent) if parent else None,
            'folders': [{'name': folder.name or str(folder), 'path': str(folder)}
                        for folder in sorted(folders, key=lambda p: p.name.casefold())], 'truncated': truncated}


async def parse_pdf(path: Path, config: Settings):
    # Windows Uvicorn reload uses a Selector loop, which cannot launch asyncio
    # subprocesses. Popen + a communication thread works on both loop types.
    worker = Path(__file__).with_name('pdf_worker.py')
    process = subprocess.Popen(
        [sys.executable, str(worker), str(path), str(config.max_pages_per_pdf)],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
    )
    communication = asyncio.create_task(asyncio.to_thread(process.communicate))
    try:
        output, _ = await asyncio.wait_for(asyncio.shield(communication), config.pdf_timeout_seconds)
        if process.returncode:
            raise AppError('PDF_PARSE_FAILED', '部分 PDF 无法读取、加密或超过解析限制；请检查文献文件。')
        return json.loads(output)
    except TimeoutError:
        raise AppError('PDF_TIMEOUT', 'PDF 解析超时，请移除异常文件或减小文献集。') from None
    finally:
        if process.poll() is None:
            process.kill()
        # Reap the worker and its pipe-reading thread on cancellation as well.
        await asyncio.shield(communication)


class Library:
    def __init__(self, config: Settings, store: Store):
        self.config, self.store = config, store

    def discover(self, scope: Scope):
        candidates = set()
        # Do not follow directory symlinks during recursive traversal. Resolve every file independently.
        for folder in scope.libraries:
            for path in folder.rglob('*'):
                if path.suffix.lower() != '.pdf' or not path.is_file():
                    continue
                resolved = path.resolve()
                if not contained(resolved, self.config.allowed_roots) or not contained(resolved, scope.libraries):
                    raise AppError('INVALID_KNOWLEDGE_PATH', '知识库包含指向允许范围之外的 PDF 链接。')
                candidates.add(resolved)
                if len(candidates) > self.config.max_papers:
                    raise AppError('LIBRARY_TOO_LARGE', f'文献数量超过限制 {self.config.max_papers}。')
        return {path: file_fingerprint(path, self.config.max_pdf_bytes) for path in sorted(candidates)}

    async def index(self, project_id: str, scope: Scope):
        candidates = await asyncio.to_thread(self.discover, scope)
        cached = await asyncio.to_thread(self.store.papers, scope.id)
        removed = {row['id'] for path, row in cached.items() if Path(path) not in candidates}
        changed, passages, warnings, pages = [], [], [], 0
        for path, fingerprint in candidates.items():
            old = cached.get(str(path))
            if old and old['fingerprint'] == fingerprint:
                record = old
            else:
                digest = await asyncio.to_thread(digest_file, path)
                if old and old['digest'] == digest and old['fingerprint'].split(':')[-1] == fingerprint.split(':')[-1]:
                    record = {**old, 'fingerprint': fingerprint}
                else:
                    parsed = await parse_pdf(path, self.config)
                    if await asyncio.to_thread(digest_file, path) != digest:
                        raise AppError('PDF_CHANGED', 'PDF 在解析期间发生变化，请重试。', 409)
                    if old:
                        removed.add(old['id'])
                    record = await asyncio.to_thread(indexed_paper, path, digest, fingerprint, parsed)
                if await asyncio.to_thread(file_fingerprint, path, self.config.max_pdf_bytes) != fingerprint:
                    raise AppError('PDF_CHANGED', 'PDF 在索引期间发生变化，请重试。', 409)
                changed.append(record)
            paper, chunks = record['paper'], record['chunks']
            pages += paper['pages']
            if pages > self.config.max_total_pages:
                raise AppError('LIBRARY_TOO_LARGE', '文献总页数超过配置限制。')
            if not chunks:
                warnings.append(f'{paper["title"]}：未提取到文字，可能需要 OCR。')
            passages.extend(chunks)
        await asyncio.to_thread(self.store.update_index, project_id, scope.workdir, scope.id, changed, removed)
        return passages, warnings

    def source(self, project_id, paper_id):
        record = self.store.source(project_id, paper_id)
        if not record:
            raise AppError('PAPER_NOT_FOUND', '该项目中没有这篇已索引论文。', 404)
        path = Path(record['path']).resolve()
        if not contained(path, self.config.allowed_roots) or not path.is_file():
            raise AppError('PAPER_NOT_FOUND', '源论文不可访问。', 404)
        if digest_file(path) != record['digest']:
            raise AppError('PDF_CHANGED', '论文已修改，请重新生成综述以同步页码。', 409)
        return path


def indexed_paper(path, digest, fingerprint, parsed):
    paper_id = 'paper-' + hashlib.sha256((str(path) + digest).encode()).hexdigest()[:24]
    paper = {'id': paper_id, 'title': parsed['title'] or path.stem, 'author': parsed['author'] or '作者未知',
             'year': None, 'pages': len(parsed['pages']), 'summary': '', 'pdfAvailable': True}
    metadata = bibliography(path,digest)
    if metadata:
        paper.update(title=metadata['title'],author=', '.join(metadata['authors']) or '作者未知',
                     year=metadata['year'],**{k:v for k,v in metadata.items() if k not in ('title','authors','year')})
    chunks = []
    for page, (text,region) in enumerate(zip(parsed['pages'],content_regions(parsed['pages'])), 1):
        text = normalize(text)
        for start in range(0, len(text), 1300):
            passage = text[start:start+1600]
            if len(passage.strip()) >= 20:
                chunks.append({'id': f'{paper_id}-p{page}-c{start}', 'paper': paper, 'page': page,
                               'text': passage,'content_region':region})
    if chunks:
        paper['summary'] = chunks[0]['text'][:220]
    return {'id': paper_id, 'path': str(path), 'digest': digest, 'fingerprint': fingerprint, 'paper': paper, 'chunks': chunks}


def named_retrieval_queries(queries):
    """Split explicitly named Latin methods, preserving hyphenated identities."""
    queries = list(dict.fromkeys(q.strip() for q in queries if q.strip()))
    names = []
    for query in queries:
        for match in re.finditer(r'(?<![A-Za-z0-9-])(?:[A-Za-z]+-[A-Za-z]+|[A-Z][A-Z0-9]{2,})(?![A-Za-z0-9-])', query):
            name = match[0]
            if name not in {'PDF', 'API', 'DOI', 'HTTP', 'HTTPS', 'LLM', 'GPU', 'CPU'}:
                names.append(name)
    return list(dict.fromkeys([*names, *queries]))


def title_method_score(title, name):
    """Title cues prioritize source coverage; they never verify paper identity."""
    boundary = r'(?![a-z0-9-])'
    if re.match(re.escape(name) + boundary, title, re.I):
        return 4
    words = re.findall(r'[A-Za-z]+', title)
    for i, word in enumerate(words):
        if word.lower() in {'for', 'with', 'via', 'using', 'towards', 'through'} and i >= 2:
            if ''.join(w[0] for w in words[:i]).upper() == name.upper():
                return 2 if re.search(r'\b(survey|review)\b', title, re.I) else 3
            break
    return 1 if re.search(r'(?<![a-z0-9-])' + re.escape(name) + boundary, title, re.I) else 0


class SearchIndex:
    """Bounded in-memory BM25 over page-preserving passages; English words + CJK bigrams."""

    def __init__(self, chunks):
        self.chunks = chunks
        self.postings = defaultdict(list)
        self.document_terms=defaultdict(Counter)
        self.document_lengths=Counter()
        lengths = []
        for i, chunk in enumerate(chunks):
            counts = Counter(tokens(chunk['text'] + ' ' + chunk['paper']['title']))
            document=chunk['paper']['id']
            self.document_lengths[document]+=1
            self.document_terms[document].update(counts.keys())
            lengths.append(sum(counts.values()))
            for word, count in counts.items():
                self.postings[word].append((i, count))
        average = sum(lengths) / max(1, len(lengths)) or 1
        self.norms = [1.2 * (.25 + .75 * length / average) for length in lengths]

    def rank_papers(self, queries):
        expanded = named_retrieval_queries(queries)
        original = {q.strip() for q in queries}
        names = [q for q in expanded if q not in original or re.fullmatch(r'[A-Za-z0-9-]+', q)]
        catalog = {c['paper']['id']: c['paper']['title'] for c in self.chunks}
        # One strong title match per named method before incidental mentions.
        direct = []
        for name in names:
            matches = sorted(catalog, key=lambda key: (-title_method_score(catalog[key], name), key))
            if matches and title_method_score(catalog[matches[0]], name) >= 3:
                direct.append(matches[0])
        ranked = [self.search(query, len(self.document_lengths)) for query in expanded]
        return list(dict.fromkeys([*direct, *(
            hit['paper']['id'] for rank in zip_longest(*ranked)
            for hit in rank if hit is not None)]))

    def search_many(self, queries, limit=6, document_ids=None, paper_ids=None, content_region=None):
        """Fuse real question/subquestion results; no gold papers or pages are used."""
        if limit<=0: return []
        queries=named_retrieval_queries(queries)
        ranked=[self.search(q,max(6,limit*2),document_ids,paper_ids,content_region) for q in queries]
        scores=defaultdict(float);items={}
        for hits in ranked:
            for rank,hit in enumerate(hits,1):
                items[hit['id']]=hit;scores[hit['id']]+=1/(60+rank)
        result=[];seen=set();pages=Counter()
        def admit(hit):
            key=(hit['paper']['id'],hit['page'])
            if hit['id'] in seen or pages[key]>=1: return
            result.append(hit);seen.add(hit['id']);pages[key]+=1
        # Reserve a first hit for each supplied subquestion before fused fill.
        catalog = {c['paper']['id']: c['paper']['title'] for c in self.chunks}
        for query, hits in zip(queries, ranked):
            if len(result) >= limit:
                break
            primary = sorted(catalog, key=lambda key: (-title_method_score(catalog[key], query), key))
            if re.fullmatch(r'[A-Za-z0-9-]+', query) and primary and title_method_score(catalog[primary[0]], query) >= 3:
                targeted = self.search(query, 1, document_ids, [primary[0]] if paper_ids is None else [p for p in paper_ids if p == primary[0]], content_region)
                if targeted:
                    admit(targeted[0])
                    continue
            if hits:
                admit(hits[0])
        for key in sorted(items,key=lambda key:(-scores[key],key)):
            if len(result)>=limit: break
            admit(items[key])
        return result

    def search(self, query: str, limit=6, document_ids=None, paper_ids=None, content_region=None):
        if limit <= 0:
            return []
        # Conservative, domain-level aliases; not machine translation. Unknown
        # concepts remain unknown and can be searched by the Researcher in English.
        aliases = {'检索':'retrieval retrieve', '生成':'generation generate',
                   '反思':'reflection', '检查':'critique support', '判断':'decide decision',
                   '是否需要':'need necessary adaptive', '按需':'adaptive demand',
                   '下一句':'next sentence', '下一句话':'next sentence',
                   '什么时候':'trigger confidence', '何时':'trigger confidence',
                   '重新':'regenerate', '置信度':'confidence probability threshold',
                   '训练':'training', '推理':'inference reasoning', '证据':'evidence support',
                   '数据集':'dataset', '指标':'metric', '成本':'cost', '硬件':'hardware',
                   '比较':'compare comparison', '评估':'evaluation', '准确率':'accuracy',
                   '查资料':'retrieval retrieve search documents acquire acquires',
                   '查找资料':'retrieval retrieve search documents',
                   '需不需要':'need necessary adaptive conditional conditionally',
                   '不确定':'uncertain uncertainty confidence',
                   '触发':'trigger threshold conditional',
                   '花费':'cost latency tokens', '耗时':'latency time',
                   '局限':'limitation limitations', '出处':'citation evidence source'}
        expanded = query + ' ' + ' '.join(v for k,v in aliases.items() if k in query)
        prioritize_body=not re.search(r'appendi[xxc]|prompt|附录|提示词',query,re.I)
        scores = defaultdict(float)
        for term in sorted(set(tokens(expanded))):
            matches = self.postings.get(term, ())
            inverse = math.log(1 + (len(self.chunks) - len(matches) + .5) / (len(matches) + .5))
            frequencies={doc:terms[term]/self.document_lengths[doc] for doc,terms in self.document_terms.items()}
            maximum=max(frequencies.values(),default=1) or 1
            for i, count in matches:
                chunk=self.chunks[i]
                if content_region is not None and chunk.get('content_region','body')!=content_region:
                    continue
                if document_ids is not None and chunk.get('document_id') not in document_ids:
                    continue
                if paper_ids is not None and chunk.get('paper_id',chunk['paper']['id']) not in paper_ids:
                    continue
                # Suppress incidental mentions of another method in related work
                # or references, while retaining their original passages.
                topical=.15+.85*frequencies[chunk['paper']['id']]/maximum
                body=.65 if prioritize_body and chunk.get('content_region')=='back_matter' else 1
                scores[i] += topical * body * inverse * count * 2.2 / (count + self.norms[i])
        ranked = sorted(scores, key=lambda i: (-scores[i], self.chunks[i]['id']))
        # Limit repeated passages on the same page so several papers can be represented.
        per_page, grouped = Counter(), {}
        for i in ranked:
            chunk = self.chunks[i]
            key = (chunk['paper']['id'], chunk['page'])
            if per_page[key] >= 2:
                continue
            per_page[key] += 1
            grouped.setdefault(chunk['paper']['id'], []).append(chunk)
        # Round-robin ranked documents, retaining BM25 ordering within each one.
        # A single long paper must not occupy every slot in a comparison query.
        result=[]
        while grouped and len(result)<limit:
            for key in list(grouped):
                result.append(grouped[key].pop(0))
                if not grouped[key]: del grouped[key]
                if len(result)==limit: break
        return result
