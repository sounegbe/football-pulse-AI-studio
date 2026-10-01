# Run M6 on your computer

This source snapshot includes current M1–M6 code, tests and reports. It excludes credentials, account databases, uploaded/private files, QA state, installed dependencies and Git history. It is not a GitHub push. Extract into a fresh folder to preserve any existing checkout.

Requirements: Python 3.12, pip and venv support. Node is only required if recompiling CSS or running frontend tests; compiled CSS is already included.

From the extracted project folder:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python manage.py create-user 2solo
.venv/bin/python scripts/run_local_live.py
```

The account command asks twice for a new local studio password (12–128 characters). The launcher asks for your OpenAI API key without displaying it, keeps it in the server process environment, and does not save it to a file. Enter the key only in your terminal. Press Enter for the proposed pinned test model, or enter a model available to your API account.

Default test model: `gpt-4.1-mini-2025-04-14`, listed with Responses support in the official model documentation checked on 2026-10-01: https://developers.openai.com/api/docs/models/gpt-4.1-mini . Account access and billing still need to be confirmed. Cost remains unknown until current model rates are configured; see the M6 report for pricing variables. The launcher deliberately clears inherited rates to avoid estimates for the wrong model.

Open http://127.0.0.1:8000/desktop and sign in as `2solo` with your local studio password. This is separate from your OpenAI credential. No synthetic QA account or project is included.

The application can start without generating anything. Live generation accepts only claims with current explicit human reviews and supporting evidence. We will prepare one controlled reviewed test and verify its actual provider response, usage, saved result and browser behavior before declaring M6 fully verified. Do not treat merely starting the server as that live check.

If Python reports a missing venv module or dependency installation fails, keep the non-secret error text so setup can be corrected. Do not send API keys or passwords.
