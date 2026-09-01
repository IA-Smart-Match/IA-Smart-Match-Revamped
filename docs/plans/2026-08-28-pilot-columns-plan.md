# Implementation plan — pilot column decisions: board_role and contact fields

**Date:** 2026-08-28 · **Plan id:** P9 · **Worktree branch:** `plan/pilot-columns`
**Executor:** frontier orchestrator agent (high reasoning) delegating fenced task
cards to subagents. Self-contained; no chat history required.

> **Amended/superseded for scope — 31 August 2026.** This plan's cards are
> superseded for scope by
> `docs/superpowers/specs/2026-08-31-ratification-and-feature-delivery-design.md`
> §6 (slice V2) and recorded in
> `docs/decisions/2026-08-31-session-ratification.md` §7. **Authorized now:**
> only the four static HTTPS URL-shape validation rules (§6.1 of the
> design), and only where no persistence, DNS/network call, or contact-data
> path is opened. Raw URL persistence remains blocked without a separately
> approved host/path projection. **Gate A (`board_role`) and Gate B
> (contact-field collection) below remain open exactly as this plan already
> states, and no branch may run past its own gate.** See
> `docs/decisions/p9-gate-a-board-role-decision-draft.md` and
> `docs/decisions/p9-gate-b-contact-fields-worksheet.md` for the recorded
> working directions, neither of which closes its gate. A later agent may
> not select a card from this file without first checking the current
> authorized boundary in the design and the ratification record.

## Standing constraints (restated)

- No real PII in fixtures or tests — synthetic values only.
- ADR-0014: "published" provenance is not consent for platform disclosure or
  outreach; contact data stays out of event titles, tags, metric drill-downs,
  and public payloads unless the approved policy explicitly permits it.
- No push, no PR, no production-readiness claims.

## Stop-gates (two independent decisions; branches select separately)

### Gate A — `board_role` (Dr. Wang)

Committed artifact (expected under `docs/decisions/`, building on
`docs/pilot-data/board-role-decision-prep.md`) answering:

1. Is `board_role` intrinsic to a professional, or scoped to that person's
   relationship with one unit/chapter?
2. If relationship-scoped: multiplicity (multiple simultaneous roles?),
   effective dates, and source semantics.

### Gate B — public URL / contact fields (Dr. Wang + privacy owner)

Committed artifact (building on
`docs/pilot-data/event-contact-fields-decision-prep.md`) with an explicit
**collect or drop** per field: `Public URL`,
`Point(s) of Contact (published)`, `Contact Email / Phone (published)`.
If any contact field is collected, the artifact must also record purpose,
minimization, retention, correction path, and who may view/export.

Gates pass independently; run only the branches whose gate passed. If a gate
artifact is missing or leaves alternatives open: stop that branch and report.

## Current state (verifiable)

- `docs/pilot-data/columns.yaml`: `board_role` sits under
  `professionals.optional` as an explicitly documented holding position; the
  three contact fields sit under events optional; both are `open_questions`.
- **Not wired:** `smartmatch_worker.handlers` calls
  `validate_columns(..., required=(), optional=())` (~line 570) — the ratified
  contract does not yet constrain imports. Wiring it is card W1 (J10), a
  deliberate separate slice.
- `docs/pilot-data/verify_fixtures.py` + fixtures verify the contract shape.
- `Opportunities.tsx` reads `event["Public URL"]` from the legacy path only.

## Branch A1 — `board_role` stays a flat professional attribute

- **Fence:** `docs/pilot-data/columns.yaml` commentary,
  `docs/pilot-data/README.md`, fixtures + `verify_fixtures.py`.
- **Work:** remove the open question; document the ratified flat semantics;
  fixtures exercise presence/absence; discard the relationship interpretation
  explicitly in commentary.

## Branch A2 — `board_role` is a unit-relationship record

Lanes after a joint schema-shape review against the artifact's multiplicity
and effective-date answers:

- **A2a (serial migration resource):** new expand-phase migration + 
  `smartmatch_persistence/schema.py`: tenant/unit-anchored relationship table
  (professional ↔ unit, role, effective dates per the artifact); tenant
  isolation and schema-drift tests; migration integration test.
- **A2b (parallel):** `columns.yaml` moves `board_role` out of
  `professionals`; import-mapping design doc for how a flat CSV column maps
  into relationship rows; fixtures covering one person in two units with
  different roles — and rejecting the discarded flat interpretation.
- **A2c (join):** wire import mapping in the worker for the relationship rows
  (depends on W1).

## Branch B — per-field collect/drop

For each field the artifact **drops**:

- **Fence:** `columns.yaml`, `README.md`, fixtures.
- **Work:** remove from the optional list; update fixture verification;
  note in `Opportunities.tsx`'s inventory (plan P8 card O4a removes the legacy
  read path — coordinate, don't duplicate).

For each field the artifact **collects**:

- **Fence:** fixtures + validation module + tests first; worker wiring only
  after W1.
- **Work:** synthetic valid/invalid fixtures (absent URL, valid URL, named
  contact, email, phone — all fake); validation findings named per the
  contract's finding style; redaction expectations encoded as tests: collected
  contact values never appear in event titles, tags, metric drill-down rows,
  or any public payload unless the policy explicitly names the audience.
  Role/minimum-disclosure tests per ADR-0014 before any UI/API exposure.

## Card W1 — wire columns.yaml into worker validation (J10; after either gate)

- **Fence:** `smartmatch_worker` handlers (validate_columns call site) + unit
  tests + fixture-backed tests.
- **Work:** bind `validate_columns` required/optional arguments to the ratified
  contract loaded from `columns.yaml` (single source of truth — no duplicated
  literal lists); imports violating the contract produce named findings into
  the existing quarantine/review path, not silent drops.
- **Partial-ratification rule:** enforcement is **section-level**. W1 wires
  only the sections whose gate has passed: after Gate A alone, professional
  columns are enforced while the three contact fields remain in an explicit
  `undecided` posture (accepted as optional, flagged for review, never
  rejected and never rendered); after Gate B, event contact sections wire in
  per their collect/drop outcomes. W1 must not treat a still-open
  `open_questions` entry as ratified contract.
- **Note:** W1 is valuable after *any* gate ratifies its section; do not bury
  it inside a documentation change (it is its own reviewable slice).

## Evidence ladder

1. `python docs/pilot-data/verify_fixtures.py`; focused pytest for worker
   validation; `make check`
2. **CI-only proof:** migration (branch A2) on PostgreSQL; full import-path
   integration tests.

## Done means

- Each decision is written, and fixtures cover the chosen shape while
  rejecting the discarded one.
- Worker validation enforces the ratified contract (W1).
- No collected contact value can reach a public surface without the policy's
  named audience; drops are fully removed, not just undocumented.
