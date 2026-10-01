# Milestone 6 — queued generation and provider execution

Date: 2026-09-30. Implementation built and locally verified. **Live OpenAI verification is pending:** no server API key or model is configured. No live request, commit, push or deployment was performed. M7 has not started.

## What changed

The supplied M6 generation card is integrated into the existing M5 result column, retaining its gradient, border, neon progress styling, four-stage arrangement and surrounding workbench. Fake Gemini/Opta progress, token streaming, statistics and duration estimates were replaced with owned job state. Reviewed-claim selection and operational controls fit the same panel. The public M1/M4 test-response action stays explicitly separate.

A SQLite queue and single-process worker now execute only jobs enrolled through the new generation API. Old record-only `/jobs` entries never become unexpected paid requests. Migration 004 adds per-attempt model, token limit, pricing snapshot, lifecycle stage, provider response ID, usage, estimated cost, timestamps and retry parent. Existing drafts/revisions remain compatible.

## Control and API map

| Control | Behavior |
| --- | --- |
| Refresh claims/jobs | Reads real review readiness, all claim pages, and recent owned attempts |
| Claim selection | Only currently reviewed claims; 1–100 distinct IDs; server checks again |
| Generate reviewed draft | Creates one durable idempotent attempt with format/depth/cues; free-form facts are rejected |
| Progress/elapsed | Actual queue/validation/request/completion stages, with elapsed time from saved timestamps; no simulated token percentage or completion estimate |
| Cancel | Existing owned cancellation API; late provider output cannot become a result |
| Recheck | Reads the existing attempt; never submits another billable request |
| Retry | New linked attempt and fresh reviewed snapshot; only failed/cancelled attempts; no automatic retry |
| History | Owned attempts, paginated with Load older attempts |
| Preview | Actual owned result asset rendered as literal text |
| Use result in editor | Explicit replacement dialog; Keep editing preserves current work; save remains explicit |
| Cost | Provider token usage plus rates captured when queued; missing usage/rates remain unknown |

New endpoints are `POST/GET /api/projects/{id}/generation`, `GET /generation/{job_id}` and `POST /generation/{job_id}/retry`. They retain account ownership, CSRF and origin checks. Creation/retry requires an editable project and configured provider. Limits are three active jobs and thirty attempts per account per UTC day; retries count as attempts. Server-side generation input is bounded to 128 KiB, response bytes to 1 MiB and accepted draft bytes to 200,000.

## Provider and evidence handling

The OpenAI Responses adapter uses a fixed HTTPS endpoint, disables redirects/environment proxies, requests `store: false`, bounds output tokens and enforces a total request deadline. It makes no automatic provider retries. Authentication, access, rate-limit, timeout, network, incomplete, refused and malformed responses become safe error codes; raw provider bodies, keys and submitted facts are not logged or echoed.

The prompt contains the selected reviewed claims and active supporting quotations with provenance. Quotations are explicitly treated as untrusted data. The worker checks reviews/project state before requesting and again inside the transaction accepting the result. Source corrections/withdrawal cancel affected active jobs through M3's existing invalidation. No AI output is automatically verified or approved for publication. The result asset preserves the full output; importing it into the editor uses safe `unknown` mode.

A successful attempt writes an owned text asset and records the result atomically with job completion. Cancelled attempts retain any subsequently reported usage/cost, but discard content. Cancellation does not promise to stop an already sent remote request or billing; a provider timeout also leaves billing unknown when usage is unavailable. Queued jobs survive restart; interrupted running jobs fail without automatic re-submission. Unknown previous charges remain unknown. This architecture supports one application process; do not launch multiple API workers against this data directory.

## Server configuration required for live verification

| Environment variable | Meaning |
| --- | --- |
| `STUDIO_GENERATION_ENABLED=1` | Explicitly enables the generation worker |
| `OPENAI_API_KEY` | Server-only API credential; never put it in browser code or chat |
| `STUDIO_OPENAI_MODEL` | Explicit model identifier available to the account; prefer a pinned version |
| `STUDIO_MAX_OUTPUT_TOKENS` | Default 6000; allowed 256–16000 |
| `STUDIO_PROVIDER_TIMEOUT` | Total request deadline; default 90 seconds; allowed 5–120 |
| `STUDIO_INPUT_USD_PER_MILLION` | Configured uncached-input rate |
| `STUDIO_CACHED_INPUT_USD_PER_MILLION` | Configured cached-input rate |
| `STUDIO_OUTPUT_USD_PER_MILLION` | Configured output rate |

Configure all three rates together or omit all three. Estimates use reported token counts and the saved configured rates; they are not invoices. No current price or account model availability is assumed. Daily/active limits and token limits are request bounds, not an exact currency spending cap. Use the provider account's spending controls as needed.

Official implementation reference: [OpenAI text generation](https://developers.openai.com/api/docs/guides/text), inspected during M6. Model selection, account access, billing and live network connectivity are still to be confirmed in the configured server environment.

## Tests and browser verification

**68 Python tests + 22 frontend tests = 90 passing tests.** Existing milestone regressions pass. The live HTTP/restart smoke walkthrough also passed.

New coverage includes evidence gates, ownership/CSRF, unconfigured provider, idempotency replay, original request options, safe owned output, known/unknown cost, manual retry, queued/in-flight cancellation, source withdrawal during execution, archived projects, malformed provider contracts, queue bounds, legacy-record isolation, interrupted worker recovery, usage retained after storage failure, incomplete/refused output, secret-safe errors, fixed-host transport, total deadline and configuration validation. Frontend tests cover ambiguous submission replay, active duplicate blocking, explicit editor replacement, private-context cleanup, selection validation and polling failure without submission.

Browser checks used **an isolated synthetic provider**, labelled `QA SIMULATION — QA_ONLY_SYNTHETIC_PROVIDER`. They exercised actual research, generation, worker, asset and draft APIs. No credentials were entered or live OpenAI output claimed.

- Empty claim selection rejected without submission.
- Actual queued/running attempt was cancelled; no result accepted.
- Separate retry hit a controlled rate-limit failure, then another retry succeeded.
- Synthetic usage and configured-rate estimate displayed; literal markup stayed text.
- Keep editing left output intact; explicit replacement loaded actual result; versioned save succeeded.
- Server restart preserved draft and separate succeeded/failed/cancelled attempt history.
- At 390px, the panel fits between x=24 and x=366; internal width does not overflow, and controls/results remain usable.

Evidence: [desktop](evidence/m6-desktop-final.jpg) and [390px panel](evidence/m6-mobile-final.jpg). All content and displayed usage/prices in these images are synthetic test fixtures.

## Remaining gate and next action

M6's local implementation and simulated-provider verification are complete. **M6 is not fully live-verified until server-side OpenAI configuration is provided and one real reviewed generation passes API → worker → usage → saved result → browser verification.** Long-form quality and 30-minute episode length are not proven by short synthetic fixtures. M5 clipboard/fullscreen/browser-download limits and M3 live publisher retrieval limits remain.

Stay on M6 for that live check. Do not start M7 without approval.
