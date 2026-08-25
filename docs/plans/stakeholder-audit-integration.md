# Stakeholder test-log audit: integration plan

An audit of Dr. Ann Wang's 19–20 August test log against this repository already
exists as a plan. Its classification of the findings is sound and is carried
forward here unchanged. Its account of *this repository* is not: it was written
against a tree four commits older than the current one, in a clone whose branch
does not exist here, and it collides with two controls that landed in those four
commits.

This document is that plan, corrected against the tree it will actually be
executed on, so the next agent writes the nine artifacts instead of
re-discovering why the first attempt fails at commit 2.

**Base:** `claude/f11-transaction-per-migration` @ `b8142fc`.
**Branch:** `claude/stakeholder-audit-integration`.
**Scope of this document:** it plans; it writes nothing else. No ADR, no
manifest entry, no backlog row, no scanner change, no code.

---

## 1. What this is, and where its evidence lives

The audit answers one question: **for each thing the stakeholder found, does the
new architecture close it — and where it does not, what closes it?**

Its result, unchanged:

| Status | Count | Meaning |
|---|---|---|
| COVERED | 1 | Structurally closed, with tests (Fix #7, mock-login) |
| PARTIAL | 6 | The principle exists; the specific failure would recur |
| ABSENT | 8 | No contract, no backlog item, no archive decision — silence |
| MOOT | 1 | The surface it describes no longer exists |

The revamp is strong on everything the *security* audit found — auth, tenancy,
durability, fabrication, ICS — and the f11 work makes it stronger. It is silent
on most of what the *stakeholder* found, because her findings are about product
truthfulness (do two pages agree, does a number have a definition, is a reward
reachable) and those were never written down as contracts.

### 1.1 Three source documents live outside this repository

None of the audit's primary evidence is tracked here:

| Source | Where it is | How to pin it |
|---|---|---|
| The test log — 37 rows, 16 fix items, 15 kickoff questions | Not in this repository | Date + author: 19–20 August 2026, Dr. Ann Wang |
| The architecture diagram set (diagram 3 names classroom reset; diagram 22 names the missing governance files) | Not in this repository | Diagram number, as the audit cites them |
| Architecture v1.1 | Not in this repository | Section number |

**This is the house style, not a defect.** Architecture v1.1 is cited by section
number in `README.md`, `apps/web/DESIGN.md`, every ADR, and every manifest entry
(`contract_refs: ["v1.1 §3.1", …]`), and its text has never been vendored. The
audit may cite the test log the same way.

What it must do — and what the existing documents do — is **pin the version**.
`docs/migration/migration-manifest.yaml` records `legacy_sha`,
`legacy_sha_verified`, and the command used to verify it. The audit document
should open with the same three facts for the test log: author, date, and the
legacy commit walked (`bdce024`, verified below).

Whether the test log should instead be vendored into the repository, redacted,
is an open question in §9 — it names real people, which is the subject of the
severity-1 finding itself.

---

## 2. Corrections to the plan as written, each verified

Every claim below was reproduced against the tree. The command is given so the
next agent can re-run it rather than trust this document — which is the standard
`docs/plans/transaction-boundary-defects.md` sets and the reason F9/MM-004 was
caught.

### 2.1 The branch table is stale, and the branch it names does not exist

The plan's table lists four `claude/*` branches and puts its own work on
`claude/nebiux-snapshot-audit-vzoy9f` at `aa568b4`, describing it as
"already-pushed" and therefore needing no force.

**That branch exists nowhere** — not locally in either clone, not on origin.
Origin carries exactly three:

```
$ git branch -a
  claude/f11-transaction-per-migration
  claude/smart-match-v1-migration-sp1t49
  claude/wave-c-orchestration-review-1y8pph
  remotes/origin/HEAD -> origin/claude/smart-match-v1-migration-sp1t49
  remotes/origin/claude/f11-transaction-per-migration
  remotes/origin/claude/smart-match-v1-migration-sp1t49
  remotes/origin/claude/wave-c-orchestration-review-1y8pph
```

The plan was written in a third working environment whose branch was never
pushed. Nothing is lost by this, but the "no force-push needed" reasoning does
not apply, because there is no remote branch to fast-forward.

### 2.2 f11 has advanced four commits, and is now a superset of wave-c as well

The plan describes f11 as fifteen commits ahead of `origin/HEAD`. It is now
nineteen. The four it has not seen:

```
b8142fc  J14: a replay reports the generation its own key created
a61540e  0004: three columns for J14, J17 and J9
d64390f  F10: exercise the CHECK constraints instead of naming them
0c7daa8  F8: index the ADRs, and check the index against them
```

`0c7daa8` is the one that matters — see §2.3.

f11 is also now a strict superset of the *other* live branch:

```
$ git merge-base claude/f11-transaction-per-migration claude/wave-c-orchestration-review-1y8pph
4e3543034d422178a6ff666266650f6e9e9bb2e3   # = wave-c's tip
$ git log --oneline claude/f11-transaction-per-migration..claude/wave-c-orchestration-review-1y8pph
                                            # empty
```

So basing on f11 loses nothing from either line of work. The plan's judgement
was right; it is now more strongly right than when it was made.

### 2.3 ADR-0010 is reserved, and a test enforces contiguity

The plan takes ADR numbers **0010–0014**, reasoning that 0008 and 0009 are the
highest taken. Two things landed in `0c7daa8` that break this.

**First, 0010 is reserved.** `docs/architecture/decisions/README.md:52-56`:

> ## Reserved numbers
>
> **ADR-0010 is reserved** for agent-memory Slice 1
> (`docs/superpowers/plans/2026-08-24-agent-memory-slice-0.md` and the design spec
> beside it). It has no file yet. Do not take that number for anything else.

**Second, the obvious workaround also fails.** Shifting to 0011–0015 leaves a
gap at 0010, and `tests/unit/test_adr_index.py:432` refuses it:

```python
def test_adr_numbers_are_contiguous_from_one() -> None:
    """A gap means an ADR was deleted, which is not how ADRs are retired.

    A decision that stops being true gets a superseding ADR and keeps its file.
    A missing number is therefore a mistake — either a deletion, or a reserved
    number that grew a file somewhere other than this directory.
    """
```

The docstring anticipates this exact case.

**Resolution, decided:** take **0010–0014** for the stakeholder ADRs and rewrite
the *Reserved numbers* section to reserve **0015** for agent-memory Slice 1.
Slice 1 has no file, so nothing is displaced, and contiguity holds.

**Third, and unmentioned by the plan at all: every new ADR needs an index row.**
`tests/unit/test_adr_index.py` compares the table against the directory in both
directions and checks each row's link target, title, bare status, and date
against the ADR's own header block; requires statuses from a closed vocabulary
(`Accepted`, `Proposed`, `Rejected`, `Superseded`, `Deprecated`); requires rows
in number order; and requires both supersession cells to be `—` or a
well-formed comma-separated list. Five ADRs means five rows, each with eight
cells. The plan budgets no work for this.

The `Decides` column is prose and is **not** checked — the README says so, and
records that its first draft stated the opposite of what ADR-0005 decides.
Write those five cells carefully; nothing else will.

### 2.4 The agent-memory ledger has no candidate state

The plan proposes three records under `docs/agent-memory/approved/` and says
they "land as candidates for the maintainer to approve in the merge."

There is no candidate state to land in. `tools/agent_memory_check.py:59`:

```python
STATUSES = frozenset({"approved", "superseded", "revoked", "stale"})
```

`LEDGER_DIR` (line 390) is `docs/agent-memory/approved` and is the only
directory the validator reads; there is no `candidates/` directory in the tree.
`docs/agent-memory/README.md:38` states the rule directly: *"`approved`,
`superseded`, `revoked`, or `stale`. Candidates never live here."*

A record in `approved/` must therefore say `status: approved` and carry a
`reviewed_by` — records `0001`–`0003` all carry the maintainer's address. The
ledger's other rule, *"No agent may approve any candidate — not merely its
own,"* means an agent cannot supply that field on its own initiative.

**Resolution, decided:** the three claims are **stated in §9 of this document
and not written as records this pass.** They ship only after the maintainer
approves each claim explicitly. The plan's own reasoning for excluding the
severity-1 PII finding from the ledger — pointer-rule violation, since its
sources are legacy-repo paths — is correct and stands.

### 2.5 The severity-1 exposure is six paths, not four

Verified against the local legacy clone at `bdce024` (`Update vercel.json`),
which is the commit `migration-manifest.yaml` pins as `legacy_sha`:

| Tracked path | Contents (verified by header + row count, contents not reproduced) |
|---|---|
| `Category 3 - IA West Smart Match CRM/data/data_speaker_profiles.csv` | 18 data rows. Header: `Name,Board Role,Metro Region,Company,Title,Expertise Tags` |
| `…/data/data_cpp_events_contacts.csv` | 15 data rows, including `Point(s) of Contact (published)` and `Contact Email / Phone (published)` |
| `…/data/poc_contacts.json` | Named individuals with real `@cpp.edu` addresses, org, role, **and a dated `comm_history` array** |
| `…/data/pipeline_sample_data.csv` | 58 data rows pairing `speaker_name` with `match_score`, `rank`, `stage` |
| `archived/Categories list/Category 3 IA West Smart Watch/data_speaker_profiles.csv` | **byte-identical duplicate** (`cmp` reports no difference) |
| `archived/Categories list/Category 3 IA West Smart Watch/data_cpp_events_contacts.csv` | duplicate |

Two corrections to the plan's description:

- **Six paths, not four.** A remediation that removes four leaves two intact.
- **`poc_contacts.json` is a communications log**, not a contact list. It
  records who was contacted, when, by what channel, and what was said. That is a
  materially different disclosure from a name and a title, and the manifest
  entry should say which of the six carries which kind of data rather than
  grouping them as "contacts".

`MM-A04` (manifest line 266) is confirmed to cover only
`data/{demo.db,smartmatch.db}` and `data/feedback/feedback-log.jsonl`. None of
the six appears anywhere in the manifest.

### 2.6 The legacy engagement facts check out verbatim

`Category 3 - IA West Smart Match CRM/frontend/src/lib/studentPoints.ts`:

```ts
/** Total redeemable balance: streak bonus + attendance bonus (demo formula). */
export function getStudentTotalPoints(profile: …): number {
  return profile.attendance_streak * 100 + profile.events_attended * 25;
}
```

The formula is exactly as the plan states, it is computed in the browser, and
**the source itself calls it a demo formula** — worth quoting in ADR-0013,
because it means the legacy authors did not believe it was a balance either.

The catalog's cost field is `pointsCost` (not `points`), on
`StudentRewardItem`, across four categories: `linkedin`, `platforms`, `certs`,
`growth`. Re-read the actual values before quoting the 5,000–45,000 range.

### 2.7 The README numbers in the plan are not in the README

The plan says it will edit "the current text, not the `aa568b4` text I first
read", citing moved counts: *authz 32, schema-drift 115, rate limiter 18+4*.
None of those strings appears in `README.md` on f11. Its only aggregate test
claim is line 49:

> **489 tests total** (488 pass, 1 skipped by design — see …)

The section the plan amends — `### Proposed, scaffolded, or deliberately absent`
— is at line 53 and is a three-column table (`Capability | State | Gated on`).
Re-read it before editing. This is precisely the failure mode the plan invokes
against F9/MM-004, reproduced inside the plan itself.

### 2.8 The scanner allowlist has eleven entries, not nine

`tools/scan_forbidden.py:200`, `ALLOWLIST: dict[tuple[str, str], str]`, eleven
entries — the tenth and eleventh being `apps/web/DESIGN.md` and
`ADR-0008-globally-unique-external-subject.md`, both for `mock-login`.

The three rule codes the audit will need to name are confirmed to exist:
`mock-login`, `demo-mode-fallback`, `fabricated-score`. The full code set is
`client-supplied-identity`, `demo-mode-fallback`, `fabricated-meeting`,
`fabricated-score`, `hard-coded-credential`, `legacy-import`,
`local-business-persistence`, `mock-login`, `module-level-mutable-state`,
`mutating-get`, `provider-call-in-request-path`, `unconditional-success`.

The plan's characterization of the edit is right: a `(path, rule_code) → reason`
map, data only, no rule or logic change.

### 2.9 What the plan got right, confirmed

- **The stakeholder-term grep still returns zero** on the current f11 tip:
  `reward`, `funnel`, `Ann Wang`, `disclosure`, `gamif`, `drill`, `ZoneInfo`,
  `America/`, `studentPoints`, `test log` — no hits, case-insensitive, whole
  tree. Not one of the 16 fix items is touched by the four new commits either.
  **The audit's classification stands unchanged.**
- **No `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`, or `CODEOWNERS`** at the
  repository root. The five `LICENSE` hits are `legacy_license:` fields in the
  manifest. F13 is real.
- **Manifest IDs `MM-A09`, `MM-F03`, `MM-F04` are free.** Taken: `MM-001`–`005`,
  `MM-A01`–`A08`, `MM-F01`, `MM-F02`.
- **`apps/web/DESIGN.md` carries D-1 through D-8**, with D-4, D-6 and D-7 open
  as the plan describes.
- **`make memory` exists** and is part of `make check`
  (`check: format-check lint typecheck imports test scan memory`).

---

## 3. The controls this work runs into

Six, in the order they will be met.

### 3.1 The ADR index and its test

`tests/unit/test_adr_index.py` runs in the no-database lane, so it fails on
`make test` and in CI, not only on `make check`. Adding an ADR file without its
row, or a row without its file, is an error; so is a gap in the numbering, a
status outside the vocabulary, a row out of number order, a date that disagrees
with the ADR header, or an `Amended` cell whose leading date token differs from
the status line's.

The index table is read only from between `## The index` and the next level-1 or
level-2 heading, with fenced code blocks resolved first. An ADR's header block
is read from above its first level-2 heading.

### 3.2 The agent-memory ledger

Covered in §2.4. Additionally, for whenever the three records are written:

- `sources` are `path@blob_sha`, repository-relative, at least one, no absolute
  paths, no `..`, no URLs. The blob SHA must resolve **at HEAD**, so the records
  must be committed *after* the files they cite — the plan's ordering of the
  memory commit last is correct and load-bearing.
- `content_hash` is `sha256:` over the stripped body; the validator names the
  value it expected.
- `project_id: smartmatch` and `repository_id: f943437b-6a8f-47fe-9c0d-478988b70d9a`
  must match `.agent-memory.yaml`.
- `authority` is `observation`, `convention`, or `external-research` — **never
  `decision`**. The instruction-shape check applies to the `claim` field as well
  as the body.
- Ledger numbers `0001`–`0003` are taken.

### 3.3 Identifier namespaces already in use

Verified by extracting every ID cell from the tables.

| Namespace | Taken | Free for this work |
|---|---|---|
| Decisions outside engineering | D1–D5 | **D6–D9** |
| Foundation | F1, F2a, F2b, F3–F12 | **F13** |
| Command-path defects | J1–J17 | — (do not extend; f11 owns this namespace) |
| Audit | A1a, A1b, A1c, A2–A5 | — |
| Frontend | D-0, W1–W7, D-1…D-8 | — |
| Manifest | MM-001–005, MM-A01–A08, MM-F01–F02 | **MM-A09, MM-F03, MM-F04** |
| Ledger | 0001–0003 | 0004–0006 (deferred, §9) |
| ADR | 0001–0009, 0010 reserved | **0010–0014**, reservation moves to 0015 |

The plan's proposal of an **S-namespace** for stakeholder-derived backlog items
is good and should be kept: it does not collide, and it makes provenance
self-evident in a table where every other prefix means a phase.

### 3.4 The scanner

`make scan` walks the tree for twelve forbidden patterns. Any document that
*names* `mock-login`, `demo_mode`, or a fabricated-score pattern in order to
discuss it needs an `ALLOWLIST` entry keyed on `(path, rule_code)`. The audit
document and any ADR quoting a legacy defect will need them.

### 3.5 The other clone has CRLF drift — do not work there

`/mnt/e/Programming/Github Repo/IA-Smart-Match-Revamped` sits on
`claude/wave-c-orchestration-review-1y8pph` with 128 files reported modified.
The diff is entirely line endings:

```
$ git diff -- .nvmrc | cat -A
-22$
+22^M$
$ git diff --stat | tail -1
 127 files changed, 30991 insertions(+), 30991 deletions(-)
```

A commit made from that clone rewrites every line ending in the repository and
buries the actual change. Work in
`/mnt/e/Programming/Github Repo/IA-SmartMatch-F11`, which is on f11 with a clean
tree. Repairing the first clone is separate work and is not part of this.

### 3.6 The gates cannot all be run here

There is no `make`, no system PostgreSQL, and no `sudo` in this environment.
`make check` cannot be invoked as written. §7 gives what to run instead, and
what must be reported as un-run rather than assumed green.

### 3.7 Touching the scanner invalidates a ledger record — verified the hard way

**This was found by executing §5.12 of this plan rather than by reading it, and
it breaks the plan's commit sequence.**

Agent-memory record `0003-forbidden-scan-covers-every-file-type.md` cites
`tools/scan_forbidden.py@23e540da…`. The validator recomputes that blob SHA and
reports the record when its source has uncommitted changes or has moved. So the
moment the allowlist gains an entry:

```
$ .venv/bin/python tools/agent_memory_check.py
Agent-memory ledger problems found (1):
  docs/agent-memory/approved/0003-forbidden-scan-covers-every-file-type.md  [dirty-source]
    -> source 'tools/scan_forbidden.py' has uncommitted changes; the claim
       cannot be verified by anyone else
```

and `tests/unit/test_agent_memory_check.py::test_the_real_ledger_validates_clean`
fails with it. Committing does not clear it — the blob SHA has moved, which the
validator reports too.

**Consequences for the plan as written.** It describes the scanner edit as
"data only; no rule or logic changes" and schedules it in commit 4, then drops
the memory commit entirely (§2.4). Commit 4 therefore leaves `make check` red
and `make test` red, and nothing later in the sequence turns them green.

**The remedy, which the ledger prescribes.** `docs/agent-memory/README.md`:
*"re-verify the claim and update the record, or mark it superseded. Do not
update the SHA alone."* So after any scanner edit:

1. Re-read record `0003` and decide whether its claim still holds. A data-only
   allowlist addition does not touch `applies_to` or the credential rule, so it
   does. An edit that added an `applies_to` tuple, or excluded a prefix, would
   not — and would need the record superseded rather than re-pointed.
2. Update `sources` to the new `git rev-parse HEAD:tools/scan_forbidden.py`,
   **after** the scanner change is committed.
3. Leave `content_hash` alone if the body is unchanged; the body is the claim's
   reasoning, not its pointer.

This is *not* an agent approving a record. It is the documented remedy for a
staleness report on an already-approved one. It is still a write to the approved
ledger, so say so in the commit message rather than letting it ride along.

**Add a seventh commit to §4** for exactly this, after the scanner change lands.

---

## 4. The commits, corrected

The plan's sequence is sound. Five changes, marked **[CHANGED]**.

| # | Commit | Contents | Change |
|---|---|---|---|
| 1 | `docs: audit the stakeholder test log against the revamped architecture` | `docs/architecture/review/stakeholder-test-log-audit.md` | — |
| 2 | `docs: record the invariants the stakeholder findings imply` | ADR-0010, 0011, 0012 + **three index rows** + **reservation moved to 0015** | **[CHANGED]** |
| 3 | `docs: design the engagement surface the revamp had left unclassified` | ADR-0013, ADR-0014 + **two index rows**, `docs/architecture/engagement-model.md` | **[CHANGED]** |
| 4 | `docs: track the real-identity exposure and three unclassified surfaces` | Manifest MM-A09 (**six paths**), MM-F03, MM-F04, MM-002 and MM-A08 amendments; scanner allowlist | **[CHANGED]** |
| 5 | `docs: carry the stakeholder findings into the backlog and design brief` | Backlog D6–D9, F13, S1–S12; `apps/web/DESIGN.md`; `README.md` | — |
| ~~6~~ | ~~`docs(agent-memory): propose three records`~~ | — | **[CHANGED — dropped.** See §2.4 and §9.] |
| 6 | `docs(agent-memory): re-point record 0003 at the scanner it now describes` | Record `0003` `sources` SHA, after commit 4 | **[CHANGED — new.** Forced by §3.7; without it commits 4 onward leave the tree red.] |

The reservation edit belongs in **commit 2**, not a separate one: between taking
ADR-0010 and moving the reservation, the tree states two different things about
the same number, and a commit should not be the boundary of that.

Per `docs/plans/orchestrator-handoff.md`: one coherent stage per commit, a
message explaining *why*, and `code-review` at high effort on the staged diff
before each — with findings verified against the tree rather than applied on
trust.

---

## 5. The nine artifacts

For each: where it goes, what it says, and **what must be re-read before it is
written**. The last column exists because two of the plan's file claims did not
survive checking (§2.7, §2.8), and the audit's whole value is that its citations
hold.

### 5.1 `docs/architecture/review/stakeholder-test-log-audit.md` — new

The meeting document, in the register style of
`docs/architecture/review/contract-findings.md`. Opens with the three pinning
facts from §1.1: author, dates, and `legacy_sha bdce024`.

Three tables:

- **Fix List traceability** — all 16 rows: item, severity, status
  (COVERED / PARTIAL / ABSENT / MOOT), the artifact that closes it *or* the new
  ID that will, and a file-path citation.
- **Test Log traceability** — the 18 ISSUE and 1 BLOCKED rows, collapsing rows
  that map to a single fix item.
- **Kickoff questions** — which of the 15 the architecture already answers
  (Q1 factors → F-001 plus the MM-002 mapping; Q4 dates/times → ADR-0010;
  Q13 scope → the engagement design), and which still need the student team.

Every COVERED claim cites a path. Every ABSENT claim names the ID that will
track it. Needs `ALLOWLIST` entries — it will name `mock-login` to record Fix #7
as closed.

**Re-read first:** `contract-findings.md` for register style and finding-ID
convention (`F-001`, `S-003`); `README.md:53` for the exact capability names.

### 5.2 ADR-0010 — Event temporal model: instant + IANA zone + precision

Closes Fix #4 (no resolved dates) and Fix #6 (the 3 AM / 7 AM display bug).

An event stores a UTC instant, its IANA zone, **and** a precision enum
(`exact` / `date_only` / `unresolved`). An event at `unresolved` cannot reach a
matchable or publishable state. Display renders in the event's own zone with the
zone named.

This puts the 3 AM bug in the model, where a test can see it, rather than in a
render layer that does not exist yet. It extends the discipline already in
`python/smartmatch_domain/smartmatch_domain/ics.py`, whose `generate_ics`
requires a resolved timezone-aware datetime and raises `UnschedulableEventError`
otherwise — see MM-001's `behavior_rejected`, which records the legacy's
"30 days from now" fabrication as a v1.1 §3.6 N1 violation.

**Re-read first:** `ics.py` and MM-001. The ADR should cite the existing rule
and generalize it, not restate it as new.

### 5.3 ADR-0011 — Accountable numbers

Closes Fix #5, #8, #12. Three rules, one idea:

1. **Definition.** Every user-visible aggregate has one canonical name and a
   one-sentence definition in a register. A metric with no definition does not
   ship.
2. **One owning query.** Two views cannot disagree, because only one query
   computes the value.
3. **Drill-down.** Clicking an aggregate returns exactly the rows it was
   computed from — the invariant that catches `15 vs 31`.

And the fourth, which is really the first: **a value with no evidence is
`unknown`, never `0`.** This generalizes to a platform rule what
`python/smartmatch_domain/smartmatch_domain/feedback.py` already does in one
module, where `acceptance_rate` returns `None` rather than `0.0` for an empty
set.

Names the casualties from the test log: Pain Score, pipeline footprint, contract
active, Fatigue-vs-Load, "Topic Relevance 0%" on an AI event, "Match Depth 0",
"Rest recommended: 0" beside a flagged volunteer.

**Re-read first:** `feedback.py` and `tests/unit/test_feedback.py`, to quote the
existing behaviour exactly; `DESIGN.md §1.1` (provenance) and `§1.2` (truthful
failure states), which are adjacent but not the same rule — provenance says
where a value came from, this says what it means.

### 5.4 ADR-0012 — Event identity and the controlled tag vocabulary

Closes the remainder of Fix #4: duplicates, leaked source-page names in titles,
open-ended tags.

A deterministic entity-resolution key for events — host unit + normalized title
+ resolved date window — and a closed 10–12 term role/type vocabulary that
extraction maps into. Unmapped values are quarantined, never rendered.
Source-page provenance is a field, not part of the title.

**Re-read first:** MM-A08, whose R3 crawler entry this constrains.

### 5.5 ADR-0013 — Attendance-derived engagement: points ledger and rewards

Closes Fix #9 and #15.

A server-authoritative, append-only ledger derived from attendance. Balance is a
fold over entries, never a client formula — quote `studentPoints.ts` and its own
`(demo formula)` comment (§2.6) as the thing being replaced. Redemption is a
command with an approval step. A catalog item with a real fulfilment cost cannot
be listed without a named budget owner and a funded balance: the structural form
of the stakeholder's "name an owner or don't ship rewards."

**Re-read first:** the legacy `studentPoints.ts` and `studentRewardsCatalog.ts`
for exact values; `db/migrations/versions/0001_foundation_baseline.py` for the
composite-key convention.

### 5.6 ADR-0014 — Disclosure consent, distinct from contact consent

Closes Fix #11, and records a stakeholder decision that currently has no record
anywhere: cut in-app chat; keep "people you met at this event"; make the button
an opt-in LinkedIn URL; route deeper access through a coordinator-mediated
mentor request; gate attendance visibility on consent.

Disclosure consent is its own record — subject, audience scope, purpose,
granted/revoked — with its own lifecycle. Attendance is visible to a peer only
under an active disclosure consent.

**Re-read first:** `python/smartmatch_domain/smartmatch_domain/consent.py`. It
models **contact** consent. The ADR must say precisely how the two differ rather
than implying the existing type can be widened.

### 5.7 `docs/architecture/engagement-model.md` — new

The full design, since this surface is being designed in rather than archived.

- **ERD additions** — `attendance_record`; `point_ledger_entry` (append-only,
  `tenant_id`, source, reason, actor); `reward_item` (`fulfilment_cost`,
  `budget_owner_id`, `funded`); `redemption`
  (`requested → approved → fulfilled | denied | expired`); `disclosure_consent`.
  Composite `(tenant_id, id)` keys per ADR-0004, as proven in
  `0001_foundation_baseline.py` and now enforced by the widened F7 drift test.
- **Derivation rule** — points are a function of recorded attendance and nothing
  else. A reversal is a compensating entry, never a delete, so the evidence
  plane stays append-only.
- **Economy calibration** — the stakeholder's ask as a testable property: *the
  cheapest reward is reachable within N events*, N a program-owner parameter
  (proposed default 3). Show the arithmetic against the legacy numbers — 100 per
  event against a 2,500 item is 25 events; against the real catalog's 5,000, it
  is 50. Free-to-give items sort first by construction, not editorially.
- **The motivating view** — "400 pts — 2,100 more for a mentor session" is
  specified as progress-to-nearest-*reachable* reward, which is only non-vacuous
  if the calibration above holds.
- **Unified agenda view** — registered and open-to-register in one time-ordered
  agenda, explicitly not a month grid ("a mostly-empty month looks like a dead
  chapter"), region badges, event-local times per ADR-0010.
- **Explicitly not built** — in-app chat, with the decision, its owner, and its
  date.

**Re-read first:** `0001_foundation_baseline.py` for the key convention and the
`ltree` usage; the F7 drift test for what it will check about these tables.

### 5.8 `docs/migration/migration-manifest.yaml` — amend

Five changes, in the existing entry schema exactly (`id`, `legacy_path`,
`legacy_symbol`, `legacy_license`, `target_path`, `disposition`, `contract_refs`,
`behavior_retained`, `behavior_rejected`, `status`, and the rest as §10 of the
orchestrator contract requires).

- **MM-A09** (new, `archived`) — **the six paths from §2.5**, each with what it
  contains, distinguishing the communications log from the contact lists. Names
  the exposure; records that git history means taking the Vercel deployment down
  does not remove it; flags the interaction with kickoff Q11 (open-sourcing the
  repository); assigns an owner. **No writes to the legacy repository** — see
  §8.
- **MM-F03** (new, `inventoried`) — student pages, `studentPoints.ts`,
  `studentRewardsCatalog.ts` → `REPLACE`. A browser-computed balance is not a
  balance. `contract_refs` → ADR-0013.
- **MM-F04** (new, `archived`) — `StudentConnect.tsx` chat → `ARCHIVE`, retaining
  "people you met at this event" as a requirement under ADR-0014.
- **MM-002** amend — the mapping from the seven factors the stakeholder was
  shown to the nine proposed, naming what happens to `calendar_fit`
  (→ `availability`, Stage A) and to `historical_conversion` and
  `student_interest` (dropped — which needs an owner's decision, not silence).
  Her three symptoms — the exact 43% tie, Topic Relevance 0%, Match Depth 0 —
  become required golden cases for gate G1.
- **MM-A08** amend — carry ADR-0010 and ADR-0012 into the R3 crawler entry so
  the invariants are inherited rather than rediscovered.

**Re-read first:** MM-002 and MM-A08 in full; MM-A04 (line 266) to state
explicitly that MM-A09 covers what A04 does not. Parse the file afterwards (§7).

### 5.9 `docs/plans/remaining-foundation-r1-work.md` — amend

New rows in the existing tables, using the free IDs from §3.3.

- **Blocked outside engineering:** D6 rewards budget owner · D7 points-economy
  calibration (the N of §5.7) · D8 disclosure-consent policy and what the
  "FERPA-aware" claim actually asserts · D9 licensing (kickoff Q11, gated by
  MM-A09).
- **Foundation:** F13 governance files — `LICENSE`, `SECURITY.md`,
  `CONTRIBUTING.md`, `CODEOWNERS`. Architecture diagram 22 names their absence as
  a legacy deficiency and the revamp reproduces it (§2.9).
- **R1/R2, S-namespace:** S1 metric register + drill-down contract test ·
  S2 unknown ≠ zero in the render primitive · S3 event temporal model migration ·
  S4 entity-resolution key · S5 tag vocabulary + quarantine · S6–S10 engagement
  tables, ledger, catalog, redemption, disclosure consent · S11 performance
  budget and QR load test (50 concurrent scans, kickoff Q14) · S12 the funnel
  as a contract with one owning query.

The frontend section is **ON HOLD** behind D-0 (a `DESIGN.md` owner). S1 and S2
are render-layer items and inherit that hold; say so in their rows rather than
letting them read as available work.

**Re-read first:** the section boundaries — the file has *Blocked on decisions*,
*Foundation completion*, *R1 — Matching foundation*, *R1 — Frontend — ON HOLD*,
*Deferred beyond R1*, and *Suggested next three*. The last of these names J10,
J8, and D1; adding twelve S-items does not change that recommendation and should
not be written as if it does.

### 5.10 `apps/web/DESIGN.md` — amend

To **Part 1** (settled): event-local time with the zone named; unknown ≠ zero
enforced in the value primitive rather than by memory; a drill-down affordance on
every aggregate; action queue before statistics on the coordinator and admin
home, with named people rather than an average when n is small.

To **Part 2**: the decisions her findings raise.

And record that **D-7 is now partly settled** — QR check-in is phone-first, so
mobile is a primary target, not a responsive afterthought.

**Re-read first:** §1.1 through §1.7 and the D-1…D-8 table (lines 129–136). The
file already carries an `ALLOWLIST` entry for `mock-login`.

### 5.11 `README.md` — amend

Three edits. One row in the `### Proposed, scaffolded, or deliberately absent`
table (line 53) for the engagement surface, one for the funnel, and a correction
to the stale test count on line 49 (§7.3). The table is three columns:
`Capability | State | Gated on`. The README opens by disavowing inaccuracy by
omission, and omitting both is exactly that.

**Re-read first:** §2.7. Do not carry over the plan's remembered counts; they
are not in the file. Consider also whether the `## Documentation` table (line
171) should gain the newer plan documents — it currently lists neither
`defect-remediation.md`, `transaction-boundary-defects.md`,
`orchestrator-handoff.md`, nor the agent-memory directory. That is adjacent, and
is a judgement call rather than part of this scope.

### 5.12 `tools/scan_forbidden.py` — allowlist entries only

`ALLOWLIST` is a `(path, rule_code) → reason` map at line 200 with eleven
entries. Add one per new document that names a forbidden pattern, with a reason
in the established one-sentence form. **Data only. No rule and no logic change.**

---

## 6. Traceability skeleton

The table the audit document fills in. Statuses are carried forward from the
audit unchanged; the closing artifact column is what this plan adds.

**Fourteen of the sixteen fix items are described in the source plan. Items #2
and #14 are not.** They are left blank deliberately rather than guessed — read
them from the test log. A skeleton with two invented rows is worse than one with
two visible holes.

| Fix | Subject | Sev | Status | Closed by |
|---|---|---|---|---|
| #1 | Real identities tracked in the legacy git history | 1 | ABSENT | MM-A09 (six paths, §2.5) + D9 |
| #2 | *(not described in the source plan — read from the test log)* | — | — | — |
| #3 | The funnel — Matched → Contacted → Confirmed → Attended → Member Inquiry | — | ABSENT | S12 + ADR-0011 (one owning query) |
| #4 | Event data quality: no resolved dates, duplicates, open-ended tags | — | ABSENT | ADR-0010, ADR-0012, S3, S4, S5; MM-A08 amended |
| #5 | Two pages showing "opportunities" do not agree | — | ABSENT | ADR-0011 + S1 |
| #6 | Times display as 3 AM / 7 AM | — | PARTIAL | ADR-0010 |
| #7 | mock-login | — | **COVERED** | Archived; `test_api_health.py`, `test_command_path.py` assert 404 |
| #8 | "Unknown" and "zero" are the same value | — | ABSENT | ADR-0011 + S2 (held behind D-0) |
| #9 | Student points are a browser formula | — | ABSENT | ADR-0013, `engagement-model.md`, MM-F03, S6–S8 |
| #10 | Student calendar is a mostly-empty month grid | — | ABSENT | `engagement-model.md` — unified agenda view |
| #11 | In-app chat cut; peer visibility undecided | — | ABSENT | ADR-0014, MM-F04, S10, D8 |
| #12 | Clicking 15 returns 31 rows | — | ABSENT | ADR-0011 drill-down invariant + S1 |
| #13 | Dashboard redesign ordering | — | ABSENT | `apps/web/DESIGN.md` Part 1 + Part 2 |
| #14 | *(not described in the source plan — read from the test log)* | — | — | — |
| #15 | Rewards catalog is unreachable (5,000–45,000 points) | — | ABSENT | ADR-0013 economy calibration, D6, D7, S9 |
| #16 | Student Connect surface unclassified | — | ABSENT | MM-F03, MM-F04 |

From the test log only, with no fix-item number:

| Finding | Closed by |
|---|---|
| Past Events takes 5 s | S11 (performance budget) |
| QR under 50 concurrent scans (kickoff Q14) | S11 (load test) |
| No data-minimization statement for QR signup (Q31) | D8 |
| Nothing defines "FERPA-aware" (Q35) | D8 |
| No classroom reset tooling, though architecture diagram 3 names it | Backlog row; no ID assigned yet |
| No `LICENSE` / `SECURITY.md` / `CONTRIBUTING.md` / `CODEOWNERS` (diagram 22, Q11) | F13 |

---

## 7. Verification

`make` is not available in this environment, nor is a system PostgreSQL, nor
`sudo`. Run the underlying commands directly against the project virtualenv, or
in Docker. **Report anything that could not be run as un-run.** Do not report a
gate green because the change "does not touch typed code".

### 7.1 Unchanged-green gates

Nothing in this work touches typed code, so these should pass before and after
identically. Run them both times, and diff the output rather than eyeballing it.

```bash
.venv/bin/ruff format --check .
.venv/bin/ruff check .
.venv/bin/mypy python/ services/
PYTHONPATH="$DOMAIN_PATH" .venv/bin/lint-imports --config pyproject.toml
```

### 7.2 The ADR index test — the one that will actually fail first

```bash
.venv/bin/pytest tests/unit/test_adr_index.py -v
```

Run it after **every** ADR added, not once at the end. It checks membership both
ways, contiguity, number order, the status vocabulary, and each row's title,
status and date against the ADR's own header. Five ADRs added in two commits
means two opportunities to leave the tree red.

### 7.3 The full no-database lane

```bash
.venv/bin/pytest tests/ -m "not integration"
```

Measured baseline on `b8142fc`, immediately before this document was committed:

```
394 passed, 1 skipped, 344 deselected, 8 warnings in 22.20s
```

That is 739 collected. **`README.md:49` says "489 tests total (488 pass, 1
skipped by design)", which is stale** — add it to the README amendments in
§5.11, and use the measured numbers above rather than the README's. If the
count moves, say why.

### 7.4 The scanner, verified negatively

```bash
.venv/bin/python tools/scan_forbidden.py     # must pass
```

An allowlist entry nobody has watched fail is not verified. For **each** new
entry: remove it, confirm the scan fails and names the expected `(path,
rule_code)`, restore it, confirm the scan passes. Record the failure message in
the commit message or the verification note.

### 7.5 The manifest parses, and the new entries are complete

The manifest is not schema-validated by any test, so parse it explicitly:

```bash
.venv/bin/python -c "import yaml,sys; d=yaml.safe_load(open('docs/migration/migration-manifest.yaml')); print(len(d['entries']),'entries'); print([e['id'] for e in d['entries']])"
```

Then check by hand that MM-A09, MM-F03 and MM-F04 each carry every field §10 of
the orchestrator contract requires, comparing against a neighbouring entry of
the same disposition rather than against memory.

### 7.6 The memory gate

```bash
.venv/bin/python tools/agent_memory_check.py
```

No records are *added* by this work (§2.4), but one is **modified**: record
`0003` is re-pointed at the scanner after the allowlist entry lands (§3.7).
Run this immediately after the scanner commit — it will fail — and again after
the re-point, where it must report three records and pass. Also run
`tests/unit/test_agent_memory_check.py`, which asserts the same thing and fails
in the no-database lane.

### 7.7 Integration tests

```bash
.venv/bin/pytest tests/ -m integration    # requires PostgreSQL
```

There is no local PostgreSQL here. Bring one up in Docker if the daemon is
running; **otherwise say plainly that they were not run.** Reporting them green
without running them is the failure this repository has already been burned by.

### 7.8 Claim check

Every path, line reference, count, and quotation in the audit document re-read
against the f11 file immediately before commit.

The audit's entire value is that its citations hold. This repository has been
burned once by a document asserting a test that did not exist (F9 / MM-004), and
the source plan for this work reproduced the same failure twice — §2.7 and §2.8.
Assume it will happen a third time and check for it.

---

## 8. Assumptions

1. **The audit's classification is correct.** This document verified that the
   four new commits do not touch any of the 16 fix items, and that the
   stakeholder-term grep still returns zero. It did **not** re-derive the
   classification from the test log, which is not in this repository.
2. **`legacy_sha bdce024` is the commit the stakeholder walked.** The manifest
   pins it as `legacy_sha_verified: true`, and the local legacy clone is at that
   commit. If the Vercel deployment was built from a different commit, the PII
   finding still holds — those files are tracked at `bdce024` — but the screen
   behaviour in the test log may not correspond.
3. **f11 will not be rebased or force-pushed** while this work is in flight. It
   is `b8142fc` on origin's `claude/f11-transaction-per-migration`, and the plan
   bases on it without merging it anywhere.
4. **Basing on f11 is not endorsing it.** J15, J16 and J17 remain open defects
   filed by its own authors. None of them touch this work.
5. **No production code ships from this.** The engagement design lands as
   contracts, an ERD, and backlog rows; the tables ship in R2 alongside
   attendance, per the existing sequencing in `remaining-foundation-r1-work.md`.

---

## 9. Open questions

Every one of these needs a person, not an engineering decision. The
recommendation column is a recommendation; none of them is settled here.

| # | Question | Recommendation | Owner |
|---|---|---|---|
| Q1 | Remediation for the six legacy PII paths: history rewrite, or repository replacement? | Neither is an engineering task. Decide before answering kickoff Q11. | Named owner — currently unassigned |
| Q2 | May the repository be open-sourced (kickoff Q11)? | Blocked on Q1. | Program owner |
| Q3 | Rewards budget owner (D6) | A catalog item with a real fulfilment cost cannot be listed without one. | Program owner |
| Q4 | Points-economy calibration: the N in "cheapest reward reachable within N events" (D7) | Proposed default 3. Legacy arithmetic gives 25–50. | Program owner |
| Q5 | Disclosure-consent policy, and what "FERPA-aware" actually asserts (D8) | Must be written before S10 is built, not after. | Privacy / legal / records |
| Q6 | Do `historical_conversion` and `student_interest` return, or are they dropped? | Record the decision either way. Silence is the current state and is worse than either answer. | Program owner (gate G1) |
| Q7 | Should the test log be vendored into this repository, redacted? | It names real people, which is the subject of Fix #1. Default to external citation with the version pinned (§1.1). | Maintainer |
| Q8 | Do the three memory-ledger claims get approved? | See below. | Maintainer |

### Q8 — the three deferred ledger claims

Stated here so the maintainer can approve or reject each on its own. None is
written as a record (§2.4). All would be `authority: observation`,
`privacy_class: repo-public`, numbered `0004`–`0006`.

| # | Claim |
|---|---|
| 0004 | The stakeholder test log is the product-truthfulness counterpart to the security audit; the two find disjoint defect classes. |
| 0005 | The displayed seven-factor set does not map onto the proposed nine; three factors have no target and no decision. |
| 0006 | "Unknown" and "zero" are one value everywhere except `feedback.acceptance_rate`. |

The severity-1 PII finding is deliberately **not** among them. Its sources are
legacy-repository paths, and the pointer rule refuses anything outside this
repository — correctly, since that rule is what makes the ledger safe to keep
permanently. It lives in MM-A09 and the audit document instead.

---

## 10. Deliberately out of scope

- **No writes to the legacy repository.** The orchestrator contract forbids it
  without authorization, and the severity-1 remediation there is Q1 — a decision
  with a named owner, not an engineering task. It is documented here and
  assigned.
- **No production code.**
- **No decisions reserved to a gate owner.** Where a finding needs a number, this
  plan records the decision, a recommendation, and an owner. It does not pick.
- **No merge of f11 into anything.**
- **No repair of the CRLF drift** in the other clone (§3.5). Separate work.
