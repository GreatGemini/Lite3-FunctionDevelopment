import json
import os
import site
import sys
import tempfile
import unittest
from pathlib import Path
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = Path(__file__).resolve().parents[1]
site.addsitedir(str(ROOT/'vendor'))
sys.path.insert(0,str(ROOT))
from PySide6.QtWidgets import QApplication
from rover.inspection_ui import InspectionPanel
from rover.inspection import InspectionError


class ReadOnlyRuntime:
    def camera_frame(self): return None,0,''


class InspectionUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.panel = InspectionPanel(ReadOnlyRuntime(), self.temp.name)
    def tearDown(self):
        self.panel.shutdown()
        self.panel.close()
        self.temp.cleanup()
    def test_consent_and_key_required_settings_never_contain_secret(self):
        self.panel.key.setText('test-secret')
        with self.assertRaises(InspectionError): self.panel.credentials()
        self.panel.consent.setChecked(True)
        key, model = self.panel.credentials()
        self.assertEqual(key,'test-secret')
        content = Path(self.temp.name,'inspection-settings.json').read_text(encoding='utf-8')
        self.assertNotIn('test-secret',content)
        self.assertEqual(set(json.loads(content)),{'model','interval','limit'})
    def test_idle_controls_and_cancel_controls(self):
        self.assertTrue(self.panel.start_button.isEnabled())
        self.assertFalse(self.panel.finish_button.isEnabled())
        self.assertFalse(self.panel.export_button.isEnabled())
        self.panel.session._set('capturing','test')
        self.panel.refresh()
        self.assertFalse(self.panel.start_button.isEnabled())
        self.assertTrue(self.panel.finish_button.isEnabled())
        self.panel.cancel()
        self.assertTrue(self.panel.start_button.isEnabled())
    def test_shutdown_clears_key(self):
        self.panel.key.setText('test-secret')
        self.panel.shutdown()
        self.assertEqual(self.panel.key.text(),'')


if __name__ == '__main__': unittest.main()
