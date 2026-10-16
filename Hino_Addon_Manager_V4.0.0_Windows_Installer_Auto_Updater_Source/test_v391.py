import unittest
import HinoAddonManager as h
class PolestarTests(unittest.TestCase):
 def test_group_all_modules(self):
  modules=['Polestar','Polestar_Codex','PolestarGuides','PolestarItemData','PolestarQuestDatabase']
  self.assertEqual(set(h.package_groups([{'name':m} for m in modules])),{'Polestar Guides'})
 def test_other_projects_unchanged(self):
  self.assertEqual(h.addon_group({'name':'Questie'}),'Questie + QuestieDB')
  self.assertEqual(h.addon_group({'name':'PolestarOther'}),'PolestarOther')
 def test_known_identity_not_download_permission(self):
  meta=h.declared_provider({'name':'Polestar','curse_project_id':''},{})
  self.assertEqual(meta['project_id'],'1744437')
  self.assertFalse(meta['download_authorized'])
 def test_unchanged_unverified_status(self):
  self.assertEqual(h.simple_status('Compatibility unverified'),'Check required')
  self.assertEqual(h.simple_status('Update available'),'Update available')
if __name__=='__main__':unittest.main()
