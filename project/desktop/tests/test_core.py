import sys,site,struct,math,time,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
site.addsitedir(str(ROOT/'vendor'));sys.path.insert(0,str(ROOT/'vendor'));sys.path.insert(0,str(ROOT))
from rover.protocol import decode
from rover.model import StateStore,JOINTS
from rover.logs import parse_line
def packet(code,p):return struct.pack('<III',code,len(p),1)+p
class ProtocolTests(unittest.TestCase):
    def test_documented_joint_fixture(self):
        raw=bytes.fromhex('0209000060000000010000002efd3ccf47e4e1bff1304992f49ee7bfc3d7eefe8567f13f9ae4b66d6583f1bf24d8f33c3d00f13f8c16222a0b1f0140e8baaaaa3803ef3fd009000060bdd2bfdb0433531150e73f7d0b000072f0e53f0a3d0cc3f071e73fc3d7eefe7b52f93f')
        code,v=decode(raw);self.assertEqual(code,0x902);self.assertAlmostEqual(v['joint.FL_HipX.position'],-0.5591162726995316);self.assertAlmostEqual(v['joint.HR_Knee.position'],1.5826377828902742)
    def test_aligned_state_fields_and_placeholders(self):
        p=bytearray(200);struct.pack_into('<ii',p,0,6,13);struct.pack_into('<3d',p,80,2,3,.5)
        struct.pack_into('<i',p,164,1);struct.pack_into('<d',p,168,25);p[180]=1;p[181]=0;struct.pack_into('<2d',p,184,.28,4.5)
        code,v=decode(packet(0x901,p));self.assertEqual(v['position.yaw'],.5);self.assertTrue(v['balance']);self.assertFalse(v['zero']);self.assertEqual(v['ultrasound.rear'],4.5)
        self.assertNotIn('charging',v);self.assertNotIn('battery.percent',v)
    def test_sdk_padding_variants_units(self):
        for size in (332,336):
            p=bytearray(size);struct.pack_into('<Ii9f',p,0,123,234,1,2,3,180,0,0,0,0,9.8)
            struct.pack_into('<4f',p,44,1,2,3,40);struct.pack_into('<12d',p,240 if size==336 else 236,*range(12))
            _,v=decode(packet(0x906,p));self.assertAlmostEqual(v['angular.roll'],math.pi);self.assertEqual(v['joint.FL_HipX.temperature'],40);self.assertEqual(v['force.HR.z'],11)
    def test_malformed_and_unknown(self):
        for data in [b'',struct.pack('<III',1,0,9),packet(0x901,bytes(199)),packet(0x902,bytes(8)),struct.pack('<III',1,4,1)]:
            with self.subTest(data=data[:12]),self.assertRaises(ValueError):decode(data)
        self.assertEqual(decode(packet(0xbeef,b'abc'))[1],{})
    def test_nan_rejected(self):
        with self.assertRaises(ValueError):decode(packet(0x902,struct.pack('<12d',*([float('nan')]*12))))
    def test_speaker(self):
        self.assertTrue(decode(struct.pack('<III',0x11050F08,1,0))[1]['speaker'])
class StateTests(unittest.TestCase):
    def test_expiry_and_no_placeholder_data(self):
        s=StateStore()
        with patch('rover.model.time.time',return_value=100):s.update({'basic':6,'charging':True},'fixture',ttl=3)
        with patch('rover.model.time.time',return_value=105):r=s.snapshot()
        self.assertEqual(r['fields']['basic']['status'],'stale');self.assertEqual(r['fields']['charging']['status'],'unsupported');self.assertNotIn('value',r['fields']['charging'])
    def test_snapshot_independent(self):
        s=StateStore();s.update({'basic':6},'test');a=s.snapshot();a['fields']['basic']['value']=9;self.assertEqual(s.snapshot()['fields']['basic']['value'],6)
    def test_log_fields(self):
        v=parse_line('[Battery info] battery_level = 25%, temp = 34°C, voltage = 27.80V')
        self.assertEqual(v['battery.percent'],25);self.assertEqual(v['battery.voltage'],27.8)
        v=parse_line('[Motor Temperature] FL:44.09, 40.63, 35.43, FR:42.36, 40.63, 33.70, HL:42.36, 40.63, 35.43, HR:40.63, 38.90, 33.70')
        self.assertEqual(len(v),12);self.assertEqual(v['joint.HR_Knee.temperature'],33.7)
    def test_log_hint_not_state(self):
        v=parse_line('Stand up action has finished, waitting to switch to force control mode!')
        self.assertIn('log.motion_hint',v);self.assertNotIn('basic',v)
if __name__=='__main__':unittest.main()
