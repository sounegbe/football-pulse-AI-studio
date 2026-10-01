"""Real HTTP/restart verification with isolated temporary data; no real user credentials."""
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import httpx
from app.backend.database import Database
from app.backend.security import provision_user

ROOT = Path(__file__).resolve().parents[1]

def run():
    with tempfile.TemporaryDirectory() as directory:
        db = Database(Path(directory))
        db.initialize()
        password = secrets.token_urlsafe(24)
        provision_user(db, 'smoke-user', password)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        environment = dict(os.environ, STUDIO_DATA_DIR=directory)
        def start():
            process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'main:app', '--app-dir', str(ROOT), '--host', '127.0.0.1', '--port', str(port)], cwd=ROOT.parent, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(60):
                try:
                    if httpx.get(f'http://127.0.0.1:{port}/health', trust_env=False).status_code == 200:
                        return process
                except httpx.ConnectError:
                    time.sleep(.1)
                if process.poll() is not None:
                    raise RuntimeError('Server exited before health check')
            process.terminate()
            process.wait(timeout=5)
            raise RuntimeError('Server failed to become healthy')
        process = start()
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{port}', trust_env=False) as client:
                for path in ['/', '/static/css/style.css', '/static/js/app.js', '/health']:
                    assert client.get(path).status_code == 200
                response = client.post('/api/auth/login', json={'username': 'smoke-user', 'password': password}, headers={'X-Studio-Request':'1'})
                assert response.status_code == 200
                client.headers['X-CSRF-Token'] = response.json()['csrf_token']
                p = client.post('/api/projects', json={'title':'Live smoke project'}).json()['id']
                draft = {'news':'Live HTTP sample', 'content':'  Saved script\n', 'content_type':'youtube_script', 'expected_version':0, 'depth':2, 'audio_cues':False, 'content_mode':'manual'}
                assert client.put(f'/api/projects/{p}/draft', json=draft).status_code == 200
                asset = client.post(f'/api/projects/{p}/assets', content=b'saved file', headers={'Content-Type':'text/plain', 'X-Filename':'sample.txt'}).json()['id']
                job = client.post(f'/api/projects/{p}/jobs', json={'kind':'export','idempotency_key':'live-1','payload':{}}).json()['id']
                assert client.get(f'/api/projects/{p}/assets/{asset}/download').content == b'saved file'
                base = f'/api/projects/{p}/research'
                quote = 'Synthetic United won 2–1.'
                source = client.post(base+'/sources', json={'url':'https://example.org/smoke','title':'Synthetic fixture','publisher':'QA','text':quote,'published_at':'2026-01-10T12:00:00Z'}).json()
                claim = client.post(base+'/claims', json={'statement':quote}).json()
                selection = {'kind':'generation','idempotency_key':'reviewed-live','payload':{'claim_ids':[claim['id']],'content_type':'youtube_script'}}
                assert client.post(f'/api/projects/{p}/jobs', json=selection).status_code == 409
                assert client.post(base+f"/claims/{claim['id']}/evidence", json={'source_id':source['id'],'quote':quote,'relation':'supports','expected_claim_version':1}).status_code == 201
                assert client.post(base+f"/claims/{claim['id']}/reviews", json={'decision':'verified','reason':'Reviewed the dated exact synthetic fixture quote.','expected_version':2}).status_code == 200
                generation = client.post(f'/api/projects/{p}/jobs', json=selection).json()
                process.terminate()
                process.wait(timeout=5)
                process = start()
                assert client.get('/api/auth/session').status_code == 200
                saved = client.get(f'/api/projects/{p}/draft').json()
                assert saved['content'] == draft['content'] and saved['depth'] == 2 and not saved['audio_cues'] and saved['content_mode'] == 'manual'
                pdf = client.get(f'/api/projects/{p}/draft/export.pdf?expected_version=1')
                assert pdf.status_code == 200 and pdf.content.startswith(b'%PDF-')
                assert client.get(f'/api/projects/{p}/assets/{asset}/download').content == b'saved file'
                assert client.get(f'/api/projects/{p}/jobs/{job}').json()['status'] == 'queued'
                assert client.post(f'/api/projects/{p}/jobs/{job}/cancel').json()['status'] == 'cancelled'
                stored = client.get(base+f"/claims/{claim['id']}").json()
                assert stored['status'] == 'verified' and len(stored['reviews']) == 2
                assert stored['evidence'][0]['quote'] == quote
                assert client.get(f"/api/projects/{p}/jobs/{generation['id']}").json()['payload']['review_snapshot'] == generation['payload']['review_snapshot']
                assert client.patch(base+f"/sources/{source['id']}/status", json={'status':'withdrawn','expected_version':1,'reason':'QA withdraws this source after restart.'}).status_code == 200
                assert client.get(base+f"/claims/{claim['id']}").json()['status'] == 'pending'
                assert client.get(f"/api/projects/{p}/jobs/{generation['id']}").json()['status'] == 'cancelled'
                assert client.post('/api/auth/logout').status_code == 204
                assert client.get('/api/projects').status_code == 401
                print('PASS: real HTTP login, project, exact draft, file download, queued job, restart persistence, reviewed research snapshots, source withdrawal, generation cancellation and logout.')
        finally:
            process.terminate()
            process.wait(timeout=5)

if __name__ == '__main__':
    run()
