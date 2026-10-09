import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from main import create_app
from app.backend.config import Settings
from app.backend.security import provision_user, reset_password


class LoginRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = create_app(Settings(data_dir=Path(self.temp.name)), start_worker=False)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.password = '  original password  '
        provision_user(self.app.state.database, 'alice', self.password)

    def login(self, username='alice', password=None):
        return self.client.post('/api/auth/login', json={
            'username': username, 'password': self.password if password is None else password
        }, headers={'X-Studio-Request': '1'})

    def test_username_spaces_normalized_password_spaces_preserved(self):
        response = self.login('  ALICE  ')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['user']['username'], 'alice')
        self.assertEqual(self.client.get('/api/auth/session').status_code, 200)
        self.assertEqual(self.login(password=self.password.strip()).status_code, 401)
        for username in ['   ', 'ali ce', 'alice@example.com']:
            self.assertEqual(self.login(username).status_code, 422)

    def test_reset_revokes_sessions_preserves_projects_and_other_accounts(self):
        response = self.login()
        self.client.headers['X-CSRF-Token'] = response.json()['csrf_token']
        project = self.client.post('/api/projects', json={'title': 'Keep this work'}).json()
        with TestClient(self.app) as other:
            provision_user(self.app.state.database, 'bob', 'bob-password-12345')
            self.assertEqual(other.post('/api/auth/login', json={'username': 'bob', 'password': 'bob-password-12345'}, headers={'X-Studio-Request': '1'}).status_code, 200)
            reset_password(self.app.state.database, ' ALICE ', 'new-password-12345')
            self.assertEqual(other.get('/api/auth/session').status_code, 200)
        self.assertEqual(self.client.get('/api/auth/session').status_code, 401)
        self.assertEqual(self.login().status_code, 401)
        self.assertEqual(self.login(password='new-password-12345').status_code, 200)
        self.assertEqual(self.client.get('/api/projects/' + project['id']).json()['title'], 'Keep this work')

    def test_invalid_reset_is_atomic_and_missing_user_is_not_created(self):
        self.assertEqual(self.login().status_code, 200)
        for username, password in [('alice', 'short'), ('alice', 'x' * 129), ('missing', 'valid-password-12345')]:
            with self.assertRaises(ValueError):
                reset_password(self.app.state.database, username, password)
        self.assertEqual(self.client.get('/api/auth/session').status_code, 200)
        self.assertEqual(self.login().status_code, 200)
        with self.app.state.database.transaction() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM users').fetchone()[0], 1)

    def test_recovery_clears_account_limit_but_keeps_client_limit(self):
        for _ in range(10):
            self.login(password='wrong')
        self.assertEqual(self.login().status_code, 429)
        reset_password(self.app.state.database, 'alice', 'recovered-password-123')
        self.assertEqual(self.login(password='recovered-password-123').status_code, 200)
        with self.app.state.database.transaction() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM login_attempts').fetchone()[0], 12)
