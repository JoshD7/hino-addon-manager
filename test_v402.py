import unittest
from pathlib import Path
from unittest.mock import patch
import hino_selfupdate as updater

class UpdaterHandoffTests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(updater.APP_VERSION, '4.2.1')

    def test_reject_invalid_version(self):
        with patch.object(updater.sys, 'platform', 'win32'):
            with self.assertRaises(ValueError):
                updater.run_installer(Path('setup.exe'), '../bad')

    def test_helper_handoff_arguments(self):
        script = Path(__file__).with_name('HinoUpdateHelper.ps1')
        with patch.object(updater.sys, 'platform', 'win32'), patch.object(updater, 'helper_path', return_value=script), patch.object(updater.subprocess, 'Popen') as popen:
            with patch.object(updater.sys, 'executable', str(Path(__file__).with_name('HinoAddonManager.exe'))):
                updater.run_installer(Path(__file__), '4.0.3')
        argv = popen.call_args.args[0]
        self.assertIn('-ParentPid', argv)
        self.assertEqual(argv[argv.index('-ExpectedVersion') + 1], '4.0.3')
        self.assertEqual(argv[argv.index('-File') + 1], str(script))
