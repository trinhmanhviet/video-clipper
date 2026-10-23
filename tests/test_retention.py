import os
import shutil
import uuid
import unittest
from pathlib import Path

from retention import Retention
from store import Store


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).parent / '.tmp' / ('retention-' + uuid.uuid4().hex)
        self.root.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.root)
        self.store = Store(self.root)
        self.retention = Retention(self.store, seconds=600, clock=lambda: 2000)

    def old(self, table, item, **changes):
        item.update(created=1000, last_access=1000, **changes)
        self.store.put(table, item)
        return item

    def media(self):
        path = self.store.root / 'media' / (uuid.uuid4().hex + '.mp4')
        path.write_bytes(b'video')
        item = self.store.add_media('sample.mp4', path.name, {'duration': 5})
        return self.old('media', item), path

    def job(self, media, status='completed'):
        item = self.store.add_job('export', {'media_id': media['id']})
        folder = self.store.root / 'jobs' / item['id']
        (folder / 'frames').mkdir(parents=True)
        (folder / 'clip.mp4').write_bytes(b'output')
        (folder / 'frames' / 'frame.png').write_bytes(b'frame')
        (folder / 'frames.zip').write_bytes(b'zip')
        return self.old('jobs', item, status=status, finished=1000), folder

    def test_expired_source_outputs_frames_and_zip_are_deleted(self):
        media, source = self.media()
        job, folder = self.job(media)
        self.retention.cleanup()
        self.assertFalse(source.exists())
        self.assertFalse(folder.exists())
        self.assertTrue(self.store.get('media', media['id'])['expired'])
        self.assertEqual(self.store.get('jobs', job['id'])['status'], 'expired')

    def test_queued_and_processing_jobs_keep_their_source(self):
        for state in ('queued', 'processing'):
            with self.subTest(state=state):
                media, source = self.media()
                job, folder = self.job(media, state)
                self.retention.cleanup()
                self.assertTrue(source.exists())
                self.assertTrue(folder.exists())
                self.store.update_job(job['id'], status='cancelled')

    def test_download_lease_protects_output_and_source_then_restarts_timer(self):
        media, source = self.media()
        job, folder = self.job(media)
        _, release = self.retention.acquire('jobs', job['id'])
        self.retention.cleanup(now=4000)
        self.assertTrue(folder.exists())
        self.assertTrue(source.exists())
        self.retention.clock = lambda: 4000
        release()
        release()  # safe when a response is closed more than once
        self.retention.cleanup(now=4599)
        self.assertTrue(source.exists())
        self.retention.cleanup(now=4601)
        self.assertFalse(source.exists())
        self.assertFalse(folder.exists())

    def test_source_stream_lease_protects_source(self):
        media, source = self.media()
        _, release = self.retention.acquire('media', media['id'])
        self.retention.cleanup(now=4000)
        self.assertTrue(source.exists())
        release()

    def test_recent_use_and_recent_completion_preserve_media(self):
        media, source = self.media()
        self.retention.touch('media', media['id'])
        self.retention.cleanup(now=2599)
        self.assertTrue(source.exists())
        job, folder = self.job(media)
        self.store.update_job(job['id'], finished=2500)
        self.retention.cleanup(now=3000)
        self.assertTrue(source.exists())
        self.assertTrue(folder.exists())

    def test_stale_partial_upload_and_failed_import_orphans_are_removed(self):
        for parent, name in [('uploads', 'orphan.part'), ('media', 'orphan.mp4.part')]:
            path = self.store.root / parent / name
            path.write_bytes(b'partial')
            os.utime(path, (1000, 1000))
        self.retention.cleanup()
        self.assertEqual(list((self.store.root / 'uploads').iterdir()), [])
        self.assertEqual(list((self.store.root / 'media').iterdir()), [])

    def test_live_import_fragments_are_preserved(self):
        job = self.old('jobs', self.store.add_job('import', {'url': 'https://example.com/v'}), status='processing')
        path = self.store.root / 'media' / (job['id'] + '.mp4.part')
        path.write_bytes(b'downloading')
        os.utime(path, (1000, 1000))
        self.retention.cleanup()
        self.assertTrue(path.exists())

    def test_recent_upload_activity_keeps_partial_file(self):
        item = {'id': 'a' * 32, 'created': 1000, 'last_access': 1000, 'size': 10}
        self.store.put('uploads', item)
        path = self.store.root / 'uploads' / (item['id'] + '.part')
        path.write_bytes(b'part')
        os.utime(path, (1000, 1000))
        self.retention.touch('uploads', item['id'])
        self.retention.cleanup()
        self.assertTrue(path.exists())
        self.retention.cleanup(now=2601)
        self.assertFalse(path.exists())

    def test_outside_storage_path_is_never_deleted(self):
        outside = self.root.parent / ('outside-' + self.root.name + '.mp4')
        outside.write_bytes(b'preserve')
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        item = self.store.add_media('outside.mp4', str(outside), {})
        self.old('media', item)
        self.retention.cleanup()
        self.assertTrue(outside.exists())

    def test_metadata_status_reads_do_not_extend_expiry(self):
        media, source = self.media()
        job, folder = self.job(media)
        for _ in range(3):
            self.store.get('jobs', job['id'])
        self.retention.cleanup()
        self.assertFalse(folder.exists())

    def test_legacy_records_receive_grace_once_without_reviving_expired_files(self):
        media, source = self.media()
        del media['last_access']
        self.store.put('media', media)
        self.retention.grant_legacy_grace()
        self.assertEqual(self.store.get('media', media['id'])['last_access'], 2000)
        self.retention.clock = lambda: 2500
        self.retention.grant_legacy_grace()
        self.assertEqual(self.store.get('media', media['id'])['last_access'], 2000)
        self.retention.cleanup(now=2601)
        self.retention.grant_legacy_grace()
        self.assertFalse(source.exists())
        self.assertTrue(self.store.get('media', media['id'])['expired'])

    def http_client(self):
        from studio import create_app
        app = create_app(self.root, start_worker=False)
        self.store = app.extensions['store']
        self.retention = app.extensions['retention']
        self.retention.clock = lambda: 2000
        return app.test_client()

    def test_http_stream_is_protected_until_response_close(self):
        client = self.http_client()
        media, source = self.media()
        response = client.get('/api/media/' + media['id'] + '/stream', buffered=False)
        self.assertEqual(response.status_code, 200)
        self.retention.cleanup(now=4000)
        self.assertTrue(source.exists())
        self.retention.clock = lambda: 4000
        response.close()
        self.assertFalse(self.retention.active)
        self.retention.cleanup(now=4601)
        self.assertFalse(source.exists())

    def test_http_expiry_returns_terminal_job_and_actionable_download_error(self):
        client = self.http_client()
        media, _ = self.media()
        job, _ = self.job(media)
        client.get('/api/jobs/' + job['id'])  # polling must not renew retention
        self.retention.cleanup()
        self.assertEqual(client.get('/api/jobs/' + job['id']).json['status'], 'expired')
        response = client.get('/api/jobs/' + job['id'] + '/files/clip.mp4')
        self.assertEqual(response.status_code, 410)
        self.assertIn('10 phút', response.json['error'])

    def test_http_user_activity_renews_source_and_health_reports_600_seconds(self):
        client = self.http_client()
        media, source = self.media()
        self.assertEqual(client.post('/api/media/' + media['id'] + '/touch').status_code, 200)
        self.retention.cleanup(now=2599)
        self.assertTrue(source.exists())
        self.assertEqual(client.get('/api/health').json['retention_seconds'], 600)

