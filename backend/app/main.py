import asyncio
import contextlib
import json
import logging
from contextlib import asynccontextmanager
from ipaddress import ip_address
from secrets import compare_digest
from uuid import uuid4

from anyio import CancelScope
from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import ValidationError
from starlette.background import BackgroundTask

from .config import Settings, settings
from .errors import AppError
from .library import Library, list_folders, resolve_project
from .model import ModelClient
from .schemas import Project, ReviewRequest
from .store import Store
from .workflow import Workflow

log = logging.getLogger('folio')


def first_error(error):
    if isinstance(error, BaseExceptionGroup):
        return first_error(error.exceptions[0])
    return error


def is_loopback(host):
    if not host:
        return False
    if host == 'localhost':
        return True
    try:
        address = ip_address(host)
        return (getattr(address, 'ipv4_mapped', None) or address).is_loopback
    except ValueError:
        return False


async def read_json(request, schema, max_bytes):
    if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
        raise AppError('INVALID_REQUEST', '请使用 application/json 请求格式。', 415)
    body = bytearray()
    async for part in request.stream():
        if len(body) + len(part) > max_bytes:
            raise AppError('REQUEST_TOO_LARGE', '请求超过大小限制，请减少对话历史或引用。', 413)
        body.extend(part)
    try:
        return schema.model_validate_json(body)
    except ValidationError:
        raise AppError('INVALID_REQUEST', '请求格式无效，请检查研究问题、项目配置和历史数据。', 422) from None


