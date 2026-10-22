# Reliable PC video backend — 2026-10-23

**Goal:** Make video.multigen.store reliably cut the user's real portrait video,
with accurate timestamps, visible progress and persistent downloadable results.

**Architecture:** A new Flask/Waitress app on 127.0.0.1:8790, a SQLite job/media
store, a bounded single-job executor and FFmpeg subprocess progress with timeout.
Only opaque media IDs are accepted from the public API. Data lives under this
tool's own folder. Cloudflare Tunnel provides HTTPS without opening inbound
ports. The existing Render version remains available for rollback until the
PC backend and public-domain tests pass.

**User scope:** Keep video.multigen.store; PC may be the backend. Preserve game,
Comfy, existing tunnel routes, and the user's original video.

## Work

- [x] Reproduce the current long job using the actual 39,855,434-byte 1080x1920,
  30fps input and 38.379–140.068s cut. Record wall time, duration and video frames.
- [x] Add failing tests for durable jobs, exact range validation, media-ID-only
  lookup, progress and cancelled/time-limited subprocesses.
- [x] Implement `studio.py` and `processing.py`: persistent jobs, one active
  export, real FFmpeg progress, bounded CPU threads, explicit output checks,
  MP4/MP3/frame ZIP, nonblocking URL import and cooperative cancellation.
- [x] Implement `templates/studio.html`, `static/studio.js` and `studio.css`:
  chunked uploads, preview and frame stepping, timestamp/range controls,
  visible progress/elapsed time, job recovery after refresh, result preview.
- [x] Run local HTTP end-to-end on real input. Do not claim completion from a
  synthetic one-second fixture. Check both the full requested cut and frames.
- [x] Start backend/tunnel persistently and configure only this hostname after
  local verification. Verify public upload/cut/download and refresh recovery.
- [x] Save measured evidence, deployment/start/stop instructions and source.

## Acceptance

No indefinite "processing": all jobs reach a persisted terminal state, timeout
or can be cancelled. Refresh recovers progress. Cut timestamps are precise to
the source frame rate; optional packet-copy mode is explicitly approximate.
Tests and measured wall time must use the real user video. PC must be on and
connected for this deployment; explain that limitation clearly at handoff.
