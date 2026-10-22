# FFmpeg export fix — 2026-10-22

## Findings

The deployed `/api/logs` repeated the FFmpeg build banner because the worker
discarded stderr after its first 300 characters. The original decoder error
cannot be recovered from that log. Both uploaded source names from the failed
jobs now return 404. The most recent attempt used a source uploaded over nine
hours earlier; the service deletes inactive files after one hour.

The old `-threads 2` preceded `-i`, limiting input decoding only. A real local
720p encode still reported `threads=18 lookahead_threads=3` in libx264. Encoding
is now explicitly limited on the output side as well. This addresses excess
parallel resource use; it does not establish the unseen cause of the earlier
20-second failed jobs.

## Changes

- FFmpeg runs without its build banner, reports the final useful error lines
  plus exit code, and retains full stderr in per-job cut/frame logs.
- Output video/audio encoders and filters have explicit thread limits.
- Expired/missing uploads give a clear re-upload instruction before launching
  FFmpeg. Playback refreshes inactivity retention; cleanup skips sources/output
  folders while jobs use them, including overlapping jobs on one upload.
- Invalid time ranges fail before processing. Frame extraction errors or zero
  frames cannot silently create a successful empty ZIP.
- Output folder suffixes distinguish jobs started during the same second.
- Error text preserves line breaks and scrolls inside the modal.

## Verification

Run `python -m unittest discover -s tests -v` in an isolated environment with
the project requirements. Thirteen tests cover worker failures, cleanup and
encoder options, plus real FFmpeg 720p/4K cuts, MP3 export and a six-frame ZIP.
An invalid MP4 surfaces the actual `moov atom not found` / decoder error.

`/api/health` reports processing revision `2026-10-22-ffmpeg-errors-v1` so the
deployed version can be confirmed before the online end-to-end check.
