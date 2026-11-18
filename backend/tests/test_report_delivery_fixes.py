from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.library import SearchIndex, named_retrieval_queries
from app.research.engine import ThreeAgentWorkflow
from app.research.presentation import conditions_text, library_scope_issues, PRECISION_PENDING, PRECISION_REVIEWED
from app.main import create_app
from test_business import setup, local_client, ScriptedModel, events
from test_three_agent import Trio


class DeliveryTrio(Trio):
    async def invoke(self, role, payload, schema, tools, meter):
        selection = payload['task']['local_library_selection']
        assert selection['catalog_is_preview'] is True
        assert 'catalog_titles' not in selection
        result = await super().invoke(role, payload, schema, tools, meter)
        if role == 'reporter':
            data = result.model_dump()
            first = data['claims'][0]
            data['claims'] = [dict(first, text='First finding.'), dict(first, text='Second finding.'),
                              dict(first, kind='synthesis', text='First inference.'),
                              dict(first, kind='synthesis', text='Second inference.')]
            data['comparison_table'][0]['cells']['training'] = '本地证据未报&#x544A;'
            data['comparison_table'][0]['conditions'] = {'model': None, 'source_type': '原文'}
            return schema(**data)
        return result


def test_grouped_delivery_keeps_all_audit_claims_and_single_table(setup):
    config, payload, _ = setup
    payload['question'] = '请比较检索方法并提供对照表'
    with local_client(create_app(config, ScriptedModel(), research_agents=DeliveryTrio())) as client:
        response = client.post('/api/v2/reviews/stream', json=payload)
        assert events(response)[-1]['taskStatus'] == 'completed'
        run = client.get('/api/v1/runs/' + response.headers['x-run-id']).json()
        report = run['report']
        headings = [s['heading'] for s in report['sections']]
        assert headings.count('研究发现') == 1
        assert headings.count('综合分析与比较') == 1
        assert [len(s['paragraphs']) for s in report['sections']] == [2, 2]
        assert len(report['comparison_table']) == 1
        assert report['comparison_table'][0]['cells']['training'] == '本地证据未报告'
        assert report['comparison_table'][0]['conditions'] == {'source_type': '原文'}
        assert len(report['claims']) == 5
        assert len(report['review']['checked_claim_ids']) == 5
        raw = next(a['payload'] for a in run['artifacts'] if a['kind'] == 'report_draft')
        assert raw['claims'][-1]['presentation'] == 'comparison_row'
        assert raw['claims'][-1]['scope'] == '来源性质：原文'
        assert '&#x544A;' in raw['comparison_table'][0]['cells']['training']
        assert 'local_library_selection' in next(a['payload'] for a in run['artifacts'] if a['kind'] == 'task_spec') or any(a['kind'] == 'local_library_selection' for a in run['artifacts'])


def test_precision_warning_changes_only_for_completed_delivery():
    report = {'claims': [], 'comparison_table': [], 'limitations': []}
    meter = SimpleNamespace(models=0, tools=0, tokens=0)
    for status in ('completed', 'partial', 'blocked'):
        result = ThreeAgentWorkflow.render(report, None, [], [], {}, status, [PRECISION_PENDING], meter)
        assert (PRECISION_REVIEWED if status == 'completed' else PRECISION_PENDING) in result['unresolved']
    assert report['limitations'] == []


@pytest.mark.parametrize('text', ['本地无原始 RAG 方法论文', '本地没有原始论文', '本地库不存在该论文'])
def test_library_absence_claims_are_blocked(text):
    report = {'claims': [{'claim_id': 'c', 'text': text, 'evidence_ids': ['e'], 'scope': ''}]}
    issues = library_scope_issues(report, {'local_library_selection': {'indexed_papers': 100}})
    assert len(issues) == 1 and issues[0]['severity'] == 'blocking'


def test_scoped_evidence_gap_is_allowed():
    report = {'claims': [{'claim_id': 'c', 'text': '本轮未取得原始论文的原文证据', 'evidence_ids': [], 'scope': ''}]}
    assert not library_scope_issues(report, {'local_library_selection': {'indexed_papers': 100}})
    assert conditions_text({'model': None, 'metric': '', 'source_type': '原文'}) == '来源性质：原文'


def test_named_methods_reserve_primary_titles_over_incidental_mentions():
    chunks = [
        {'id': 'a', 'paper': {'id': 'primary', 'title': 'Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks'}, 'page': 3, 'text': 'RAG sequence and token marginalization.'},
        {'id': 'b', 'paper': {'id': 'survey', 'title': 'A Survey of RAG'}, 'page': 1, 'text': ('RAG Self-RAG FLARE trigger retrieval comparison ' * 25)},
        {'id': 'c', 'paper': {'id': 'self', 'title': 'Self-RAG: Learning to Retrieve'}, 'page': 3, 'text': 'Retrieve token evaluates utility.'},
    ]
    index = SearchIndex(chunks)
    query = '比较 RAG、Self-RAG 与 FLARE 的触发机制，引用 PDF 页码'
    assert named_retrieval_queries([query])[:3] == ['RAG', 'Self-RAG', 'FLARE']
    assert index.rank_papers([query])[0] == 'primary'
    assert 'self' in index.rank_papers([query])[:3]
    assert named_retrieval_queries(['比较Self-RAG']) == ['Self-RAG', '比较Self-RAG']
    assert 'RAG' not in named_retrieval_queries(['比较Self-RAG'])


def test_serialized_conditions_do_not_leak_internal_values():
    from app.research.context import scoped_claim_text
    claim = {'text': '本地证据未报&#x544A;', 'scope': "{'model': None, 'task': None, 'source_type': '二手综述'}"}
    text = scoped_claim_text(claim)
    assert 'None' not in text and "{'" not in text
    assert '来源性质：二手综述' in text


def test_missing_cost_information_is_not_a_library_absence_claim():
    report = {'claims': [{'claim_id': 'c', 'text': '本地缺少可核实的成本数据', 'evidence_ids': [], 'scope': ''}]}
    assert not library_scope_issues(report, {'local_library_selection': {'indexed_papers': 100}})


def test_scope_gate_blocks_false_absence_even_when_model_reviewer_passes(setup):
    config, payload, _ = setup
    payload['research_budget'] = {'feedback_batches': 0}
    class FalseAbsence(Trio):
        async def invoke(self, role, payload, schema, tools, meter):
            result = await super().invoke(role, payload, schema, tools, meter)
            if role == 'reporter':
                result.claims[0].scope = '本地无原始 RAG 方法论文，该列来自二手综述'
            return result
    with local_client(create_app(config, ScriptedModel(), research_agents=FalseAbsence())) as client:
        response = client.post('/api/v2/reviews/stream', json=payload)
        assert events(response)[-1]['taskStatus'] == 'partial'
        report = client.get('/api/v1/runs/' + response.headers['x-run-id']).json()['report']
        assert report['verification'] != 'passed'
        assert any(i['category'] == 'scope' and i['severity'] == 'blocking' for i in report['review']['issues'])


def test_encoded_citations_are_validated_before_decoding_for_display():
    from app.errors import AppError
    from app.research.citations import validate_citations, display_citations
    with pytest.raises(AppError):
        validate_citations('&#91;evidence-fake&#93;', [], [])
    with pytest.raises(AppError):
        validate_citations('&#91;&#91;99&#93;&#93;', [], [])
    assert display_citations('本地证据未报&#x544A; [evidence-real]', {'evidence-real': 1}) == '本地证据未报告 [[1]]'
