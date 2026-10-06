"""Owned, durable generation queue and a single-process worker."""
import hashlib
import json
import threading
import uuid
from typing import Literal
from fastapi import APIRouter, Depends, Request, Response, HTTPException
from pydantic import Field
from app.backend.api import Input, project, job_dict
from app.backend.research import ReviewedGeneration
from app.backend.research_service import selected_snapshot, assert_job_review_current
from app.backend.security import current_user, fail
from app.backend.database import timestamp
from app.backend.generation_provider import OpenAIProvider, GeminiProvider, ProviderError, build_prompt, calculate_cost, valid_usage

router = APIRouter(prefix='/api/projects/{project_id}/generation')

class GenerationCreate(ReviewedGeneration):
    idempotency_key: str = Field(min_length=1, max_length=100, pattern=r'^[a-zA-Z0-9._-]+$')
    tone: Literal['neutral', 'analytical', 'conversational', 'energetic'] = 'neutral'

class RetryCreate(Input):
    idempotency_key: str = Field(min_length=1, max_length=100, pattern=r'^[a-zA-Z0-9._-]+$')


def generation_dict(db, row):
    result = job_dict(row)
    run = dict(db.execute('SELECT * FROM generation_runs WHERE job_id=?', (row['id'],)).fetchone())
    run['pricing'] = json.loads(run['pricing'])
    run['usage'] = json.loads(run['usage']) if run['usage'] else None
    run['stage'] = row['status'] if row['status'] in ('succeeded','failed','cancelled') else run['stage']
    run['cost_basis'] = 'configured rates; estimate, not invoice' if run['cost_usd'] is not None else 'unknown'
    result['generation'] = run
    return result


def enqueue(db, project_id, selection, key, config, retry_of=None):
    snapshot = selected_snapshot(db, project_id, selection['claim_ids'])
    payload = json.dumps(dict(selection, review_snapshot=snapshot), sort_keys=True, separators=(',',':'))
    try:
        build_prompt(json.loads(payload))
    except ProviderError:
        fail(422, 'generation_input_too_large', 'Select fewer reviewed claims; the provider input exceeds 128 KiB.')
    existing = db.execute('SELECT * FROM jobs WHERE project_id=? AND idempotency_key=?', (project_id,key)).fetchone()
    if existing:
        run = db.execute('SELECT retry_of FROM generation_runs WHERE job_id=?', (existing['id'],)).fetchone()
        if existing['kind']!='generation' or existing['payload']!=payload or not run or run['retry_of']!=retry_of:
            fail(409,'idempotency_conflict','This key belongs to a different request.')
        return generation_dict(db,existing), False
    # Bound outstanding work and daily requests, including manual retries.
    owner = db.execute('SELECT owner_id FROM projects WHERE id=?',(project_id,)).fetchone()[0]
    outstanding = db.execute("SELECT COUNT(*) FROM jobs j JOIN projects p ON p.id=j.project_id JOIN generation_runs r ON r.job_id=j.id WHERE p.owner_id=? AND j.status IN ('queued','running')",(owner,)).fetchone()[0]
    daily = db.execute("SELECT COUNT(*) FROM jobs j JOIN projects p ON p.id=j.project_id JOIN generation_runs r ON r.job_id=j.id WHERE p.owner_id=? AND j.created_at>=date('now')",(owner,)).fetchone()[0]
    if outstanding>=3 or daily>=30:
        fail(429,'generation_limit','Generation limit reached: three active jobs or thirty requests per UTC day.')
    now, identity = timestamp(), str(uuid.uuid4())
    db.execute("INSERT INTO jobs VALUES (?,?,?,'queued',0,?,?,NULL,NULL,?,?)", (identity,project_id,'generation',key,payload,now,now))
    db.execute('INSERT INTO generation_runs (job_id,provider,model,max_output_tokens,pricing,retry_of) VALUES (?,?,?,?,?,?)', (identity,config.provider,config.model,config.max_output_tokens,json.dumps(config.pricing),retry_of))
    return generation_dict(db,db.execute('SELECT * FROM jobs WHERE id=?',(identity,)).fetchone()), True


@router.post('',status_code=201)
def create_generation(project_id: str, body: GenerationCreate, request: Request, response: Response, user=Depends(current_user)):
    config = request.app.state.generation_config
    with request.app.state.database.transaction(write=True) as db:
        project(db,project_id,user,editable=True)
        if not config.ready:
            fail(503,'generation_not_configured','Live generation is disabled or the server provider configuration is missing.')
        selection=body.model_dump(exclude={'idempotency_key'})
        result,created=enqueue(db,project_id,selection,body.idempotency_key,config)
        response.status_code=201 if created else 200
    request.app.state.generation_worker.wake.set()
    return result


