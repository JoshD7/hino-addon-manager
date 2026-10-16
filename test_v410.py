import unittest
import HinoAddonManager as h

class CurseForgeReleaseLinkTests(unittest.TestCase):
    def test_official_file_page(self):
        mod={'links':{'websiteUrl':'https://www.curseforge.com/wow/addons/polestar-guides'}}
        self.assertEqual(h.cf_official_url(mod,{'id':123456}),
            'https://www.curseforge.com/wow/addons/polestar-guides/files/123456')

    def test_refuses_untrusted_host(self):
        for site in ('https://curseforge.com.evil.example/wow/addons/test',
                     'http://www.curseforge.com/wow/addons/test',
                     'https://www.curseforge.com/other/test'):
            with self.subTest(site=site), self.assertRaises(ValueError):
                h.cf_official_url({'links':{'websiteUrl':site}}, {'id':123})

    def test_needs_file_id(self):
        with self.assertRaises(ValueError):
            h.cf_official_url({'links':{'websiteUrl':'https://www.curseforge.com/wow/addons/polestar-guides'}}, {'id':'invalid'})

if __name__ == '__main__':
    unittest.main()
