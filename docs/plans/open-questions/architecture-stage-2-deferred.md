# Architecture Stage 2 — open questions carried by the target-architecture plan

**Date:** 2026-09-08 · **Slice:** Stage 2 target architecture and the M0–M8
migration sequence · **Status:** ACTIVE

Every item here is a decision a human has to make that engineering could not
make for them. None of them stopped Stage 2: each carries a **safe default that
Stage 2 planned on**, and each default is chosen so that being wrong about it
degrades into *refusing, waiting, or not doing* rather than into *doing
something irreversible to a live system or a real person*.

That asymmetry is the whole policy, inherited from
`docs/plans/open-questions/r4-outreach-deferred.md` and
`docs/plans/open-questions/f5-deploy-deferred.md`: a deferral that fails toward
inaction costs an increment a week; a deferral that fails toward action costs a
deleted page, an unrecoverable row, or an outage on a pilot somebody is using.

Nothing here is a placeholder that *reports success*. Where a decision is
missing, the plan sequences around it and says which decision it is waiting on.

**Not an open question: U1.** Stage 1 left "which command types reach the worker,
and what executes them" UNKNOWN and reported "eight submitting routers, three
handlers". That was resolved in tree on 2026-09-08 — four routers submit, three
command types reach the worker, and every one has an executor, two of them
composed at the root in `services/worker/smartmatch_worker/main.py` rather than
in `default_registry()`. The resolution and the corrected table are recorded in
`docs/architecture/TARGET_ARCHITECTURE.md` under "Where Stage 2 disagrees with
Stage 1"; R-04 survives in a sharper form (the map is complete today, but nothing
asserts it, and the root-composed handlers are invisible to a reader of
`default_registry()`), which is what M1's registry-map test closes. It is a
finding, not a deferral, and it does not belong in this file.

---

## Summary

| OQ | Question | Blocks | Safe default assumed | Who decides |
|---|---|---|---|---|
| **OQ-S2-001** | Is the pilot VM live, with real users on it right now? | The sequencing of every phase; batching; M8 deletions | **Assume YES.** Every increment gets a rollback window; M3 migrates one page; M4 changes no response; M6 adds no migration | Program owner |
| **OQ-S2-002** | Disposition of the seven legacy portal pages — port, delete, or correct the notice? | M8 / Phase 6 (R-17) | **Assume none of the three.** Leave all seven exactly as they are; the M8 card is blocked, not defaulted | Program owner + the coordinator who uses them |
| **OQ-S2-003** | Retention period per append-only table | Any deletion job; the privacy statement; storage planning | **Assume indefinite.** Nothing is deleted; no retention job is written (R-13) | Program owner + whoever holds the data-protection obligation |
| **OQ-S2-004** | Is migration downgrade a supported operation? | The rollback story for every schema increment (R-14, U4) | **Assume NO.** Roll back by restore, not by downgrade; every increment is planned as forward-only-safe | Program owner + operations |
| **OQ-S2-005** | Why was git history rewritten on 2026-09-05, and is pre-history recoverable? | R-16 archiving; any claim about provenance before that date (U8) | **Assume pre-history is unavailable.** Treat 2026-09-05 as the evidentiary floor; cite nothing earlier | Program owner |
| **OQ-S2-006** | Does the product need travel-time proximity — a live route matrix? | The Google Routes adapter; `scoring_mode`; comparability of stored runs | **Assume NO.** Great-circle from ZCTA centroids stands; no adapter is written | Program owner, against customer §9 |

---

## OQ-S2-001 — Is the pilot VM live, with real users on it?

**Question.** Is the deployed appliance carrying real coordinators, students and
speakers doing real work right now — or is it an environment the team can take
down, migrate in one pass, and restore from a dump?

**Why engineering cannot answer it.** It is a fact about who is using the
software, not about the software. The repository contains the evidence that a
real login exists — `POST /v1/auth/login` against `pilot_credential`,
owner-authorized on 2026-09-04 (`services/api/smartmatch_api/main.py` module
docstring; `docs/decisions/pilot-login-decision-2026-09-04.md`) — and the seed
tooling that populates it (`tools/seed_pilot_logins.py`,
`tools/seed_pilot_principals.py`). It contains no evidence of *sessions*. Only
the program owner knows whether last week's demonstration became this week's
workflow.