@router.get('')
def list_generation(project_id: str, request: Request, limit: int=20, offset: int=0,user=Depends(current_user)):
    if not 1<=limit<=100 or offset<0:
        fail(422,'invalid_pagination','Invalid pagination.')
    with request.app.state.database.transaction() as db:
        project(db,project_id,user)
        rows=db.execute('SELECT j.* FROM jobs j JOIN generation_runs r ON r.job_id=j.id WHERE j.project_id=? ORDER BY j.created_at DESC,j.id LIMIT ? OFFSET ?',(project_id,limit,offset))
        return {'items':[generation_dict(db,row) for row in rows]}


@router.get('/{job_id}')
def get_generation(project_id: str,job_id: str,request: Request,user=Depends(current_user)):
    with request.app.state.database.transaction() as db:
        project(db,project_id,user)
        row=db.execute('SELECT j.* FROM jobs j JOIN generation_runs r ON r.job_id=j.id WHERE j.id=? AND j.project_id=?',(job_id,project_id)).fetchone()
        if not row:
            fail(404,'generation_not_found','Generation job not found.')
        return generation_dict(db,row)


@router.post('/{job_id}/retry',status_code=201)
def retry_generation(project_id: str,job_id: str,body: RetryCreate,request: Request,response: Response,user=Depends(current_user)):
    config=request.app.state.generation_config
    with request.app.state.database.transaction(write=True) as db:
        project(db,project_id,user,editable=True)
        row=db.execute('SELECT j.* FROM jobs j JOIN generation_runs r ON r.job_id=j.id WHERE j.id=? AND j.project_id=?',(job_id,project_id)).fetchone()
        if not row:
            fail(404,'generation_not_found','Generation job not found.')
        if row['status'] not in ('failed','cancelled'):
            fail(409,'generation_not_retryable','Only failed or cancelled jobs can be retried.')
        if not config.ready:
            fail(503,'generation_not_configured','Live generation is not configured.')
        selection=json.loads(row['payload']);selection.pop('review_snapshot')
        result,created=enqueue(db,project_id,selection,body.idempotency_key,config,job_id)
        response.status_code=201 if created else 200
    request.app.state.generation_worker.wake.set()
    return result


