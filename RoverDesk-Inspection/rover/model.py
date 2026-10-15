"""Robot-independent state model. No commands or credentials in snapshots."""
import copy
import math
import threading
import time
from collections import deque

BASIC={1:'趴下',4:'准备',5:'起立中',6:'站立 / 力控',7:'下趴中',8:'失控保护',9:'姿态调整',11:'翻身',17:'归零',18:'后空翻',20:'打招呼'}
GAIT={0:'平地慢速',2:'复杂地形通用',4:'平地中速',5:'平地高速',6:'复杂地形抓地',12:'太空步',13:'高抬腿'}
MOTION={0:'基本状态',1:'踏步',2:'扭动',4:'扭动跳',11:'跳远'}
JOINTS=[f'{leg}_{joint}' for leg in ('FL','FR','HL','HR') for joint in ('HipX','HipY','Knee')]
FIELDS={}
def field(key,label,group,unit='',supported=True):
    FIELDS[key]={'label':label,'group':group,'unit':unit,'supported':supported}
for key,label in [('basic','基本状态'),('gait','步态状态'),('motion','运动状态'),('balance','需要迈步调整平衡'),('zero','归零完成'),('speaker','扬声器')]:
    field(key,label,'整机状态')
for key,label,unit in [('battery.percent','电池电量','%'),('battery.raw','UDP 电量原始值','原始值'),('battery.voltage','电池电压','V'),('battery.temperature','电池温度','°C')]:
    field(key,label,'电源',unit)
for key,label in [('charging','充电状态'),('error_state','故障码'),('task_state','任务状态'),('touchdown','触地 / 楼梯标志')]:
    field(key,label,'手册占位字段',supported=False)
for prefix,group,axes,units in [
    ('rpy','姿态角',('roll','pitch','yaw'),('°',)*3),
    ('angular','姿态角速度',('roll','pitch','yaw'),('rad/s',)*3),
    ('acc','世界系加速度',('x','y','z'),('m/s²',)*3),
    ('position','世界系位姿',('x','y','yaw'),('m','m','rad')),
    ('world_velocity','世界系速度',('x','y','yaw'),('m/s','m/s','rad/s')),
    ('body_velocity','机身系速度',('x','y','yaw'),('m/s','m/s','rad/s'))]:
    for axis,unit in zip(axes,units): field(f'{prefix}.{axis}',f'{group} {axis}',group,unit)
for side in ('front','rear'):field(f'ultrasound.{side}','前方距离' if side=='front' else '后方距离','超声波','m')
for joint in JOINTS:
    for prop,label,unit in [('position','角度','rad'),('velocity','角速度','rad/s'),('torque','扭矩','N·m'),('temperature','温度','°C')]:
        field(f'joint.{joint}.{prop}',f'{joint} {label}','关节',unit)
for leg in ('FL','FR','HL','HR'):
    for axis in ('x','y','z'):field(f'force.{leg}.{axis}',f'{leg} 足端力 {axis}','SDK 接触力','SDK 原值')
for key,label in [('sdk.tick','SDK 时标'),('sdk.imu_timestamp','IMU 时标'),('log.motion_hint','日志动作提示'),('log.gyro_connected','日志陀螺仪连接'),('log.voltage_normal','日志电压正常'),('log.wifi_connected','日志控制端连接')]:
    field(key,label,'诊断')

class StateStore:
    def __init__(self):
        self.lock=threading.RLock()
        self.values={}
        self.links={}
        self.events=deque(maxlen=150)
        self.meta={}
        self.packet_counts={}
        self.started=time.time()
        self.closed=False
    def update(self,values,source,quality='live',ttl=4):
        now=time.time()
        with self.lock:
            if self.closed:return
            for key,value in values.items():
                if key not in FIELDS or not FIELDS[key]['supported']:continue
                if isinstance(value,float) and not math.isfinite(value):continue
                self.values[key]={'value':value,'source':source,'quality':quality,'updated_at':now,'ttl':ttl}
    def link(self,name,state,detail=''):
        with self.lock:
            previous=self.links.get(name,{})
            self.links[name]={'state':state,'detail':str(detail)[:350],'updated_at':time.time()}
            if previous.get('state') != state:self.event(f'{name}: {state} {detail}')
    def event(self,text):
        with self.lock:self.events.append({'time':time.time(),'text':str(text)[:600]})
    def packet(self,code):
        with self.lock:self.packet_counts[code]=self.packet_counts.get(code,0)+1
    def snapshot(self):
        with self.lock:
            now=time.time()
            data={}
            for key,spec in FIELDS.items():
                entry={**spec,**self.values.get(key,{})}
                if not spec['supported']:entry['status']='unsupported'
                elif 'updated_at' not in entry:entry['status']='unavailable'
                else:
                    entry['age_seconds']=round(max(0,now-entry['updated_at']),2)
                    entry['status']='stale' if self.closed or entry['age_seconds']>entry['ttl'] else entry['quality']
                data[key]=entry
            return copy.deepcopy({'schema_version':1,'read_only':True,'timestamp':now,'fields':data,'connections':self.links,'metadata':self.meta,'packet_counts':self.packet_counts,'events':list(self.events)})

def display(key,entry):
    if entry.get('status')=='unsupported':return '不支持（手册占位）'
    if 'value' not in entry:return '—'
    val=entry['value']
    enums={'basic':BASIC,'gait':GAIT,'motion':MOTION}
    if key in enums:return f'{enums[key].get(val,"未知状态")} ({val})'
    if isinstance(val,bool):return '是' if val else '否'
    if isinstance(val,float):return f'{val:.3f}'.rstrip('0').rstrip('.')
    return str(val)
