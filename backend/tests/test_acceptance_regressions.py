import asyncio
import hashlib
import json

import pytest
from pydantic import Field
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from app.library import Library, SearchIndex, resolve_project
from app.main import create_app
from app.research.agents import ThreeAgents
from app.research.context import original_windows
from app.research.contracts import Budget, ResearchOutput
from app.research.workspace import Meter, Workspace
from app.schemas import Project
from app.store import Store
from test_business import setup, local_client, ScriptedModel, events
from test_three_agent import Trio


@pytest.mark.parametrize('repair_mode',['valid','unknown','failed','execution_error'])
def test_invalid_spans_get_one_grounded_repair_and_are_never_auto_mapped(setup,repair_mode):
    config,payload,_=setup
    class Repair(Trio):
        async def invoke(self,role,payload,schema,tools,meter):
            if role=='researcher':
                if 'repair_instruction' in payload:
                    assert tools==[] and 1<=len(payload['candidate_originals'])<=12
                    span=payload['candidate_originals'][0]['id'] if repair_mode!='unknown' else 'still-invented'
                    if repair_mode=='failed':
                        return ResearchOutput(status='failed',evidence=[{'span_id':span,'finding':'not successful'}])
                    if repair_mode=='execution_error':
                        return ResearchOutput(status='partial',outcome='execution_error',evidence=[{'span_id':span,'finding':'not successful'}])
                else: span='invented-span-id'
                return ResearchOutput(status='success',evidence=[{'span_id':span,'finding':'retrieval coverage','conditions':{}}])
            return await super().invoke(role,payload,schema,tools,meter)
    with local_client(create_app(config,ScriptedModel(),research_agents=Repair())) as client:
        response=client.post('/api/v2/reviews/stream',json=payload)
        last=events(response)[-1]
        if repair_mode=='valid': assert last['taskStatus']=='completed'
        else:
            assert last['type']=='error'
            assert last['code']==('UNKNOWN_SPAN' if repair_mode=='unknown' else 'AGENT_FAILED')


def test_scope_qualification_is_identical_in_review_and_delivery(setup):
    from app.research.context import scoped_claim_text
    config,payload,_=setup
    class Scoped(Trio):
        async def invoke(self,role,payload,schema,tools,meter):
            if role=='reviewer':
                assert all(c['text'].startswith('适用范围：') for c in payload['report']['claims'])
            return await super().invoke(role,payload,schema,tools,meter)
    with local_client(create_app(config,ScriptedModel(),research_agents=Scoped())) as client:
        response=client.post('/api/v2/reviews/stream',json=payload)
        assert events(response)[-1]['taskStatus']=='completed'
        report=client.get('/api/v1/runs/'+response.headers['x-run-id']).json()['report']
        assert report['sections'][0]['paragraphs'][0].startswith(scoped_claim_text(report['claims'][0]))


@pytest.mark.parametrize('assessment,covered,expected_research,expected_status',[
    ('optional',True,1,'completed'),('required',True,2,'partial'),
    ('missing',True,2,'partial'),('optional',False,2,'partial')])
def test_only_explicitly_reviewed_optional_requests_can_avoid_research(setup,assessment,covered,expected_research,expected_status):
    config,payload,_=setup
    payload['research_budget']={'feedback_batches':1}
    class Assess(Trio):
        async def invoke(self,role,payload,schema,tools,meter):
            result=await super().invoke(role,payload,schema,tools,meter)
            if role=='reviewer':
                from app.research.contracts import RequestAssessment
                assert payload['requested_evidence'][0]['request_id']=='request-1'
                result.question_covered=covered
                result.request_assessments=[] if assessment=='missing' else [RequestAssessment(
                    request_id='request-1',necessary=assessment=='required',reason='Required original support' if assessment=='required' else 'Extra cost experiment is outside the mechanism question')]
            return result
    trio=Assess(requests=True)
    with local_client(create_app(config,ScriptedModel(),research_agents=trio)) as client:
        response=client.post('/api/v2/reviews/stream',json=payload)
        assert events(response)[-1]['taskStatus']==expected_status
        assert trio.roles.count('researcher')==expected_research


