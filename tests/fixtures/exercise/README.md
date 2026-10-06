# Class-exercise fixtures

Fictional profiles shaped by overall survey percentages. All student profiles
are fictional (decisions D13 and D15 in
`docs/decisions/class-exercise-decisions-2026-09-25.md`).

## The files

| File | What it is | Read by |
|------|------------|---------|
| `SmartMatch_Student_Body_300.xlsx` | Ann's full workbook of 2026-09-24, sheets `Profiles` (300 rows) and `Events` (12 rows). **Source of truth** for the `.accdb` and the CSV. | `tests/unit/exercise_workbooks.py`, the golden tests |
| `SmartMatch_Student_Body_300_10022026.xlsx` | Ann's full workbook of 2026-10-02, cut to the same two sheets. The September file plus one last `Events` column, `event_description` (Northline 571 characters, Harbor 561, blank on the ten past events). Every other cell equals the September file. **The file the instructor uploads now.** | `tests/unit/exercise_workbooks.py` (`ANN_OCT02_FILE`) |
| `SmartMatch_Student_Body_Sample_20.xlsx` | Ann's 20-row sample. Refused by the parser by design (below the row floor). | `tests/unit/exercise_workbooks.py` |
| `SmartMatch_Student_Body_300.accdb` | Derived Microsoft Access copy of the 300 workbook, for Access users. Tables `Profiles` and `Events` equal the xlsx cell for cell; `Attendance` holds the 162 `(profile_id, event_id)` pairs split out of `Profiles.events_attended`. | `tools/compute_event_major_fit.ps1` |
| `../../../test_data/event_major_fit.csv` | Chau's derived major-fit table: one row per profile, `E11_major_fit` and `E12_major_fit` (1 = the profile's major is the event's target major, or the event is "All majors"). | `tests/unit/test_exercise_event_major_fit_csv.py` |

The app itself only reads `.xlsx` uploads. The `.accdb` and the CSV are
conveniences for working with the data outside the app.

## Rules

1. The xlsx is the source of truth. If it changes, rebuild the `.accdb` and
   regenerate the CSV; never edit them by hand to disagree with it.
2. The `.accdb` must never hold document metadata. Before committing a new
   copy, clear Author, Company and LastAuthor under File > Info > Properties,
   and check it has no machine paths, user names or email addresses.
3. Never commit an Access lock file (`*.laccdb`, `*.ldb`). They record the
   machine and user name of whoever has the database open; `.gitignore`
   excludes them.
4. `test_exercise_event_major_fit_csv.py` recomputes the CSV from the xlsx
   through the real parser and fails if the two drift apart.
5. A new workbook from Ann is cut before it is committed: keep the `Profiles`
   and `Events` sheets, remove `Read Me` and `Benchmark`, and reset the
   document properties so no person's name is in the file (decision D4).
   `*.xlsx` is ignored repository-wide, so add it with `git add -f`.

## Open manual step: the `.accdb` and the October file

The `.accdb` mirrors the **September** workbook. Its `Events` table has no
`event_description` column. Rebuilding it from the October workbook needs
Microsoft Access on Windows and has not been done. Until it is, treat the
`.accdb` as the September data: the profiles and the other event columns are
the same in both files, so `test_data/event_major_fit.csv` is unaffected.

## Regenerating the major-fit CSV

On Windows with the Microsoft Access ODBC driver installed, from the repository
root:

```powershell
powershell -ExecutionPolicy Bypass -File tools/compute_event_major_fit.ps1
```

This opens the `.accdb` read-only and rewrites `test_data/event_major_fit.csv`.
Pass `-DbPath` or `-CsvPath` to use other files. Pass `-WriteTable` only if you
also want an `EventMajorFit` table written into the database; do not commit a
`.accdb` changed that way.

## Credit

The Access dataset idea, the major-fit rule, the PowerShell script and the CSV
are Chau's work (PR #243). The committed `.accdb` is a clean rebuild of her
copy.
