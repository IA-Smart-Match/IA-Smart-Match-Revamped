# Page 11 — instructor: passcode, data file, teams, unlock

The instructor's one page. Behind a simple passcode: load or replace the
data file, set the invite limit, open results per event, ask for every team
at once, and see or reset each team's work. It is used on a laptop at the
lectern, sometimes projected.

- **Route:** `/exercise/instructor`. Code: `ExerciseInstructor.tsx`, `InstructorDatasets.tsx`, `InstructorTeams.tsx`.
- **System:** [`DESIGN.md` 6.24 and 7.11](../../DESIGN.md#711-instructor-exerciseinstructor), motion `ce-unlock`, `ce-notice-in`, `ce-fade-rise`.
- **Component:** [instructor unlock panel](../components/instructor-unlock-panel.md).
- **Content:** data file, invite limit and teams table in [README section 7](../README.md#7-shared-fictional-data).
- **States:** checking, signed out, wrong passcode, signed in, uploading, upload report, upload refused, move-every-team confirm, team reset confirm, team detail open, ask-for-every-team result, session expired.

## Google Stitch prompt

Screen A (signed out):

```text
Desktop web, 1280px, eggwhite #F8F6F1 page, gold-wash ribbon. Title
"Instructor" (Archivo SemiExpanded 600, 48px); lead "Load a data file, open
results for an event, and see what each team has done."

A centred white card 480px wide, 14px corners, soft shadow, 32px padding:
a key icon in CPP Green #005030, the label "Passcode", a password field
with a show/hide eye toggle, and a full-width primary CPP Green button
"Open the instructor page". Under the button, small #59665F text: "The
passcode is shared by the course team. It is not your university login."
```

Screen B (signed in):

```text
Same page, signed in. Two columns (8/4).

Left column:
1. White card "Open results for an event" (Source Serif 4 32px): meta line
   "For Ann's file, 25 September. Teams can run results only for an event
   that is open." Two rows: "Northline Analytics" with a pale green chip and
   open-padlock icon "Results are open"; "Harbor Consumer Brands" with a
   beige chip and padlock "Results are closed" and a secondary button "Open
   results".
2. White card "Teams": six rows. Each row: a round seal with the team
   number (Archivo bold), "In Ann's file, 25 September — 3 saved settings,
   1 result run.", "Asking: A small reward. Has already asked." and actions
   "Open this team's work" (secondary) and "Clear team 1's work" (quiet red
   text). Use: Team 1 (3, 1, A small reward., asked), Team 2 (2, 1,
   Required., not asked), Team 3 (3, 0, not picked), Team 4 (3, 2, A small
   reward., asked), Team 5 (1, 0, not picked), Team 6 (0, 0, not picked).
   Show Team 2's row with an inline confirm: "This clears team 2's saved
   settings and result runs. No other team is touched." and a red button
   "Yes, clear team 2" beside a quiet "Keep their work".
3. White card "Ask for every team at once": "This runs in one go for every
   team that has picked a way of asking and has not asked yet. If it cannot
   be done, no team is changed." and a secondary button "Ask for every
   team".

Right column (sticky):
4. White card "Data files": a dashed-outline drop zone with a spreadsheet
   icon, "Drop Ann's workbook here, or choose a file", helper "Choose Ann's
   workbook exactly as she sent it. Do not save it as a CSV first.", a
   field "Call this file", and a secondary button "Upload this file". Below,
   one dataset row: "Ann's file, 25 September", "smartmatch_exercise_300.xlsx
   — 300 profiles, 12 events", a number stepper "How many names a list may
   hold" = 30 with "Set the limit", and a quiet button "Move every team to
   this file".
5. A quiet button "Sign out of this browser" with the line "This clears the
   passcode from this browser only. It does not sign out anywhere else."
```

**390 follow-up:** "At 390px, one column in this order: open results, teams,
ask for every team, data files, sign out. Team rows stack their actions
full width."

## Claude Design prompt

```text
Build /exercise/instructor for the Smart Match class exercise with the
preamble tokens, reusing the instructor-unlock-panel component. h1
"Instructor"; lead "Load a data file, open results for an event, and see
what each team has done."

Signed out: centred card (480px): Lucide KeyRound 32px --ce-primary,
<label> "Passcode", password input (autocomplete current-password) with a
show/hide toggle button (aria-pressed, Lucide Eye/EyeOff, 44px target),
primary "Open the instructor page" (full width; "Checking…" while
pending), helper "The passcode is shared by the course team. It is not your
university login." Wrong passcode → calm notice with the server's sentence
inside the card, field kept and refocused.

Signed in, grid 8/4 at 1280, right column sticky:
Left: (1) unlock panel; (2) Teams card — a <ul> of six team rows: seal
(40px circle, --ce-primary-tint, numeral --ce-font-display 700), summary
lines (body 18px), actions "Open this team's work" (secondary; expands an
inline detail with "Saved settings" and "Result runs" lists) and "Clear
team N's work" (quiet --ce-danger text → inline confirm with destructive
"Yes, clear team N" and quiet "Keep their work"); (3) "Ask for every team at
once" card with secondary "Ask for every team" → "Asking for every team…" →
done line (role status, --ce-avocado-tint): "Asked for 1 team (2).
Skipped 5."
Right: (4) "Data files" card: dropzone (<label> wrapping a file input
accepting .xlsx; dashed 2px --ce-line-strong, Lucide FileSpreadsheet 32px;
drag-over = --ce-primary outline + --ce-primary-tint wash), field "Call this
file", secondary "Upload this file". Uploading shows three stages in text
("Reading the file" → "Checking the columns" → "Saved") with a thin
determinate bar for the file transfer only. Upload report: calm notice with
the server's own sentence, then a <dl> grid: Profiles 300, Events 12, Events
in the exercise 2, Profiles with no card 230, Different interest words 18,
Different topic words 18. Dataset row with label, "smartmatch_exercise_300
.xlsx — 300 profiles, 12 events", an invite-limit number input (label "How
many names a list may hold", min 1) + secondary "Set the limit", and quiet
"Move every team to this file" → inline confirm "This moves every team to
this file and clears the work of every team it moves." with destructive
"Yes, move every team here" and quiet "Keep them where they are". (5) quiet
"Sign out of this browser" + its helper line.

States for the switcher: Checking (skeleton) · Signed out · Wrong passcode ·
Signed in · Uploading · Upload report · Upload refused (calm notice with an
illustrative server sentence "The workbook is missing the column
stated_interests." and the chosen file name kept) · Move-every-team confirm
· Team reset confirm · Team detail open · Ask-for-every-team done · Session
expired (calm notice "Enter the passcode again to continue." and the
passcode card) · 390.

Destructive actions confirm inline, never in a modal. Only transport
failures use a red outline.
```

## Review checklist

1. Unlock comes first on the page; data files sit to the side.
2. Every destructive action states exactly what it clears and confirms inline.
3. The passcode page does not look like a university sign-in.
4. The upload shows the server's own report sentence.
