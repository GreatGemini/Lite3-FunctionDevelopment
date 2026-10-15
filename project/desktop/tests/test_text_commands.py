import struct
from test_motion import MotionTests
from test_motion_ui import MotionUITests
from rover.motion import VOICE,MotionError
from rover.text_commands import COMMANDS,parse_command

class TextControllerTests(MotionTests):
    def test_all_documented_commands(self):
        expected=[1,2,3,4,5,6,7,8,9,11,12,13,14,15,22]
        self.assertEqual(list(COMMANDS.values()),expected)
        for name,value in COMMANDS.items():
            self.assertEqual(parse_command(name),(name,value))
            self.c.stop();self.sent.clear()
            self.store.update({'basic':1 if value==1 else 6},'fixture')
            self.c.arm();self.c.text_command(value)
            self.assertEqual([(k,v) for k,v,t in self.decoded() if k==VOICE],[(VOICE,value)])
    def test_reject_ambiguous_and_unarmed(self):
        for text in ('不要前进','前进然后停止','22','左转','前进？',''):
            with self.assertRaises(ValueError):parse_command(text)
        with self.assertRaises(MotionError):self.c.text_command(3)
        self.assertEqual(self.sent,[])
    def test_stop_timeout_and_no_retry(self):
        self.c.arm();self.c.text_command(3);self.sent.clear()
        with self.assertRaises(MotionError):self.c.text_command(3)
        self.now+=1.1;self.c.tick()
        self.assertIn((VOICE,7,0),self.decoded());self.assertIsNone(self.c.voice_active)
        self.assertFalse(any(k==VOICE and v==3 for k,v,t in self.decoded()))
    def test_stop_on_disarm_and_stale(self):
        for stale in (False,True):
            self.store.update({'basic':6},'fixture');self.c.arm();self.c.text_command(13);self.sent.clear()
            if stale:self.store.values['basic']['updated_at']-=2;self.c.tick()
            else:self.c.disarm()
            self.assertIn((VOICE,7,0),self.decoded());self.assertFalse(self.c.armed)
    def test_stop_works_when_locked(self):
        self.c.text_command(7);self.assertIn((VOICE,7,0),self.decoded())

class TextUITests(MotionUITests):
    def test_fill_does_not_execute_and_explicit_execute(self):
        self.w.set_command_text('打招呼');self.assertEqual(self.sent,[])
        self.assertFalse(self.w.microphone_button.isEnabled())
        self.r.store.update({'basic':6},'test');self.w.arm_box.setChecked(True)
        self.w.execute_text_command()
        self.assertIn((VOICE,22,0),[struct.unpack('<III',p) for p in self.sent])
        self.w.stop_text_command()
        self.assertIn((VOICE,7,0),[struct.unpack('<III',p) for p in self.sent])
