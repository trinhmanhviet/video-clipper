import json
import subprocess
import shutil
import uuid
import os
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import app


class ProcessingTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).parent / '.tmp'
        base.mkdir(exist_ok=True)
        self.directory = base / uuid.uuid4().hex
        self.directory.mkdir()
        self.addCleanup(shutil.rmtree, self.directory)
        self.outputs = patch.object(app, 'OUTPUTS_DIR', self.directory / 'outputs')
        self.outputs.start()
        self.addCleanup(self.outputs.stop)
        for name in ('UPLOADS_DIR', 'THUMBS_DIR'):
            directory = self.directory / name.lower()
            directory.mkdir()
            patcher = patch.object(app, name, directory)
            patcher.start()
            self.addCleanup(patcher.stop)
        app.tasks['test'] = {'status': 'pending', 'message': '', 'result': None}
        self.source = self.directory / 'input.mp4'
        self.source.write_bytes(b'fixture')

    def run_worker(self, **extra):
        params = dict(source=str(self.source), is_local=True, title='test',
                      start_time='0', end_time='1', format_id='original')
        params.update(extra)
        app.process_worker('test', params)
        return app.tasks['test']

    def test_failure_shows_cause_instead_of_ffmpeg_banner(self):
        stderr = 'ffmpeg version 7.1.5\nconfiguration: ' + 'x' * 600 + '\nError opening input file: No such file or directory\n'
        with patch.object(app.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', stderr)):
            task = self.run_worker()
        self.assertEqual(task['status'], 'error')
        self.assertIn('No such file or directory', task['message'])
        self.assertNotIn('ffmpeg version', task['message'])

    def test_deleted_upload_has_actionable_error_without_launching_ffmpeg(self):
        self.source.unlink()
        with patch.object(app.subprocess, 'run') as run:
            task = self.run_worker()
        self.assertEqual(task['status'], 'error')
        self.assertIn('tải lại', task['message'].lower())
        run.assert_not_called()

    def test_encoder_threads_are_limited_on_output_not_only_input(self):
        calls = []
        def run(cmd, **kwargs):
            calls.append(cmd)
            Path(cmd[-1]).write_bytes(b'encoded')
            return subprocess.CompletedProcess(cmd, 0, '', '')
        with patch.object(app.subprocess, 'run', side_effect=run):
            task = self.run_worker()
        self.assertEqual(task['status'], 'completed')
        cmd = calls[0]
        self.assertIn('-hide_banner', cmd)
        self.assertIn('-threads:v', cmd)
        self.assertGreater(cmd.index('-threads:v'), cmd.index('-i'))
        self.assertEqual(cmd[cmd.index('-threads:v') + 1], '2')

    def test_failed_frame_extraction_never_returns_empty_success_zip(self):
        def run(cmd, **kwargs):
            if any('frame_%05d' in arg for arg in cmd):
                return subprocess.CompletedProcess(cmd, 1, '', 'Error: frame extraction failed')
            Path(cmd[-1]).write_bytes(b'encoded')
            return subprocess.CompletedProcess(cmd, 0, '', '')
        with patch.object(app.subprocess, 'run', side_effect=run):
            task = self.run_worker(extract_frames=True)
        self.assertEqual(task['status'], 'error')
        self.assertIn('frame extraction failed', task['message'])

    def test_invalid_time_range_fails_before_processing(self):
        with patch.object(app.subprocess, 'run') as run:
            task = self.run_worker(start_time='5', end_time='2')
        self.assertEqual(task['status'], 'error')
        run.assert_not_called()

    def test_cleanup_preserves_files_in_use_and_releases_them_afterward(self):
        source = app.UPLOADS_DIR / ('test_' + uuid.uuid4().hex + '.mp4')
        source.write_bytes(b'fixture')
        self.addCleanup(source.unlink, missing_ok=True)
        def run(cmd, **kwargs):
            os.utime(source, (1, 1))
            app.cleanup_expired_files(time.time() - 3600)
            self.assertTrue(source.exists(), 'Cleanup removed the active source')
            Path(cmd[-1]).write_bytes(b'encoded')
            return subprocess.CompletedProcess(cmd, 0, '', '')
        with patch.object(app.subprocess, 'run', side_effect=run):
            task = self.run_worker(source=str(source))
        self.assertEqual(task['status'], 'completed')
        self.assertNotIn(source.resolve(), app.active_paths)

    def test_successful_ffmpeg_with_zero_extracted_frames_is_an_error(self):
        def run(cmd, **kwargs):
            if not any('frame_%05d' in arg for arg in cmd):
                Path(cmd[-1]).write_bytes(b'encoded')
            return subprocess.CompletedProcess(cmd, 0, '', '')
        with patch.object(app.subprocess, 'run', side_effect=run):
            task = self.run_worker(extract_frames=True)
        self.assertEqual(task['status'], 'error')

    def test_silent_killed_encoder_explains_resource_exit(self):
        with patch.object(app.subprocess, 'run', return_value=subprocess.CompletedProcess([], -9, '', '')):
            task = self.run_worker()
        self.assertEqual(task['status'], 'error')
        self.assertIn('bộ nhớ', task['message'])

    def test_same_upload_stays_protected_until_both_jobs_finish(self):
        nested = [False]
        def run(cmd, **kwargs):
            if not nested[0]:
                nested[0] = True
                app.tasks['second'] = dict(status='pending', message='', result=None)
                app.process_worker('second', dict(source=str(self.source), is_local=True,
                                   start_time='0', end_time='1', title='second'))
                self.assertIn(self.source.resolve(), app.active_paths)
            Path(cmd[-1]).write_bytes(b'encoded')
            return subprocess.CompletedProcess(cmd, 0, '', '')
        with patch.object(app.subprocess, 'run', side_effect=run):
            task = self.run_worker()
        self.assertEqual(task['status'], 'completed', task['message'])
        self.assertNotIn(self.source.resolve(), app.active_paths)


if __name__ == '__main__':
    unittest.main()
