from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pypdf import PdfWriter

from app.main import create_app
from app.research.workspace import Workspace
from app.store import Store
from test_business import setup, local_client, ScriptedModel
from test_three_agent import Trio


def test_blank_pdf_rejected_at_upload(setup):
    config,_,_=setup
    path=config.workspace_root/'blank.pdf'
    writer=PdfWriter();writer.add_blank_page(width=612,height=792)
    with path.open('wb') as stream:writer.write(stream)
    with local_client(create_app(config,ScriptedModel(),research_agents=Trio())) as client:
        response=client.post('/api/v2/projects/p/uploads',content=path.read_bytes(),headers={'Content-Type':'application/pdf'})
        assert response.status_code==422
        assert response.json()['error']['code']=='PDF_NO_EXTRACTABLE_TEXT'


def test_repeat_upload_reuses_id_and_remains_project_isolated(setup):
    config,_,papers=setup
    with local_client(create_app(config,ScriptedModel(),research_agents=Trio())) as client:
        args={'content':(papers/'study.pdf').read_bytes(),'headers':{'Content-Type':'application/pdf'}}
        a=client.post('/api/v2/projects/p/uploads',**args)
        b=client.post('/api/v2/projects/p/uploads',**args)
        assert a.status_code==b.status_code==200
        assert a.json()['file_id']==b.json()['file_id']
        assert a.json()['text_pages']==1
        assert client.get('/api/v2/projects/other/objects/'+a.json()['file_id']).status_code==404


def test_concurrent_identical_object_save_is_idempotent(setup):
    config,_,_=setup
    store=Store(config.runtime_dir);workspace=Workspace(store,'p','r')
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids=list(pool.map(lambda _:workspace.save('upload',{'hash':'same'},'upload-id'),range(40)))
    assert set(ids)=={'upload-id'}
    with store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM research_objects WHERE project='p'").fetchone()[0]==1
        assert db.execute("SELECT COUNT(*) FROM artifacts WHERE run_id='r'").fetchone()[0]==1
