from copy import deepcopy
import pytest
from pydantic import ValidationError
from app.research.reviewing import review_contract, incomplete_batch, merge_reviews
from app.research.contracts import report_contract
from app.research.presentation import task_scope_issues
from app.main import create_app
from test_business import setup, local_client, ScriptedModel, events
from test_three_agent import Trio


def payload():
    return {'report':{'claims':[{'claim_id':'c1'},{'claim_id':'c2'}]},
            'evidence':[{'evidence_id':'e1'}], 'requested_evidence':[]}


def result():
    return {'status':'success','verdict':'pass','checked_claim_ids':['c1','c2'],
            'unchecked_claim_ids':[],'issues':[],'question_covered':True}


@pytest.mark.parametrize('change',[
    {'checked_claim_ids':['c1','foreign']},
    {'unchecked_claim_ids':['c1']},
    {'checked_claim_ids':['c1']},
    {'checked_claim_ids':['c1','c1','c2']},
    {'issues':[{'claim_id':'foreign','evidence_ids':[],'owner':'reporter','category':'factual','severity':'blocking','problem':'wrong','required_fix':'fix'}]},
])
def test_batch_rejects_foreign_overlapping_missing_or_duplicate_targets(change):
    with pytest.raises(ValidationError): review_contract(payload())(**(result()|change))


def test_optional_refinement_requires_re_evaluation_instead_of_silent_downgrade():
    issue={'claim_id':'c1','evidence_ids':['e1'],'owner':'reporter','category':'citation',
           'severity':'blocking','problem':'事实无误，属于可选精修','required_fix':'change wording'}
    with pytest.raises(ValidationError):review_contract(payload())(**(result()|{'verdict':'revise','issues':[issue]}))
    issue.update(category='style',severity='warning')
    accepted=review_contract(payload())(**(result()|{'issues':[issue]}))
    assert accepted.verdict=='pass'
    issue.update(category='factual',severity='blocking',problem='Source reports five; draft reports ten.')
    checked=review_contract(payload())(**(result()|{'verdict':'revise','issues':[issue]}))
    assert checked.issues[0].severity=='blocking'


def test_incomplete_batch_never_inherits_a_pass():
    first=review_contract(payload())(**result())
    other=payload();other['report']['claims']=[{'claim_id':'c3'}]
    merged=merge_reviews([first,incomplete_batch(other,'INVALID_REVIEW_BATCH')])
    assert merged.status=='partial' and merged.verdict=='undetermined'
    assert merged.checked_claim_ids==['c1','c2'] and merged.unchecked_claim_ids==['c3']
    assert 'INVALID_REVIEW_BATCH' in merged.errors


def test_concise_default_contract_retains_explicit_claim_count():
    claim={'text':'fact','kind':'finding','scope':'excerpt','evidence_ids':['e1']}
    base={'status':'success','claims':[claim]*5}
    with pytest.raises(ValidationError): report_contract({'question':'Explain components'})(**base)
    assert len(report_contract({'question':'Explain components','output_requirements':{'max_claims':6}})(**base).claims)==5


def test_two_components_do_not_authorize_a_missing_second_paper():
    task={'question':'WebThinker 的 Explorer 与 Draft 各负责什么？'}
    report={'claims':[{'claim_id':'c1','evidence_ids':['e1'],'text':'另一篇无法在本地定位原文'}]}
    assert task_scope_issues(report,task)[0]['severity']=='blocking'
    assert not task_scope_issues(report,{'question':'比较两篇不同论文'})


