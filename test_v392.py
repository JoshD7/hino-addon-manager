import unittest
from unittest.mock import patch
import HinoAddonManager as h
class NewReleaseTests(unittest.TestCase):
 def test_non_windows_read_is_empty(self):
  with patch.object(h.sys,'platform','linux'):self.assertEqual(h.load_cf_credential(),'')
 def test_non_windows_write_rejected(self):
  with patch.object(h.sys,'platform','linux'):
   with self.assertRaises(RuntimeError):h.save_cf_credential('dummy')
 def test_target_is_private_app_namespace(self):
  self.assertEqual(h.CF_CREDENTIAL_TARGET,'HinoAddonManager/CurseForgeAPI/v1')
if __name__=='__main__':unittest.main()
