"""Real PDF parsing/retrieval and simulated-agent HTTP contract checks; zero API calls."""
import asyncio
import hashlib
import json
import platform
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from app.config import Settings
from app.library import Library, SearchIndex, normalize, parse_pdf, resolve_project
from app.main import create_app
from app.research.contracts import ResearchOutput, ReportOutput, ReviewOutput
from app.research.sources import correspondence
from app.schemas import Project
from app.store import Store

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'data/manual-test-results/corpus-offline'


class NoModel:
    def check(self):
        pass


class ContractAgents:
    """Deliberately scripted. Passing its Reviewer is NOT a model quality result."""
    def __init__(self, owner=None):
        self.owner, self.roles, self.reviews = owner, [], 0

    async def invoke(self, role, payload, schema, tools, meter):
        meter.charge('model', role)
        self.roles.append(role)
        if role == 'researcher':
            span = payload['initial_passages'][0]
            return ResearchOutput(status='success', evidence=[{
                'span_id':span['id'], 'finding':'Scripted transport check only.', 'conditions':{}}])
        if role == 'reporter':
            eid = payload['evidence'][0]['evidence_id']
            return ReportOutput(status='success', claims=[{
                'text':'测试替身仅验证证据、引用与交付管道，不代表真实模型的语义审核。',
                'kind':'finding', 'evidence_ids':[eid], 'scope':'simulated-agent contract test only'}])
        self.reviews += 1
        issue = self.owner and self.reviews == 1
        return ReviewOutput(status='success', verdict='revise' if issue else 'pass',
            checked_claim_ids=[c['claim_id'] for c in payload['report']['claims']], unchecked_claim_ids=[],
            issues=[{'claim_id':payload['report']['claims'][0]['claim_id'], 'evidence_ids':[],
                     'owner':self.owner, 'severity':'blocking', 'problem':'Scripted feedback',
                     'required_fix':'Exercise targeted routing'}] if issue else [])


async def inspect(manifest, cases, runtime):
    config = Settings(_env_file=None, workspace_root=ROOT, allowed_roots=[ROOT], runtime_dir=runtime)
    parsed, rows, checks = {}, [], []
    for paper in manifest['papers']:
        path = ROOT / 'data/papers' / paper['filename']
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == paper['sha256'], paper['key'] + ': hash changed'
        doc = await parse_pdf(path, config)
        parsed[paper['key']] = doc
        chars = [len(t.strip()) for t in doc['pages']]
        record = dict(paper, arxiv_id=paper['arxiv_id'])
        match = correspondence(record, doc['pages'][0])
        assert sum(chars) > 5000 and chars[0] > 200, paper['key'] + ': not text-rich'
        assert match == 'matched', paper['key'] + ': identity/content ' + match
        rows.append({'key':paper['key'], 'filename':paper['filename'], 'pages':len(chars),
                     'characters':sum(chars), 'text_pages':sum(c >= 20 for c in chars),
                     'sha256':digest, 'content_correspondence':match, 'parsed':'passed'})
    for case in cases['cases']:
        for item in case['evidence']:
            text = normalize(parsed[item['key']]['pages'][item['page']-1])
            for anchor in item['anchors']:
                assert anchor.casefold() in text.casefold(), (case['id'], item, anchor)
            checks.append({'case':case['id'], **item, 'anchor_check':'passed'})
    # Deliberate metadata/PDF mismatch uses actual, different documents.
    rag = next(p for p in manifest['papers'] if p['key'] == 'rag')
    assert correspondence(rag, parsed['selfrag']['pages'][0]) == 'mismatch'
    store = Store(runtime)
    project = Project(id='fixed-corpus-index', name='Fixed corpus', workingDirectory=str(ROOT),
                      knowledgePaths=['data/test-corpus/fixed'])
    library=Library(config,store)
    chunks, warnings = await library.index(project.id, resolve_project(project, config))
    assert len({c['paper']['id'] for c in chunks}) == 3
    index = SearchIndex(chunks)
    digest_keys = {p['sha256']:p['key'] for p in manifest['papers']}
    id_keys = {}
    for c in chunks:
        source=library.source(project.id,c['paper']['id'])
        id_keys[c['paper']['id']] = digest_keys[hashlib.sha256(source.read_bytes()).hexdigest()]
    retrieval = []
    for probe in cases['retrieval_probes']:
        results = index.search(probe['query'], 6)
        hits = [{'key':id_keys[r['paper']['id']], 'page':r['page']} for r in results]
        covered = [any(h['key']==e['key'] and h['page'] in e['pages'] for h in hits)
                   for e in probe['expected']]
        retrieval.append({**probe, 'top_k':6, 'hits':hits, 'expected_covered':covered,
                          'all_expected_covered':all(covered)})
    return {'papers':rows, 'gold_anchors':checks, 'index_chunks':len(chunks),
            'index_warnings':warnings, 'retrieval':retrieval,
            'mismatched_identity_pdf':'rejected'}


