"""Small durable store; no per-browser state or server paths in API requests."""
import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        for name in ('media', 'jobs', 'uploads', 'logs'):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        self.db = self.root / 'studio.sqlite3'
        self.lock = threading.RLock()
        with self.connect() as c:
            c.execute('PRAGMA journal_mode=WAL')
            c.execute('CREATE TABLE IF NOT EXISTS media (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            c.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            c.execute('CREATE TABLE IF NOT EXISTS uploads (id TEXT PRIMARY KEY, data TEXT NOT NULL)')

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.db, timeout=15)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def put(self, table, item):
        with self.lock, self.connect() as c:
            c.execute(f'INSERT OR REPLACE INTO {table} (id,data) VALUES (?,?)',
                      (item['id'], json.dumps(item, ensure_ascii=False)))
        return item

    def get(self, table, ident):
        with self.connect() as c:
            row = c.execute(f'SELECT data FROM {table} WHERE id=?', (ident,)).fetchone()
        return json.loads(row[0]) if row else None

    def add_media(self, name, path, info):
        return self.put('media', dict(id=uuid.uuid4().hex, name=name, path=str(path),
                                     created=time.time(), **info))

    def add_job(self, kind, params):
        return self.put('jobs', dict(id=uuid.uuid4().hex, kind=kind, params=params, status='queued',
                        progress=0, stage='queued', message='Đang chờ xử lý', created=time.time(),
                        started=None, finished=None, cancel_requested=False, result=None, error=None))

    def update_job(self, ident, **changes):
        with self.lock:
            item = self.get('jobs', ident)
            item.update(changes)
            return self.put('jobs', item)

    def jobs(self):
        with self.connect() as c:
            rows = c.execute('SELECT data FROM jobs').fetchall()
        return sorted((json.loads(row[0]) for row in rows), key=lambda j: j['created'])

    def cancel(self, ident):
        with self.lock:
            job = self.get('jobs', ident)
            changes = dict(cancel_requested=True)
            if job['status'] == 'queued':
                changes.update(status='cancelled', finished=time.time(), message='Đã hủy')
            return self.update_job(ident, **changes)

    def media_path(self, item):
        path = (self.root / 'media' / item['path']).resolve()
        if not path.is_relative_to(self.root / 'media'):
            raise ValueError('Invalid media storage path')
        return path
