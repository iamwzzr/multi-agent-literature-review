"""Download pinned public arXiv PDFs. No model calls. PDFs stay out of Git."""
import argparse
import hashlib
import json
import shutil
import subprocess
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAPERS = [
    ('rag', '2005.11401v4', 'Lewis_2020_Retrieval_Augmented_Generation.pdf', True),
    ('selfrag', '2310.11511v1', 'Asai_2023_Self_RAG.pdf', True),
    ('flare', '2305.06983v2', 'Jiang_2023_FLARE.pdf', True),
    ('dpr', '2004.04906v3', 'Karpukhin_2020_DPR.pdf', False),
    ('fid', '2007.01282v2', 'Izacard_2020_FiD.pdf', False),
    ('ircot', '2212.10509v2', 'Trivedi_2022_IRCoT.pdf', False),
    ('crag', '2401.15884v3', 'Yan_2024_CRAG.pdf', False),
]


class Metadata(HTMLParser):
    def __init__(self):
        super().__init__()
        self.values = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta' and attrs.get('name', '').startswith('citation_'):
            self.values.setdefault(attrs['name'], []).append(attrs.get('content', ''))


def fetch(url, path):
    subprocess.run(['curl', '--fail', '--location', '--retry', '2', '--connect-timeout', '20',
                    '--max-time', '180', '--silent', '--show-error', url, '-o', str(path)], check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--download', action='store_true', help='Fetch public PDFs and identity pages')
    parser.add_argument('--write-metadata',action='store_true',help='Write hash-bound user-supplied bibliography sidecars')
    args = parser.parse_args()
    target = ROOT / 'docs/testing/corpus.json'
    expected = {p['arxiv_id']:p['sha256'] for p in json.loads(target.read_text())['papers']} if target.exists() else {}
    folder = ROOT / 'data/papers'
    fixed = ROOT / 'data/test-corpus/fixed'
    records = ROOT / 'data/manual-test-results/corpus-sources'
    for path in (folder, fixed, records, ROOT / 'docs/testing'):
        path.mkdir(parents=True, exist_ok=True)
    manifest = []
    for key, identifier, filename, regression in PAPERS:
        pdf = folder / filename
        page = records / (key + '.html')
        source = 'https://arxiv.org/abs/' + identifier
        if args.download:
            if not page.exists():
                fetch(source, page)
                time.sleep(3)
            if not pdf.exists():
                partial = pdf.with_suffix('.pdf.part')
                fetch('https://arxiv.org/pdf/' + identifier, partial)
                if not partial.read_bytes().startswith(b'%PDF'):
                    raise ValueError('Not a PDF: ' + identifier)
                partial.replace(pdf)
                time.sleep(3)
        metadata = Metadata()
        metadata.feed(page.read_text())
        values = metadata.values
        record = {'key': key, 'arxiv_id': identifier, 'filename': filename,
                  'title': values['citation_title'][0], 'authors': values.get('citation_author', []),
                  'arxiv_first_publication_date': values.get('citation_date', [None])[0],
                  'source': source, 'pdf_url': 'https://arxiv.org/pdf/' + identifier,
                  'version_policy': 'Pinned arXiv version; filename year is first arXiv year, not necessarily venue year.',
                  'sha256': hashlib.sha256(pdf.read_bytes()).hexdigest(), 'bytes': pdf.stat().st_size,
                  'fixed_regression': regression, 'doi': None,
                  'rights': 'Publicly accessible arXiv download; consult source license before redistribution.',
                  'identity_check': 'Metadata read from pinned arXiv identity page; not a backend identity verdict.'}
        if identifier in expected and record['sha256'] != expected[identifier]:
            raise ValueError('Frozen corpus hash changed: ' + identifier + '; inspect before updating the manifest')
        if regression:
            shutil.copyfile(pdf, fixed / filename)
        if args.write_metadata:
            year=record['arxiv_first_publication_date']
            supplied={'sha256':record['sha256'],'title':record['title'],'authors':record['authors'],
                      'year':int(year[:4]) if year else None,'source':source,
                      'year_basis':'first_arxiv_submission','identity_status':'not_assigned_by_manifest'}
            for target_pdf in ([pdf,fixed/filename] if regression else [pdf]):
                target_pdf.with_suffix('.metadata.json').write_text(json.dumps(supplied,ensure_ascii=False,indent=2)+'\n')
        manifest.append(record)
        print(key, identifier, record['bytes'], flush=True)
    target.write_text(json.dumps({'prepared_at': datetime.now(timezone.utc).isoformat(),
                                 'topic': 'Retrieval-augmented generation: retrieval mechanisms and evidence reliability',
                                 'papers': manifest}, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
