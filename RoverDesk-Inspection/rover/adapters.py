"""Telemetry adapters with a separately armed desktop motion controller."""
import base64
import io
import json
import socket
import threading
import time
from abc import ABC,abstractmethod
from pathlib import Path
from .model import StateStore
from .protocol import decode
from .logs import parse_line
from .motion import MotionController

class RobotAdapter(ABC):
    capabilities={'telemetry','camera','diagnostics'}
    @abstractmethod
    def start(self,password=''):...
    @abstractmethod
    def stop(self):...

class Lite3Adapter(RobotAdapter):
    def __init__(self,profile,store,known_hosts):
        self.profile=dict(profile);self.store=store;self.known_hosts=known_hosts
        self.halt=threading.Event();self.threads=[];self.ssh=None;self.udp=None
        self.frame_lock=threading.Lock();self.jpeg=None;self.frame_time=0;self.resolution=''
    def spawn(self,fn,*args):
        t=threading.Thread(target=fn,args=args,daemon=True);self.threads.append(t);t.start()
    def start(self,password=''):
        self.spawn(self.receive_udp)
        self.spawn(self.camera)
        if password:self.spawn(self.read_ssh,password)
        else:self.store.link('SSH','未连接','输入 SSH 密码可读取电量、温度和服务信息')
    def stop(self):
        self.halt.set()
        if self.udp:
            try:self.udp.close()
            except OSError:pass
        if self.ssh:self.ssh.close()
        for name in ('UDP','SSH','摄像头'):self.store.link(name,'已断开')
    def frame(self):
        with self.frame_lock:return self.jpeg,self.frame_time,self.resolution
    def receive_udp(self):
        try:
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
                self.udp=s
                s.bind(('0.0.0.0',int(self.profile['listen_port'])))
                s.settimeout(0.5)
                self.store.link('UDP','等待数据',f"所有本机 IPv4 地址:{self.profile['listen_port']}；仅接收 {self.profile['robot_ip']}")
                last=0
                while not self.halt.is_set():
                    try:packet,source=s.recvfrom(65535)
                    except socket.timeout:
                        if last and time.monotonic()-last>3:self.store.link('UDP','数据中断','超过 3 秒未收到有效状态报文')
                        continue
                    if source[0]!=self.profile['robot_ip']:continue
                    try:code,values=decode(packet)
                    except ValueError as e:
                        # Rate limit repeated malformed-packet messages.
                        if time.monotonic()-getattr(self,'last_bad',0)>3:
                            self.store.event(f'UDP 报文未解析: {e}');self.last_bad=time.monotonic()
                        continue
                    self.store.packet(f'0x{code:04X}')
                    if values:
                        last=time.monotonic()
                        self.store.update(values,f'UDP 0x{code:04X}',ttl=3)
                        self.store.link('UDP','在线','有效状态报文已接收')
        except OSError as e:
            if not self.halt.is_set():self.store.link('UDP','连接失败',e)
    def camera(self):
        import av
        from PIL import Image  # explicit dependency for standalone packaging
        while not self.halt.is_set():
            try:
                self.store.link('摄像头','连接中')
                with av.open(self.profile['camera_url'],options={'rtsp_transport':'tcp'},timeout=(5,4)) as stream:
                    last=0
                    for frame in stream.decode(video=0):
                        if self.halt.is_set():return
                        if time.monotonic()-last<0.10:continue
                        last=time.monotonic()
                        buf=io.BytesIO();frame.to_image().save(buf,format='JPEG',quality=85)
                        with self.frame_lock:
                            self.jpeg=buf.getvalue();self.frame_time=time.time();self.resolution=f'{frame.width} × {frame.height}'
                        self.store.link('摄像头','在线',self.resolution)
            except Exception as e:
                if self.halt.is_set():return
                self.store.link('摄像头','重连中',str(e).replace(self.profile['camera_url'],'摄像头'))
                self.halt.wait(2)
    def read_ssh(self,password):
        import paramiko
        source=(Path(__file__).parent/'remote_reader.py').read_text(encoding='utf-8')
        encoded=base64.b64encode(source.encode()).decode()
        command=f"python3 -u -c \"import base64;exec(base64.b64decode('{encoded}'))\""
        while not self.halt.is_set():
            client=paramiko.SSHClient();self.ssh=client
            try:
                client.load_system_host_keys()
                if Path(self.known_hosts).exists():client.load_host_keys(str(self.known_hosts))
                client.set_missing_host_key_policy(paramiko.RejectPolicy())
                self.store.link('SSH','连接中')
                sock=socket.socket();sock.settimeout(6)
                try:
                    if self.profile.get('listen_ip') not in ('','0.0.0.0'):sock.bind((self.profile['listen_ip'],0))
                    sock.connect((self.profile['robot_ip'],22))
                    client.connect(self.profile['robot_ip'],username=self.profile['ssh_user'],password=password,sock=sock,allow_agent=False,look_for_keys=False,timeout=6,banner_timeout=6,auth_timeout=6)
                except Exception:
                    sock.close();raise
                if self.halt.is_set():return
                client.get_transport().set_keepalive(5)
                stdin,stdout,stderr=client.exec_command(command,timeout=10)
                stdin.close()
                self.store.link('SSH','在线','只读采集；不会启动、停止或修改机器人')
                for line in stdout:
                    if self.halt.is_set():return
                    msg=json.loads(line)
                    if msg['kind']=='info':
                        with self.store.lock:self.store.meta.update({k:v for k,v in msg.items() if k!='kind'})
                    elif msg['kind']=='poll':
                        with self.store.lock:self.store.meta.update(service=msg['service'],active_log=msg['active_log'],uptime_seconds=msg['uptime'])
                        self.store.link('SSH','在线','只读日志与系统状态')
                        for log in msg['lines']:
                            values=parse_line(log)
                            hint=values.pop('log.motion_hint',None)
                            if values:self.store.update(values,'SSH 实时日志',ttl=15)
                            if hint:
                                self.store.update({'log.motion_hint':hint},'SSH 动作日志',quality='inferred',ttl=10)
                                self.store.event(hint)
                    else:self.store.event('远程只读采集: '+msg.get('message',''))
                if not self.halt.is_set():raise ConnectionError('SSH 日志通道已关闭')
            except paramiko.AuthenticationException:
                self.store.link('SSH','认证失败','请检查用户名和密码');return
            except paramiko.BadHostKeyException:
                self.store.link('SSH','主机密钥不匹配','已拒绝连接，请核对设备身份');return
            except Exception as e:
                if self.halt.is_set():return
                self.store.link('SSH','连接失败',e)
                # Do not repeat authentication against unknown hosts.
                if 'known_hosts' in str(e) or 'not found in known_hosts' in str(e):return
                self.halt.wait(4)
            finally:client.close()

