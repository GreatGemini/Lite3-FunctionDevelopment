import os,sys,site,unittest,struct,tempfile
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];site.addsitedir(str(ROOT/'vendor'));sys.path.insert(0,str(ROOT/'vendor'));sys.path.insert(0,str(ROOT))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEvent
from PySide6.QtGui import QFontDatabase
from rover.adapters import Runtime
from rover.motion import MotionController,AXES
from rover.ui import MainWindow
class Bridge:
    state='test';detail='loopback only'
    def stop(self):pass
    def config(self):return {}
class MotionUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        for f in ('msyh.ttc','msyhbd.ttc','segoeui.ttf'):
            QFontDatabase.addApplicationFont(str(Path(os.environ['WINDIR'])/'Fonts'/f))
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.sent=[]
        self.r=Runtime(ROOT/'known_hosts');self.r.store.update({'basic':98},'test')
        self.r.motion=MotionController({},self.r.store,send=self.sent.append)
        profile={'name':'UI test','adapter':'lite3','robot_ip':'127.0.0.1','listen_ip':'127.0.0.1','listen_port':43897,'ssh_user':'test','camera_url':'rtsp://127.0.0.1/test'}
        self.w=MainWindow(self.r,Bridge(),self.tmp.name,[profile]);self.w.show();self.app.processEvents()
    def tearDown(self):
        self.w.close();self.app.processEvents();self.tmp.cleanup()
    def test_arm_hold_release_focus_loss(self):
        self.assertEqual(self.sent,[])
        self.w.pose_choice.setCurrentIndex(2);self.w.arm_box.setChecked(True);self.w.refresh()
        self.assertTrue(self.r.motion.armed)
        b=self.w.motion_buttons['forward'];self.assertTrue(b.isEnabled())
        b.setDown(True);b.pressed.emit();self.assertEqual(self.r.motion.direction,'forward')
        b.setDown(False);b.released.emit();self.assertIsNone(self.r.motion.direction)
        self.w.eventFilter(self.app,QEvent(QEvent.ApplicationDeactivate))
        self.assertFalse(self.r.motion.armed);self.assertIsNone(self.r.motion.observed)
        self.assertTrue(all(v==0 for k,v,t in [struct.unpack('<III',p) for p in self.sent] if k in AXES))
    def test_pose_display_follows_fresh_telemetry(self):
        for code,text in [(1,'趴下'),(6,'站立'),(9,'站立')]:
            self.r.store.update({'basic':code},'test');self.w.refresh()
            self.assertTrue(self.w.pose_choice.isHidden())
            self.assertEqual(self.w.pose_auto.text(),'自动识别：'+text)
            self.assertEqual(self.r.motion._posture(),{1:'sit',6:'stand',9:'stand'}[code])
        self.r.store.update({'basic':98},'test');self.w.refresh()
        self.assertFalse(self.w.pose_choice.isHidden())
        self.w.pose_choice.setCurrentIndex(2)
        self.assertEqual(self.r.motion._posture(),'stand')
        self.r.store.values['basic']['updated_at']-=2;self.w.refresh()
        self.assertTrue(self.w.pose_choice.isHidden())
        self.assertIn('等待',self.w.pose_auto.text())
        self.r.store.update({'basic':8},'test');self.w.refresh()
        self.assertTrue(self.w.pose_choice.isHidden())
        self.assertIn('无法识别',self.w.pose_auto.text())
        self.assertEqual(self.sent,[])
    def test_speed_slider_updates_without_motion_and_resets_on_disconnect(self):
        self.w.refresh();self.w.speed_slider.setValue(3)
        self.assertEqual(self.r.motion.speed_level,3);self.assertEqual(self.sent,[])
        self.w.disconnect_robot();self.w.refresh()
        self.assertEqual(self.w.speed_slider.value(),1)
        self.assertFalse(self.w.speed_slider.isEnabled())
    def test_unknown_pose_and_ui_arm_not_automatic(self):
        self.w.arm_box.setChecked(True);self.w.refresh()
        self.w.motion_buttons['stand'].click()
        self.assertFalse(any(struct.unpack('<III',p)[0]==0x21010202 for p in self.sent))
        self.w.grab().save(str(ROOT/'qa-motion-ui.png'))
if __name__=='__main__':unittest.main()
