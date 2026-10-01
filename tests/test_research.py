from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import socket
import sqlite3
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from concurrent.futures import ThreadPoolExecutor
from fastapi import HTTPException
from fastapi.testclient import TestClient
from main import create_app
from app.backend.config import Settings
from app.backend.database import Database
from app.backend.jobs import transition_job
from app.backend.security import provision_user
from app.backend.source_import import ArticleText, canonical_url, fetch_source, public_address, SourceImportError

class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = Settings(data_dir=Path(self.temp.name))
        self.app = create_app(self.settings)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        provision_user(self.app.state.database, 'reviewer', 'reviewer-password-123')
        login = self.client.post('/api/auth/login', json={'username':'reviewer','password':'reviewer-password-123'}, headers={'X-Studio-Request':'1'})
        self.client.headers['X-CSRF-Token'] = login.json()['csrf_token']
        self.project = self.client.post('/api/projects', json={'title':'Research episode'}).json()['id']
        self.base = f'/api/projects/{self.project}/research'

    def source(self, text='Synthetic United won 2–1.', published='2026-01-10T12:00:00Z', url='https://example.org/report'):
        response = self.client.post(self.base+'/sources', json={'url':url,'title':'Synthetic fixture report','publisher':'Fixture publisher','text':text,'published_at':published})
        self.assertIn(response.status_code, (200,201), response.text)
        return response.json()

    def claim(self, statement='Synthetic United won 2–1.'):
        response = self.client.post(self.base+'/claims', json={'statement':statement})
        self.assertIn(response.status_code, (200,201), response.text)
        return response.json()

    def evidence(self, claim, source, relation='supports', quote=None):
        version = self.client.get(self.base+'/claims/'+claim['id']).json()['version']
        response = self.client.post(self.base+'/claims/'+claim['id']+'/evidence', json={'source_id':source['id'],'quote':quote or source['text'],'relation':relation,'expected_claim_version':version})
        self.assertIn(response.status_code, (200,201), response.text)
        return response.json()

    def review(self, claim, decision='verified', expected=None):
        version = expected or self.client.get(self.base+'/claims/'+claim['id']).json()['version']
        return self.client.post(self.base+'/claims/'+claim['id']+'/reviews', json={'decision':decision,'reason':'I compared the statement with the dated source quotation.','expected_version':version})

    def generation(self, claim, key='generation-1', extra=None):
        payload = {'claim_ids':[claim['id']],'content_type':'youtube_script'}
        if extra:
            payload.update(extra)
        return self.client.post(f'/api/projects/{self.project}/jobs', json={'kind':'generation','idempotency_key':key,'payload':payload})

    def verified(self):
        source, claim = self.source(), self.claim()
        evidence = self.evidence(claim, source)
        self.assertEqual(self.review(claim).status_code, 200)
        return source, claim, evidence

    def test_pending_without_evidence_cannot_verify_bundle_or_generate(self):
        claim = self.claim()
        self.assertEqual(claim['status'], 'pending')
        self.assertEqual(self.review(claim).status_code, 409)
        self.assertEqual(self.generation(claim).status_code, 409)
        self.assertEqual(self.client.post(self.base+'/bundle', json={'claim_ids':[claim['id']]}).status_code, 409)
        self.assertFalse(self.client.get(self.base+'/readiness').json()['has_reviewed_claims'])
        self.assertEqual(self.client.post(self.base+'/claims', json={'statement':'fake','status':'verified'}).status_code, 422)

    def test_verified_claim_has_provenance_and_job_snapshot(self):
        source, claim, evidence = self.verified()
        ready = self.client.get(self.base+'/readiness').json()
        self.assertTrue(ready['all_claims_verified'])
        self.assertFalse(ready['truth_guaranteed'])
        bundle = self.client.post(self.base+'/bundle', json={'claim_ids':[claim['id']]}).json()
        self.assertEqual(bundle['reviewed_claims'][0]['evidence'][0]['quote'], source['text'])
        job = self.generation(claim)
        self.assertEqual(job.status_code, 201, job.text)
        self.assertEqual(job.json()['payload']['review_snapshot'], bundle['reviewed_claims'])
        self.assertEqual(self.generation(claim).status_code, 200)
        transition_job(self.app.state.database, job.json()['id'], 'running')
        self.assertEqual(self.client.get(self.base+'/claims/'+claim['id']).json()['reviews'][-1]['event'], 'review_decision')

    def test_undated_source_is_not_sufficient(self):
        source, claim = self.source(published=None), self.claim()
        self.evidence(claim, source)
        self.assertEqual(self.review(claim).status_code, 409)
        self.assertIn('dated_supporting_evidence_required', self.client.get(self.base+'/claims/'+claim['id']).json()['verification_blockers'])

    def test_quote_must_be_exact_and_offsets_must_match(self):
        source, claim = self.source(), self.claim()
        url = self.base+'/claims/'+claim['id']+'/evidence'
        payload = {'source_id':source['id'],'quote':'Invented quote','relation':'supports','expected_claim_version':1}
        self.assertEqual(self.client.post(url,json=payload).status_code, 422)
        payload.update(quote=source['text'],quote_start=1)
        self.assertEqual(self.client.post(url,json=payload).status_code, 422)
        self.assertEqual(self.client.get(self.base+'/claims/'+claim['id']).json()['version'], 1)

    def test_duplicate_sources_and_claims_are_identified_without_extra_reviews(self):
        first = self.source(url='https://example.org/report?utm_campaign=x')
        duplicate = self.source(url='https://example.org/report')
        self.assertEqual(first['id'], duplicate['id'])
        syndicated = self.source(url='https://another.example.org/copy')
        self.assertEqual(syndicated['duplicate_of'], first['id'])
        changed = self.source(text='Corrected result.', url='https://example.org/report')
        self.assertNotEqual(changed['id'], first['id'])
        claim = self.claim('Synthetic United won 2–1.')
        self.assertEqual(self.claim('SYNTHETIC   UNITED WON 2–1.')['id'],claim['id'])
        evidence = self.evidence(claim,syndicated)
        self.assertEqual(self.evidence(claim,syndicated)['id'],evidence['id'])
        self.assertEqual(len(self.client.get(self.base+'/claims/'+claim['id']).json()['reviews']),1)

    def test_contradiction_revokes_review_cancels_job_and_requires_resolution(self):
        source, claim, _ = self.verified()
        job = self.generation(claim).json()
        contradiction = self.source(text='Synthetic United did not win.',url='https://example.org/correction')
        evidence = self.evidence(claim, contradiction, 'contradicts')
        current = self.client.get(self.base+'/claims/'+claim['id']).json()
        self.assertEqual(current['status'], 'pending')
        self.assertIn('contradictory_evidence_unresolved',current['verification_blockers'])
        self.assertEqual(self.review(claim).status_code,409)
        changed_job = self.client.get(f"/api/projects/{self.project}/jobs/{job['id']}").json()
        self.assertEqual(changed_job['status'],'cancelled')
        self.assertEqual(changed_job['error_code'],'research_changed')
        withdrawn = self.client.post(self.base+'/claims/'+claim['id']+'/evidence/'+evidence['id']+'/withdraw', json={'reason':'Correction applied to a different fixture; this comparison was invalid.','expected_claim_version':current['version']})
        self.assertEqual(withdrawn.status_code,200)
        self.assertEqual(self.review(claim).status_code,200)
        self.assertEqual(self.generation(claim,key='generation-2').status_code,201)
        history = self.client.get(self.base+'/claims/'+claim['id']).json()['reviews']
        self.assertEqual([r['event'] for r in history],['evidence_added','review_decision','evidence_added','evidence_withdrawn','review_decision'])

    def test_source_withdrawal_and_restore_require_fresh_review(self):
        source,claim,_ = self.verified()
        job=self.generation(claim).json()
        transition_job(self.app.state.database,job['id'],'running')
        url=self.base+'/sources/'+source['id']+'/status'
        withdrawn=self.client.patch(url,json={'status':'withdrawn','expected_version':1,'reason':'Publisher retracted this report.'})
        self.assertEqual(withdrawn.status_code,200)
        self.assertEqual(self.review(claim).status_code,409)
        self.assertEqual(self.client.get(f"/api/projects/{self.project}/jobs/{job['id']}").json()['status'],'cancelled')
        restored=self.client.patch(url,json={'status':'active','expected_version':2,'reason':'Publisher supplied a reviewed explanation.'})
        self.assertEqual(restored.status_code,200)
        self.assertEqual(self.client.get(self.base+'/claims/'+claim['id']).json()['status'],'pending')
        self.assertEqual(len(self.client.get(self.base+'/sources/'+source['id']).json()['history']),3)
        self.assertEqual(self.review(claim).status_code,200)

    def test_stale_and_concurrent_reviews_conflict(self):
        source,claim=self.source(),self.claim()
        self.evidence(claim,source)
        self.assertEqual(self.review(claim,expected=1).status_code,409)
        def save(_):return self.review(claim,expected=2).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(save,range(2))),[200,409])

    def test_rejected_disputed_and_pending_are_not_generation_inputs(self):
        source,claim,_=self.verified()
        for decision in ['rejected','disputed','pending']:
            self.assertEqual(self.review(claim,decision).status_code,200)
            self.assertEqual(self.generation(claim).status_code,409)

    def test_generation_payload_cannot_inject_unreviewed_facts_or_duplicate_claims(self):
        _,claim,_=self.verified()
        self.assertEqual(self.generation(claim,extra={'news':'Unreviewed transfer rumor'}).status_code,422)
        self.assertEqual(self.generation(claim,extra={'review_snapshot':[]}).status_code,422)
        self.assertEqual(self.generation(claim,extra={'claim_ids':[claim['id'],claim['id']]}).status_code,422)
        self.assertEqual(self.generation(claim,extra={'claim_ids':[]}).status_code,422)
        self.assertEqual(self.generation(claim,extra={'claim_ids':['wrong']} ).status_code,422)

    def test_foreign_project_or_account_cannot_link_read_or_review_research(self):
        source,claim,_=self.verified()
        other=self.client.post('/api/projects',json={'title':'Other project'}).json()['id']
        self.assertEqual(self.client.post(f'/api/projects/{other}/research/bundle',json={'claim_ids':[claim['id']]}).status_code,404)
        other_claim=self.client.post(f'/api/projects/{other}/research/claims',json={'statement':'Other claim'}).json()['id']
        self.assertEqual(self.client.post(f'/api/projects/{other}/research/claims/{other_claim}/evidence',json={'source_id':source['id'],'quote':source['text'],'relation':'supports','expected_claim_version':1}).status_code,404)
        provision_user(self.app.state.database,'outsider','outsider-password-123')
        login=self.client.post('/api/auth/login',json={'username':'outsider','password':'outsider-password-123'},headers={'X-Studio-Request':'1'})
        self.client.headers['X-CSRF-Token']=login.json()['csrf_token']
        for path in ['/sources','/sources/'+source['id'],'/claims','/claims/'+claim['id'],'/readiness']:
            self.assertEqual(self.client.get(self.base+path).status_code,404)
        self.assertEqual(self.review(claim,expected=3).status_code,404)
        self.assertEqual(self.client.post(self.base+'/sources/import',json={'url':'https://www.uefa.com/article'}).status_code,404)

    def test_archived_projects_are_readable_but_cannot_be_reviewed_or_changed(self):
        source,claim,_=self.verified()
        self.client.patch('/api/projects/'+self.project,json={'title':'Archived','archived':True,'expected_version':1})
        self.assertEqual(self.client.get(self.base+'/claims/'+claim['id']).status_code,200)
        self.assertEqual(self.review(claim).status_code,409)
        self.assertEqual(self.client.post(self.base+'/claims',json={'statement':'new'}).status_code,409)

    def test_future_naive_dates_invalid_urls_and_bad_review_are_rejected(self):
        payload={'url':'https://example.org/article','title':'Report','publisher':'Publisher','text':'Source text'}
        for date in ['2026-01-01','2026-01-01T10:00:00',(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),'bad-date']:
            self.assertEqual(self.client.post(self.base+'/sources',json=dict(payload,published_at=date)).status_code,422)
        for url in ['http://example.org','file:///etc/passwd','https://user:pass@example.org','https://127.0.0.1/x','https://example.org:8443','https://example.org/x#fragment','https://example.org/%0d%0aHost:x']:
            self.assertEqual(self.client.post(self.base+'/sources',json=dict(payload,url=url)).status_code,422,url)
        claim=self.claim()
        self.assertEqual(self.client.post(self.base+'/claims/'+claim['id']+'/reviews',json={'decision':'verified','reason':'ok','expected_version':1}).status_code,422)

    def test_import_failure_is_typed_and_does_not_create_source(self):
        with patch('app.backend.research.fetch_source',side_effect=SourceImportError('source_connection_failed','Import failed.')):
            response=self.client.post(self.base+'/sources/import',json={'url':'https://www.uefa.com/article'})
        self.assertEqual(response.status_code,502)
        self.assertEqual(self.client.get(self.base+'/sources').json()['items'],[])
        response=self.client.post(self.base+'/sources/import',json={'url':'https://unapproved.example.org/article'})
        self.assertEqual(response.status_code,422)
        self.assertEqual(response.json()['detail']['code'],'source_host_denied')

    def test_imported_source_keeps_acquisition_and_is_not_automatically_verified(self):
        fetched={'url':'https://www.uefa.com/article','title':'Fixture article','publisher':'www.uefa.com','text':'Fixture report.','published_at':'2026-01-01T12:00:00+00:00'}
        with patch('app.backend.research.fetch_source',return_value=fetched):
            response=self.client.post(self.base+'/sources/import',json={'url':fetched['url']})
        self.assertEqual(response.status_code,201,response.text)
        self.assertEqual(response.json()['acquisition'],'url_import')
        self.assertFalse(self.client.get(self.base+'/readiness').json()['has_reviewed_claims'])

    def test_restart_preserves_review_snapshots_and_migration(self):
        source,claim,_=self.verified()
        with TestClient(create_app(self.settings)) as restarted:
            restarted.cookies.update(self.client.cookies)
            row=restarted.get(self.base+'/claims/'+claim['id']).json()
            self.assertEqual(row['status'],'verified')
            self.assertEqual(row['reviews'][-1]['evidence_snapshot'][0]['content_hash'],source['content_hash'])
            self.assertEqual(restarted.get('/health').json()['schema_version'],4)

    def test_changed_source_snapshot_supersedes_old_and_invalidates_reviews(self):
        source,claim,_=self.verified()
        job=self.generation(claim).json()
        changed=self.source(text='Corrected fixture score.',url=source['url'])
        self.assertNotEqual(changed['id'],source['id'])
        self.assertEqual(self.client.get(self.base+'/sources/'+source['id']).json()['status'],'withdrawn')
        self.assertEqual(self.client.get(self.base+'/claims/'+claim['id']).json()['status'],'pending')
        self.assertEqual(self.client.get(f"/api/projects/{self.project}/jobs/{job['id']}").json()['status'],'cancelled')

    def test_metadata_correction_preserves_provenance_and_resets_review(self):
        source,claim,_=self.verified()
        payload={'title':source['title'],'publisher':source['publisher'],'published_at':'2026-01-11T12:00:00Z','expected_version':1,'reason':'Publication time was corrected against the original page.'}
        changed=self.client.patch(self.base+'/sources/'+source['id']+'/metadata',json=payload)
        self.assertEqual(changed.status_code,200)
        self.assertEqual(self.client.get(self.base+'/claims/'+claim['id']).json()['status'],'pending')
        history=self.client.get(self.base+'/sources/'+source['id']).json()['history']
        self.assertEqual(len(history),2)
        self.assertNotEqual(history[0]['metadata_snapshot'],history[1]['metadata_snapshot'])
        self.assertEqual(self.client.patch(self.base+'/sources/'+source['id']+'/metadata',json=payload).status_code,409)

    def test_worker_refuses_outdated_review_snapshot(self):
        _,claim,_=self.verified()
        job=self.generation(claim).json()
        # Simulates a stale external job record that escaped normal invalidation.
        with self.app.state.database.transaction(write=True) as db:
            db.execute('UPDATE research_claims SET version=version+1 WHERE id=?',(claim['id'],))
        with self.assertRaises(HTTPException) as rejected:
            transition_job(self.app.state.database,job['id'],'running')
        self.assertEqual(rejected.exception.detail['code'],'research_changed')

