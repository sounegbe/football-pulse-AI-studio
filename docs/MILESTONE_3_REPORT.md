# Milestone 3 — source research and claim review

Date: 2026-09-30. Backend implementation and local verification passed. Live external publisher retrieval remains unverified. M4 has not started; no commit, push or deployment was performed.

## Result

Projects now retain attributed source text snapshots, publication/capture dates, fingerprints, duplicate relationships, exact quoted evidence, claim statuses and review history. New or imported information never becomes verified automatically. Verification records a human decision with dated supporting evidence and no unresolved active contradiction; API bundles explicitly state `truth_guaranteed: false`.

Generation job records accept only selected verified claim IDs and a content format. The server supplies an immutable review snapshot. Changed evidence/source metadata, withdrawal and changed article text invalidate affected reviews and cancel queued/running generation work; worker transitions recheck snapshots. Completed jobs remain historical records. AI generation and publication are not connected.

The supplied product frontend is preserved. Browser verification used a separate synthetic QA page and isolated database calling the real authenticated application APIs.

## Build, test, fix, test again

Added transactional migration 002 and research/import services, routes and M2 job integration. Review and source changes require current versions and retain reasons/history. Ownership checks prevent linking or accessing another project/account's research.

Review found two material cases requiring fixes: a changed article at the same URL now supersedes the old active snapshot and revokes affected reviews; source title/publisher/date corrections now retain an audit snapshot and require fresh review. The duplicate-source test fixture was corrected to attach the active syndicated snapshot after supersession rather than the withdrawn original.

Final checks:

| Check | Result |
| --- | --- |
| Python unittest discovery | 46 passed: 22 M1/M2 and 24 M3 |
| Node frontend suite | 5 passed |
| Real HTTP walkthrough with actual server restart | Passed; session, draft, file, jobs, quotes and review snapshots persisted; withdrawal revoked review and cancelled generation |
| Browser research workflow | Passed all six scenarios through real protected APIs |
| Browser after server stop/start | Verified claim, original exact quote and five review events reloaded |

Commands: `.venv/bin/python -m unittest discover -s tests -v`, `node --test tests/test_frontend.cjs`, `.venv/bin/python -m tests.live_smoke`.

Browser scenarios covered source attribution/deduplication, pending-claim rejection, explicit dated review, snapshot creation, contradiction revocation/job cancellation, withdrawal with fresh review and retained history. Evidence: [research workflow](evidence/m3-browser-research.jpg). Restart persistence was also visibly confirmed in the browser; its screenshot could not be attached.

Negative tests cover missing/undated evidence, exact quote offsets, rejected/disputed claims, injected generation inputs, cross-account/project access, stale/concurrent reviews, archive restrictions, metadata correction, source supersession and outdated worker snapshots. Import transport tests exercise publisher allowlisting before DNS, public addresses only, connection address pinning, TLS hostname usage, redirects, formats, encoding, size and timeout failures.

## Limits and next milestone

External import transport was exercised with controlled test responses; successful live retrieval from a real publisher was not verified in this environment. Do not infer live publisher coverage from the browser manual-ingestion checks. Import failures return typed errors and create no source. Extraction supports bounded UTF-8 HTML/plain text and may omit dates or article text on complex publisher pages; undated evidence cannot establish verification. Redirecting article URLs must be replaced by their allowed final URL or manually ingested.

Human review can still be mistaken; the application records provenance and decision history rather than guaranteeing truth. Current app storage remains single-process SQLite. Production research screens, AI extraction/generation workers and publishing checks belong to later milestones.

M1 browser verification remains passed, documented in MILESTONE_1_REPORT.md. M3 is ready for review with the external retrieval limit above; continue to M4 only after approval under the agreed milestone process.
