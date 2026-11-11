import asyncio
import io
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.config import Settings
from app.errors import AppError
from app.library import Library, resolve_project, search
from app.main import create_app
from app.model import ModelClient
from app.schemas import Draft, Findings, Plan, ReviewCheck, ReviewRequest
from app.store import Store


def make_pdf(path, text='The retrieval pipeline improved evidence coverage in this experiment. The study used five papers.'):
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                             NameObject('/Subtype'): NameObject('/Type1'),
                             NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
    stream = DecodedStreamObject()
    stream.set_data(f'BT /F1 12 Tf 50 700 Td ({text}) Tj ET'.encode('ascii'))
    page[NameObject('/Contents')] = writer._add_object(stream)
    writer.add_metadata({'/Title': 'Retrieval Study', '/Author': 'Test Author'})
    with path.open('wb') as file:
        writer.write(file)


class ScriptedModel:
    """Test-only substitute. Never selectable through production configuration."""
    def __init__(self, bad_quote=False, fail_once=False, always_fail=False, mode='review'):
        self.bad_quote, self.fail_once, self.always_fail = bad_quote, fail_once, always_fail
        self.mode, self.roles, self.verifications = mode, [], 0

    def check(self):
        pass

    async def complete(self, role, instruction, payload, schema):
        self.roles.append(role)
        if role == 'coordinator':
            return Plan(mode=self.mode, tasks=[{'id': 'coverage', 'question': 'retrieval coverage', 'queries': ['retrieval coverage']}])
        if role == 'researcher':
            passage = payload['passages'][0]
            return Findings(findings=[{'claim': 'retrieval improved coverage', 'chunk_id': passage['id'],
                                       'quote': 'invented evidence' if self.bad_quote else passage['text']}])
        if role == 'synthesizer':
            return Draft(sections=[{'id': 'findings', 'heading': 'Findings',
                                    'paragraphs': ['The experiment reports improved retrieval coverage.[[1]]']}])
        if role == 'reviewer':
            self.verifications += 1
            unsupported = self.always_fail or (self.fail_once and self.verifications == 1)
            return ReviewCheck(verdicts=[{'section_id': 'findings', 'paragraph': 0,
                                          'supported': not unsupported, 'reason': 'Need stronger coverage evidence' if unsupported else '',
                                          'followup_query': 'retrieval coverage' if unsupported else ''}])
        raise AssertionError(role)


@pytest.fixture
def setup(tmp_path):
    papers = tmp_path / 'papers'
    papers.mkdir()
    make_pdf(papers / 'study.pdf')
    config = Settings(_env_file=None, workspace_root=tmp_path, allowed_roots=[tmp_path],
                      runtime_dir=tmp_path/'runtime', max_revision_rounds=1)
    payload = {'conversationId': 'conversation-1', 'project': {'id': 'project-1', 'name': 'Study',
               'workingDirectory': str(tmp_path), 'knowledgePaths': ['papers']},
               'question': 'Does retrieval improve coverage?', 'history': [], 'references': []}
    return config, payload, papers


def events(response):
    assert response.status_code == 200, response.text
    assert response.headers['content-type'].startswith('application/x-ndjson')
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def output(lines):
    sections, evidence = [], []
    for event in lines:
        if event['type'] == 'evidence':
            assert event['index'] == len(evidence) + 1
            evidence.append(event['item'])
        if event['type'] == 'section':
            sections.append({'id': event['id'], 'heading': event['heading'], 'paragraphs': []})
        if event['type'] == 'delta':
            section = next(s for s in sections if s['id'] == event['sectionId'])
            index = event['paragraph']
            assert index <= len(section['paragraphs'])
            if index == len(section['paragraphs']):
                section['paragraphs'].append('')
            section['paragraphs'][index] += event['text']
    assert lines[-1]['type'] == 'done'
    return {'sections': sections, 'evidence': evidence}


