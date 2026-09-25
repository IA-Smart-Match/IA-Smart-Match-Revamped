# CE-DATASET — the class exercise reads Ann's workbook

Ann's final data file arrived 2026-09-24 (`SmartMatch_Student_Body_300.xlsx`, plus a
20-row sample). This plan replaces the placeholder CSV layout (OQ-CE-01) so the
instructor uploads Ann's `.xlsx` as-is. Owner rulings of 2026-09-24 are inputs, not
questions.

Branches: `feat/exercise-ann-dataset` (code, this plan), then
`docs/exercise-ann-dataset` (register, spec, proposal) after code review.

## Decisions taken here

| # | Decision | Why |
|---|---|---|
| 1 | Upload is the `.xlsx` bytes as the raw body; the CSV path is removed | Owner ruling 1; no multipart (ruling 2026-09-21) |
| 2 | Zip guard runs on the ZIP central directory **before** openpyxl opens the file: entry count, total and per-entry uncompressed size, compression ratio | Owner ruling 1; CPython's `ZipExtFile` stops at the declared size, so the declared sizes bound real output |
| 3 | openpyxl `read_only=True, data_only=True`; refuse all uploads if `openpyxl.DEFUSEDXML` is not `True` | Fail closed on XML entity attacks |
| 4 | Read only `Profiles` and `Events`; never `Read Me` or `Benchmark` | Brief |
| 5 | Not read: `events_attended_count`, `info_level`, `event_type`, `event_date` | All derivable or display-only; nothing shows them. Not required columns |
| 6 | `card_completed` is the card flag. `No` with interests or goal on the row is refused | The file states it; a contradiction is not guessed |
| 7 | `seats` is read on the two exercise events and must equal `EVENT_SEATS` (60) | The simulation runs with 60; a file saying otherwise is refused rather than ignored |
| 8 | `sequence` = the event's row position on the `Events` sheet | Ann's file has no position column; E01–E12 are in order |
| 9 | `"All majors"` is expanded at ingest to the six majors | `same_major` stays a pure set test; every reader sees concrete majors |
| 10 | Topics, majors, years and goals are closed vocabularies in `smartmatch_domain.exercise.vocabulary`; cells are matched by the existing fold and stored as Ann's spelling | Ruling 6; `Supply chain / logistics / operation` kept verbatim |
| 11 | Career goal fit uses `CAREER_GOAL_TOPICS`, marked `PLACEHOLDER (Ann to confirm role→topic table)`, applied where a card becomes evidence | Ruling 2; the stored goal stays Ann's label |
| 12 | Last tie-break step reads `tiebreak_order`; datasets without it keep the SHA-256 order | Ruling 3 |
| 13 | Year rank Senior 4 > Junior 3 > Sophomore 2 > Freshman 1, in the domain vocabulary; the API's placeholder constant becomes `EXERCISE_CLASS_YEAR_RANK` | Ruling 4 |
| 14 | Copied cards carry `hidden_true_interests` and `hidden_true_career_goal` (`CopiedCardCareerGoal.HIDDEN_GOAL`) | Ruling 5, OQ-CE-13 |
| 15 | Migration `0042_exercise_ann_dataset`: `exercise_profile.hidden_true_career_goal` (withheld) and `tiebreak_order` (`>= 1`, unique per dataset) | Brief |
| 16 | Migration 0037's historical PLACEHOLDER comments stay | An applied revision is history |

## Milestones (commit + push each)

1. Plan (this file).
2. Red: domain tests for the workbook reader, vocabulary, ingest, tie-break, asking; golden test from Ann's Read Me.
3. Green: domain.
4. Migration, persistence, API, frontend, deps and locks; their tests.
5. Opus code review + security review of the xlsx parser; fix CRITICAL/HIGH/MEDIUM.
6. Docs PR.

## Golden test (Ann's Read Me)

P004 (Accounting, card states Technology / information systems) against a plain
Accounting major for E11 (Northline). Pinned on the 300-row file restricted to the
20 sample IDs, because design spec §3's 50-profile floor refuses the 20-row file by
itself. Any gap between Ann's wording and the tie-break (§4.4) is reported to the
owner rather than coded around.
