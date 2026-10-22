"""Exercise actual FFmpeg cut, MP3 conversion, frame archive and invalid input."""
import json
import shutil
import subprocess
import unittest
import uuid
import zipfile
from pathlib import Path
from unittest.mock import patch

import app


@unittest.skipUnless(app.FFMPEG_PATH and app.FFPROBE_PATH, 'FFmpeg/FFprobe required')
class MediaIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(__file__).parent / '.tmp' / uuid.uuid4().hex
        self.directory.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.directory)
        patcher = patch.object(app, 'OUTPUTS_DIR', self.directory / 'outputs')
        patcher.start()
        self.addCleanup(patcher.stop)

    def source(self, size='1280x720'):
        path = self.directory / 'source.mp4'
        subprocess.run([app.FFMPEG_PATH, '-hide_banner', '-loglevel', 'error', '-y',
                        '-f', 'lavfi', '-i', f'testsrc2=size={size}:rate=12',
                        '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=44100',
                        '-t', '1.5', '-c:v', 'libx264', '-threads:v', '2', '-preset', 'ultrafast',
                        '-c:a', 'aac', str(path)], check=True, capture_output=True)
        return path

    def process(self, source, **extra):
        task_id = uuid.uuid4().hex
        app.tasks[task_id] = dict(status='pending', message='', result=None)
        params = dict(source=str(source), is_local=True, start_time='0.25', end_time='1.25',
                      format_id='original', title='integration')
        params.update(extra)
        app.process_worker(task_id, params)
        task = app.tasks[task_id]
        self.assertEqual(task['status'], 'completed', task['message'])
        result = task['result']
        folder = app.OUTPUTS_DIR / result['run_folder']
        output = folder / result['video_file']
        probe = subprocess.run([app.FFPROBE_PATH, '-v', 'error', '-show_entries',
                                'format=duration:stream=codec_name,width,height', '-of', 'json', str(output)],
                               check=True, capture_output=True, text=True)
        return result, folder, json.loads(probe.stdout)

    def test_cut_and_frames_archive_is_real_and_has_correct_duration(self):
        result, folder, probe = self.process(self.source(), extract_frames=True, frame_fps='6')
        self.assertAlmostEqual(float(probe['format']['duration']), 1, delta=.12)
        self.assertEqual(probe['streams'][0]['codec_name'], 'h264')
        self.assertEqual(result['frames_count'], 6)
        with zipfile.ZipFile(folder / result['frames_zip']) as archive:
            self.assertEqual(len(archive.namelist()), 6)
            self.assertEqual(archive.testzip(), None)

    def test_mp3_export(self):
        result, folder, probe = self.process(self.source(), format_id='mp3')
        self.assertEqual(probe['streams'][0]['codec_name'], 'mp3')
        self.assertAlmostEqual(float(probe['format']['duration']), 1, delta=.12)
        self.assertIsNone(result['frames_zip'])

    def test_4k_cut_with_bounded_encoder(self):
        result, folder, probe = self.process(self.source('3840x2160'))
        self.assertEqual(probe['streams'][0]['width'], 3840)
        self.assertEqual(probe['streams'][0]['height'], 2160)

    def test_invalid_media_surfaces_actual_decoder_error(self):
        source = self.directory / 'broken.mp4'
        source.write_bytes(b'not a media file')
        task_id = uuid.uuid4().hex
        app.tasks[task_id] = dict(status='pending', message='', result=None)
        app.process_worker(task_id, dict(source=str(source), is_local=True, start_time='0', end_time='1'))
        task = app.tasks[task_id]
        self.assertEqual(task['status'], 'error')
        self.assertNotIn('ffmpeg version', task['message'])
        self.assertTrue('Invalid data' in task['message'] or 'moov atom not found' in task['message'], task['message'])
