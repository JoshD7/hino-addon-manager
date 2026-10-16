import unittest
import hino_selfupdate as updater

class AppVersionTests(unittest.TestCase):
    def test_version_bumped(self):
        self.assertEqual(updater.APP_VERSION, '4.0.3')

    def test_only_newer_release(self):
        base = f'https://github.com/{updater.REPOSITORY}/releases/download/v4.0.2/'
        release = {
            'tag_name': 'v4.0.2',
            'assets': [
                {'name': name, 'browser_download_url': base + name}
                for name in (updater.SETUP_NAME, updater.HASH_NAME)
            ],
        }
        self.assertEqual(updater.select_update(release, current='4.0.1')['version'], '4.0.2')
        self.assertIsNone(updater.select_update(dict(release, tag_name='v4.0.1')))

if __name__ == '__main__':
    unittest.main()