def test_delivery_gate_independently_checks_supplement_assessments():
    from copy import deepcopy
    from app.research.contracts import delivery_allowed
    report={'report_version':1,'evidence_snapshot_id':'s','claims':[
        {'claim_id':'c','kind':'finding','evidence_ids':['e']}],
        'evidence_requests':[{'request_id':'request-1','question':'Extra experiment'}]}
    review={'status':'success','verdict':'pass','reviewed_report_version':1,'reviewed_evidence_snapshot_id':'s',
            'checked_claim_ids':['c'],'unchecked_claim_ids':[],'issues':[],'question_covered':True,
            'request_assessments':[{'request_id':'request-1','necessary':False,'reason':'Outside the question'}]}
    evidence=[{'evidence_id':'e','paper_id':'p','correspondence':'user_provided'}]
    papers=[{'paper_id':'p','source':'local','identity_status':'unresolved'}]
    assert delivery_allowed(report,review,evidence,papers)
    for patch in ({'question_covered':False},{'request_assessments':[]},
                  {'request_assessments':[{'request_id':'wrong','necessary':False}]},
                  {'request_assessments':[{'request_id':'request-1','necessary':True}]}):
        changed=deepcopy(review);changed.update(patch)
        assert not delivery_allowed(report,changed,evidence,papers)


def test_bad_identifier_in_review_comment_is_preserved_but_not_rendered_as_citation(setup):
    config,payload,_=setup
    payload['research_budget']={'feedback_batches':0}
    class BadReview(Trio):
        async def invoke(self,role,payload,schema,tools,meter):
            result=await super().invoke(role,payload,schema,tools,meter)
            if role=='reviewer':
                from app.research.contracts import IssueDraft
                result.issues=[IssueDraft(claim_id=payload['report']['claims'][0]['claim_id'],owner='reporter',
                    severity='blocking',problem='Check evidence-invented-original',required_fix='Recheck original')]
            return result
    with local_client(create_app(config,ScriptedModel(),research_agents=BadReview())) as client:
        response=client.post('/api/v2/reviews/stream',json=payload)
        assert events(response)[-1]['taskStatus']=='partial'
        report=client.get('/api/v1/runs/'+response.headers['x-run-id']).json()['report']
        assert report['review']['verdict']=='undetermined'
        assert 'evidence-invented-original' in report['review']['issues'][0]['problem']
        assert 'evidence-invented-original' not in json.dumps(report['sections'])


def test_conditions_and_contested_claims_are_visible_but_bounded():
    from app.research.context import evidence_view,report_view
    card={'evidence_id':'e','document_id':'d','paper_id':'p','location':{'page':1},
          'quote':'original','finding':'finding','conditions':{'model':'Model-A','datasets':'SharedQA','notes':'x'*10000}}
    view=evidence_view([card])[0]
    assert view['conditions_preview']['model']=='Model-A'
    assert len(json.dumps(view['conditions_preview']))<1300
    assert len(card['conditions']['notes'])==10000
    catalog=evidence_view([card],include_quote=False)[0]
    assert 'quote' not in catalog and catalog['quote_available_via_query_evidence']
    text='source-qualified statement '*80
    draft={'report_id':'r','report_version':1,'claims':[{'claim_id':'c','kind':'finding','text':text,'evidence_ids':['e']}]}
    assert 'text' not in report_view(draft)['claims'][0]
    assert report_view(draft,['c'])['claims'][0]['text']==text


def test_comparison_initialization_collects_condition_sources(setup):
    from test_business import make_pdf
    config,payload,papers=setup
    make_pdf(papers/'conditions.pdf','The base model generator architecture uses ModelA. Datasets benchmarks evaluation metrics use SharedQA.')
    payload['question']='比较模型与评测条件 retrieval coverage'
    class Inspect(Trio):
        async def invoke(self,role,payload,schema,tools,meter):
            if role=='researcher':
                assert any('ModelA' in c['text'] for c in payload['condition_passages']+payload['initial_passages'])
            return await super().invoke(role,payload,schema,tools,meter)
    with local_client(create_app(config,ScriptedModel(),research_agents=Inspect())) as client:
        response=client.post('/api/v2/reviews/stream',json=payload)
        assert events(response)[-1]['taskStatus']=='completed'
        run=client.get('/api/v1/runs/'+response.headers['x-run-id']).json()
        assert any(a['kind']=='condition_retrieval' for a in run['artifacts'])


