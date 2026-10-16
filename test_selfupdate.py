import unittest
import hino_selfupdate as u

class SelfUpdateTests(unittest.TestCase):
 def test_versions(self):
  self.assertEqual(u.parsed_version('v4.0.1'), (4,0,1))
  self.assertIsNone(u.parsed_version('v4.0.1-beta'))
 def test_assets_required(self):
  self.assertIsNone(u.select_update({'tag_name':'v4.0.2','assets':[]}))
 def test_matching_release(self):
  p=f'https://github.com/{u.REPOSITORY}/releases/download/v4.0.2/'
  data={'tag_name':'v4.0.2','assets':[{'name':n,'browser_download_url':p+n} for n in (u.SETUP_NAME,u.HASH_NAME)]}
  self.assertEqual(u.select_update(data)['version'],'4.0.2')
  self.assertIsNone(u.select_update(data,current='4.1.0'))
 def test_checksum(self):
  self.assertEqual(u.parse_checksum(('a'*64+'  '+u.SETUP_NAME).encode()),'a'*64)
  with self.assertRaises(ValueError):u.parse_checksum(b'not a checksum')
