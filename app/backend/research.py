from datetime import datetime, timedelta, timezone
import hashlib
import json
import unicodedata
import uuid
from fastapi import APIRouter, Depends, Request, Response
from pydantic import StrictBool, StrictInt, Field, field_validator
from app.backend.api import Input, project, ContentType
from app.backend.database import timestamp
from app.backend.security import current_user, fail
from app.backend.source_import import canonical_url, fetch_source, SourceImportError
from app.backend.research_service import evidence_snapshot, invalidate_claim, review_record, selected_snapshot, verification_blockers
from typing import Literal

router = APIRouter(prefix='/api/projects/{project_id}/research')


def dated(value):
    if value is None:
        return None
    date = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if date.tzinfo is None:
        raise ValueError('Use an ISO date and time with a timezone')
    date = date.astimezone(timezone.utc)
    if date > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ValueError('Future dates cannot be used as recorded events or publications')
    return date.isoformat()


class SourceCreate(Input):
    url: str = Field(min_length=1, max_length=2048)
    title: str = Field(min_length=1, max_length=200)
    publisher: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=100000)
    published_at: str | None = Field(default=None, max_length=60)
    _url = field_validator('url')(canonical_url)
    _date = field_validator('published_at')(dated)

class SourceImport(Input):
    url: str = Field(min_length=1, max_length=2048)
    _url = field_validator('url')(canonical_url)

class SourceStatus(Input):
    status: Literal['active','withdrawn']
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=10, max_length=2000)

class SourceMetadata(Input):
    title: str = Field(min_length=1, max_length=200)
    publisher: str = Field(min_length=1, max_length=100)
    published_at: str | None = Field(default=None, max_length=60)
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=10, max_length=2000)
    _date = field_validator('published_at')(dated)

class ClaimCreate(Input):
    statement: str = Field(min_length=1, max_length=4000)
    event_at: str | None = Field(default=None, max_length=60)
    _date = field_validator('event_at')(dated)

class EvidenceCreate(Input):
    source_id: str = Field(min_length=1, max_length=36)
    quote: str = Field(min_length=1, max_length=4000)
    quote_start: int | None = Field(default=None, ge=0)
    relation: Literal['supports','contradicts','context']
    expected_claim_version: int = Field(ge=1)

class EvidenceWithdraw(Input):
    expected_claim_version: int = Field(ge=1)
    reason: str = Field(min_length=10, max_length=2000)

class ReviewCreate(Input):
    decision: Literal['pending','verified','rejected','disputed']
    reason: str = Field(min_length=10, max_length=2000)
    expected_version: int = Field(ge=1)

class ResearchSelection(Input):
    claim_ids: list[str] = Field(min_length=1, max_length=100)
    @field_validator('claim_ids')
    @classmethod
    def ids(cls, values):
        if len(set(values)) != len(values):
            raise ValueError('Select each claim only once')
        for value in values:
            if str(uuid.UUID(value)) != value:
                raise ValueError('Claim IDs must be canonical UUIDs')
        return values

class ReviewedGeneration(ResearchSelection):
    content_type: ContentType = 'youtube_script'
    depth: StrictInt = Field(default=3, ge=1, le=3)
    audio_cues: StrictBool = True


def pagination(limit, offset):
    if not 1 <= limit <= 100 or offset < 0:
        fail(422, 'invalid_pagination', 'Limit must be 1–100 and offset must be nonnegative.')


def source(db, project_id, source_id):
    row = db.execute('SELECT * FROM research_sources WHERE id=? AND project_id=?', (source_id, project_id)).fetchone()
    if not row:
        fail(404, 'source_not_found', 'Source not found in this project.')
    return row


def claim(db, project_id, claim_id):
    row = db.execute('SELECT * FROM research_claims WHERE id=? AND project_id=?', (claim_id, project_id)).fetchone()
    if not row:
        fail(404, 'claim_not_found', 'Claim not found in this project.')
    return row


def source_event(db, row, actor_id, reason):
    snapshot = {key:row[key] for key in ('url','title','publisher','published_at','content_hash','status','version')}
    db.execute('INSERT INTO source_events VALUES (?,?,?,?,?,?,?,?)', (str(uuid.uuid4()), row['id'], actor_id, row['status'], reason, row['version'], json.dumps(snapshot, sort_keys=True), timestamp()))


def source_changed(db, source_id, actor_id, reason, event):
    linked = db.execute('SELECT DISTINCT claim_id FROM claim_evidence WHERE source_id=?', (source_id,)).fetchall()
    for entry in linked:
        invalidate_claim(db, entry['claim_id'], actor_id, reason, event)


