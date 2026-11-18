import pytest

from app.errors import AppError
from app.main import create_app
from app.research.anchors import locate_quote
from app.research.context import EvidenceRegistry
from app.research.engine import ThreeAgentWorkflow
from app.research.workspace import Workspace
from app.store import Store
from test_business import setup, local_client, ScriptedModel, events, output
from test_three_agent import Trio


def test_anchor_preserves_raw_offsets_across_spaces_and_linebreaks():
    text='Header\n\nThe  method\nretrieves passages.\nFooter'
    found=locate_quote(text,'The method retrieves passages.')
    assert found['status']=='matched'
    anchor=found['candidates'][0]
    assert text[anchor['raw_start']:anchor['raw_end']]=='The  method\nretrieves passages.'
    assert anchor['line_start']==3 and anchor['line_end']==4
    assert ' '.join(text.split())[anchor['start']:anchor['end']]==anchor['selector']['exact']


def test_duplicate_quote_is_ambiguous_until_a_valid_offset_is_supplied():
    text='Repeated original. Other context. Repeated original.'
    found=locate_quote(text,'Repeated original.')
    assert found['status']=='ambiguous' and len(found['candidates'])==2
    position=text.rfind('Repeated original.')
    assert locate_quote(text,'Repeated original.',position)['candidates'][0]['start']==position
    assert locate_quote(text,'Repeated original.',position+1)['status']=='mismatch'


@pytest.mark.parametrize('quote',['','fabricated paraphrase'])
def test_no_fuzzy_match_can_become_verified(quote):
    assert locate_quote('Real source sentence.',quote)['status']=='missing'


def test_chunk_boundary_whitespace_does_not_shift_page_anchor():
    text='a'*1300+' '+'retrieval evidence '*200
    chunks=[]
    ThreeAgentWorkflow.add_chunks({'document_id':'d','paper_id':'p','pages':[text]},
        {'paper_id':'p','title':'Title'},chunks)
    for chunk in chunks:
        anchor=locate_quote(text,chunk['text'],chunk['start'])
        assert anchor['status']=='matched'
        assert text[chunk['start']:chunk['end']]==chunk['text']


def test_chunk_offsets_and_short_quote_are_copied_from_source(setup):
    config,_,_=setup
    text='Background. The method retrieves passages using the input query. Limitations remain.'
    doc={'document_id':'d','paper_id':'p','pages':[text],'correspondence':'user_provided'}
    chunks=[]
    ThreeAgentWorkflow.add_chunks(doc,{'paper_id':'p','title':'Title'},chunks)
    cards=[]
    registry=EvidenceRegistry(lambda:{c['id']:c for c in chunks},{'d':doc},Workspace(Store(config.runtime_dir),'a','r'),cards)
    quote='The method retrieves passages using the input query.'
    card=registry.add(chunks[0]['id'],'finding',{},quote=quote)
    assert card['quote']==quote and text[card['location']['start']:card['location']['end']]==quote
    assert registry.add(chunks[0]['id'],'same quote',{},quote=quote)['evidence_id']==card['evidence_id']
    with pytest.raises(AppError):
        registry.add(chunks[0]['id'],'fake',{},quote='The method never retrieves passages.')


def test_location_endpoint_fresh_source_project_isolation_and_hash(setup):
    from pathlib import Path
    config,payload,_=setup
    with local_client(create_app(config,ScriptedModel(),research_agents=Trio())) as client:
        response=client.post('/api/v2/reviews/stream',json=payload)
        delivered=output(events(response))
        evidence=delivered['evidence'][0]
        url='/api/v2/projects/'+payload['project']['id']+'/evidence/'+evidence['evidenceId']+'/location'
        result=client.get(url)
        assert result.status_code==200
        anchor=result.json()
        assert anchor['status']=='matched' and anchor['page']==evidence['page']
        assert anchor['candidates'][0]['selector']['exact']==evidence['excerpt']
        assert anchor['supports_pdf_coordinates'] is False
        assert client.get(url.replace(payload['project']['id'],'wrong-project')).status_code==404
        ws=Workspace(Store(config.runtime_dir),payload['project']['id'],'read')
        doc=ws.get(evidence['paper']['id'])
        Path(doc['path']).write_bytes(b'%PDF changed')
        assert client.get(url).status_code==409
