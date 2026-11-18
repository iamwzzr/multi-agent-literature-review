import pytest
from app.errors import AppError
from app.main import create_app
from app.research.context import EvidenceRegistry
from app.research.workspace import Workspace
from app.store import Store
from test_business import setup,local_client,ScriptedModel,events,output
from test_three_agent import Trio


def test_exact_quote_can_relocate_to_another_page_of_same_pdf(setup):
    config,_,_=setup
    quote='This is the exact original mechanism sentence.'
    spans={'s':{'id':'s','document_id':'d','paper_id':'p','page':1,'start':0,'text':'Different source passage on first page.'}}
    document={'pages':[spans['s']['text'],quote],'correspondence':'user_provided'}
    cards=[];ws=Workspace(Store(config.runtime_dir),'p','r')
    registry=EvidenceRegistry(lambda:spans,{'d':document},ws,cards)
    card=registry.add('s','finding',{},quote=quote)
    assert card['quote']==quote and card['location']['page']==2
    assert card['span_ids'][0] in spans
    assert registry.add('s','finding',{},quote=quote)['evidence_id']==card['evidence_id']
    spans.clear()  # Simulate rebuilding the searchable chunk index after online admission.
    assert registry.add(card['span_ids'][0],'finding',{},quote=quote)['evidence_id']==card['evidence_id']


def test_duplicate_or_cross_document_quote_never_auto_relocates(setup):
    config,_,_=setup
    quote='Repeated original sentence with details.'
    span={'id':'s','document_id':'d','paper_id':'p','page':1,'text':'Different source passage.'}
    ws=Workspace(Store(config.runtime_dir),'p','r')
    for pages in ([span['text'],quote,quote],[span['text']]):
        registry=EvidenceRegistry(lambda:{'s':span},
            {'d':{'pages':pages,'correspondence':'user_provided'},'other':{'pages':[quote],'correspondence':'user_provided'}},ws,[])
        with pytest.raises(AppError): registry.add('s','finding',{},quote=quote)


class WrongQuote(Trio):
    async def invoke(self,role,payload,schema,tools,meter):
        result=await super().invoke(role,payload,schema,tools,meter)
        if role=='researcher':result.evidence[0].quote='This fabricated sentence does not exist in the paper.'
        return result


def test_handoff_keeps_actual_source_and_records_quote_fallback(setup):
    config,payload,_=setup
    with local_client(create_app(config,ScriptedModel(),research_agents=WrongQuote())) as client:
        response=client.post('/api/v2/reviews/stream',json=payload)
        delivered=output(events(response))
        assert 'fabricated sentence' not in delivered['evidence'][0]['excerpt']
        run=client.get('/api/v1/runs/'+response.headers['x-run-id']).json()
        assert any(a['kind']=='quote_precision_fallback' for a in run['artifacts'])
        card=next(a['payload'] for a in run['artifacts'] if a['kind']=='evidence')
        assert any('短引文' in limitation for limitation in card['limitations'])
