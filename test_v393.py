import unittest
import HinoAddonManager as h
class CurseForgeUpdateTests(unittest.TestCase):
    def test_grouped_polestar_project(self):
        self.assertEqual(h.cf_project_for({'name':'Polestar','curse_project_id':''}), '1744437')
        self.assertEqual(h.cf_project_for({'name':'PolestarQuestDatabase','curse_project_id':''}), '1744437')
    def test_toc_project(self):
        self.assertEqual(h.cf_project_for({'name':'SampleAddon','curse_project_id':'1234'}),'1234')
    def test_unknown_is_not_guessed(self):
        self.assertIsNone(h.cf_project_for({'name':'OtherAddon','curse_project_id':''}))
    def test_update_metadata(self):
        self.assertEqual(h.cf_release_status('0.2.3',[{'name':'Polestar-0.2.4.zip','versions':['1.60.1']}])[0],'Update available')
    def test_retail_is_not_eligible(self):
        self.assertEqual(h.cf_release_status('1.0.0',[{'name':'Demo-9.0.0.zip','versions':['12.0.0']}])[0],'No compatible release')
    def test_unknown_version(self):
        self.assertEqual(h.cf_release_status('Unknown',[{'name':'Demo-2.0.0.zip','versions':['1.60.1']}])[0],'Version unverified')
    def test_no_misread_client_version(self):
        self.assertEqual(h.cf_file_version({'name':'Addon_FOREVER_1.60.1.zip'}),())
    def test_release_status_is_not_install_authority(self):
        self.assertEqual(h.simple_status('No compatible release'),'No Forever release')
if __name__=='__main__':unittest.main()