class GenerationWorker:
    def __init__(self,database,config,provider=None):
        self.database,self.config=database,config
        self.provider=provider or (GeminiProvider(config) if config.provider == 'gemini' else OpenAIProvider(config))
        self.stop_event,self.wake=threading.Event(),threading.Event()
        self.thread=None

    def start(self):
        if self.config.ready:
            self.thread=threading.Thread(target=self.loop,name='generation-worker',daemon=True)
            self.thread.start()

    def stop(self):
        self.stop_event.set();self.wake.set()
        if self.thread:
            self.thread.join(timeout=1)

    def loop(self):
        while not self.stop_event.is_set():
            try:
                if self.run_once():
                    continue
            except Exception:
                # Never log raw provider errors or submitted content. A running record is recovered at restart.
                import logging
                logging.getLogger(__name__).error('Generation worker storage failure')
            self.wake.wait(1);self.wake.clear()

    def claim(self):
        with self.database.transaction(write=True) as db:
            row=db.execute("SELECT j.* FROM jobs j JOIN generation_runs r ON r.job_id=j.id WHERE j.status='queued' ORDER BY j.created_at,j.id LIMIT 1").fetchone()
            if not row:
                return None
            try:
                assert_job_review_current(db,row)
                if db.execute('SELECT archived FROM projects WHERE id=?',(row['project_id'],)).fetchone()[0]:
                    raise ProviderError('project_archived')
            except (HTTPException,ProviderError):
                db.execute("UPDATE jobs SET status='failed',error_code='research_or_project_changed',updated_at=? WHERE id=?",(timestamp(),row['id']))
                db.execute("UPDATE generation_runs SET completed_at=? WHERE job_id=?",(timestamp(),row['id']))
                return {'skip':True}
            now=timestamp()
            db.execute("UPDATE jobs SET status='running',progress=10,updated_at=? WHERE id=?",(now,row['id']))
            db.execute("UPDATE generation_runs SET stage='validating',started_at=? WHERE job_id=?",(now,row['id']))
            return dict(row)

    def run_once(self):
        row=self.claim()
        if not row:
            return False
        if row.get('skip'):
            return True
        identity=row['id'];result=None;error=None
        try:
            payload=json.loads(row['payload']);build_prompt(payload)
            with self.database.transaction(write=True) as db:
                current=db.execute('SELECT * FROM jobs WHERE id=?',(identity,)).fetchone()
                if current['status']!='running':
                    return True
                assert_job_review_current(db,current)
                run=dict(db.execute('SELECT * FROM generation_runs WHERE job_id=?',(identity,)).fetchone())
                if run['provider'] != self.config.provider or run['model'] != self.config.model:
                    raise ProviderError('provider_configuration_changed')
                db.execute("UPDATE generation_runs SET stage='requesting',billing_status='unknown' WHERE job_id=?",(identity,))
                db.execute('UPDATE jobs SET progress=30,updated_at=? WHERE id=?',(timestamp(),identity))
            result=self.provider.generate(payload,run['model'],run['max_output_tokens'])
            if not isinstance(result,dict) or not isinstance(result.get('content'),str) or not result['content'].strip() or len(result['content'].encode())>200000:
                raise ProviderError('provider_invalid_response')
            reported=result.get('usage')
            if not isinstance(reported,dict) or valid_usage({'input_tokens':reported.get('input_tokens'),'output_tokens':reported.get('output_tokens'),'input_tokens_details':{'cached_tokens':reported.get('cached_tokens',0)}}) is None:
                raise ProviderError('provider_usage_missing')
            if result.get('response_id') is not None and not isinstance(result['response_id'],str):
                raise ProviderError('provider_invalid_response')
        except ProviderError as exc:
            error=exc
        except HTTPException:
            error=ProviderError('research_changed')
        except Exception:
            error=ProviderError('provider_invalid_response')
        if error:
            result=None
        usage=result['usage'] if result else error.usage
        response_id=result.get('response_id') if result else error.response_id
        asset_path=None
        try:
            with self.database.transaction(write=True) as db:
                current=db.execute('SELECT * FROM jobs WHERE id=?',(identity,)).fetchone()
                run=dict(db.execute('SELECT * FROM generation_runs WHERE job_id=?',(identity,)).fetchone())
                pricing=json.loads(run['pricing'])
                db.execute('UPDATE generation_runs SET usage=?,cost_usd=?,provider_response_id=?,billing_status=?,completed_at=? WHERE job_id=?',(json.dumps(usage) if usage else None,calculate_cost(usage,pricing),response_id,'reported' if usage else run['billing_status'],timestamp(),identity))
                # Cancellation wins, even when provider usage arrived afterwards.
                if current['status']!='running':
                    return True
                try:
                    assert_job_review_current(db,current)
                    if db.execute('SELECT archived FROM projects WHERE id=?',(row['project_id'],)).fetchone()[0]:
                        raise ProviderError('project_archived')
                except (HTTPException,ProviderError):
                    error=ProviderError('research_or_project_changed')
                if self.stop_event.is_set():
                    error=ProviderError('worker_interrupted')
                if error:
                    db.execute("UPDATE jobs SET status='failed',error_code=?,updated_at=? WHERE id=?",(error.code,timestamp(),identity))
                    return True
                raw=result['content'].encode()
                asset_id=str(uuid.uuid4());asset_path=self.database.data_dir/'assets'/asset_id
                with asset_path.open('xb') as handle:
                    handle.write(raw)
                asset_path.chmod(0o600)
                now=timestamp()
                db.execute('INSERT INTO assets VALUES (?,?,?,?,?,?,?)',(asset_id,row['project_id'],'ai-draft.txt','text/plain',len(raw),hashlib.sha256(raw).hexdigest(),now))
                db.execute("UPDATE generation_runs SET stage='complete' WHERE job_id=?",(identity,))
                db.execute("UPDATE jobs SET status='succeeded',progress=100,result_asset_id=?,updated_at=? WHERE id=?",(asset_id,now,identity))
        except Exception:
            if asset_path:
                try:
                    asset_path.unlink(missing_ok=True)
                except OSError:
                    pass
            # Retain reported billing even if saving the result failed. Never resubmit automatically.
            with self.database.transaction(write=True) as db:
                run=db.execute('SELECT pricing FROM generation_runs WHERE job_id=?',(identity,)).fetchone()
                db.execute('UPDATE generation_runs SET usage=?,cost_usd=?,provider_response_id=?,billing_status=?,completed_at=? WHERE job_id=?',(json.dumps(usage) if usage else None,calculate_cost(usage,json.loads(run['pricing'])),response_id,'reported' if usage else 'unknown',timestamp(),identity))
                db.execute("UPDATE jobs SET status='failed',error_code='generation_storage_failed',updated_at=? WHERE id=? AND status='running'",(timestamp(),identity))
        return True
