> DRAFT — needs Danny (program owner of record) decision, with the records/privacy, metrics and security owners (privacy owner unnamed, see #296). Nothing here is decided.

# #302 — W4 engagement metrics: packets for OQ-SE-04 to OQ-SE-08

**Standing rule: W4 is STOPPED. Do not build counts-only and do not expose rows meanwhile** (`docs/plans/README.md:48-51`; `docs/plans/2026-09-14-student-engagement-program-plan.md:127-129`; register default for SE-05, `docs/plans/open-questions/student-engagement-deferred.md:44`). ADR-0011 is not superseded or weakened (`plan:128`). W4 = slice 8, gated on SE-04..08 (`plan:58`).

**Sources:** register rows `:43-47`; ADR-0011 rules 1-4 (`docs/architecture/decisions/ADR-0011-accountable-numbers.md:51-88`); existing role packet `docs/decision-packets/metrics-authz.md`. Closure of any row needs a dated attributed artifact plus the evidence in the row (`register:12`). Safe defaults are not decisions (`register:4-6`).

**What exists in the schema (facts, not choices):**
- `event_registration`: `tenant_id`, `owning_unit_id`, `event_id`, `subject_id`, `status` in {`registered`,`cancelled`}, `registered_at`, `updated_at`; one row per student per event whatever its status (`python/smartmatch_persistence/smartmatch_persistence/schema.py:2749-2790`, unique `uq_event_registration_subject_event`).
- `attendance_record`: `tenant_id`, `owning_unit_id`, `subject_id`, `event_id`, `method`, `created_at` (`schema.py:438-453`). Registration is deliberately not an attendance method (`schema.py:2753-2756`).
- `pipeline_record` measures the speaker-handoff journey, not registration-to-attendance (`plan:112-113`; register SE-04 default).

Order below is the dependency order: each later packet assumes the earlier one is answered.

## 1. OQ-SE-04 — which metric, which one owning query?
- **Question:** what registered engagement metric(s) and exactly one query join `event_registration` to `attendance_record`, on what event/time/cohort basis? (`register:43`)
- **Blocks:** SE-05..08 (they need something to protect); the registered-metric entry and fixture cases; also the OQ-SE-03 attribution question (see #301 draft SE-03c).
- **Options:**
  1. One metric: attended / registered, per event, per unit. Single query; simplest reconciliation.
  2. Two or more metrics (for example registered count, attended count, attended-of-registered rate), each its own name and own query. ADR-0011 rule 3 forbids variants filtered in the view layer, so each needs its own entry (`ADR-0011:71-80`).
  3. A funnel (registered -> attended) as a set of mutually consistent metrics. ADR-0011 notes five separate queries will not stay consistent, so it implies one shared query or CTE.
- **Open sub-points:** whether `cancelled` registrations count in the denominator; whether attendance without registration counts; how an empty set renders (ADR-0011 rule 1: `unknown`, never `0`, `ADR-0011:51-58`). Unknown whether `registered_at`, `event` date, or `created_at` is the time basis.
- **Safe default in force:** no registration-to-attendance aggregate; `pipeline_record` excluded (`register:43`).
- **Who decides:** program owner + metrics owner + records/privacy owner (`register:43`).

## 2. OQ-SE-06 — which students and events are in the population?
- **Question:** which students/events count, including profiles absent, deleted, or changed during the period? (`register:45`)
- **Blocks:** any published number; edge-case query fixtures (`register:45`).
- **Options:**
  1. Everyone with an `event_registration` row for events in a stated window, regardless of later profile state. Stable counts; keeps rows about students whose profile was later deleted (a retention question).
  2. Only currently-existing active students at read time. Counts move retroactively when profiles are deleted.
  3. A snapshot at period close, stored. Reproducible numbers; adds a stored snapshot (itself a retention/privacy decision).
- **Also to state:** event window basis; cohort or unit scope (`owning_unit_id`); treatment of cancel-then-re-register (one row, `registered_at` never moves, `schema.py:2775-2777`).
- **Safe default in force:** no population inferred, no number published (`register:45`).
- **Who decides:** program owner + metrics + records owners.

## 3. OQ-SE-05 — which constituent fields satisfy ADR-0011?
- **Question:** which exact row fields and privacy treatment does the drill-down return so it reconciles to the aggregate? (`register:44`)
- **Blocks:** the drill-down route, row schema, authorization tests, and the "exact reconciliation" evidence.
- **Constraint:** the drill-down returns exactly the rows the aggregate was computed from, same query (`ADR-0011:82-88`); a counts-only aggregate with no drill-down is a conflict the register does not resolve (`plan:127-128`).
- **Options:**
  1. Full constituent rows for authorized roles (`subject_id`, `event_id`, `status`, timestamps, attendance `method`). Satisfies reconciliation directly; exposes student identifiers to whichever roles SE-08 names.
  2. Pseudonymized constituents (stable opaque id in place of `subject_id`). Reconciles by count; needs a pseudonym mapping and a rule for who can resolve it.
  3. Rows only above the SE-07 suppression threshold, with suppressed cells carrying no drill-down. Needs an agreed exception to rule 4; ADR-0011 is not weakened here (`plan:128`), so this option needs an explicit ADR-0011 reading by its owner.
- **Safe default in force:** W4 STOPPED; do not choose counts-only or expose rows (`register:44`).
- **Who decides:** records/privacy + metrics + security owners (`register:44`). Disclosure standard: ADR-0014 minimum disclosure; aggregate access does not authorize row-level payload (`metrics-authz.md`, quoting ADR-0014).

## 4. OQ-SE-07 — suppression threshold and complementary cells
- **Question:** what minimum cell size is suppressed, and what rules stop derived totals reconstructing a suppressed cell? (`register:46`)
- **Blocks:** any published small-cell number; reconstruction/adversarial tests.
- **Options:**
  1. A fixed minimum (one value for all W4 aggregates). Simple to test. Precedent only, not adopted: OQ-CBA-003 suppresses speaker-feedback mean and count below three responses (`cba-phase-deferred.md:15`).
  2. Per-metric thresholds. Fits different populations; more rules to test.
  3. Threshold plus complementary suppression (hide a second cell, or the total, when one cell is hidden). Needed whenever a total and its parts are both shown; costs more screens/tests.
- **Interaction:** a suppressed cell conflicts with SE-05 option 1 (drill-down must return the same rows) unless SE-05 answers it.
- **Safe default in force:** publish neither small cells nor derived totals that reconstruct them (`register:46`).
- **Who decides:** records/privacy + metrics owners.

## 5. OQ-SE-08 — role matrix for aggregates and exact rows
- **Question:** which roles read W4 aggregates; which read exact rows? (`register:47`)
- **Blocks:** allow/deny tests for aggregate and exact-row routes.
- **Options** (also framed in `metrics-authz.md`, which selects none):
  1. Extend the closed policy unchanged: aggregates readable by any active unit membership (except speaker-only principals), drill-down `{admin, coordinator}` (`docs/decisions/metrics-authorization-decision-draft.md:35`, `:63-64`, `:72`).
  2. A narrower policy for W4 specifically (for example `{admin, coordinator}` for both). Matches the register default; second policy matrix and test set.
  3. Widen to Event Host (`volunteer`). Excluded today by OQ-SC-13 and OQ-CBA-042 (`register:34`; `cba-phase-deferred.md` OQ-CBA-042 quoted in `metrics-authz.md`); owners would need to say why engagement differs.
- **Safe default in force:** `{admin, coordinator}` only for any read; no Host access (`register:47`).
- **Who decides:** program owner + records/privacy + security owners; consider OQ-CBA-042 and OQ-SC-13.

## Register fact to settle
The SE-08 safe default says `{admin, coordinator}` for **any** read (`register:47`), while the closed 2026-09-02 metrics decision lets any active unit membership read aggregates (`metrics-authorization-decision-draft.md:63`). Both are "in force" for different surfaces; option 1 vs 2 in SE-08 decides which governs W4.

## Open questions
1. SE-04: which metric set and basis (cancelled in denominator? attendance without registration?) — program owner + metrics owner + records/privacy owner.
2. SE-06: population and time basis, and treatment of deleted/changed profiles — program owner + metrics + records owners.
3. SE-05: constituent fields and pseudonymization, and whether suppressed cells get a drill-down — records/privacy + metrics + security owners.
4. SE-07: threshold value, per-metric or global, complementary-cell rule — records/privacy + metrics owners.
5. SE-08: W4 roles for aggregates and rows; does the closed metrics policy extend? — program owner + records/privacy + security owners.
6. Who is the records/privacy owner for these rows (none named for B26, #296)? — Danny.
