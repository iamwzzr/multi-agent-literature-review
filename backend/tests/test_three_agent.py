import asyncio
import json
from copy import deepcopy

import httpx
import pytest

from app.errors import AppError
from app.research.contracts import Budget, ResearchOutput, ReportOutput, ReviewOutput, delivery_allowed
from app.research.engine import ThreeAgentWorkflow
from app.research.sources import AcademicSources, correspondence
from app.research.workspace import Workspace, Meter
from app.schemas import ReviewRequest
from app.store import Store
from app.library import Library, resolve_project
from test_business import setup, local_client, ScriptedModel, output, events
from app.main import create_app


class Trio:
    def __init__(self, owner=None, bad_id=False, requests=False):
        self.roles, self.owner, self.bad_id = [], owner, bad_id
        self.reviews = 0
        self.requests = requests

    async def invoke(self, role, payload, schema, tools, meter):
        meter.charge('model',role)
        self.roles.append(role)
        if role == 'researcher':
            span=payload['initial_passages'][0]
            return ResearchOutput(status='success',evidence=[{'span_id':span['id'],'finding':'Retrieval improved coverage.','conditions':{'dataset':None}}])
        if role == 'reporter':
            eid='invented' if self.bad_id else payload['evidence'][0]['evidence_id']
            return ReportOutput(status='success', claims=[{'text':'Retrieval improved coverage.','kind':'finding','evidence_ids':[eid],'scope':'this experiment'}],
                comparison_table=[{'cells':{'finding':'improved coverage'},'evidence_ids':[eid]}],
                evidence_requests=['retrieve cost information'] if self.requests else [])
        self.reviews+=1
        claims=payload['report']['claims']
        issue=bool(self.owner and self.reviews==1)
        return ReviewOutput(status='success',verdict='revise' if issue else 'pass',
            checked_claim_ids=[c['claim_id'] for c in claims],unchecked_claim_ids=[],
            issues=[{'claim_id':claims[0]['claim_id'],'owner':self.owner,'severity':'blocking','problem':'missing scope','required_fix':'narrow statement'}] if issue else [])


def test_three_roles_local_policy_and_versions(setup, monkeypatch):
    config,payload,_=setup
    async def forbidden(*args,**kwargs):
        raise AssertionError('Local mode must not query academic services')
    monkeypatch.setattr(AcademicSources,'request',forbidden)
    trio=Trio()
    with local_client(create_app(config,ScriptedModel(),research_agents=trio)) as client:
        response=client.post('/api/v2/reviews/stream',json=payload)
        report=output(events(response))
        assert report['evidence']
        run=client.get('/api/v1/runs/'+response.headers['x-run-id']).json()
        assert run['report']['task_status']=='completed'
        assert run['report']['review']['reviewed_report_version']==run['report']['report_version']
        assert run['report']['review']['reviewed_evidence_snapshot_id']==run['report']['evidence_snapshot_id']
        assert '未外部核实' in run['report']['evidence'][0]['paper']['summary']
        assert run['report']['comparison_table']
        assert trio.roles==['researcher','reporter','reviewer']


@pytest.mark.parametrize('owner,expected',[('reporter',1),('researcher',2)])
def test_targeted_owner_routing(setup,owner,expected):
    config,payload,_=setup
    trio=Trio(owner=owner)
    with local_client(create_app(config,ScriptedModel(),research_agents=trio)) as client:
        response=client.post('/api/v2/reviews/stream',json=payload)
        assert events(response)[-1]['taskStatus']=='completed'
        assert trio.roles.count('researcher')==expected
        assert trio.roles.count('reporter')==2


def test_reporter_evidence_request_and_feedback_limit(setup):
    config,payload,_=setup
    payload['research_budget']={'feedback_batches':1}
    trio=Trio(requests=True)
    with local_client(create_app(config,ScriptedModel(),research_agents=trio)) as client:
        lines=events(client.post('/api/v2/reviews/stream',json=payload))
        assert lines[-1]['type']=='done'
        assert trio.roles.count('researcher')==2
        assert trio.roles.count('reporter')==2


