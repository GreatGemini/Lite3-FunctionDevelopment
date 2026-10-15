"""UI changes are checked using a mock sender; never move a real robot."""
import struct
from unittest.mock import patch
import test_motion_ui
from rover.motion import AXES


class UpdatedControlTests(test_motion_ui.MotionUITests):
    def test_ssh_success_locks_field_and_disconnect_unlocks(self):
        self.w.password.setText('test-secret')
        self.r.store.link('SSH','在线')
        self.w.refresh()
        self.assertFalse(self.w.password.isEnabled())
        self.assertEqual(self.w.password.text(),'SSH已连接')
        self.assertFalse(self.w.show_password.isEnabled())
        self.w.disconnect_robot()
        self.assertTrue(self.w.password.isEnabled())
        self.assertEqual(self.w.password.text(),'')
        self.assertTrue(self.w.show_password.isEnabled())

    def test_authentication_failure_unlocks_and_does_not_clear_retry_input(self):
        self.w.update_ssh_input('连接中')
        self.assertFalse(self.w.password.isEnabled())
        self.r.store.link('SSH','认证失败')
        self.w.refresh()
        self.assertTrue(self.w.password.isEnabled())
        self.assertEqual(self.w.password.text(),'')
        self.w.password.setText('new-secret')
        self.w.refresh()
        self.assertEqual(self.w.password.text(),'new-secret')

    def test_click_connect_when_ssh_online_does_not_submit_status_text(self):
        self.w.update_ssh_input('在线')
        with patch.object(self.r,'connect') as connect:
            self.w.connect_robot()
            connect.assert_not_called()

    def test_icon_hold_release_and_tab_change_stop(self):
        self.r.store.update({'basic':6},'test')
        self.w.arm_box.setChecked(True)
        self.w.refresh()
        self.assertEqual(self.w.motion_tabs.count(),2)
        self.w.motion_tabs.setCurrentIndex(1)
        for direction, button in self.w.icon_motion_buttons.items():
            self.assertTrue(button.isEnabled())
            button.setDown(True)
            button.pressed.emit()
            self.assertEqual(self.r.motion.direction,direction)
            button.setDown(False)
            button.released.emit()
            self.assertIsNone(self.r.motion.direction)
        button=self.w.icon_motion_buttons['forward']
        button.setDown(True)
        button.pressed.emit()
        self.sent.clear()
        self.w.motion_tabs.setCurrentIndex(0)
        self.assertIsNone(self.r.motion.direction)
        self.assertIsNone(self.w.hold_button)
        self.assertFalse(button.isDown())
        self.assertTrue(all(value==0 for code,value,kind in map(lambda data:struct.unpack('<III',data),self.sent) if code in AXES))
        self.assertTrue(self.r.motion.armed)

    def test_both_button_sets_follow_same_arm_state(self):
        self.w.refresh()
        self.assertTrue(all(not b.isEnabled() for b in self.w.icon_motion_buttons.values()))
        self.r.store.update({'basic':6},'test')
        self.w.arm_box.setChecked(True)
        self.w.refresh()
        self.assertTrue(all(b.isEnabled() for b in self.w.icon_motion_buttons.values()))
        self.w.lock_motion('测试失焦',focus_only=True)
        self.w.refresh()
        self.assertTrue(all(not b.isEnabled() for b in self.w.icon_motion_buttons.values()))
        self.assertTrue(all(not b.isEnabled() for b in self.w.motion_buttons.values()))