def test_comparison_search_diversifies_and_can_scope_documents():
    chunks=[{'id':str(i),'document_id':doc,'paper':{'id':doc,'title':'Methods'},
             'page':i+1,'text':text} for i,(doc,text) in enumerate([
        ('a','retrieval reflection confidence '*20),('a','retrieval reflection confidence '*15),
        ('a','retrieval reflection confidence '*10),('b','retrieval confidence'),('c','retrieval reflection')])]
    index=SearchIndex(chunks)
    assert {c['document_id'] for c in index.search('retrieval reflection confidence',3)}=={'a','b','c'}
    assert {c['document_id'] for c in index.search('retrieval',6,['b'])}=={'b'}
    assert index.search('retrieval',6,[])==[]
    assert index.search('retrieval',0)==[]


def test_condition_search_can_prefer_body_without_losing_appendix_access():
    common={'paper':{'id':'p','title':'Study'},'document_id':'d'}
    index=SearchIndex([{**common,'id':'a','page':1,'text':'Datasets evaluated include SharedQA.','content_region':'body'},
                       {**common,'id':'b','page':2,'text':'Datasets evaluation datasets benchmarks tasks.','content_region':'back_matter'}])
    assert [c['id'] for c in index.search('datasets evaluation',content_region='body')]==['a']
    assert [c['id'] for c in index.search('datasets',content_region='back_matter')]==['b']


def test_chinese_research_terms_retrieve_english_without_inventing_unrelated_matches():
    chunks=[{'id':'a','paper':{'id':'p','title':'Mechanism'},'page':1,
             'text':'A confidence threshold triggers retrieval for the next sentence.'}]
    index=SearchIndex(chunks)
    assert index.search('下一句话何时触发检索')[0]['id']=='a'
    assert index.search('铌钛超导临界电流')==[]


def test_actual_langchain_graph_finishes_with_schema_after_bounded_tool_rounds(setup,monkeypatch):
    config,_,_=setup
    @tool
    def search_document(query:str)->dict:
        """Look for relevant documents."""
        return {'status':'empty','data':[],'error':None}
    class RecordingFake(FakeMessagesListChatModel):
        bindings:list=Field(default_factory=list)
        def bind_tools(self,tools,**kwargs):
            self.bindings.append([t.name for t in tools])
            return self
    output={'status':'partial','outcome':'insufficient_evidence','evidence':[],
            'unresolved_gaps':['No relevant evidence in the supplied documents.']}
    responses=[AIMessage(content='',tool_calls=[{'name':'search_document','args':{'query':f'query {i}'},'id':f'call{i}'}]) for i in range(4)]
    responses.append(AIMessage(content='',tool_calls=[{'name':'ResearchOutput','args':output,'id':'final'}]))
    fake=RecordingFake(responses=responses)
    monkeypatch.setattr('app.research.agents.ChatOpenAI',lambda **kwargs:fake)
    store=Store(config.runtime_dir)
    meter=Meter(Budget(),Workspace(store,'bounded','run'))
    result=asyncio.run(ThreeAgents(config).invoke('researcher',{},ResearchOutput,[search_document],meter))
    assert result.outcome=='insufficient_evidence'
    assert fake.bindings[-1]==['ResearchOutput']
    assert meter.models==5 and meter.tools==4
    with store.connect() as db:
        rows=db.execute('SELECT kind,payload FROM research_objects WHERE project=?',('bounded',)).fetchall()
    calls=[json.loads(r['payload']) for r in rows if r['kind']=='agent_tool_call']
    results=[json.loads(r['payload']) for r in rows if r['kind']=='agent_tool_result']
    assert len(calls)==4 and all(c['tool']=='search_document' and c['arguments_hash'] for c in calls)
    assert all(r['status']=='empty' for r in results)


