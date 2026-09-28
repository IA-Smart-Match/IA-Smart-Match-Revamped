# Class-exercise fixtures

Fictional profiles shaped by overall survey percentages. All student profiles
are fictional (decisions D13 and D15 in
`docs/decisions/class-exercise-decisions-2026-09-25.md`).

## The files

| File | What it is | Read by |
|------|------------|---------|
| `SmartMatch_Student_Body_300.xlsx` | Ann's full workbook, sheets `Profiles` (300 rows) and `Events` (12 rows). **Source of truth.** | `tests/unit/exercise_workbooks.py`, the golden tests |
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