def test_full_review_pdf_and_persistence(setup):
    config, payload, papers = setup
    model = ScriptedModel()
    app = create_app(config, model)
    with TestClient(app) as client:
        assert client.get('/api/v1/health').json() == {'status': 'ok', 'apiVersion': 'v1'}
        preflight = client.options('/api/v1/reviews/stream', headers={
            'Origin': 'http://127.0.0.1:5173', 'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'content-type'})
        assert preflight.status_code == 200
        response = client.post('/api/v1/reviews/stream', json=payload)
        report = output(events(response))
        assert len(report['evidence']) == 1
        item = report['evidence'][0]
        assert item['page'] == 1 and item['paper']['pages'] == 1
        assert item['paper']['year'] is None
        assert 'retrieval' in item['excerpt']
        source = client.get('/api/v1/papers/pdf', params={'projectId': 'project-1', 'paperId': item['paper']['id']})
        assert source.status_code == 200 and source.content.startswith(b'%PDF')
        assert 'inline' in source.headers['content-disposition']
        assert client.get('/api/v1/papers/pdf', params={'projectId': 'other', 'paperId': item['paper']['id']}).status_code == 404
        run = client.get('/api/v1/runs/' + response.headers['x-run-id']).json()
        assert run['status'] == 'completed'
        assert run['report']['sections'] == report['sections']
        assert {'task_assignment', 'retrieval', 'draft_version', 'verification_report', 'reviewed_draft'} <= {a['kind'] for a in run['artifacts']}
        assert model.roles == ['coordinator', 'researcher', 'synthesizer', 'reviewer']
    reopened = Store(config.runtime_dir)
    assert reopened.run(run['id'])['status'] == 'completed'


def test_targeted_followup_and_reviewed_version(setup):
    config, payload, _ = setup
    model = ScriptedModel(fail_once=True)
    with TestClient(create_app(config, model)) as client:
        response = client.post('/api/v1/reviews/stream', json=payload)
        lines = events(response)
        assert any(e.get('feedback') for e in lines)
        run = client.get('/api/v1/runs/' + response.headers['x-run-id']).json()
        assert model.roles.count('researcher') == 2
        versions = [a['payload'] for a in run['artifacts'] if a['kind'] == 'draft_version']
        assert [v['version'] for v in versions] == [1, 2]
        assert run['report']['sections'] == output(lines)['sections']


def test_unverified_paragraphs_never_published(setup):
    config, payload, _ = setup
    model = ScriptedModel(always_fail=True)
    with TestClient(create_app(config, model)) as client:
        response = client.post('/api/v1/reviews/stream', json=payload)
        report = output(events(response))
        assert model.verifications == 2
        assert report['evidence'] == []
        assert not any(s['id'] == 'findings' for s in report['sections'])
        assert any('待核查' in p for s in report['sections'] for p in s['paragraphs'])


def test_fabricated_quote_removed(setup):
    config, payload, _ = setup
    model = ScriptedModel(bad_quote=True)
    with TestClient(create_app(config, model)) as client:
        report = output(events(client.post('/api/v1/reviews/stream', json=payload)))
        assert report['evidence'] == []
        assert 'synthesizer' not in model.roles


def test_revision_and_unchanged_audit(setup):
    config, payload, _ = setup
    model = ScriptedModel()
    with TestClient(create_app(config, model)) as client:
        original = output(events(client.post('/api/v1/reviews/stream', json=payload)))
        payload['history'] = [{'question': payload['question'], **original}]
        payload['question'] = '核查已有引用'
        model.mode = 'reply'
        response = client.post('/api/v1/reviews/stream', json=payload)
        lines = events(response)
        assert lines[-1]['reportUnchanged'] is True
        assert any(e['type'] == 'reply' for e in lines)
        assert not any(e['type'] == 'section' for e in lines)
        assert client.get('/api/v1/runs/'+response.headers['x-run-id']).json()['report']['sections'] == original['sections']
        # Tampered browser history must never use the server-owned unchanged-report shortcut.
        payload['history'][0]['sections'][0]['paragraphs'][0] = 'Fabricated browser claim[[1]]'
        assert not events(client.post('/api/v1/reviews/stream', json=payload))[-1].get('reportUnchanged')


def test_paths_missing_model_errors_and_cors(setup, tmp_path):
    config, payload, _ = setup
    with TestClient(create_app(config)) as client:
        response = client.post('/api/v1/reviews/stream', json=payload, headers={'Origin': 'http://localhost:5173'})
        assert response.status_code == 503
        assert response.json()['error']['code'] == 'MODEL_NOT_CONFIGURED'
        assert response.headers['access-control-allow-origin'] == 'http://localhost:5173'
        payload['project']['knowledgePaths'] = ['../']
        response = client.post('/api/v1/reviews/stream', json=payload)
        assert response.status_code == 422
        assert response.json()['error']['code'] == 'INVALID_KNOWLEDGE_PATH'
        payload['question'] = ' '
        assert client.post('/api/v1/reviews/stream', json=payload).status_code == 422


def test_request_size_limit(setup):
    config, payload, _ = setup
    config.max_request_bytes = 1024
    with TestClient(create_app(config, ScriptedModel())) as client:
        response = client.post('/api/v1/reviews/stream', content=b'x'*1025, headers={'Content-Type': 'application/json'})
        assert response.status_code == 413


def test_index_updates_removals_and_isolation(setup):
    config, payload, papers = setup
    store = Store(config.runtime_dir)
    library = Library(config, store)
    project = ReviewRequest.model_validate(payload).project
    scope = resolve_project(project, config)
    chunks, _ = asyncio.run(library.index(project.id, scope))
    old_id = chunks[0]['paper']['id']
    assert search(chunks, 'retrieval coverage')
    assert not search(chunks, 'quantum superconductivity')
    make_pdf(papers/'study.pdf', 'A changed retrieval paper explains a new experimental result and limitations.')
    with pytest.raises(AppError, match='论文已修改'):
        library.source(project.id, old_id)
    changed, _ = asyncio.run(library.index(project.id, scope))
    assert changed[0]['paper']['id'] != old_id
    (papers/'study.pdf').unlink()
    empty, _ = asyncio.run(library.index(project.id, scope))
    assert empty == [] and store.papers(scope.id) == []


def test_blank_pdf_and_invalid_pdf(setup):
    config, payload, papers = setup
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(str(papers/'study.pdf'))
    with TestClient(create_app(config, ScriptedModel())) as client:
        report = output(events(client.post('/api/v1/reviews/stream', json=payload)))
        assert not report['evidence']
        assert 'OCR' in str(report)
        (papers/'study.pdf').write_bytes(b'not a PDF')
        response = client.post('/api/v1/reviews/stream', json=payload)
        assert events(response)[-1]['code'] == 'PDF_PARSE_FAILED'
        assert client.get('/api/v1/runs/'+response.headers['x-run-id']).json()['status'] == 'failed'


def test_concurrency_rejection(setup):
    config, payload, _ = setup
    app = create_app(config, ScriptedModel())
    with TestClient(app) as client:
        app.state.active.add(payload['project']['id'])
        assert client.post('/api/v1/reviews/stream', json=payload).status_code == 409
        app.state.active.clear()
        app.state.active.update({'busy-1', 'busy-2'})
        assert client.post('/api/v1/reviews/stream', json=payload).status_code == 429


def test_model_adapter_json_errors_and_retry(setup):
    config, _, _ = setup
    config.model_api_key = 'test-key'
    # Settings assignments are not validated; make a correctly typed replacement instance.
    config = Settings(_env_file=None, **{**config.model_dump(), 'model_api_key': 'test-key', 'model_name': 'test-model'})
    attempts = []
    def handler(request):
        attempts.append(request)
        body = json.loads(request.content)
        assert body['response_format'] == {'type': 'json_object'}
        assert request.headers['authorization'] == 'Bearer test-key'
        if len(attempts) == 1:
            return httpx.Response(429)
        result = {'mode': 'review', 'tasks': [{'id': 'a', 'question': 'retrieval', 'queries': ['retrieval']}]}
        return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(result)}}]})
    client = ModelClient(config, httpx.MockTransport(handler))
    assert asyncio.run(client.complete('coordinator', 'test', {}, Plan)).tasks
    assert len(attempts) == 2
    invalid = ModelClient(config, httpx.MockTransport(lambda _: httpx.Response(200, json={'choices': [{'message': {'content': 'invalid'}}]})))
    with pytest.raises(AppError) as error:
        asyncio.run(invalid.complete('coordinator', 'test', {}, Plan))
    assert error.value.code == 'MODEL_OUTPUT_INVALID'