def test_limitations_are_audited_and_cannot_pass_when_unchecked(setup):
    config,payload,_=setup
    payload['research_budget']={'feedback_batches':0}
    class Limited(Trio):
        async def invoke(self,role,payload,schema,tools,meter):
            result=await super().invoke(role,payload,schema,tools,meter)
            if role=='reporter': result.limitations=['The entire paper has no mitigation for query errors.']
            if role=='reviewer':
                hidden=[c['claim_id'] for c in payload['report']['claims'] if c.get('presentation')=='limitation']
                assert hidden
                result.checked_claim_ids=[c for c in result.checked_claim_ids if c not in hidden]
                result.unchecked_claim_ids=hidden
                result.verdict='undetermined'
            return result
    with local_client(create_app(config,ScriptedModel(),research_agents=Limited())) as client:
        response=client.post('/api/v2/reviews/stream',json=payload)
        assert events(response)[-1]['taskStatus']=='partial'
        report=client.get('/api/v1/runs/'+response.headers['x-run-id']).json()['report']
        assert report['verification']!='passed'
        assert any(c.get('presentation')=='limitation' for c in report['claims'])


@pytest.mark.parametrize('cited',[False,True])
def test_limitations_never_inherit_arbitrary_citations_even_when_reviewer_passes(setup,cited):
    config,payload,_=setup
    payload['research_budget']={'feedback_batches':0}
    class Limited(Trio):
        async def invoke(self,role,payload,schema,tools,meter):
            result=await super().invoke(role,payload,schema,tools,meter)
            if role=='reporter':
                suffix=f" [{payload['evidence'][0]['evidence_id']}]" if cited else ''
                result.limitations=['Limited to this experiment.'+suffix]
            return result
    with local_client(create_app(config,ScriptedModel(),research_agents=Limited())) as client:
        response=client.post('/api/v2/reviews/stream',json=payload)
        assert events(response)[-1]['taskStatus']==('completed' if cited else 'partial')
        report=client.get('/api/v1/runs/'+response.headers['x-run-id']).json()['report']
        limitation=next(c for c in report['claims'] if c.get('presentation')=='limitation')
        assert bool(limitation['evidence_ids']) is cited
        if not cited:
            assert any(i['claim_id']==limitation['claim_id'] and i['category']=='citation'
                       and i['severity']=='blocking' for i in report['review']['issues'])


@pytest.mark.parametrize('outcome,errors,expected',[
    (None,[],'blocked'),('insufficient_evidence',[],'blocked'),
    ('execution_error',[],'AGENT_FAILED'),(None,['TOOL_ERROR'],'AGENT_FAILED')])
def test_no_evidence_is_distinct_from_actual_execution_failure(setup,outcome,errors,expected):
    config,payload,_=setup
    class Empty(Trio):
        async def invoke(self,role,payload,schema,tools,meter):
            assert role=='researcher'
            return ResearchOutput(status='failed',outcome=outcome,evidence=[],
                                  unresolved_gaps=['The supplied documents do not support this topic.'],errors=errors)
    with local_client(create_app(config,ScriptedModel(),research_agents=Empty())) as client:
        response=client.post('/api/v2/reviews/stream',json=payload)
        last=events(response)[-1]
        if expected=='blocked':
            assert last['taskStatus']=='blocked' and last['verification']=='no_evidence'
            report=client.get('/api/v1/runs/'+response.headers['x-run-id']).json()['report']
            assert report['stop_reason']=='insufficient_evidence' and not report['evidence']
        else: assert last['type']=='error' and last['code']==expected


def test_neighboring_context_preserves_source_coordinates():
    original={'data':{'document_id':'d','page':4,'content_hash':'hash',
        'text':'A partial paragraph continues',
        'adjacent_pages':[{'page':5,'start':0,'end':25,'text':'Two mitigation strategies'}]}}
    evidence=[{'document_id':'d','location':{'page':4},'quote':'paragraph continues','evidence_id':'e'}]
    window=original_windows([original],evidence)[0]
    assert window['content_hash']=='hash'
    assert window['adjacent_pages']==original['data']['adjacent_pages']
    assert window['windows'][0]['text']==original['data']['text']


