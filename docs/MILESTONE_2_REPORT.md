# Milestone 2 — workspace persistence and security foundation

Status: backend foundation built, fixed and verified through automated tests and real HTTP requests. M1 browser verification also passed; its report and desktop/mobile evidence have been updated. Stop for approval before M3.

## What changed and why

The studio now has a durable data layer for later frontend screens. SQLite migrations create accounts, sessions, owned projects, drafts, immutable revisions, uploaded assets and job records. It keeps first-party FastAPI and the supplied frontend intact. No cloud account or API credential is required to verify this foundation.

Accounts are provisioned locally with a non-echoing password prompt. Passwords use salted PBKDF2-SHA256 with 600,000 iterations. Sessions use random tokens; only session/CSRF hashes are stored in the database. Session cookies are HttpOnly and SameSite=Strict, with Secure enabled in production. Writes check CSRF tokens and request origins; login also requires a custom request header and applies persistent rate limits. Sessions rotate on login and revoke on logout or expiry. Validation errors omit submitted passwords and content.

Ownership is enforced on every project, draft, revision, asset and job API. Another account receives 404 for inaccessible records. Renames, archive/restore and draft saves use expected-version checks. Concurrent draft saves cannot overwrite newer work. Restoring an older revision creates a new revision and preserves the old history and exact script whitespace.

Uploads have bounded size, plain filenames, random storage IDs, SHA-256 checksums and private file permissions. Downloads are attachments with nosniff; uploaded media labels are untrusted metadata, not decoder validation. Failed writes roll back the database and remove partially created files; missing files and storage/database failures return explicit errors.

Jobs have stable IDs, idempotency keys, queued/running/succeeded/failed/cancelled states and monotonic progress. Cancellation prevents later progress updates; successful results must reference an asset in the same project. Restart recovery marks interrupted running jobs failed while preserving queued jobs. These are job contracts and records; execution workers, rendering and AI providers remain unfinished.

## Build, test, fix, test again

Initial M2 tests exposed two issues: inherited string trimming changed saved script whitespace, and an oversized body produced a generic 400. Fixed exact-text draft persistence and request-size handling to return 413, then re-ran the suite. Also verified storage-failure responses and worker progress/cancellation behavior.

Passed: 22 Python test methods (19 M2 and 3 M1), 5 frontend JavaScript tests, dependency consistency, syntax and whitespace checks. Checks cover ownership across all resources, login/CSRF/origin/expiry/revocation, password/token handling, production cookie flags, invalid payloads, size bounds, archive/restore, immutable revisions, simultaneous saves, transaction rollback, uploads/downloads, idempotency, job transitions and restart persistence.

Real Uvicorn HTTP walkthrough passed: page/static/health serving → sign in → create project → save an exact draft → upload/download a file → enqueue a job → stop/restart the server → reload session/draft/file/job → cancel job → logout → reject unauthenticated access. Tests use temporary databases, files and synthetic credentials. No real account password or session token appears in the report.

M1 browser checks passed against the actual page and API, with a local-only harness for injected errors and a 390px iframe viewport for responsive QA. All four formats, blank validation, loading/disabled state, server/JSON failures, actual 15-second timeout, successful retry, safe text rendering and mobile submission were observed. Browser-extension metadata errors were separate from application execution.

## Scope boundaries

M2 is an API and data foundation. The supplied designs remain unchanged; sign-in, project controls and automatic draft saving have not yet been connected to their frontend screens. Verification of M2 saved-work flows was through live HTTP, not an invented replacement frontend. The existing public M1 generation endpoint continues to return an explicitly labelled stub.

SQLite is a local foundation. Production database/hosting, shared-workspace roles, public registration/password recovery, provider connections, real generation, media decoding/transcoding, cloud storage, workers, and later studio controls remain in the roadmap. Current job recovery assumes one application process. The committed legacy venv is untouched; the new .venv and private data are ignored.

No commit, push, deployment, publication or external message was made. M3 has not started.

## How to verify and study

Use README.md for setup and account provisioning. Run `python -m unittest discover -s tests -v`, `node --test tests/test_frontend.cjs`, and `python -m tests.live_smoke`.

Read the code in this order: app/migrations/001_foundation.sql (what is saved), app/backend/database.py (atomic storage), app/backend/security.py (who can access it), app/backend/api.py (project/revision/file contracts), and app/backend/jobs.py (work states). A project is the container, a draft is its latest saved text, a revision is a permanent earlier snapshot, an asset is a stored file, and a job is a tracked future task.

Design references consulted: Python sqlite3 and hashlib documentation; OWASP Session Management and CSRF Prevention Cheat Sheets. These informed the implementation; tests provide project-specific evidence.
