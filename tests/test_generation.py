import json
import threading
import unittest
from unittest.mock import patch
from app.backend.generation_provider import GenerationConfig, ProviderError, parse_response, calculate_cost, build_prompt, OpenAIProvider
from tests import test_research as research_helpers


class FixtureProvider:
    def __init__(self):
        self.calls=[];self.error=None;self.hook=None
    def generate(self,payload,model,maximum):
        self.calls.append((payload,model,maximum))
        if self.hook:self.hook()
        if self.error:raise ProviderError(self.error)
        return {'content':'## Synthetic chapter\nSynthetic United won 2–1. <img> is literal.\n','response_id':'qa-response','usage':{'input_tokens':100,'output_tokens':50,'cached_tokens':20}}


class GenerationTests(unittest.TestCase):
    setUp=research_helpers.ResearchTests.setUp
    source=research_helpers.ResearchTests.source
    claim=research_helpers.ResearchTests.claim
    evidence=research_helpers.ResearchTests.evidence
    review=research_helpers.ResearchTests.review
    verified=research_helpers.ResearchTests.verified

    def configure(self):
        self.provider=FixtureProvider()
        self.app.state.generation_config=GenerationConfig(True,'qa-key','qa-model',6000,10,('2','1','8'))
        self.worker=self.app.state.generation_worker
        self.worker.config=self.app.state.generation_config
        self.worker.provider=self.provider
        self.url=f'/api/projects/{self.project}/generation'

    def enqueue(self,claim,key='gen-1'):
        return self.client.post(self.url,json={'claim_ids':[claim['id']],'content_type':'youtube_script','depth':2,'audio_cues':False,'idempotency_key':key})

    def test_disabled_auth_ownership_and_csrf(self):
        self.configure();_,claim,_=self.verified()
        self.app.state.generation_config=GenerationConfig()
        self.assertEqual(self.enqueue(claim).status_code,503)
        self.assertEqual(self.client.post('/api/projects/missing/generation',json={'claim_ids':[claim['id']],'idempotency_key':'x'}).status_code,404)
        self.client.headers.pop('X-CSRF-Token')
        self.assertEqual(self.enqueue(claim).status_code,403)
        self.client.cookies.clear()
        self.assertEqual(self.client.get(self.url).status_code,401)

    def test_evidence_gate_and_bounded_input(self):
        self.configure();claim=self.claim()
        self.assertEqual(self.enqueue(claim).status_code,409)
        _,claim,_=self.verified()
        with patch('app.backend.generation.build_prompt',side_effect=ProviderError('generation_input_too_large')):
            self.assertEqual(self.enqueue(claim).status_code,422)
        self.assertEqual(self.client.post(self.url,json={'claim_ids':[claim['id']],'news':'invented','idempotency_key':'bad'}).status_code,422)

    def test_success_idempotency_options_usage_asset_and_no_auto_draft(self):
        self.configure();_,claim,_=self.verified()
        result=self.enqueue(claim);self.assertEqual(result.status_code,201,result.text)
        identity=result.json()['id']
        self.assertEqual(self.enqueue(claim).status_code,200)
        self.assertTrue(self.worker.run_once());self.assertFalse(self.worker.run_once())
        completed=self.client.get(self.url+'/'+identity).json()
        self.assertEqual(completed['status'],'succeeded');self.assertEqual(completed['progress'],100)
        self.assertEqual(completed['generation']['cost_usd'],'0.00058')
        self.assertEqual(completed['generation']['billing_status'],'reported')
        raw=self.client.get(f'/api/projects/{self.project}/assets/'+completed['result_asset_id']+'/download').text
        self.assertIn('<img> is literal',raw)
        self.assertEqual(self.client.get(f'/api/projects/{self.project}/draft').status_code,404)
        payload,model,maximum=self.provider.calls[0]
        self.assertEqual((payload['depth'],payload['audio_cues'],model,maximum),(2,False,'qa-model',6000))
        self.assertIn('Synthetic United',build_prompt(payload))
        self.assertEqual(self.client.post(self.url+'/'+identity+'/retry',json={'idempotency_key':'retry'}).status_code,409)

    def test_manual_retry_new_attempt_and_unknown_billing(self):
        self.configure();_,claim,_=self.verified()
        identity=self.enqueue(claim).json()['id'];self.provider.error='provider_rate_limit';self.worker.run_once()
        first=self.client.get(self.url+'/'+identity).json()
        self.assertEqual(first['error_code'],'provider_rate_limit');self.assertIsNone(first['generation']['cost_usd'])
        self.assertEqual(first['generation']['billing_status'],'unknown')
        retry_url=self.url+'/'+identity+'/retry'
        retry=self.client.post(retry_url,json={'idempotency_key':'retry-1'})
        self.assertEqual(retry.status_code,201,retry.text)
        self.assertEqual(self.client.post(retry_url,json={'idempotency_key':'retry-1'}).status_code,200)
        self.provider.error=None;self.worker.run_once()
        self.assertEqual(self.client.get(self.url+'/'+retry.json()['id']).json()['status'],'succeeded')
        self.assertEqual(len(self.provider.calls),2)

    def test_cancel_queued_and_inflight_discards_result_but_retains_usage(self):
        self.configure();_,claim,_=self.verified()
        first=self.enqueue(claim).json()['id']
        self.client.post(f'/api/projects/{self.project}/jobs/{first}/cancel')
        self.assertFalse(self.worker.run_once());self.assertEqual(len(self.provider.calls),0)
        second=self.enqueue(claim,'gen-2').json()['id']
        self.provider.hook=lambda:self.client.post(f'/api/projects/{self.project}/jobs/{second}/cancel')
        self.worker.run_once();job=self.client.get(self.url+'/'+second).json()
        self.assertEqual(job['status'],'cancelled');self.assertIsNone(job['result_asset_id'])
        self.assertEqual(job['generation']['cost_usd'],'0.00058')
        self.assertFalse(list((self.settings.data_dir/'assets').iterdir()))

    def test_source_change_midflight_cancels_and_retry_rechecks_review(self):
        self.configure();source,claim,_=self.verified()
        identity=self.enqueue(claim).json()['id']
        self.provider.hook=lambda:self.client.patch(self.base+'/sources/'+source['id']+'/status',json={'status':'withdrawn','reason':'Synthetic correction','expected_version':source['version']})
        self.worker.run_once();job=self.client.get(self.url+'/'+identity).json()
        self.assertEqual(job['status'],'cancelled');self.assertIsNone(job['result_asset_id'])
        self.assertEqual(self.client.post(self.url+'/'+identity+'/retry',json={'idempotency_key':'r'}).status_code,409)

    def test_queue_limit_and_legacy_queue_not_executed(self):
        self.configure();_,claim,_=self.verified()
        legacy=self.client.post(f'/api/projects/{self.project}/jobs',json={'kind':'generation','idempotency_key':'legacy','payload':{'claim_ids':[claim['id']],'content_type':'youtube_script'}})
        self.assertEqual(legacy.status_code,201)
        self.assertFalse(self.worker.run_once())
        for key in ['a','b','c']:self.assertEqual(self.enqueue(claim,key).status_code,201)
        self.assertEqual(self.enqueue(claim,'d').status_code,429)

    def test_archived_project_and_invalid_provider_result_never_succeed(self):
        self.configure();_,claim,_=self.verified();identity=self.enqueue(claim).json()['id']
        self.provider.generate=lambda *args:{'content':'missing usage'}
        self.worker.run_once()
        self.assertEqual(self.client.get(self.url+'/'+identity).json()['error_code'],'provider_usage_missing')
        other=self.enqueue(claim,'second').json()['id']
        with self.app.state.database.transaction(write=True) as db:
            db.execute('UPDATE projects SET archived=1 WHERE id=?',(self.project,))
        self.worker.run_once()
        self.assertEqual(self.client.get(self.url+'/'+other).json()['status'],'failed')

    def test_storage_failure_retains_provider_usage_and_has_no_result(self):
        self.configure();_,claim,_=self.verified();identity=self.enqueue(claim).json()['id']
        with patch('pathlib.Path.open',side_effect=OSError('synthetic storage failure')):
            self.worker.run_once()
        job=self.client.get(self.url+'/'+identity).json()
        self.assertEqual(job['status'],'failed');self.assertEqual(job['error_code'],'generation_storage_failed')
        self.assertEqual(job['generation']['cost_usd'],'0.00058');self.assertIsNone(job['result_asset_id'])

    def test_single_atomic_claim_and_restart_recovery(self):
        self.configure();_,claim,_=self.verified();identity=self.enqueue(claim).json()['id']
        row=self.worker.claim();self.assertEqual(row['id'],identity);self.assertIsNone(self.worker.claim())
        self.app.state.database.initialize()
        job=self.client.get(self.url+'/'+identity).json()
        self.assertEqual(job['status'],'failed');self.assertEqual(job['error_code'],'worker_interrupted')
        self.assertIsNone(job['generation']['cost_usd'])


