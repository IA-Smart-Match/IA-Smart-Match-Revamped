# Backlog status report — 2026-08-30

**Branch:** `friday-deliverable-828` at `4f27e22` (four commits ahead of
`fc40a06`: `8ac41da`, `5012981`, `9019ccf`, `4f27e22`).
**Author:** prepared by an agent; every figure below was re-run against the
working tree today, not copied from a prior document. Where a number could
not be independently confirmed, that is stated rather than assumed.
**This document decides nothing, signs nothing, and fills no owner field.**

---

## 0. What actually moved today — the honest summary

- **Two Stage 0 domain parsers landed**: `ical_parser.py` and
  `jsonld_parser.py` under `python/smartmatch_domain/smartmatch_domain/`, with
  97 unit tests (33 + 64) against synthetic fixtures in
  `tests/fixtures/event_sources/` (57 files). **Confirmed**: fixture-only —
  neither module is exported from `smartmatch_domain/__init__.py` (`__all__ =
  ["__version__"]`) or imported by anything outside their own test files. No
  transport, no route, no migration.
- **The crawler threat model advanced from revision 3 to revision 4**,
  answering an adversarial review that returned **DO NOT SIGN** on revision 3
  (three blocking findings: T-02's proxy escape hatch, C-6's tier-blind
  auto-update allowlist, C-1 vs. T-14's unresolved persistence tension). It
  remains, **confirmed by reading the file**, an **unsigned draft** — the
  signature block's reviewer name and date are blank, and
  `test_g3_threat_model_remains_unsigned_draft` still passes.
- **ADR-0015 Amendment A1 was drafted** (quota-counting vs. monetary-spend
  reservation semantics). Status is **PROPOSED**, the approver line is blank,
  and — correctly, per the constraints on this task — the ADR's own
  `**Status:**` line still reads a bare `Accepted`, unchanged, because
  `test_an_amended_adr_is_marked_amended_in_the_index` couples that line to
  the README's Amended column and ratification has not happened.
- **Two preparation packets were added**: the P9 Gate B contact-fields
  worksheet (every decision field blank) and a blocked-work register that
  inventories every blank owner field in the portfolio and orders the blocked
  plans by decision cost rather than plan number.
- **Pre-existing `make lint` / `make format-check` failures were cleared.**
  Confirmed by rebuilding `fc40a06` in a scratch worktree and re-running both
  checks there: both genuinely failed at `fc40a06` (`ruff format --check`: 2
  files would be reformatted; `ruff check`: 1 SIM300 finding), independent of
  the parser/docs work, and both are green at `HEAD`.

**What did not move:** no gate closed, nothing was signed, no owner field was
filled, and P1, P2, P5, P7, P8, P9 are blocked on exactly what they were
blocked on before today. P6 gained a signed G3 half (dated 2026-08-29, so
*not* today's work) but its R3 half is still an unsigned draft, now at
revision 4 instead of 3.

---

## 1. Verification — re-run today, not trusted from prior notes

| Check | Claimed | Measured | Verdict |
|---|---|---|---|
| `make test` | 1021 passed, 1 skipped, 494 deselected | **1021 passed, 1 skipped, 494 deselected, 8 warnings in 29.94s** | **Confirmed** |
| `make format-check` | exit 0 | `ruff format --check .` → "217 files already formatted", exit 0 | **Confirmed** |
| `make lint` | exit 0 | `ruff check .` → "All checks passed!", exit 0 | **Confirmed** |
| `make typecheck` | exit 0 | mypy: "Success: no issues found in 54 source files", exit 0 | **Confirmed** |
| `make imports` | exit 0 | import-linter: 4 contracts kept, 0 broken, exit 0 | **Confirmed** |
| `make scan` | exit 0 | forbidden-behavior scan clean, 453 files, exit 0 | **Confirmed** |
| `make memory` | exit 0 | agent-memory ledger clean, 3 records, exit 0 | **Confirmed** |
| `make licenses` | exit 0 | 43 allowed, 4 recorded exceptions, 0 undetermined, exit 0 | **Confirmed** |
| `make infra-check` | exit 0 | 4 environments, 40 identifiers, none shared, exit 0 | **Confirmed** |
| `fc40a06` baseline test count | **"941 passed"** (as given) | **924 passed, 1 skipped, 494 deselected** (925 collected under `-m "not integration"`; 1419 collected total, unfiltered) | **NOT CONFIRMED — the given baseline figure appears to be wrong.** See below. |
| `fc40a06` `make lint` / `make format-check` | already red, pre-existing | Reproduced independently: `ruff format --check` fails on 2 files, `ruff check` reports 1 SIM300 finding (both in test files fixed by `8ac41da`) | **Confirmed** |

### The one figure that did not check out

The task brief states the baseline at `fc40a06` was **941 passed**. Rebuilding
`fc40a06` in an isolated git worktree (`git worktree add … fc40a06 --detach`)
and running the exact `make test` command (`pytest tests/ -m "not
integration"`) against it gives **924 passed, 1 skipped**, not 941. This was
checked two independent ways:

1. Direct test run: dot-counting the progress output gives 924 `.` and 1 `s`
   (a pytest quirk in this environment silently drops the final summary line
   on this specific checkout — collection-only runs lose it too — so the
   count was taken from the progress characters and cross-checked against
   `--collect-only -q`'s per-file counts, which sum to the same 925).
2. Arithmetic cross-check: `fc40a06` collects **1419** tests total
   (unfiltered) versus **1516** at `HEAD` — a difference of exactly **97**,
   which is precisely the number of new iCal/JSON-LD tests added today. The
   deselected (`integration`-marked) count is 494 at both commits, unchanged.
   `924 passed at fc40a06` + `97 new tests, all passing` = **1021 passed at
   HEAD**, which matches the confirmed current number exactly. `941 + 97 =
   1038 ≠ 1021`, which does not reconcile.

Both paths agree on **924**, and 924 is the only figure consistent with
today's net change being exactly the 97 new parser tests. **Flag: the "941
passed" baseline given in this task's brief could not be reproduced and is
most likely incorrect; the reconciled, self-consistent baseline is 924 passed,
1 skipped, 494 deselected at `fc40a06`.**

---

## 2. The P1–P9 portfolio (`docs/plans/2026-08-28-plan-portfolio-index.md`)

Per-plan detail is drawn from the portfolio index, each plan file's own
stop-gate section, and `docs/plans/prep/blocked-work-register-830.md` (dated
today, prepared but not itself a decision). Nothing below fills a blank.

### P1 — metrics authorization (`2026-08-28-metrics-authz-plan.md`)
- **What:** apply a ratified metrics-authorization decision (aggregate vs.
  row-level read rules) to the API.
- **State:** blocked on a workshop. `docs/decisions/metrics-authorization-decision-draft.md`
  poses four questions and answers none.
- **Blocks:** who must act — product + security, together.
- **Today:** unchanged. Current behavior stays intentionally ungated and is
  pinned by `tests/authz/test_policy_matrix.py::INTENTIONALLY_UNGATED_OPERATIONS` —
  nothing is silently wrong.
- **Coupling:** if P9 Gate B collects any contact field, P1 gains a new
  dependent (minimum-disclosure roles for contact data). A "drop" outcome on
  Gate B keeps P1 uncoupled.

### P2 — institutional sign-in (`2026-08-28-a1b-institutional-sign-in-plan.md`)
- **What:** wire a real identity provider; card A0 (audit + worksheet) already
  landed (`30ad0d4`, prior to today).
- **State:** cards A1–A4 blocked, but not on a decision — `docs/decisions/a1b-idp-configuration-worksheet.md`
  has every field `_(blank)_` because **no IdP tenant exists yet**. This is
  infrastructure procurement, not a workshop question.
- **Who must act:** whoever can provision an identity provider.
- **Today:** unchanged.
- **Register's recommendation:** stop describing A1–A4 as workshop-blocked;
  re-file as procurement-blocked so it isn't repeatedly queued behind a
  meeting that can't resolve it.

### P3 — ADR-0011 zero-coercion cleanup (`2026-08-28-adr0011-zero-coercion-cleanup-plan.md`)
- **What:** replace `?? 0` / `|| 0` coercions in the legacy frontend with
  honest nullable numerics per ADR-0011.
- **State:** **appears complete.** All four cards landed prior to today:
  Z1 inventory (`58ef92f`), Z2 nullable-numeric type seam (`2672397`), Z3
  consumer-surface fixes (`3bb8d7f`), Z4 guard test (`04ae5df`). Gate was
  "none"; nothing outstanding found.
- **Today:** unchanged — this work predates the four commits in scope.

### P4 — performance & caching (`2026-08-28-performance-caching-plan.md`)
- **What:** Stage 0 (measure) + Stage 1 (frontend query cache, code
  splitting, HTTP revalidation, retire legacy crawler poll).
- **State:** **Stage 0 + Stage 1 appear complete**, all prior to today: M1
  baseline (`fb0ffa1`, `53b94dd`, `e6160ed`), lane F1 query cache
  (`5925da7`), F3 HTTP revalidation (`73b3d40`), F2 code-splitting
  (`87f668c`), F4 legacy-poll retirement (`b1204ed`). M1's own recorded
  decision was to **skip Stage 2/3** (PostgreSQL read models / Redis) as
  unnecessary against the measured numbers.
- **Today:** unchanged.

### P5 — G1 matching, M1–M10 (`2026-08-28-g1-matching-m1-m10-plan.md`)
- **What:** approve the factor registry and golden case set, then implement
  scoring.
- **State:** blocked on the longest pole in the portfolio. Scoring
  fails closed by design (`assert_registry_approved()`); the legacy engine's
  max attainable score is 0.90 (9 declared factors, 7 computed) and must not
  be ported or characterized.
- **Blocks:** a named **program owner** — currently unnamed
  (`g1-factor-registry-workshop-packet.md`: "Blocking owner: program owner
  (name TBD)"). The workshop packet itself is complete; naming the owner is a
  prerequisite to running the workshop, not an output of it.
- **Today:** unchanged.

### P6 — G3 events, S3–S5 (`2026-08-28-g3-events-s3-s5-plan.md`)
- **What:** constrained event discovery/crawl pipeline; gated on **both** a
  G3 decision artifact and a signed R3 threat model.
- **State — the half that moved today:**
  - **G3 decision: signed**, 2026-08-29 (the day before today's commits) by
    Danny Tran, Development Lead — `docs/decisions/g3-crawler-decision.md`,
    confirmed no required field blank. This closes only the G3 half of the
    gate.
  - **R3 threat model: still an unsigned draft**, now at revision 4 (up from
    3) after today's fixes to three blocking findings from an adversarial
    review. Confirmed by reading the signature block: reviewer name and date
    both blank; `test_g3_threat_model_remains_unsigned_draft` still passes.
    Outstanding pre-live blockers recorded in the draft itself: T-07 (tools/
    providers dimension unfilled), T-13 (egress enforcement point unnamed),
    T-14 (blocked on P9 Gate B), a new C-1-vs-T-14 tension (evidence-retention
    contract vs. no-raw-content-storage), a new T-19-vs-signed-G3 tension
    (single approver vs. required second approver — needs a G3 amendment),
    T-27/T-28/T-29 relabeled **CANNOT CLOSE** rather than signed as
    requirements they don't meet, plus an open **reviewer-authority question**
    (is the Development Lead the same role as "named security reviewer"?
    unresolved).
  - **Stage 0 parser work landed today** (see §0) — pure domain work that
    doesn't need G3, but the plan itself notes it should be "confirmed as
    in-scope with the P6 owner" first; no such confirmation record was found
    in this tree. Flagged, not resolved, in
    `docs/plans/prep/campus-event-discovery-capability.md` (updated today,
    see §4).
- **Who must act:** a named security reviewer for R3 (see blank-owner
  inventory, §5); the reviewer-authority question is a human fact, not
  something an agent can resolve.

### P7 — D6/D7 rewards (`2026-08-28-d6-rewards-s8-s9-plan.md`)
- **What:** ledger fold (S8 listing, S9 redemption) for attendance-derived
  points.
- **State:** blocked on a budget that does not exist. `docs/decisions/pilot-decisions.md`
  D6 states plainly no budget exists and no holder is named; the coordinator
  role is explicitly *not* a budget owner. `budget_owner_id NOT NULL` is
  already enforced (`test_reward_item_rejects_a_null_budget_owner`), so
  nothing can drift silently here.
- **Who must act:** whoever controls reward funding.
- **Today:** unchanged.

### P8 — opportunities metric, S12 (`2026-08-28-opportunities-s12-plan.md`)
- **What:** one canonical, registered "opportunities" metric replacing two
  disagreeing surfaces (a merged CSV+crawler page with fabricated
  dates/roles, and an unregistered dashboard prose figure).
- **State:** blocked — **no artifact exists under `docs/decisions/` at all**
  for the canonical definition (confirmed: `ls docs/decisions/` has no
  opportunities file). Likely inherits P6 (today's page is crawler-fed) and
  possibly P5 (if a score floor is adopted), per the plan's own stop-gate
  language — but that is evidence about the *current* page, not the *intended*
  definition, which doesn't exist in writing.
- **Who must act:** the product owner — role is referenced but not named
  anywhere in the repository.
- **Today:** unchanged.

### P9 — pilot columns (`2026-08-28-pilot-columns-plan.md`)
Two independent stop-gates; branches select separately.
- **Gate A (`board_role`):** blocked on Dr. Wang — two questions (intrinsic
  vs. relationship-scoped attribute; if relationship-scoped, multiplicity +
  effective dates). `columns.yaml` correctly documents the current state as a
  holding position. Unchanged today.
- **Gate B (contact fields — Public URL, Point(s) of Contact, Contact
  Email/Phone):** **the cheapest open gate in the portfolio.** A full
  worksheet was prepared today
  (`docs/decisions/p9-gate-b-contact-fields-worksheet.md`) with a
  recommendation per field (collect the URL; drop the other two for the
  pilot) — but every decision field, and the signature, is still `_(blank)_`.
  A "drop all three" outcome would need no privacy owner and would add no
  dependency on P1. The gate blocks because it's undecided, not because it's
  restrictive.
- **Today:** the worksheet is new; no decision was made on it.

---

## 3. Everything else under `docs/plans/` — enumerated

Reading each file's own status marker plus commit evidence, roughly in three
buckets.

### 3a. Historical planning documents — believed superseded/closed, not
re-verified card-by-card today (flagged where the file itself says so)

These predate the `friday-deliverable-828` merges visible in the git log
(`a1b-sign-in`, `perf-caching` branches, the P3 cleanup cards) and describe
branch states (`c4ae716`, `claude/pr1-blockers-todos-er5heu`, PR #1/#3/#7)
that are now history. They were **not** individually re-audited beyond what
each file states about itself; treat the summaries below as "what the
document says", not as independently re-verified today.

- **`critical-path-plans.md`** — master index of a now-historical
  `main`-vs-`pr1-blockers` split. Planning only; superseded by later merges.
- **`critical-path-authorization.md`** (CP-GRANT, CP-A5), **`critical-path-matching-gate.md`**
  (CP-G1, CP-MATCH), **`critical-path-port-rereview.md`** (CP-REREVIEW,
  CP-V11), **`critical-path-pr1-merge.md`** (CP-PR1) — planning-only
  documents for the PR1-blockers branch merge. CP-G1's blocker (a named
  program owner) is the same live blocker as P5's today.
- **`critical-path-legacy-pii.md`** (CP-PII) — **not closable from this
  repository.** Six paths of real people's data live in
  `BrooklynD23/Nebiux-Team-IA-West-SmartMatch`. **No owner**, per the file's
  own header. Not re-verified today (out of scope — it names a different
  repository).
- **`defect-remediation.md`** — F9 (29 port-verification findings), F7
  (landed in `f6980ef`, historical), F8 (ADR index), A5 (job owning unit).
- **`transaction-boundary-defects.md`** (J11, J12, F11) — the file states
  **all three are implemented** (`565898c`, `4e35430`, plus the migration
  transaction test/ADR-0009), preserved for its reasoning, not as open work.
- **`remaining-foundation-r1-work.md`** — dependency-ordered backlog (D1–D5
  blocked on outside decisions; D1/program-owner is the same blocker as P5).
- **`remaining-engineering-brief.md`** / **`remaining-engineering-implementation-plan.md`** —
  planning inputs dated 2026-08-28, referencing Wave 3C as complete
  (`4edcec2`) and sequencing the stakeholder Fix #7 frontend work (roles/
  sign-in). Superseded in sequence by the later A1b/P2 work.
- **`g1-g3-d6-remedy-plan.md`** — diagnosis that G1/G3/D6 closures are
  **intentional fail-closed behavior**, not product bugs; the G3 crawler
  pipeline in particular was, as of this plan, empty by design (no route, no
  client) — now partially superseded by the Stage 0 parser landing and the
  signed G3 decision, both after this plan was written.
- **`stakeholder-audit-integration.md`** — corrects an older audit-integration
  plan against a specific historical branch/commit (`claude/f11-transaction-per-migration`
  @ `b8142fc`); superseded by subsequent ADR work (ADR-0009 through 0014 are
  now committed).
- **`frontend-migration.md`** / **`frontend-broken-buttons.md`** — legacy
  frontend inventory (42 broken/lying controls cataloged); explicitly
  "planning only... blocked on `apps/web/DESIGN.md` (D-0)". A partial
  remediation landed today's-branch-adjacent (`169bf4b`, "remove seven
  frontend controls that faked success (B12,B13,B20,B21,B32,B33,B37)"),
  predating the four commits in scope. Remaining ~35 controls' status against
  this inventory was not re-audited in this pass.
- **`opportunities-metric-inventory.md`** — the evidentiary basis for P8's
  "current page is crawler-fed" note above; explicitly "no metric
  implementation", blocked-on-stakeholder.
- **`adr0011-frontend-coercion-inventory.md`** — the Z1 card's own inventory
  (7 violations found and fixed, ~14 measured-zero-ok, ~30 layout-ok, 8
  out-of-scope) — consistent with P3 being complete (§2).
- **`perf-baseline-828.md`** — an earlier baseline document for a different
  branch/commit (`plan/perf-caching` @ `2357251`) than the one folded into
  P4's M1 card; superseded by the M1 documents cited under P4.
- **`orchestrator-handoff.md`**, **`friday-deliverable-828-review.md`**,
  **`pr1-blockers-handoff.md`**, **`pr3-verification-evidence.md`** — session
  handoffs and PR-evidence snapshots for specific historical HEADs
  (`69611b2`, `17fb0d9`, `2e13032`, `afd80c8`). Point-in-time records, not
  live backlog items; not re-verified against current HEAD.

**None of the above was reported as newly changed by today's four commits**;
`git show --stat` for `8ac41da`/`5012981`/`9019ccf`/`4f27e22` touches none of
these files.

### 3b. G3/R3 preparation documents — new or advanced today

- **`docs/decisions/g3-crawler-decision.md`** — signed (2026-08-29, so the
  signature predates today; the file itself was only *committed* today per
  commit `9019ccf`, which the threat model's stabilization note required
  before any signature could reference fixed bytes).
- **`docs/security/crawler-threat-model-draft.md`** — revision 4 today;
  unsigned; **not edited by this agent** per the standing constraint (gate
  artifact under human review).
- **`docs/security/r3-technical-review-findings.md`** — the adversarial
  review behind revision 2/3; reviewer field unfilled (`_(unfilled — see
  §6)_`); committed today.
- **`docs/security/prompt-injection-assessment.md`** — T-11 in depth;
  committed today.
- **`docs/plans/prep/g3-allowlist-candidates.md`**,
  **`g3-eval-and-vocabulary-candidates.md`**, **`g3-limits-and-policy-options.md`** —
  research inputs to the G3 decision; committed today, superseded in part by
  the G3 decision's §2.2 "restructured 2026-08-29" source table (drawn from a
  second research pass, not solely from `g3-allowlist-candidates.md` §8).
- **`docs/plans/prep/campus-event-discovery-capability.md`** — the Stage 0
  discovery roadmap document; **updated by this agent today** (see §4) to
  record that the iCal/JSON-LD parsers now exist.
- **`docs/plans/prep/blocked-work-register-830.md`** — new today; the source
  for most of §2's blocking detail above.
- **`docs/decisions/p9-gate-b-contact-fields-worksheet.md`** — new today; see
  P9 Gate B above.
- **`docs/architecture/decisions/ADR-0015-charge-quota-before-refusal.md`**
  Amendment A1 — new today; **not edited by this agent** (gate artifact).

---

## 4. Documentation changes made in this pass (Task 1)

One edit, to close the one genuine staleness found:

- **`docs/plans/prep/campus-event-discovery-capability.md`**, Stage 0 bullet
  on "Deterministic parser work against committed fixtures" — added a
  **Status: landed 2026-08-30** note recording that the iCal and JSON-LD
  parsers now exist, are fixture-only, and that this document has no record
  of whether the P6-owner confirmation it calls for was obtained before the
  work started.

Everything else checked and found **not** stale:

- `docs/architecture/decisions/README.md` (the ADR index) — **left
  unchanged, correctly.** `tests/unit/test_adr_index.py` passes as-is; ADR-0015's
  Amended column correctly still reads `—` because Amendment A1 is PROPOSED
  and unratified, exactly per this task's instruction not to mark it amended.
- No `docs/CODEMAPS/` directory exists anywhere in this repository (checked);
  there is nothing there to go stale, and none was fabricated.
- No README or index enumerating domain modules, test suites, or fixture
  directories was found elsewhere in the tree
  (`python/smartmatch_domain/smartmatch_domain/__init__.py` is a docstring
  module, not an enumerating index; `tests/` has no README).
- `docs/plans/2026-08-28-g3-events-s3-s5-plan.md` (P6's own plan file) does
  not mention the parsers at all and needed no change.

---

## 5. The blank-owner inventory

Every unfilled owner/approver/reviewer/signature field found, and what each
blocks. **None of these was filled by this agent; all are reported as found.**

| # | Field | Location | Blocks |
|---|---|---|---|
| 1 | **R3 security reviewer** | `docs/security/crawler-threat-model-draft.md` signature block (name/date blank); `r3-technical-review-findings.md` header: `Reviewer: (unfilled — see §6)` | All of P6 past the R3 gate |
| 2 | **R3 reviewer *authority*** (is the Development Lead the same role as "named security reviewer"?) | Same, recorded as an open question, not a blank field | Same as #1 — an unresolved question, not merely a name to supply |
| 3 | **ADR-0015 Amendment A1 approver** | `ADR-0015-charge-quota-before-refusal.md` §Amendment A1: `**Approver of this amendment:** ______________________ (blank — deliberately)` | Ratification of Amendment A1; T-08's conservative-reclaim direction in the threat model depends on this amendment landing |
| 4 | **P9 Gate B decisions + signature** (three per-field collect/drop choices, plus §8 signature) | `docs/decisions/p9-gate-b-contact-fields-worksheet.md` §0.3, §0.4 | P9 Gate B branch selection; R3's T-14; MP-4's final scope; the Stage 0 §4 schema review |
| 5 | **Privacy owner of record** | `p9-gate-b-contact-fields-worksheet.md` §0.2 — **"no such role is named anywhere in this repository"** | P9 Gate B, R3's T-14, MP-4 |
| 6 | **Program owner (D1/G1)** | `docs/plans/workshops/g1-factor-registry-workshop-packet.md`: "Blocking owner: program owner (name TBD)" | All of P5; P8 if a score floor is adopted |
| 7 | **Rewards budget owner (D6)** | `docs/decisions/pilot-decisions.md` D6: "does **not** name a budget holder, and no budget exists" | P7 entirely; enforced in schema by `test_reward_item_rejects_a_null_budget_owner` |
| 8 | **Product owner (opportunities definition)** | P8 stop-gate; **no artifact exists under `docs/decisions/` at all** | P8 |
| 9 | **IdP configuration** (product/vendor, tenant, issuer URL, JWKS, algorithms, key-rotation policy — every field) | `docs/decisions/a1b-idp-configuration-worksheet.md`: "**Status:** UNFILLED — this is a blank worksheet" | P2 cards A1–A4 (this is procurement, not a name to fill) |
| 10 | **Interim project owner** | `docs/decisions/pilot-decisions.md`: "Interim owner: DangT … **This is a self-assignment**", unratified, pending IA West confirmation | Nothing directly; noted so it is not mistaken for institutional authority |
| 11 | **`DESIGN.md` owner (D-0)** | `docs/decisions/pilot-decisions.md` §197: "deferred, not decided" | `apps/web/DESIGN.md` / frontend-migration rebuild sequencing |
| 12 | **Legacy PII remediation owner** | `docs/plans/critical-path-legacy-pii.md`: "It currently has **no owner**" | CP-PII, in a different repository entirely |
| 13 | **T-07 allowed tools/providers** | `crawler-threat-model-draft.md` outstanding-dependencies list | T-07's own closure; T-23 (LLM-provider data disclosure) cites the same unfilled dimension |
| 14 | **T-13 egress enforcement point** | Same list — "enforcement point unnamed" | Live-fetch prerequisite (already gated regardless) |
| 15 | **T-19 second allowlist approver** | Same list — requires a **G3 amendment**, since signed G3 names exactly one approver who also proposes | T-19's closure |
| 16 | **T-23 LLM provider name / retention terms** | Same list — "provider unnamed" | T-23's closure |

**Register item 6 (allowlist entry approver, R3 findings §5)** is the one
blank that *was* resolved — by the signed G3 §10 row 1 (Danny Tran) on
2026-08-29 — and is recorded here only to note that `r3-technical-review-findings.md`
§5's text describing it as open is now stale prose inside an otherwise-frozen
review document; not edited, since that file is a dated review artifact, not
a live index.

---

## 6. Cheapest available unblocks, ordered by decision cost

Carried forward from `blocked-work-register-830.md` §3, which orders by
leverage rather than plan number — reproduced here because it directly
answers "what should happen next":

1. **P9 Gate B** (register item 4/§2 above). Three collect/drop choices plus
   a signature. The worksheet already states a recommendation for each field.
   A "drop all three" outcome needs no privacy owner and closes cleanly.
2. **Name the four missing owners** (register items 5, 6, 7, 8 above —
   privacy owner, program owner, rewards budget owner, opportunities product
   owner). Not a workshop — each is a sentence a human can write in one
   sitting; three other plans (P5, P7, P8, plus P9 Gate B) are waiting on a
   name rather than on a decision.
3. **P1 metrics authz.** Four bounded questions; the portfolio already flags
   it as high leverage per unit of decision spent.
4. **P5 G1 registry** — once item 2 names a program owner, the workshop
   packet is already complete and can run immediately.
5. **P9 Gate A, P8's definition, P7's D6/D7** as their respective owners
   become available.
6. **P2 A1–A4** — re-file as procurement-blocked rather than
   workshop-blocked; no workshop produces an IdP issuer URL.
7. **R3 reviewer-authority question** (register items 1–2) — a fact about the
   organization, not the repository; an agent cannot resolve it, but naming
   it explicitly (1a: the Development Lead *is* the reviewing authority, or
   1b: a separate reviewer is required) is itself cheap and would let R3
   proceed toward a real signing pass.

---

## 7. Stale, contradictory, or unverifiable items found across the plan set

- **The `fc40a06` baseline test count (941 passed) does not reproduce** — see
  §1. This is the highest-value correction in this report; every
  "net new passing tests today" claim should use 924 → 1021 (+97), not 941 →
  1021 (+80).
- **`docs/security/r3-technical-review-findings.md` §5** still describes the
  "allowlist entry approver" as an open blank; it has been resolved (signed
  G3 §10 row 1, 2026-08-29). Not edited here, since the findings document is
  a dated review record rather than a live status page, but a reader relying
  on it alone would be misled.
- **`docs/plans/g1-g3-d6-remedy-plan.md`** describes the G3 crawler pipeline
  as categorically empty (no route, no client, intentional capability
  absence). That is still true for routes/transport, but is now slightly
  behind the Stage 0 parser landing and the signed G3 decision — both postdate
  the remedy plan. Not contradictory, just incomplete as of today; flagged
  rather than edited, since the remedy plan is a diagnosis document, not a
  live tracker.
- **`docs/plans/frontend-broken-buttons.md`** catalogs 42 broken/lying
  controls; commit `169bf4b` (predating this task's four commits) removed
  seven of them (B12, B13, B20, B21, B32, B33, B37). The remaining count
  against that inventory was not re-audited in this pass and should not be
  assumed still accurate at "42".
- **Numbering collisions flagged by the documents themselves, not by this
  report:** `critical-path-plans.md` and `defect-remediation.md` both warn
  that unhyphenated backlog IDs (F7, F8, F9, A5) and hyphenated
  port-verification findings (F-7, F-8, F-9) refer to different things, and
  that stakeholder-audit "Q1" is not kickoff "Q1". Anyone continuing this
  backlog should keep reading those documents' own disambiguation notes
  rather than relying on ID alone.
- **Nothing in the four commits scoped for this report touches the
  `critical-path-*`, `remaining-*`, `transaction-boundary-defects.md`, or
  `pr*-*.md` files** — their status is exactly what those files themselves
  already say, none of it re-verified line-by-line here beyond what's noted
  in §3a.

---

## 8. What this report did not do

- Did not sign, approve, or fill any field, anywhere.
- Did not modify `docs/security/crawler-threat-model-draft.md` or
  `docs/architecture/decisions/ADR-0015-charge-quota-before-refusal.md`.
- Did not push, open a PR, merge, or deploy anything.
- Did not re-derive or second-guess the G3 decision's substance, or the
  threat model's revision-4 technical content — only its signature state was
  checked (unsigned, confirmed).
- Did not re-audit every historical `docs/plans/*.md` file card-by-card;
  §3a states plainly which files were read only at the level of their own
  stated status.
