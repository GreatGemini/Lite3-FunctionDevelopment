import io
import json
import site
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
site.addsitedir(str(ROOT/'vendor'))
sys.path.insert(0, str(ROOT))
from PIL import Image
from rover.inspection import (InspectionSession, InspectionError, VisionClient,
                              prepare_image, report_html, validate_report)


def photo():
    image = Image.effect_noise((320, 240), 80).convert('RGB')
    buffer = io.BytesIO()
    image.save(buffer, 'JPEG')
    return buffer.getvalue()


def inventory(ids=('F001',)):
    return {'summary': '测试场景，仅测试数据', 'items': [{
        'name': '椅子', 'category': '家具', 'description': '有靠背', 'color': '黑色',
        'visible_text': '', 'location': '画面左侧', 'count_min': 1, 'confidence': '高',
        'evidence_frame_ids': list(ids), 'uncertainties': '跨帧数量未确认',
    }], 'limitations': ['测试样例，不代表实际房间。']}


class Response:
    def __init__(self, payload):
        self.payload = payload
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, *args): return json.dumps(self.payload).encode()


class FakeClient:
    def __init__(self, api_key, model): self.api_key, self.model = api_key, model
    def analyze(self, frames, directory):
        result = inventory([f['id'] for f in frames])
        result['model'] = self.model
        return result


class InspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.now = time.time()
        self.data = photo()
        self.frame = (self.data, self.now, '320x240')
        self.session = InspectionSession(self.temp.name, lambda: self.frame, FakeClient, clock=lambda: self.now)
    def tearDown(self):
        if self.session.thread and self.session.thread.is_alive():
            self.session.cancel()
            self.session.thread.join(2)
        self.temp.cleanup()
    def initialized(self):
        self.session._initialize(5, 20, 'fake-model')

    def test_no_camera_rejects_before_creating_session(self):
        self.frame = (None, 0, '')
        with self.assertRaises(InspectionError): self.session.start('fake-key')
        self.assertIsNone(self.session.directory)

    def test_freshness_reused_frames_duplicate_and_blur(self):
        self.initialized()
        self.assertTrue(self.session.sample())
        self.assertFalse(self.session.sample())
        self.now += 5
        self.frame = (self.data, self.now, '')
        self.assertFalse(self.session.sample())
        self.assertEqual(self.session.skipped['duplicate'], 1)
        self.frame = (self.data, self.now-4, '')
        self.assertFalse(self.session.sample())
        blank = io.BytesIO()
        Image.new('RGB', (320, 240), 'black').save(blank, 'JPEG')
        self.now += 5
        self.frame = (blank.getvalue(), self.now, '')
        self.assertFalse(self.session.sample())
        self.assertEqual(self.session.skipped['blur'], 1)
        self.assertEqual(len(self.session.frames), 1)

    def test_invalid_images_and_configuration(self):
        with self.assertRaises(InspectionError): prepare_image(b'not a picture')
        for interval, limit in ((1, 20), (5, 25), (True, 20)):
            with self.assertRaises(InspectionError): self.session._initialize(interval, limit, 'fake')

    def test_image_limit_automatically_finishes_and_persists_report(self):
        self.session.start('do-not-persist', limit=1)
        self.session.thread.join(3)
        snap = self.session.snapshot()
        self.assertEqual(snap['state'], 'complete')
        self.assertEqual(len(snap['frames']), 1)
        self.assertTrue((self.session.directory/'report.html').exists())
        self.assertTrue((self.session.directory/'frames/F001.jpg').exists())
        contents = ''.join(p.read_text(encoding='utf-8') for p in self.session.directory.glob('*.json'))
        self.assertNotIn('do-not-persist', contents)
        self.assertEqual(json.loads((self.session.directory/'session.json').read_text(encoding='utf-8'))['mode'], 'manual')

    def test_finish_empty_capture_is_actionable_error(self):
        self.initialized()
        with self.assertRaisesRegex(InspectionError, '没有采到'): self.session._analyze(FakeClient('key','model'))

    def test_import_does_not_require_robot_and_retains_identical_images(self):
        path = Path(self.temp.name)/'source.jpg'
        path.write_bytes(self.data)
        self.frame = (None, 0, '')
        self.session.import_and_analyze([str(path), str(path)], 'fake-key')
        self.session.thread.join(3)
        self.assertEqual(self.session.state, 'complete')
        self.assertEqual(len(self.session.frames), 2)

    def test_rejects_nonexistent_evidence_and_bad_counts(self):
        with self.assertRaisesRegex(InspectionError, '不存在'): validate_report(inventory(('F002',)), {'F001'})
        for count in (0, -1, True, 1.5):
            result = inventory()
            result['items'][0]['count_min'] = count
            with self.assertRaises(InspectionError): validate_report(result, {'F001'})

    def test_html_escapes_model_text_and_preserves_evidence(self):
        result = inventory()
        result['summary'] = '<script>alert(1)</script>'
        output = report_html(result, [{'id':'F001','file':'frames/F001.jpg','captured_at':'test'}])
        self.assertNotIn('<script>', output)
        self.assertIn('&lt;script&gt;', output)
        self.assertIn('href="#frame-F001"', output)
        self.assertIn('src="frames/F001.jpg"', output)

    def test_api_payload_image_and_schema_and_store_false(self):
        self.initialized()
        self.session.sample()
        requests = []
        def transport(request, timeout):
            requests.append(request)
            return Response({'status':'completed','output':[{'type':'message','content':[
                {'type':'output_text','text':json.dumps(inventory())}]}], 'usage':{'input_tokens':3}})
        client = VisionClient('test-secret', 'test-model', transport)
        result = client.analyze(self.session.frames, self.session.directory)
        payload = json.loads(requests[0].data)
        self.assertEqual(requests[0].full_url, 'https://api.openai.com/v1/responses')
        self.assertFalse(payload['store'])
        self.assertTrue(payload['text']['format']['strict'])
        self.assertTrue(payload['input'][0]['content'][2]['image_url'].startswith('data:image/jpeg;base64,'))
        self.assertNotIn('test-secret', json.dumps(result))
        self.assertEqual(result['usage']['input_tokens'], 3)

    def test_api_errors_do_not_echo_secrets(self):
        self.initialized()
        self.session.sample()
        def transport(request, timeout):
            raise HTTPError(request.full_url, 401, 'test-secret', {}, None)
        with self.assertRaises(InspectionError) as caught:
            VisionClient('test-secret','model',transport).analyze(self.session.frames,self.session.directory)
        self.assertNotIn('test-secret', str(caught.exception))

    def test_incomplete_or_refused_response_not_reported_as_success(self):
        self.initialized()
        self.session.sample()
        for payload in (
            {'status':'incomplete'},
            {'status':'completed','output':[{'content':[{'type':'refusal'}]}]},
            {'status':'completed','output':[{'content':[{'type':'output_text','text':'bad json'}]}]},
        ):
            with self.assertRaises(InspectionError):
                VisionClient('key','model',lambda *a, **k: Response(payload)).analyze(self.session.frames,self.session.directory)

    def test_cancel_inflight_analysis_does_not_publish_report(self):
        started, release = threading.Event(), threading.Event()
        class SlowClient(FakeClient):
            def analyze(self, frames, directory):
                started.set()
                release.wait(2)
                return super().analyze(frames, directory)
        self.session.client_factory = SlowClient
        self.session.start('key', limit=1)
        self.assertTrue(started.wait(2))
        self.session.cancel()
        release.set()
        self.session.thread.join(2)
        self.assertEqual(self.session.state, 'cancelled')
        self.assertIsNone(self.session.report)
        self.assertFalse((self.session.directory/'report.json').exists())

    def test_network_failure_preserves_frames_for_retry(self):
        class FailedClient(FakeClient):
            def analyze(self, *args): raise InspectionError('网络失败')
        self.session.client_factory = FailedClient
        self.session.start('key', limit=1)
        self.session.thread.join(2)
        self.assertEqual(self.session.state, 'error')
        self.assertEqual(len(self.session.frames), 1)
        self.session.client_factory = FakeClient
        self.session.retry('new-key')
        self.session.thread.join(2)
        self.assertEqual(self.session.state, 'complete')


if __name__ == '__main__': unittest.main()
