import unittest
from fastapi.testclient import TestClient
from main import create_app
from app.backend.config import Settings
from pathlib import Path
import tempfile

class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.client = TestClient(create_app(Settings(data_dir=Path(self.directory.name))))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def test_pages(self):
        for path in ['/', '/static/css/style.css', '/static/js/app.js', '/health']:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.client.get('/health').json()['generation_mode'], 'stub')

    def test_all_formats_and_boundary(self):
        for kind in ['news_article', 'youtube_script', 'short_video', 'social_post']:
            with self.subTest(kind=kind):
                response = self.client.post('/api/generate', json={'news': 'a' * 2000, 'content_type': kind})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['content_type'], kind)
                self.assertEqual(response.json()['mode'], 'stub')

    def test_invalid_requests(self):
        cases = [
            {'news': '', 'content_type': 'youtube_script'},
            {'news': '   ', 'content_type': 'youtube_script'},
            {'news': 'a' * 2001, 'content_type': 'youtube_script'},
            {'news': 'news', 'content_type': 'unknown'},
            {'news': 12, 'content_type': 'youtube_script'},
            {'content_type': 'youtube_script'},
            {'news': 'news', 'content_type': 'youtube_script', 'extra': True},
        ]
        for payload in cases:
            with self.subTest(payload=str(payload)[:70]):
                self.assertEqual(self.client.post('/api/generate', json=payload).status_code, 422)
        self.assertEqual(self.client.post('/api/generate', content='{', headers={'Content-Type': 'application/json'}).status_code, 422)
        self.assertEqual(self.client.get('/api/generate').status_code, 405)
        self.assertEqual(self.client.get('/missing').status_code, 404)

if __name__ == '__main__':
    unittest.main()
