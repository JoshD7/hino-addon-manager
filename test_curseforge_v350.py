import io,json,unittest
from unittest.mock import Mock
import HinoAddonManager as h
class API(unittest.TestCase):
 def mock_open(self, data):
  resp=Mock();resp.read.return_value=json.dumps({'data':data}).encode();resp.__enter__=Mock(return_value=resp);resp.__exit__=Mock(return_value=False)
  return Mock(return_value=resp)
 def test_search(self):
  opener=self.mock_open([{'id':42,'name':'Test','slug':'test'}])
  with unittest.mock.patch.object(h,'cf_request',return_value=[{'id':42,'name':'Test','slug':'test'}]) as request:
   result=h.cf_search('testkey','Polestar')
  self.assertEqual(result[0]['id'],42)
  self.assertEqual(request.call_args[0][0],'testkey')
 def test_version_label(self):
  self.assertTrue(h.cf_forever_evidence({'versions':['WoW Forever 1.60.1']}))
  self.assertFalse(h.cf_forever_evidence({'versions':['Retail 11.0.0']}))
 def test_key_required(self):
  with self.assertRaises(ValueError):h.cf_request('','/games/1')
 def test_bad_path(self):
  with self.assertRaises(ValueError):h.cf_request('x','/../other')
if __name__=='__main__':unittest.main()
