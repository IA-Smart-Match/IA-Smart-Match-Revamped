# Student walkthrough recorder

Records the student flow (pick team, pick event, read the list, open results) as a 1280x720 .webm with Playwright. No captions.

```
WALKTHROUGH_BASE_URL=http://localhost:5273 WALKTHROUGH_OUT_DIR=/path/to/video npx -p playwright node tools/walkthrough/record_student_flow.mjs
```

Environment only (nothing is stored in the repo):
- `WALKTHROUGH_BASE_URL` (required)
- `WALKTHROUGH_OUT_DIR`, `WALKTHROUGH_TEAM` (default 1), `WALKTHROUGH_PAUSE_MS` (default 4000; tune for a 3 to 5 minute video)
- `EXERCISE_INSTRUCTOR_PASSCODE` (optional; unlocks instructor results in an unrecorded window first)

Needs Chromium installed (`npx playwright install chromium`).
