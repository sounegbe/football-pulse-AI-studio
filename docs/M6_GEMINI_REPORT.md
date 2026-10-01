# M6 optional Gemini provider

October 1, 2026. Local implementation and synthetic verification completed.
Live Google verification remains pending; M7 and Render deployment are paused.

Preserved the supplied frontend layout and added provider-aware status text.
OpenAI remains the default; Gemini is selected explicitly by server config or
`scripts/run_local_live.py --provider gemini`. Keys are hidden in prompts,
excluded from config representation, and passed only in server request headers.
No new runtime dependency or database migration is required.

Both adapters share bounded HTTP transport (fixed host, no redirects/proxies,
1 MiB response bound, total timeout, no automatic retries) and the existing
review gates, queue, cancellation, owned assets, retry and explicit save flow.
Gemini parsing requires a completed text response, rejects blocked/truncated
outputs, preserves available usage on failures, and excludes thought text.
Thinking tokens count in output usage. Costs remain unknown without model/tier
rates; free quota is never assumed from the key itself.

Provider and model are stored on each generation attempt. A queued attempt
whose provider/model no longer matches server config fails without an external
request. Explicit retry uses current config. No cross-provider failover occurs.

Validation: the full Python suite passed with the first five Gemini tests
(73 tests); the sixth queue/adapter integration test was then added and all six
Gemini tests passed. Total Python coverage is now 74 tests. All 22 existing
frontend tests passed. Launcher selection and secret isolation passed using
synthetic credentials and a mocked process launch. Whitespace checks passed.

Browser verification used the actual app, synthetic account and reviewed
research APIs, Gemini request construction/response parsing with QA-only
transport, then queued generation, reported usage, explicit editor replacement,
save version 1, reload and persisted history. The result is visibly labeled
synthetic, with literal markup preserved. The browser screenshot could not be attached because file synchronization was
unavailable; the visible application state was verified directly.

No live provider request was sent. A free-tier-capable Gemini key and model
must be configured locally before the real M6 gate can pass. Follow
`docs/LOCAL_GEMINI_SETUP.md`. The existing Render proposal remains unapproved.
