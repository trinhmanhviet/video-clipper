"""Idle file retention; active jobs and open HTTP responses are never swept."""
import logging
import os
import shutil
import stat
import threading
import time
from collections import Counter
from pathlib import Path


class Expired(LookupError):
    pass


class Retention:
    def __init__(self, store, seconds=600, clock=time.time):
        self.store, self.seconds, self.clock = store, seconds, clock
        self.active = Counter()
        self.thread = None

    def records(self, table):
        import json
        with self.store.connect() as c:
            return [json.loads(row[0]) for row in c.execute(f'SELECT data FROM {table}')]

    @staticmethod
    def last_use(item):
        return max(item.get('created') or 0, item.get('finished') or 0, item.get('last_access') or 0)

    def grant_legacy_grace(self):
        with self.store.lock:
            for table in ('media', 'jobs', 'uploads'):
                for item in self.records(table):
                    if 'last_access' not in item and not item.get('expired') and item.get('status') != 'expired':
                        item['last_access'] = self.clock()
                        self.store.put(table, item)

    def touch(self, table, ident):
        with self.store.lock:
            item = self.store.get(table, ident)
            if not item:
                raise KeyError(ident)
            if item.get('expired') or item.get('status') == 'expired':
                raise Expired('File đã tự xoá sau 10 phút không sử dụng. Hãy chọn video hoặc xuất lại.')
            item['last_access'] = self.clock()
            self.store.put(table, item)
            media_id = item.get('params', {}).get('media_id') if table == 'jobs' else item.get('media_id')
            if media_id:
                parent = self.store.get('media', media_id)
                if parent and not parent.get('expired'):
                    parent['last_access'] = self.clock()
                    self.store.put('media', parent)
            return item

    def acquire(self, table, ident):
        with self.store.lock:
            item = self.touch(table, ident)
            self.active[table, ident] += 1
        released = False

        def release():
            nonlocal released
            with self.store.lock:
                if released:
                    return
                released = True
                self.touch(table, ident)
                self.active[table, ident] -= 1
                if not self.active[table, ident]:
                    del self.active[table, ident]
        return item, release

    def remove(self, path, parent):
        """Check resolved bounds and Windows reparse points before any recursive delete."""
        path, parent = Path(path), Path(parent).resolve()
        if not parent.is_relative_to(self.store.root):
            return False
        if path.resolve() == parent or not path.resolve().is_relative_to(parent):
            return False
        def reparse(p):
            return p.is_symlink() or bool(getattr(p.lstat(), 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0))
        try:
            if not path.exists():
                return not path.is_symlink()
            if reparse(path):
                return False
            if path.is_dir():
                for root, dirs, files in os.walk(path, followlinks=False):
                    if any(reparse(Path(root) / name) for name in dirs + files):
                        return False
                shutil.rmtree(path)
            else:
                path.unlink()
            return True
        except OSError:
            logging.exception('Retention will retry locked file: %s', path)
            return False

    def cleanup(self, now=None):
        now = self.clock() if now is None else now
        cutoff, removed = now - self.seconds, 0
        with self.store.lock:
            jobs = self.records('jobs')
            protected_jobs = {j['id'] for j in jobs if j['status'] in ('queued', 'processing') or self.active['jobs', j['id']]}
            protected_media = {j['params'].get('media_id') for j in jobs if j['id'] in protected_jobs}
            media_activity = {}
            for job in jobs:
                mid = job['params'].get('media_id')
                if mid and job['status'] != 'expired':
                    media_activity[mid] = max(media_activity.get(mid, 0), self.last_use(job))
                if job['id'] in protected_jobs or job['status'] == 'expired' or self.last_use(job) > cutoff:
                    continue
                if self.remove(self.store.root / 'jobs' / job['id'], self.store.root / 'jobs'):
                    job.update(status='expired', expired=True, result=None, error=None,
                               message='File đã tự xoá sau 10 phút không sử dụng.')
                    self.store.put('jobs', job)
                    removed += 1
            for item in self.records('media'):
                if item.get('expired') or item['id'] in protected_media or self.active['media', item['id']]:
                    continue
                if max(self.last_use(item), media_activity.get(item['id'], 0)) > cutoff:
                    continue
                if self.remove(self.store.root / 'media' / item['path'], self.store.root / 'media'):
                    item['expired'] = True
                    self.store.put('media', item)
                    removed += 1
            for item in self.records('uploads'):
                if item.get('expired') or self.active['uploads', item['id']] or self.last_use(item) > cutoff:
                    continue
                if self.remove(self.store.root / 'uploads' / (item['id'] + '.part'), self.store.root / 'uploads'):
                    item['expired'] = True
                    self.store.put('uploads', item)
                    removed += 1
            # Failed imports / interrupted uploads may never have obtained a media record.
            known_media = {str((self.store.root / 'media' / m['path']).resolve()) for m in self.records('media')}
            known_uploads = {u['id'] + '.part' for u in self.records('uploads')}
            import_prefixes = {j['id'] for j in jobs if j['kind'] == 'import' and
                               (j['id'] in protected_jobs or self.last_use(j) > cutoff)}
            for folder in ('media', 'uploads'):
                base = self.store.root / folder
                for path in base.iterdir():
                    if not path.is_file() or str(path.resolve()) in known_media or path.name in known_uploads:
                        continue
                    if any(path.name.startswith(prefix + '.') for prefix in import_prefixes):
                        continue
                    if path.stat().st_mtime <= cutoff and self.remove(path, base):
                        removed += 1
        return removed

    def start(self):
        self.grant_legacy_grace()
        def loop():
            while True:
                try:
                    self.cleanup()
                except Exception:
                    logging.exception('File retention sweep failed; retrying')
                time.sleep(30)
        self.thread = threading.Thread(target=loop, name='file-retention', daemon=True)
        self.thread.start()
