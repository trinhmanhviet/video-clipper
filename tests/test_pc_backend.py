import json
import shutil
import time
import unittest
import uuid
from pathlib import Path

from studio import create_app


class PCBackendTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).parent / '.tmp' / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.root)
        self.app = create_app(self.root, start_worker=False)
        self.client = self.app.test_client()

    def test_health_identifies_pc_backend(self):
        self.assertEqual(self.client.get('/api/health').json['backend'], 'pc-v2')

    def test_arbitrary_server_paths_are_not_accepted_as_media(self):
        r = self.client.post('/api/jobs', json={'media_id': '../../app.py', 'start': 0, 'end': 1})
        self.assertEqual(r.status_code, 404)

    def test_jobs_survive_application_reload(self):
        store = self.app.extensions['store']
        media = store.add_media('demo.mp4', 'fixture.mp4', {'duration': 10, 'fps': 30, 'width': 640, 'height': 360})
        r = self.client.post('/api/jobs', json={'media_id': media['id'], 'start': 1, 'end': 2})
        self.assertEqual(r.status_code, 202)
        again = create_app(self.root, start_worker=False).test_client()
        recovered = again.get('/api/jobs/' + r.json['id'])
        self.assertEqual(recovered.json['status'], 'queued')
        self.assertEqual(recovered.json['params']['start'], 1)

    def test_range_outside_video_is_rejected_before_queueing(self):
        store = self.app.extensions['store']
        media = store.add_media('demo.mp4', 'fixture.mp4', {'duration': 3, 'fps': 30})
        for start, end in [(2, 1), (-1, 2), (0, 5), (0, float('inf'))]:
            r = self.client.post('/api/jobs', json={'media_id': media['id'], 'start': start, 'end': end})
            self.assertEqual(r.status_code, 400, (start, end, r.json))

    def test_progress_and_cancel_are_persisted(self):
        store = self.app.extensions['store']
        job = store.add_job('export', {'start': 0, 'end': 1})
        store.update_job(job['id'], status='processing', progress=42, message='Encoding')
        self.assertEqual(self.client.get('/api/jobs/' + job['id']).json['progress'], 42)
        r = self.client.post('/api/jobs/' + job['id'] + '/cancel')
        self.assertTrue(r.json['cancel_requested'])

    def test_chunk_upload_enforces_next_offset(self):
        r = self.client.post('/api/uploads', json={'name': 'demo.mp4', 'size': 10})
        self.assertEqual(r.status_code, 201)
        upload = r.json['id']
        r = self.client.put('/api/uploads/' + upload + '?offset=5', data=b'abc', content_type='application/octet-stream')
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json['offset'], 0)
        r = self.client.put('/api/uploads/' + upload + '?offset=0', data=b'abc', content_type='application/octet-stream')
        self.assertEqual(r.json['offset'], 3)


if __name__ == '__main__':
    unittest.main()