def test_stream_uses_actual_http_model_adapter(setup):
    config, payload, _ = setup
    config = Settings(_env_file=None, **{**config.model_dump(), 'model_api_key':'test-key', 'model_name':'test-model'})
    scripted = ScriptedModel()
    schemas = {'coordinator':Plan,'researcher':Findings,'synthesizer':Draft,'reviewer':ReviewCheck}
    async def provider(request):
        assert request.url.path == '/v1/chat/completions'
        body = json.loads(request.content)
        message = json.loads(body['messages'][-1]['content'])
        result = await scripted.complete(message['role'], message['task'], message['data'], schemas[message['role']])
        return httpx.Response(200,json={'choices':[{'message':{'content':result.model_dump_json()}}]})
    adapter = ModelClient(config,httpx.MockTransport(provider))
    with TestClient(create_app(config,adapter)) as client:
        report = output(events(client.post('/api/v1/reviews/stream',json=payload)))
        assert report['evidence'] and report['sections']
        assert scripted.roles == ['coordinator','researcher','synthesizer','reviewer']


def test_budget_and_pdf_size_boundaries(setup):
    config, payload, _ = setup
    config.max_model_calls = 4
    with TestClient(create_app(config, ScriptedModel(always_fail=True))) as client:
        lines = events(client.post('/api/v1/reviews/stream', json=payload))
        assert lines[-1]['type'] == 'error'
        assert lines[-1]['code'] == 'MODEL_BUDGET_EXCEEDED'
    config.max_pdf_bytes = 10
    with TestClient(create_app(config, ScriptedModel())) as client:
        assert events(client.post('/api/v1/reviews/stream', json=payload))[-1]['code'] == 'PDF_TOO_LARGE'


