"""Regression and acceptance tests for evidence IDs in reviewed deliverables."""
import json
import re
from copy import deepcopy

import pytest

from app.errors import AppError
from app.main import create_app
from app.research.citations import cited_paragraph, display_citations, validate_citations
from app.research.contracts import ReportOutput
from test_business import setup, local_client, ScriptedModel, events, output
from test_three_agent import Trio


@pytest.mark.parametrize('text', [
    'Finding [evidence-abc][evidence-def].',
    'Finding [[evidence-abc]][[evidence-def]].',
    'Finding [evidence-abc, evidence-def].',
    'Finding evidence-abc and `evidence-def`.',
])
def test_internal_citation_forms_convert_to_frontend_protocol(text):
    result = display_citations(text, {'evidence-abc': 1, 'evidence-def': 2})
    assert 'evidence-' not in result
    assert set(re.findall(r'\[\[(\d+)\]\]', result)) == {'1', '2'}
    assert '[[[' not in result


def test_append_only_missing_citations_preserves_prose():
    refs = {'evidence-abc': 1, 'evidence-def': 2}
    assert cited_paragraph('A [evidence-abc].', list(refs), refs) == 'A [[1]].[[2]]'
    assert display_citations('Method [RAG] and p < 0.05.', refs) == 'Method [RAG] and p < 0.05.'


@pytest.mark.parametrize('text,declared', [
    ('A [evidence-fake].', ['evidence-real']),
    ('A [evidence-real].', []),
])
def test_invalid_inline_citation_cannot_be_hidden_by_valid_suffix(text, declared):
    with pytest.raises(AppError) as exc:
        validate_citations(text, declared, ['evidence-real'])
    assert exc.value.code == 'UNKNOWN_EVIDENCE'


def test_model_cannot_assign_numeric_display_citations():
    with pytest.raises(AppError):
        validate_citations('A [[99]].', ['evidence-real'], ['evidence-real'])


class InlineTrio(Trio):
    def __init__(self, invalid=None):
        super().__init__()
        self.invalid = invalid

    async def invoke(self, role, payload, schema, tools, meter):
        result = await super().invoke(role, payload, schema, tools, meter)
        if role == 'reporter':
            data = result.model_dump()
            eid = data['claims'][0]['evidence_ids'][0]
            data['claims'][0]['text'] = 'Retrieval improved coverage. [' + eid + ']'
            data['comparison_table'][0]['cells']['finding'] = 'Improved coverage [' + eid + ']'
            data['comparison_table'][0]['cells']['unreported_cost'] = None
            data['comparison_table'][0]['conditions'] = {'setting': 'This experiment [' + eid + ']'}
            if self.invalid:
                if self.invalid == 'claim':
                    data['claims'][0]['text'] += '[evidence-fake]'
                elif self.invalid == 'table':
                    data['comparison_table'][0]['cells']['finding'] += '[evidence-fake]'
            return ReportOutput(**data)
        return result


def test_reviewed_delivery_and_table_have_numeric_citations_but_raw_audit_is_preserved(setup):
    config, payload, _ = setup
    with local_client(create_app(config, ScriptedModel(), research_agents=InlineTrio())) as client:
        response = client.post('/api/v2/reviews/stream', json=payload)
        rendered = output(events(response))
        data = client.get('/api/v1/runs/' + response.headers['x-run-id']).json()
        report = data['report']
        assert report['task_status'] == 'completed'
        display = json.dumps(rendered['sections']) + json.dumps(report['comparison_table'][0]['cells'])
        assert 'evidence-' not in display and '[[1]]' in display
        assert 'None' not in json.dumps(rendered['sections'])
        assert any('未知（未报告）' in p for s in rendered['sections'] for p in s['paragraphs'])
        assert report['comparison_table'][0]['conditions']['setting'] == 'This experiment [[1]]'
        assert len(rendered['evidence']) == 1
        raw = next(a['payload'] for a in data['artifacts'] if a['kind'] == 'report_draft')
        assert '[evidence-' in raw['claims'][0]['text']
        assert raw['report_version'] == report['review']['reviewed_report_version']
        assert raw['evidence_snapshot_id'] == report['review']['reviewed_evidence_snapshot_id']


@pytest.mark.parametrize('where', ['claim', 'table'])
def test_invalid_inline_reference_is_rejected_before_review(setup, where):
    config, payload, _ = setup
    trio = InlineTrio(where)
    with local_client(create_app(config, ScriptedModel(), research_agents=trio)) as client:
        response = client.post('/api/v2/reviews/stream', json=payload)
        assert events(response)[-1]['code'] == 'UNKNOWN_EVIDENCE'
        assert 'reviewer' not in trio.roles


def test_empty_local_folder_does_not_generate_report(setup):
    config, payload, _ = setup
    folder = config.workspace_root / 'empty'
    folder.mkdir()
    payload['project']['knowledgePaths'] = ['empty']
    trio = Trio()
    with local_client(create_app(config, ScriptedModel(), research_agents=trio)) as client:
        response = client.post('/api/v2/reviews/stream', json=payload)
        assert events(response)[-1]['taskStatus'] == 'blocked'
        assert trio.roles == []


def test_upload_rejects_non_pdf_and_wrong_content_type(setup):
    config, _, _ = setup
    with local_client(create_app(config, ScriptedModel(), research_agents=Trio())) as client:
        url = '/api/v2/projects/upload-negative/uploads'
        assert client.post(url, content=b'not a pdf', headers={'Content-Type': 'application/pdf'}).status_code == 422
        assert client.post(url, content=b'not a pdf', headers={'Content-Type': 'text/plain'}).status_code == 415


def test_changed_original_pdf_is_detected(setup):
    config, payload, _ = setup
    from pathlib import Path
    from app.research.workspace import Workspace
    from app.store import Store
    with local_client(create_app(config, ScriptedModel(), research_agents=Trio())) as client:
        response = client.post('/api/v2/reviews/stream', json=payload)
        report = output(events(response))
        document_id = report['evidence'][0]['paper']['id']
        document = Workspace(Store(config.runtime_dir), payload['project']['id'], 'test').get(document_id)
        Path(document['path']).write_bytes(b'%PDF changed original')
        result = client.get('/api/v1/papers/pdf', params={'projectId': payload['project']['id'], 'paperId': document_id})
        assert result.status_code == 409
        assert result.json()['error']['code'] == 'ORIGINAL_CHANGED'
