import unittest
from pathlib import Path
import hino_selfupdate as updater

class LayoutV422Tests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(updater.APP_VERSION, '4.2.2')

    def test_layout_features_in_source(self):
        source=(Path(__file__).parent/'HinoAddonManager.py').read_text(encoding='utf-8')
        for feature in ("self._startup_maximized", "def close_window(self)", "def fit_addon_columns(self", "settings_canvas=tk.Canvas", "settings_canvas.yview_scroll", "tablebox.bind('<Configure>',self.fit_addon_columns)"):
            with self.subTest(feature=feature):
                self.assertIn(feature, source)

    def test_version_files_match(self):
        folder=Path(__file__).parent
        self.assertEqual((folder/'HinoAddonManager.version').read_text(encoding='utf-8').strip(),updater.APP_VERSION)

if __name__=='__main__':
    unittest.main()
