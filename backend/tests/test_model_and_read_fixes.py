import asyncio
import pytest

from app.research.context import select_original_items
from app.research.citations import display_citations
from app.research.agents import ThreeAgents
from app.model import ModelClient
from test_business import setup


def test_read_original_accepts_evidence_id_in_both_supported_fields():
    card={'evidence_id':'evidence-e','document_id':'d','location':{'page':3,'start':5},'quote':'original'}
    for kwargs in ({'evidence_id':'evidence-e'},{'span_id':'evidence-e'}):
        items,error=select_original_items({},[card],'d',3,**kwargs)
        assert error is None and items==[card]
    assert select_original_items({},[card],'wrong',3,evidence_id='evidence-e')[1]=='REFERENCE_LOCATION_MISMATCH'
    assert select_original_items({},[card],'d',2,evidence_id='evidence-e')[1]=='REFERENCE_LOCATION_MISMATCH'
    assert select_original_items({},[],'d',3,evidence_id='evidence-e')[1]=='UNKNOWN_EVIDENCE'


def test_default_read_includes_current_quote_not_arbitrary_first_page_chunks():
    card={'evidence_id':'evidence-e','document_id':'d','location':{'page':3,'start':5000},'quote':'later original'}
    assert select_original_items({},[card],'d',3)[0]==[card]


def test_generic_internal_id_placeholder_is_not_displayed_as_a_real_citation():
    assert display_citations('See [evidence-...] markers.',{})=='See 内部证据编号 markers.'


def test_async_model_client_honors_proxy_policy_and_closes(setup,monkeypatch):
    config,_,_=setup;config=config.model_copy(update={'model_trust_env':False})
    agents=ThreeAgents(config);record={}
    class Transport:
        def __init__(self,**kwargs):record.update(kwargs)
        async def __aenter__(self):return self
        async def __aexit__(self,*args):record['closed']=True
    async def invoke(*args):return 'result'
    monkeypatch.setattr('app.research.agents.httpx.AsyncClient',Transport)
    monkeypatch.setattr(agents,'_invoke',invoke)
    assert asyncio.run(agents.invoke('researcher',{},None,[],None))=='result'
    assert record['trust_env'] is False and record['closed'] is True


def test_legacy_model_client_also_honors_proxy_policy(setup):
    config,_,_=setup;config=config.model_copy(update={'model_trust_env':False})
    client=ModelClient(config).open_client()
    assert client._trust_env is False
    asyncio.run(client.aclose())