@pytest.mark.parametrize('repair', [True,False])
def test_invalid_batch_is_retried_and_never_auto_approved(setup,repair):
    config,request,_=setup;request['research_budget']={'feedback_batches':0}
    class Invalid(Trio):
        def __init__(self): super().__init__();self.attempts=0
        async def invoke(self,role,payload,schema,tools,meter):
            output=await super().invoke(role,payload,schema,tools,meter)
            if role=='reviewer':
                self.attempts+=1
                if not repair or self.attempts==1:output.unchecked_claim_ids=list(output.checked_claim_ids)
            return output
    agents=Invalid()
    with local_client(create_app(config,ScriptedModel(),research_agents=agents)) as client:
        response=client.post('/api/v2/reviews/stream',json=request)
        assert events(response)[-1]['taskStatus']==('completed' if repair else 'partial')
        run=client.get('/api/v1/runs/'+response.headers['x-run-id']).json()
        assert agents.attempts==2
        assert any(a['kind']=='review_batch_invalid' for a in run['artifacts'])
        assert any(a['kind']=='review_batch_input' for a in run['artifacts'])
        review=run['report']['review']
        assert not set(review['checked_claim_ids']) & set(review['unchecked_claim_ids'])
        if not repair:assert review['checked_claim_ids']==[] and 'INVALID_REVIEW_BATCH' in review['errors']


def test_bibliography_groups_document_versions_without_losing_anchors():
    from app.research.presentation import bibliography_view
    cards=[{'paper':{'id':doc,'title':'Paper'},'evidenceId':e,'page':page,'location':{'page':page}}
           for doc,e,page in [('v1','e1',1),('v1','e2',3),('v2','e3',1)]]
    result=bibliography_view(cards)
    assert len(result)==2
    assert [c['index'] for c in result[0]['citations']]==[1,2]
    assert [c['page'] for c in result[0]['citations']]==[1,3]
    assert result[1]['document_id']=='v2'


def test_success_label_does_not_hide_review_execution_errors():
    with pytest.raises(ValidationError):
        review_contract(payload())(**(result()|{'errors':['source_read_failed']}))


@pytest.mark.parametrize('override', [False,True])
def test_no_estimation_policy_is_derived_from_user_constraint_and_keeps_override(setup,override):
    config,request,_=setup
    request['question']='Retrieval coverage：依据文献能否确认每次回答的成本？禁止估算、换算或补写金额。'
    request['output_requirements']={'max_claims':6} if override else {}
    with local_client(create_app(config,ScriptedModel(),research_agents=Trio())) as client:
        response=client.post('/api/v2/reviews/stream',json=request)
        assert events(response)[-1]['type']=='done'
        run=client.get('/api/v1/runs/'+response.headers['x-run-id']).json()
        task=next(a['payload'] for a in run['artifacts'] if a['kind']=='task_spec')
        assert task['answer_policy']['no_estimation'] is True
        assert task['output_requirements']['max_claims']==(6 if override else 2)


def test_scoped_unknown_may_complete_only_after_independent_full_coverage_review():
    from app.research.contracts import delivery_allowed
    report={'status':'partial','errors':[],'report_version':1,'evidence_snapshot_id':'s',
            'claims':[{'claim_id':'c','kind':'finding','evidence_ids':['e']}], 'evidence_requests':[]}
    review={'status':'success','verdict':'pass','question_covered':True,'errors':[],
            'reviewed_report_version':1,'reviewed_evidence_snapshot_id':'s',
            'checked_claim_ids':['c'],'unchecked_claim_ids':[],'issues':[]}
    evidence=[{'evidence_id':'e','paper_id':'p','correspondence':'user_provided'}]
    papers=[{'paper_id':'p','source':'local'}]
    assert delivery_allowed(report,review,evidence,papers)
    for change in ({'question_covered':False},{'status':'partial'},{'unchecked_claim_ids':['c']},
                   {'errors':['source_read_failed']},{'reviewed_report_version':0},
                   {'issues':[{'severity':'blocking','status':'open'}]}):
        assert not delivery_allowed(report,review|change,evidence,papers)
    for change in ({'status':'failed'},{'errors':['execution_error']}):
        assert not delivery_allowed(report|change,review,evidence,papers)
    needs=dict(report,evidence_requests=[{'request_id':'r'}])
    assert not delivery_allowed(needs,review,evidence,papers)
    assert not delivery_allowed(needs,review|{'request_assessments':[{'request_id':'r','necessary':True}]},evidence,papers)
