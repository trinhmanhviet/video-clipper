# Integrated video source and trim range

User-specified design: place URL input permanently above preview; drop/select
files directly in preview; local remove button returns to an empty chooser;
one visible track with two draggable, keyboard-accessible range handles.
Keep the other control positions and mobile export action. Use a mildly dark
slate palette. Removing the open video does not delete server files/results.

- [x] Test handle bounds and crossing before implementation.
- [x] Merge source markup into always-visible preview; add remove and empty state.
- [x] Implement one-track range and UI lifecycle, preserving job processing.
- [x] Verify real file selection/replacement, both handles and phone layout.
- [x] Clean generated test files; save small screenshots; push source.

Verified five Node tests; file chooser, remove/reselect and both mouse-drag handles in Chrome. Keyboard End stops the start handle before the end. At 360px there is no horizontal overflow and the URL remains above preview. A 1.000–3.000s export completed with a 12-frame download link. Final external verification was unavailable during the earlier approval outage; UI export completion and the range tests were verified. Source is included in the subsequent retention update. Generated sample media were cleaned locally.