def test_invalid_citations_fail_closed(setup):
    config, payload, _ = setup
    class WrongCitations(ScriptedModel):
        async def complete(self, role, instruction, data, schema):
            if role == 'synthesizer':
                return Draft(sections=[{'id':'findings','heading':'Findings','paragraphs':['Invented claim[[99]]']}])
            return await super().complete(role, instruction, data, schema)
    with TestClient(create_app(config, WrongCitations())) as client:
        report = output(events(client.post('/api/v1/reviews/stream', json=payload)))
        assert not report['evidence']
        assert not any('Invented claim' in p for s in report['sections'] for p in s['paragraphs'])


def test_project_path_collision_is_rejected(setup, tmp_path):
    config, payload, _ = setup
    with TestClient(create_app(config, ScriptedModel())) as client:
        output(events(client.post('/api/v1/reviews/stream', json=payload)))
        other = tmp_path/'different'
        other.mkdir()
        payload['project']['workingDirectory'] = str(other)
        payload['project']['knowledgePaths'] = []
        assert client.post('/api/v1/reviews/stream',json=payload).status_code == 409


def test_page_numbers_and_contextual_revision(setup, tmp_path):
    from pypdf import PdfReader
    config, payload, papers = setup
    first = tmp_path/'first.pdf'
    make_pdf(first, 'This background paragraph concerns unrelated astronomy and stellar observations.')
    writer = PdfWriter()
    writer.add_page(PdfReader(first).pages[0])
    writer.add_page(PdfReader(papers/'study.pdf').pages[0])
    writer.write(str(papers/'study.pdf'))
    contexts = []
    class ContextModel(ScriptedModel):
        async def complete(self, role, instruction, data, schema):
            if role == 'synthesizer':
                contexts.append(data['context'])
            return await super().complete(role, instruction, data, schema)
    with TestClient(create_app(config, ContextModel())) as client:
        original = output(events(client.post('/api/v1/reviews/stream', json=payload)))
        assert original['evidence'][0]['page'] == 2
        assert original['evidence'][0]['paper']['pages'] == 2
        prior = {'question': payload['question'], **original}
        payload['history'] = [prior]
        payload['references'] = [{'conversationId':'related','title':'Related review','turn':prior}]
        payload['question'] = '补充这一综述的局限性'
        revised = output(events(client.post('/api/v1/reviews/stream', json=payload)))
        assert revised['sections'] and revised['evidence']
        assert contexts[-1]['history'][-1]['sections'] == original['sections']
        assert contexts[-1]['references'][0]['conversationId'] == 'related'


def test_model_failure_is_stream_error_and_releases_slot(setup):
    config, payload, _ = setup
    class BrokenModel(ScriptedModel):
        async def complete(self, *args):
            raise AppError('MODEL_TIMEOUT', '模型调用超时', 503)
    app = create_app(config, BrokenModel())
    with TestClient(app) as client:
        lines = events(client.post('/api/v1/reviews/stream', json=payload))
        assert lines[-1] == {'type': 'error', 'code': 'MODEL_TIMEOUT', 'message': '模型调用超时'}
        assert not app.state.active


def test_interrupted_runs_marked_on_restart(setup):
    config, payload, _ = setup
    store = Store(config.runtime_dir)
    store.start('unfinished', ReviewRequest.model_validate(payload))
    store.recover_interrupted()
    assert store.run('unfinished')['status'] == 'interrupted'


def test_model_repairs_schema_and_deepseek_reasoning(setup):
    config, _, _ = setup
    config = Settings(_env_file=None, **{**config.model_dump(), 'model_api_key':'test-key',
                      'model_name':'test-model', 'model_reasoning_effort':'none'})
    attempts = []
    def provider(request):
        body = json.loads(request.content)
        attempts.append(body)
        assert body['reasoning_effort'] == 'none'
        content = '{"mode":"review","tasks":[]}' if len(attempts) == 1 else json.dumps({
            'mode':'review','tasks':[{'id':'a','question':'retrieval','queries':['retrieval']}]})
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'```json\n'+content+'\n```'}}]})
    adapter = ModelClient(config,httpx.MockTransport(provider))
    result = asyncio.run(adapter.complete('coordinator','test',{},Plan))
    assert result.tasks[0].id == 'a'
    assert len(attempts) == 2
    assert 'failed schema validation' in attempts[-1]['messages'][-1]['content']
