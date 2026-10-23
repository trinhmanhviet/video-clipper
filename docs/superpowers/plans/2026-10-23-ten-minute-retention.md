# Ten-minute file retention

User request: show storage location and automatically remove files after ten minutes.

Design: retain source media, exports/frames/ZIP and partial uploads for 600 seconds
after their last actual use or job completion. Polling job status is not activity.
Protect queued/running jobs, uploads and open HTTP file responses. Transfer close
starts a fresh ten-minute window. Sweep every 30 seconds. Grant existing records
one initial ten-minute window when enabling retention. Keep tiny expired metadata
to explain why a download is unavailable. Constrain all deletes to data subfolders.

- [x] Add and run failing tests for expiration, active jobs/transfers and path bounds.
- [x] Implement retention service and integrate API file leases and upload activity.
- [x] Handle expiration in UI and send throttled touches on actual editing/playback.
- [x] Verify tests and activate on the idle backend; verify configured TTL is 600.
- [x] Clean test artifacts and update deployment documentation.

Live public health confirmed retention_enabled=true, retention_seconds=600 and cleanup_interval_seconds=30. Fourteen retention tests and the existing processing suite passed. Legacy test scratch directories were removed.