def test_batched_review_preserves_cross_row_comparison_conditions():
    from app.research.context import review_payloads
    evidence=[{'evidence_id':'e','document_id':'d','paper_id':'p','location':{'page':1},'quote':'original'}]
    report={'report_id':'r','report_version':1,'evidence_snapshot_id':'s',
        'claims':[{'claim_id':str(i),'kind':'synthesis','text':'Different models need not mean disjoint datasets.',
                   'evidence_ids':['e']} for i in range(7)],
        'comparison_table':[{'cells':{'method':'A','datasets':'SharedQA, OtherQA'}},
                            {'cells':{'method':'B','datasets':'SharedQA, ThirdQA'}}]}
    original=[{'data':{'document_id':'d','page':1,'text':'original','content_hash':'h'}}]
    batches=review_payloads({},report,evidence,[],original,[],10000)
    assert len(batches)==2
    assert all(len(b['report_outline'])==7 for b in batches)
    assert all([row['cells']['datasets'] for row in b['comparison_context']]==
               ['SharedQA, OtherQA','SharedQA, ThirdQA'] for b in batches)


def test_report_contract_enforces_requested_rows_without_trimming_audited_text():
    from app.research.contracts import report_contract
    from pydantic import ValidationError
    row={'cells':{'A':'first','B':'second'},'evidence_ids':['e']}
    claim={'text':'A comparison','kind':'synthesis','evidence_ids':['e'],'scope':'this experiment'}
    schema=report_contract({'question':'给一行比较','output_requirements':{'max_claims':1}})
    assert len(schema(status='success',claims=[claim],comparison_table=[row]).comparison_table)==1
    with pytest.raises(ValidationError): schema(status='success',claims=[claim],comparison_table=[row,row])
    with pytest.raises(ValidationError): schema(status='success',claims=[claim,claim])
    schema=report_contract({'question':'说明限制','output_requirements':{}})
    with pytest.raises(ValidationError): schema(status='success',claims=[claim],comparison_table=[row])


def test_program_blocks_no_overlap_claim_even_if_model_reviewer_passes(setup):
    from test_business import make_pdf
    from app.research.contracts import ReportOutput
    config,payload,papers=setup
    make_pdf(papers/'other.pdf','A second retrieval study also evaluated SharedQA.')
    payload['research_budget']={'feedback_batches':0}
    class Overlap(Trio):
        async def invoke(self,role,payload,schema,tools,meter):
            if role=='researcher':
                selected={c['document_id']:c for c in payload['initial_passages']}
                assert len(selected)==2
                return ResearchOutput(status='success',evidence=[{'span_id':c['id'],'finding':'Retrieval evidence',
                    'conditions':{'datasets':'SharedQA'}} for c in selected.values()])
            if role=='reporter':
                return ReportOutput(status='success',claims=[{'text':'两篇论文的数据集完全不重叠。','kind':'synthesis',
                    'evidence_ids':[e['evidence_id'] for e in payload['evidence']],'scope':'these papers'}])
            return await super().invoke(role,payload,schema,tools,meter)
    with local_client(create_app(config,ScriptedModel(),research_agents=Overlap())) as client:
        response=client.post('/api/v2/reviews/stream',json=payload)
        assert events(response)[-1]['taskStatus']=='partial'
        report=client.get('/api/v1/runs/'+response.headers['x-run-id']).json()['report']
        assert report['review']['verdict']=='revise'
        assert any('sharedqa' in i['problem'] for i in report['review']['issues'])


def test_budget_during_revision_does_not_attach_previous_verdict(setup):
    config,payload,_=setup
    payload['research_budget']={'feedback_batches':1,'model_calls':4}
    with local_client(create_app(config,ScriptedModel(),research_agents=Trio(owner='reporter'))) as client:
        response=client.post('/api/v2/reviews/stream',json=payload)
        assert events(response)[-1]['taskStatus']=='partial'
        report=client.get('/api/v1/runs/'+response.headers['x-run-id']).json()['report']
        assert report['report_version']==2 and report['review'] is None