def insert_source(db, project_id, body, acquisition, response, actor_id):
    fingerprint = hashlib.sha256(body.text.encode()).hexdigest()
    existing = db.execute('SELECT * FROM research_sources WHERE project_id=? AND url=? AND content_hash=?', (project_id, body.url, fingerprint)).fetchone()
    if existing:
        if any(existing[key] != getattr(body, key) for key in ('title','publisher','published_at')):
            fail(409, 'source_metadata_conflict', 'This snapshot already exists with different metadata. Use the version-checked metadata endpoint.')
        response.status_code = 200
        return dict(existing)
    duplicate = db.execute('SELECT id FROM research_sources WHERE project_id=? AND content_hash=? ORDER BY captured_at,id LIMIT 1', (project_id, fingerprint)).fetchone()
    source_id = str(uuid.uuid4())
    db.execute('''INSERT INTO research_sources (id,project_id,url,title,publisher,published_at,captured_at,acquisition,text,content_hash,duplicate_of)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)''', (source_id, project_id, body.url, body.title, body.publisher, body.published_at, timestamp(), acquisition, body.text, fingerprint, duplicate['id'] if duplicate else None))
    older = db.execute("SELECT * FROM research_sources WHERE project_id=? AND url=? AND id<>? AND status='active'", (project_id, body.url, source_id)).fetchall()
    for previous in older:
        reason = 'A changed text snapshot was ingested for this source URL.'
        db.execute("UPDATE research_sources SET status='withdrawn',version=version+1,withdrawn_reason=? WHERE id=?", (reason, previous['id']))
        source_event(db, source(db, project_id, previous['id']), actor_id, reason)
        source_changed(db, previous['id'], actor_id, reason, 'source_superseded')
    source_event(db, source(db, project_id, source_id), actor_id, 'Source snapshot ingested.')
    return dict(source(db, project_id, source_id))


@router.post('/sources', status_code=201)
def create_source(project_id: str, body: SourceCreate, request: Request, response: Response, user=Depends(current_user)):
    with request.app.state.database.transaction(write=True) as db:
        project(db, project_id, user, editable=True)
        return insert_source(db, project_id, body, 'manual', response, user['user_id'])


@router.post('/sources/import', status_code=201)
def import_source(project_id: str, body: SourceImport, request: Request, response: Response, user=Depends(current_user)):
    with request.app.state.database.transaction() as db:
        project(db, project_id, user, editable=True)
    try:
        fetched = fetch_source(body.url)
        imported = SourceCreate(**fetched)
    except SourceImportError as exc:
        fail(502 if exc.code in ('source_connection_failed','source_dns_failed','source_http_failed','source_timeout') else 422, exc.code, str(exc))
    with request.app.state.database.transaction(write=True) as db:
        project(db, project_id, user, editable=True)
        return insert_source(db, project_id, imported, 'url_import', response, user['user_id'])


@router.get('/sources')
def list_sources(project_id: str, request: Request, limit: int = 50, offset: int = 0, user=Depends(current_user)):
    pagination(limit, offset)
    with request.app.state.database.transaction() as db:
        project(db, project_id, user)
        return {'items':[dict(row) for row in db.execute('SELECT id,project_id,url,title,publisher,published_at,captured_at,acquisition,content_hash,duplicate_of,status,version,withdrawn_reason FROM research_sources WHERE project_id=? ORDER BY captured_at DESC,id LIMIT ? OFFSET ?', (project_id, limit, offset))]}


@router.get('/sources/{source_id}')
def get_source(project_id: str, source_id: str, request: Request, user=Depends(current_user)):
    with request.app.state.database.transaction() as db:
        project(db, project_id, user)
        row = dict(source(db, project_id, source_id))
        row['history'] = [dict(r) for r in db.execute('SELECT * FROM source_events WHERE source_id=? ORDER BY source_version', (source_id,))]
        return row


@router.patch('/sources/{source_id}/status')
def change_source_status(project_id: str, source_id: str, body: SourceStatus, request: Request, user=Depends(current_user)):
    with request.app.state.database.transaction(write=True) as db:
        project(db, project_id, user, editable=True)
        row = source(db, project_id, source_id)
        if row['version'] != body.expected_version:
            fail(409, 'version_conflict', 'The source changed. Reload it before reviewing.')
        if row['status'] == body.status:
            fail(409, 'source_status_unchanged', 'The source already has this status.')
        db.execute('UPDATE research_sources SET status=?, version=version+1, withdrawn_reason=? WHERE id=?', (body.status, body.reason if body.status == 'withdrawn' else None, source_id))
        source_event(db, source(db, project_id, source_id), user['user_id'], body.reason)
        source_changed(db, source_id, user['user_id'], body.reason, 'source_'+body.status)
        return dict(source(db, project_id, source_id))