**Safe default assumed: YES.** Stage 2 planned the entire M0–M8 sequence as if
people are on it. Concretely, that assumption is load-bearing in four places:

1. **Every increment gets a rollback window.** Each M-n is independently
   shippable *and* independently reversible, and reversibility is stated in the
   increment rather than assumed. This is why the sequence is eight increments
   and not three.
2. **M3 migrates exactly one page** to the generated client, as the pattern
   (T-2.x). A live pilot cannot absorb a simultaneous rewrite of 49 files of
   inline `fetch`; one page is a change a coordinator can survive and the team
   can revert in one commit.
3. **M4 logs but changes no response.** The request-logging middleware and the
   `ApiError` single-log rule (AP-09) add a log line and a correlation id and
   alter no status code, no body, and no header a client reads. Observability
   that changes behaviour is a behaviour change wearing a disguise.
4. **M6 adds no migration.** Declaring table ownership is data plus a test, and
   bringing indexes under parity is a declaration in `schema.py` matched against
   migrations that already ran. The `schema.py` split stays an *optional*
   follow-up after M6, never before — a live system is the worst possible place
   to discover that a module move changed an import order.

**What changes if the answer is NO.**

- **Phases 1–3 can batch.** M2, M3 and M4 stop needing separate rollback windows
  and can land as one boundaries-and-contract change. M3 in particular stops
  being "migrate one page as the pattern" (T-2.x) and becomes "migrate the client
  surface", because a broken page costs nobody anything.
- **M8's deletions proceed without a notice period.** The three dead components
  (R-06b) and any of the seven legacy pages OQ-S2-002 disposes of can be removed
  the moment the decision lands, rather than after a deprecation window.
- **M6 may take a migration**, and the `schema.py` split can be considered
  alongside it rather than strictly after.
- **ADR-0022** (the Compose appliance *is* the production topology) is unaffected
  in substance — the appliance is still the topology — but its Consequences
  section stops carrying "and it has users on it" as an operational constraint.

---

## OQ-S2-002 — Disposition of the seven legacy portal pages

**Question.** For each of the seven legacy portal pages (R-17): port it to the
current architecture, delete it, or leave it and correct the notice it shows?

**Why engineering cannot answer it.** Each page is a product decision about
whether a workflow still exists. Porting costs engineering time against a
contract that M3 has not finished generating; deleting removes a route a
coordinator may have bookmarked; leaving it means committing to a notice that is
honest about what the page no longer does. The repository can say what each page
*is* — it cannot say whether anyone still needs it.

**Safe default assumed: none of the three, deliberately.** Stage 2 leaves all
seven exactly as they are and blocks the M8 card on this question rather than
picking a default. This is the one place where a "safe default" would itself be
the risk: deleting is irreversible for a user, porting spends the budget of two
increments, and rewriting the notice is a product claim engineering is not
entitled to make. What Stage 2 *does* assume is that **doing nothing to them is
survivable** — the pages are not a security or correctness defect, they are a
coherence defect.

**What changes if the answer differs.**

- **M8 / Phase 6 unblocks per page**, not as a block: the increment is written as
  seven independent decisions precisely so a partial answer moves part of it.
- **Port** → the pages become M3 client consumers and the T-2.x pattern must land
  first; M3's scope grows and Phase 2 gets longer.
- **Delete** → routes disappear, which interacts with OQ-S2-001: with live users,
  each deletion needs a notice period and a redirect; without, it is one commit.
- **Correct the notice** → a copy change that must pass
  `tools/scan_cba_terminology.py`, since a legacy portal page is exactly the
  CBA-visible copy that scanner reads.
- **The deletion of the three dead components (R-06b) is not blocked on this** and
  proceeds in M8 regardless — they have no production caller at all (AP-08).

---

## OQ-S2-003 — Retention period per append-only table

