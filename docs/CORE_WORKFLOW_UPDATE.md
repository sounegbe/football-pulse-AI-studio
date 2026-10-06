# Core workflow update — October 6, 2026

## Implemented

- Result viewer: actual chapter/word counts, complete-script copy and exact TXT
  download, saved PDF, teleprompter, explicit reviewed tone attempts.
- Research UI: manual dated sources, allowed article import, source correction
  and withdrawal, claims, exact evidence relations, evidence withdrawal, human
  review decisions, blockers and audit history.
- Core editor: full-script Markdown text, formatting and cue markers, local undo/
  redo, versioned Save Changes, revision preview and explicit restore.
- Phone demo: the root opens the responsive creator shell, retaining a visible
  temporary-storage notice and keeping real provider execution disabled.

## Verification

Automated Python, frontend, real HTTP/restart and deployment checks are recorded
with this update. Synthetic responses exercise the provider queue without sending
provider requests. A new tone attempt preserves the reviewed claim IDs and original
format/depth/cue options; replay after an ambiguous failure reuses its submission
key. Evidence changes still invalidate queued work. Editor restoration is version
checked. Source and script markup remain literal text.

## Remaining work and limits

This update is not completion of all 25 planned milestones. M7 live provider
verification remains pending. The M8 core editor is usable, but the complete
supplied structured cue-card/rich-text layout, chapter-specific frame links and
revert-to-original-AI action remain unfinished. M9–M25 have not been implemented
by this update. SEO, Shorts, thumbnails, voiceover, rendering, publishing, analytics,
live feeds and simulation still require their individual implementation and tests.
Provider-based acceptance needs a securely configured API key. Channel publishing
and private source/media services need their corresponding accounts and scopes.
The current free Render filesystem is ephemeral; accounts are re-provisioned for
the demo but saved projects/assets disappear on restart or spin-down. A durable
free deployment requires migrating both SQLite and local asset storage to external
services; a paid disk was not approved and is not provisioned.

No paid compute/database/storage, publishing action, or live AI request is added.
The existing Foundation service is untouched.
