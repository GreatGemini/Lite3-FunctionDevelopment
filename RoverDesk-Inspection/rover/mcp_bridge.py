"""Embedded, loopback-only, token-authenticated MCP service. Read-only tools."""
import base64
import json
import secrets
import socket
import threading
import time
from pathlib import Path
from typing import Any

class MCPBridge:
    def __init__(self,runtime,data_dir,port=8766):
        self.runtime=runtime;self.port=port;self.server=None;self.state='未启动';self.detail=''
        token_file=Path(data_dir)/'mcp-token.txt'
        if not token_file.exists():token_file.write_text(secrets.token_urlsafe(32),encoding='utf-8')
        self.token=token_file.read_text(encoding='utf-8').strip()
    def config(self):
        return {'mcpServers':{'rover-desk':{'url':f'http://127.0.0.1:{self.port}/mcp','headers':{'Authorization':'Bearer '+self.token}}}}
    def start(self):
        threading.Thread(target=self._safe_run,daemon=True).start()
    def _safe_run(self):
        try:self._run()
        except Exception as e:self.state="启动失败";self.detail=str(e)
    def _run(self):
        import uvicorn
        from mcp.server import MCPServer
        from mcp_types import ToolAnnotations,CallToolResult,ImageContent,TextContent
        mcp=MCPServer('Rover Desk',version='0.1.0',instructions='只读机器狗状态。必须查看每项 status 和 age_seconds；过期数据不代表当前状态。此服务没有运动控制能力。')
        ann=ToolAnnotations(readOnlyHint=True,destructiveHint=False,idempotentHint=True,openWorldHint=False)
        @mcp.tool(annotations=ann,structured_output=True)
        def list_robots()->dict[str,Any]:
            """List the selected robot and implemented adapters/capabilities."""
            s=self.runtime.snapshot()
            return {'robot':s['robot'],'capabilities':s['capabilities']}
        @mcp.tool(annotations=ann,structured_output=True)
        def get_robot_state()->dict[str,Any]:
            """Read every field with validity, source, units and freshness."""
            return self.runtime.snapshot()
        @mcp.tool(annotations=ann,structured_output=True)
        def get_joint_states()->dict[str,Any]:
            """Read all 12 joints: position, velocity, torque and temperature."""
            s=self.runtime.snapshot()
            return {k:v for k,v in s['fields'].items() if k.startswith('joint.')}
        @mcp.tool(annotations=ann,structured_output=True)
        def get_diagnostics()->dict[str,Any]:
            """Read connections, service status and bounded local diagnostic events."""
            s=self.runtime.snapshot()
            return {k:s[k] for k in ('connections','metadata','packet_counts','events')}
        @mcp.tool(annotations=ann,structured_output=False)
        def get_camera_frame()->CallToolResult:
            """Read latest camera JPEG. Refuses a stale frame older than 3 seconds."""
            data,stamp,size=self.runtime.camera_frame()
            if not data or time.time()-stamp>3:
                return CallToolResult(content=[TextContent(type='text',text='摄像头无实时画面或画面已过期')],isError=True)
            return CallToolResult(content=[TextContent(type='text',text=json.dumps({'captured_at':stamp,'resolution':size})),ImageContent(type='image',data=base64.b64encode(data).decode(),mimeType='image/jpeg')])
        @mcp.resource('robot://current/state',mime_type='application/json')
        def state_resource()->str:return json.dumps(self.runtime.snapshot(),ensure_ascii=False)
        app=mcp.streamable_http_app(json_response=True,stateless_http=True,host='127.0.0.1')
        token=self.token
        class Guard:
            async def __call__(self,scope,receive,send):
                if scope['type']=='http':
                    h={k.lower():v for k,v in scope.get('headers',[])}
                    expected=('Bearer '+token).encode()
                    if not secrets.compare_digest(h.get(b'authorization',b''),expected):
                        await send({'type':'http.response.start','status':401,'headers':[(b'content-type',b'text/plain')]})
                        await send({'type':'http.response.body','body':b'Unauthorized'});return
                await app(scope,receive,send)
        try:
            sock=socket.socket();sock.bind(('127.0.0.1',self.port));sock.listen(64)
            self.server=uvicorn.Server(uvicorn.Config(Guard(),host='127.0.0.1',port=self.port,log_level='error',log_config=None,access_log=False))
            self.state='运行中';self.detail=f'127.0.0.1:{self.port}/mcp · 只读'
            self.server.run(sockets=[sock])
            sock.close();self.state='已停止'
        except Exception as e:self.state='启动失败';self.detail=str(e)
    def stop(self):
        if self.server:self.server.should_exit=True
