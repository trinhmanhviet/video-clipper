import io
import json
import shutil
import subprocess
import sys
import time
import unittest
import uuid
import zipfile
from pathlib import Path

from processing import Cancelled, binary, export_job, probe, run_process
from studio import create_app


class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).parent / '.tmp' / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.root)

    def test_silent_subprocess_times_out(self):
        before = time.monotonic()
        with self.assertRaises(TimeoutError):
            run_process([sys.executable, '-c', 'import time;time.sleep(30)'], self.root/'timeout.log', .3, lambda:False)
        self.assertLess(time.monotonic()-before, 3)

    def test_silent_subprocess_can_be_cancelled(self):
        with self.assertRaises(Cancelled):
            run_process([sys.executable, '-c', 'import time;time.sleep(30)'], self.root/'cancel.log', 30, lambda:True)

    def test_exact_trim_frames_and_reduced_resolution(self):
        app = create_app(self.root, start_worker=False)
        store = app.extensions['store']
        source = self.root/'media'/'test.mp4'
        subprocess.run([binary('ffmpeg'), '-hide_banner', '-loglevel', 'error', '-y', '-f','lavfi',
                        '-i','testsrc2=size=640x360:rate=12','-t','2','-c:v','libx264','-threads','2',str(source)],
                       capture_output=True,check=True)
        media = store.add_media('test.mp4',source.name,probe(source))
        job = store.add_job('export', dict(media_id=media['id'],start=.25,end=1.25,format='mp4',
                           frames=True,fps=6,frame_format='jpg',height=480))
        result = export_job(store,job)
        info = probe(self.root/'jobs'/job['id']/result['video'])
        self.assertAlmostEqual(info['duration'],1,delta=.1)
        self.assertEqual(info['height'],360)  # never upscale
        self.assertEqual(result['frames_count'],6)
        with zipfile.ZipFile(self.root/'jobs'/job['id']/result['frames']) as z:
            self.assertIsNone(z.testzip())
            self.assertEqual(len(z.namelist()),6)

    def test_real_chunked_http_upload_preview_and_export_metadata(self):
        app=create_app(self.root,start_worker=False);client=app.test_client()
        source=self.root/'input.mp4'
        subprocess.run([binary('ffmpeg'),'-hide_banner','-loglevel','error','-y','-f','lavfi',
                        '-i','color=size=320x240:rate=12','-t','1','-c:v','libx264','-threads','2',str(source)],
                       capture_output=True,check=True)
        data=source.read_bytes();r=client.post('/api/uploads',json={'name':'demo.mp4','size':len(data)})
        ident=r.json['id']
        for offset in range(0,len(data),1024):
            r=client.put(f'/api/uploads/{ident}?offset={offset}',data=data[offset:offset+1024])
            self.assertEqual(r.status_code,200)
        media=client.post(f'/api/uploads/{ident}/complete',json={}).json
        self.assertNotIn('path',media)
        response=client.get(media['stream_url'],headers={'Range':'bytes=0-99'})
        self.assertEqual(response.status_code,206)
        self.assertEqual(len(response.data),100)
        response.close()
        self.assertEqual(client.post('/api/jobs',json={'media_id':media['id'],'start':0,'end':.5}).status_code,202)
