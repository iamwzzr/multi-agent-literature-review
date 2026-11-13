"""Explicit opt-in live acceptance. Never collected by pytest; uses real API credits."""
import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import settings
from app.store import Store
from app.library import Library,resolve_project
from app.schemas import ReviewRequest
from app.model import ModelClient
from app.research.engine import ThreeAgentWorkflow

async def run(args):
    ModelClient(settings).check()
    request=ReviewRequest(conversationId='three-agent-acceptance',project={
        'id':'acceptance-'+args.mode,'name':'Acceptance','workingDirectory':str(settings.workspace_root),
        'knowledgePaths':['data/papers'] if args.mode!='online' else []},question=args.question,
        source_mode=args.mode,online_query=args.query,
        output_requirements={'language':'zh-CN','max_claims':3},
        research_budget={'feedback_batches':1,'model_calls':24,'seconds':400})
    store=Store(settings.runtime_dir); run_id='acceptance-'+uuid4().hex
    store.start(run_id,request)
    flow=ThreeAgentWorkflow(settings,store,Library(settings,store),None,run_id)
    try:
        async for event in flow.run(request,resolve_project(request.project,settings)):
            if event['type'] in ('phase','done'): print(json.dumps(event,ensure_ascii=True),flush=True)
        store.finish(run_id,'completed',flow.report)
        print('RESULT',json.dumps({'run':run_id,'task_status':flow.report['task_status'],
            'verification':flow.report['verification'],'claims':len(flow.report.get('claims',[])),
            'evidence':len(flow.report['evidence']),'usage':flow.report.get('usage')},ensure_ascii=True),flush=True)
    except Exception as error:
        code=getattr(error,'code',type(error).__name__)
        store.finish(run_id,'failed',code=code)
        print('FAILED',code,flush=True)
        raise SystemExit(1)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--live',action='store_true',required=True,help='Explicit consent to paid model calls')
    parser.add_argument('--mode',choices=['local','online','hybrid'],default='local')
    parser.add_argument('--question',default='仅比较 RAG 与 Self-RAG 是否按需检索；给出两条主张和一行比较表。证据不足要说明。')
    parser.add_argument('--query',default='ti:"Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks"')
    asyncio.run(run(parser.parse_args()))
