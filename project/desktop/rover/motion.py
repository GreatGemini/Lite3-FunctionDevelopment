"""Lite 3 desktop-only motion controller. Idle/connection alone sends nothing."""
import socket,struct,threading,time
HEARTBEAT=0x21040001
TOGGLE=0x21010202
ESTOP=0x21020C0E
VOICE=0x21010C0A
AXES=(0x21010130,0x21010131,0x21010135)
# Axis amplitudes, not m/s. Manual V1.0.7 pp.9-10; keep slow gait.
DEAD_ZONES=(6553,12553,9553)
SPEED_LEVELS=(0.10,0.20,0.35,0.50,0.65)
DIRECTION_SIGNS={'forward':(1,0,0),'backward':(-1,0,0),
                 'left':(0,-1,0),'right':(0,1,0),
                 'turn_left':(0,0,-1),'turn_right':(0,0,1)}
def direction_values(direction,level):
    if type(level) is not int or not 1<=level<=len(SPEED_LEVELS):raise ValueError('速度档位必须为 1—5')
    return tuple(sign*round(dead+(32767-dead)*SPEED_LEVELS[level-1]) if sign else 0
                 for sign,dead in zip(DIRECTION_SIGNS[direction],DEAD_ZONES))
DIRECTIONS={key:direction_values(key,1) for key in DIRECTION_SIGNS}

def packet(code,value=0):return struct.pack('<III',code,value&0xffffffff,0)
class MotionError(RuntimeError):pass

