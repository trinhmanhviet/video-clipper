"""Bounded subprocess runner and one-job-at-a-time persistent media queue."""
import json
import math
import os
import queue
import shutil
import socket
import ipaddress
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path
from urllib.parse import urlsplit


def binary(name):
    found = os.environ.get(name.upper() + '_PATH') or shutil.which(name)
    if not found and os.name == 'nt':
        candidate = Path('C:/Program Files/ffmpeg/bin') / (name + '.exe')
        if candidate.exists():
            found = str(candidate)
    if not found:
        raise RuntimeError(f'Không tìm thấy {name} trên máy xử lý.')
    return found


def probe(path):
    p = subprocess.run([binary('ffprobe'), '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)],
                       capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=25,
                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if p.returncode:
        raise ValueError('Không đọc được video: ' + p.stderr[-1200:])
    data = json.loads(p.stdout)
    video = next((s for s in data['streams'] if s.get('codec_type') == 'video'), None)
    if not video:
        raise ValueError('File không có luồng video.')
    fraction = video.get('avg_frame_rate', '30/1').split('/')
    fps = float(fraction[0]) / max(float(fraction[-1]), 1)
    return dict(duration=float(data['format'].get('duration', 0)), fps=fps or 30,
                width=int(video['width']), height=int(video['height']),
                codec=video['codec_name'], has_audio=any(s.get('codec_type') == 'audio' for s in data['streams']))


class Cancelled(Exception):
    pass


def run_process(cmd, log, timeout, cancelled, line_callback=None):
    """Drain progress separately so quiet/hung FFmpeg remains cancellable."""
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    with Path(log).open('w', encoding='utf-8') as errors:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=errors, stdin=subprocess.DEVNULL,
                             text=True, encoding='utf-8', errors='replace', creationflags=flags)
        lines = queue.Queue()
        def read():
            for line in p.stdout:
                lines.put(line.rstrip())
            lines.put(None)
        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        deadline = time.monotonic() + timeout
        try:
            done = False
            while not done:
                if cancelled():
                    raise Cancelled('Đã hủy tác vụ')
                if time.monotonic() >= deadline:
                    raise TimeoutError(f'Xử lý vượt quá {int(timeout)} giây và đã được dừng. Bạn có thể thử đoạn ngắn hơn.')
                try:
                    line = lines.get(timeout=.2)
                except queue.Empty:
                    if p.poll() is not None and not reader.is_alive():
                        break
                    continue
                if line is None:
                    done = True
                elif line_callback:
                    line_callback(line)
            code = p.wait(timeout=5)
        finally:
            if p.poll() is None:
                p.kill()
            p.wait(timeout=10)
            reader.join(timeout=2)
            p.stdout.close()
    if code:
        tail = Path(log).read_text(encoding='utf-8', errors='replace')[-2000:].strip()
        raise RuntimeError(tail or f'Tiến trình xử lý dừng với mã {code}.')


def export_job(store, job):
    params = job['params']
    media = store.get('media', params['media_id'])
    source = store.media_path(media)
    if not source.is_file():
        raise ValueError('Video nguồn không còn trên ổ đĩa. Hãy tải lên lại.')
    start, end = params['start'], params['end']
    duration = end - start
    folder = store.root / 'jobs' / job['id']
    folder.mkdir(exist_ok=True)
    fmt = params.get('format', 'mp4')
    output = folder / ('clip.mp3' if fmt == 'mp3' else 'clip.mp4')
    threads = str(max(1, min(6, os.cpu_count() or 2)))
    cmd = [binary('ffmpeg'), '-hide_banner', '-nostdin', '-loglevel', 'error', '-y',
           '-filter_threads', '2', '-threads', '2', '-ss', str(start), '-i', str(source), '-t', str(duration)]
    if fmt == 'mp3':
        if not media.get('has_audio', True):
            raise ValueError('Video này không có âm thanh để xuất MP3.')
        cmd += ['-vn', '-c:a', 'libmp3lame', '-b:a', '192k', '-threads:a', '2']
    else:
        cmd += ['-map', '0:v:0', '-map', '0:a:0?']
        filters = []
        height = params.get('height')
        if height:
            filters.append(f'scale=-2:min(ih\\,{height})')
        filters.append('pad=ceil(iw/2)*2:ceil(ih/2)*2')
        cmd += ['-vf', ','.join(filters), '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18',
                '-pix_fmt', 'yuv420p', '-threads:v', threads,
                '-c:a', 'aac', '-b:a', '192k', '-threads:a', '2', '-movflags', '+faststart']
    cmd += ['-progress', 'pipe:1', '-nostats', str(output)]
    cancel = lambda: bool(store.get('jobs', job['id'])['cancel_requested'])
    stamp = [0]
    def progress(stage, base, span, total):
        def update(line):
            if line.startswith('out_time_us='):
                try:
                    value = float(line.split('=', 1)[1]) / 1e6
                except ValueError:
                    return
                now = time.monotonic()
                if now - stamp[0] > .4:
                    stamp[0] = now
                    store.update_job(job['id'], progress=round(base + span * min(1, max(0, value / total)), 1),
                                     message='Đang cắt video' if stage == 'encode' else 'Đang xuất ảnh frame', stage=stage)
        return update
    frames = bool(params.get('frames')) and fmt != 'mp3'
    store.update_job(job['id'], stage='encode', message='Đang cắt video', progress=1)
    run_process(cmd, folder / 'encode.log', min(1800, max(180, duration * 4 + 60)), cancel,
                progress('encode', 1, 68 if frames else 97, duration))
    if not output.is_file() or output.stat().st_size < 100:
        raise ValueError('Đoạn cắt không có dữ liệu. Kiểm tra mốc thời gian.')
    # Validate actual stream/duration rather than treating a zero-exit header as success.
    if fmt != 'mp3':
        info = probe(output)
        if abs(info['duration'] - duration) > max(.25, 2 / media['fps']):
            raise ValueError('Độ dài đoạn xuất không đúng yêu cầu; không trả file kết quả sai.')
    result = dict(video=output.name, frames=None, frames_count=0, duration=round(duration, 3))
    if frames:
        frame_dir = folder / 'frames'
        frame_dir.mkdir(exist_ok=True)
        frame_format = params.get('frame_format', 'jpg')
        cmd = [binary('ffmpeg'), '-hide_banner', '-nostdin', '-loglevel', 'error', '-y', '-filter_threads', '2',
               '-threads', '2', '-i', str(output)]
        if params.get('fps'):
            cmd += ['-vf', f'fps={params["fps"]}']
        cmd += ['-q:v', '2', '-threads:v', '2', '-progress', 'pipe:1', '-nostats',
                str(frame_dir / ('frame_%06d.' + frame_format))]
        store.update_job(job['id'], stage='frames', message='Đang xuất ảnh frame', progress=70)
        run_process(cmd, folder / 'frames.log', min(1800, max(180, duration * 5)), cancel,
                    progress('frames', 70, 24, duration))
        pictures = sorted(frame_dir.glob('frame_*.' + frame_format))
        if not pictures:
            raise ValueError('Không có frame nào được xuất.')
        store.update_job(job['id'], stage='zip', message=f'Đang đóng gói {len(pictures)} frame', progress=95)
        archive = folder / 'frames.zip'
        # JPEG/PNG are already compressed; deflating them wasted CPU on the old host.
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as z:
            for i, path in enumerate(pictures):
                if cancel():
                    raise Cancelled('Đã hủy tác vụ')
                z.write(path, 'frames/' + path.name)
                if i % 100 == 0:
                    store.update_job(job['id'], progress=95 + 4 * i / len(pictures))
        result.update(frames=archive.name, frames_count=len(pictures))
    return result


def import_job(store, job):
    import yt_dlp
    url = job['params']['url']
    parsed = urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username:
        raise ValueError('Hãy nhập URL video công khai bắt đầu bằng https://.')
    for addr in socket.getaddrinfo(parsed.hostname, parsed.port or 443):
        if not ipaddress.ip_address(addr[4][0]).is_global:
            raise ValueError('Địa chỉ video phải là địa chỉ Internet công khai.')
    destination = store.root / 'media' / (job['id'] + '.%(ext)s')
    cancelled = lambda: bool(store.get('jobs', job['id'])['cancel_requested'])
    begun = time.monotonic()
    def hook(data):
        if cancelled():
            raise Cancelled('Đã hủy tải video')
        if time.monotonic() - begun > 600:
            raise TimeoutError('Tải video quá lâu. Hãy tải file lên trực tiếp.')
        total = data.get('total_bytes') or data.get('total_bytes_estimate') or 1
        store.update_job(job['id'], stage='download', message='Đang tải video từ liên kết',
                         progress=min(95, 95 * data.get('downloaded_bytes', 0) / total))
    opts = dict(outtmpl=str(destination), format='bestvideo+bestaudio/best', merge_output_format='mp4',
                noplaylist=True, socket_timeout=20, retries=1, fragment_retries=1,
                ffmpeg_location=str(Path(binary('ffmpeg')).parent), progress_hooks=[hook], quiet=True)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    paths = [p for p in (store.root / 'media').glob(job['id'] + '.*') if p.suffix not in ('.part', '.ytdl')]
    if not paths:
        raise ValueError('Không tải được file video. Thử tải file trực tiếp lên web.')
    path = max(paths, key=lambda p: p.stat().st_size)
    media = store.add_media(info.get('title', path.name), path.name, probe(path))
    return {'media_id': media['id']}


class Worker:
    def __init__(self, store):
        self.store = store
        for job in store.jobs():
            if job['status'] == 'processing':
                store.update_job(job['id'], status='error', finished=time.time(),
                                 error='Máy xử lý đã khởi động lại. Bấm xuất lại; video nguồn vẫn được giữ.', message='Tác vụ bị gián đoạn')
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()

    def loop(self):
        while True:
            job = next((j for j in self.store.jobs() if j['status'] == 'queued'), None)
            if not job:
                time.sleep(.4)
                continue
            try:
                self.store.update_job(job['id'], status='processing', started=time.time(), message='Bắt đầu xử lý')
                result = export_job(self.store, job) if job['kind'] == 'export' else import_job(self.store, job)
                self.store.update_job(job['id'], status='completed', progress=100, result=result,
                                      finished=time.time(), message='Đã hoàn thành')
            except Cancelled as e:
                self.store.update_job(job['id'], status='cancelled', error=str(e), finished=time.time(), message='Đã hủy')
            except Exception as e:
                self.store.update_job(job['id'], status='error', error=str(e)[-2500:], finished=time.time(), message='Xử lý không thành công')
