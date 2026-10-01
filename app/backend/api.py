import hashlib
import json
import secrets
import time
import uuid
from typing import Literal
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt
from app.backend.database import timestamp
from app.backend.security import COOKIE, check_origin, current_user, digest, fail, verify_password

router = APIRouter(prefix='/api')
ContentType = Literal['news_article', 'youtube_script', 'short_video', 'social_post']

class Input(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

class Login(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(min_length=3, max_length=64, pattern=r'^[a-zA-Z0-9._-]+$')
    password: str = Field(min_length=1, max_length=128)

class ProjectCreate(Input):
    title: str = Field(min_length=1, max_length=200)

class ProjectUpdate(ProjectCreate):
    expected_version: int = Field(ge=1)
    archived: bool = False

class DraftSave(Input):
    model_config = ConfigDict(str_strip_whitespace=False, extra="forbid")
    news: str = Field(max_length=2000)
    content: str = Field(max_length=200000)
    content_type: ContentType
    expected_version: int = Field(ge=0)
    depth: StrictInt = Field(default=3, ge=1, le=3)
    audio_cues: StrictBool = True
    content_mode: Literal['unknown','stub','manual'] = 'unknown'

class RevisionRestore(Input):
    expected_version: int = Field(ge=0)

class JobCreate(Input):
    kind: Literal['generation', 'thumbnail', 'audio', 'video', 'simulation', 'export']
    idempotency_key: str = Field(min_length=1, max_length=100, pattern=r'^[a-zA-Z0-9._-]+$')
    payload: dict = Field(default_factory=dict)


def project(db, project_id, user, editable=False):
    row = db.execute('SELECT * FROM projects WHERE id=? AND owner_id=?', (project_id, user['user_id'])).fetchone()
    if not row:
        fail(404, 'project_not_found', 'Project not found.')
    if editable and row['archived']:
        fail(409, 'project_archived', 'Restore the project before changing its contents.')
    return row


@router.post('/auth/login')
def login(body: Login, request: Request, response: Response):
    check_origin(request)
    if request.headers.get('x-studio-request') != '1':
        fail(403, 'request_header_required', 'The studio request header is required.')
    username = body.username.lower()
    now = int(time.time())
    database = request.app.state.database
    buckets = [digest('user:' + username), digest('ip:' + (request.client.host if request.client else 'unknown'))]
    with database.transaction(write=True) as db:
        db.execute('DELETE FROM login_attempts WHERE attempted_at<?', (now - 900,))
        for bucket, limit in zip(buckets, (10, 50)):
            count = db.execute('SELECT COUNT(*) FROM login_attempts WHERE bucket=?', (bucket,)).fetchone()[0]
            if count >= limit:
                fail(429, 'login_rate_limited', 'Too many sign-in attempts. Try again in 15 minutes.')
        for bucket in buckets:
            db.execute('INSERT INTO login_attempts VALUES (?,?)', (bucket, now))
        user = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
    valid = verify_password(body.password, user['password_hash'] if user else request.app.state.dummy_password_hash)
    if not user or not valid:
        fail(401, 'invalid_credentials', 'Username or password is incorrect.')
    token = secrets.token_urlsafe(32)
    csrf = digest('csrf:' + token)
    expires = now + request.app.state.settings.session_seconds
    with database.transaction(write=True) as db:
        old = request.cookies.get(COOKIE)
        if old:
            db.execute('DELETE FROM sessions WHERE token_hash=?', (digest(old),))
        db.execute('INSERT INTO sessions VALUES (?,?,?,?,?)', (digest(token), user['id'], digest(csrf), expires, timestamp()))
        db.execute('DELETE FROM sessions WHERE expires_at<=?', (now,))
    response.set_cookie(COOKIE, token, max_age=request.app.state.settings.session_seconds, httponly=True, secure=request.app.state.settings.secure_cookies, samesite='strict', path='/')
    response.headers['Cache-Control'] = 'no-store'
    return {'user': {'id': user['id'], 'username': user['username']}, 'csrf_token': csrf, 'expires_at': expires}


@router.get('/auth/session')
def session(request: Request, response: Response, user=Depends(current_user)):
    response.headers['Cache-Control'] = 'no-store'
    return {'user': {'id': user['user_id'], 'username': user['username']}, 'csrf_token': digest('csrf:' + request.cookies[COOKIE]), 'expires_at': user['expires_at']}


@router.post('/auth/logout', status_code=204)
def logout(request: Request, user=Depends(current_user)):
    with request.app.state.database.transaction(write=True) as db:
        db.execute('DELETE FROM sessions WHERE token_hash=?', (user['token_hash'],))
    response = Response(status_code=204)
    response.delete_cookie(COOKIE, path='/', httponly=True, secure=request.app.state.settings.secure_cookies, samesite='strict')
    return response


@router.get('/configuration')
def configuration(request: Request, user=Depends(current_user)):
    return {'generation_mode': 'stub', 'max_news_characters': 2000, 'max_asset_bytes': request.app.state.settings.max_asset_bytes, 'job_execution': 'generation_worker' if request.app.state.generation_config.ready else 'not_configured', 'generation_available': request.app.state.generation_config.ready, 'generation_test_provider': getattr(request.app.state.generation_worker.provider, 'is_test', False), 'generation_provider': 'openai', 'generation_model': request.app.state.generation_config.model or None, 'generation_rates_configured': request.app.state.generation_config.pricing is not None}


@router.post('/projects', status_code=201)
def create_project(body: ProjectCreate, request: Request, user=Depends(current_user)):
    now, project_id = timestamp(), str(uuid.uuid4())
    with request.app.state.database.transaction(write=True) as db:
        db.execute('INSERT INTO projects VALUES (?,?,?,0,1,?,?)', (project_id, user['user_id'], body.title, now, now))
        return dict(project(db, project_id, user))


@router.get('/projects')
def list_projects(request: Request, archived: bool = False, limit: int = 50, offset: int = 0, user=Depends(current_user)):
    if not 1 <= limit <= 100 or offset < 0:
        fail(422, 'invalid_pagination', 'Limit must be 1–100 and offset must be nonnegative.')
    with request.app.state.database.transaction() as db:
        return {'items': [dict(row) for row in db.execute('SELECT * FROM projects WHERE owner_id=? AND archived=? ORDER BY updated_at DESC, id LIMIT ? OFFSET ?', (user['user_id'], int(archived), limit, offset))]}


@router.get('/projects/{project_id}')
def get_project(project_id: str, request: Request, user=Depends(current_user)):
    with request.app.state.database.transaction() as db:
        return dict(project(db, project_id, user))


@router.patch('/projects/{project_id}')
def update_project(project_id: str, body: ProjectUpdate, request: Request, user=Depends(current_user)):
    with request.app.state.database.transaction(write=True) as db:
        row = project(db, project_id, user)
        if row['version'] != body.expected_version:
            fail(409, 'version_conflict', 'The project changed. Reload it before saving.')
        db.execute('UPDATE projects SET title=?, archived=?, version=version+1, updated_at=? WHERE id=?', (body.title, int(body.archived), timestamp(), project_id))
        return dict(project(db, project_id, user))


def save_draft(db, project_id, body, restored_from=None):
    row = db.execute('SELECT * FROM drafts WHERE project_id=?', (project_id,)).fetchone()
    version = row['version'] if row else 0
    if version != body.expected_version:
        fail(409, 'version_conflict', 'A newer draft exists. Reload it before saving.')
    now = timestamp()
    values = (project_id, body.news, body.content, body.content_type, version + 1, now, now, body.depth, int(body.audio_cues), body.content_mode)
    db.execute('INSERT INTO drafts (project_id,news,content,content_type,version,created_at,updated_at,depth,audio_cues,content_mode) VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET news=excluded.news, content=excluded.content, content_type=excluded.content_type, version=excluded.version, updated_at=excluded.updated_at, depth=excluded.depth, audio_cues=excluded.audio_cues, content_mode=excluded.content_mode', values)
    db.execute('INSERT INTO revisions (id,project_id,version,news,content,content_type,restored_from,created_at,depth,audio_cues,content_mode) VALUES (?,?,?,?,?,?,?,?,?,?,?)', (str(uuid.uuid4()), project_id, version + 1, body.news, body.content, body.content_type, restored_from, now, body.depth, int(body.audio_cues), body.content_mode))
    db.execute('UPDATE projects SET updated_at=? WHERE id=?', (now, project_id))
    return dict(db.execute('SELECT * FROM drafts WHERE project_id=?', (project_id,)).fetchone())


@router.put('/projects/{project_id}/draft')
def put_draft(project_id: str, body: DraftSave, request: Request, user=Depends(current_user)):
    with request.app.state.database.transaction(write=True) as db:
        project(db, project_id, user, editable=True)
        return save_draft(db, project_id, body)


@router.get('/projects/{project_id}/draft')
def get_draft(project_id: str, request: Request, user=Depends(current_user)):
    with request.app.state.database.transaction() as db:
        project(db, project_id, user)
        row = db.execute('SELECT * FROM drafts WHERE project_id=?', (project_id,)).fetchone()
        if not row:
            fail(404, 'draft_not_found', 'No draft has been saved yet.')
        return dict(row)


@router.get('/projects/{project_id}/revisions')
def revisions(project_id: str, request: Request, limit: int = 50, offset: int = 0, user=Depends(current_user)):
    if not 1 <= limit <= 100 or offset < 0:
        fail(422, 'invalid_pagination', 'Limit must be 1–100 and offset must be nonnegative.')
    with request.app.state.database.transaction() as db:
        project(db, project_id, user)
        return {'items': [dict(row) for row in db.execute('SELECT id, project_id, version, content_type, restored_from, created_at FROM revisions WHERE project_id=? ORDER BY version DESC LIMIT ? OFFSET ?', (project_id, limit, offset))]}


@router.get('/projects/{project_id}/revisions/{revision_id}')
def get_revision(project_id: str, revision_id: str, request: Request, user=Depends(current_user)):
    with request.app.state.database.transaction() as db:
        project(db, project_id, user)
        row = db.execute('SELECT * FROM revisions WHERE id=? AND project_id=?', (revision_id, project_id)).fetchone()
        if not row:
            fail(404, 'revision_not_found', 'Revision not found.')
        return dict(row)


@router.post('/projects/{project_id}/revisions/{revision_id}/restore')
def restore_revision(project_id: str, revision_id: str, body: RevisionRestore, request: Request, user=Depends(current_user)):
    with request.app.state.database.transaction(write=True) as db:
        project(db, project_id, user, editable=True)
        row = db.execute('SELECT * FROM revisions WHERE id=? AND project_id=?', (revision_id, project_id)).fetchone()
        if not row:
            fail(404, 'revision_not_found', 'Revision not found.')
        restored = DraftSave(news=row['news'], content=row['content'], content_type=row['content_type'], expected_version=body.expected_version, depth=row['depth'], audio_cues=bool(row['audio_cues']), content_mode=row['content_mode'])
        return save_draft(db, project_id, restored, revision_id)


@router.post('/projects/{project_id}/assets', status_code=201)
async def upload_asset(project_id: str, request: Request, user=Depends(current_user)):
    with request.app.state.database.transaction() as db:
        project(db, project_id, user, editable=True)
    filename = request.headers.get('x-filename', 'asset.bin')
    if not 1 <= len(filename) <= 200 or '/' in filename or '\\' in filename or filename in ('.', '..') or any(ord(c) < 32 or ord(c) > 126 for c in filename):
        fail(422, 'invalid_filename', 'Use a plain ASCII filename without path separators.')
    media_type = request.headers.get('content-type', '').split(';')[0].lower()
    if media_type not in ('text/plain', 'application/json', 'image/png', 'image/jpeg', 'audio/wav', 'video/mp4', 'application/octet-stream'):
        fail(415, 'unsupported_asset_type', 'This asset type is not supported.')
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > request.app.state.settings.max_asset_bytes:
            fail(413, 'asset_too_large', 'The asset exceeds the upload limit.')
        data.extend(chunk)
    if not data:
        fail(422, 'empty_asset', 'Upload a nonempty file.')
    asset_id, now = str(uuid.uuid4()), timestamp()
    path = request.app.state.settings.data_dir / 'assets' / asset_id
    try:
        with request.app.state.database.transaction(write=True) as db:
            project(db, project_id, user, editable=True)
            with path.open('xb') as file:
                path.chmod(0o600)
                file.write(data)
            db.execute('INSERT INTO assets VALUES (?,?,?,?,?,?,?)', (asset_id, project_id, filename, media_type, len(data), hashlib.sha256(data).hexdigest(), now))
            result = dict(db.execute('SELECT * FROM assets WHERE id=?', (asset_id,)).fetchone())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return result


@router.get('/projects/{project_id}/assets')
def list_assets(project_id: str, request: Request, limit: int = 50, offset: int = 0, user=Depends(current_user)):
    if not 1 <= limit <= 100 or offset < 0:
        fail(422, 'invalid_pagination', 'Limit must be 1–100 and offset must be nonnegative.')
    with request.app.state.database.transaction() as db:
        project(db, project_id, user)
        return {'items': [dict(row) for row in db.execute('SELECT * FROM assets WHERE project_id=? ORDER BY created_at DESC, id LIMIT ? OFFSET ?', (project_id, limit, offset))]}


@router.get('/projects/{project_id}/assets/{asset_id}/download')
def download_asset(project_id: str, asset_id: str, request: Request, user=Depends(current_user)):
    with request.app.state.database.transaction() as db:
        project(db, project_id, user)
        row = db.execute('SELECT * FROM assets WHERE id=? AND project_id=?', (asset_id, project_id)).fetchone()
    if not row:
        fail(404, 'asset_not_found', 'Asset not found.')
    path = request.app.state.settings.data_dir / 'assets' / row['id']
    if not path.is_file():
        fail(409, 'asset_unavailable', 'The stored file is unavailable. Restore it from backup.')
    return FileResponse(path, media_type='application/octet-stream', filename=row['filename'], headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store'})


def job_dict(row):
    result = dict(row)
    result['payload'] = json.loads(result['payload'])
    return result


@router.post('/projects/{project_id}/jobs', status_code=201)
def create_job(project_id: str, body: JobCreate, request: Request, response: Response, user=Depends(current_user)):
    try:
        payload = json.dumps(body.payload, sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (ValueError, TypeError, RecursionError):
        fail(422, "invalid_job_payload", "The job payload must contain finite JSON values.")
    if len(payload.encode()) > 16000:
        fail(422, 'job_payload_too_large', 'Job payload exceeds 16,000 bytes.')
    with request.app.state.database.transaction(write=True) as db:
        project(db, project_id, user, editable=True)
        if body.kind == 'generation':
            from app.backend.research import ReviewedGeneration
            from app.backend.research_service import selected_snapshot
            from pydantic import ValidationError
            try:
                selection = ReviewedGeneration.model_validate(body.payload)
            except ValidationError:
                fail(422, 'invalid_generation_research', 'Select 1–100 unique claim IDs and a supported content type; free-form generation facts are not accepted.')
            verified = selected_snapshot(db, project_id, selection.claim_ids)
            payload = json.dumps(dict(selection.model_dump(), review_snapshot=verified), sort_keys=True, separators=(',', ':'), allow_nan=False)
        existing = db.execute('SELECT * FROM jobs WHERE project_id=? AND idempotency_key=?', (project_id, body.idempotency_key)).fetchone()
        if existing:
            if existing['payload'] != payload or existing['kind'] != body.kind:
                fail(409, 'idempotency_conflict', 'This key belongs to a different request.')
            response.status_code = 200
            return job_dict(existing)
        now, job_id = timestamp(), str(uuid.uuid4())
        db.execute('INSERT INTO jobs VALUES (?,?,?,\'queued\',0,?,?,NULL,NULL,?,?)', (job_id, project_id, body.kind, body.idempotency_key, payload, now, now))
        return job_dict(db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone())


@router.get('/projects/{project_id}/jobs')
def list_jobs(project_id: str, request: Request, limit: int = 50, offset: int = 0, user=Depends(current_user)):
    if not 1 <= limit <= 100 or offset < 0:
        fail(422, 'invalid_pagination', 'Limit must be 1–100 and offset must be nonnegative.')
    with request.app.state.database.transaction() as db:
        project(db, project_id, user)
        return {'items': [job_dict(row) for row in db.execute('SELECT * FROM jobs WHERE project_id=? ORDER BY created_at DESC, id LIMIT ? OFFSET ?', (project_id, limit, offset))]}


@router.get('/projects/{project_id}/jobs/{job_id}')
def get_job(project_id: str, job_id: str, request: Request, user=Depends(current_user)):
    with request.app.state.database.transaction() as db:
        project(db, project_id, user)
        row = db.execute('SELECT * FROM jobs WHERE id=? AND project_id=?', (job_id, project_id)).fetchone()
        if not row:
            fail(404, 'job_not_found', 'Job not found.')
        return job_dict(row)


@router.post('/projects/{project_id}/jobs/{job_id}/cancel')
def cancel_job(project_id: str, job_id: str, request: Request, user=Depends(current_user)):
    with request.app.state.database.transaction(write=True) as db:
        project(db, project_id, user)
        row = db.execute('SELECT * FROM jobs WHERE id=? AND project_id=?', (job_id, project_id)).fetchone()
        if not row:
            fail(404, 'job_not_found', 'Job not found.')
        if row['status'] == 'cancelled':
            return job_dict(row)
        if row['status'] not in ('queued', 'running'):
            fail(409, 'job_terminal', 'A completed job cannot be cancelled.')
        db.execute("UPDATE jobs SET status='cancelled', updated_at=? WHERE id=?", (timestamp(), job_id))
        return job_dict(db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone())
