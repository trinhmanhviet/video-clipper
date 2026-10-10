import os
import sys

# Ensure UTF-8 console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import json
import time
import uuid
import shutil
import zipfile
import threading
import subprocess
import webbrowser
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory, Response

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

# Base directory (supports standalone exe or raw script)
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
UPLOADS_DIR = BASE_DIR / "uploads"
OUTPUTS_DIR = BASE_DIR / "outputs"
THUMBS_DIR = BASE_DIR / "thumbs"
BIN_DIR = BASE_DIR / "bin"

UPLOADS_DIR.mkdir(exist_ok=True)
OUTPUTS_DIR.mkdir(exist_ok=True)
THUMBS_DIR.mkdir(exist_ok=True)
BIN_DIR.mkdir(exist_ok=True)

# Logging ring buffer
class LogManager:
    def __init__(self):
        self.logs = []
        self.lock = threading.Lock()
        self.console_visible = True

    def log(self, msg: str):
        with self.lock:
            entry = f"[{time.strftime('%H:%M:%S')}] {msg}"
            self.logs.append(entry)
            if len(self.logs) > 500:
                self.logs.pop(0)
            try:
                print(entry)
            except Exception:
                pass

    def get_logs(self):
        with self.lock:
            return list(self.logs)

    def clear(self):
        with self.lock:
            self.logs.clear()

logger = LogManager()

def find_binary(name):
    candidates = [name]
    if name.endswith(".exe"):
        candidates.append(name[:-4])
    else:
        candidates.append(f"{name}.exe")
        
    for candidate in candidates:
        local_path = BIN_DIR / candidate
        if local_path.exists():
            return str(local_path)
        system_path = shutil.which(candidate)
        if system_path:
            return system_path
            
    common_paths = [
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffprobe.exe",
        r"C:\Program Files\nodejs\node.exe",
        "/usr/bin/ffmpeg",
        "/usr/bin/ffprobe",
        "/usr/bin/node",
        "/usr/local/bin/ffmpeg",
        "/usr/local/bin/ffprobe",
        "/usr/local/bin/node"
    ]
    for p in common_paths:
        if os.path.exists(p) and Path(p).name in candidates:
            return p
    return ""

FFMPEG_PATH = find_binary("ffmpeg.exe")
FFPROBE_PATH = find_binary("ffprobe.exe")
NODE_PATH = find_binary("node.exe")
FFMPEG_DIR = str(Path(FFMPEG_PATH).parent) if FFMPEG_PATH else ""

logger.log(f"Khoi tao Portable Environment: FFMPEG={bool(FFMPEG_PATH)}, FFPROBE={bool(FFPROBE_PATH)}, NODE={bool(NODE_PATH)}")

app = Flask(__name__, template_folder=str(TEMPLATES_DIR), static_folder=str(STATIC_DIR))

tasks = {}

def get_base_ydl_opts():
    opts = {
        'quiet': False,
        'no_warnings': False,
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
    }
    if FFMPEG_DIR:
        opts['ffmpeg_location'] = FFMPEG_DIR
    if NODE_PATH and os.path.exists(NODE_PATH):
        opts['js_runtimes'] = {'node': {'path': NODE_PATH}}
    return opts

