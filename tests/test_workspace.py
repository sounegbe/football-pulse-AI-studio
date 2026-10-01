import unittest
from tests import test_api

class WorkspaceContractTests(unittest.TestCase):
    setUp = test_api.BaselineTests.setUp
    # The separate M1 suite covers the backwards-compatible contract.
    def test_workspace_options(self):
        for depth in (1,2,3):
            for cues in (True,False):
                response=self.client.post('/api/generate',json={'news':' Test notes ','content_type':'social_post','depth':depth,'audio_cues':cues})
                self.assertEqual(response.status_code,200)
                self.assertEqual(response.json()['depth'],depth)
                self.assertEqual(response.json()['audio_cues'],cues)
                self.assertEqual(response.json()['mode'],'stub')
        for extra in ({'depth':0},{'depth':4},{'depth':True},{'depth':'2'},{'audio_cues':'false'},{'audio_cues':1}):
            self.assertEqual(self.client.post('/api/generate',json={'news':'notes','content_type':'youtube_script',**extra}).status_code,422)

    def test_workspace_pages_are_real_and_have_no_fake_outputs(self):
        for path in ('/','/workspace/mobile-original'):
            response=self.client.get(path)
            self.assertEqual(response.status_code,200)
            self.assertIn('/static/css/workspace.css',response.text)
            self.assertIn('Test response only.',response.text)
            self.assertNotIn('cdn.tailwindcss.com',response.text)
            self.assertNotIn('Generated via Gemini',response.text)
            self.assertIn('value="social_post"',response.text)
        self.assertEqual(self.client.get('/legacy').status_code,200)

from tests import test_research

class ReviewedWorkspaceJobTests(unittest.TestCase):
    setUp = test_research.ResearchTests.setUp

    def test_selected_options_are_saved_only_with_verified_claims(self):
        research = test_research.ResearchTests
        source = research.source(self)
        claim = research.claim(self)
        self.assertEqual(research.generation(self,claim,extra={'depth':1,'audio_cues':False}).status_code,409)
        research.evidence(self,claim,source)
        self.assertEqual(research.review(self,claim).status_code,200)
        job = research.generation(self,claim,extra={'depth':1,'audio_cues':False})
        self.assertEqual(job.status_code,201)
        self.assertEqual(job.json()['payload']['depth'],1)
        self.assertFalse(job.json()['payload']['audio_cues'])
        for extra in ({'depth':4},{'depth':True},{'audio_cues':'true'}):
            self.assertEqual(research.generation(self,claim,key='invalid-options',extra=extra).status_code,422)
