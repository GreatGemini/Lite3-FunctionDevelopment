"""Strict Lite3 UDP decoding; verified layout lengths only, little-endian."""
import math
import struct
from .model import JOINTS
HEADER=struct.Struct('<III')

def decode(packet):
    if len(packet)<12:raise ValueError('报文头不足 12 字节')
    code,size,kind=HEADER.unpack_from(packet)
    p=packet[12:]
    if kind==0:
        if p:raise ValueError('简单报文长度错误')
        return code,({'speaker':bool(size)} if code==0x11050F08 and size in (0,1) else {})
    if kind!=1 or size!=len(p):raise ValueError('报文类型或数据长度错误')
    values={}
    if code==0x0901:
        if size!=200:raise ValueError(f'整机状态 ABI 尚未支持: {size} 字节（预期 200）')
        values.update(zip(('basic','gait'),struct.unpack_from('<ii',p,0)))
        for offset,prefix,axes in [(8,'rpy',('roll','pitch','yaw')),(32,'angular',('roll','pitch','yaw')),(56,'acc',('x','y','z')),(80,'position',('x','y','yaw')),(104,'world_velocity',('x','y','yaw')),(128,'body_velocity',('x','y','yaw'))]:
            values.update({f'{prefix}.{axis}':val for axis,val in zip(axes,struct.unpack_from('<3d',p,offset))})
        values['motion']=struct.unpack_from('<i',p,164)[0]
        values['battery.raw']=struct.unpack_from('<d',p,168)[0]
        if p[180] not in (0,1) or p[181] not in (0,1):raise ValueError('状态布尔值不符合布局')
        values.update(balance=bool(p[180]),zero=bool(p[181]))
        values.update(zip(('ultrasound.front','ultrasound.rear'),struct.unpack_from('<2d',p,184)))
        # Placeholder offsets 152,156,160,176 intentionally never interpreted.
    elif code in (0x0902,0x0903):
        if size!=96:raise ValueError('关节报文必须是 12 个 double')
        prop='position' if code==0x0902 else 'velocity'
        values.update({f'joint.{j}.{prop}':v for j,v in zip(JOINTS,struct.unpack('<12d',p))})
    elif code==0x0906:
        if size not in (332,336):raise ValueError(f'SDK 状态 ABI 尚未支持: {size}')
        values['sdk.tick'],values['sdk.imu_timestamp']=struct.unpack_from('<Ii',p)
        raw=struct.unpack_from('<9f',p,8)
        for n,axis in enumerate(('roll','pitch','yaw')):
            values[f'rpy.{axis}']=raw[n]
            values[f'angular.{axis}']=math.radians(raw[3+n])
        for n,axis in enumerate(('x','y','z')):values[f'acc.{axis}']=raw[6+n]
        for i,j in enumerate(JOINTS):
            values.update({f'joint.{j}.{prop}':v for prop,v in zip(('position','velocity','torque','temperature'),struct.unpack_from('<4f',p,44+16*i))})
        force=struct.unpack_from('<12d',p,240 if size==336 else 236)
        for i,leg in enumerate(('FL','FR','HL','HR')):
            for n,axis in enumerate(('x','y','z')):values[f'force.{leg}.{axis}']=force[3*i+n]
    if any(isinstance(v,float) and not math.isfinite(v) for v in values.values()):raise ValueError('报文包含非有限浮点数')
    return code,values