class ProviderTests(unittest.TestCase):
    def response(self,**changes):
        result={'status':'completed','id':'r','output':[{'type':'message','content':[{'type':'output_text','text':'Draft'}]}],'usage':{'input_tokens':100,'output_tokens':50,'input_tokens_details':{'cached_tokens':20}}}
        result.update(changes);return result

    def test_response_validation_refusal_incomplete_and_usage(self):
        self.assertEqual(parse_response(self.response())['content'],'Draft')
        for data in [self.response(status='incomplete'),self.response(usage=None),self.response(output=[]),self.response(output=[{'type':'message','content':[{'type':'refusal'}]}])]:
            with self.assertRaises(ProviderError):parse_response(data)
        self.assertIsNone(calculate_cost(None,('1','1','1')))
        self.assertIsNone(calculate_cost({'input_tokens':1,'cached_tokens':0,'output_tokens':1},None))

    def test_transport_fixed_host_no_store_limits_and_no_error_leaks(self):
        provider=OpenAIProvider(GenerationConfig(True,'secret-never-print','test-model',256,5))
        payload={'content_type':'news_article','depth':1,'audio_cues':False,'review_snapshot':[]}
        import httpx
        requests=[]
        def handler(request):
            requests.append(request)
            return httpx.Response(200,json=self.response())
        original=httpx.AsyncClient
        with patch('app.backend.generation_provider.httpx.AsyncClient',side_effect=lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs)):
            provider.generate(payload,'test-model',256)
        request=requests[0];body=json.loads(request.content)
        self.assertEqual(str(request.url),'https://api.openai.com/v1/responses')
        self.assertFalse(body['store']);self.assertEqual(body['max_output_tokens'],256)
        self.assertNotIn('secret-never-print',json.dumps(body))
        with patch('app.backend.generation_provider.httpx.AsyncClient',side_effect=lambda **kwargs:original(transport=httpx.MockTransport(lambda req:httpx.Response(429,text='secret-never-print')),**kwargs)):
            with self.assertRaisesRegex(ProviderError,'^provider_rate_limit$'):provider.generate(payload,'test-model',256)

    def test_config_validation_secret_repr_and_total_deadline(self):
        import asyncio, os
        with patch.dict(os.environ,{'STUDIO_INPUT_USD_PER_MILLION':'NaN','STUDIO_CACHED_INPUT_USD_PER_MILLION':'1','STUDIO_OUTPUT_USD_PER_MILLION':'1'}):
            with self.assertRaises(ValueError):GenerationConfig.from_env()
        self.assertNotIn('secret-never-print',repr(GenerationConfig(True,'secret-never-print','model')))
        provider=OpenAIProvider(GenerationConfig(True,'qa','model',256,5))
        async def expired(awaitable,timeout):
            awaitable.close()
            raise TimeoutError()
        with patch('app.backend.generation_provider.asyncio.wait_for',side_effect=expired):
            with self.assertRaisesRegex(ProviderError,'^provider_timeout$'):
                provider.generate({'content_type':'news_article','depth':1,'audio_cues':False,'review_snapshot':[]},'model',256)
