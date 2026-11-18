"""100-real-PDF HTTP integration with scripted agents; zero paid model calls."""
import hashlib
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'backend/tools')]
from app.config import Settings
from app.main import create_app
from app.schemas import Project
from fastapi.testclient import TestClient
from prepare_corpus_100 import PAPERS,load_manifest,verify_corpus
from test_corpus_100 import review_contract
from test_corpus_offline import ContractAgents,NoModel


def main():
    papers=load_manifest();verify_corpus(papers)
    config=Settings(_env_file=None,workspace_root=ROOT,allowed_roots=[ROOT],runtime_dir=ROOT/'data/runtime/corpus-benchmark')
    project=Project(id='retrieval-benchmark',name='HTTP functional',workingDirectory=str(ROOT),knowledgePaths=[str(PAPERS)])
    result={'paid_model_calls':0,'agents':'scripted','verified_files':100,
        'review':review_contract(config,papers,project)}
    with TestClient(create_app(config,NoModel(),research_agents=ContractAgents()),base_url='http://127.0.0.1',client=('127.0.0.1',51000)) as client:
        payload={'conversationId':'anchor-http','project':project.model_dump(),
            'question':'WebThinker Deep Web Explorer autonomous think-search-and-draft','source_mode':'local',
            'research_budget':{'documents':10,'model_calls':10,'feedback_batches':0,'seconds':300}}
        response=client.post('/api/v2/reviews/stream',json=payload)
        lines=[json.loads(l) for l in response.text.splitlines() if l.strip()]
        assert lines[-1]['type']=='done',lines[-1]
        run=client.get('/api/v1/runs/'+response.headers['x-run-id']).json()
        assert run['report']['task_status']=='completed'
        evidence=run['report']['evidence'][0]
        endpoint=f"/api/v2/projects/{project.id}/evidence/{evidence['evidenceId']}/location"
        located=client.get(endpoint)
        assert located.status_code==200 and located.json()['status']=='matched'
        assert located.json()['candidates'][0]['selector']['exact']==evidence['excerpt']
        assert client.get(endpoint.replace(project.id,'another-project')).status_code==404
        result['precise_anchor']={'status':'matched','page':located.json()['page'],'cross_project':'rejected'}
        payload['conversationId']='budget-http';payload['research_budget']['model_calls']=1
        stopped=client.post('/api/v2/reviews/stream',json=payload)
        budget_run=client.get('/api/v1/runs/'+stopped.headers['x-run-id']).json()
        assert budget_run['report']['task_status'] in ('partial','blocked')
        assert budget_run['report']['verification']!='passed'
        assert budget_run['report']['usage']['model_calls']<=1
        result['budget_stop']={'task_status':budget_run['report']['task_status'],'model_calls':budget_run['report']['usage']['model_calls']}
        rag=next(p for p in papers if p['key']=='rag')
        data=(PAPERS/rag['filename']).read_bytes()
        headers={'Content-Type':'application/pdf'}
        first=client.post(f'/api/v2/projects/{project.id}/uploads',headers=headers,content=data)
        again=client.post(f'/api/v2/projects/{project.id}/uploads',headers=headers,content=data)
        assert first.status_code==again.status_code==200
        assert first.json()['file_id']==again.json()['file_id']
        assert first.json()['sha256']==rag['sha256']
        result['repeat_real_pdf_upload']='same ID and verified hash'
    target=ROOT/'data/manual-test-results/corpus-100-functional.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True))


if __name__=='__main__':main()