class SourceTransportTests(unittest.TestCase):
    def test_host_allowlist_precedes_dns_resolution(self):
        with patch('app.backend.source_import.socket.getaddrinfo') as resolver:
            with self.assertRaises(SourceImportError):fetch_source('https://unapproved.example.org/article')
            resolver.assert_not_called()

    def test_all_dns_answers_must_be_public(self):
        for address in ['127.0.0.1','10.0.0.1','169.254.169.254','::1','::ffff:127.0.0.1','224.0.0.1','192.0.2.1']:
            with self.subTest(address=address),patch('app.backend.source_import.socket.getaddrinfo',return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',(address,443))]):
                with self.assertRaises(SourceImportError):public_address('www.uefa.com')
        with patch('app.backend.source_import.socket.getaddrinfo',return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443))]):
            self.assertEqual(public_address('www.uefa.com'),'8.8.8.8')

    def transport(self,status=200,mime='text/html',encoding='identity',body=b'<title>Report</title><article>Fixture goal.</article>'):
        connection=MagicMock()
        response=connection.getresponse.return_value
        response.status=status
        response.getheader.side_effect=lambda name,default=None:{'Content-Type':mime,'Content-Encoding':encoding}.get(name,default)
        response.read1.side_effect=[body,b'']
        return connection

    def test_public_address_is_pinned_and_html_is_filtered(self):
        connection=self.transport(body=b'<title>Report</title><nav>Menu</nav><script>bad()</script><article>Fixture goal.</article>')
        with patch('app.backend.source_import.public_address',return_value='8.8.8.8'),patch('app.backend.source_import.PinnedHTTPSConnection',return_value=connection) as pinned:
            result=fetch_source('https://www.uefa.com/article?utm_source=x')
        pinned.assert_called_once_with('www.uefa.com','8.8.8.8')
        self.assertEqual(result['text'],'Fixture goal.')
        connection.close.assert_called_once()

    def test_redirects_formats_encoding_oversize_and_timeout_are_denied(self):
        for connection,code in [(self.transport(status=302),'source_redirect_denied'),(self.transport(mime='application/pdf'),'source_format_denied'),(self.transport(encoding='gzip'),'source_format_denied'),(self.transport(body=b'x'*(1024*1024+1)),'source_too_large'),(self.transport(body=b'\xff'),'source_encoding_denied')]:
            with patch('app.backend.source_import.public_address',return_value='8.8.8.8'),patch('app.backend.source_import.PinnedHTTPSConnection',return_value=connection):
                with self.assertRaises(SourceImportError) as result:fetch_source('https://www.uefa.com/article')
                self.assertEqual(result.exception.code,code)
                connection.close.assert_called_once()

    def test_article_metadata_and_undated_fallback(self):
        parser=ArticleText();parser.feed('<title>Test</title><meta property="article:published_time" content="2026-01-01T12:00:00Z"><article>Text.</article>')
        self.assertEqual(parser.result()['published_at'],'2026-01-01T12:00:00+00:00')
        parser=ArticleText();parser.feed('<title>Test</title><article>Text.</article>')
        self.assertIsNone(parser.result()['published_at'])

if __name__=='__main__':unittest.main()
