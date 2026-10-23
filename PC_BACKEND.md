# Video Clipper — backend PC

Public URL: https://video.multigen.store

## Deployment on this PC

- App: `D:\Projects\MH-Clone\tools\video_clipper_server\studio.py`
- Isolated Python: `D:\Projects\MH-Clone\.tools\clip-fix-env\Scripts\python.exe`
- FFmpeg / ffprobe: `C:\Program Files\ffmpeg\bin`
- HTTP listens on **127.0.0.1:8790** only. A dedicated Cloudflare Tunnel forwards HTTPS.
- Windows scheduled task **Multigen Video Clipper PC** starts `launcher.py` at login.
  The launcher checks both processes every 10 seconds and restarts a stopped process.
  It does not change power/sleep settings. The PC must remain awake and online.
- `data/` contains persistent SQLite metadata, uploads, source videos, results and logs.
  Refreshing a browser keeps its current media, selected timestamps and job ID.
  Completed results survive a backend restart. An interrupted export becomes an explicit
  error and can be submitted again using the retained source.
- One job runs at a time, at most ten jobs wait/run, with at most six encoder threads.
  Uploads use 4 MiB requests, with offset checking and retry/resume, up to 2 GiB per file.
- PNG at original resolution can produce very large archives. JPG and a lower frame rate
  are available. The UI shows the estimated number of frames before exporting.
- Files automatically expire after **10 minutes without use**, checked every 30 seconds.
  Source videos, export folders (including loose frames/ZIP/logs), partial uploads and
  failed-import fragments are covered. Queued/running jobs and open HTTP file transfers
  are protected. Transfer close starts a fresh ten-minute window; job-status polling
  does not extend it. Editing and foreground playback renew the current source.
  Existing records receive an initial ten-minute grace window when retention starts.
  Tiny SQLite expiry records and service logs remain for status/diagnostics.

## Start / stop / inspect

```powershell
Start-ScheduledTask -TaskName 'Multigen Video Clipper PC'
Get-ScheduledTask -TaskName 'Multigen Video Clipper PC'
Invoke-RestMethod https://video.multigen.store/api/health
```

For maintenance, stop the scheduled task first, then stop only this tool's backend and
tunnel processes (their latest PIDs are in `data/backend.pid` and `data/tunnel.pid`).
Verify process command lines before stopping a PID; Windows can reuse PIDs. Other
Cloudflare tunnels and Comfy processes are independent.

Logs: `data/logs/backend.log`, `data/logs/tunnel.log`, and each job's `encode.log` /
`frames.log` under `data/jobs/<id>/`.

## DNS / rollback

Only the proxied CNAME `video.multigen.store` was changed on 2026-10-23:

- Current: `fbfbf80d-f3fa-407f-a9da-4f0a62cf89f8.cfargotunnel.com`
- Previous: `video-clipper-3izi.onrender.com`, proxied, TTL Auto.

The Render deployment and its legacy `app.py` are retained for rollback. `studio.py`
is the PC app; the old Docker entry point is intentionally unchanged.
Tunnel configuration and credentials live under ignored `tunnel/`. Never commit them.

## Verification, 2026-10-23

Real source: 39,855,434 bytes, H.264/AAC, 1080×1920, 30 fps, 167.5 seconds.
Requested interval: **38.379–140.068 seconds** (101.689 seconds).

| Test | Measured result |
|---|---|
| Public HTTPS chunk upload | 6.97 seconds |
| Full public export | 15.19 seconds until completed |
| Downloaded public MP4 | ffprobe confirmed duration and 1080×1920 |
| Local full export + 6 fps JPG | 23.22 seconds, 610 frames, valid ZIP |
| Local 3-second original-fps PNG | 90 frames, valid ZIP (about 207 MB) |
| Browser timestamps | Both fields and sliders agree; survive refresh |
| Public URL import | Actual original video imported and previewable |
| Public UI MP4 + frames export | 3-second cut, 18 JPG frames; downloaded 6,030,488-byte ZIP passed integrity check; MP4 HTTP Range returned 206 |
| Restart recovery | Stopped idle backend PID 1412; launcher started PID 36724; public health recovered |
| Automated suite | 23 tests passed, including real FFmpeg, upload range requests, timeout and cancellation |

Timings are observations on this machine, not speed guarantees. Detailed JSON evidence
and downloaded videos are under `D:\Projects\MH-Clone\build\clip-backend-evidence`;
user video/data are not committed to Git.

Run tests using the dedicated environment:

```powershell
& D:\Projects\MH-Clone\.tools\clip-fix-env\Scripts\python.exe -m unittest discover -s tests -v
```
