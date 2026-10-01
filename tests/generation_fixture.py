"""QA-only provider. Never used by main:app; every result is explicitly synthetic."""
import time
from pathlib import Path
from app.backend.config import ROOT
from app.backend.generation_provider import ProviderError, GeminiProvider
import json

class QAGenerationProvider:
    is_test=True
    def generate(self,payload,model,maximum):
        path=ROOT/'.qa-generation'
        scenario=path.read_text().strip() if path.exists() else 'normal'
        for _ in range(30 if scenario=='slow' else 4):time.sleep(.2)
        if scenario=='rate_limit':raise ProviderError('provider_rate_limit')
        if scenario=='timeout':raise ProviderError('provider_timeout')
        if scenario=='invalid':raise ProviderError('provider_invalid_response')
        return {'content':'## QA synthetic opening\nThis is a controlled provider fixture, not live OpenAI output. Synthetic United won 2–1.\n\n## QA synthetic closing\nThe draft still needs human review. <img onerror=alert(1)> stays literal.\n', 'response_id':'qa-synthetic-response', 'usage':{'input_tokens':120,'cached_tokens':20,'output_tokens':70}}


class QAGeminiProvider(GeminiProvider):
    """Exercises Gemini request construction/parsing without external requests."""
    is_test = True

    def _send(self, endpoint, body, headers, parser):
        request = json.loads(body)
        assert endpoint.startswith('https://generativelanguage.googleapis.com/v1beta/models/')
        assert request['generationConfig']['candidateCount'] == 1
        fixture = QAGenerationProvider().generate({}, '', 0)
        return parser({'responseId': 'qa-gemini-synthetic-response',
                       'candidates': [{'finishReason': 'STOP', 'content': {'parts': [
                           {'text': fixture['content'].replace('not live OpenAI output', 'not live Gemini output')}]}}],
                       'usageMetadata': {'promptTokenCount': 120, 'cachedContentTokenCount': 20,
                                         'candidatesTokenCount': 70}})
