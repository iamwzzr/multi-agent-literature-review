"""Repeatable HTTP acceptance against the running backend; --live permits paid calls."""
import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true', required=True)
    parser.add_argument('--cases', default='insufficient,comparison,online,hybrid,upload,budget')
    parser.add_argument('--base-url', default='http://127.0.0.1:35549')
    parser.add_argument('--model-calls', type=int, default=18)
    parser.add_argument('--seconds', type=int, default=300)
    args = parser.parse_args()
    if not 1 <= args.model_calls <= 60 or not 1 <= args.seconds <= 600:
        parser.error('model-calls must be 1..60 and seconds must be 1..600')
    if not set(args.cases.split(',')) <= {'local','insufficient','comparison','online','hybrid','upload','budget'}:
        parser.error('Unknown acceptance case')
    folder = settings.workspace_root / 'data/manual-test-results' / datetime.now().strftime('%Y%m%d-%H%M%S')
    folder.mkdir(parents=True, exist_ok=True)
    print('RESULTS_FOLDER', folder, flush=True)
    headers = {}
    token = settings.access_token.get_secret_value()
    if token:
        headers['Authorization'] = 'Bearer ' + token
    summary = []

    def save(name, data):
        (folder / (name + '.json')).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    with httpx.Client(base_url=args.base_url, headers=headers, timeout=650, trust_env=False) as client:
        health = client.get('/health')
        health.raise_for_status()
        assert health.json()['status'] == 'ok'
        print('HEALTH ok', flush=True)
        # No model calls: invalid upload, missing directory, missing run and project isolation.
        invalid_upload = client.post('/api/v2/projects/acceptance-negative/uploads', content=b'not PDF', headers={'Content-Type':'application/pdf'})
        wrong_type = client.post('/api/v2/projects/acceptance-negative/uploads', content=b'not PDF', headers={'Content-Type':'text/plain'})
        assert invalid_upload.status_code == 422 and wrong_type.status_code == 415
        missing_run = client.get('/api/v1/runs/does-not-exist-' + uuid4().hex)
        assert missing_run.status_code == 404

        def payload(name):
            return {
                'conversationId': 'acceptance-' + uuid4().hex,
                'project': {'id':'system-check-' + name, 'name':'Backend acceptance',
                    'workingDirectory':str(settings.workspace_root), 'knowledgePaths':['data/papers']},
                'source_mode':'local',
                'question':'仅比较本地 RAG 与 Self-RAG 是否按需检索，给出两条有原文依据的结论、一行比较和适用限制。重要结论提供 PDF 页码，不使用外部结论。',
                'output_requirements':{'language':'zh-CN','max_claims':3},
                'research_budget':{'documents':4,'feedback_batches':1,'model_calls':args.model_calls,'tool_calls':90,'seconds':args.seconds}}

        bad = payload('negative')
        bad['project']['knowledgePaths'] = ['data/does-not-exist-' + uuid4().hex]
        bad_response = client.post('/api/v2/reviews/stream', json=bad)
        assert 400 <= bad_response.status_code < 500
        save('negative-http', {'invalid_upload':invalid_upload.json(), 'invalid_directory':bad_response.json(), 'missing_run':missing_run.json()})
        print('NEGATIVE_HTTP passed', flush=True)

        # Real TCP cancellation; close after first phase before waiting for generation.
        cancel = payload('cancel')
        with client.stream('POST','/api/v2/reviews/stream',json=cancel) as response:
            response.raise_for_status()
            cancel_id = response.headers['x-run-id']
            for line in response.iter_lines():
                if line.strip():
                    assert json.loads(line)['type'] == 'phase'
                    break
        for _ in range(100):
            cancelled = client.get('/api/v1/runs/' + cancel_id).json()
            if cancelled['status'] == 'cancelled':
                break
            time.sleep(.1)
        assert cancelled['status'] == 'cancelled'
        with client.stream('POST','/api/v2/reviews/stream',json=cancel) as response:
            response.raise_for_status()
            retry_id = response.headers['x-run-id']
            next(line for line in response.iter_lines() if line.strip())
        for _ in range(100):
            retried = client.get('/api/v1/runs/' + retry_id).json()
            if retried['status'] == 'cancelled': break
            time.sleep(.1)
        assert retried['status'] == 'cancelled'
        save('cancel', {'first':cancelled, 'retry':retried})
        print('CANCELLATION_AND_RETRY passed', flush=True)

        for name in args.cases.split(','):
            request = payload(name)
            if name == 'insufficient':
                request['question'] = '仅根据本地 RAG 和 Self-RAG，是否报告了完全相同硬件、模型和数据集下每次回答的人民币成本？没有则明确未找到，禁止估算或补写。最多两条主张。'
            elif name == 'comparison':
                request['question'] = '仅根据本地 RAG 和 Self-RAG，能否得出 Self-RAG 在所有任务上均优于 RAG？核对模型、数据集和指标，指出不能直接比较之处；最多两条主张和一行比较，提供原文页码。'
            elif name in ('online','hybrid'):
                request['source_mode'] = name
                request['online_query'] = 'ti:"Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks"'
                if name == 'online':
                    request['project']['knowledgePaths'] = []
                    request['question'] = '仅根据在线取得的 RAG 原始论文，用两条主张说明检索和生成机制，给出原文证据及页码。'
                else:
                    request['question'] += '如证据不足，可受控联网补证，明确来源和未解决问题。'
            elif name == 'upload':
                uploaded = client.post('/api/v2/projects/'+request['project']['id']+'/uploads',
                    content=(settings.workspace_root/'data/papers/Lewis_2020_Retrieval_Augmented_Generation.pdf').read_bytes(),
                    headers={'Content-Type':'application/pdf'})
                uploaded.raise_for_status()
                fid = uploaded.json()['file_id']
                assert client.get('/api/v2/projects/wrong-project/objects/'+fid).status_code == 404
                request['project']['knowledgePaths'] = []
                request['uploaded_file_ids'] = [fid]
                request['question'] = '仅根据上传论文，用一条主张概括检索机制，提供原文引用及 PDF 页码。'
            elif name == 'budget':
                request['research_budget']['model_calls'] = 1
            elif name != 'local':
                raise ValueError('Unknown case ' + name)

            print('START', name, flush=True)
            started = time.monotonic()
            stream = []
            try:
                with client.stream('POST','/api/v2/reviews/stream',json=request) as response:
                    response.raise_for_status()
                    run_id = response.headers['x-run-id']
                    for line in response.iter_lines():
                        if not line.strip(): continue
                        event = json.loads(line)
                        stream.append(event)
                        if event['type'] in ('phase','done','error'):
                            print(name, json.dumps(event, ensure_ascii=True), flush=True)
                data = client.get('/api/v1/runs/'+run_id).json()
                save(name, {'request':request,'events':stream,'run':data})
                report = data.get('report') or {}
                displayed = json.dumps(report.get('sections',[]), ensure_ascii=False)
                assert 'evidence-' not in displayed, 'Internal evidence ID leaked into delivered prose'
                numbers = [int(n) for n in re.findall(r'\[\[(\d+)\]\]', displayed)]
                assert all(1 <= n <= len(report.get('evidence',[])) for n in numbers)
                assert stream and stream[-1]['type'] == 'done', 'Execution error instead of task result'
                if report.get('task_status') == 'completed':
                    review = report['review']
                    assert report['verification'] == 'passed' and review['verdict'] == 'pass'
                    assert review['reviewed_report_version'] == report['report_version']
                    assert review['reviewed_evidence_snapshot_id'] == report['evidence_snapshot_id']
                if name == 'budget':
                    assert report['task_status'] in ('partial','blocked') and report['verification'] != 'passed'
                    assert report.get('usage',{}).get('model_calls',0) <= 1
                if request['source_mode'] == 'local':
                    assert not any(a['kind'] == 'source_query' for a in data.get('artifacts',[]))
                for item in report.get('evidence',[]):
                    pdf = client.get('/api/v1/papers/pdf',params={'projectId':request['project']['id'],'paperId':item['paper']['id']})
                    assert pdf.status_code == 200 and pdf.content.startswith(b'%PDF')
                    assert 1 <= item['page'] <= item['paper']['pages']
                queries = sum(a['kind']=='source_query' for a in data.get('artifacts',[]))
                result = {'case':name,'run_id':run_id,'execution':'passed','task_status':report.get('task_status'),
                    'verdict':(report.get('review') or {}).get('verdict'),'evidence':len(report.get('evidence',[])),
                    'source_queries':queries,'usage':report.get('usage'),'seconds':round(time.monotonic()-started,1)}
            except Exception as error:
                result = {'case':name,'execution':'failed','exception':type(error).__name__,'message':str(error),'seconds':round(time.monotonic()-started,1)}
            summary.append(result)
            save('summary',summary)
            print('CASE_RESULT',json.dumps(result,ensure_ascii=True),flush=True)
    print('ACCEPTANCE_FINISHED', folder, flush=True)
    if any(item['execution'] == 'failed' for item in summary):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
