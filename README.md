# Football Pulse AI Studio

M1 provides a working creator form and a **test response API**. AI generation is not connected. The supplied Stitch designs remain the visual source of truth for later integration; this milestone preserves the existing creator page.

## Run

Use Python 3.12 (tested) and run from the repository folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 on the machine running the server. No API keys are needed for this stub. Use a fresh `.venv`, rather than the old committed `venv` folder. App file paths are resolved relative to `main.py`, so launching with Uvicorn's `--app-dir` from another folder also works.

## Verify

Node 24 was used for JavaScript tests.

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
node --test tests/test_frontend.cjs
```

`GET /health` reports status and stub mode. `POST /api/generate` takes trimmed `news` (1–2,000 characters) and `content_type` (`news_article`, `youtube_script`, `short_video`, or `social_post`). Invalid payloads return 422. Success returns `content`, `content_type`, and `mode: "stub"`.

Manual browser checklist: blank news; each of four formats; visible test-response notice; repeated click while pending; failed request and retry; preserved news after error; mobile single-column layout. API and DOM-stub tests do not replace browser verification.

## M2: saved-work foundation

Start the server as above. A local SQLite database and private asset directory are created under `data/` and excluded from Git. Keep the database and asset files together when backing up or restoring; stop the application before copying the directory.

Create an account locally (the password is requested privately in the terminal):

```bash
python manage.py create-user 2solo
```

There is no public registration or sign-in screen in this milestone. The supplied UI is preserved; these APIs are the foundation for later screen integration. Open `/docs` or `/openapi.json` for the API contracts.

- `POST /api/auth/login`: username/password JSON and `X-Studio-Request: 1`. Returns a CSRF token and sets an HttpOnly session cookie.
- `GET /api/auth/session`: returns the current account and CSRF token for page reloads.
- Saved-work writes require the cookie and `X-CSRF-Token`; logout revokes the session.
- `/api/projects`: create/list/get and version-checked rename/archive/restore.
- `/api/projects/{id}/draft`: save/load with `expected_version` (0 for first save).
- `/api/projects/{id}/revisions`: immutable history; restoring adds a new revision.
- `/api/projects/{id}/assets`: upload raw bytes with `Content-Type` and `X-Filename`, list metadata, or download by asset ID. Limit: 10 MiB. Downloads are attachments; uploaded format labels do not certify that media is valid.
- `/api/projects/{id}/jobs`: create/list/get/cancel durable job records. Reusing an idempotency key with the same request returns the original job. **This generic endpoint creates record-only jobs; M6 execution is enrolled separately through `/generation`. Rendering workers remain unconnected.**

Configuration uses `STUDIO_DATA_DIR`, `STUDIO_ENV` (`production` enables Secure cookies), and comma-separated exact `STUDIO_ALLOWED_ORIGINS`. Development defaults allow only the two localhost origins on port 8000. Production requires explicit HTTPS origins. No credentials are stored in source files. Session lifetime is eight hours; login limits are 10 attempts per account and 50 per client address in 15 minutes. Set the public origin to match your deployed application when deployment is implemented.

This foundation supports one application process. At startup, previously running jobs become failed with `worker_interrupted`; queued jobs remain queued. Multiple workers and automatic retries belong to the worker milestone. Database migrations apply transactionally and refuse unknown newer schema versions.

Run the live HTTP/restart walkthrough after installing development dependencies:

```bash
python -m tests.live_smoke
```

For supervised local browser QA, `npm run dev` is a small adapter that launches the same FastAPI app using Python 3.12 dependencies from `.venv`. It accepts `--host` and `--port`; it introduces no JavaScript application framework. The production startup target remains `main:app`. `tests.preview_app` is a separate QA-only fault-injection/mobile harness enabled only by a local `.qa-preview` marker, which is excluded from Git. Do not use that harness for deployment.

## M3: research and explicit claim review

Research APIs live under `/api/projects/{id}/research` and use the same account ownership, session and CSRF protections as saved work. New claims are pending. “Verified” records an explicit human review; it does not guarantee factual truth.

- `/sources`: manually ingest source text with URL, title, publisher and optional dated publication; list/get immutable text snapshots. Identical submissions are deduplicated.
- `/sources/import`: fetch a public HTTPS article from the configured publisher allowlist. Redirects, private addresses, unsupported formats and oversized responses are rejected. Live publisher retrieval has not been verified in this environment; use manual ingestion when retrieval is unavailable.
- `/sources/{source_id}/metadata` and `/status`: version-checked correction or withdrawal with a reason and retained audit history.
- `/claims`: create/list/get claims, review history and verification blockers.
- `/claims/{claim_id}/evidence`: attach an exact quotation from a source in the same project, with a supporting, contradictory or contextual relation.
- `/claims/{claim_id}/evidence/{evidence_id}/withdraw`: retain the evidence record while withdrawing its use, with a reason.
- `/claims/{claim_id}/reviews`: record pending, verified, rejected or disputed decisions using the current version and a reason. Verification requires active dated supporting evidence and no active contradictory evidence.
- `/bundle`: select verified claim IDs and receive a versioned evidence snapshot. `/readiness` explains outstanding blockers.

Changing evidence, correcting source metadata, withdrawing a source or importing changed text at the same URL resets affected reviews and cancels queued/running generation jobs. A generation job accepts only `claim_ids` and `content_type`; the server attaches the current reviewed evidence snapshot and workers recheck it before running or succeeding. The reviewed generation worker is introduced in M6 below; publishing remains a future milestone. The M1 public stub remains a clearly labelled test response.

Browser research checks use `tests.preview_app` and `/qa/research` with an isolated synthetic account/database. This diagnostic page is not a production screen. See `docs/MILESTONE_3_REPORT.md` for results and remaining verification limits.

## M4: supplied creator workspace controls

The home page now uses the supplied `creator_workspace_milestone_4` layout. `/workspace/mobile-original` retains the earlier supplied mobile variant; `/legacy` retains the M1 creator page. The supplied desktop reference is integrated in M5 below.

Presets are explicitly unverified examples. Metric chips add a source-note prompt rather than inventing measurements. The character counter, four output formats, three analytical depths and audio-cue setting feed the validated test-response API. `depth` is an integer 1–3 and `audio_cues` is a boolean; old M1 callers can omit both. Reviewed generation jobs retain these options while preserving M3's claim gate.

Generate and regenerate use real requests, a 15-second timeout and pending guards. Regenerate repeats the last successful input/options. A failed request preserves the current input and previous result. Input reset and result clear are separate. Copy writes the exact response through the Clipboard API; denied/unavailable access gives a manual-copy message. Clipboard access requires a supported secure context; successful browser copying was not verified in the HTTP preview. The original mobile variant's teleprompter shows the actual result.

Stage 5 rejects empty/test results. SEO, media assets and future navigation screens remain visibly unavailable rather than reporting simulated success. No AI provider or worker is connected by M4.

Workspace CSS is compiled locally from the supplied Tailwind configuration and checked in, so the runtime Tailwind CDN is unnecessary. To update styles: `npm ci` then `npm run build:css`. Fonts, icons and logo URLs remain from the supplied designs. `npm run test:frontend` checks M1 and M4 controls. Browser QA for both 390px variants is `/qa/workspace-mobile` in the isolated QA app. See `docs/MILESTONE_4_REPORT.md`.

## M5: desktop workspace and saved project continuity

`/desktop` preserves the supplied M5 layout and connects owned projects, versioned drafts, chapters, research readiness and owned MP4 previews. Home chooses it at initial widths >=1024px; M4 mobile routes remain. Drafts/revisions persist depth, cues and `unknown`/`manual`/`stub` mode. Unsaved context stays in memory; save explicitly for restart continuity. Conflicting saves preserve the editor; replacing dirty work requires a choice.

`GET /api/projects/{id}/draft/export.pdf?expected_version=N` exports the owned saved snapshot with embedded DejaVuSans and literal text. Unsupported font characters return 422. PDF bytes/pagination are verified; browser download collection remains unverified. Clipboard/fullscreen can be denied in the HTTP preview, with visible fallbacks. Source preview decodes actual MP4 bytes; video rendering and AI generation remain future work.

See `docs/MILESTONE_5_REPORT.md` for M5 browser evidence and limits. Current M6 status is below.

## M6: reviewed generation jobs

The desktop result column now includes the supplied M6 generation panel. Refresh reviewed claims, select claims, generate, recheck, cancel or retry as a new attempt. Output is saved as an owned text asset; using it in the editor requires an explicit replacement choice and saving remains explicit. AI drafts always require human review.

`POST /api/projects/{id}/generation` accepts reviewed `claim_ids`, `content_type`, `depth`, `audio_cues` and an `idempotency_key`. List/get endpoints expose stages, usage and configured-rate cost estimates; `/generation/{job_id}/retry` creates a linked attempt. No automatic paid retry occurs. The old generic `/jobs` endpoint remains record-only; only enrolled `generation_runs` are executed.

Live execution defaults to disabled. Configure `STUDIO_GENERATION_ENABLED=1`, a server-only `OPENAI_API_KEY`, and an explicit `STUDIO_OPENAI_MODEL`. Optional output/deadline and all-three pricing variables are detailed in `docs/MILESTONE_6_REPORT.md`. Run one API process; the lifespan starts/stops its single worker. Cancellation discards late content, but does not guarantee a remote request or charge stops. Unknown usage/cost stays unknown; running jobs interrupted by restart fail without re-submission.

The local QA provider is isolated in `tests/generation_fixture.py`, never used by `main:app`. It is visibly synthetic, uses no live key, and exercises real APIs at `/qa/generation`. 90 automated tests pass; live OpenAI verification still requires configuration. M7 has not started.
