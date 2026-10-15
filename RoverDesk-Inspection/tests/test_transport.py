import sys,site,socket,threading,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];site.addsitedir(str(ROOT/'vendor'));sys.path.insert(0,str(ROOT/'vendor'));sys.path.insert(0,str(ROOT))
from rover.model import StateStore
from rover.adapters import Lite3Adapter,Runtime
import struct

class TransportTests(unittest.TestCase):
    def test_udp_receives_secondary_local_address_and_shutdown(self):
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
            s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        store=StateStore()
        a=Lite3Adapter({'robot_ip':'127.0.0.1','listen_ip':'127.0.0.1','listen_port':port},store,'')
        thread=threading.Thread(target=a.receive_udp);thread.start()
        try:
            deadline=time.monotonic()+3
            while 'UDP' not in store.snapshot()['connections'] and time.monotonic()<deadline:time.sleep(.01)
            packet=struct.pack('<III12d',0x902,96,1,*range(12))
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sender:sender.sendto(packet,('127.0.0.2',port))
            deadline=time.monotonic()+3
            while not store.values and time.monotonic()<deadline:time.sleep(.01)
            snap=store.snapshot();self.assertEqual(snap['fields']['joint.HR_Knee.position']['value'],11)
            self.assertEqual(snap['connections']['UDP']['state'],'在线')
        finally:a.stop();thread.join(2)
        self.assertFalse(thread.is_alive())
    def test_disconnect_immediately_invalidates(self):
        r=Runtime('');r.store.update({'battery.percent':25},'fixture',ttl=1000)
        r.disconnect();r.store.update({'battery.percent':100},'late worker')
        v=r.snapshot()['fields']['battery.percent']
        self.assertEqual(v['status'],'stale');self.assertEqual(v['value'],25)
if __name__=='__main__':unittest.main()
