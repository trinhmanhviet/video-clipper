# Compact video studio

Goal: modern, compact desktop editing and a usable phone layout.

Design: light neutral surfaces, violet actions, a dark video stage, restrained
typography. Collapse the native source disclosure after loading a video. Desktop
preview sits beside export options; phones use one column and a fixed export
action with safe-area padding. Touch controls are at least 44px and phone inputs
use 16px text. Keep existing API and control IDs; no framework or font dependency.

## Plan

- [x] Update studio.html and studio.css.
- [x] Bind source filename/disclosure and duration summary in studio.js.
- [x] Inspect desktop, tablet, 390px and 360px layouts with loaded media and frames.
- [x] Verify actual upload/cut/ZIP, refresh and range controls in browser.
- [x] Remove generated test media, preserve real jobs, retain small screenshots.
- [x] Commit and push existing branch; verify public assets.

Visual changes use browser verification, avoiding tests that duplicate HTML/CSS.

Verified: desktop 1905px, tablet 820px, phones 390px and 360px; no horizontal overflow. Phone buttons measured 44–46px; time inputs 16px. A real 0.500–2.500s cut from a dedicated 4-second sample completed, with a valid 12-frame JPG ZIP. Timestamps survived refresh. Test source and outputs were removed; user media and completed jobs were preserved. Screenshots are local under build/clip-ui-preview.