**Question.** How long does each append-only table keep a row: `job_event`,
`delivery_event`, `contact_channel_transition`, `pilot_login_attempt`, and the
`match_run` snapshots?

**Why engineering cannot answer it.** Retention is a legal and institutional
obligation, not a storage preference. Two of these tables hold personal data
whose retention is somebody's compliance duty (`delivery_event` records that a
named person was contacted; `contact_channel_transition` records the consent
history that authorized it), one is a security record (`pilot_login_attempt`),
and two are the evidence that makes an outcome explainable after the fact
(`job_event`, `match_run`). Each has a different right answer and none of them is
engineering's to choose. Note the asymmetry: `match_run` snapshots are also the
*only* record of what a superseded rulebook produced — deleting them destroys the
ability to explain a past run at its own `REGISTRY_VERSION`
(`factor_registry.py:143,488`).

**Safe default assumed: indefinite retention.** Nothing is deleted; no retention
job exists; no `DELETE` runs on any of the five tables. That is the default that
fails toward *keeping evidence we may not need* rather than *destroying evidence
we cannot recreate*. It is not cost-free — it is a growing storage and a growing
privacy exposure, and it is recorded as such in R-13.

**What changes if the answer differs.**

- **M7 / Phase 6** is where the retention decision is *recorded* (the brief's
  "retention and downgrade decisions recorded"). A concrete period turns that from
  a recorded decision into a real increment: a deletion path, its authorization,
  and its own append-only record of what was deleted.
- **ADR-0014** (disclosure consent) gains a lifetime: a consent record's retention
  and the retention of the transitions that produced it must agree, or the
  consent history outlives the consent.
- **A deletion path is a new writer** on tables M6/ADR-0019 declares as
  single-writer — the ownership map must name it.
- If retention is short for `match_run` snapshots, **`scoring_mode` and the
  superseded-version constants lose their point**: nothing old survives to
  compare, and ADR-0016's "1.x runs readable but never compared across the bump"
  becomes moot rather than satisfied.

---

## OQ-S2-004 — Is migration downgrade a supported operation?

**Question.** When an increment is reverted, is `alembic downgrade` the mechanism
— or is the mechanism "restore from backup and replay"?

**Why engineering cannot answer it.** It is an operational commitment, not a code
property. Supporting downgrade means every migration author writes and *tests* a
reverse path, and the team accepts that a downgrade which drops a column destroys
the rows written since the upgrade. Not supporting it means the recovery story is
a restore, which needs a backup schedule, a tested restore, and an accepted
data-loss window. Both are defensible; only the owner can choose which cost the
programme pays. U4 records that the current downgrade paths are unproven — they
are written, not exercised.

**Safe default assumed: NO, downgrade is not supported.** Stage 2 plans every
schema increment as forward-only-safe: additive columns and tables, no drops in
the same increment as the code that stops using them, and reversibility achieved
by reverting *code* while the schema stays ahead. This is why M6 is written to add
no migration at all, and why §"never remove a compatibility path before proving it
unused" is a rule rather than a preference.

**What changes if the answer is YES.**

- **Every migration gains a tested downgrade**, and the CI step "Migrations apply
  from an empty database" gains a companion that applies and then reverses. That
  is a new gate — an addition, never a relaxation.
- **M6 and any table added under ADR-0019** must carry a reverse path, which
  changes the cost estimate for Phase 5.
- **ADR-0009** (one transaction per revision) becomes doubly load-bearing: a
  downgrade that half-applies is worse than an upgrade that half-applies, because
  it runs during an incident.
- The rollback window OQ-S2-001 assumes gets *shorter*, not longer — a downgrade
  is faster than a restore, so with live users this answer materially improves the
  sequencing.

---

## OQ-S2-005 — Why was git history rewritten on 2026-09-05, and is pre-history recoverable?

**Question.** What produced the history rewrite at 2026-09-05 (U8), was it
deliberate, and does a copy of the pre-rewrite history exist anywhere — a mirror,
a fork, a local clone, a backup?

