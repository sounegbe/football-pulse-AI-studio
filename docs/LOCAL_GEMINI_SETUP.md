# Local Gemini test

Render deployment remains paused. Gemini is optional; OpenAI remains supported.
This integration has local automated and synthetic browser checks, but no live
Google request has been verified yet. M6 live verification remains pending.

Create a key in Google AI Studio: https://aistudio.google.com/apikey.
Check your account's free-tier model availability and quota before generating:
https://ai.google.dev/gemini-api/docs/pricing. Free-tier inputs and outputs may
be used to improve Google's products; use public or synthetic test material.
Do not enable paid billing merely to run this test.

From the project directory, after installing `requirements.txt` in `.venv`:

```bash
.venv/bin/python manage.py create-user 2solo
.venv/bin/python scripts/run_local_live.py --provider gemini
```

Skip account creation if this local data directory already has your account.
The launcher asks for the key without echoing or saving it. Never send it in
chat. It proposes `gemini-2.5-flash-lite`; select a text model currently
available in your account with free quota. Model availability is not guaranteed.
Use the bare model identifier, without `models/`.

Open http://127.0.0.1:8000/desktop, sign in, and prepare a project with a source,
supporting quote, claim and human review. Refresh reviewed claims, select the
claim, generate, inspect the result, explicitly use it in the editor, and save.
Reload and restart to verify persistence. Cancel/retry controls remain the same.

Server configuration: `STUDIO_GENERATION_PROVIDER=gemini`, `GEMINI_API_KEY`,
`STUDIO_GEMINI_MODEL`, and `STUDIO_GENERATION_ENABLED=1`. Keys stay server-side.
Changing provider or model fails older queued jobs without sending them to the
new provider; an explicit retry creates an attempt using current configuration.

The UI reports actual provider token usage, including thinking tokens in output
usage while excluding thinking text from the draft. Costs remain unknown unless
you configure all three existing pricing variables for the selected model and
billing tier. A free-tier key does not imply unlimited usage or permanent free
access; 429 quota/rate-limit failures require an explicit retry.

Official API references: https://ai.google.dev/api and
https://ai.google.dev/api/generate-content.
