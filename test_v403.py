"""V4.0.3 release detection checks without contacting GitHub."""
import unittest
import hino_selfupdate as updater

class V403ReleaseTests(unittest.TestCase):
    def test_expected_app_version(self):
        self.assertEqual(updater.APP_VERSION, '4.2.0')

    def test_v402_will_detect_v403(self):
        tag = 'v4.0.3'
        url = f'https://github.com/{updater.REPOSITORY}/releases/download/{tag}/'
        release = {
            'tag_name': tag,
            'draft': False,
            'prerelease': False,
            'assets': [
                {'name': name, 'browser_download_url': url + name}
                for name in (updater.SETUP_NAME, updater.HASH_NAME)
            ]
        }
        found = updater.select_update(release, current='4.0.2')
        self.assertIsNotNone(found)
        self.assertEqual(found['version'], '4.0.3')
        self.assertIsNone(updater.select_update(release, current='4.0.3'))
        self.assertIsNone(updater.select_update(dict(release, draft=True), current='4.0.2'))

if __name__ == '__main__':
    unittest.main()
