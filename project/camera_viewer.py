import sys, time, threading, io, json
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
sys.path.insert(0, str(Path.home() / "AppData/Local/Temp/lite3-video-deps"))
import av

ROOT = Path(__file__).resolve().parent
URL = "rtsp://192.168.1.120:8554/test"
lock = threading.Lock()
latest = None
updated = 0.0
error = "Connecting"
stop = threading.Event()

def receive():
    global latest, updated, error
    saved = False
    while not stop.is_set():
        try:
            with av.open(URL, options={"rtsp_transport": "tcp"}, timeout=(5, 5)) as stream:
                last = 0
                for frame in stream.decode(video=0):
                    if stop.is_set():
                        return
                    now = time.monotonic()
                    if now - last < 0.12:
                        continue
                    last = now
                    buffer = io.BytesIO()
                    frame.to_image().save(buffer, format="JPEG", quality=85)
                    data = buffer.getvalue()
                    with lock:
                        latest, updated, error = data, now, ""
                    if not saved:
                        (ROOT / "camera-first-frame.jpg").write_bytes(data)
                        saved = True
                        print(f"First frame: {frame.width}x{frame.height}", flush=True)
        except Exception as exc:
            with lock:
                error = str(exc)
            print("Stream:", exc, flush=True)
            stop.wait(2)

PAGE = """<!doctype html><html lang="zh"><meta charset="utf-8"><title>Lite 3 实时摄像头</title>
<style>body{background:#101820;color:#e9f2f5;font:18px system-ui;margin:30px auto;max-width:1000px;padding:0 20px}img{width:100%;max-height:75vh;object-fit:contain;background:#000;border-radius:12px}p{color:#9db0be}#status{font-size:16px}</style>
<h1>Lite 3 实时摄像头</h1><p>运动主机 · 192.168.1.120 · 本机预览</p><img id="video" alt="等待摄像头画面"><p id="status">正在连接…</p>
<script>const im=document.getElementById('video'),st=document.getElementById('status');
async function tick(){try{const r=await fetch('/status',{cache:'no-store'}),s=await r.json();
if(s.ready){im.src='/frame.jpg?t='+Date.now();im.style.opacity=s.age<3?1:0.35;}
st.textContent=s.ready&&s.age<3?'实时画面 · 预览约 8 帧/秒':('等待视频 / 画面已中断 · '+s.error);
}catch(e){st.textContent='本机预览服务已停止';im.style.opacity=0.35;}setTimeout(tick,150);}tick();</script></html>""".encode()

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split('?')[0]
        with lock:
            data, stamp, message = latest, updated, error
        if path == '/':
            payload, mime, code = PAGE, 'text/html; charset=utf-8', 200
        elif path == '/status':
            payload = json.dumps({'ready':data is not None,'age':time.monotonic()-stamp if stamp else None,'error':message}).encode()
            mime, code = 'application/json', 200
        elif path == '/frame.jpg' and data:
            payload, mime, code = data, 'image/jpeg', 200
        else:
            payload, mime, code = b'Frame unavailable', 'text/plain', 404
        self.send_response(code)
        self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(payload)))
        self.send_header('Cache-Control','no-store')
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
    def log_message(self,*args):
        pass

if __name__ == '__main__':
    server=ThreadingHTTPServer(('127.0.0.1',8765),Handler)
    threading.Thread(target=receive,daemon=True).start()
    timer=threading.Timer(1800,server.shutdown)
    timer.daemon=True
    timer.start()
    print('Viewer http://127.0.0.1:8765 — auto-stop in 30 minutes',flush=True)
    try:
        server.serve_forever()
    finally:
        stop.set()
        timer.cancel()
        server.server_close()
