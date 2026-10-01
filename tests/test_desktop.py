from io import BytesIO
from pathlib import Path
import sqlite3
import tempfile
import unittest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from tests import test_foundation
from main import create_app
from app.backend.database import Database
from app.backend.config import ROOT

class DesktopBackendTests(unittest.TestCase):
    setUp=test_foundation.FoundationTests.setUp
    login=test_foundation.FoundationTests.login
    project=test_foundation.FoundationTests.project

    def save(self,p,version=0,**extra):
        return self.client.put(f'/api/projects/{p}/draft',json={'news':'  Synthetic notes\n','content':'## Opening\nLiteral <img onerror=alert(1)>\n## Closing\nRésumé — final paragraph.\n','content_type':'youtube_script','expected_version':version,'depth':2,'audio_cues':False,'content_mode':'manual',**extra})

    def test_options_revision_restore_and_restart(self):
        p=self.project()['id'];first=self.save(p).json()
        self.assertEqual(first['depth'],2);self.assertFalse(first['audio_cues']);self.assertEqual(first['content_mode'],'manual')
        self.assertEqual(self.save(p,1,depth=1,audio_cues=True,content_mode='stub').status_code,200)
        revision=self.client.get(f'/api/projects/{p}/revisions').json()['items'][-1]['id']
        restored=self.client.post(f'/api/projects/{p}/revisions/{revision}/restore',json={'expected_version':2}).json()
        self.assertEqual(restored['depth'],2);self.assertFalse(restored['audio_cues']);self.assertEqual(restored['content_mode'],'manual');self.assertEqual(restored['content'],first['content'])
        with TestClient(create_app(self.settings)) as restarted:
            restarted.cookies.update(self.client.cookies)
            persisted=restarted.get(f'/api/projects/{p}/draft').json()
            self.assertEqual(persisted,restored)

    def test_draft_options_are_strict_and_conflicts_keep_saved_data(self):
        p=self.project()['id'];first=self.save(p).json()
        for bad in ({'depth':True},{'depth':'1'},{'depth':0},{'depth':4},{'audio_cues':1},{'content_mode':'verified'}):
            self.assertEqual(self.save(p,1,**bad).status_code,422)
        self.assertEqual(self.save(p,0,content='overwrite').status_code,409)
        self.assertEqual(self.client.get(f'/api/projects/{p}/draft').json(),first)

    def test_pdf_saved_content_literal_unicode_pagination_and_version(self):
        p=self.project('Synthetic PDF layout QA')['id']
        text='## Chapter 1 — Opening\nRésumé & literal <img onerror=alert(1)>\n'+'Synthetic line with readable spacing.\n'*120+'## Chapter 2 — Closing\nFINAL SENTINEL\n'
        self.assertEqual(self.save(p,content=text).status_code,200)
        response=self.client.get(f'/api/projects/{p}/draft/export.pdf?expected_version=1')
        self.assertEqual(response.status_code,200);self.assertEqual(response.headers['content-type'],'application/pdf');self.assertTrue(response.content.startswith(b'%PDF-'))
        reader=PdfReader(BytesIO(response.content));self.assertGreater(len(reader.pages),1)
        extracted='\n'.join(page.extract_text() for page in reader.pages)
        self.assertIn('Résumé & literal <img onerror=alert(1)>',extracted);self.assertIn('FINAL SENTINEL',extracted);self.assertIn('mode: manual',extracted)
        self.assertEqual(self.client.get(f'/api/projects/{p}/draft/export.pdf?expected_version=2').status_code,409)
        artifact=ROOT/'docs/evidence/m5-draft-export.pdf';artifact.write_bytes(response.content)

    def test_pdf_ownership_empty_unsupported_and_archive(self):
        p=self.project()['id'];base=f'/api/projects/{p}/draft/export.pdf?expected_version=1'
        self.assertEqual(self.client.get(base).status_code,404)
        self.save(p,content='漢字')
        self.assertEqual(self.client.get(base).status_code,422)
        self.save(p,1,content='Synthetic ASCII supported draft')
        self.assertEqual(self.client.get(base.replace('=1','=2')).status_code,200)
        self.client.patch(f'/api/projects/{p}',json={'title':'Archived PDF','expected_version':1,'archived':True})
        self.assertEqual(self.client.get(base.replace('=1','=2')).status_code,200)
        with TestClient(self.app) as stranger:
            self.assertEqual(stranger.get(base).status_code,401)
            self.login(stranger,'bob','bob-password-12345')
            self.assertEqual(stranger.get(base).status_code,404)

    def test_migration_of_existing_v2_draft_is_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            db=Database(Path(directory));Path(directory).mkdir(exist_ok=True)
            with sqlite3.connect(db.path) as connection:
                connection.execute('CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY,applied_at TEXT NOT NULL)')
                for version,name in ((1,'001_foundation.sql'),(2,'002_research.sql')):
                    connection.executescript((ROOT/'app/migrations'/name).read_text())
                    connection.execute('INSERT INTO schema_migrations VALUES (?,?)',(version,'fixture'))
                connection.execute("INSERT INTO users VALUES ('owner','fixture','fixture','fixture')")
                connection.execute("INSERT INTO projects VALUES ('project','owner','Existing',0,1,'fixture','fixture')")
                connection.execute("INSERT INTO drafts VALUES ('project',' Old notes ',' Old content\\n','youtube_script',1,'fixture','fixture')")
            db.initialize()
            with db.transaction() as connection:
                saved=dict(connection.execute('SELECT * FROM drafts').fetchone())
                self.assertEqual(saved['news'],' Old notes ');self.assertEqual(saved['depth'],3);self.assertEqual(saved['audio_cues'],1);self.assertEqual(saved['content_mode'],'unknown')

    def test_desktop_routes_and_no_inline_simulation(self):
        response=self.client.get('/desktop')
        self.assertEqual(response.status_code,200)
        self.assertNotIn('simulateGeneration',response.text);self.assertNotIn('onclick=',response.text)
        self.assertNotIn('Opta Live Stream: Connected',response.text);self.assertNotIn('Tactician Alex',response.text)
        for path in ('/static/js/desktop.js','/static/js/desktop-core.js','/static/js/workspace-route.js','/static/fonts/DejaVuSans.ttf'):
            self.assertEqual(self.client.get(path).status_code,200)
