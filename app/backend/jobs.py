"""Generic job transition contract. M6 executes only the explicit generation_runs queue."""
from app.backend.database import timestamp
from app.backend.research_service import assert_job_review_current

TRANSITIONS = {'queued': {'running', 'cancelled'}, 'running': {'succeeded', 'failed', 'cancelled'}}


def transition_job(database, job_id, target, progress=0, result_asset_id=None, error_code=None):
    if type(progress) is not int or not 0 <= progress <= 100:
        raise ValueError('Progress must be an integer between 0 and 100')
    with database.transaction(write=True) as db:
        job = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
        if not job:
            raise ValueError('Job not found')
        if target in ('running', 'succeeded'):
            assert_job_review_current(db, job)
        if target not in TRANSITIONS.get(job['status'], set()):
            raise ValueError('Invalid job state transition')
        if result_asset_id:
            asset = db.execute('SELECT project_id FROM assets WHERE id=?', (result_asset_id,)).fetchone()
            if not asset or asset['project_id'] != job['project_id']:
                raise ValueError('Result asset must belong to the job project')
        if target == 'succeeded' and not result_asset_id:
            raise ValueError('A successful job must have a result asset')
        if target == 'failed' and not error_code:
            raise ValueError('A failed job must have an error code')
        if target != 'succeeded' and result_asset_id:
            raise ValueError('Only a successful job can reference a result')
        if target != 'failed' and error_code:
            raise ValueError('Only a failed job can have an error code')
        if target == 'succeeded':
            progress = 100
        if progress < job['progress']:
            raise ValueError('Progress cannot decrease')
        db.execute('UPDATE jobs SET status=?, progress=?, result_asset_id=?, error_code=?, updated_at=? WHERE id=?', (target, progress, result_asset_id, error_code, timestamp(), job_id))
        return dict(db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone())


def update_progress(database, job_id, progress):
    """Monotonic progress update for an active worker; cancellation wins races."""
    if type(progress) is not int or not 0 <= progress <= 99:
        raise ValueError('Running progress must be an integer between 0 and 99')
    with database.transaction(write=True) as db:
        job = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
        if not job or job['status'] != 'running':
            raise ValueError('Only a running job can report progress')
        if progress < job['progress']:
            raise ValueError('Progress cannot decrease')
        db.execute('UPDATE jobs SET progress=?, updated_at=? WHERE id=?', (progress, timestamp(), job_id))
        return dict(db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone())
