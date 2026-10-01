"""Local-only browser QA harness around the actual application.

Faults are controlled by a checkout-local file, never by a public API.
This module is not the production startup target.
"""
import asyncio
from pathlib import Path
from fastapi.responses import HTMLResponse, JSONResponse, Response
import json
import secrets
import time
from app.backend.config import ROOT, Settings
from app.backend.database import timestamp
from app.backend.security import COOKIE, digest, provision_user
from main import create_app
from app.backend.generation_provider import GenerationConfig
from tests.generation_fixture import QAGenerationProvider

# The QA server uses disposable accounts/data, never the regular studio database.
app = create_app(Settings(data_dir=ROOT / '.qa-data', allowed_origins=('http://terminal.local:4173', 'http://localhost:8000', 'http://127.0.0.1:8000')), generation_config=GenerationConfig(True,'qa-not-a-live-key','QA_ONLY_SYNTHETIC_PROVIDER',6000,10,('2','1','8')), generation_provider=QAGenerationProvider())


SCENARIO = Path(__file__).resolve().parents[1] / '.qa-scenario'

@app.middleware('http')
async def browser_scenario(request, call_next):
    mode = SCENARIO.read_text().strip() if SCENARIO.exists() else 'normal'
    if request.url.path == '/api/generate' and request.method == 'POST':
        if mode == 'slow':
            await asyncio.sleep(6)
        elif mode == 'timeout':
            await asyncio.sleep(18)
        elif mode == 'http_error':
            return JSONResponse({'detail':'QA server failure'}, status_code=500)
        elif mode == 'bad_json':
            return Response('invalid JSON', media_type='application/json')
        elif mode == 'unsafe_text':
            body = await request.json()
            return JSONResponse({'content':'<img src=x onerror=alert(1)>\nQA text', 'content_type':body['content_type'], 'mode':'stub', 'depth':body.get('depth',3), 'audio_cues':body.get('audio_cues',True)})
    return await call_next(request)

@app.get('/qa/mobile', response_class=HTMLResponse, include_in_schema=False)
def mobile_preview():
    return '''<!doctype html><html><head><title>M1 Mobile Browser QA</title></head>
    <body style="margin:0;background:#202020;color:white;font:16px Arial">
    <p>Actual creator page at a 390px mobile viewport</p>
    <iframe title="Mobile creator workspace" src="/" style="width:390px;height:1100px;border:0"></iframe>
    </body></html>'''


@app.get('/qa/research', response_class=HTMLResponse, include_in_schema=False)
def research_browser_qa():
    return qa_session_response((ROOT / 'tests/research_qa.html').read_text())

def qa_session_response(html):
    # Issue a synthetic test session server-side. No user credentials are requested or exposed.
    db = app.state.database
    with db.transaction() as connection:
        account = connection.execute('SELECT id FROM users WHERE username=?', ('qa-reviewer',)).fetchone()
    account_id = account['id'] if account else provision_user(db, 'qa-reviewer', secrets.token_urlsafe(24))
    token = secrets.token_urlsafe(32)
    csrf = digest('csrf:' + token)
    with db.transaction(write=True) as connection:
        connection.execute('INSERT INTO sessions VALUES (?,?,?,?,?)', (digest(token), account_id, digest(csrf), int(time.time())+3600, timestamp()))
    response = HTMLResponse(html)
    response.set_cookie(COOKIE, token, httponly=True, samesite='strict', max_age=3600, path='/')
    response.headers['Cache-Control'] = 'no-store'
    return response

@app.get('/qa/workspace-mobile', response_class=HTMLResponse, include_in_schema=False)
def workspace_mobile():
    return '''<!doctype html><html><head><title>M4 Mobile Layout Checks</title></head>
    <body style="margin:0;background:#0f131c;color:white;font:16px Arial">
    <h1 style="font-size:18px;margin:16px">M4: both supplied mobile workspace variants at 390px</h1>
    <div style="display:flex;gap:20px;flex-wrap:wrap">
    <iframe id="m4-mobile" title="M4 mobile workspace" src="/" style="width:390px;height:950px;border:0"></iframe>
    <iframe id="original-mobile" title="Original mobile workspace" src="/workspace/mobile-original" style="width:390px;height:950px;border:0"></iframe>
    </div></body></html>'''


@app.get('/qa/desktop', response_class=HTMLResponse, include_in_schema=False)
def desktop_qa():
    return qa_session_response((ROOT / 'tests/desktop_qa.html').read_text())

@app.get('/qa/desktop-mobile', response_class=HTMLResponse, include_in_schema=False)
def desktop_mobile_qa():
    with app.state.database.transaction() as connection:
        row = connection.execute("SELECT id FROM projects WHERE title='M5 synthetic continuity fixture' ORDER BY updated_at DESC LIMIT 1").fetchone()
    target='/desktop?project='+row['id'] if row else '/desktop'
    return '<!doctype html><html><head><title>M5 Desktop Responsive Check</title></head><body style="margin:0;background:#0f131c;color:white"><h1 style="font:18px Arial">Desktop shell at 390px</h1><iframe id="desktop-mobile" title="Desktop shell at mobile width" src="' + target + '" style="width:390px;height:950px;border:0"></iframe></body></html>'


@app.get('/qa/fixture-video', include_in_schema=False)
def fixture_video():
    return Response((ROOT / 'tests/fixtures/preview.mp4').read_bytes(), media_type='video/mp4')

@app.get('/qa/generation', response_class=HTMLResponse, include_in_schema=False)
def generation_browser_qa():
    return qa_session_response((ROOT / 'tests/generation_qa.html').read_text())

@app.get('/qa/generation-mobile', response_class=HTMLResponse, include_in_schema=False)
def generation_mobile():
    with app.state.database.transaction() as db:
        row=db.execute("SELECT id FROM projects WHERE title='M6 synthetic reviewed generation' ORDER BY updated_at DESC LIMIT 1").fetchone()
    if not row:
        return HTMLResponse('Prepare the synthetic generation project first.',status_code=404)
    return HTMLResponse('<!doctype html><html><head><title>M6 responsive generation</title></head><body style="margin:0;background:#10131c;color:white"><h1>Generation at 390px</h1><iframe id="generation-mobile" title="M6 generation mobile width" style="width:390px;height:1050px;border:0" src="/desktop?project='+row['id']+'"></iframe></body></html>')
