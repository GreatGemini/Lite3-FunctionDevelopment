# This script runs in memory on the robot. It reads only; never modifies state.
import glob,json,os,subprocess,time
from pathlib import Path
home=Path.home()
print(json.dumps({'kind':'info','hostname':os.uname().nodename,'architecture':os.uname().machine,'network_config':(home/'jy_exe/conf/network.toml').read_text(),'model_config':(home/'jy_exe/conf/name.toml').read_text()}),flush=True)
active_path=None
position=0
first=True
while True:
    try:
        status=subprocess.check_output(['systemctl','show','jy_exe','-p','ActiveState','-p','SubState','-p','MainPID'],timeout=3).decode()
        path=None
        pids=subprocess.run(['pgrep','-x','tee'],capture_output=True,timeout=2).stdout.decode().split()
        for pid in pids:
            try:
                args=Path('/proc/'+pid+'/cmdline').read_bytes().split(b'\0')
                for arg in args[1:]:
                    candidate=Path(os.fsdecode(arg))
                    if candidate.parent==home/'jy_exe/log' and candidate.suffix=='.log':path=candidate
            except (OSError,ValueError):pass
        lines=[]
        if path is not None:
            size=path.stat().st_size
            if str(path)!=active_path or size<position:
                active_path=str(path)
                # Skip history: future appended lines only, no old readings as live.
                position=size
            with path.open('rb') as f:
                f.seek(position)
                chunk=f.read(65536)
                end=chunk.rfind(b'\n')
                if end>=0:
                    lines=chunk[:end].decode(errors='replace').splitlines()
                    position+=end+1
        print(json.dumps({'kind':'poll','service':status,'active_log':active_path if path else None,'lines':lines,'uptime':Path('/proc/uptime').read_text().split()[0]}),flush=True)
    except Exception as e:print(json.dumps({'kind':'error','message':str(e)}),flush=True)
    time.sleep(2)