def http_contract(runtime):
    config = Settings(_env_file=None, workspace_root=ROOT, allowed_roots=[ROOT], runtime_dir=runtime)
    results = []
    def record(name, passed, **extra):
        assert passed, name
        results.append({'case':name,'result':'passed','execution':'in-process HTTP, scripted agents',**extra})
    def payload(project_id, paths=None):
        return {'conversationId':'offline-contract', 'project':{'id':project_id,'name':project_id,
                'workingDirectory':str(ROOT),'knowledgePaths':paths if paths is not None else ['data/test-corpus/fixed']},
                'question':'RAG-Sequence RAG-Token document marginalization',
                'source_mode':'local','research_budget':{'feedback_batches':1}}
    def run(client, body):
        response = client.post('/api/v2/reviews/stream', json=body)
        assert response.status_code == 200, response.text
        events = [json.loads(s) for s in response.text.splitlines() if s.strip()]
        assert events[-1]['type'] == 'done', events[-1]
        run_id = response.headers['x-run-id']
        run = client.get('/api/v1/runs/' + run_id).json()
        return run, events
    agents = ContractAgents()
    with TestClient(create_app(config, NoModel(), research_agents=agents),
                    base_url='http://127.0.0.1', client=('127.0.0.1',50000)) as client:
        record('health', client.get('/api/v1/health').json()['status']=='ok')
        record('reject_non_pdf',client.post('/api/v2/projects/invalid/uploads',content=b'not-pdf',
               headers={'Content-Type':'application/pdf'}).status_code==422)
        record('reject_wrong_content_type',client.post('/api/v2/projects/invalid/uploads',content=b'not-pdf',
               headers={'Content-Type':'text/plain'}).status_code==415)
        body=payload('bad-path',['data/not-a-real-corpus'])
        record('reject_missing_directory',400<=client.post('/api/v2/reviews/stream',json=body).status_code<500)
        run_data, _ = run(client,payload('fixed-contract'))
        report=run_data['report']
        review=report['review']
        record('fixed_pdf_three_role_contract',report['task_status']=='completed' and agents.roles==['researcher','reporter','reviewer'])
        record('review_version_binding',review['reviewed_report_version']==report['report_version'] and
               review['reviewed_evidence_snapshot_id']==report['evidence_snapshot_id'])
        text=json.dumps(report['sections'],ensure_ascii=False)
        numbers=[int(n) for n in re.findall(r'\[\[(\d+)\]\]',text)]
        record('display_citation_mapping',bool(numbers) and 'evidence-' not in text and
               all(1<=n<=len(report['evidence']) for n in numbers))
        for evidence in report['evidence']:
            doc=client.get('/api/v2/projects/fixed-contract/objects/'+evidence['paper']['id']).json()
            text=normalize(doc['pages'][evidence['page']-1])
            record('original_page_excerpt',normalize(evidence['excerpt']) in text)
            response=client.get('/api/v1/papers/pdf',params={'projectId':'fixed-contract','paperId':evidence['paper']['id']})
            record('source_pdf_endpoint',response.status_code==200 and
                   hashlib.sha256(response.content).hexdigest()==doc['content_hash'])
        record('local_no_academic_network',not any(a['kind']=='source_query' for a in run_data.get('artifacts',[])))
        raw=(ROOT/'data/test-corpus/fixed/Lewis_2020_Retrieval_Augmented_Generation.pdf').read_bytes()
        response=client.post('/api/v2/projects/upload-contract/uploads',content=raw,headers={'Content-Type':'application/pdf'})
        record('real_pdf_upload',response.status_code==200)
        file_id=response.json()['file_id']
        record('upload_cross_project_isolation',client.get('/api/v2/projects/wrong/objects/'+file_id).status_code==404)
        body=payload('upload-contract',[]);body['uploaded_file_ids']=[file_id]
        uploaded,_=run(client,body)
        record('upload_only_pipeline',uploaded['report']['task_status']=='completed')
        empty,_=run(client,payload('empty-contract',[]))
        record('empty_library_blocked',empty['report']['task_status']=='blocked' and not empty['report']['evidence'])
        body=payload('budget-contract');body['research_budget']['model_calls']=1
        limited,_=run(client,body)
        record('budget_not_false_pass',limited['report']['task_status'] in ('partial','blocked') and
               limited['report']['verification']!='passed' and limited['report']['usage']['model_calls']<=1)
        # Blank-page PDF is intentionally image/textless, not part of the academic corpus.
        blank=runtime/'textless.pdf';writer=PdfWriter();writer.add_blank_page(612,792)
        with blank.open('wb') as f: writer.write(f)
        body=payload('textless-contract',[str(runtime)])
        # Keep textless in its own directory, so uploaded originals cannot be discovered.
        empty_dir=runtime/'textless';empty_dir.mkdir();blank.rename(empty_dir/'blank.pdf')
        body['project']['knowledgePaths']=[str(empty_dir)]
        textless,_=run(client,body)
        record('textless_not_invented',textless['report']['task_status']=='blocked' and not textless['report']['evidence'])
    for owner, expected in [('reporter',['researcher','reporter','reviewer','reporter','reviewer']),
                            ('researcher',['researcher','reporter','reviewer','researcher','reporter','reviewer'])]:
        agents=ContractAgents(owner)
        with TestClient(create_app(config,NoModel(),research_agents=agents),
                        base_url='http://127.0.0.1',client=('127.0.0.1',50000)) as client:
            run_data,_=run(client,payload('routing-'+owner))
            record('targeted_feedback_'+owner,agents.roles==expected and run_data['report']['task_status']=='completed')
    return results


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((ROOT/'docs/testing/corpus.json').read_text())
    cases=json.loads((ROOT/'docs/testing/cases.json').read_text())
    with tempfile.TemporaryDirectory(prefix='offline-',dir=OUT) as temp:
        runtime=Path(temp)
        result={'executed_at':datetime.now(timezone.utc).isoformat(),'python':platform.python_version(),
                'model_calls_paid':0,'scope':'Actual PDFs/backend; model agents are scripted, no semantic quality acceptance.'}
        result['corpus']=asyncio.run(inspect(manifest,cases,runtime/'index'))
        result['http_contract']=http_contract(runtime/'http')
    (OUT/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'papers':len(result['corpus']['papers']),
        'pages':sum(p['pages'] for p in result['corpus']['papers']),
        'anchors':len(result['corpus']['gold_anchors']),
        'retrieval_probes':[{ 'id':p['id'],'covered':p['all_expected_covered']} for p in result['corpus']['retrieval']],
        'http_checks':len(result['http_contract']),'paid_model_calls':0},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
