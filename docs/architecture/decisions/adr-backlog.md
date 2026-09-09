# ADR backlog — decisions that need a record and cannot get one yet

**Stage 2, 8 September 2026.** Companion to `README.md`.

Every entry here is a decision this repository will have to record durably, and
cannot record today — because the evidence does not exist yet, or because the
answer belongs to someone who is not engineering. Writing a Proposed ADR without
either would produce a document whose Context is a guess, which is worse than an
empty slot: an ADR is read as a decision with reasoning behind it.

**The filename is deliberate.** This file is *not* named `ADR-BACKLOG.md`.
`tests/unit/test_adr_index.py` globs `ADR-*.md` in this directory and asserts
every match is `ADR-NNNN-slug.md`; a file called `ADR-BACKLOG.md` fails that
assertion and takes the whole no-database lane with it. Lowercase keeps the name
readable and outside the glob.

Nothing here is scheduled by being listed. An entry graduates when its "evidence
still needed" column is satisfied and its owner has answered.

---

## The backlog

### B-01 — Retention period per append-only table

- **Candidate title:** Retention and deletion policy for the append-only tables
- **Would decide:** how long `job_event`, `delivery_event`,
  `contact_channel_transition`, `pilot_login_attempt` and `match_run` snapshots
  are kept, per table, and what "deleted" means for each — dropped, aggregated,
  or exported first. `match_run` is the awkward one: ADR-0011's reproducibility
  argument depends on a snapshot being re-readable, so its retention is a
  product commitment rather than a storage decision.
- **Why not now:** the answer is a policy, not a measurement. At pilot volume
  none of these tables is near a size that forces a decision (R-13 is P3 for that
  reason), and choosing a number in the absence of a stated obligation would
  record engineering's preference as the institution's policy.
- **Evidence still needed:** the institution's records-retention obligation for
  login attempts and delivery events; the product answer on how far back a match
  run must be reproducible; observed growth rates once the pilot has run long
  enough to have any.
- **Owner:** institution (records policy) and product owner (match-run
  reproducibility).
- **Related:** R-13, OQ-S2-003.

### B-02 — Whether migration downgrade is a supported operation

- **Candidate title:** Migration downgrade is (not) a supported operation
- **Would decide:** whether `downgrade()` bodies are maintained and tested, or
  whether the rollback story is forward-only with a restore-from-backup path —
  and if forward-only, that new revisions stop writing downgrade bodies nobody
  will run.
- **Why not now:** it turns on the rollback procedure of the topology of record,
  which ADR-0022 has only just named. 33 revisions are forward-tested from empty
  on every PR and there is no evidence any `downgrade()` has ever run (R-14). The
  decision is cheap to record and expensive to record *wrongly*: committing to
  supported downgrade means testing upgrade→downgrade→upgrade for every revision
  under ADR-0009's one-transaction-per-revision rule.
- **Evidence still needed:** the appliance's actual rollback procedure written
  down (ADR-0022 names redeploying previous image tags; what that implies for a
  schema already migrated forward is the open part); one attempt at running the
  existing downgrades against a seeded database, to learn whether they work at
  all.
- **Owner:** engineering, with the program owner on the acceptable
  recovery-time story.
- **Related:** R-14, OQ-S2-004, ADR-0009, ADR-0022.

### B-03 — Structured logging shape and correlation-id propagation

- **Candidate title:** One structured log line per request, with a correlation id
- **Would decide:** the field set of a request log line, where the correlation id
  originates and how it crosses the API→outbox→worker boundary, and what an
  `ApiError` logs exactly once.
- **Why not now:** the shape should be decided from a working implementation
  rather than ahead of one. M4 lands the middleware beside `MaxBodySizeMiddleware`
  and the once-per-`ApiError` rule; the ADR is worth writing when the field set
  has survived a week of use and the correlation id has actually been carried
  through a job. Deciding a schema first would freeze guesses about which fields
  matter, in a system with 20 logging references across 70k lines (R-03) and so
  no experience to draw on.