ADAPTERS={'lite3':Lite3Adapter}

class Runtime:
    def __init__(self,known_hosts):
        self.store=StateStore();self.adapter=None;self.motion=None;self.known_hosts=known_hosts;self.profile={};self.app_info={}
    def connect(self,profile,password=''):
        self.disconnect()
        self.store=StateStore();self.profile=dict(profile)
        cls=ADAPTERS[profile['adapter']]
        self.adapter=cls(profile,self.store,self.known_hosts)
        self.motion=MotionController(profile,self.store) if profile['adapter']=='lite3' else None
        if self.motion:self.motion.start_worker()
        self.store.event('已连接配置：'+profile['name']+'；遥控默认锁定')
        self.adapter.start(password)
    def disconnect(self):
        if self.motion:
            try:self.motion.close()
            except OSError as e:self.store.event('关闭遥控发送失败：'+str(e))
            self.motion=None
        if self.adapter:self.adapter.stop();self.adapter=None
        with self.store.lock:self.store.closed=True
    def snapshot(self):
        snap=self.store.snapshot();snap['metadata'].update(self.app_info);snap['robot']={k:v for k,v in self.profile.items() if k not in ('password',)}
        snap['capabilities']={'read_telemetry':True,'camera':True,'motion_control':self.motion is not None,'mcp_motion_control':False,'adapters':list(ADAPTERS)}
        snap['control']=self.motion.status() if self.motion else {'armed':False,'direction':None,'message':'未连接','operator_posture':None,'busy':False}
        return snap
    def camera_frame(self):return self.adapter.frame() if self.adapter else (None,0,'')
