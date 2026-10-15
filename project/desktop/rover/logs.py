"""Parse only fresh appended log lines; never label inferred state as telemetry."""
import re
from .model import JOINTS
NUMBER=r'([-+]?\d+(?:\.\d+)?)'

def parse_line(line):
    result={}
    battery=re.search(r'battery_level\s*=\s*'+NUMBER+r'%.*?temp\s*=\s*'+NUMBER+r'.*?voltage\s*=\s*'+NUMBER+r'V',line)
    if battery:result.update(zip(('battery.percent','battery.temperature','battery.voltage'),map(float,battery.groups())))
    if '[Motor Temperature]' in line:
        for leg in ('FL','FR','HL','HR'):
            m=re.search(leg+r':\s*'+NUMBER+r'\s*,\s*'+NUMBER+r'\s*,\s*'+NUMBER,line)
            if m:
                for prop,value in zip(('HipX','HipY','Knee'),m.groups()):result[f'joint.{leg}_{prop}.temperature']=float(value)
    for token,key in [('gyro connect','log.gyro_connected'),('battary voltage normal','log.voltage_normal'),('wifi connect','log.wifi_connected')]:
        m=re.search(re.escape(token)+r':\s*([01])',line)
        if m:result[key]=bool(int(m.group(1)))
    hint=None
    if 'Stand down action has finished' in line:hint='下趴动作完成（日志）'
    elif 'Stand up action has finished' in line:hint='起立动作完成（日志）'
    elif 'Standing down' in line:hint='下趴中（日志）'
    elif 'Standing up' in line:hint='起立中（日志）'
    elif 'Switching to force control mode' in line:hint='切换至力控（日志）'
    elif 'kWaitForStanding' in line:hint='等待起立（日志）'
    elif 'Soft Emergency' in line:hint='软件急停（日志）'
    if hint:result['log.motion_hint']=hint
    return result
