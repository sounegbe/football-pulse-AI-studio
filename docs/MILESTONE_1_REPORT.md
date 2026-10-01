# Milestone 1 — baseline repair

Status: PASS — built, automated checks passed, and browser application verification passed on 2026-09-30. M2 was separately authorized; see MILESTONE_2_REPORT.md for its result.

## Changes

- Fixed JavaScript reading response data before initialization.
- Added stable format identifiers and pressed-state accessibility attributes without changing the layout.
- Added loading/disabled states, duplicate-submit prevention, 15-second cancellation, HTTP/network/invalid-response errors and input preservation for retry.
- Rendered output with textContent, preventing response HTML from executing.
- Added backend whitespace trimming, a 1–2,000-character limit, four allowed content types and rejection of unexpected fields.
- Explicitly identified the fixed response as stub mode. No AI provider is connected.
- Resolved application files relative to main.py; added /health.
- Added setup instructions, isolated .venv workflow, pinned development test dependency and regression tests.

## Verification

Passed: 3 Python unittest methods covering page/static/health serving, all formats and boundary length, invalid/malformed requests and method/not-found behavior. Passed: 5 Node tests covering validation, format selection, trimmed input, safe rendering, pending/duplicate handling, failure recovery and timeout cancellation. Dependency consistency, JavaScript syntax and git whitespace checks passed.

A real Uvicorn subprocess launched from the parent folder was tested over HTTP: GET page/CSS/JS/health returned 200; all four generation formats returned 200 with mode=stub; invalid input returned 422. The smoke-test subprocess was stopped after verification. This does not establish a remotely accessible preview.

The initial loopback browser attempt was blocked. A supervised development adapter subsequently served the actual FastAPI application for browser QA; no deployment was made.

Browser PASS: meaningful page and stylesheet render; blank input validation and focus; all four format selections submit to the real API and display the matching type and explicit stub notice; slow requests disable all format buttons and the generation button; server errors and invalid JSON are handled; the actual 15-second timeout restores controls and preserves input; successful retry restores output; a response containing HTML displays as text with zero image elements. At a 390px iframe viewport the actual page uses a single grid column, submits successfully and has no horizontal overflow. Desktop and mobile screenshots are saved under docs/evidence.

Failure scenarios were supplied by tests/preview_app.py, a separate local-only harness around main:app. Normal submissions used the actual generation endpoint. The test harness is not the production entry point; scenario files are ignored and removed after QA. Console inspection found browser-extension metadata errors and the intentionally injected server-error request, but no application JavaScript exception during the successful journey.

No commit, push or deployment was performed. Existing Stitch design files were not modified. The audit describes the pre-M1 baseline; this report records subsequent repairs.
