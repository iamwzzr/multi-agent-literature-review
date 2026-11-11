import asyncio
import contextlib
import json
import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import ValidationError

from .config import Settings, settings
from .errors import AppError
from .library import Library, resolve_project
from .model import ModelClient
from .schemas import ReviewRequest
from .store import Store
from .workflow import Workflow

log = logging.getLogger('folio')


def first_error(error):
    if isinstance(error, BaseExceptionGroup):
        return first_error(error.exceptions[0])
    return error


def create_app(config: Settings | None = None, model=None):
    config = config or settings
    store = Store(config.runtime_dir)
    library = Library(config, store)

    @asynccontextmanager
    async def lifespan(app):
        store.recover_interrupted()
        yield

    app = FastAPI(title='Multi-Agent Literature Review', version='0.2.0', lifespan=lifespan)
    app.state.store, app.state.library = store, library
    app.state.model = model or ModelClient(config)
    app.state.active = set()
    app.state.producers = set()
    app.add_middleware(CORSMiddleware,
                       allow_origins=list(dict.fromkeys(config.cors_origins + [config.frontend_origin])),
                       allow_credentials=False, allow_methods=['GET', 'POST', 'OPTIONS'],
                       allow_headers=['Content-Type', 'Accept'], expose_headers=['X-Run-Id'])

    @app.exception_handler(AppError)
    async def app_error(request, error):
        return JSONResponse(error.payload(), status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        return JSONResponse({'error': {'code': 'INVALID_REQUEST', 'message': '请求参数格式无效，请检查接口约定。'}}, status_code=422)

    @app.get('/health', tags=['system'])
    @app.get('/api/v1/health', tags=['system'])
    async def health():
        return {'status': 'ok', 'apiVersion': 'v1'}

    @app.get('/api/v1/papers/pdf', tags=['papers'])
    async def source_pdf(projectId: str, paperId: str):
        path = await asyncio.to_thread(library.source, projectId, paperId)
        return FileResponse(path, media_type='application/pdf', filename=path.name,
                            content_disposition_type='inline', headers={'Cache-Control': 'no-store'})

    @app.get('/api/v1/runs/{run_id}', tags=['system'])
    async def run_status(run_id: str):
        result = store.run(run_id)
        if not result:
            raise AppError('RUN_NOT_FOUND', '任务不存在。', 404)
        return result

    @app.post('/api/v1/reviews/stream', tags=['reviews'])
    async def review(request: Request):
        if request.headers.get('content-type', '').split(';')[0].lower() != 'application/json':
            raise AppError('INVALID_REQUEST', '请使用 application/json 请求格式。', 415)
        body = bytearray()
        async for part in request.stream():
            body.extend(part)
            if len(body) > config.max_request_bytes:
                raise AppError('REQUEST_TOO_LARGE', '请求超过大小限制，请减少对话历史或引用。', 413)
        try:
            data = ReviewRequest.model_validate_json(bytes(body))
        except ValidationError:
            raise AppError('INVALID_REQUEST', '请求格式无效，请检查研究问题、项目配置和历史数据。', 422) from None
        scope = resolve_project(data.project, config)
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
        except Exception:
            app.state.active.discard(data.project.id)
            raise
        workflow = Workflow(config, store, library, app.state.model, run_id)
        log.info('review_started run=%s project=%s conversation=%s', run_id, data.project.id, data.conversationId)

        async def stream():
            queue = asyncio.Queue(maxsize=32)

            async def produce():
                try:
                    # Whole-run timeout also bounds indexing and model retry time.
                    async with asyncio.timeout(900):
                        async for event in workflow.run(data, scope):
                            if event['type'] == 'done':
                                store.finish(run_id, 'completed', workflow.report)
                            await queue.put(event)
                except asyncio.CancelledError:
                    store.finish(run_id, 'cancelled', code='CLIENT_DISCONNECTED')
                    raise
                except Exception as failure:
                    error = first_error(failure)
                    if isinstance(error, AppError):
                        code, message = error.code, error.message
                    elif isinstance(error, TimeoutError):
                        code, message = 'RUN_TIMEOUT', '本轮运行超时，请缩小文献集或研究范围。'
                    else:
                        code, message = 'INTERNAL_ERROR', '后端执行失败，请检查本机日志和输入文献。'
                    log.error('review_failed run=%s code=%s error_type=%s', run_id, code, type(error).__name__)
                    store.finish(run_id, 'failed', code=code)
                    await queue.put({'type': 'error', 'code': code, 'message': message})

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
                    yield json.dumps(event, ensure_ascii=False) + '\n'
                    if event['type'] in ('done', 'error'):
                        break
            finally:
                if not producer.done():
                    producer.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await producer
                app.state.producers.discard(producer)
                app.state.active.discard(data.project.id)
                log.info('review_finished run=%s', run_id)

        return StreamingResponse(stream(), media_type='application/x-ndjson', headers={
            'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no', 'X-Run-Id': run_id,
        })

    return app


app = create_app()
