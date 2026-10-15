"""Evidence-based alarms. Never infers a hardware fault from missing data."""
import math
import time
from collections import deque

RULES=[('battery_critical','紧急','低电量保护','电量低于 20%'),
       ('protection','紧急','失控保护','基本状态为 8；具体原因未知'),
       ('udp','紧急','状态通信中断','连接后 10 秒仍无有效基本状态（本软件检测）'),
       ('battery_low','一般','电量偏低','20% ≤ 电量 < 35%'),
       ('ssh','一般','SSH 采集中断','已请求 SSH 连接，10 秒后仍未在线'),
       ('camera','一般','摄像头中断','连接后 10 秒仍无新鲜画面'),
       ('overheat','紧急','关节过温','暂无明确告警源，原厂阈值未公开'),
       ('overcurrent','紧急','关节过流','暂无电流告警上报源'),
       ('fall','紧急','跌倒保护','暂无独立触发标志，不能仅凭状态 8 区分'),
       ('app_link','一般','原厂 App 断连','当前软件无法读取原厂 App 连接状态')]

class AlarmMonitor:
    def __init__(self):
        self.history=deque(maxlen=300);self.previous={};self.started=None
    def reset(self):
        self.started=None;self.previous={}
    def evaluate(self,snapshot,connected,camera_stamp=0,now=None):
        now=time.time() if now is None else now
        if connected and self.started is None:self.started=now
        if not connected:self.started=None
        grace=connected and now-self.started>=10
        fields=snapshot['fields'];links=snapshot.get('connections',{})
        def live(key):
            e=fields.get(key,{})
            return e.get('value') if connected and e.get('status')=='live' else None
        battery=live('battery.percent');basic=live('basic')
        if not isinstance(battery,(int,float)) or isinstance(battery,bool) or not math.isfinite(battery) or not 0<=battery<=100:battery=None
        checks={'battery_critical':None if battery is None else battery<20,
                'battery_low':None if battery is None else 20<=battery<35,
                'protection':None if basic is None else basic==8,
                'udp':None if not grace else basic is None,
                'ssh':None if not grace or links.get('SSH',{}).get('state') in (None,'未连接','已断开') else links['SSH']['state']!='在线',
                'camera':None if not grace else not (camera_stamp>0 and 0<=now-camera_stamp<3)}
        rows=[]
        for key,severity,title,rule in RULES:
            value=checks.get(key)
            state='告警中' if value is True else '正常' if value is False else '未判定'
            upgraded=key=='battery_low' and battery is not None and battery<20
            if upgraded:state='已升级紧急'
            evidence=rule
            if key.startswith('battery') and battery is not None:evidence=f'当前电量 {battery:g}%；'+rule
            if key=='protection' and basic is not None:evidence=f'基本状态 {basic}；'+rule
            old=self.previous.get(key)
            if value is True and old is not True:self.history.appendleft((now,severity,title,'触发',evidence))
            elif old is True and value is not True:self.history.appendleft((now,severity,title,'升级为紧急' if upgraded else '恢复' if value is False else '监测结束' if not connected else '数据失效，无法确认恢复',evidence))
            self.previous[key]=value
            rows.append((key,severity,title,state,evidence))
        return rows

class AlarmAudio:
    """Nonblocking Windows playback: two tones, then a 3s/5s silence."""
    def __init__(self,clock=time.monotonic):
        self.clock=clock;self.current=None;self.next_at=0;self.enabled=True;self.temp=None;self.paths={};self.error=''
    def _play(self,severity):
        import winsound
        if not self.paths:
            import tempfile,wave,struct
            from pathlib import Path
            self.temp=tempfile.TemporaryDirectory(prefix='rover-alarms-')
            for kind,freq in [('紧急',1200),('一般',600)]:
                samples=[];rate=22050
                for tone in (True,False,True):
                    duration=.18 if tone else .12
                    n=int(rate*duration)
                    for i in range(n):
                        envelope=min(1,i/220,(n-1-i)/220) if tone else 0
                        samples.append(int(9000*envelope*math.sin(2*math.pi*freq*i/rate)))
                path=Path(self.temp.name)/(str(freq)+'.wav')
                with wave.open(str(path),'wb') as wav:
                    wav.setparams((1,2,rate,0,'NONE','not compressed'));wav.writeframes(struct.pack('<'+'h'*len(samples),*samples))
                self.paths[kind]=str(path)
        winsound.PlaySound(self.paths[severity],winsound.SND_FILENAME|winsound.SND_ASYNC|winsound.SND_NODEFAULT)
    def stop(self):
        if self.current is not None:
            try:
                import winsound
                winsound.PlaySound(None,0)
            except (ImportError,RuntimeError):pass
        self.current=None;self.next_at=0
    def update(self,severity):
        if not self.enabled or severity is None:self.stop();return
        now=self.clock()
        if severity!=self.current or now>=self.next_at:
            try:self._play(severity);self.error=''
            except (ImportError,RuntimeError,OSError) as e:self.error='声音不可用：'+str(e)
            self.current=severity;self.next_at=now+.48+(3 if severity=='紧急' else 5)
    def close(self):
        self.stop()
        if self.temp:self.temp.cleanup()
