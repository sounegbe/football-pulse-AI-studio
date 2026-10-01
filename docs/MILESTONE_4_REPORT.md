# Milestone 4 — creator workspace controls

Date: 2026-09-30. Implemented and locally tested. AI generation, successful browser clipboard access and downstream SEO handoff are not claimed complete. M5 has not started. No commit, push or deployment was performed.

## What changed and why

Home now uses the supplied `creator_workspace_milestone_4` markup, theme, navigation and control arrangement. The earlier `creator_workspace` variant is retained at `/workspace/mobile-original`; the M1 page remains at `/legacy`. M5's dedicated desktop reference is untouched. Fonts/icons/logo URLs remain supplied assets. Tailwind's supplied theme is compiled into a checked-in stylesheet; runtime CDN compilation is removed.

The original timed generation animation and fake copied/dispatched toasts were replaced with real request handling and actual clipboard attempts. Presets are explicitly labelled unverified; metrics chips insert source-note prompts. Fake generated football claims, duration/word statistics and connected-data badges were removed from the result state. The empty, loading, success and error states reflect actual request outcomes.

## Controls and boundaries

| Supplied control | M4 behavior |
| --- | --- |
| Three context presets | Insert labelled unverified examples and update counter |
| Input/counter/reset | 2,000-character validation; reset preserves last result |
| xG/passing/pressing chips | Append source-note prompts; reject excess length without altering input |
| Four formats | Map article/youtube/short/social to validated API enums; social added to older variant |
| Analytical depth | Three levels, accessible slider and current label |
| Audio cues | Accessible switch; boolean validated and retained in request/job |
| Generate | Actual POST, timeout, safe text rendering, disabled mutation controls while pending |
| Regenerate | Repeat last successful request/options, even after input edits |
| Copy | Write exact displayed response; report denied/unavailable access honestly |
| Result clear | Clear result/regeneration snapshot; preserve input/options |
| Stage 5 | Guard empty/test output; no simulated handoff to unbuilt SEO screen |
| Teleprompter in original variant | Real modal displaying the response; close restores workspace |
| B-roll preview | Disabled with explanation until a media asset/preview exists |
| Future navigation/settings | Explain unavailable screen; no fake successful operation |

Public `/api/generate` remains a clearly labelled M1 test-response service, not production AI generation. It now strictly validates depth (integer 1–3) and audio cues (boolean), echoes accepted settings and keeps old callers compatible. Authenticated reviewed-generation job payloads also retain these options; pending/unverified claims still cannot queue generation.

## Test, fix, test again, browser verification

Automated verification: 49 Python tests and 13 Node tests pass. M4 adds three Python contracts and eight frontend tests to the M1–M3 suites. Python checks cover strict option types/bounds, both page routes, absence of fake generated output and reviewed-only job options. Frontend checks cover all formats, bounds, pending duplicate/mutation guards, presets/notes/reset, regeneration snapshot, preservation on failure, exact clipboard text/rejection, malformed and mismatched responses, network errors, timeout and stage/navigation guards.

Real HTTP/restart walkthrough passes, including existing saved-work/review persistence and source invalidation. CSS compilation and JavaScript syntax checks pass.

Browser verification called actual FastAPI APIs using synthetic/example text. Blank news focused input; preset/note insertion and counter worked; four formats succeeded; depth 2 and cues off were echoed correctly. Delayed request disabled all mutation controls and restored them. HTTP 500 preserved input and last successful response; retry succeeded. Regenerate succeeded and Stage 5 refused test output.

Both supplied mobile variants were tested in 390px iframes. Each document's client and scroll width was 390px. Both generated real test responses. The original variant's teleprompter opened and displayed the actual response, then closed.

Corrections during verification: options are checked against server response before accepting output; regeneration uses the successful snapshot rather than silently adopting later edits; source-note insertions preserve input if too long. The test runner was adjusted to avoid counting inherited duplicate M1 tests. Static pipeline check icons were changed to pending icons because this workspace has no reviewed project selected.

Evidence: [workspace](evidence/m4-workspace-desktop.jpg), [both mobile variants](evidence/m4-workspace-mobile.jpg). The wide screenshot uses the M4 mobile layout at a wider viewport; it is not completion of the dedicated M5 desktop workspace.

## Remaining limits

The HTTP preview denied clipboard access. The actual failure message was verified in browser; exact clipboard writes and rejection handling passed controlled frontend tests. Successful copying in a supported HTTPS/localhost browser still needs verification. The browser response is a stub; analytical depth/cues are accepted settings and do not create genuine AI output yet. Stage 5 is a guarded boundary; its successful processing awaits AI content and the later SEO milestone. B-roll/media and future screens remain tracked in the full milestone map.

M3 live external publisher retrieval remains unverified. This milestone does not change that limit. M1's earlier browser check remains recorded as passed.

## Understand before continuing

Input is what you are currently editing. Result is the last successful response. Regenerate repeats the saved successful request; Generate uses the current input/settings. Errors preserve both. Clear input and clear result act independently. Only later reviewed AI content can advance into the SEO flow.

Next: M5's supplied desktop workspace, after approval. Follow BUILD → TEST → FIX → TEST AGAIN → VERIFY IN APPLICATION → EXPLAIN → STOP.