- **Evidence still needed:** M4 merged; one real diagnosis performed using the
  new lines; confirmation of whether the id survives the outbox hop or has to be
  stored on the job row to do so.
- **Owner:** engineering.
- **Related:** R-03, AP-09, migration increment M4.

### B-04 — Splitting `schema.py` along declared ownership

- **Candidate title:** `schema.py` is split along the ownership map
- **Would decide:** whether the 44 tables move into per-context modules, and if
  so how the drift test, the parity test and the 26 importing repositories are
  carried across.
- **Why not now:** ADR-0019 is Proposed, not accepted, and the ownership map does
  not exist. Splitting before it does is the anti-goal
  `OPUS_AUDIT_HANDOFF.md` §7 names explicitly. The split is also *optional* even
  after the map lands — it is the consequence, not the goal.
- **Evidence still needed:** ADR-0019 accepted and the map green in CI; evidence
  that the merge-conflict cost R-20 predicts is actually being paid, which is a
  measurement nobody has taken.
- **Owner:** engineering.
- **Related:** R-20, ADR-0004, ADR-0019.

### B-05 — Disposition of the seven legacy portal pages

- **Candidate title:** The legacy portal pages are ported, deleted, or corrected
- **Would decide:** for each of the seven routed pages backed by 24 endpoints no
  service serves, whether it is ported to `/v1`, deleted, or left with a retirement
  notice — and in the third case, a notice whose stated reason is true.
  `Calendar.tsx`'s current notice is honest in form and factually wrong in
  content (R-17).
- **Why not now:** each page is a product question about whether the capability is
  wanted, not a technical one. Deleting a page users reach is a product decision;
  porting one is a commitment to build 24 endpoints.
- **Evidence still needed:** the owner's per-page answer; whether the pilot VM is
  live with real users, which changes what "leave it" costs.
- **Owner:** product owner.
- **Related:** R-17, OQ-S2-002, OQ-S2-001, migration increment M8.

### B-06 — Live route matrix, and what `scoring_mode` records

- **Candidate title:** Travel-time proximity changes the measurement, not the
  fidelity
- **Would decide:** whether the live Routes adapter is built, and — before it is —
  that the run-level record of *which measurement produced a score* is the
  existing `scoring_mode` column (migration `0032`) rather than a new one.
- **Why not now:** the first half is a product need nobody has asserted. The
  architectural point is already sharp and is the reason this is a backlog entry
  rather than nothing: today's proximity is great-circle distance from ZCTA
  centroids, and travel time is a **different measurement, not a coarser one**
  (`wip-analysis.md` §1.2). Every `match_run` snapshot computed before the
  adapter lands is incomparable with one computed after, which collides with
  ADR-0011's accountability rules and with ADR-0016's pinned scoring modes.
- **Evidence still needed:** a product statement that travel time is required;
  a decision on whether pre- and post-adapter runs are ever compared, and if so
  how the pin is surfaced to a reader of a run.
- **Owner:** product owner (need), engineering (the pin).
- **Related:** OQ-S2-006, `wip-analysis.md` §1.2, ADR-0011, ADR-0016.

### B-07 — A1b convergence at `get_current_principal`

- **Candidate title:** Two authentication mechanisms, one principal-resolution
  seam
- **Would decide:** that pilot password login and institutional SSO converge at
  `dependencies.get_current_principal` / `_subject_for_token` — resolve a
  subject, then load the principal server-side, with no branch that skips the
  server-side load — so that A1b is a swap rather than a rewrite, and neither
  mechanism can become a third path.
- **Why not now:** the property appears to hold already (`dependencies.py:86,119`,
  per `wip-analysis.md` §1.4), and an ADR asserting a property that has not been
  verified against a second real issuer would be recording a hope. The
  configuration it depends on — issuer URL, audience, claim mapping, tenant
  mapping — is marked OUTSTANDING — EXTERNAL DEPENDENCY throughout.
