import sys,site,struct,time,unittest,socket
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];site.addsitedir(str(ROOT/'vendor'));sys.path.insert(0,str(ROOT))
from rover.model import StateStore
from rover.motion import MotionController,MotionError,AXES,HEARTBEAT,TOGGLE,ESTOP,DIRECTIONS,packet,direction_values,DEAD_ZONES
class MotionTests(unittest.TestCase):
    def setUp(self):
        self.now=10.;self.sent=[];self.store=StateStore()
        self.store.update({'basic':6},'fixture',ttl=10)
        self.c=MotionController({},self.store,send=self.sent.append,clock=lambda:self.now)
    def decoded(self):return [struct.unpack('<III',p) for p in self.sent]
    def test_speed_levels_bounds_signs_and_no_send(self):
        previous={key:(0,0,0) for key in DIRECTIONS}
        for level in range(1,6):
            self.c.set_speed(level)
            for key in DIRECTIONS:
                values=direction_values(key,level)
                for i,value in enumerate(values):
                    if value:
                        self.assertGreater(abs(value),DEAD_ZONES[i])
                        self.assertLessEqual(abs(value),32767)
                        self.assertGreater(abs(value),abs(previous[key][i]))
                        self.assertEqual(value>0,DIRECTIONS[key][i]>0)
                previous[key]=values
        self.assertEqual(self.sent,[])
        for bad in (0,6,1.5,True):
            with self.assertRaises(MotionError):self.c.set_speed(bad)
    def test_speed_transmitted_and_cannot_change_while_moving(self):
        self.c.set_speed(4);self.c.arm();self.c.begin('left')
        with self.assertRaises(MotionError):self.c.set_speed(5)
        self.now+=.13;self.c.renew('left');self.sent.clear();self.c.tick()
        values={k:(v if v<2**31 else v-2**32) for k,v,t in self.decoded() if k in AXES}
        self.assertEqual(tuple(values[k] for k in AXES),direction_values('left',4))
        self.c.stop();self.sent.clear();self.c.set_speed(2);self.c.tick()
        self.assertTrue(all(v==0 for k,v,t in self.decoded() if k in AXES))
    def test_idle_and_close_are_silent(self):
        self.c.tick();self.c.close();self.assertEqual(self.sent,[])
    def test_packet_negative_axis(self):
        self.assertEqual(packet(AXES[1],-14500),struct.pack('<IiI',AXES[1],-14500,0))
    def test_arm_heartbeat_no_motion(self):
        self.c.arm();self.c.tick();self.assertEqual(self.decoded(),[(HEARTBEAT,0,0)])
    def test_all_directions_and_dead_zones(self):
        for direction,expected in DIRECTIONS.items():
            self.c.arm();self.c.begin(direction);self.now+=.13;self.c.renew(direction);self.sent.clear();self.c.tick()
            axes={code:(value if value<2**31 else value-2**32) for code,value,kind in self.decoded() if code in AXES}
            self.assertEqual(tuple(axes[k] for k in AXES),expected)
            self.c.stop()
    def test_deadman_stops_without_ui_renewal(self):
        self.c.arm();self.c.begin('forward');self.now+=.3;self.sent.clear();self.c.tick()
        self.assertIsNone(self.c.direction);self.assertTrue(all(v==0 for k,v,t in self.decoded() if k in AXES))
    def test_release_and_disarm_clear_all_axes(self):
        self.c.arm();self.c.begin('right');self.sent.clear();self.c.disarm()
        self.assertEqual(len(self.sent),9);self.assertTrue(all(v==0 for _,v,_ in self.decoded()))
        self.c.tick();self.assertFalse(self.c.armed)
    def test_stale_telemetry_disarms(self):
        self.c.arm();self.c.begin('forward');self.store.values['basic']['updated_at']-=2
        self.c.tick();self.assertFalse(self.c.armed);self.assertIsNone(self.c.direction)
    def test_unknown_requires_local_posture_confirmation(self):
        self.store.update({'basic':98},'fixture');self.c.arm()
        with self.assertRaises(MotionError):self.c.begin('forward')
        self.c.confirm_posture('stand');self.c.begin('forward')
        self.c.stop();self.c.disarm();self.c.arm()
        with self.assertRaises(MotionError):self.c.begin('forward')
    def test_known_protection_cannot_be_overridden(self):
        self.store.update({'basic':8},'fixture')
        self.c.confirm_posture('stand')
        with self.assertRaises(MotionError):self.c.arm()
    def test_toggle_once_and_cooldown(self):
        self.store.update({'basic':1},'fixture');self.c.arm();self.c.posture('stand')
        with self.assertRaises(MotionError):self.c.posture('stand')
        self.assertEqual(sum(k==TOGGLE for k,v,t in self.decoded()),1)
        self.assertIsNone(self.c.observed)
    def test_same_posture_never_toggles(self):
        self.c.arm()
        with self.assertRaises(MotionError):self.c.posture('stand')
        self.assertFalse(any(k==TOGGLE for k,v,t in self.decoded()))
    def test_estop_available_without_arming(self):
        self.c.emergency_stop();self.assertEqual(self.decoded(),[(ESTOP,0,0)])
        self.assertFalse(self.c.armed)
    def test_protection_during_control_disarms(self):
        self.c.arm();self.c.begin('forward');self.store.update({'basic':8},'fixture')
        self.c.tick();self.assertFalse(self.c.armed);self.assertIsNone(self.c.direction)
    def test_actual_transport_only_loopback(self):
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as receiver:
            receiver.bind(('127.0.0.1',0));receiver.settimeout(1)
            c=MotionController({'listen_ip':'127.0.0.1','robot_ip':'127.0.0.1','command_port':receiver.getsockname()[1]},self.store)
            try:
                c.arm();c.tick()
                self.assertEqual(receiver.recvfrom(1024)[0],packet(HEARTBEAT))
            finally:c.close()
if __name__=='__main__':unittest.main()
