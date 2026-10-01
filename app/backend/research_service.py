import json
import uuid
from app.backend.database import timestamp
from app.backend.security import fail


def evidence_snapshot(db, claim_id):
    return [dict(row) for row in db.execute('''SELECT e.id AS evidence_id, e.source_id, e.quote, e.relation,
        e.status AS evidence_status, e.version AS evidence_version, s.url, s.publisher, s.published_at,
        s.captured_at, s.content_hash, s.status AS source_status, s.version AS source_version
        FROM claim_evidence e JOIN research_sources s ON s.id=e.source_id
        WHERE e.claim_id=? ORDER BY e.id''', (claim_id,))]


def review_record(db, claim, user_id, decision, reason, event):
    db.execute('INSERT INTO claim_reviews VALUES (?,?,?,?,?,?,?,?,?)', (str(uuid.uuid4()), claim['id'], user_id, decision, reason, event, claim['version'], json.dumps(evidence_snapshot(db, claim['id']), sort_keys=True), timestamp()))


def invalidate_claim(db, claim_id, user_id, reason, event):
    db.execute("UPDATE research_claims SET status='pending', version=version+1, updated_at=? WHERE id=?", (timestamp(), claim_id))
    claim = db.execute('SELECT * FROM research_claims WHERE id=?', (claim_id,)).fetchone()
    review_record(db, claim, user_id, 'pending', reason, event)
    # Invalidate queued/running generation records referencing this claim. M6 workers also recheck before accepting output.
    rows = db.execute("SELECT id,payload FROM jobs WHERE project_id=? AND kind='generation' AND status IN ('queued','running')", (claim['project_id'],)).fetchall()
    for row in rows:
        payload = json.loads(row['payload'])
        if claim_id in payload.get('claim_ids', []):
            db.execute("UPDATE jobs SET status='cancelled', error_code='research_changed', updated_at=? WHERE id=?", (timestamp(), row['id']))


def verification_blockers(db, claim_id):
    evidence = evidence_snapshot(db, claim_id)
    active = [e for e in evidence if e['evidence_status'] == 'active' and e['source_status'] == 'active']
    blockers = []
    if not any(e['relation'] == 'supports' and e['published_at'] for e in active):
        blockers.append('dated_supporting_evidence_required')
    if any(e['relation'] == 'contradicts' for e in active):
        blockers.append('contradictory_evidence_unresolved')
    return blockers


def selected_snapshot(db, project_id, claim_ids):
    result = []
    for claim_id in claim_ids:
        claim = db.execute('SELECT * FROM research_claims WHERE id=? AND project_id=?', (claim_id, project_id)).fetchone()
        if not claim:
            fail(404, 'claim_not_found', 'A selected claim does not belong to this project.')
        if claim['status'] != 'verified' or verification_blockers(db, claim_id):
            fail(409, 'research_not_verified', 'Every selected claim needs a current verified review.')
        result.append({'claim_id': claim_id, 'claim_version': claim['version'], 'statement':claim['statement'], 'event_at':claim['event_at'], 'evidence':evidence_snapshot(db, claim_id)})
    if len(json.dumps(result).encode()) > 1024 * 1024:
        fail(422, 'review_snapshot_too_large', 'Select a smaller reviewed claim set; the snapshot exceeds 1 MiB.')
    return result


def assert_job_review_current(db, job):
    if job['kind'] != 'generation':
        return
    payload = json.loads(job['payload'])
    claims = payload.get('claim_ids', [])
    if not claims or not payload.get('review_snapshot'):
        fail(409, 'research_not_verified', 'This generation job has no reviewed research snapshot.')
    current = selected_snapshot(db, job['project_id'], claims)
    if current != payload['review_snapshot']:
        fail(409, 'research_changed', 'The research changed after this job was queued.')
