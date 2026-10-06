from contextlib import asynccontextmanager
from typing import Literal
import logging
import sqlite3
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt
from app.backend.api import router
from app.backend.research import router as research_router
from app.backend.draft_export import router as export_router
from app.backend.generation import router as generation_router, GenerationWorker
from app.backend.generation_provider import GenerationConfig
from app.backend.config import ROOT, Settings
from app.backend.database import Database
from app.backend.security import hash_password

logger = logging.getLogger(__name__)

class GenerateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    news: str = Field(min_length=1, max_length=2000)
    content_type: Literal['news_article', 'youtube_script', 'short_video', 'social_post']
    depth: StrictInt = Field(default=3, ge=1, le=3)
    audio_cues: StrictBool = True

class GenerateResponse(BaseModel):
    content: str
    content_type: str
    mode: Literal['stub'] = 'stub'
    depth: int = 3
    audio_cues: bool = True

class BodyTooLarge(Exception):
    pass

class BodyLimitMiddleware:
    def __init__(self, app, max_asset_bytes):
        self.app = app
        self.max_asset_bytes = max_asset_bytes

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        limit = self.max_asset_bytes if scope['method'] == 'POST' and scope['path'].endswith('/assets') else 2 * 1024 * 1024
        total = 0
        oversized = False
        headers = dict(scope.get('headers', []))
        try:
            declared_size = int(headers.get(b'content-length', b'0'))
        except ValueError:
            declared_size = 0
        if declared_size > limit:
            response = JSONResponse(status_code=413, content={'detail': {'code': 'body_too_large', 'message': 'The request body exceeds the size limit.'}})
            return await response(scope, receive, send)
        async def limited_receive():
            nonlocal total, oversized
            message = await receive()
            if message['type'] == 'http.request':
                total += len(message.get('body', b''))
                if total > limit:
                    oversized = True
                    raise BodyTooLarge()
            return message
        async def checked_send(message):
            if oversized:
                raise BodyTooLarge()
            await send(message)
        try:
            await self.app(scope, limited_receive, checked_send)
        except BodyTooLarge:
            response = JSONResponse(status_code=413, content={'detail': {'code': 'body_too_large', 'message': 'The request body exceeds the size limit.'}})
            await response(scope, receive, send)


def create_app(settings=None, generation_config=None, generation_provider=None, start_worker=True):
    settings = settings or Settings.from_env()
    database = Database(settings.data_dir)
    generation_config = generation_config or GenerationConfig.from_env()
    worker = GenerationWorker(database, generation_config, generation_provider)
    @asynccontextmanager
    async def lifespan(application):
        database.initialize()
        application.state.dummy_password_hash = hash_password('dummy-' + '0' * 32)
        if start_worker:
            worker.start()
        try:
            yield
        finally:
            worker.stop()

    application = FastAPI(title='Football Pulse AI Studio', lifespan=lifespan)
    application.state.settings = settings
    application.state.database = database
    application.state.generation_config = generation_config
    application.state.generation_worker = worker
    application.add_middleware(BodyLimitMiddleware, max_asset_bytes=settings.max_asset_bytes)

    @application.middleware('http')
    async def response_headers(request, call_next):
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc):
        # Do not echo passwords or submitted content in validation responses.
        fields = [{'field': '.'.join(str(x) for x in e['loc']), 'type': e['type']} for e in exc.errors()]
        return JSONResponse(status_code=422, content={'detail': {'code': 'validation_error', 'message': 'The request is invalid.', 'fields': fields}})

    @application.exception_handler(sqlite3.OperationalError)
    async def database_unavailable(request: Request, exc):
        logger.error('Database operation failed (%s)', type(exc).__name__)
        return JSONResponse(status_code=503, content={'detail': {'code': 'database_unavailable', 'message': 'Saved work is temporarily unavailable. Please retry.'}})

    @application.exception_handler(OSError)
    async def storage_unavailable(request: Request, exc):
        logger.error('Storage operation failed (%s)', type(exc).__name__)
        return JSONResponse(status_code=503, content={'detail': {'code': 'storage_unavailable', 'message': 'File storage is temporarily unavailable. Please retry.'}})

    application.mount('/static', StaticFiles(directory=ROOT / 'app/static'), name='static')
    application.include_router(router)
    application.include_router(research_router)
    application.include_router(export_router)
    application.include_router(generation_router)

    @application.get('/', response_class=HTMLResponse)
    def home():
        return (ROOT / 'app/templates/workspace.html').read_text(encoding='utf-8')

    @application.get('/desktop', response_class=HTMLResponse)
    @application.get('/results', response_class=HTMLResponse)
    def desktop_creator():
        return (ROOT / 'app/templates/workspace_desktop.html').read_text(encoding='utf-8')

    @application.get('/legacy', response_class=HTMLResponse)
    def legacy_creator():
        return (ROOT / 'app/templates/index.html').read_text(encoding='utf-8')

    @application.get('/workspace/mobile-original', response_class=HTMLResponse)
    def original_mobile_creator():
        return (ROOT / 'app/templates/workspace_original.html').read_text(encoding='utf-8')

    @application.get('/health')
    def health():
        with database.transaction() as db:
            version = db.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0]
        return {'status': 'ok', 'generation_mode': 'stub', 'schema_version': version}

    @application.post('/api/generate', response_model=GenerateResponse)
    def generate_content(request: GenerateRequest):
        # Public M1 stub remains available; saved-work APIs require authentication.
        return GenerateResponse(content='Test response from Football Pulse AI Studio. AI generation is not connected yet.', content_type=request.content_type, depth=request.depth, audio_cues=request.audio_cues)

    return application

app = create_app()