**Why engineering cannot answer it.** The rewrite removed the evidence that would
answer it. Nothing in the working tree records the reason, and no examination of
the current repository can distinguish "history was rewritten to remove a
committed secret" from "history was rewritten to squash a noisy branch" — two
answers with opposite consequences. Only the person who ran it, or the
organization that holds the mirrors, can say.

**Safe default assumed: pre-history is unavailable, and 2026-09-05 is the
evidentiary floor.** Stage 2 cites nothing earlier as provenance. Where a
document needs a pre-2026-09-05 reference it uses the artifact in tree — a
decision record, an ADR, a plan — never a commit. R-16's archiving requirement is
scoped to what exists from the floor forward: `docs/plans` documents carry a
status header (AP-13) *because* their history cannot be relied upon to say whether
they are still live.

**What changes if the answer differs.**

- **If the rewrite removed a secret**, this stops being an archiving question and
  becomes an incident: the exposed credential must be rotated regardless of
  whether the history is recoverable, and every mirror must be purged. That work
  precedes Phase 0.
- **If pre-history is recoverable**, R-16's archiving increment (M5 / Phase 4) can
  reconstruct plan provenance from commits instead of from status headers — the
  status headers are still worth having, but they stop being the *only* source.
  Superseded plans could then be dated from their history rather than annotated by
  hand.
- **If the rewrite was routine and nothing is recoverable**, nothing changes; this
  entry stands as the record of why no Stage 2 document cites a commit older than
  the floor.

---

## OQ-S2-006 — Does the product need travel-time proximity?

**Question.** Does the product require a live route matrix — real travel times for
the `proximity` and `travel_burden` factors — or is straight-line distance from a
ZCTA centroid the measurement the product actually wants?

**Why engineering cannot answer it.** Because the two are not better and worse
versions of the same number; they are **different measurements**
(`docs/architecture/wip-analysis.md` §1.2). Great-circle distance from a ZCTA
centroid answers "how far apart are these places". A route matrix answers "how
long would this person be travelling", which depends on mode, time of day, and
traffic — and which will rank a speaker differently, not more accurately, for the
same pair of locations. Choosing between them is choosing what the product means
by proximity, which is a product decision. It also carries a cost and a vendor:
the live adapter is a paid, external dependency, and ADR-0016 already fixed
proximity as a **step function on raw miles** (Near `<25` → `1.00`, Mid `25–<75` →
`0.60`, Far `≥75` → `0.20`, lower-inclusive and upper-exclusive, with a missing
address as `unknown` rather than Far) — a banding that would have to be
re-derived in minutes rather than miles.

**Safe default assumed: NO.** Great-circle distance from ZCTA centroids stands.
`registry.py:196` records that the live Routes adapter is *not implemented*, and
Stage 2 writes no adapter, opens no vendor account, and adds no port for one
(§"never create generic abstractions for hypothetical needs"). What Stage 2 does
do is preserve the *ability* to answer differently later: `scoring_mode`
(migration `0032_match_run_scoring_mode.py`) is the existing column that records
which measurement produced a run, and ADR-0016's pinned-mode precedent
(`cba-physical-1` / `cba-virtual-1`) is the mechanism a new measurement would use.

**What changes if the answer is YES.**

- **M7 / Phase 6 gains a second adapter contract** beside ADR-0021's: a
  `RouteMatrixProvider` contract test against a recorded-response transport,
  written *before* the adapter, on the ADR-0021 pattern.
- **ADR-0016 is amended or superseded**, not quietly reinterpreted: its proximity
  bands are defined on raw miles and a travel-time measurement needs its own
  bands, its own `REGISTRY_VERSION` bump, and its own scoring mode. Every
  `match_run` computed before the bump becomes non-comparable to every run after —
  which is exactly the property `SUPERSEDED_REGISTRY_VERSION`
  (`factor_registry.py:143`) exists to keep honest.
- **A paid provider enters the request-adjacent path**, which means spend
  ceilings, reservations, and the `BudgetFailure` → `failed_budget` terminal state
  become live concerns for match runs and not only for paid extraction.
- **OQ-S2-003's `match_run` retention answer gets more expensive to get wrong**,
  because the snapshots become the only record of which measurement a past
  recommendation rested on.
