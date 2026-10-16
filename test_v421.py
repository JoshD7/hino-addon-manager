"""Validate app version marker and installer/helper packaging."""
import unittest
from pathlib import Path
import hino_selfupdate as updater

ROOT=Path(__file__).resolve().parent

class V421VersionVerification(unittest.TestCase):
    def test_version_marker_matches_application(self):
        self.assertEqual((ROOT/'HinoAddonManager.version').read_text(encoding='utf-8').strip(),updater.APP_VERSION)

    def test_installer_packages_version_marker(self):
        iss=(ROOT/'HinoAddonManager.iss').read_text(encoding='utf-8')
        self.assertIn('Source: "HinoAddonManager.version"; DestDir: "{app}"',iss)
        self.assertIn('#define AppVersion "'+updater.APP_VERSION+'"',iss)

    def test_helper_does_not_require_uninstall_registry(self):
        helper=(ROOT/'HinoUpdateHelper.ps1').read_text(encoding='utf-8')
        self.assertIn("'HinoAddonManager.version'",helper)
        self.assertIn('$actual -ne $ExpectedVersion',helper)
        self.assertNotIn('Windows\\CurrentVersion\\Uninstall',helper)

if __name__=='__main__':
    unittest.main()
