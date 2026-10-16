import unittest
from types import SimpleNamespace
from unittest.mock import Mock
import HinoAddonManager as h
class ReleaseActions(unittest.TestCase):
 def manager(self):
  obj=h.GUI.__new__(h.GUI)
  obj.cfg={'sources':{'Questie':'Questie/Questie'}}
  obj.results={'Questie':{'status':'Update available','asset':{'name':'Questie.zip'},'release':{'tag':'v12.1.0+v1.0.6'}},'Polestar':{'status':'Update available','cf_metadata_only':True,'latest_cf_file':{'name':'Polestar-0.2.4.zip','versions':['1.60.1']}}}
  return obj
 def test_installable(self):
  obj=self.manager();self.assertTrue(obj.can_install_update({'name':'Questie'}));self.assertFalse(obj.can_install_update({'name':'Polestar'}))
 def test_labels(self):
  obj=self.manager();self.assertEqual(obj.visible_update_status({'name':'Polestar'}),'New version · manual');self.assertEqual(obj.visible_update_status({'name':'Questie'}),'Ready to update')
 def test_latest(self):
  obj=self.manager();self.assertEqual(obj.latest_display({'name':'Polestar'}),'0.2.4');self.assertEqual(obj.latest_display({'name':'Questie'}),'12.1.0')
 def test_action(self):
  obj=self.manager();obj.update_all=Mock();obj.update_selected_row({'name':'Questie'});obj.update_all.assert_called_once_with({'Questie','QuestieDB'})
if __name__=='__main__':unittest.main()
