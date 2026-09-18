# Class exercise — open-question register

**Status:** scoped register for `ProductScope.CLASS_EXERCISE`, created
2026-09-16. Rows here concern the class exercise only. Nothing here closes an
OQ-SC, OQ-SE, or OQ-CBA row, and nothing in those registers closes a row here:
the exercise stores no real student and no real event, so the privacy, records,
and consent questions of the CBA track do not arise in it.

**Owner of the scope:** Ann Wang (instructor and project lead). Placeholders
below are the numbers in her build table and stay in force until she confirms
or replaces them.

| ID | Decision question | Owner | Placeholder / safe default | Blocks | Status |
|---|---|---|---|---|---|
| OQ-CE-01 | What are the final column names and value vocabularies of the data file (major, year, past events, stated interests, career goal, hidden true interests)? | Ann | None — the 20-row sample due Fri Sept 18 answers this. Until then the spec's data model is marked PLACEHOLDER. | Ingest, factors, markers | OPEN — waits on 9/18 |
| OQ-CE-02 | What default weights do the four factors carry when a team opens an event? | Ann + Chau | Equal weights (0.25 each), shown in plain words. | Matching | OPEN |
| OQ-CE-03 | What are the four coefficients of the simulated-results rule (true-interest fit lift, frequent-attender lift, same-major lift, chance size)? | Ann + Chau | Chau proposes; Ann confirms before the November practice run. | Results | OPEN |
| OQ-CE-04 | What are the three "asking for more" percentages? | Ann | 30 percent / 55 percent / 80 percent with 15 percent non-responding, as named constants. | Refresh | OPEN — Ann confirms before the practice run |
| OQ-CE-05 | Is the data file CSV or XLSX? | Ann + Danny | CSV read with the standard library. XLSX would add `openpyxl` as a runtime dependency for one screen. | Ingest | OPEN — ask on 9/18 |
| OQ-CE-06 | Where does the site live and what is its stable address? | Danny | The pilot VM path in `docs/operations/vm-deploy.md`, exercise scope only, no CBA routers registered. | Hosting | OPEN |
| OQ-CE-07 | How is the instructor passcode set and shared with Ann and Dr. Lin? | Danny + Ann | One environment variable per deployment; shared out of band; rotated after the spring run. | Instructor page | OPEN |
| OQ-CE-08 | Do two browser tabs that enter the same team number share one workspace, or is each tab its own workspace? | Ann | Shared per team number: Ann's table says "one browser tab per team, team number entered", so a second tab on the same team sees the same saved runs. | Team workspaces | OPEN — confirm on 9/18 |
| OQ-CE-09 | What license line goes on the opening screen? | Ann | None shown until Ann provides the sentence. | Opening screen | OPEN — by Nov 20 |

## Closure discipline

A row closes with a dated line naming who decided and what. Ann's Friday
check-in notes are sufficient evidence for this register.
