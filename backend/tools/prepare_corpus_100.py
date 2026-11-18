"""Restore or verify the frozen public-article corpus without model calls."""

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'docs/testing/corpus-100.json'
PAPERS = ROOT / 'data/papers-100'


def load_manifest():
    papers = json.loads(MANIFEST.read_text(encoding='utf-8'))['papers']
    ids, filenames, keys, hashes = set(), set(), set(), set()
    for paper in papers:
        match = re.fullmatch(r'(\d{4}\.\d{4,5})v\d+', paper['arxiv_id'])
        filename = paper['filename']
        if not match or paper['pdf_url'] != f"https://arxiv.org/pdf/{paper['arxiv_id']}":
            raise ValueError(f"Expected a versioned arXiv PDF for {paper['key']}")
        if Path(filename).name != filename or not filename.endswith('.pdf'):
            raise ValueError(f"Invalid PDF filename: {filename}")
        ids.add(match[1])
        filenames.add(filename)
        keys.add(paper['key'])
        hashes.add(paper['sha256'])
    if {len(papers), len(ids), len(filenames), len(keys), len(hashes)} != {100}:
        raise ValueError('The manifest must contain 100 unique papers and files')
    return papers


def matching_pdf(path, paper):
    if not path.is_file() or path.stat().st_size != paper['bytes']:
        return False
    with path.open('rb') as contents:
        if contents.read(5) != b'%PDF-':
            return False
        contents.seek(0)
        return hashlib.file_digest(contents, 'sha256').hexdigest() == paper['sha256']


def verify_corpus(papers):
    expected = {p['filename'] for p in papers}
    present = {p.relative_to(PAPERS).as_posix() for p in PAPERS.rglob('*')
               if p.suffix.lower() == '.pdf' and p.is_file()}
    problems = [p['filename'] for p in papers if not matching_pdf(PAPERS / p['filename'], p)]
    problems.extend(sorted(present - expected))
    if problems:
        raise ValueError('Check missing, mismatched or extra corpus PDFs: ' + ', '.join(problems))


def download(path, paper):
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix='.part', delete=False) as handle:
        partial = Path(handle.name)
    try:
        subprocess.run(
            ['curl', '--fail', '--location', '--proto', '=https', '--proto-redir', '=https',
             '--retry', '2', '--retry-delay', '4', '--retry-all-errors', '--connect-timeout', '15',
             '--max-time', '120', '--max-filesize', '30000000', '--silent', '--show-error',
             paper['pdf_url'], '-o', str(partial)],
            check=True,
        )
        if not matching_pdf(partial, paper):
            raise ValueError(f"Downloaded PDF differs from the frozen file: {path.name}")
        partial.replace(path)
    finally:
        partial.unlink(missing_ok=True)


def write_sidecar(path, paper):
    date = paper.get('arxiv_first_publication_date') or ''
    sidecar = {'sha256': paper['sha256'], 'title': paper['title'], 'authors': paper['authors'],
               'year': int(date[:4]) if date[:4].isdigit() else None, 'source': paper['source'],
               'year_basis': 'first_arxiv_submission', 'identity_status': 'not_assigned_by_manifest'}
    path.with_suffix('.metadata.json').write_text(
        json.dumps(sidecar, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download', action='store_true', help='Restore missing or mismatched files from arXiv')
    args = parser.parse_args()
    papers = load_manifest()
    if args.download:
        PAPERS.mkdir(parents=True, exist_ok=True)
        for paper in papers:
            path = PAPERS / paper['filename']
            if not matching_pdf(path, paper):
                print('Downloading', paper['key'], flush=True)
                download(path, paper)
                time.sleep(3)
            write_sidecar(path, paper)
    verify_corpus(papers)
    print(f'{len(papers)} PDFs verified in {PAPERS}')


if __name__ == '__main__':
    main()
