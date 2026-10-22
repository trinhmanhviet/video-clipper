"""PC-backed video clipper. Run with Waitress; bind only to loopback."""
import math
import os
import shutil
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_file
from store import Store
from processing import Worker, probe

BASE = Path(__file__).resolve().parent
EXTENSIONS = {'.mp4', '.mov', '.mkv', '.webm', '.avi', '.m4v', '.mpeg', '.mpg'}


def create_app(data_dir=None, start_worker=True):
    app = Flask(__name__, template_folder=str(BASE / 'templates'), static_folder=str(BASE / 'static'))
    app.config['MAX_CONTENT_LENGTH'] = 9 * 1024 * 1024
    store = Store(data_dir or os.environ.get('CLIP_DATA_DIR') or BASE / 'data')
    app.extensions['store'] = store
    upload_lock = threading.Lock()
    if start_worker:
        app.extensions['worker'] = Worker(store)

    @app.errorhandler(ValueError)
    def invalid(e):
        return jsonify(error=str(e)), 400

    @app.errorhandler(413)
    def too_large(e):
        return jsonify(error='Khối tải lên quá lớn. Hãy tải lại trang để tiếp tục theo từng phần.'), 413

    @app.after_request
    def headers(response):
        if request.path.startswith('/api/') or request.path == '/':
            response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    def media_or_404(ident):
        item = store.get('media', ident)
        if not item:
            abort(404)
        return item

    def job_or_404(ident):
        item = store.get('jobs', ident)
        if not item:
            abort(404)
        return item

    def public_media(item):
        return {k: v for k, v in item.items() if k != 'path'} | {'stream_url': '/api/media/' + item['id'] + '/stream'}

    def queue_room():
        if sum(j['status'] in ('processing', 'queued') for j in store.jobs()) >= 10:
            raise ValueError('Đang có nhiều tác vụ. Chờ tác vụ trước hoàn tất hoặc hủy bớt.')

    @app.get('/')
    def home():
        return render_template('studio.html')

    @app.get('/api/health')
    def health():
        return jsonify(status='ok', backend='pc-v2', revision='2026-10-23',
                       processing=sum(j['status'] == 'processing' for j in store.jobs()))

    @app.post('/api/uploads')
    def begin_upload():
        data = request.get_json() or {}
        name = str(data.get('name', 'video.mp4'))[:240]
        extension = Path(name).suffix.lower()
        size = int(data.get('size', 0))
        if extension not in EXTENSIONS:
            raise ValueError('Chọn file video MP4, MOV, MKV, WebM hoặc AVI.')
        if size <= 0 or size > 2 * 1024 ** 3:
            raise ValueError('File phải lớn hơn 0 và không quá 2 GB.')
        if shutil.disk_usage(store.root).free < size + 512 * 1024 ** 2:
            raise ValueError('Ổ lưu trữ máy xử lý không đủ dung lượng cho video này.')
        ident = uuid.uuid4().hex
        item = dict(id=ident, name=name, size=size, extension=extension, created=time.time())
        store.put('uploads', item)
        (store.root / 'uploads' / (ident + '.part')).touch()
        return jsonify(id=ident, offset=0), 201

    @app.get('/api/uploads/<ident>')
    def upload_status(ident):
        item = store.get('uploads', ident)
        if not item:
            abort(404)
        path = store.root / 'uploads' / (ident + '.part')
        return jsonify(id=ident, offset=path.stat().st_size if path.exists() else item['size'],
                       media_id=item.get('media_id'))

    @app.put('/api/uploads/<ident>')
    def upload_chunk(ident):
        with upload_lock:
            item = store.get('uploads', ident)
            if not item or item.get('media_id'):
                abort(404)
            path = store.root / 'uploads' / (ident + '.part')
            current = path.stat().st_size
            if int(request.args.get('offset', -1)) != current:
                return jsonify(error='Tiếp tục từ phần đã tải', offset=current), 409
            chunk = request.get_data()
            if not chunk or current + len(chunk) > item['size']:
                raise ValueError('Kích thước phần tải lên không hợp lệ.')
            with path.open('ab') as f:
                f.write(chunk)
            return jsonify(offset=path.stat().st_size)

    @app.post('/api/uploads/<ident>/complete')
    def complete_upload(ident):
        with upload_lock:
            item = store.get('uploads', ident)
            if not item:
                abort(404)
            if item.get('media_id'):
                return jsonify(public_media(media_or_404(item['media_id'])))
            path = store.root / 'uploads' / (ident + '.part')
            if not path.exists() or path.stat().st_size != item['size']:
                raise ValueError('Chưa tải đủ video. Hãy thử lại.')
            info = probe(path)
            destination = store.root / 'media' / (ident + item['extension'])
            path.replace(destination)
            media = store.add_media(item['name'], destination.name, info)
            item['media_id'] = media['id']
            store.put('uploads', item)
            return jsonify(public_media(media))

    @app.get('/api/media/<ident>')
    def get_media(ident):
        return jsonify(public_media(media_or_404(ident)))

    @app.get('/api/media/<ident>/stream')
    def stream(ident):
        media = media_or_404(ident)
        path = store.media_path(media)
        if not path.exists():
            abort(404)
        return send_file(path, conditional=True)

    @app.post('/api/import')
    def import_url():
        queue_room()
        url = str((request.get_json() or {}).get('url', '')).strip()
        if not url.startswith(('https://', 'http://')):
            raise ValueError('Nhập liên kết video http:// hoặc https://.')
        return jsonify(store.add_job('import', {'url': url})), 202

    @app.post('/api/jobs')
    def export():
        data = request.get_json() or {}
        media = media_or_404(str(data.get('media_id', '')))
        start, end = float(data.get('start', 0)), float(data.get('end', media['duration']))
        if not all(math.isfinite(v) for v in (start, end)) or not 0 <= start < end <= media['duration'] + .01:
            raise ValueError('Chọn mốc bắt đầu/kết thúc nằm trong video, kết thúc phải sau bắt đầu.')
        fmt = data.get('format', 'mp4')
        if fmt not in ('mp4', 'mp3'):
            raise ValueError('Định dạng xuất không hợp lệ.')
        height = data.get('height')
        if height not in (None, 480, 720, 1080):
            raise ValueError('Độ phân giải không hợp lệ.')
        fps = data.get('fps')
        if fps is not None and fps not in (1, 3, 6, 12, 15, 24, 30, 60):
            raise ValueError('Tốc độ xuất frame không hợp lệ.')
        frame_format = data.get('frame_format', 'jpg')
        if frame_format not in ('png', 'jpg'):
            raise ValueError('Định dạng ảnh không hợp lệ.')
        queue_room()
        params = dict(media_id=media['id'], start=start, end=min(end, media['duration']), format=fmt,
                      height=height, fps=fps, frames=bool(data.get('frames')), frame_format=frame_format)
        return jsonify(store.add_job('export', params)), 202

    @app.get('/api/jobs/<ident>')
    def status(ident):
        job = job_or_404(ident)
        job['elapsed'] = round((job.get('finished') or time.time()) - (job.get('started') or time.time()), 1)
        if job['result'] and job['kind'] == 'export':
            result = job['result']
            result['video_url'] = f'/api/jobs/{ident}/files/{result["video"]}'
            if result['frames']:
                result['frames_url'] = f'/api/jobs/{ident}/files/{result["frames"]}'
        return jsonify(job)

    @app.post('/api/jobs/<ident>/cancel')
    def cancel(ident):
        job = job_or_404(ident)
        if job['status'] in ('queued', 'processing'):
            job = store.cancel(ident)
        return jsonify(job)

    @app.get('/api/jobs/<ident>/files/<name>')
    def download(ident, name):
        job = job_or_404(ident)
        result = job.get('result') or {}
        if job['status'] != 'completed' or name not in (result.get('video'), result.get('frames')):
            abort(404)
        return send_file(store.root / 'jobs' / ident / name, conditional=True,
                         as_attachment=request.args.get('download') == '1', download_name=name)

    return app


if __name__ == '__main__':
    from waitress import serve
    app = create_app()
    print('Video Clipper PC backend ready on http://127.0.0.1:8790', flush=True)
    serve(app, host='127.0.0.1', port=int(os.environ.get('CLIP_PORT', 8790)), threads=8,
          max_request_body_size=9 * 1024 * 1024, channel_timeout=120)
