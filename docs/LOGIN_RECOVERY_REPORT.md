# Login recovery checkpoint — October 9, 2026

## Findings

The inspected `master` repository already contains milestones 1–6, M7 result
viewing and the core M8 editing flow. The earlier conversational recap understated
that progress. Those historical milestone claims remain subject to their reports;
this checkpoint does not certify live provider or hosted operation.

Account provisioning trims and lowercases usernames, while the previous login
payload rejected leading/trailing whitespace. This reproducible mismatch is now
fixed with a username-only validation step. Password whitespace is preserved.
The originally reported login failure cannot be conclusively attributed to this
edge case without the user's local database and original error response.

`manage.py reset-password USERNAME` provides trusted local recovery. It requests
and confirms passwords privately, rejects invalid lengths/missing accounts,
updates the hash and revokes all account sessions in one database transaction.
It clears the account attempt bucket but retains the client-address limit.
Saved work and other accounts remain unchanged. No HTTP recovery endpoint,
public registration, frontend redesign or database migration was added.

The command must use the same `STUDIO_DATA_DIR` as the application. Provider API
keys do not provision users. No actual user account was inspected or reset.

## Verification

- 81 Python tests pass, including four new login/recovery cases.
- 26 JavaScript tests pass.
- Real HTTP walkthrough passes login, project/draft/file operations, restart
  persistence, research review/withdrawal, generation cancellation and logout.
- New cases verify whitespace/case normalization, exact password spacing,
  session revocation, retained projects, isolation of other accounts, atomic
  rejection of invalid recovery and account/client rate-limit behavior.
- Local Uvicorn startup succeeds with an isolated synthetic QA database.
- Cloud browser access to localhost was blocked (`ERR_BLOCKED_BY_CLIENT`).
  Visual login interaction remains unverified; automated checks do not replace it.

## Remaining work

Apply the checkpoint to the user's actual checkout, provision/reset only if
needed, and verify sign-in, reload and an owned saved project there. Live Gemini
verification remains pending configuration and deliberate submission. Review
the milestone map before extending incomplete M8 or later media/publishing work.
GitHub write access and any deployment require separate confirmed results.
