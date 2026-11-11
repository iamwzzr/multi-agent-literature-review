"""Real TCP test: in-process TestClient buffers streams and cannot prove disconnect handling."""
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

from test_business import make_pdf


def test_disconnect_cancels_model_and_releases_project(tmp_path):
    papers = tmp_path / 'papers'
    papers.mkdir()
    make_pdf(papers/'paper.pdf')
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    sock.close()
    backend = Path(__file__).resolve().parents[1]
    code = '''
import asyncio,sys,uvicorn
from pathlib import Path
from app.main import create_app
from app.config import Settings
from test_business import ScriptedModel
class SlowModel(ScriptedModel):
    async def complete(self,*args):
        await asyncio.sleep(60)
        return await super().complete(*args)
root=Path(sys.argv[1])
config=Settings(_env_file=None,workspace_root=root,allowed_roots=[root],runtime_dir=root/'runtime')
uvicorn.run(create_app(config,SlowModel()),host='127.0.0.1',port=int(sys.argv[2]),log_level='warning')
'''
    # Explicit test-only PYTHONPATH; production has no fake-model configuration switch.
    import os
    env = dict(os.environ, PYTHONPATH=str(backend) + os.pathsep + str(backend/'tests'))
    process = subprocess.Popen([sys.executable, '-c', code, str(tmp_path), str(port)],
                               cwd=backend, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f'http://127.0.0.1:{port}'
    try:
        with httpx.Client(timeout=5, trust_env=False) as client:
            for _ in range(80):
                if process.poll() is not None:
                    raise AssertionError(process.stdout.read().decode(errors='replace'))
                try:
                    if client.get(base+'/api/v1/health').status_code == 200:
                        break
                except httpx.RequestError:
                    pass
                time.sleep(.1)
            else:
                raise AssertionError('Server did not start')
            payload = {'conversationId':'cancel-test','project':{'id':'cancel-project','name':'Test',
                       'workingDirectory':str(tmp_path),'knowledgePaths':['papers']},
                       'question':'retrieval coverage','history':[],'references':[]}
            with client.stream('POST',base+'/api/v1/reviews/stream',json=payload) as response:
                assert response.status_code == 200
                run_id = response.headers['x-run-id']
                assert json.loads(next(response.iter_lines()))['type'] == 'phase'
            for _ in range(80):
                run = client.get(base+'/api/v1/runs/'+run_id).json()
                if run['status'] == 'cancelled':
                    break
                time.sleep(.1)
            assert run['status'] == 'cancelled'
            # The same project must be admitted again instead of remaining stuck as PROJECT_BUSY.
            with client.stream('POST',base+'/api/v1/reviews/stream',json=payload) as response:
                assert response.status_code == 200
    finally:
        process.terminate()
        process.communicate(timeout=10)
