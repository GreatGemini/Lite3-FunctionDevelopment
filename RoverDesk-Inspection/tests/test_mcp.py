import sys,site,time,tempfile,json,asyncio,unittest,urllib.request,urllib.error,socket
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];site.addsitedir(str(ROOT/'vendor'));sys.path.insert(0,str(ROOT/'vendor'));sys.path.insert(0,str(ROOT))
from rover.adapters import Runtime
from rover.mcp_bridge import MCPBridge
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
import httpx2
class MCPTests(unittest.TestCase):
    def test_readonly_authenticated_mcp(self):
        with tempfile.TemporaryDirectory() as d:
            runtime=Runtime(Path(d)/'known_hosts');runtime.store.update({'basic':1},'test')
            with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            bridge=MCPBridge(runtime,d,port);bridge.start()
            try:
                for _ in range(100):
                    if bridge.state=='运行中':break
                    if bridge.state=='启动失败':self.fail(bridge.detail)
                    time.sleep(.1)
                # Wait for ASGI lifespan as well as socket bind.
                time.sleep(.5)
                url=f'http://127.0.0.1:{port}/mcp'
                with self.assertRaises(urllib.error.HTTPError) as cm:urllib.request.urlopen(url,timeout=3)
                self.assertEqual(cm.exception.code,401)
                async def run():
                    http=httpx2.AsyncClient(headers={'Authorization':'Bearer '+bridge.token})
                    async with http, Client(streamable_http_client(url,http_client=http)) as client:
                        tools=await client.list_tools()
                        names={t.name for t in tools.tools}
                        self.assertEqual(names,{'list_robots','get_robot_state','get_joint_states','get_diagnostics','get_camera_frame'})
                        result=await client.call_tool('get_robot_state',{})
                        data=result.structured_content
                        self.assertTrue(data['read_only']);self.assertEqual(data['fields']['basic']['value'],1)
                        self.assertFalse(data['capabilities']['motion_control'])
                        camera=await client.call_tool('get_camera_frame',{})
                        self.assertTrue(camera.is_error)
                asyncio.run(run())
            finally:bridge.stop()
if __name__=='__main__':unittest.main()
