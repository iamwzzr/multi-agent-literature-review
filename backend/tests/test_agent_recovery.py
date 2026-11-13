import asyncio
from types import SimpleNamespace

from app.research.agents import ThreeAgents
from app.research.contracts import Budget, ResearchOutput
from app.research.workspace import Meter, Workspace
from app.store import Store
from test_business import setup


def test_serialized_structured_response_obeys_same_contract(setup, monkeypatch):
    config, _, _ = setup
    monkeypatch.setattr('app.research.agents.ChatOpenAI', lambda **kwargs: object())
    class Fake:
        async def ainvoke(self, *args, **kwargs):
            return {'structured_response': {'status':'partial','evidence':[]}, 'messages':[]}
    monkeypatch.setattr('app.research.agents.create_agent', lambda **kwargs: Fake())
    meter = Meter(Budget(), Workspace(Store(config.runtime_dir),'mapping','run'))
    result = asyncio.run(ThreeAgents(config).invoke('researcher',{},ResearchOutput,[],meter))
    assert isinstance(result,ResearchOutput) and result.status == 'partial'


def test_format_retry_removes_research_tools_and_still_validates(setup, monkeypatch):
    config, _, _ = setup
    monkeypatch.setattr('app.research.agents.ChatOpenAI', lambda **kwargs: object())
    calls = []
    class Fake:
        def __init__(self, first): self.first = first
        async def ainvoke(self, *args, **kwargs):
            if self.first:
                return {'messages':[SimpleNamespace(content='Collected notes, not the required output.')], 'structured_response':None}
            return {'structured_response':{'status':'partial','evidence':[]}}
    def create(**kwargs):
        calls.append(kwargs)
        return Fake(len(calls)==1)
    monkeypatch.setattr('app.research.agents.create_agent',create)
    meter = Meter(Budget(), Workspace(Store(config.runtime_dir),'retry','run'))
    tool = SimpleNamespace(name='search_document')
    result = asyncio.run(ThreeAgents(config).invoke('researcher',{},ResearchOutput,[tool],meter))
    assert result.status == 'partial'
    assert calls[0]['tools'] == [tool] and calls[1]['tools'] == []
