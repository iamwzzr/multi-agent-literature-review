import asyncio
import hashlib
import json
import math
import re
import sys
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .config import Settings
from .errors import AppError
from .schemas import Project
from .store import Store


def contained(path: Path, roots: list[Path]) -> bool:
    return any(path.is_relative_to(root.expanduser().resolve()) for root in roots)


def digest_file(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def normalize(text):
    return ' '.join(text.split())


def tokens(text):
    stop = {'the', 'and', 'for', 'with', 'that', 'this', 'from', 'are', 'how', 'what', 'does', '研究', '文献'}
    words = re.findall(r'[a-z0-9]{2,}', text.lower())
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

    async def index(self, project_id: str, scope: Scope):
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
        cached = {r['path']: r for r in self.store.papers(scope.id)}
        records, warnings, pages = [], [], 0
        for path in sorted(candidates):
            if path.stat().st_size > self.config.max_pdf_bytes:
                raise AppError('PDF_TOO_LARGE', 'PDF 超过单文件大小限制，请缩小文献集。')
            digest = await asyncio.to_thread(digest_file, path)
            old = cached.get(str(path))
            if old and old['digest'] == digest:
                paper, chunks = json.loads(old['paper']), json.loads(old['chunks'])
            else:
                parsed = await parse_pdf(path, self.config)
                if await asyncio.to_thread(digest_file, path) != digest:
                    raise AppError('PDF_CHANGED', 'PDF 在解析期间发生变化，请重试。', 409)
                paper_id = 'paper-' + hashlib.sha256((str(path) + digest).encode()).hexdigest()[:24]
                paper = {
                    'id': paper_id, 'title': parsed['title'] or path.stem,
                    'author': parsed['author'] or '作者未知', 'year': None,
                    'pages': len(parsed['pages']), 'summary': '', 'pdfAvailable': True,
                }
                chunks = []
                for page, text in enumerate(parsed['pages'], 1):
                    text = normalize(text)
                    for start in range(0, len(text), 1300):
                        passage = text[start:start+1600]
                        if len(passage.strip()) < 20:
                            continue
                        chunk_id = f'{paper_id}-p{page}-c{start}'
                        chunks.append({'id': chunk_id, 'paper': paper, 'page': page, 'text': passage})
                if chunks:
                    paper['summary'] = chunks[0]['text'][:220]
            pages += paper['pages']
            if pages > self.config.max_total_pages:
                raise AppError('LIBRARY_TOO_LARGE', '文献总页数超过配置限制。')
            if not chunks:
                warnings.append(f'{paper["title"]}：未提取到文字，可能需要 OCR。')
            records.append({'id': paper['id'], 'path': str(path), 'digest': digest, 'paper': paper, 'chunks': chunks})
        self.store.bind(project_id, scope.workdir, scope.id)
        self.store.replace_papers(scope.id, records)
        return [c for r in records for c in r['chunks']], warnings

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


def search(chunks, query: str, limit=6):
    """Bounded in-memory BM25 over page-preserving passages; English words + CJK bigrams."""
    query_terms = set(tokens(query))
    if not chunks or not query_terms:
        return []
    counts = [Counter(tokens(c['text'] + ' ' + c['paper']['title'])) for c in chunks]
    lengths = [sum(c.values()) for c in counts]
    average = sum(lengths) / len(lengths) or 1
    df = {t: sum(t in count for count in counts) for t in query_terms}
    ranked = []
    for chunk, count, length in zip(chunks, counts, lengths):
        score = 0.0
        for term in query_terms:
            frequency = count[term]
            inverse = math.log(1 + (len(chunks) - df[term] + .5) / (df[term] + .5))
            score += inverse * frequency * 2.2 / (frequency + 1.2 * (.25 + .75 * length / average))
        if score > 0:
            ranked.append((score, chunk['id'], chunk))
    ranked.sort(key=lambda r: (-r[0], r[1]))
    # Limit repeated passages on the same page so several papers can be represented.
    result, per_page = [], Counter()
    for _, _, chunk in ranked:
        key = (chunk['paper']['id'], chunk['page'])
        if per_page[key] >= 2:
            continue
        per_page[key] += 1
        result.append(chunk)
        if len(result) == limit:
            break
    return result
