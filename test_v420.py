import unittest
import HinoAddonManager as h

class SaferDetectionV420(unittest.TestCase):
    def test_real_github_metadata(self):
        self.assertEqual(h.source_from_metadata({'source':'https://github.com/Questie/Questie'}),'Questie/Questie')
        self.assertEqual(h.source_from_metadata({'source':'https://github.com/Questie/Questie.git'}),'Questie/Questie')

    def test_lookalike_github_host_rejected(self):
        for url in ('https://github.com.evil.example/Questie/Questie',
                    'https://notgithub.com/Questie/Questie',
                    'https://other.example/?u=github.com/Questie/Questie',
                    'https://github.com@evil.example/Questie/Questie'):
            with self.subTest(url=url):
                self.assertIsNone(h.source_from_metadata({'source':url}))

    def test_generic_asset_requires_unambiguous_tag(self):
        item={'name':'Example','version':'1.2.0'}
        release={'tag':'v1.3.0','assets':[{'name':'Example.zip','browser_download_url':'https://example.com/Example.zip'}]}
        self.assertIsNotNone(h.candidate_github_asset(item,release))
        for tag in ('v1.3.0+v9.0.0','v1.60.1-example-1.3.0','nightly-2026-10-17','v1.2.0'):
            with self.subTest(tag=tag):
                self.assertIsNone(h.candidate_github_asset(item,dict(release,tag=tag)))

    def test_multiple_assets_unverified(self):
        item={'name':'Example','version':'1.2.0'}
        assets=[{'name':x,'browser_download_url':'https://example.com/'+x} for x in ('Retail.zip','Forever.zip')]
        self.assertIsNone(h.candidate_github_asset(item,{'tag':'1.3.0','assets':assets}))

if __name__=='__main__':
    unittest.main()