def test_no_fake_evidence_and_budget_not_pass(setup):
    config,payload,_=setup
    with local_client(create_app(config,ScriptedModel(),research_agents=Trio(bad_id=True))) as client:
        assert events(client.post('/api/v2/reviews/stream',json=payload))[-1]['code']=='UNKNOWN_EVIDENCE'
    payload['research_budget']={'model_calls':1}
    with local_client(create_app(config,ScriptedModel(),research_agents=Trio())) as client:
        response=client.post('/api/v2/reviews/stream',json=payload)
        assert events(response)[-1]['taskStatus']=='blocked'
        run=client.get('/api/v1/runs/'+response.headers['x-run-id']).json()
        assert run['report']['verification']!='passed'


def test_gate_rejects_stale_review_and_online_identity():
    report={'report_version':2,'evidence_snapshot_id':'s2','claims':[{'claim_id':'c','kind':'finding','evidence_ids':['e']}]}
    review={'status':'success','verdict':'pass','reviewed_report_version':2,'reviewed_evidence_snapshot_id':'s2','checked_claim_ids':['c'],'unchecked_claim_ids':[],'issues':[]}
    evidence=[{'evidence_id':'e','paper_id':'p','correspondence':'matched'}]
    papers=[{'paper_id':'p','source':'online','identity_status':'verified'}]
    assert delivery_allowed(report,review,evidence,papers)
    stale=deepcopy(review);stale['reviewed_report_version']=1
    assert not delivery_allowed(report,stale,evidence,papers)
    stale=deepcopy(review);stale['reviewed_evidence_snapshot_id']='old'
    assert not delivery_allowed(report,stale,evidence,papers)
    papers[0]['identity_status']='unresolved'
    assert not delivery_allowed(report,review,evidence,papers)
    papers[0]['identity_status']='verified';evidence[0]['correspondence']='mismatch'
    assert not delivery_allowed(report,review,evidence,papers)


def test_wrong_pdf_not_matched():
    p={'title':'Correct Paper','authors':['Jane Smith'],'arxiv_id':'2005.11401v1'}
    assert correspondence(p,'Completely different paper by John Jones')=='unresolved'
    assert correspondence(p,'Correct Paper Jane Smith arXiv:2005.11401v2')=='mismatch'
    assert correspondence(p,'Correct Paper Jane Smith arXiv:2005.11401v1')=='matched'


def test_immutable_objects_project_isolation(setup):
    config,_,_=setup
    store=Store(config.runtime_dir)
    a=Workspace(store,'a','run');b=Workspace(store,'b','run')
    a.save('document',{'hash':'one'},'d')
    assert a.get('d')['hash']=='one'
    with pytest.raises(AppError): b.get('d')
    with pytest.raises(AppError): a.save('document',{'hash':'two'},'d')


def test_upload_and_reference(setup):
    config,payload,papers=setup
    with local_client(create_app(config,ScriptedModel(),research_agents=Trio())) as client:
        response=client.post('/api/v2/projects/project-1/uploads',content=(papers/'study.pdf').read_bytes(),headers={'Content-Type':'application/pdf'})
        assert response.status_code==200
        fid=response.json()['file_id']
        assert client.get('/api/v2/projects/other/objects/'+fid).status_code==404
        payload['uploaded_file_ids']=[fid]
        payload['project']['knowledgePaths']=[]
        assert events(client.post('/api/v2/reviews/stream',json=payload))[-1]['taskStatus']=='completed'


def test_service_empty_error_and_identity_conflict(setup,monkeypatch):
    config,_,_=setup
    store=Store(config.runtime_dir);ws=Workspace(store,'p','r');meter=Meter(Budget(),ws)
    calls=[]
    atom='''<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/2005.11401v1</id><title>Correct Paper</title><author><name>Jane Smith</name></author><published>2020-01-01</published></entry></feed>'''
    def handler(request):
        calls.append(str(request.url))
        raw=atom if len(calls)==1 else atom.replace('Correct Paper','Wrong Paper')
        return httpx.Response(200,content=raw)
    service=AcademicSources(config,ws,meter,httpx.MockTransport(handler))
    async def no_sleep(*args): pass
    monkeypatch.setattr('app.research.sources.asyncio.sleep',no_sleep)
    found,gaps=asyncio.run(service.discover('retrieval','online'))
    assert found[0]['identity_status']=='conflict'
    assert len(calls)==2
    with pytest.raises(PermissionError): asyncio.run(service.discover('q','local'))
    empty=AcademicSources(config,ws,meter,httpx.MockTransport(lambda r:httpx.Response(200,content='<feed xmlns="http://www.w3.org/2005/Atom"/>')))
    assert asyncio.run(empty.discover('q','online'))==([],[])
    failed=AcademicSources(config,ws,meter,httpx.MockTransport(lambda r:httpx.Response(403)))
    assert asyncio.run(failed.discover('q','online'))[1]==['HTTP_403']


