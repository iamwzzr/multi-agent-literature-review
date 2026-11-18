"""Verify actual live-suite outputs against re-read PDF bytes without model calls."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

root=Path(__file__).resolve().parents[2];sys.path[:0]=[str(root/'backend'),str(root/'backend/tools')]
from app.config import settings
from app.main import create_app
from fastapi.testclient import TestClient
from test_corpus_offline import NoModel
from prepare_corpus_100 import load_manifest

def main():
    parser=argparse.ArgumentParser();parser.add_argument('folder');args=parser.parse_args()
    folder=Path(args.folder)
    config=settings.model_copy(update={'runtime_dir':root/'data/runtime/corpus-functional'})
    headers={}
    token=config.access_token.get_secret_value()
    if token:headers['Authorization']='Bearer '+token
    by_hash={p['sha256']:p['key'] for p in load_manifest()}
    checks=[]
    with TestClient(create_app(config,NoModel()),base_url='http://127.0.0.1',client=('127.0.0.1',52000),headers=headers) as client:
        for file in sorted(folder.glob('L*.json')):
            data=json.loads(file.read_text(encoding='utf-8'))
            run=data.get('run') or {};report=run.get('report') or {}
            if not report:
                checks.append({'case':file.stem,'status':'no report','error':run.get('error_code')});continue
            project=data['request']['project']['id'];count=0
            for item in report.get('evidence',[]):
                endpoint=f"/api/v2/projects/{project}/evidence/{item['evidenceId']}/location"
                located=client.get(endpoint);assert located.status_code==200,(file.stem,located.status_code)
                anchor=located.json();assert anchor['status']=='matched',(file.stem,anchor['status'])
                assert anchor['candidates'][0]['selector']['exact']==item['excerpt']
                assert anchor['content_hash'] in by_hash
                assert anchor['page']==item['page']
                count+=1
            review=report.get('review') or {}
            if report['task_status']=='completed':
                assert review['verdict']=='pass' and report['verification']=='passed'
                assert report['report_version']==review['reviewed_report_version']
                assert report['evidence_snapshot_id']==review['reviewed_evidence_snapshot_id']
            checks.append({'case':file.stem,'task_status':report['task_status'],
                'quotes_reparsed_and_located':count,
                'quote_fallbacks':sum(a['kind']=='quote_precision_fallback' for a in run.get('artifacts',[])),
                'exact_relocations':sum(a['kind']=='quote_relocation' for a in run.get('artifacts',[])),
                'model_calls':(report.get('usage') or {}).get('model_calls')})
    target=folder/'independent-source-verification.json'
    target.write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(checks,ensure_ascii=True))

if __name__=='__main__':main()
