# Stakeholder test-log audit — findings against the revamped architecture

**Test log audited:** Dr. Ann Wang, 19–20 August 2026
**Legacy baseline walked:** `bdce024de1a9bf488c6bd9a7c24a3c87e03ffa42` (the
`legacy_sha` pinned by `docs/migration/migration-manifest.yaml`, recorded there
as `legacy_sha_verified: true`)
**Repository audited:** `claude/f11-transaction-per-migration` @ `b8142fc`
**Status vocabulary:** `COVERED` · `PARTIAL` · `ABSENT` · `MOOT`

---

## Summary

The revamp is strong on everything the *security* review found — authentication,
tenancy, durability, fabrication, ICS correctness — and the f11 work makes it
stronger. It is close to silent on what this stakeholder found, because her
findings are about **product truthfulness**: do two pages agree, does a number
have a definition, is an advertised reward reachable. Those were never written
down as contracts, so nothing in the tree contradicts them and nothing enforces
them either.

| Status | Count | Meaning |
|---|---|---|
| COVERED | 1 | Structurally closed, with tests |
| PARTIAL | 6 | The principle exists; the specific failure would recur |
| ABSENT | 8 | No contract, no backlog item, no archive decision — silence |
| MOOT | 1 | The surface it describes no longer exists |

These totals are the audit's own, carried forward. **They are not reproduced by
the per-row status column below** — see [Reconciliation gap](#reconciliation-gap),
which is an open hole in this document, not a rounding difference.

A term search over the whole tree at `b8142fc` returns **zero** hits,
case-insensitively, for `reward`, `funnel`, `disclosure`, `gamif`, `drill`,
`ZoneInfo`, `America/`, `studentPoints`, `Ann Wang`, and `test log`. Nothing in
the repository speaks to these findings in either direction.

---

## Provenance, and what could not be verified here

This audit cites its primary source by version rather than vendoring it, which
is the house style: Architecture v1.1 is cited by section number in `README.md`,
`apps/web/DESIGN.md`, every ADR, and every manifest `contract_refs` list, and its
text has never been vendored either.

Three source documents live outside this repository:

| Source | Where it is | How it is pinned |
|---|---|---|
| The test log — 37 rows, 16 fix items, 15 kickoff questions | Not in this repository | Author + dates: Dr. Ann Wang, 19–20 August 2026 |
| The architecture diagram set (diagram 3 names classroom reset; diagram 22 names the missing governance files) | Not in this repository | Diagram number |
| Architecture v1.1 | Not in this repository | Section number |

**The test log is not in the legacy repository either.** This was checked rather
than assumed. The legacy tree at `bdce024` does carry
`Category 3 - IA West Smart Match CRM/docs/testing/test_log.md`, and it is **not**
this document: it is an unfilled Sprint-4 template — tester "Person B", dated
2026-03-20, every result cell empty, and a Bugs section reading "No bugs were
logged during the code-side Sprint 4 hardening verification pass." The adjacent
`bug_log.md` closes at B-010 with zero active bugs. Neither names this
stakeholder, neither carries an August date, and neither contains any of the 16
fix items.

**What follows from that.** Three things in this document could not be sourced
and are left visibly blank rather than inferred:

1. **Fix items #2 and #14.** Fourteen of the sixteen are described in the
   upstream analysis; these two are not. Two invented rows would be worse than
   two visible holes.
2. **The per-row statuses.** They are inferred from the upstream analysis's
   prose, not read from the log. See [Reconciliation gap](#reconciliation-gap).
3. **The 18 ISSUE and 1 BLOCKED test-log rows.** Only six log findings without a
   fix-item number are recoverable from the upstream analysis; the remainder
   cannot be transcribed without the log.

Whether the log should be vendored here, redacted, is an open question — it
names real people, which is the subject of the severity-1 finding itself. It is
tracked as Q7 in `docs/plans/stakeholder-audit-integration.md` §9.

---

## Fix List traceability

Sixteen items. **Closed by** names the artifact that closes the finding, or the
identifier that will.

| Fix | Subject | Sev | Status | Closed by |
|---|---|---|---|---|
| #1 | Real identities tracked in the legacy git history | 1 | ABSENT | MM-A09 (six paths) + D9; remediation is Q1 and **unassigned** |
| #2 | *(not recoverable — read from the test log)* | — | — | — |
| #3 | The funnel — Matched → Contacted → Confirmed → Attended → Member Inquiry | — | ABSENT | S12 + ADR-0011 (one owning query) |
| #4 | Event data quality: no resolved dates, duplicates, open-ended tags | — | ABSENT | ADR-0010, ADR-0012, S3, S4, S5; MM-A08 amended |
| #5 | Two pages showing "opportunities" do not agree | — | ABSENT | ADR-0011 + S1 |
| #6 | Times display as 3 AM / 7 AM | — | PARTIAL | ADR-0010 |
| #7 | Caller-selected identity at `POST /auth/mock-login` | — | **COVERED** | Archived as MM-A01; `tests/contract/test_api_health.py:52` and `tests/integration/test_command_path.py:520` each assert 404 |
| #8 | "Unknown" and "zero" are the same value | — | ABSENT | ADR-0011 + S2 (held behind D-0) |
| #9 | Student points are a browser formula | — | ABSENT | ADR-0013, `engagement-model.md`, MM-F03, S6–S8 |
| #10 | Student calendar is a mostly-empty month grid | — | ABSENT | `engagement-model.md` — unified agenda view |
| #11 | In-app chat cut; peer visibility undecided | — | ABSENT | ADR-0014, MM-F04, S10, D8 |
| #12 | Clicking 15 returns 31 rows | — | ABSENT | ADR-0011 drill-down invariant + S1 |
| #13 | Dashboard redesign ordering | — | ABSENT | `apps/web/DESIGN.md` Part 1 + Part 2 |
| #14 | *(not recoverable — read from the test log)* | — | — | — |
| #15 | Rewards catalog unreachable — 2,500–45,000 points against 25 per event | — | ABSENT | ADR-0013 economy calibration, D6, D7, S9 |
| #16 | Student Connect surface unclassified | — | ABSENT | MM-F03, MM-F04 |

### The one COVERED item, in full

Fix #7 is the only finding the revamp closes structurally, and it is closed
because the *security* review reached it first, not because this log did. The
legacy endpoint let a caller name their own role in the request body. It is
recorded as archived in the migration manifest (MM-A01), the forbidden-behavior
scanner carries a rule whose code is `mock-login` and whose pattern matches both
the route and the `role = request.json` shape, and two tests assert the route is
gone rather than merely unused:

- `tests/contract/test_api_health.py:52` — `test_mock_login_endpoint_does_not_exist`,
  against the unauthenticated app.
- `tests/integration/test_command_path.py:520` — `test_mock_login_does_not_exist`,
  against the authenticated app, so the route cannot return 404 for the wrong
  reason.

ADR-0008 also names the pattern, to argue why a tenant-scoped identity lookup
would revive it.

### Where a principle exists but the failure would recur

Three of the findings land near something the repository already does correctly,
which is why they are PARTIAL rather than ABSENT, and why the ADRs below
generalize existing behavior rather than inventing it:

| Finding | The behavior that already exists | Why it does not close the finding |
|---|---|---|
| #6 — times display in the wrong zone | `smartmatch_domain.ics.generate_ics` requires a resolved, timezone-aware datetime and raises `UnschedulableEventError` otherwise (`ics.py:60`, `:110`, `:115`); MM-001 records the legacy's "30 days from now" fabrication as a v1.1 §3.6 N1 violation | The rule lives in one exporter. Nothing carries a zone or a precision on the event itself, so any other render path can reproduce 3 AM |
| #8 — "unknown" and "zero" are one value | `FeedbackWindow.acceptance_rate` returns `None`, not `0.0`, for an empty set (`feedback.py:132`) | One module, one metric. It is a local habit, not a platform rule, and there is no render primitive to enforce it |
| #15 — an unreachable rewards catalog | — | Nothing in the tree models points, rewards, or attendance at all |

---

## Reconciliation gap

**This is a known hole in this document.** The headline totals in the Summary are
the audit's own count — 1 COVERED, 6 PARTIAL, 8 ABSENT, 1 MOOT. The status
column in the Fix List table above, whose values are inferred from the upstream
analysis's prose rather than read from the test log, comes out at:

| | COVERED | PARTIAL | ABSENT | MOOT | blank |
|---|---|---|---|---|---|
| Headline (audit's own) | 1 | 6 | 8 | 1 | 0 |
| Per-row (inferred here) | 1 | 1 | 12 | 0 | 2 |

Five PARTIAL rows and the single MOOT row are unaccounted for. **Inference from
a summary cannot recover which items had a principle already in place** — that
distinction is exactly what the PARTIAL status records, and it is exactly what a
summary drops.

Treat the headline totals as authoritative and the per-row column as a draft
until someone reconciles it **against the test log**. The log is not on disk in
either repository (see Provenance), so this cannot be closed from here.

---

## Test-log findings with no fix-item number

The log carries 18 ISSUE rows and 1 BLOCKED row. Six are recoverable without it;
the rest are not transcribed here rather than being guessed at.

| Finding | Closed by |
|---|---|
| Past Events takes 5 s | S11 — performance budget |
| QR check-in under 50 concurrent scans (kickoff Q14) | S11 — load test |
| No data-minimization statement for QR signup (Q31) | D8 |
| Nothing defines what "FERPA-aware" asserts (Q35) | D8 |
| No classroom-reset tooling, though architecture diagram 3 names it | Backlog row; no identifier assigned yet |
| No `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`, or `CODEOWNERS` (diagram 22, Q11) | F13 |

The last of these was verified directly: none of the four files exists at the
repository root at `b8142fc`. The only `LICENSE` matches in the tree are
`legacy_license:` fields in the migration manifest.

---

## Kickoff questions

Fifteen were asked. Five are answerable from the architecture as it stands or as
this audit extends it; the rest need the student team or a named owner, and are
not enumerated here because the list is not recoverable without the log.

| # | Question | Answered by |
|---|---|---|
| Q1 | Which factors does matching actually use? | Finding `F-001` in `contract-findings.md` — the registry declares nine and computes seven — plus the MM-002 amendment mapping the seven she was shown onto the nine proposed |
| Q4 | How are dates and times resolved and displayed? | ADR-0010 |
| Q11 | May the repository be open-sourced? | **Blocked on Q1 of the open questions** — the six legacy paths in MM-A09 are tracked in git history, so this cannot be answered before the remediation decision |
| Q13 | What is in scope for the student surface? | `docs/architecture/engagement-model.md` and ADR-0013 |
| Q14 | Does QR check-in hold up at event scale? | S11 — no answer today; the load test is the answer |

---

## What this audit does not do

- **It does not re-derive the classification from the log.** The log is not in
  either repository. What was verified here is that the four f11 commits since
  `aa568b4` touch none of the sixteen fix items, and that the term search still
  returns zero.
- **It does not write to the legacy repository.** The orchestrator contract
  forbids it without authorization. The severity-1 remediation is a decision
  that needs an owner, recorded as MM-A09 and as Q1.
- **It does not pick any number reserved to a gate owner** — the points-economy
  calibration, the rewards budget, and the disclosure-consent policy each carry a
  recommendation and an owner, and no decision.

## Where the work is tracked

| Kind | Where |
|---|---|
| Invariants the findings imply | ADR-0010 … ADR-0014 |
| The engagement surface, designed in | `docs/architecture/engagement-model.md` |
| Legacy dispositions | `docs/migration/migration-manifest.yaml` — MM-A09, MM-F03, MM-F04; MM-002 and MM-A08 amended |
| Backlog | `docs/plans/remaining-foundation-r1-work.md` — D6–D9, F13, S1–S12 |
| Decisions needing a person | `docs/plans/stakeholder-audit-integration.md` §9 |