@pytest.mark.parametrize('text,expected',[
    ('没有任何一篇论文报告这种比较。',True),
    ('在已检查的证据中，没有任何一篇论文报告这种比较。',False)])
def test_paper_wide_denial_cannot_coexist_with_disclaimed_full_reading(text,expected):
    from app.research.comparisons import overlap_issues
    report={'claims':[{'claim_id':'c','text':text,'evidence_ids':['e']}],
            'limitations':['未核对其余正文或附录部分。']}
    assert bool(overlap_issues(report,[])) is expected


def test_unrequested_performance_scores_are_not_added_to_mechanism_comparisons():
    from app.research.comparisons import overlap_issues
    report={'claims':[{'claim_id':'c','text':'Baseline EM=68.6 versus method EM=41.3.',
                       'evidence_ids':['e']}], 'limitations':[]}
    assert overlap_issues(report,[],{'question':'说明方法与可比条件'})
    assert not overlap_issues(report,[],{'question':'比较相同数据集上的具体数值得分'})


@pytest.mark.parametrize('text,blocked',[
    ('使用 Llama2 7B [evidence-f15ad2695e9d41bda62141255b1b69d8]。',False),
    ('只说明 F1 指标 [evidence-f1999]。',False),
    ('F1=42.3 [evidence-f1999]。',True),
    ('ROUGE-L 30.5。',True)])
def test_metric_detection_does_not_interpret_citation_ids_as_scores(text,blocked):
    from app.research.comparisons import overlap_issues
    report={'claims':[{'claim_id':'c','text':text,'evidence_ids':['evidence-f1999']}], 'limitations':[]}
    assert bool(overlap_issues(report,[],{'question':'说明模型和可比条件'})) is blocked


@pytest.mark.parametrize('category,expected',[('factual','blocking'),('citation','blocking'),('style','warning')])
def test_factual_warnings_cannot_bypass_delivery_gate(category,expected):
    from app.research.contracts import IssueDraft
    issue=IssueDraft(claim_id='c',owner='reporter',severity='warning',category=category,
                     problem='Unsupported assertion' if category!='style' else 'Optional formatting',required_fix='Review')
    assert issue.severity==expected


def test_hash_bound_bibliography_refreshes_without_upgrading_identity(setup):
    config,payload,papers=setup
    pdf=papers/'study.pdf';digest=hashlib.sha256(pdf.read_bytes()).hexdigest()
    sidecar=pdf.with_suffix('.metadata.json')
    metadata={'sha256':digest,'title':'Provided bibliography','authors':['Known Author'],'year':2020,
              'source':'https://arxiv.org/abs/example'}
    sidecar.write_text(json.dumps(metadata))
    store=Store(config.runtime_dir);library=Library(config,store)
    project=Project.model_validate(payload['project']);scope=resolve_project(project,config)
    chunks,_=asyncio.run(library.index(project.id,scope))
    assert chunks[0]['paper']['title']=='Provided bibliography'
    metadata['title']='Updated bibliography';sidecar.write_text(json.dumps(metadata))
    chunks,_=asyncio.run(library.index(project.id,scope))
    assert chunks[0]['paper']['title']=='Updated bibliography'
    with local_client(create_app(config,ScriptedModel(),research_agents=Trio())) as client:
        response=client.post('/api/v2/reviews/stream',json=payload)
        assert events(response)[-1]['taskStatus']=='completed'
        run=client.get('/api/v1/runs/'+response.headers['x-run-id']).json()
        record=next(a['payload'] for a in run['artifacts'] if a['kind']=='paper_record')
        assert record['title']=='Updated bibliography' and record['authors']==['Known Author']
        assert record['identity_status']=='unresolved'
    metadata['sha256']='wrong';sidecar.write_text(json.dumps(metadata))
    chunks,_=asyncio.run(library.index(project.id,scope))
    assert chunks[0]['paper']['title']=='Retrieval Study'
