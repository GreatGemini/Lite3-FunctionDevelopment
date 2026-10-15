from test_motion import MotionTests
from rover.motion import HEARTBEAT,VOICE,AXES,MotionError

class ControlSessionTests(MotionTests):
    def test_focus_locks_input_but_keeps_heartbeat(self):
        self.c.arm();self.c.begin('forward');self.c.lock_input('focus');self.sent.clear()
        self.now+=.3;self.c.tick()
        self.assertFalse(self.c.armed);self.assertTrue(self.c.session_active)
        self.assertIn((HEARTBEAT,0,0),self.decoded())
        self.assertTrue(all(v==0 for k,v,t in self.decoded() if k in AXES))
    def test_focus_does_not_interrupt_discrete_action(self):
        self.c.arm();self.c.text_command(8);self.sent.clear();self.c.lock_input('focus')
        self.now+=.3;self.c.tick()
        self.assertEqual(self.c.voice_active,8)
        self.assertNotIn((VOICE,7,0),self.decoded())
        self.assertIn((HEARTBEAT,0,0),self.decoded())
        with self.assertRaises(MotionError):self.c.text_command(9)
    def test_focus_stops_translation(self):
        self.c.arm();self.c.text_command(3);self.sent.clear();self.c.lock_input('focus')
        self.assertIn((VOICE,7,0),self.decoded());self.assertIsNone(self.c.voice_active)
    def test_stand_completion_without_injected_stop(self):
        self.store.update({'basic':1},'test');self.c.arm();self.c.text_command(1);self.sent.clear()
        self.store.update({'basic':6},'test');self.now+=1;self.c.tick();self.now+=.4;self.c.tick()
        self.assertIsNone(self.c.voice_active);self.assertNotIn((VOICE,7,0),self.decoded())
    def test_unknown_action_times_out_and_locks_but_retains_heartbeat(self):
        self.c.arm();self.c.text_command(13);self.sent.clear()
        self.now+=10.1;self.c.tick();self.assertNotIn((VOICE,7,0),self.decoded())
        self.now+=5;self.c.tick();self.assertIn((VOICE,7,0),self.decoded())
        self.assertFalse(self.c.armed);self.assertTrue(self.c.session_active)
    def test_close_stops_then_ends_session(self):
        self.c.arm();self.c.text_command(8);self.sent.clear();self.c.close()
        self.assertIn((VOICE,7,0),self.decoded());self.assertFalse(self.c.session_active)
        self.sent.clear();self.c.tick();self.assertEqual(self.sent,[])
    def test_protection_keeps_connection_not_motion(self):
        self.c.arm();self.store.update({'basic':8},'test');self.c.tick();self.sent.clear()
        self.now+=.3;self.c.tick();self.assertEqual(self.decoded(),[(HEARTBEAT,0,0)])
        self.assertFalse(self.c.armed)