def create_app(config: Settings | None = None, model=None, research_agents=None):
    config = config or settings
    store = Store(config.runtime_dir)
    library = Library(config, store)
    model = model or ModelClient(config)
    access_token = config.access_token.get_secret_value().encode()

    async def require_access(request: Request):
        local = request.client and is_loopback(request.client.host) and is_loopback(request.url.hostname)
        if not access_token:
            if not local:
                raise AppError('LOCAL_ONLY', '未配置访问令牌，服务仅接受本机回环连接。', 403)
            return
        if not local and request.url.scheme != 'https':
            raise AppError('HTTPS_REQUIRED', '远程访问必须使用 HTTPS。', 403)
        scheme, _, supplied = request.headers.get('Authorization', '').partition(' ')
        if scheme.lower() != 'bearer' or not compare_digest(supplied.encode(), access_token):
            raise AppError('AUTH_REQUIRED', '请输入该后端的访问令牌。', 401)

    @asynccontextmanager
    async def lifespan(app):
        await asyncio.to_thread(store.recover_interrupted)
        if isinstance(model, ModelClient):
            async with model.session():
                yield
        else:
            yield

    app = FastAPI(title='Multi-Agent Literature Review', version='0.2.0', lifespan=lifespan,
                  dependencies=[Depends(require_access)])
    app.state.store, app.state.library = store, library
    app.state.model = model
    app.state.active = set()
    app.state.producers = set()
    app.add_middleware(CORSMiddleware,
                       allow_origins=list(dict.fromkeys(config.cors_origins + [config.frontend_origin])),
                       allow_credentials=False, allow_methods=['GET', 'POST', 'DELETE', 'OPTIONS'],
                       allow_headers=['Content-Type', 'Accept', 'Authorization'], expose_headers=['X-Run-Id'])

    @app.exception_handler(AppError)
    async def app_error(request, error):
        headers = {'WWW-Authenticate': 'Bearer'} if error.status == 401 else None
        return JSONResponse(error.payload(), status_code=error.status, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        return JSONResponse({'error': {'code': 'INVALID_REQUEST', 'message': '请求参数格式无效，请检查接口约定。'}}, status_code=422)

    @app.get('/health', tags=['system'])
    @app.get('/api/v1/health', tags=['system'])
    async def health():
        return {'status': 'ok', 'apiVersion': 'v1'}

    @app.get('/api/v1/folders', tags=['projects'])
    async def folders(path: str | None = Query(default=None, max_length=2048)):
        return await asyncio.to_thread(list_folders, config, path)

    @app.post('/api/v1/projects/validate', tags=['projects'])
    async def validate_project(request: Request):
        project = await read_json(request, Project, config.max_request_bytes)
        scope = await asyncio.to_thread(resolve_project, project, config)
        locked = await asyncio.to_thread(store.validate_project, project.id, scope.workdir)
        return {'workingDirectory': str(scope.workdir), 'knowledgePaths': list(map(str, scope.libraries)),
                'workingDirectoryLocked': locked}

    @app.get('/api/v1/papers/pdf', tags=['papers'])
    async def source_pdf(projectId: str, paperId: str):
        try:
            path = await asyncio.to_thread(library.source, projectId, paperId)
        except AppError as error:
            if error.code != 'PAPER_NOT_FOUND':
                raise
            import hashlib
            from pathlib import Path
            from .research.workspace import Workspace
            from .library import digest_file
            document = Workspace(store, projectId, 'read').get(paperId)
            path = Path(document.get('path', '')).resolve()
            allowed = (config.runtime_dir / 'originals' / hashlib.sha256(projectId.encode()).hexdigest()).resolve()
            if not path.is_relative_to(allowed) or not path.is_file():
                raise AppError('PAPER_NOT_FOUND', '该项目中不存在对应的原始文档。',404)
            if await asyncio.to_thread(digest_file,path) != document.get('content_hash'):
                raise AppError('ORIGINAL_CHANGED', '原始文档版本已变化。',409)
        return FileResponse(path, media_type='application/pdf', filename=path.name,
                            content_disposition_type='inline', headers={'Cache-Control': 'no-store'})

    @app.get('/api/v1/runs/{run_id}', tags=['system'])
    async def run_status(run_id: str, projectId: str | None = None, conversationId: str | None = None,
                         includeArtifacts: bool = True):
        result = await asyncio.to_thread(store.run, run_id, projectId, conversationId, includeArtifacts)
        if not result:
            raise AppError('RUN_NOT_FOUND', '任务不存在。', 404)
        return JSONResponse(result, headers={'Cache-Control': 'no-store'})

    @app.delete('/api/v1/projects/{project_id}/conversations/{conversation_id}', tags=['projects'])
    async def delete_conversation(project_id: str, conversation_id: str):
        if project_id in app.state.active:
            raise AppError('PROJECT_BUSY', '该项目仍有任务运行，请先停止或等待任务完成。', 409)
        app.state.active.add(project_id)
        try:
            # The transaction must finish before another run for this project may start.
            store.delete_conversation(project_id, conversation_id)
        finally:
            app.state.active.discard(project_id)
        return Response(status_code=204)

    @app.post('/api/v2/reviews/stream', tags=['reviews'])
    @app.post('/api/v1/reviews/stream', tags=['reviews'])
    async def review(request: Request):
        data = await read_json(request, ReviewRequest, config.max_request_bytes)
        if request.url.path.startswith('/api/v2/') and data.architecture != 'three_agent':
            raise AppError('INVALID_ARCHITECTURE', '第一版 v2 接口固定使用三个 Agent。',422)
        if data.architecture == 'legacy' and data.source_mode != 'local':
            raise AppError('SOURCE_POLICY_DENIED', '旧兼容接口仅支持本地资料。',422)
        scope = await asyncio.to_thread(resolve_project, data.project, config)
        # Validate pre-stream configuration, so the frontend gets a useful HTTP error.
        app.state.model.check()
        if data.project.id in app.state.active:
            raise AppError('PROJECT_BUSY', '该项目已有任务运行，请等待完成或停止后重试。', 409)
        if len(app.state.active) >= config.max_concurrent_reviews:
            raise AppError('SERVER_BUSY', '当前并发任务已满，请稍后重试。', 429)
        app.state.active.add(data.project.id)
        run_id = str(uuid4())
        try:
            store.bind(data.project.id, scope.workdir, scope.id)
            store.start(run_id, data)
        except AppError:
            app.state.active.discard(data.project.id)
            raise
        except Exception as failure:
            app.state.active.discard(data.project.id)
            log.error('review_start_failed run=%s error_type=%s', run_id, type(failure).__name__)
            raise AppError('INTERNAL_ERROR', '后端无法启动本轮任务，请检查服务日志和运行目录。', 500) from None
        if data.architecture == 'three_agent' and (isinstance(app.state.model, ModelClient) or research_agents is not None):
            from .research.engine import ThreeAgentWorkflow
            workflow = ThreeAgentWorkflow(config, store, library, app.state.model, run_id, agents=research_agents)
        else:
            workflow = Workflow(config, store, library, app.state.model, run_id)
        log.info('review_started run=%s project=%s conversation=%s', run_id, data.project.id, data.conversationId)
        producer = None
        released = False
        terminal = False

        async def release_run():
            nonlocal released
            if released:
                return
            released = True
            # A streaming disconnect can cancel the ASGI task while cleanup is still in progress.
            with CancelScope(shield=True):
                try:
                    if producer is not None:
                        if not producer.done():
                            producer.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await producer
                finally:
                    app.state.producers.discard(producer)
                    app.state.active.discard(data.project.id)
                    if not terminal:
                        try:
                            await asyncio.to_thread(store.finish, run_id, 'cancelled', code='CLIENT_DISCONNECTED')
                        except Exception as failure:
                            log.error('review_cancel_not_saved run=%s error_type=%s', run_id, type(failure).__name__)
                    log.info('review_finished run=%s', run_id)

        async def stream():
            nonlocal producer, terminal
            queue = asyncio.Queue(maxsize=32)

            async def produce():
                try:
                    # Whole-run timeout also bounds indexing and model retry time.
                    async with asyncio.timeout(900):
                        async for event in workflow.run(data, scope):
                            if event['type'] == 'done':
                                await asyncio.to_thread(store.finish, run_id, 'completed', workflow.report)
                            await queue.put(event)
                except Exception as failure:
                    cause = first_error(failure)
                    if isinstance(cause, AppError):
                        error = cause
                    elif isinstance(cause, TimeoutError):
                        error = AppError('RUN_TIMEOUT', '本轮运行超时，请缩小文献集或研究范围。', retryable=False)
                    else:
                        error = AppError('INTERNAL_ERROR', '后端执行失败，请检查服务日志和输入文献。', 500)
                    if not isinstance(cause, AppError):
                        import traceback
                        await asyncio.to_thread(store.artifact,run_id,'exception_diagnostic', {
                            'exception_type':type(cause).__name__,
                            'frames':[{'file':f.filename,'function':f.name,'line':f.lineno} for f in traceback.extract_tb(cause.__traceback__)[-8:]]})
                    details = error.details()
                    log.error('review_failed run=%s code=%s agent=%s error_type=%s', run_id, error.code, error.agent, type(cause).__name__)
                    try:
                        await asyncio.to_thread(store.finish, run_id, 'failed', error=details)
                    except Exception as failure:
                        log.error('review_error_not_saved run=%s error_type=%s', run_id, type(failure).__name__)
                    await queue.put({'type': 'error', **details})

            producer = asyncio.create_task(produce())
            app.state.producers.add(producer)
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=.5)
                    except TimeoutError:
                        yield '\n'  # NDJSON keepalive, ignored by the frontend parser.
                        continue
                    terminal = event['type'] in ('done', 'error')
                    yield json.dumps(event, ensure_ascii=False) + '\n'
                    if terminal:
                        break
            finally:
                await release_run()

        return StreamingResponse(stream(), media_type='application/x-ndjson', headers={
            'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no', 'X-Run-Id': run_id,
        }, background=BackgroundTask(release_run))

    @app.post('/api/v2/projects/{project_id}/uploads')
    async def upload(project_id: str, request: Request):
        import hashlib
        from .research.workspace import Workspace, identifier
        if request.headers.get('content-type','').split(';')[0] != 'application/pdf':
            raise AppError('INVALID_FILE', '上传正文必须是 application/pdf。', 415)
        content = bytearray()
        async for part in request.stream():
            if len(content)+len(part)>config.max_pdf_bytes:
                raise AppError('PDF_TOO_LARGE','PDF 超出文件大小限制。',413)
            content.extend(part)
        if not content.startswith(b'%PDF'):
            raise AppError('INVALID_FILE','上传文件不是 PDF。',422)
        from .library import parse_pdf
        folder=config.runtime_dir/'uploads'/hashlib.sha256(project_id.encode()).hexdigest()
        folder.mkdir(parents=True,exist_ok=True)
        path=folder/(hashlib.sha256(content).hexdigest()+'.pdf')
        if not path.exists(): path.write_bytes(content)
        await parse_pdf(path, config)
        ws=Workspace(store,project_id,'upload')
        file_id=identifier('upload')
        ws.save('upload',{'kind':'upload','path':str(path),'content_hash':hashlib.sha256(content).hexdigest()},file_id)
        return {'file_id':file_id}

    @app.get('/api/v2/projects/{project_id}/objects/{object_id}')
    async def research_object(project_id: str, object_id: str):
        from .research.workspace import Workspace
        return Workspace(store,project_id,'read').get(object_id)

    return app


app = create_app()
