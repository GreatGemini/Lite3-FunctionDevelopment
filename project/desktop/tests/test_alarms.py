import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rover.alarms import AlarmMonitor,AlarmAudio

class AlarmTests(unittest.TestCase):
    def snapshot(self,battery=50,basic=6,status='live'):
        return {'fields':{'battery.percent':{'value':battery,'status':status},'basic':{'value':basic,'status':status}},'connections':{'SSH':{'state':'在线'}}}
    def active(self,rows):return {r[0] for r in rows if r[3]=='告警中'}
    def test_battery_boundaries_and_recovery(self):
        monitor=AlarmMonitor()
        for value,expected in [(35,set()),(34.9,{'battery_low'}),(20,{'battery_low'}),(19.9,{'battery_critical'}),(0,{'battery_critical'}),(40,set())]:
            self.assertEqual(self.active(monitor.evaluate(self.snapshot(value),True,now=100)),expected)
        self.assertTrue(any(h[3]=='恢复' for h in monitor.history))
    def test_stale_is_unknown_not_recovered(self):
        monitor=AlarmMonitor();monitor.evaluate(self.snapshot(10),True,now=100)
        rows=monitor.evaluate(self.snapshot(10,status='stale'),True,now=101)
        self.assertEqual(self.active(rows),set())
        self.assertIn('无法确认恢复',monitor.history[0][3])
    def test_network_grace_disconnect_and_unknown_hardware(self):
        monitor=AlarmMonitor();s=self.snapshot(status='unavailable');s['connections']['SSH']['state']='连接失败'
        self.assertEqual(self.active(monitor.evaluate(s,True,now=100)),set())
        self.assertEqual(self.active(monitor.evaluate(s,True,now=110)),{'udp','camera','ssh'})
        rows=monitor.evaluate(s,False,now=111);self.assertEqual(self.active(rows),set())
        self.assertTrue(all(r[3]=='未判定' for r in rows if r[0] in ('overheat','overcurrent','fall','app_link')))
    def test_protection_is_not_inferred_cause(self):
        rows=AlarmMonitor().evaluate(self.snapshot(basic=8),True,now=100)
        self.assertEqual(self.active(rows),{'protection'})
    def test_history_does_not_repeat_and_invalid_battery(self):
        monitor=AlarmMonitor()
        for _ in range(10):monitor.evaluate(self.snapshot(10),True,now=100)
        self.assertEqual(len(monitor.history),1)
        for invalid in (-1,101,float('nan'),True):
            self.assertEqual(self.active(monitor.evaluate(self.snapshot(invalid),True,now=100)),set())
    def test_sound_cadence_preemption_and_mute(self):
        now=[0];audio=AlarmAudio(clock=lambda:now[0]);played=[]
        audio._play=played.append
        audio.update('一般');self.assertAlmostEqual(audio.next_at,5.48)
        now[0]=1;audio.update('一般');self.assertEqual(played,['一般'])
        audio.update('紧急');self.assertEqual(played,['一般','紧急']);self.assertAlmostEqual(audio.next_at,4.48)
        now[0]=4.49;audio.update('紧急');self.assertEqual(len(played),3)
        audio.enabled=False;audio.update('紧急');self.assertIsNone(audio.current)
        audio.close()

if __name__=='__main__':unittest.main()