- **Evidence still needed:** verification that no branch skips the server-side
  load, ideally as a test; the institution's issuer configuration.
- **Owner:** institution (configuration), engineering (the seam).
- **Related:** `wip-analysis.md` §1.4, `docs/plans/open-questions/a1b-live-idp-deferred.md`,
  non-negotiable 4 (identity is never caller-supplied).

### B-08 — A status vocabulary for `docs/plans`

- **Candidate title:** Every plan document declares its status
- **Would decide:** the closed vocabulary — `ACTIVE` / `LANDED` /
  `SUPERSEDED BY …` / `ABANDONED` — where the header goes, whether non-active
  documents move to `docs/plans/archive/`, and what a test asserts.
- **Why not now:** the vocabulary is cheap; assigning a status to 40+ existing
  documents is not, and it cannot be done from the repository alone. The visible
  git history begins 2026-09-05 while plans date from 2026-08-28, so history
  cannot resolve which landed (R-16), and OQ-S2-005 asks why. Recording the
  vocabulary before knowing whether pre-history is recoverable risks archiving
  documents that are still current.
- **Evidence still needed:** OQ-S2-005's answer on the history rewrite; a pass
  over the corpus by someone who was present for it.
- **Owner:** engineering, with the program owner on what happened to the history.
- **Related:** R-16, AP-13, OQ-S2-005, migration increment M5.

### B-09 — Agent-memory Slice 1

- **Candidate title:** (unwritten) Agent-memory Slice 1
- **Would decide:** whatever
  `docs/superpowers/plans/2026-08-24-agent-memory-slice-0.md` and its design spec
  propose, subject to ADR-0003 — no agent orchestration, adapter, or tool layer
  in Foundation. That constraint is what has kept it unwritten, not neglect.
- **Why not now:** no file, no author, and a standing decision it must argue
  against rather than assume.
- **Evidence still needed:** the slice's design settled; an argument that meets
  ADR-0003 on its own terms.
- **Owner:** engineering.
- **Related:** ADR-0003; the displaced reservation, below.

---

## Inherited disagreements

Two places where Stage 2 found the tree disagreeing with Stage 1. Both are
recorded rather than quietly corrected, because the *shape* of each disagreement
is itself a finding.

**The U1 count.** Stage 1 reported "three registered handlers, eight submitting
routers" (`wip-analysis.md` §2, R-04). Verified in tree on 8 September 2026: four
routers submit, three command types reach the worker over HTTP, and every one has
an executor — two of them composed at the root in `worker/main.py` rather than in
`default_registry()`. The eight counted docstring mentions and idempotency-only
reservations. **The risk does not go away with the count.** It sharpens: the map
is complete and nothing asserts it, and two of the five handlers are invisible to
a reader of `default_registry()`. ADR-0023 records that form.

**The stale reservation.** `README.md`'s "Reserved numbers" section said ADR-0016
was reserved for agent-memory Slice 1 and had no file, while
`ADR-0016-cba-scoring-policy.md` had existed since 5 September 2026. The section
is corrected in this Stage 2 change. The correction is not bookkeeping: it is the
third time the same reservation has been displaced, for the same reason each time
— a reservation with no file cannot hold a number, because
`test_adr_numbers_are_contiguous_from_one` refuses a gap. It now has no number at
all, which is the honest state, and B-09 above is where it lives instead.

**A third, smaller one.** `data-architecture.md` §8 and `domain-model.md` §6 both
say `routers/match_runs.py` writes match-run rows directly, giving `match_run`
two writers. In tree, `routers/match_runs.py:22-27` says nothing there inserts a
`match_run` row and nothing there could — the table's `job_id` is a `NOT NULL`
foreign key to `job` — and the router's only repository call is a read
(`match_runs.py:1175`). The single writer is `handle_match_run_create`. ADR-0019
resolves the ownership explicitly rather than leaving two documents wrong, and
notes that what settled the question was a docstring, in a repository where three
docstrings have been found false.
