import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from fastapi.testclient import TestClient
from main import create_app
from app.backend.config import Settings
from app.backend.database import Database
from app.backend.jobs import transition_job, update_progress
from app.backend.security import COOKIE, digest, provision_user

class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = Settings(data_dir=Path(self.temp.name), max_asset_bytes=1024)
        self.app = create_app(self.settings)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        provision_user(self.app.state.database, 'alice', 'alice-password-123')
        provision_user(self.app.state.database, 'bob', 'bob-password-12345')
        self.login()

    def login(self, client=None, username='alice', password='alice-password-123'):
        client = client or self.client
        response = client.post('/api/auth/login', json={'username': username, 'password': password}, headers={'X-Studio-Request': '1'})
        self.assertEqual(response.status_code, 200, response.text)
        client.headers['X-CSRF-Token'] = response.json()['csrf_token']
        return response

    def project(self, title='Episode 1'):
        response = self.client.post('/api/projects', json={'title': title})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def draft(self, project_id, version=0, content='  Script\n  indented\n'):
        return self.client.put(f'/api/projects/{project_id}/draft', json={'news': 'Football news', 'content': content, 'content_type': 'youtube_script', 'expected_version': version})

    def job(self, project_id, key='job-1', payload=None):
        return self.client.post(f'/api/projects/{project_id}/jobs', json={'kind': 'video', 'idempotency_key': key, 'payload': payload or {}})

    def asset(self, project_id, data=b'hello'):
        return self.client.post(f'/api/projects/{project_id}/assets', content=data, headers={'Content-Type': 'text/plain', 'X-Filename': 'script.txt'})

    def test_session_cookie_secrets_rotation_logout(self):
        first_token = self.client.cookies[COOKIE]
        response = self.login()
        new_token = self.client.cookies[COOKIE]
        self.assertNotEqual(first_token, new_token)
        self.assertIn('HttpOnly', response.headers['set-cookie'])
        self.assertIn('SameSite=strict', response.headers['set-cookie'])
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(self.client.get('/api/auth/session').json()['csrf_token'], response.json()['csrf_token'])
        with self.app.state.database.transaction() as db:
            self.assertIsNone(db.execute('SELECT * FROM sessions WHERE token_hash=?', (digest(first_token),)).fetchone())
            rows = [dict(r) for r in db.execute('SELECT * FROM sessions')]
            self.assertNotIn(new_token, json.dumps(rows))
            self.assertNotIn(response.json()['csrf_token'], json.dumps(rows))
            self.assertNotIn('alice-password-123', db.execute('SELECT password_hash FROM users WHERE username=?', ('alice',)).fetchone()[0])
        self.assertEqual(self.client.post('/api/auth/logout').status_code, 204)
        self.assertEqual(self.client.get('/api/projects').status_code, 401)
        self.client.cookies.set(COOKIE, new_token)
        self.assertEqual(self.client.get('/api/projects').status_code, 401)

    def test_production_cookie_is_secure(self):
        settings = Settings(data_dir=Path(self.temp.name), secure_cookies=True)
        with TestClient(create_app(settings), base_url='https://testserver') as client:
            response = self.login(client)
            self.assertIn('Secure', response.headers['set-cookie'])
            self.assertEqual(client.get('/api/auth/session').status_code, 200)

    def test_csrf_origin_and_unauthenticated_denials(self):
        token = self.client.headers.pop('x-csrf-token')
        self.assertEqual(self.client.post('/api/projects', json={'title': 'X'}).status_code, 403)
        self.client.headers['X-CSRF-Token'] = 'wrong'
        self.assertEqual(self.client.post('/api/projects', json={'title': 'X'}).status_code, 403)
        self.client.headers['X-CSRF-Token'] = token
        for header in [{'Origin': 'https://evil.example'}, {'Sec-Fetch-Site': 'cross-site'}]:
            self.assertEqual(self.client.post('/api/projects', json={'title': 'X'}, headers=header).status_code, 403)
        self.client.cookies.clear()
        self.assertEqual(self.client.get('/api/projects').status_code, 401)
        self.assertEqual(self.client.post('/api/auth/login', json={'username': 'alice', 'password': 'alice-password-123'}).status_code, 403)
        self.assertEqual(self.client.post('/api/auth/login', json={'username': 'alice', 'password': 'alice-password-123'}, headers={'X-Studio-Request': '1', 'Origin': 'https://evil.example'}).status_code, 403)

    def test_expired_session(self):
        with self.app.state.database.transaction(write=True) as db:
            db.execute('UPDATE sessions SET expires_at=?', (int(time.time()) - 1,))
        self.assertEqual(self.client.get('/api/auth/session').status_code, 401)

    def test_bad_login_and_rate_limit(self):
        responses = []
        for _ in range(11):
            responses.append(self.client.post('/api/auth/login', json={'username': 'nobody', 'password': 'incorrect'}, headers={'X-Studio-Request': '1'}).status_code)
        self.assertEqual(responses[:10], [401] * 10)
        self.assertEqual(responses[-1], 429)

    def test_validation_does_not_echo_password(self):
        secret = 'private-' * 50
        response = self.client.post('/api/auth/login', json={'username': 'alice', 'password': secret}, headers={'X-Studio-Request': '1'})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(secret, response.text)
        self.assertEqual(response.json()['detail']['code'], 'validation_error')

    def test_project_update_archive_restore_and_conflict(self):
        p = self.project()
        url = f"/api/projects/{p['id']}"
        response = self.client.patch(url, json={'title': 'Renamed', 'expected_version': 1, 'archived': True})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['version'], 2)
        self.assertEqual(self.client.get('/api/projects').json()['items'], [])
        self.assertEqual(len(self.client.get('/api/projects?archived=true').json()['items']), 1)
        self.assertEqual(self.draft(p['id']).status_code, 409)
        self.assertEqual(self.asset(p['id']).status_code, 409)
        self.assertEqual(self.job(p['id']).status_code, 409)
        self.assertEqual(self.client.patch(url, json={'title': 'stale', 'expected_version': 1}).status_code, 409)
        self.assertEqual(self.client.patch(url, json={'title': 'Restored', 'expected_version': 2}).status_code, 200)
        self.assertEqual(self.draft(p['id']).status_code, 200)

    def test_cross_account_cannot_access_any_project_resource(self):
        p = self.project()
        self.draft(p['id'])
        revision = self.client.get(f"/api/projects/{p['id']}/revisions").json()['items'][0]['id']
        asset = self.asset(p['id']).json()['id']
        job = self.job(p['id']).json()['id']
        self.login(username='bob', password='bob-password-12345')
        base = f"/api/projects/{p['id']}"
        for path in [base, base+'/draft', base+'/revisions', base+'/revisions/'+revision, base+'/assets', base+'/assets/'+asset+'/download', base+'/jobs', base+'/jobs/'+job]:
            self.assertEqual(self.client.get(path).status_code, 404, path)
        self.assertEqual(self.client.patch(base, json={'title':'No','expected_version':1}).status_code, 404)
        self.assertEqual(self.draft(p['id']).status_code, 404)
        self.assertEqual(self.asset(p['id']).status_code, 404)
        self.assertEqual(self.job(p['id']).status_code, 404)
        self.assertEqual(self.client.post(base+'/jobs/'+job+'/cancel').status_code, 404)
        self.assertEqual(self.client.post(base+'/revisions/'+revision+'/restore', json={'expected_version':1}).status_code, 404)
        self.assertEqual(self.client.get('/api/projects').json()['items'], [])

    def test_revision_history_preserves_whitespace_and_restore_is_new_revision(self):
        p = self.project()['id']
        first = self.draft(p).json()
        self.assertEqual(first['content'], '  Script\n  indented\n')
        revision = self.client.get(f'/api/projects/{p}/revisions').json()['items'][0]['id']
        self.assertEqual(self.draft(p, 1, 'new').json()['version'], 2)
        self.assertEqual(self.draft(p, 1, 'stale').status_code, 409)
        response = self.client.post(f'/api/projects/{p}/revisions/{revision}/restore', json={'expected_version':2})
        self.assertEqual(response.json()['version'], 3)
        self.assertEqual(response.json()['content'], first['content'])
        history = self.client.get(f'/api/projects/{p}/revisions').json()['items']
        self.assertEqual(len(history), 3)
        self.assertEqual(history[0]['restored_from'], revision)
        self.assertEqual(self.client.get(f'/api/projects/{p}/revisions/{revision}').json()['content'], first['content'])

    def test_concurrent_draft_updates_only_one_wins(self):
        p = self.project()['id']
        self.draft(p)
        def save(text):
            return self.draft(p, 1, text).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(save, ['first', 'second']))
        self.assertEqual(sorted(statuses), [200, 409])
        self.assertEqual(self.client.get(f'/api/projects/{p}/draft').json()['version'], 2)

    def test_asset_upload_download_and_limits(self):
        p = self.project()['id']
        data = b'<script>alert(1)</script>'
        asset = self.asset(p, data)
        self.assertEqual(asset.status_code, 201)
        self.assertEqual(asset.json()['sha256'], hashlib.sha256(data).hexdigest())
        response = self.client.get(f"/api/projects/{p}/assets/{asset.json()['id']}/download")
        self.assertEqual(response.content, data)
        self.assertEqual(response.headers['content-type'], 'application/octet-stream')
        self.assertIn('attachment', response.headers['content-disposition'])
        self.assertEqual(response.headers['x-content-type-options'], 'nosniff')
        self.assertEqual(self.asset(p, b'x'*1025).status_code, 413)
        self.assertEqual(self.asset(p, b'').status_code, 422)
        self.assertEqual(self.client.post(f'/api/projects/{p}/assets', content=b'x', headers={'Content-Type':'text/html','X-Filename':'file.html'}).status_code, 415)
        self.assertEqual(self.client.post(f'/api/projects/{p}/assets', content=b'x', headers={'Content-Type':'text/plain','X-Filename':'../escape'}).status_code, 422)
        self.assertEqual(len(self.client.get(f'/api/projects/{p}/assets').json()['items']), 1)

    def test_asset_transaction_rolls_back_and_missing_files_are_reported(self):
        p = self.project()['id']
        with patch.object(Path, 'open', side_effect=OSError('disk full')):
            self.assertEqual(self.asset(p).status_code, 503)
        self.assertEqual(self.client.get(f'/api/projects/{p}/assets').json()['items'], [])
        self.assertEqual(list((self.settings.data_dir/'assets').iterdir()), [])
        asset = self.asset(p).json()
        (self.settings.data_dir/'assets'/asset['id']).unlink()
        self.assertEqual(self.client.get(f"/api/projects/{p}/assets/{asset['id']}/download").status_code, 409)

    def test_jobs_idempotency_state_and_cancel(self):
        p = self.project()['id']
        job = self.job(p, payload={'duration':30}).json()
        self.assertEqual(job['status'], 'queued')
        repeat = self.job(p, payload={'duration':30})
        self.assertEqual(repeat.status_code, 200)
        self.assertEqual(repeat.json()['id'], job['id'])
        self.assertEqual(self.job(p, payload={'duration':60}).status_code, 409)
        transition_job(self.app.state.database, job['id'], 'running', progress=20)
        self.assertEqual(update_progress(self.app.state.database, job['id'], 30)['progress'], 30)
        with self.assertRaises(ValueError):
            update_progress(self.app.state.database, job['id'], 10)
        response = self.client.post(f"/api/projects/{p}/jobs/{job['id']}/cancel")
        self.assertEqual(response.json()['status'], 'cancelled')
        with self.assertRaises(ValueError):
            update_progress(self.app.state.database, job['id'], 40)
        self.assertEqual(self.client.post(f"/api/projects/{p}/jobs/{job['id']}/cancel").status_code, 200)
        with self.assertRaises(ValueError):
            transition_job(self.app.state.database, job['id'], 'succeeded')
        self.assertEqual(len(self.client.get(f'/api/projects/{p}/jobs').json()['items']), 1)

    def test_job_success_requires_owned_asset_and_failed_requires_error(self):
        p = self.project()['id']
        job = self.job(p).json()
        with self.assertRaises(ValueError):
            transition_job(self.app.state.database, job['id'], 'succeeded')
        transition_job(self.app.state.database, job['id'], 'running', progress=10)
        with self.assertRaises(ValueError):
            transition_job(self.app.state.database, job['id'], 'failed')
        other = self.project('Other')['id']
        foreign_asset = self.asset(other).json()['id']
        with self.assertRaises(ValueError):
            transition_job(self.app.state.database, job['id'], 'succeeded', result_asset_id=foreign_asset)
        result_asset = self.asset(p).json()['id']
        transition_job(self.app.state.database, job['id'], 'succeeded', result_asset_id=result_asset)
        self.assertEqual(self.client.get(f"/api/projects/{p}/jobs/{job['id']}").json()['progress'], 100)
        self.assertEqual(self.client.post(f"/api/projects/{p}/jobs/{job['id']}/cancel").status_code, 409)

    def test_restart_persists_project_draft_assets_sessions_and_recovers_running_job(self):
        p = self.project()['id']
        self.draft(p)
        asset = self.asset(p).json()['id']
        job = self.job(p).json()['id']
        transition_job(self.app.state.database, job, 'running', progress=40)
        queued = self.job(p, 'queued').json()['id']
        with TestClient(create_app(self.settings)) as restarted:
            restarted.cookies.update(self.client.cookies)
            self.assertEqual(restarted.get(f'/api/projects/{p}').status_code, 200)
            self.assertEqual(restarted.get(f'/api/projects/{p}/draft').json()['version'], 1)
            self.assertEqual(restarted.get(f'/api/projects/{p}/assets/{asset}/download').content, b'hello')
            failed = restarted.get(f'/api/projects/{p}/jobs/{job}').json()
            self.assertEqual(failed['status'], 'failed')
            self.assertEqual(failed['error_code'], 'worker_interrupted')
            self.assertEqual(restarted.get(f'/api/projects/{p}/jobs/{queued}').json()['status'], 'queued')
            self.assertEqual(restarted.get('/health').json()['schema_version'], 4)
        with self.app.state.database.transaction() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM schema_migrations').fetchone()[0], 4)

    def test_transactions_rollback_and_foreign_keys_are_enforced(self):
        p = self.project()['id']
        with self.assertRaises(RuntimeError):
            with self.app.state.database.transaction(write=True) as db:
                db.execute('UPDATE projects SET title=? WHERE id=?', ('should roll back',p))
                raise RuntimeError('interrupted')
        self.assertEqual(self.client.get(f'/api/projects/{p}').json()['title'], 'Episode 1')
        with self.assertRaises(sqlite3.IntegrityError):
            with self.app.state.database.transaction(write=True) as db:
                db.execute('INSERT INTO projects VALUES (?,?,?,0,1,?,?)', ('bad','missing-owner','title','now','now'))

    def test_invalid_payloads_and_pagination(self):
        p = self.project()['id']
        self.assertEqual(self.client.post('/api/projects', json={'title':'  '}).status_code, 422)
        self.assertEqual(self.client.get('/api/projects?limit=101').status_code, 422)
        self.assertEqual(self.client.get(f'/api/projects/{p}/draft').status_code, 404)
        self.assertEqual(self.client.get(f'/api/projects/{p}/revisions/missing').status_code, 404)
        self.assertEqual(self.client.get(f'/api/projects/{p}/jobs/missing').status_code, 404)
        self.assertEqual(self.job(p, payload={'x':'x'*16001}).status_code, 422)
        response = self.client.post(f'/api/projects/{p}/jobs', content='{"kind":"video","idempotency_key":"nan","payload":{"x":NaN}}', headers={'Content-Type':'application/json'})
        self.assertEqual(response.status_code, 422)
        response = self.client.post('/api/projects', content=b'x'*(2*1024*1024+1), headers={'Content-Type':'application/json'})
        self.assertEqual(response.status_code, 413)

    def test_database_busy_returns_typed_error(self):
        with patch.object(self.app.state.database, 'transaction', side_effect=sqlite3.OperationalError('secret path')):
            response = self.client.get('/api/projects')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('secret path', response.text)

    def test_configuration_and_environment_validation(self):
        config = self.client.get('/api/configuration').json()
        self.assertEqual(config['job_execution'], 'not_configured')
        self.assertEqual(config['max_asset_bytes'], 1024)
        with patch.dict('os.environ', {'STUDIO_ENV':'production', 'STUDIO_ALLOWED_ORIGINS':'http://localhost:8000'}):
            with self.assertRaises(ValueError):
                Settings.from_env()
        with patch.dict('os.environ', {'STUDIO_ALLOWED_ORIGINS':'http://external.example'}):
            with self.assertRaises(ValueError):
                Settings.from_env()
        with patch.dict('os.environ', {'STUDIO_ENV':'production', 'STUDIO_ALLOWED_ORIGINS':'https://studio.example'}):
            self.assertTrue(Settings.from_env().secure_cookies)

if __name__ == '__main__':
    unittest.main()