@router.patch('/sources/{source_id}/metadata')
def update_source_metadata(project_id: str, source_id: str, body: SourceMetadata, request: Request, user=Depends(current_user)):
    with request.app.state.database.transaction(write=True) as db:
        project(db, project_id, user, editable=True)
        row = source(db, project_id, source_id)
        if row['version'] != body.expected_version:
            fail(409, 'version_conflict', 'The source changed. Reload it before correcting metadata.')
        db.execute('UPDATE research_sources SET title=?,publisher=?,published_at=?,version=version+1 WHERE id=?', (body.title, body.publisher, body.published_at, source_id))
        source_event(db, source(db, project_id, source_id), user['user_id'], body.reason)
        source_changed(db, source_id, user['user_id'], body.reason, 'source_metadata_changed')
        return dict(source(db, project_id, source_id))


@router.post('/claims', status_code=201)
def create_claim(project_id: str, body: ClaimCreate, request: Request, response: Response, user=Depends(current_user)):
    normalized = ' '.join(unicodedata.normalize('NFKC', body.statement).casefold().split())
    fingerprint = hashlib.sha256((normalized + '\n' + (body.event_at or '')).encode()).hexdigest()
    with request.app.state.database.transaction(write=True) as db:
        project(db, project_id, user, editable=True)
        existing = db.execute('SELECT * FROM research_claims WHERE project_id=? AND fingerprint=?', (project_id, fingerprint)).fetchone()
        if existing:
            response.status_code = 200
            return dict(existing)
        claim_id, now = str(uuid.uuid4()), timestamp()
        db.execute('INSERT INTO research_claims VALUES (?,?,?,?,?,\'pending\',1,?,?)', (claim_id, project_id, body.statement, fingerprint, body.event_at, now, now))
        return dict(claim(db, project_id, claim_id))


@router.get('/claims')
def list_claims(project_id: str, request: Request, limit: int = 50, offset: int = 0, user=Depends(current_user)):
    pagination(limit, offset)
    with request.app.state.database.transaction() as db:
        project(db, project_id, user)
        return {'items':[dict(row) for row in db.execute('SELECT * FROM research_claims WHERE project_id=? ORDER BY created_at DESC,id LIMIT ? OFFSET ?', (project_id, limit, offset))]}


@router.get('/claims/{claim_id}')
def get_claim(project_id: str, claim_id: str, request: Request, user=Depends(current_user)):
    with request.app.state.database.transaction() as db:
        project(db, project_id, user)
        result = dict(claim(db, project_id, claim_id))
        result['evidence'] = evidence_snapshot(db, claim_id)
        result['verification_blockers'] = verification_blockers(db, claim_id)
        result['reviews'] = []
        for row in db.execute('SELECT * FROM claim_reviews WHERE claim_id=? ORDER BY claim_version,id', (claim_id,)):
            review = dict(row)
            review['evidence_snapshot'] = json.loads(review['evidence_snapshot'])
            result['reviews'].append(review)
        return result


@router.post('/claims/{claim_id}/evidence', status_code=201)
def add_evidence(project_id: str, claim_id: str, body: EvidenceCreate, request: Request, response: Response, user=Depends(current_user)):
    with request.app.state.database.transaction(write=True) as db:
        project(db, project_id, user, editable=True)
        row = claim(db, project_id, claim_id)
        if row['version'] != body.expected_claim_version:
            fail(409, 'version_conflict', 'The claim changed. Reload it before adding evidence.')
        evidence_source = source(db, project_id, body.source_id)
        if evidence_source['status'] != 'active':
            fail(409, 'source_withdrawn', 'This source is withdrawn.')
        start = body.quote_start if body.quote_start is not None else evidence_source['text'].find(body.quote)
        end = start + len(body.quote)
        if start < 0 or evidence_source['text'][start:end] != body.quote:
            fail(422, 'quote_not_in_source', 'The quote must exactly match the stored source text.')
        existing = db.execute('SELECT * FROM claim_evidence WHERE claim_id=? AND source_id=? AND quote_start=? AND quote_end=? AND relation=?', (claim_id, body.source_id, start, end, body.relation)).fetchone()
        if existing:
            if existing['status'] == 'withdrawn':
                fail(409, 'evidence_withdrawn', 'This exact evidence was withdrawn. Its history is preserved.')
            response.status_code = 200
            return dict(existing)
        evidence_id = str(uuid.uuid4())
        db.execute('INSERT INTO claim_evidence (id,claim_id,source_id,quote,quote_start,quote_end,relation,created_at) VALUES (?,?,?,?,?,?,?,?)', (evidence_id, claim_id, body.source_id, body.quote, start, end, body.relation, timestamp()))
        invalidate_claim(db, claim_id, user['user_id'], 'Evidence added; a fresh review is required.', 'evidence_added')
        return dict(db.execute('SELECT * FROM claim_evidence WHERE id=?', (evidence_id,)).fetchone())