def test_langchain_create_agent_structured_execution(setup):
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage
    from langchain.agents import create_agent
    from langchain.agents.structured_output import ToolStrategy
    class BindableFake(FakeMessagesListChatModel):
        def bind_tools(self,tools,**kwargs): return self
    model=BindableFake(responses=[AIMessage(content='',tool_calls=[{'name':'ResearchOutput','args':{'status':'partial','evidence':[]},'id':'call1'}])])
    agent=create_agent(model=model,tools=[],response_format=ToolStrategy(ResearchOutput,handle_errors=False))
    result=asyncio.run(agent.ainvoke({'messages':[{'role':'user','content':'test'}]}))
    assert result['structured_response'].status=='partial'


def test_hybrid_gap_supplement_and_local_lookup_policy(setup,monkeypatch):
    config,payload,_=setup
    queried=[]
    async def discover(self,query,mode):
        queried.append(mode)
        return [],['AUTHORITY_TIMEOUT']
    monkeypatch.setattr(AcademicSources,'discover',discover)
    trio=Trio(requests=True)
    payload['source_mode']='hybrid'
    payload['research_budget']={'feedback_batches':1}
    with local_client(create_app(config,ScriptedModel(),research_agents=trio)) as client:
        response=client.post('/api/v2/reviews/stream',json=payload)
        assert events(response)[-1]['taskStatus']=='partial'
        assert queried==['hybrid']
    payload['source_mode']='local';payload['allow_local_metadata_lookup']=True
    looked=[]
    async def lookup(self,header,allowed):
        looked.append(allowed)
        return {'identity_status':'unresolved'}
    monkeypatch.setattr(AcademicSources,'lookup_local',lookup)
    with local_client(create_app(config,ScriptedModel(),research_agents=Trio())) as client:
        assert events(client.post('/api/v2/reviews/stream',json=payload))[-1]['type']=='done'
        assert looked==[True]


def test_online_without_fulltext_is_blocked_not_empty_search(setup,monkeypatch):
    config,payload,_=setup
    async def discover(self,query,mode):
        return [{'paper_id':'p','title':'Known paper','identity_status':'verified','source':'online'}],[]
    async def fetch(self,paper):
        return None,'FULL_TEXT_UNAVAILABLE:HTTP_403'
    monkeypatch.setattr(AcademicSources,'discover',discover)
    monkeypatch.setattr(AcademicSources,'fetch',fetch)
    payload['source_mode']='online'
    with local_client(create_app(config,ScriptedModel(),research_agents=Trio())) as client:
        response=client.post('/api/v2/reviews/stream',json=payload)
        assert events(response)[-1]['taskStatus']=='blocked'
        run=client.get('/api/v1/runs/'+response.headers['x-run-id']).json()
        assert 'FULL_TEXT_UNAVAILABLE' in str(run['report']['unresolved'])
        assert any(a['kind']=='paper_candidate' for a in run['artifacts'])


def test_document_version_pdf_route(setup):
    config,payload,_=setup
    with local_client(create_app(config,ScriptedModel(),research_agents=Trio())) as client:
        response=client.post('/api/v2/reviews/stream',json=payload)
        report=output(events(response))
        paper=report['evidence'][0]['paper']
        original=client.get('/api/v1/papers/pdf',params={'projectId':payload['project']['id'],'paperId':paper['id']})
        assert original.status_code==200 and original.content.startswith(b'%PDF')
        assert client.get('/api/v1/papers/pdf',params={'projectId':'wrong','paperId':paper['id']}).status_code==404


def test_v2_cannot_downgrade_architecture(setup):
    config,payload,_=setup
    payload['architecture']='legacy'
    with local_client(create_app(config,ScriptedModel(),research_agents=Trio())) as client:
        assert client.post('/api/v2/reviews/stream',json=payload).status_code==422


