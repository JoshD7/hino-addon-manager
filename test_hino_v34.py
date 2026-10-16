import tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import HinoAddonManager as h

class SourceTests(unittest.TestCase):
 def test_toc_metadata(self):
  with tempfile.TemporaryDirectory() as d:
   folder=Path(d)/'Demo';folder.mkdir()
   (folder/'Demo.toc').write_text('## Title: Demo\n## Version: 1.2.3\n## X-Wago-ID: AbCd12\n## Interface: 16001\n')
   item=h.toc_info(folder)
   self.assertEqual(item['toc_files'],['Demo.toc'])
   self.assertEqual(h.identify_source(item,{})['provider'],'wago')
 def test_no_false_current(self):
  item={'name':'Demo','version':'1.0.0'}
  self.assertEqual(h.classify(item,{'tag':'1.0.0','assets':[]})[0],'Compatibility unverified')
 def test_project_id(self):
  self.assertEqual(h.identify_source({'name':'Demo','curse_project_id':'12345'}, {})['provider'],'curseforge')

class PackageTests(unittest.TestCase):
 def test_groups(self):
  items=[{'name':x} for x in ['Bagnon','BagBrother','Bagnon_Bank','GearQuestForever','GearQuestForever_HUNTER','Questie','QuestieDB','Auctionator']]
  groups=h.package_groups(items)
  self.assertEqual(len(groups),4)
  self.assertEqual(len(groups['Bagnon family']),3)
  self.assertEqual(len(groups['GearQuest Forever']),2)
 def test_package_status(self):
  self.assertEqual(h.package_status(['Up to date','Not checked online']),'Not checked / unverified')
  self.assertEqual(h.package_status(['Up to date','Up to date']),'Up to date')
 def test_interface_summary(self):
  self.assertEqual(h.interface_summary('120100, 16001, 50504'),'120100 (+2)')

if __name__=='__main__':unittest.main()
