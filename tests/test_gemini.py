import json
import os
import unittest
from unittest.mock import patch
import httpx
from app.backend.generation_provider import GenerationConfig, GeminiProvider, ProviderError, parse_gemini_response
from tests import test_generation as generation_helpers


def response():
    return {'responseId': 'synthetic-gemini-response',
            'candidates': [{'finishReason': 'STOP', 'content': {'parts': [
                {'text': 'Private thought', 'thought': True}, {'text': '## Draft\nLiteral <img>'}]}}],
            'usageMetadata': {'promptTokenCount': 100, 'candidatesTokenCount': 40,
                              'thoughtsTokenCount': 10, 'cachedContentTokenCount': 20}}


class GeminiAdapterTests(unittest.TestCase):
    def test_text_and_usage_include_thinking_without_exposing_thoughts(self):
        result = parse_gemini_response(response())
        self.assertEqual(result['content'], '## Draft\nLiteral <img>')
        self.assertEqual(result['usage'], {'input_tokens': 100, 'output_tokens': 50, 'cached_tokens': 20})

    def test_refusal_incomplete_invalid_and_missing_usage(self):
        for reason, code in [('MAX_TOKENS', 'provider_incomplete'), ('SAFETY', 'provider_refused')]:
            data = response(); data['candidates'][0]['finishReason'] = reason
            with self.assertRaises(ProviderError) as context: parse_gemini_response(data)
            self.assertEqual(context.exception.code, code)
            self.assertEqual(context.exception.usage['output_tokens'], 50)
        cases = [None, {}, {'promptFeedback': {'blockReason': 'SAFETY'}}]
        for changes in [{'usageMetadata': None}, {'usageMetadata': {'promptTokenCount': True}},
                        {'usageMetadata': {'promptTokenCount': 100, 'candidatesTokenCount': 1, 'cachedContentTokenCount': 101}},
                        {'candidates': [{'finishReason': 'STOP', 'content': {'parts': []}}]}]:
            data = response(); data.update(changes); cases.append(data)
        for data in cases:
            with self.assertRaises(ProviderError): parse_gemini_response(data)

    def test_transport_secret_header_fixed_host_and_no_retry(self):
        provider = GeminiProvider(GenerationConfig(True, 'synthetic-secret', 'gemini-test', 256, 5, provider='gemini'))
        payload = {'content_type': 'news_article', 'depth': 1, 'audio_cues': False, 'review_snapshot': []}
        requests = []; original = httpx.AsyncClient
        def handler(req): requests.append(req); return httpx.Response(200, json=response())
        with patch('app.backend.generation_provider.httpx.AsyncClient', side_effect=lambda **kw: original(transport=httpx.MockTransport(handler), **kw)):
            provider.generate(payload, 'gemini-test', 256)
        req = requests[0]
        self.assertEqual(str(req.url), 'https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent')
        self.assertEqual(req.headers['x-goog-api-key'], 'synthetic-secret')
        self.assertNotIn('synthetic-secret', req.content.decode())
        self.assertEqual(json.loads(req.content)['generationConfig']['maxOutputTokens'], 256)
        requests.clear()
        def limited(req): requests.append(req); return httpx.Response(429, text='synthetic-secret')
        with patch('app.backend.generation_provider.httpx.AsyncClient', side_effect=lambda **kw: original(transport=httpx.MockTransport(limited), **kw)):
            with self.assertRaisesRegex(ProviderError, '^provider_rate_limit$'): provider.generate(payload, 'gemini-test', 256)
        self.assertEqual(len(requests), 1)
        with self.assertRaises(ProviderError): provider.generate(payload, '../other?key=bad', 256)

    def test_config_selects_only_provider_key_and_rejects_path_model(self):
        with patch.dict(os.environ, {'STUDIO_GENERATION_PROVIDER': 'gemini', 'GEMINI_API_KEY': 'synthetic-secret',
                                    'OPENAI_API_KEY': 'other-secret', 'STUDIO_GEMINI_MODEL': 'gemini-test'}, clear=True):
            config = GenerationConfig.from_env()
            self.assertEqual((config.provider, config.api_key, config.model), ('gemini', 'synthetic-secret', 'gemini-test'))
            self.assertNotIn('synthetic-secret', repr(config))
            os.environ['STUDIO_GEMINI_MODEL'] = 'models/other'
            with self.assertRaises(ValueError): GenerationConfig.from_env()


class GeminiQueueTests(unittest.TestCase):
    setUp = generation_helpers.GenerationTests.setUp
    source = generation_helpers.GenerationTests.source
    claim = generation_helpers.GenerationTests.claim
    evidence = generation_helpers.GenerationTests.evidence
    review = generation_helpers.GenerationTests.review
    verified = generation_helpers.GenerationTests.verified
    configure = generation_helpers.GenerationTests.configure
    enqueue = generation_helpers.GenerationTests.enqueue

    def test_adapter_result_saved_through_actual_queue(self):
        self.configure(); _, claim, _ = self.verified()
        config = GenerationConfig(True, 'synthetic-key', 'gemini-test', provider='gemini')
        self.app.state.generation_config = self.worker.config = config
        self.worker.provider = GeminiProvider(config)
        job = self.enqueue(claim).json()
        original = httpx.AsyncClient
        with patch('app.backend.generation_provider.httpx.AsyncClient', side_effect=lambda **kw: original(
                transport=httpx.MockTransport(lambda req: httpx.Response(200, json=response())), **kw)):
            self.worker.run_once()
        completed = self.client.get(self.url + '/' + job['id']).json()
        self.assertEqual(completed['status'], 'succeeded')
        self.assertEqual(completed['generation']['provider'], 'gemini')
        self.assertEqual(completed['generation']['usage']['output_tokens'], 50)
        self.assertIsNone(completed['generation']['cost_usd'])
        text = self.client.get(f'/api/projects/{self.project}/assets/' + completed['result_asset_id'] + '/download').text
        self.assertIn('Literal <img>', text)
        self.assertNotIn('Private thought', text)
        self.assertEqual(self.client.get(f'/api/projects/{self.project}/draft').status_code, 404)

    def test_gemini_identity_persisted_and_config_switch_never_sends(self):
        self.configure(); _, claim, _ = self.verified()
        config = GenerationConfig(True, 'synthetic-key', 'gemini-test', provider='gemini')
        self.app.state.generation_config = self.worker.config = config
        job = self.enqueue(claim).json()
        self.assertEqual(job['generation']['provider'], 'gemini')
        self.assertEqual(self.client.get('/api/configuration').json()['generation_provider'], 'gemini')
        self.worker.config = GenerationConfig(True, 'synthetic-key', 'other-model')
        self.worker.run_once()
        failed = self.client.get(self.url + '/' + job['id']).json()
        self.assertEqual(failed['error_code'], 'provider_configuration_changed')
        self.assertEqual(self.provider.calls, [])
