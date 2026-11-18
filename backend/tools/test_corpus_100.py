"""Measure retrieval against pinned PDF pages and smoke-test the review HTTP route."""

import asyncio
import hashlib
import json
import tempfile
import time
from pathlib import Path

from prepare_corpus_100 import PAPERS, ROOT, load_manifest, verify_corpus
from test_corpus_offline import ContractAgents, NoModel
from fastapi.testclient import TestClient
from app.config import Settings
from app.errors import AppError
from app.library import Library, SearchIndex, normalize, resolve_project
from app.main import create_app
from app.schemas import Project
from app.store import Store

CASES = ROOT / 'docs/testing/agent-capability-cases.json'
OUTPUT = ROOT / 'data/manual-test-results/corpus-100-offline.json'
REVIEW_BUDGET = 10


async def retrieval_report(config, papers, cases, project):
    store = Store(config.runtime_dir)
    library = Library(config, store)
    scope = resolve_project(project, config)
    old_limit = Library(config.model_copy(update={'max_papers': 40}), store)
    try:
        old_limit.discover(scope)
    except AppError as error:
        assert error.code == 'LIBRARY_TOO_LARGE'
    else:
        raise AssertionError('Expected a 100-file directory to exceed a 40-file index limit')

    start = time.perf_counter()
    chunks, warnings = await library.index(project.id, scope)
    index = SearchIndex(chunks)
    index_seconds = round(time.perf_counter() - start, 2)
    by_digest = {p['sha256']: p for p in papers}
    by_id = {row['id']: by_digest[row['digest']]['key'] for row in store.papers(scope.id).values()}
    assert len(by_id) == len({c['paper']['id'] for c in chunks}) == 100
    assert not warnings, warnings

    pages = {}
    for chunk in chunks:
        pages.setdefault((by_id[chunk['paper']['id']], chunk['page']), []).append(normalize(chunk['text']).casefold())

    def probe(query, gold):
        hits = [{'paper': by_id[c['paper']['id']], 'page': c['page']} for c in index.search(query, limit=6)]
        keys = {(hit['paper'], hit['page']) for hit in hits}
        return {'hits': hits, 'gold_pages_found': len(gold & keys), 'gold_pages_total': len(gold)}

    results = []
    for case in cases:
        gold = {(e['key'], e['page']) for e in case['evidence']}
        for e in case['evidence']:
            source = pages.get((e['key'], e['page']), [])
            for anchor in e['anchors']:
                assert any(anchor.casefold() in span for span in source), (case['id'], e['key'], e['page'], anchor)
        queries = [case['question'], *case.get('subquestions', [])]
        selected = [by_id[key] for key in index.rank_papers(queries)[:REVIEW_BUDGET]]
        question_only = {by_id[key] for key in index.rank_papers(queries[:1])[:REVIEW_BUDGET]}
        gold_papers = {key for key, _ in gold}
        result = {'case': case['id'], 'candidate_papers': selected,
                  'gold_papers_found': len(gold_papers & set(selected)),
                  'gold_papers_found_question_only': len(gold_papers & question_only),
                  'gold_papers_total': len(gold_papers)}
        if gold:
            result['question_top_6'] = probe(case['question'], gold)
            result['english_terms_top_6'] = probe(case['retrieval_query'], gold)
        results.append(result)
    return {'indexed_papers': len(by_id), 'pages': sum(p['pages'] for p in papers), 'passages': len(chunks),
            'cold_index_seconds': index_seconds, 'old_limit_error': 'LIBRARY_TOO_LARGE', 'cases': results}


def review_contract(config, papers, project):
    target = next(p for p in papers if p['key'] == 'webthinker')
    alphabetical_position = sorted(p['filename'] for p in papers).index(target['filename']) + 1
    assert alphabetical_position > 40
    request = {'conversationId': 'library-100-smoke', 'project': project.model_dump(),
               'source_mode': 'local', 'architecture': 'three_agent',
               'question': 'WebThinker Deep Web Explorer autonomous think-search-and-draft',
               'research_budget': {'documents': REVIEW_BUDGET, 'seconds': 300}}
    agents = ContractAgents()
    with TestClient(create_app(config, NoModel(), research_agents=agents),
                    base_url='http://127.0.0.1', client=('127.0.0.1', 50000)) as client:
        started = time.perf_counter()
        response = client.post('/api/v2/reviews/stream', json=request)
        assert response.status_code == 200, response.text
        events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
        assert events[-1]['type'] == 'done', events[-1]
        run = client.get('/api/v1/runs/' + response.headers['x-run-id']).json()
        report = run['report']
        assert report['task_status'] == 'completed'
        assert agents.roles == ['researcher', 'reporter', 'reviewer']
        assert report['review']['reviewed_report_version'] == report['report_version']
        assert report['review']['reviewed_evidence_snapshot_id'] == report['evidence_snapshot_id']
        selection, = [a['payload'] for a in run['artifacts'] if a['kind'] == 'local_library_selection']
        assert selection['indexed_papers'] == 100
        assert 0 < selection['admitted_local_papers'] <= REVIEW_BUDGET
        evidence, = report['evidence']
        document_id = evidence['paper']['id']
        document = client.get(f'/api/v2/projects/{project.id}/objects/{document_id}').json()
        page = evidence['page']
        assert normalize(evidence['excerpt']) in normalize(document['pages'][page - 1])
        pdf = client.get('/api/v1/papers/pdf', params={'projectId': project.id, 'paperId': document_id})
        assert pdf.status_code == 200
        assert hashlib.sha256(pdf.content).hexdigest() == document['content_hash'] == target['sha256']
        assert not any(a['kind'] == 'source_query' for a in run['artifacts'])
    return {'paper': target['key'], 'alphabetical_position': alphabetical_position, 'pdf_page': page,
            'roles': agents.roles, 'task_status': report['task_status'], 'source_matches_manifest': True,
            'review_budget': REVIEW_BUDGET, 'admitted_papers': selection['admitted_local_papers'],
            'warm_review_seconds': round(time.perf_counter() - started, 2)}


def main():
    papers = load_manifest()
    verify_corpus(papers)
    cases = json.loads(CASES.read_text(encoding='utf-8'))['cases']
    with tempfile.TemporaryDirectory(prefix='folio-corpus-100-') as temp:
        config = Settings(_env_file=None, workspace_root=ROOT, allowed_roots=[ROOT], runtime_dir=Path(temp))
        project = Project(id='corpus-100-check', name='100-paper evaluation', workingDirectory=str(ROOT),
                          knowledgePaths=[str(PAPERS)])
        result = {'paid_model_calls': 0, 'http_model': 'scripted',
                  'retrieval': asyncio.run(retrieval_report(config, papers, cases, project)),
                  'http': review_contract(config, papers, project)}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('100 PDFs verified. Offline metrics:', OUTPUT)
    for case in result['retrieval']['cases']:
        print(case['case'], 'gold papers in candidates', f"{case['gold_papers_found']}/{case['gold_papers_total']}")
    print('HTTP contract:', json.dumps(result['http'], ensure_ascii=False))


if __name__ == '__main__':
    main()