@router.post('/claims/{claim_id}/evidence/{evidence_id}/withdraw')
def withdraw_evidence(project_id: str, claim_id: str, evidence_id: str, body: EvidenceWithdraw, request: Request, user=Depends(current_user)):
    with request.app.state.database.transaction(write=True) as db:
        project(db, project_id, user, editable=True)
        row = claim(db, project_id, claim_id)
        if row['version'] != body.expected_claim_version:
            fail(409, 'version_conflict', 'The claim changed. Reload it before withdrawing evidence.')
        evidence = db.execute('SELECT * FROM claim_evidence WHERE id=? AND claim_id=?', (evidence_id, claim_id)).fetchone()
        if not evidence:
            fail(404, 'evidence_not_found', 'Evidence not found.')
        if evidence['status'] != 'active':
            fail(409, 'evidence_withdrawn', 'This evidence is already withdrawn.')
        db.execute("UPDATE claim_evidence SET status='withdrawn',version=version+1,withdrawn_reason=? WHERE id=?", (body.reason, evidence_id))
        invalidate_claim(db, claim_id, user['user_id'], body.reason, 'evidence_withdrawn')
        return dict(db.execute('SELECT * FROM claim_evidence WHERE id=?', (evidence_id,)).fetchone())


@router.post('/claims/{claim_id}/reviews')
def review_claim(project_id: str, claim_id: str, body: ReviewCreate, request: Request, user=Depends(current_user)):
    with request.app.state.database.transaction(write=True) as db:
        project(db, project_id, user, editable=True)
        row = claim(db, project_id, claim_id)
        if row['version'] != body.expected_version:
            fail(409, 'version_conflict', 'The claim changed. Reload it before reviewing.')
        if body.decision == 'verified':
            blockers = verification_blockers(db, claim_id)
            if blockers:
                fail(409, 'verification_blocked', 'Cannot verify: ' + ', '.join(blockers) + '.')
        db.execute('UPDATE research_claims SET status=?,version=version+1,updated_at=? WHERE id=?', (body.decision, timestamp(), claim_id))
        updated = claim(db, project_id, claim_id)
        review_record(db, updated, user['user_id'], body.decision, body.reason, 'review_decision')
        # A new review version invalidates any existing generation snapshot, even when re-verifying.
        rows = db.execute("SELECT id,payload FROM jobs WHERE project_id=? AND kind='generation' AND status IN ('queued','running')", (project_id,)).fetchall()
        for job in rows:
            if claim_id in json.loads(job['payload']).get('claim_ids', []):
                db.execute("UPDATE jobs SET status='cancelled',error_code='research_changed',updated_at=? WHERE id=?", (timestamp(), job['id']))
        return dict(updated)


@router.post('/bundle')
def reviewed_bundle(project_id: str, body: ResearchSelection, request: Request, user=Depends(current_user)):
    with request.app.state.database.transaction() as db:
        project(db, project_id, user)
        return {'project_id':project_id, 'reviewed_claims':selected_snapshot(db, project_id, body.claim_ids), 'verification_method':'human_review', 'truth_guaranteed':False}


@router.get('/readiness')
def readiness(project_id: str, request: Request, user=Depends(current_user)):
    with request.app.state.database.transaction() as db:
        project(db, project_id, user)
        claims = db.execute('SELECT id,status FROM research_claims WHERE project_id=?', (project_id,)).fetchall()
        items = [{'claim_id':row['id'], 'status':row['status'], 'blockers':verification_blockers(db, row['id'])} for row in claims]
        ready = [i['claim_id'] for i in items if i['status'] == 'verified' and not i['blockers']]
        return {'items':items, 'verified_claim_ids':ready, 'has_reviewed_claims':bool(ready), 'all_claims_verified':bool(items) and len(ready)==len(items), 'verification_method':'human_review', 'truth_guaranteed':False}
