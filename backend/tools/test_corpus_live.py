"""Fixed-corpus REAL model HTTP acceptance. Requires --live; uses API credits."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
from prepare_corpus_100 import PAPERS as FULL_CORPUS, load_manifest, verify_corpus
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import settings

ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--live',action='store_true',required=True,help='Make paid model calls')
    parser.add_argument('--suite', choices=('fixed','corpus-100'), default='fixed')
    parser.add_argument('--case-file',help='Optional local regression case JSON; gold checks are never sent to agents')
    parser.add_argument('--tool-calls',type=int,default=100)
    parser.add_argument('--cases',help='Comma-separated case IDs; defaults to all cases in the selected suite')
    parser.add_argument('--base-url',default='http://127.0.0.1:35549')
    parser.add_argument('--model-calls',type=int,default=24)
    parser.add_argument('--project-id',help='Reuse one project for sequential cases and its local index cache')
    parser.add_argument('--seconds',type=int,default=300)
    args=parser.parse_args()
    if not 1<=args.model_calls<=60 or not 1<=args.seconds<=600 or not 1<=args.tool_calls<=150:
        parser.error('Budget out of bounds')
    if not settings.model_api_key.get_secret_value() or not settings.model_name:
        parser.error('Configure local .env MODEL_API_KEY and MODEL_NAME; never commit credentials')
    full_suite = args.suite == 'corpus-100'
    case_file = ROOT/'docs/testing'/('agent-capability-cases.json' if full_suite else 'cases.json')
    if args.case_file:case_file=Path(args.case_file).resolve()
    cases=json.loads(case_file.read_text(encoding='utf-8'))['cases']
    wanted=args.cases.split(',') if args.cases else [case['id'] for case in cases]
    if not set(wanted)<={c['id'] for c in cases}: parser.error('Unknown case ID')
    if full_suite:
        papers = load_manifest()
        verify_corpus(papers)
    else:
        papers=json.loads((ROOT/'docs/testing/corpus.json').read_text(encoding='utf-8'))['papers']
    by_key={p['key']:p for p in papers}
    by_digest={p['sha256']:p['key'] for p in papers}
    timestamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'data/manual-test-results'/(args.suite+'-live-'+timestamp)
    out.mkdir(parents=True)
    headers={}
    if settings.access_token.get_secret_value():
        headers['Authorization']='Bearer '+settings.access_token.get_secret_value()
    summary={'executed_at':datetime.now(timezone.utc).isoformat(),'model':settings.model_name,
             'base_url':settings.model_base_url,'budget':{'model_calls_per_case':args.model_calls,'seconds_per_case':args.seconds,'tool_calls_per_case':args.tool_calls},
             'model_max_tokens':settings.model_max_tokens,'reasoning_effort':settings.model_reasoning_effort,
             'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
             'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in (ROOT/'backend/app').rglob('*.py')},
             'working_tree_dirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()),
             'requirements_sha256':hashlib.sha256((ROOT/'backend/requirements.txt').read_bytes()).hexdigest(),
             'suite': args.suite,'shared_project_id':args.project_id, 'case_file_sha256':hashlib.sha256(case_file.read_bytes()).hexdigest(),
             'corpus_sha256':{k:p['sha256'] for k,p in by_key.items()},'results':[]}
    def save(name,value):
        (out/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('RESULTS',out,flush=True)
    with httpx.Client(base_url=args.base_url,headers=headers,timeout=650,trust_env=False) as client:
        client.get('/api/v1/health').raise_for_status()
        for case_id in wanted:
            case=next(c for c in cases if c['id']==case_id)
            library = FULL_CORPUS
            if not full_suite:
                library=ROOT/'data/test-corpus/cases'/case_id
                library.mkdir(parents=True,exist_ok=True)
                for key in case['keys']:
                    p=by_key[key]
                    source=ROOT/'data/papers'/p['filename']
                    assert hashlib.sha256(source.read_bytes()).hexdigest()==p['sha256']
                    shutil.copyfile(source,library/p['filename'])
                    if source.with_suffix('.metadata.json').is_file():
                        shutil.copyfile(source.with_suffix('.metadata.json'),(library/p['filename']).with_suffix('.metadata.json'))
                assert {p.name for p in library.glob('*.pdf')}=={by_key[k]['filename'] for k in case['keys']}, 'Unexpected extra case PDFs'
            document_budget = 10 if full_suite else 3
            request={'conversationId':case_id+'-'+uuid4().hex,
                     'project':{'id':args.project_id or args.suite+'-'+timestamp+'-'+case_id,'name':args.suite+' '+case_id,
                                'workingDirectory':str(ROOT),'knowledgePaths':[str(library)]},
                     'question':case['question'],'source_mode':'local','architecture':'three_agent',
                     'output_requirements':case.get('output_requirements',{'language':'zh-CN','max_claims':3}),
                     'research_budget':{'documents':document_budget,'feedback_batches':1,'model_calls':args.model_calls,
                                       'tool_calls':args.tool_calls,'seconds':args.seconds}}
            if 'subquestions' in case:
                request['subquestions']=[{'question':q} for q in case['subquestions']]
            started=time.monotonic();events=[];run_id=None;data=None
            result={'case':case_id,'semantic_review':'pending','expected':case['expected'],'must_not':case['must_not']}
            print('START',case_id,flush=True)
            try:
                with client.stream('POST','/api/v2/reviews/stream',json=request) as response:
                    response.raise_for_status();run_id=response.headers['x-run-id']
                    for line in response.iter_lines():
                        if not line.strip(): continue
                        event=json.loads(line);events.append(event)
                        if event['type'] in ('phase','done','error'):
                            print(case_id,json.dumps(event,ensure_ascii=True),flush=True)
                data=client.get('/api/v1/runs/'+run_id).json()
                save(case_id,{'request':request,'events':events,'run':data})
                report=data.get('report') or {}
                markdown=['# '+case_id+' - Actual model report',
                          'Model: '+settings.model_name+'; run_id: '+run_id,
                          'task_status: '+str(report.get('task_status')),
                          'verification: '+str(report.get('verification'))]
                for section in report.get('sections',[]):
                    markdown.extend(['\n## '+section['heading'],*section['paragraphs']])
                (out/(case_id+'.md')).write_text('\n\n'.join(markdown)+'\n',encoding='utf-8')
                assert events and events[-1]['type']=='done','Stream did not finish normally'
                displayed=json.dumps(report.get('sections',[]),ensure_ascii=False)
                numbers=[int(n) for n in re.findall(r'\[\[(\d+)\]\]',displayed)]
                assert 'evidence-' not in displayed
                assert all(1<=n<=len(report.get('evidence',[])) for n in numbers)
                if report.get('task_status')=='completed':
                    review=report['review']
                    assert report['verification']=='passed' and review['verdict']=='pass'
                    assert review['reviewed_report_version']==report['report_version']
                    assert review['reviewed_evidence_snapshot_id']==report['evidence_snapshot_id']
                verified=0
                cited_pages=set()
                for e in report.get('evidence',[]):
                    document=client.get('/api/v2/projects/'+request['project']['id']+'/objects/'+e['paper']['id']).json()
                    assert ' '.join(e['excerpt'].split()) in ' '.join(document['pages'][e['page']-1].split())
                    response=client.get('/api/v1/papers/pdf',params={'projectId':request['project']['id'],'paperId':e['paper']['id']})
                    response.raise_for_status()
                    assert hashlib.sha256(response.content).hexdigest()==document['content_hash']
                    cited_pages.add((by_digest[document['content_hash']], e['page']))
                    verified+=1
                artifacts = data.get('artifacts',[])
                assert not any(a['kind']=='source_query' for a in artifacts)
                if full_suite:
                    selection, = [a['payload'] for a in artifacts if a['kind'] == 'local_library_selection']
                    assert selection['indexed_papers'] == len(papers)
                    assert selection['admitted_local_papers'] <= document_budget
                    gold = {(e['key'],e['page']) for e in case['evidence']}
                    result.update(indexed_papers=selection['indexed_papers'],
                                  selected_papers=selection['admitted_local_papers'],
                                  gold_cited_pages=len(gold & cited_pages), gold_total_pages=len(gold),
                                  cited_pages=sorted(cited_pages),
                                  feedback_batches=sum(a['kind']=='feedback_batch' for a in artifacts))
                result.update(execution='passed',run_id=run_id,task_status=report.get('task_status'),
                              verification=report.get('verification'),verdict=(report.get('review') or {}).get('verdict'),
                              evidence_checked=verified,usage=report.get('usage'))
            except Exception as error:
                # Never serialize request headers, API errors with raw auth, or model credentials.
                backend_code=(data or {}).get('error_code') or next((e.get('code') for e in reversed(events) if e['type']=='error'),None)
                result.update(execution='failed',run_id=run_id,error_type=type(error).__name__,backend_error_code=backend_code)
                save(case_id,{'request':request,'events':events,'run':data,'error_type':type(error).__name__})
            result['seconds']=round(time.monotonic()-started,2)
            summary['results'].append(result);save('summary',summary)
            print('RESULT',json.dumps(result,ensure_ascii=True),flush=True)
    if any(r['execution']=='failed' for r in summary['results']): raise SystemExit(1)


if __name__=='__main__':
    main()
