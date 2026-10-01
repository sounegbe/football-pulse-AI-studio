# Milestone 5 — desktop workspace and project continuity

Date: 2026-09-30. Built and verified locally. No commit, push or deployment. M6 has not started.

## Result

The supplied `creator_workspace_desktop_milestone_5` layout now connects to saved projects, drafts, research readiness, source assets and PDF export. Sidebar, header, blueprint cards, two-column workbench and supplied assets remain. Fabricated persona, live-feed and provider claims were removed. Generation remains an explicitly labelled test stub.

Home selects desktop at initial viewport widths >=1024px. M4 mobile layouts and `/legacy` remain available. Explicit `/desktop` adapts to narrow screens. Browser inspection found and fixed leftover sidebar padding at 390px; rendered controls now fit and the collapsed menu opens actual project navigation.

## Controls

| Control | Actual behavior |
| --- | --- |
| Account | Existing session/sign-in UI; logout revokes session and clears editor; dirty logout requires a choice |
| Projects / active workspace / Dashboard | Owned project listing and selection; unsaved changes block replacement |
| New project | Creates a real project; clean existing projects start a fresh editor |
| Save / reload | Exact notes, output, format, depth, cues and mode; optimistic version checks; explicit dirty reload choice |
| Blueprint / depth / cues | Accessible controls and strict server validation |
| Generate / regenerate | Real stub request; regenerate repeats last successful request; changed source/settings block saving old output |
| Chapters | Actual heading spans with exact original text; no invented chapters |
| Research / pipeline | Real readiness counts and blockers; no automatic verification |
| Scripts | Current saved draft preview; editing belongs to M8 |
| Jobs | Real job records; workers are not connected |
| B-roll | Owned MP4 source assets, pagination and actual byte decoding; empty/unreadable states; preview cleanup on project replacement |
| PDF | Authenticated, version-checked export of saved content |
| Copy / teleprompter | Full output; actual clipboard/fullscreen attempts and visible fallbacks |
| Shorts / SEO / thumbnails / publishing | Explain future milestone; no simulated completion |
| Settings | Account access dialog; full settings remain a later milestone |

## Persistence and PDF

Migration 003 adds depth, audio cues and content mode to drafts and immutable revisions. Existing v2 drafts receive safe defaults and `unknown` mode. Restoring a revision retains its original options and creates a new version. Restart checks retain content/options. Mode can only be `unknown`, `manual` or `stub`; saving never approves publication.

The PDF endpoint requires ownership and the expected saved version. Empty, missing, stale and foreign drafts are rejected. Embedded licensed DejaVuSans provides measured wrapping and pagination. Markup-looking input is literal text. Latin accents and punctuation are tested; unsupported glyphs/control characters return a typed 422 error. Full multilingual shaping is not claimed. The three-page synthetic sample passed text extraction and visual first/last-page inspection.

## Validation

- 55 Python tests and 18 frontend tests passed: 73 total, including previous milestone regression tests.
- Real HTTP/restart smoke walkthrough passed, including persisted draft options and PDF bytes.
- Browser: saved draft/options loaded; chapters; generate/save/reload; two-editor stale-save conflict preserved local work; dirty navigation and reload choices; actual project creation; continuity after server restart; research readiness; 390px navigation and repaired layout.
- Browser media: invalid MP4 produced a decode error; valid synthetic MP4 reported actual 320 × 180 metadata and 0.8-second duration with playback controls.
- Automated coverage includes PDF ownership/version/content, migration from v2 and option-preserving revision restore.

## Verification limits

PDF API bytes and rendered content passed, but the browser did not expose a collected download event. The UI says download requested rather than completed. The HTTP preview denies clipboard/fullscreen access: manual-copy guidance and the full-text teleprompter fallback work; successful secure-context copying/fullscreen remain unverified. The new dirty-logout confirmation is implemented but not independently browser-tested. Live publisher retrieval remains unverified from M3. No AI provider, worker, video renderer or publishing destination is connected.

## Evidence and next milestone

- [Desktop workspace](evidence/m5-desktop-verified.jpg)
- [Responsive workspace](evidence/m5-desktop-mobile.jpg)
- [Owned source video preview](evidence/m5-source-preview.jpg)
- [Synthetic saved-draft PDF](evidence/m5-draft-export.pdf)

Next is M6: actual provider/queued generation, progress, cancellation, retry and cost reporting, retaining M3 reviewed-evidence gates. Stop here for approval.