def test_parallel_artifact_writes_are_atomic(setup):
    from concurrent.futures import ThreadPoolExecutor
    config,_,_=setup
    store=Store(config.runtime_dir)
    def write(i): store.artifact('parallel-run','tool',{'n':i})
    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(write,range(100)))
    with store.connect() as db:
        rows=db.execute('SELECT seq,payload FROM artifacts WHERE run_id=? ORDER BY seq',('parallel-run',)).fetchall()
    assert [r['seq'] for r in rows]==list(range(1,101))
    assert {json.loads(r['payload'])['n'] for r in rows}==set(range(100))


def test_evidence_registry_deduplicates_and_caps_concurrent_writes(setup):
    from concurrent.futures import ThreadPoolExecutor
    from app.research.context import EvidenceRegistry
    config,_,_=setup
    ws=Workspace(Store(config.runtime_dir),'context-test','r')
    spans={str(i):{'id':str(i),'document_id':'d','paper_id':'p','page':1,'text':'real original passage'} for i in range(100)}
    cards=[]
    registry=EvidenceRegistry(lambda:spans,{'d':{'correspondence':'user_provided'}},ws,cards)
    with ThreadPoolExecutor(max_workers=12) as pool:
        same=list(pool.map(lambda i:registry.add('0','finding '+str(i),{}),range(100)))
    assert len(cards)==1 and len({e['evidence_id'] for e in same})==1
    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(lambda i:registry.add(str(i),'finding',{}),range(100)))
    assert len(cards)==12
    assert len({e['span_ids'][0] for e in cards})==12


def test_reporter_context_stays_bounded_without_changing_originals():
    from app.research.context import evidence_view,report_view
    evidence=[{'evidence_id':str(i),'document_id':'d','paper_id':'p','location':{'page':1},
        'quote':'q'*1600,'finding':'f'*1600,'conditions':{'method':'x'*10000}} for i in range(12)]
    draft={'report_id':'r','report_version':2,'claims':[{'claim_id':str(i),'kind':'finding','text':'t'*3000,'evidence_ids':['0']} for i in range(30)]}
    full=json.dumps({'evidence':evidence,'previous_report':draft})
    compact=json.dumps({'evidence':evidence_view(evidence),'previous_report':report_view(draft)})
    assert len(full)>65000 and len(compact)<40000
    assert len(evidence[0]['quote'])==1600 and len(draft['claims'][0]['text'])==3000
    assert report_view(draft)['is_preview'] is True


def test_review_context_long_pages_batched_without_mutating_sources():
    from app.research.context import review_payloads
    source='prefix '*10000+'EXACT QUOTATION'+' suffix'*10000
    original={'status':'ok','data':{'document_id':'d','page':1,'content_hash':'hash','text':source}}
    evidence=[{'evidence_id':'e','document_id':'d','paper_id':'p','location':{'page':1},'quote':'EXACT QUOTATION'}]
    report={'report_id':'r','report_version':3,'evidence_snapshot_id':'s','claims':[
        {'claim_id':str(i),'kind':'finding','text':'Claim '*300,'evidence_ids':['e']} for i in range(9)],
        'comparison_table':[{'unused':'large'*20000}],'issue_responses':[{'unneeded':'x'*100000}]}
    payloads=review_payloads({'question':'test'},report,evidence,[],[original],[],10000)
    assert len(payloads)>=3
    assert all(len(json.dumps(p,ensure_ascii=False))<=10000 for p in payloads)
    assert [c['claim_id'] for p in payloads for c in p['report']['claims']]==[str(i) for i in range(9)]
    for payload in payloads:
        window=payload['original_pages'][0]['windows'][0]
        text=' '.join(source.split())
        assert window['text']==text[window['start']:window['end']]
        assert 'EXACT QUOTATION' in window['text']
        assert payload['original_pages'][0]['is_excerpt'] is True
    assert len(original['data']['text'])>100000


def test_review_rejects_quote_not_in_original():
    from app.research.context import original_windows
    with pytest.raises(AppError) as error:
        original_windows([{'data':{'document_id':'d','page':1,'text':'real source','content_hash':'hash'}}],
            [{'document_id':'d','location':{'page':1},'quote':'fabricated','evidence_id':'e'}])
    assert error.value.code=='EVIDENCE_ORIGINAL_MISMATCH'