class MotionController:
    def __init__(self,profile,store,send=None,clock=time.monotonic):
        self.profile=dict(profile);self.store=store;self.clock=clock
        self.lock=threading.RLock();self.sock=None;self.sender=send
        self.speed_level=1;self.armed=False;self.direction=None;self.deadline=0
        self.mode_ready=0;self.next_heartbeat=0;self.zero_until=0
        self.busy_until=0;self.observed=None;self.observed_basic=None
        self.voice_active=None;self.voice_deadline=0
        self.session_active=False;self.voice_started=0;self.voice_seen_action=False;self.voice_stable_since=None
        self.message='遥控未启用';self.halt=threading.Event();self.thread=None
    def set_speed(self,level):
        with self.lock:
            if type(level) is not int or not 1<=level<=5:raise MotionError('速度档位必须为 1—5')
            if self.direction or self.voice_active is not None or self.clock()<self.busy_until:raise MotionError('请先停止移动或等待姿态切换完成，再调速')
            self.speed_level=level
    def start_worker(self):
        if self.thread is None:
            self.thread=threading.Thread(target=self._run,daemon=True);self.thread.start()
    def _send(self,code,value=0):
        data=packet(code,value)
        if self.sender:self.sender(data);return
        if self.sock is None:
            self.sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
            self.sock.bind((self.profile['listen_ip'],0))
        self.sock.sendto(data,(self.profile['robot_ip'],int(self.profile.get('command_port',43893))))
    def _axes(self,values):
        for code,value in zip(AXES,values):self._send(code,value)
    def _basic(self):
        e=self.store.snapshot()['fields']['basic']
        if e.get('status')!='live' or e.get('age_seconds',99)>.5:
            raise MotionError('整机遥测已过期，遥控已锁定')
        return e.get('value')
    @staticmethod
    def posture_from_basic(basic):
        return {1:'sit',6:'stand',9:'stand'}.get(basic)
    def _posture(self):
        basic=self._basic()
        posture=self.posture_from_basic(basic)
        if posture:return posture
        # Only the observed firmware's unmapped code permits explicit local observation.
        if basic==98 and self.observed_basic==basic:return self.observed
        return None
    def confirm_posture(self,posture):
        with self.lock:
            if posture not in ('sit','stand',None):raise MotionError('姿态选项无效')
            if self.direction:raise MotionError('请先停止移动，再确认姿态')
            self.observed=posture;self.observed_basic=self._basic() if posture else None
            if posture:self.store.event('操作员现场确认姿态：'+posture+'（不改写遥测）')
    def arm(self):
        with self.lock:
            basic=self._basic()
            if basic not in (1,6,9,98):raise MotionError('当前状态不允许接管遥控')
            if self.voice_active is not None:raise MotionError('动作仍在执行，请等待完成或点击停止')
            self.session_active=True;self.armed=True;self.direction=None;self.next_heartbeat=self.clock()
            self.message='遥控已启用；按住方向移动'
            self.store.event('桌面遥控已启用；开始心跳，未发送移动指令')
    def _require_armed(self):
        if not self.armed:raise MotionError('请先启用遥控')
        self._basic()
        if self.voice_active is not None or self.clock()<self.busy_until:raise MotionError('动作执行中，请等待完成或点击停止')
    def begin(self,direction):
        with self.lock:
            if direction not in DIRECTIONS:raise MotionError('方向无效')
            self._require_armed()
            if self._posture()!='stand':raise MotionError('请确认机器狗已站立；未知姿态禁止移动')
            self._axes((0,0,0))
            # Manual control, move mode, slow gait, disable keep-stepping.
            for code,value in ((0x21010C02,0),(0x21010D06,0),(0x21010300,0),(0x21010C06,2)):
                self._send(code,value)
            self.direction=direction;self.deadline=self.clock()+.18
            self.mode_ready=self.clock()+.12;self.zero_until=0
            self.message='按住移动；松开停止'
    def renew(self,direction):
        with self.lock:
            if self.armed and self.direction==direction:self.deadline=self.clock()+.18
    def stop(self,reason='已发送零速度'):
        with self.lock:
            active=self.voice_active
            if self.voice_active is not None:
                self._send(VOICE,7);self.voice_active=None;self.voice_deadline=0;self.busy_until=0
            self.direction=None;self.deadline=0;self.mode_ready=0
            if self.session_active:
                self._axes((0,0,0));self.zero_until=self.clock()+.35
            self.message=reason
            if active is not None:self.store.event(f'{reason}；停止动作值={active}；心跳保持={self.session_active}')
    def lock_input(self,reason):
        with self.lock:
            if self.direction is not None or self.voice_active in (3,4,5,6):self.stop(reason)
            self.armed=False;self.observed=None;self.observed_basic=None
            self.message=reason+'；控制心跳保持' if self.session_active else reason
            self.store.event(self.message)
    def disarm(self,reason='遥控已关闭'):
        with self.lock:
            try:
                if self.voice_active is not None:self.stop(reason)
                if self.armed:
                    for _ in range(3):self._axes((0,0,0))
            finally:
                self.armed=False;self.direction=None;self.deadline=0;self.zero_until=0
                self.observed=None;self.observed_basic=None;self.message=reason
                self.voice_active=None;self.voice_deadline=0
    def text_command(self,value):
        from .text_commands import COMMANDS
        with self.lock:
            if type(value) is not int or value not in COMMANDS.values():raise MotionError('不支持的文字动作')
            if value==7:
                if self.voice_active is None:self._send(VOICE,7)
                self.stop('已发送停止口令');return
            self._require_armed()
            current=self._posture()
            if current is None:raise MotionError('请先确认站立／趴下姿态')
            if value in (1,2):
                if current=={1:'stand',2:'sit'}[value]:raise MotionError('当前已是目标姿态，不重复发送')
            elif current!='stand':raise MotionError('此动作需要机器狗站立')
            self.stop();self.zero_until=0
            self._send(VOICE,value);self.voice_active=value
            duration=1.0 if value in (3,4,5,6) else 15.0
            self.voice_deadline=self.clock()+duration;self.busy_until=self.voice_deadline
            self.voice_started=self.clock();self.voice_seen_action=False;self.voice_stable_since=None
            if value in (1,2,22):self.observed=None;self.observed_basic=None
            self.message='已发送文字动作；可随时停止（未确认执行结果）'
            self.store.event(self.message+'，动作值='+str(value))
    def _check_voice(self,basic,now):
        value=self.voice_active
        if value is None:return
        # Only documented transitions count; an unchanged standing state is not an acknowledgement.
        transition={1:5,2:7,22:20}.get(value)
        if transition is not None and basic==transition:self.voice_seen_action=True
        target={1:6,2:1,22:6}.get(value)
        complete=target is not None and basic==target and (value in (1,2) or self.voice_seen_action)
        if complete and now-self.voice_started>=.5:
            if self.voice_stable_since is None:self.voice_stable_since=now
            if now-self.voice_stable_since>=.3:
                self.voice_active=None;self.voice_deadline=0;self.busy_until=0;self.zero_until=0
                self.message='状态反馈确认动作完成，未追加停止口令'
                self.store.event(self.message+'，动作值='+str(value));return
        else:self.voice_stable_since=None
        if now>=self.voice_deadline:
            if value in (3,4,5,6):self.stop('平移时限到达，已发送停止')
            else:
                self.stop('动作超时，未获得可验证的完成状态，已发送停止')
                self.armed=False;self.observed=None;self.observed_basic=None
    def posture(self,target):
        with self.lock:
            if target not in ('sit','stand'):raise MotionError('姿态目标无效')
            self._require_armed();current=self._posture()
            if current is None:raise MotionError('切换指令需要先确认当前站立/趴下姿态')
            if current==target:raise MotionError('当前已是目标姿态，不发送切换指令')
            self.stop()
            self._send(TOGGLE) # Exactly once; never retry a toggle.
            self.busy_until=self.clock()+4
            self.observed=None;self.observed_basic=None
            self.message='已发送姿态切换；请观察实际结果'
            self.store.event(self.message+'，目标='+target)
    def emergency_stop(self):
        with self.lock:
            try:self._send(ESTOP)
            finally:
                self.voice_active=None;self.voice_deadline=0;self.busy_until=0
                self.armed=False;self.direction=None;self.observed=None;self.observed_basic=None
                self.message='已发送软件急停，需原厂遥控器处理恢复'
                self.store.event(self.message)
    def tick(self):
        with self.lock:
            if not self.session_active:return
            now=self.clock()
            if now>=self.next_heartbeat:
                self._send(HEARTBEAT);self.next_heartbeat=now+.25
            if not self.armed and self.voice_active is None and not self.direction and now>=self.zero_until:return
            try:
                basic=self._basic()
                if basic not in (1,4,5,6,7,9,98) and not (self.voice_active==22 and basic==20):raise MotionError('状态不允许遥控')
            except MotionError:
                self.disarm('遥测中断或保护状态，已归零并锁定遥控');return
            self._check_voice(basic,now)
            if self.direction and (now>self.deadline or self._posture()!='stand'):
                self.stop('操作保持超时或姿态变化，已归零')
            if self.direction and now>=self.mode_ready:self._axes(direction_values(self.direction,self.speed_level))
            elif self.direction or now<self.zero_until:self._axes((0,0,0))
    def _run(self):
        while not self.halt.wait(.04):
            try:self.tick()
            except (OSError,MotionError) as e:
                with self.lock:
                    try:self.disarm('发送失败，遥控已锁定')
                    except OSError:pass
                    self.message='发送失败：'+str(e)
                    self.store.event(self.message)
    def status(self):
        with self.lock:return {'armed':self.armed,'direction':self.direction,
                               'message':self.message,'operator_posture':self.observed,'speed_level':self.speed_level,
                               'session_active':self.session_active,'text_action':self.voice_active,
                               'busy':self.voice_active is not None or self.clock()<self.busy_until}
    def close(self):
        self.halt.set()
        try:self.disarm('连接关闭，遥控已锁定')
        finally:
            with self.lock:
                if self.session_active:self.store.event('控制会话关闭，心跳结束')
                self.session_active=False
            if self.thread and self.thread is not threading.current_thread():self.thread.join(timeout=1)
            if self.sock:self.sock.close();self.sock=None