def format_seconds(seconds: float, include_ms: bool = True) -> str:
    total_sec = max(0.0, float(seconds))
    h = int(total_sec // 3600)
    m = int((total_sec % 3600) // 60)
    s = int(total_sec % 60)
    ms = int(round((total_sec - int(total_sec)) * 1000))
    if ms >= 1000:
        ms = 0
        s += 1
    if include_ms:
        return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
    return f"{h:02d}:{m:02d}:{s:02d}"

def parse_time_str(val: str) -> float:
    val = str(val).strip()
    if not val:
        return 0.0
    if ":" in val:
        parts = val.split(":")
        if len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
    return float(val)

def get_default_formats():
    return [
        {"format_id": "best", "note": "Video / Best Quality (Chất lượng gốc)", "height": 9999, "size_mb": None},
        {"format_id": "1080p", "note": "Video / 1080p Full HD", "height": 1080, "size_mb": None},
        {"format_id": "720p", "note": "Video / 720p HD", "height": 720, "size_mb": None},
        {"format_id": "480p", "note": "Video / 480p SD", "height": 480, "size_mb": None},
        {"format_id": "mp3", "note": "Audio / MP3 (320kbps)", "height": 0, "size_mb": None}
    ]

def get_local_video_info(file_path: str):
    cmd = [
        FFPROBE_PATH,
        "-v", "error",
        "-show_entries", "format=duration,size:stream=width,height,r_frame_rate,codec_name",
        "-of", "json",
        file_path
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    data = json.loads(res.stdout)
    
    duration = float(data.get("format", {}).get("duration", 0))
    size = int(data.get("format", {}).get("size", 0))
    streams = data.get("streams", [])
    video_stream = next((s for s in streams if s.get("width")), {})
    
    width = video_stream.get("width", 1920)
    height = video_stream.get("height", 1080)
    fps_str = video_stream.get("r_frame_rate", "30/1")
    try:
        num, den = fps_str.split("/")
        fps = round(float(num) / float(den), 2)
    except Exception:
        fps = 30.0

    thumb_name = f"thumb_{uuid.uuid4().hex[:8]}.jpg"
    thumb_path = THUMBS_DIR / thumb_name
    subprocess.run([
        FFMPEG_PATH, "-y",
        "-ss", str(min(1.0, duration / 2)),
        "-i", file_path,
        "-vframes", "1",
        "-q:v", "3",
        str(thumb_path)
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    formats = [
        {"format_id": "original", "note": f"Video / {height}p (Original)", "height": height, "fps": fps, "size_mb": round(size / (1024*1024), 2)},
        {"format_id": "1080p", "note": "Video / 1080p Full HD", "height": 1080, "fps": fps, "size_mb": None},
        {"format_id": "720p", "note": "Video / 720p HD", "height": 720, "fps": fps, "size_mb": None},
        {"format_id": "480p", "note": "Video / 480p SD", "height": 480, "fps": fps, "size_mb": None},
        {"format_id": "mp3", "note": "Audio / MP3 (320kbps)", "height": 0, "fps": 0, "size_mb": None}
    ]

    return {
        "title": Path(file_path).name,
        "duration": duration,
        "duration_str": format_seconds(duration, include_ms=True),
        "thumbnail": f"/thumb/{thumb_name}",
        "width": width,
        "height": height,
        "fps": fps,
        "is_local": True,
        "local_path": file_path,
        "formats": formats
    }

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/thumb/<filename>")
def get_thumb(filename):
    return send_from_directory(THUMBS_DIR, filename)

@app.route("/outputs/<run_folder>/<filename>")
def download_run_output(run_folder, filename):
    folder = OUTPUTS_DIR / run_folder
    return send_from_directory(folder, filename, as_attachment=True)

@app.route("/outputs/<filename>")
def download_output_legacy(filename):
    return send_from_directory(OUTPUTS_DIR, filename, as_attachment=True)

@app.route("/stream/<filename>")
def stream_video(filename):
    path = UPLOADS_DIR / filename
    if not path.exists():
        return "Not found", 404

    range_header = request.headers.get("Range", None)
    if not range_header:
        return send_from_directory(UPLOADS_DIR, filename)

    size = path.stat().st_size
    byte1, byte2 = 0, None
    m = range_header.replace("bytes=", "").split("-")
    if m[0]:
        byte1 = int(m[0])
    if len(m) > 1 and m[1]:
        byte2 = int(m[1])
    length = size - byte1
    if byte2:
        length = byte2 + 1 - byte1

    with open(path, "rb") as f:
        f.seek(byte1)
        data = f.read(length)

    rv = Response(data, 206, mimetype="video/mp4", content_type="video/mp4", direct_passthrough=True)
    rv.headers.add("Content-Range", f"bytes {byte1}-{byte1 + len(data) - 1}/{size}")
    rv.headers.add("Accept-Ranges", "bytes")
    return rv

@app.route("/api/info", methods=["POST"])
def get_info():
    data = request.json or {}
    source = data.get("source", "").strip()
    if not source:
        return jsonify({"error": "Vui lòng nhập URL hoặc đường dẫn file"}), 400

    logger.log(f"Dang lay thong tin nguon: {source}")

    # Local file path check
    if os.path.exists(source) and os.path.isfile(source):
        try:
            info = get_local_video_info(source)
            logger.log(f"Da lay thong tin file local: {info['title']} ({info['duration_str']})")
            return jsonify(info)
        except Exception as e:
            logger.log(f"Loi doc file local: {str(e)}")
            return jsonify({"error": f"Lỗi đọc file nội bộ: {str(e)}"}), 500

    # Online Video URL (YouTube, etc.)
    try:
        ydl_opts = get_base_ydl_opts()
        ydl_opts.update({
            'extract_flat': False,
            'skip_download': True,
        })

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            meta = ydl.extract_info(source, download=False)

        duration = float(meta.get("duration", 0))
        title = meta.get("title", "Video")
        thumbnail = meta.get("thumbnail", "")

        formats_raw = meta.get("formats", [])
        res_map = {}
        for f in formats_raw:
            h = f.get("height")
            vcodec = f.get("vcodec")
            if h and vcodec != "none":
                fps = f.get("fps")
                note_fps = f"{int(fps)}" if fps and fps > 30 else ""
                key = f"{h}p{note_fps}"
                filesize = f.get("filesize") or f.get("filesize_approx")
                if key not in res_map or (filesize and filesize > (res_map[key].get("filesize") or 0)):
                    res_map[key] = {
                        "format_id": f.get("format_id"),
                        "height": h,
                        "fps": fps,
                        "note": f"Video / {h}p{note_fps}",
                        "filesize": filesize
                    }

        sorted_formats = sorted(res_map.values(), key=lambda x: x["height"], reverse=True)
        final_formats = [
            {
                "format_id": "bestvideo+bestaudio/best",
                "note": "Video / Best Quality (Gốc)",
                "height": 9999,
                "fps": None,
                "size_mb": None
            }
        ]
        for item in sorted_formats[:6]:
            size_mb = round(item["filesize"] / (1024*1024), 2) if item["filesize"] else None
            final_formats.append({
                "format_id": item["format_id"],
                "note": item["note"],
                "height": item["height"],
                "fps": item["fps"],
                "size_mb": size_mb
            })
        final_formats.append({
            "format_id": "mp3",
            "note": "Audio / MP3 (320kbps)",
            "height": 0,
            "fps": None,
            "size_mb": None
        })

        logger.log(f"Lay thong tin online thanh cong: {title} ({format_seconds(duration)})")
        return jsonify({
            "title": title,
            "duration": duration,
            "duration_str": format_seconds(duration, include_ms=True),
            "thumbnail": thumbnail,
            "is_local": False,
            "url": source,
            "formats": final_formats
        })

    except Exception as e:
        logger.log(f"Khong lay duoc metadata URL, dung fallback: {str(e)}")
        return jsonify({
            "title": source,
            "duration": 3600,
            "duration_str": "01:00:00.000",
            "thumbnail": "",
            "is_local": False,
            "url": source,
            "formats": get_default_formats(),
            "warning": f"Không tải được chi tiết (có thể cắt trực tiếp): {str(e)}"
        })

@app.route("/api/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "Không tìm thấy file tải lên"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "Tên file trống"}), 400

    safe_name = f"{int(time.time())}_{file.filename}"
    save_path = UPLOADS_DIR / safe_name
    file.save(str(save_path))
    logger.log(f"Da tai file len: {safe_name}")

    info = get_local_video_info(str(save_path))
    info["stream_url"] = f"/stream/{safe_name}"
    return jsonify(info)

def process_worker(task_id, params):
    try:
        tasks[task_id]["status"] = "processing"
        tasks[task_id]["message"] = "Đang bắt đầu quá trình cắt..."

        source = params.get("source", "").strip()
        is_local = params.get("is_local", False)
        if not is_local and (os.path.exists(source) and os.path.isfile(source)):
            is_local = True

        start_sec = parse_time_str(params.get("start_time", "00:00:00.000"))
        end_sec = parse_time_str(params.get("end_time", "00:00:10.000"))
        format_id = params.get("format_id", "best")
        extract_frames = params.get("extract_frames", False)
        frame_format = params.get("frame_format", "png")
        frame_fps = params.get("frame_fps", "native")

        start_str = format_seconds(start_sec, include_ms=True)
        end_str = format_seconds(end_sec, include_ms=True)

        raw_title = params.get("title", "clip")
        clean_title = "".join(c for c in raw_title if c.isalnum() or c in ("-", "_")).rstrip()[:30]
        if not clean_title or len(clean_title) < 2:
            clean_title = "clip"
        timestamp_slug = time.strftime("%Y%m%d_%H%M%S")

        run_folder_name = f"{clean_title}_{timestamp_slug}"
        run_dir = OUTPUTS_DIR / run_folder_name
        run_dir.mkdir(parents=True, exist_ok=True)

        out_ext = "mp3" if format_id == "mp3" else "mp4"
        out_video_name = f"{clean_title}.{out_ext}"
        out_video_path = run_dir / out_video_name

        logger.log(f"Khoi tao doan cat: {start_str} -> {end_str} vao thu muc outputs/{run_folder_name}/")

        if is_local:
            tasks[task_id]["message"] = f"Đang cắt video với FFmpeg ({start_str} -> {end_str})..."
            logger.log(f"Chay FFmpeg cat video local...")
            if format_id == "mp3":
                cmd = [
                    FFMPEG_PATH, "-y",
                    "-ss", str(start_sec),
                    "-to", str(end_sec),
                    "-i", source,
                    "-vn", "-acodec", "libmp3lame", "-ab", "320k",
                    str(out_video_path)
                ]
            else:
                cmd = [
                    FFMPEG_PATH, "-y",
                    "-ss", str(start_sec),
                    "-to", str(end_sec),
                    "-i", source,
                    "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                    "-c:a", "aac", "-b:a", "192k",
                    str(out_video_path)
                ]
            p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
            if p.returncode != 0:
                raise RuntimeError(f"FFmpeg lỗi: {p.stderr[:300]}")
        else:
            tasks[task_id]["message"] = f"Đang tải và cắt từ YouTube ({start_str} -> {end_str})..."
            logger.log(f"Chay yt-dlp tai doan {start_str} den {end_str}...")
            ydl_opts = get_base_ydl_opts()
            ydl_opts.update({
                'download_ranges': yt_dlp.utils.download_range_func(None, [(start_sec, end_sec)]),
                'force_keyframes_at_cuts': True,
                'outtmpl': str(run_dir / f"{clean_title}.%(ext)s"),
            })

            if format_id == "mp3":
                ydl_opts['format'] = 'bestaudio/best'
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '320',
                }]
            elif format_id in ("best", "original") or not format_id:
                ydl_opts['format'] = 'bestvideo+bestaudio/best'
                ydl_opts['merge_output_format'] = 'mp4'
            elif "p" in format_id and format_id[:-1].isdigit():
                h = format_id.replace("p", "")
                ydl_opts['format'] = f'bestvideo[height<={h}]+bestaudio/best[height<={h}]/best'
                ydl_opts['merge_output_format'] = 'mp4'
            else:
                ydl_opts['format'] = f'{format_id}+bestaudio/best'
                ydl_opts['merge_output_format'] = 'mp4'

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([source])
            except Exception as e_first:
                logger.log(f"Format {format_id} fallback sang standard: {e_first}")
                ydl_opts['format'] = '18/best'
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([source])

            matches = [f for f in run_dir.glob(f"{clean_title}*") if not f.name.endswith(".zip") and not f.is_dir()]
            if matches:
                out_video_path = matches[0]
                out_video_name = out_video_path.name
            else:
                raise RuntimeError("Không tìm thấy file video sau khi tải trong thư mục kết quả")

        logger.log(f"Da tao xong video: {out_video_name}")

        # Frame extraction into run_dir / "frames"
        frames_zip_name = None
        frames_count = 0
        if extract_frames and out_ext != "mp3":
            tasks[task_id]["message"] = "Đang trích xuất tất cả frames ảnh..."
            frames_folder = run_dir / "frames"
            frames_folder.mkdir(exist_ok=True)
            logger.log(f"Bat dau trich xuat frames anh vao {frames_folder}...")

            frame_pattern = str(frames_folder / f"frame_%05d.{frame_format}")
            fps_args = []
            if frame_fps != "native":
                fps_args = ["-vf", f"fps={frame_fps}"]

            cmd_frames = [
                FFMPEG_PATH, "-y",
                "-i", str(out_video_path),
                *fps_args,
                "-q:v", "2",
                frame_pattern
            ]
            subprocess.run(cmd_frames, capture_output=True, text=True, encoding="utf-8")

            all_frames = list(frames_folder.glob(f"frame_*.{frame_format}"))
            frames_count = len(all_frames)
            logger.log(f"Trich xuat thanh cong {frames_count} anh frames")

            tasks[task_id]["message"] = f"Đang đóng gói {frames_count} ảnh vào file ZIP..."
            frames_zip_name = f"{clean_title}_frames.zip"
            frames_zip_path = run_dir / frames_zip_name
            with zipfile.ZipFile(frames_zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                for f in all_frames:
                    zipf.write(f, arcname=f"frames/{f.name}")
            logger.log(f"Da dong goi file zip: {frames_zip_name}")

        tasks[task_id]["status"] = "completed"
        tasks[task_id]["message"] = "Cắt video và xuất dữ liệu thành công!"
        tasks[task_id]["result"] = {
            "run_folder": run_folder_name,
            "video_file": out_video_name,
            "video_url": f"/outputs/{run_folder_name}/{out_video_name}",
            "frames_zip": frames_zip_name,
            "frames_url": f"/outputs/{run_folder_name}/{frames_zip_name}" if frames_zip_name else None,
            "frames_count": frames_count,
            "output_folder": str(run_dir)
        }
        logger.log(f"HOAN TAT TAC VU {task_id}")

    except Exception as e:
        tasks[task_id]["status"] = "error"
        tasks[task_id]["message"] = f"Lỗi: {str(e)}"
        logger.log(f"LOI TAC VU: {str(e)}")

@app.route("/api/process", methods=["POST"])
def process_video():
    params = request.json or {}
    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "status": "pending",
        "message": "Đang khởi tạo tác vụ...",
        "result": None
    }
    t = threading.Thread(target=process_worker, args=(task_id, params), daemon=True)
    t.start()
    return jsonify({"task_id": task_id})

@app.route("/api/status/<task_id>")
def get_task_status(task_id):
    task = tasks.get(task_id)
    if not task:
        return jsonify({"error": "Tác vụ không tồn tại"}), 404
    return jsonify(task)

@app.route("/api/open_folder", methods=["POST"])
def open_folder():
    data = request.json or {}
    folder_name = data.get("folder", "").strip()
    target_path = OUTPUTS_DIR / folder_name if folder_name else OUTPUTS_DIR
    if not target_path.exists():
        target_path = OUTPUTS_DIR
    try:
        if hasattr(os, "startfile"):
            os.startfile(str(target_path))
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/logs")
def get_live_logs():
    return jsonify({"logs": logger.get_logs()})

@app.route("/api/clear_logs", methods=["POST"])
def clear_logs():
    logger.clear()
    return jsonify({"success": True})

@app.route("/api/toggle_console", methods=["POST"])
def toggle_console():
    data = request.json or {}
    show = bool(data.get("show", True))
    hwnd = 0
    if sys.platform == "win32":
        try:
            import ctypes
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 5 if show else 0)
        except Exception:
            pass
    logger.console_visible = show
    return jsonify({"success": True, "visible": show, "hwnd": hwnd})

# Cloudflare Remote Tunnel for mobile access
tunnel_proc = None
tunnel_url = None

def start_tunnel(port):
    global tunnel_proc, tunnel_url
    cloudflared_bin = shutil.which("cloudflared")
    if not cloudflared_bin:
        logger.log("Chua phat hien cloudflared tren may.")
        return
    try:
        logger.log("Dang khoi tao Cloudflare Quick Tunnel cho dien thoai...")
        cmd = [cloudflared_bin, "tunnel", "--url", f"http://127.0.0.1:{port}"]
        tunnel_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        def reader():
            global tunnel_url
            for line in tunnel_proc.stdout:
                line_str = line.strip()
                if "trycloudflare.com" in line_str:
                    for part in line_str.split():
                        if "trycloudflare.com" in part:
                            clean_url = part.strip().strip("|").strip()
                            if not clean_url.startswith("http"):
                                clean_url = f"https://{clean_url}"
                            tunnel_url = clean_url
                            logger.log("==================================================")
                            logger.log(f"[PHONE REMOTE LINK]: {tunnel_url}")
                            logger.log("==================================================")
                            break
        threading.Thread(target=reader, daemon=True).start()
    except Exception as e:
        logger.log(f"Loi khi bat Tunnel: {e}")

@app.route("/api/tunnel")
def get_tunnel_status():
    return jsonify({
        "available": bool(shutil.which("cloudflared")),
        "url": tunnel_url,
        "qr": f"https://api.qrserver.com/v1/create-qr-code/?size=220x220&data={tunnel_url}" if tunnel_url else ""
    })

@app.route("/api/start_tunnel", methods=["POST"])
def api_start_tunnel():
    global tunnel_url
    if not tunnel_url:
        start_tunnel(5000)
    return jsonify({"success": True})

if __name__ == "__main__":
    is_hf = bool(os.environ.get("SPACE_ID"))
    default_port = 7860 if is_hf else 5000
    port = int(os.environ.get("PORT", default_port))
    
    print("======================================================")
    print(f"[Video Clipper Studio] Server running on http://0.0.0.0:{port}")
    if is_hf:
        print("[Video Clipper Studio] Environment: Hugging Face Spaces")
    print("======================================================")
    
    # Auto start remote tunnel for mobile phone access if cloudflared exists
    if shutil.which("cloudflared") and not is_hf:
        threading.Thread(target=start_tunnel, args=(port,), daemon=True).start()

    if sys.platform == "win32" and not is_hf:
        def open_browser():
            time.sleep(1.2)
            try:
                webbrowser.open(f"http://localhost:{port}")
            except Exception:
                pass
        threading.Thread(target=open_browser, daemon=True).start()

    app.run(host="0.0.0.0", port=port, debug=False)
