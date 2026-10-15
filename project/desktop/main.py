import os,sys,json,argparse,shutil
from pathlib import Path
ROOT=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))
if not getattr(sys,'frozen',False):
    import site
    site.addsitedir(str(ROOT/'vendor'))
    sys.path.insert(0,str(ROOT/'vendor'))
def main():
    p=argparse.ArgumentParser()
    p.add_argument('--autoconnect',action='store_true');p.add_argument('--smoke-seconds',type=int,default=0);p.add_argument('--screenshot');p.add_argument('--data-dir');p.add_argument('--mcp-port',type=int,default=8766)
    p.add_argument('--no-autoconnect',action='store_true',help='Start disconnected (the default)')
    args=p.parse_args()
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QFont,QFontDatabase
    from PySide6.QtWidgets import QApplication
    from rover.adapters import Runtime
    from rover.mcp_bridge import MCPBridge
    from rover.ui import MainWindow
    data=Path(args.data_dir) if args.data_dir else Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'RoverDesk'
    data.mkdir(parents=True,exist_ok=True)
    for name in ('profiles.json','known_hosts'):
        if not (data/name).exists():shutil.copyfile(ROOT/name,data/name)
    profiles=json.loads((data/'profiles.json').read_text(encoding='utf-8'))['profiles']
    app=QApplication(sys.argv[:1]);app.setApplicationName('Rover Desk')
    for font in ('msyh.ttc','msyhbd.ttc','segoeui.ttf'):
        font_path=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/font
        if font_path.exists():QFontDatabase.addApplicationFont(str(font_path))
    app.setFont(QFont('Microsoft YaHei',10))
    runtime=Runtime(data/'known_hosts');runtime.app_info={'data_directory':str(data.resolve()),'version':'0.2.2','startup_receive_only':True,'startup_autoconnect':bool(args.autoconnect and not args.no_autoconnect)};bridge=MCPBridge(runtime,data,args.mcp_port);bridge.start()
    window=MainWindow(runtime,bridge,data,profiles);window.show()
    secret=os.environ.pop('ROVER_SSH_PASSWORD','')
    if args.autoconnect and not args.no_autoconnect:QTimer.singleShot(150,lambda:window.connect_robot(secret))
    def finish():
        if args.screenshot:window.grab().save(args.screenshot)
        (data/'smoke-state.json').write_text(json.dumps(runtime.snapshot(),ensure_ascii=False,indent=2),encoding='utf-8');window.close()
    if args.smoke_seconds:QTimer.singleShot(args.smoke_seconds*1000,finish)
    return app.exec()
if __name__=='__main__':raise SystemExit(main())
