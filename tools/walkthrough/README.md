# Student walkthrough recorder

Records the student flow (pick team, Northline, save a setting, send the list, ask once, Harbor, results) as a 1280x720 .webm with Playwright. No captions.

```
cd tools/walkthrough
npm install && npx playwright install chromium
WALKTHROUGH_BASE_URL=http://localhost:5273 WALKTHROUGH_OUT_DIR=/path/to/video node record_student_flow.mjs
```

Environment only (nothing is stored in the repo):
- `WALKTHROUGH_BASE_URL` (required; only localhost or 127.0.0.1 unless `WALKTHROUGH_ALLOW_REMOTE=1`. The run writes data: clear Team N afterwards)
- `WALKTHROUGH_OUT_DIR`, `WALKTHROUGH_TEAM` (default 1), `WALKTHROUGH_PAUSE_MS` (default 7000), `WALKTHROUGH_MIN_MS` (default 210000; the recording is padded to at least this)
- `EXERCISE_INSTRUCTOR_PASSCODE` (optional; signs in on the instructor page in an unrecorded window and opens results for every event. Without it, open results on the instructor page before recording)

Not yet run end to end: the selectors follow the exercise pages; first run may need small fixes.
