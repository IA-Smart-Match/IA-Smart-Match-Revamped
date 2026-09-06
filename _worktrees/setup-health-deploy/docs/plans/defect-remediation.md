# Defect remediation plan

Covers the defect backlog: **F9** (the 29 port-verification findings),
**F7** (schema drift coverage — **landed in `f6980ef`**, §6 now records what
shipped), **F8** (ADR index), and **A5** (job owning unit).
Written to be worked top to bottom; each item names what blocks it, who owns it,
and — for the three rejected manifest entries — exactly what must be true before
a re-review can reach `verified`.

Nothing here makes anything production-ready, and nothing here is deployed.

**Two numbering schemes collide and this document keeps them apart.** Backlog
items from `remaining-foundation-r1-work.md` are unhyphenated (**F7**, **F8**,
**F9**, **A5**). Findings from `docs/migration/port-verification.md` are
hyphenated (**F-7**, **F-8**, **F-9**). They are unrelated: backlog F7 is the
schema drift test; finding F-7 is a blackout counted as workload. The backlog's
own text still says "F-1..F-27"; the review ends at F-29.

---

## 1. Two kinds of defect, and why the distinction is the plan

The 29 findings are not one list. They are two lists that happen to have been
discovered by one exercise.

**Documentation defects.** The manifest — or an adjacent document — asserts
something that is not so. The software is unaffected: correcting F-18 changes no
byte of `feedback.py`'s behavior. What is affected is the manifest's only
function. A migration manifest is not a description; it is the evidence that a
port was deliberate, that what was dropped was dropped knowingly, and that a
claimed legacy defect was a real one. An entry with a false claim in it is not a
slightly inaccurate description — it is a piece of evidence that has been shown
to be unreliable, and one false claim per entry is enough to make the rest of
that entry unusable as evidence too, because nothing distinguishes the checked
claims from the unchecked ones. That is why three entries were rejected while the
reviewer said, four separate times, that the code is better than what it
replaces.

**Code defects.** The software does the wrong thing. These have a severity that
exists independently of any document, they need a test, they need a code review,
and they can regress.

They differ on every axis that matters for sequencing:

| | Documentation defects | Code defects |
|---|---|---|
| Owner | migration owner (a claim about history) | engineering (a change in behavior) |
| Fixed by | rewriting a claim to match what was found | changing behavior, with a test |
| Risk of the fix | the correction is itself wrong | regression |
| Blocks | re-review, and therefore the Foundation gate | a caller that does not exist yet |
| Verified by | someone re-deriving the claim from source | CI |
| Can regress | no | yes |

**And there is a seam between them that this plan exists to make visible.** Six
of the false claims are not confined to the manifest. They were copied into the
module docstrings of the code they describe:

| Finding | Also asserted at | Nature |
|---|---|---|
| F-4 | `smartmatch_domain/eli.py:10` | "recent assignment pressure, travel burden, and event cadence" |
| F-10 | `smartmatch_domain/eli.py:19` | "enforced … by `tests/unit/test_eli.py`" |
| F-12 | `smartmatch_domain/ingest.py:172` | "the legacy loader reported it as present and healthy" |
| F-18, F-19 | `smartmatch_domain/feedback.py:6` | "Retained: the decline-reason vocabulary, the reason-to-factor mapping" |
| F-21 | `smartmatch_domain/feedback.py:70` | "map free text to factors by substring matching" |
| F-22 | `smartmatch_domain/feedback.py:14` | "the demo-fixture fallback in `aggregate_feedback`" |

Four of the five verdict-deciding findings — F-4, F-18, F-19, F-21 — have a copy
inside the code. **A manifest correction that stops at the YAML file leaves the
falsehood shipped in the package.** That has three consequences the rest of this
plan depends on:

1. The documentation track is not owner-clean. It has a tail that lands in
   `python/smartmatch_domain/**` and therefore needs an engineering review, even
   though the decision behind each edit belongs to the migration owner.
2. The docstring edits and the code fixes touch the same three files, so they
   should be staged together per module rather than per track — otherwise two
   agents contend for `eli.py`.
3. A re-review that reads only the manifest will pass an entry whose module
   still says the false thing. The re-review scope has to include the docstrings.

---

## 2. Findings, classified

Severity below is **this plan's assessment**, argued in §4 where it differs from
the review's. Neither column is about production risk; nothing is in production.

### Documentation defects — owner: migration owner

| Finding | Sev | Entry | What is untrue | Also fix at |
|---|---|---|---|---|
| **F-4** | High | MM-003 | `behavior_retained` names an event-cadence input that does not exist | `eli.py:10` |
| **F-13** | High | MM-004 | `characterization_tests` names parity cases that do not exist | `docs/testing/scaffold-verification.md:74` |
| **F-18** | High | MM-005 | The decline vocabulary was replaced, not retained | `feedback.py:6` |
| **F-19** | High | MM-005 | The reason-to-factor mapping was replaced, not retained | `feedback.py:6` |
| **F-21** | High | MM-005 | The claimed substring-matching legacy defect does not reproduce | `rejected-components.md:54`, `feedback.py:70` |
| F-11 | Medium | MM-004 | Dropped legacy null-count, dtype and nullability checks, unrecorded | — |
| F-12 | Medium | MM-004 | Added-behavior claim overstates what changed | `ingest.py:172` |
| F-20 | Medium | MM-005 | `legacy_path`/`legacy_symbol` omit the files the constants actually came from | — |
| F-22 | Medium | MM-005 | Demo-fixture fallback attributed to the wrong function | `rejected-components.md:53`, `feedback.py:14` |
| F-3 | Low | MM-001 | "implicit clock reads" listed as removed; the default branch still reads the clock | — |
| F-5 | Low | MM-003 | 20 cases claimed, 18 exist | — |
| F-10 | Low | MM-003 | Module docstring claims an enforcement `test_eli.py` does not perform | `eli.py:19` |
| F-14 | Low | MM-004 | 14 cases claimed, 13 exist | — |
| F-28 | Low | all | `contract_refs` unverifiable — architecture v1.1 is not in the repository | see §5 |
| F-29 | Low | — | Stale: recorded 5 dispatcher failures that were an artifact of reading mid-edit | see §3.4 |

### Code defects — owner: engineering

| Finding | This plan | Review | Module | Defect |
|---|---|---|---|---|
| **F-15** | **High** | Medium | `ingest.py` | Column set read from `rows[0]`; a fail-closed gate fails open on row order |
| F-1 | Medium | Medium | `ics.py` | `METHOD:REQUEST` with no `ORGANIZER`/`ATTENDEE` (RFC 5546 §3.2.2) |
| F-6 | Medium | Medium | `eli.py` | Stage A hard cap decided by a 4-dp display rounding |
| F-7 | Medium | Medium | `eli.py` | `MANUAL_BLACKOUT` counted as measured workload |
| F-23 | Medium | Medium | `feedback.py` | Decision floor counts total decisions, not declines |
| **F-25** | **Medium** | Low | `feedback.py` | Per-factor bound with no aggregate bound and no renormalization |
| F-24 | Medium | Medium | tests | The only test of the shadow-mode control asserts a hard-coded `return True` |
| **F-8** | **Low** | Medium | `eli.py` | Score counts the raw sequence; the snapshot reports a `frozenset` |
| F-2 | Low | Low | tests | Golden test for defect 1 asserts a type rejection, not a parsing behavior |
| F-9 | Low | Low | `eli.py` | Future-dated engagements silently dropped despite "or committed" |
| F-16 | Low | Low | `ingest.py` | Literal `null`/`none`/`nan` treated as blank in every column |
| F-17 | Low | Low | `ingest.py` | Findings report normalized headers, not the coordinator's |
| F-26 | Low | Low | `feedback.py` | `match_run_id` accepts an empty string |
| F-27 | Low | Low | `feedback.py` | `WeightProposal` is not `@final` |

F-2 and F-24 are **evidence defects** rather than behavior defects — in both
cases the code is right and the proof is not. They live in the code track because
the fix is a test, but their urgency comes from the same place as the
documentation defects: they are the reason a claim cannot be trusted.

---

## 3. Track D — corrections

### 3.1 What each rejected entry needs before re-review

Worked in the order below, each entry is independently re-reviewable. Nothing in
this section depends on anything in §4 **except** the two rows marked, where the
review's verdict text names a code defect as part of its reasoning and a
corrected description alone will not answer it.

**MM-003 → `verified`**

| # | Condition | Kind |
|---|---|---|
| 1 | `behavior_retained` no longer claims event cadence. State what was retained: recency-weighted assignment pressure and travel burden, combined into a bounded score. | doc |
| 2 | Time-based recency decay is recorded as **introduced**, not retained. The legacy's `recency_pressure` was `min(stage_order/4, 1.0)` and was not a function of time. Needs the manifest-schema change in §3.3. | doc |
| 3 | `eli.py:10` docstring updated to match. | doc-in-code |
| 4 | `target_tests` count corrected to 18, or counts removed (§3.3). | doc |
| 5 | `eli.py:19` no longer claims `tests/unit/test_eli.py` enforces the prohibited-input list. Either state what does enforce it (the closed `LoadInputs` structure) or add the assertion the docstring promises. | doc-in-code |
| 6 | **F-6 fixed.** The verdict names "a defect in the arithmetic of a hard eligibility control". Rewriting the entry does not answer it. | code |
| 7 | F-7, F-8 fixed; F-9 decided (§4.4). | code |

**MM-004 → `verified`**

| # | Condition | Kind |
|---|---|---|
| 1 | **`characterization_tests` tells the truth.** Two honest routes, and the choice is the migration owner's: (a) write real characterization cases, or (b) set the field to `n/a` with the reason. Route (a) is cheaper than it looks — the review already re-executed the legacy `_validate_columns` null logic under pandas 3.0.5 and published the transcript under F-12. Those three observed outcomes (empty fields → issue; whitespace-only → healthy; literal `nan` → issue) are exactly what a characterization case encodes. | doc + tests |
| 2 | `docs/testing/scaffold-verification.md:74` corrected. It asserts the same false thing; correcting one and not the other leaves the repository self-contradictory. | doc |
| 3 | `behavior_rejected` records the dropped per-column null counts, dtype validation and nullability checks (F-11), **and** states whether dropping dtype validation was intended — the target performs no type checking on imported cells at all. | doc + decision |
| 4 | Added-behavior claim rewritten to what actually changed (F-12): the legacy already flagged empty and `nan` values; the port escalates that to blocking and additionally catches whitespace-only. | doc |
| 5 | `ingest.py:172` comment updated to match. | doc-in-code |
| 6 | Count corrected to 13, or removed. | doc |
| 7 | **F-15 fixed** — see §4.1. It is the highest-severity code defect in the set and it is a regression against the legacy in an `ADAPT` entry, which is the specific thing this manifest exists to catch. | code |
| 8 | F-16, F-17 decided. | code + decision |

**MM-005 → `verified`**

| # | Condition | Kind |
|---|---|---|
| 1 | `behavior_retained` records the vocabulary and the mapping as **replaced** (F-18, F-19), with the justification recorded: the legacy held *two* mappings that disagree with each other on `Speaker already committed`, so there was no single legacy mapping to carry forward. That fact is the strongest argument for the redesign and it is currently nowhere in the manifest. | doc |
| 2 | The substring-matching claim is removed from `behavior_rejected`, from `docs/migration/rejected-components.md:54`, **and** from `feedback.py:70`. Three copies; one edit is not the fix. | doc + doc-in-code |
| 3 | The demo-fixture fallback is attributed to `render_feedback_sidebar` (`acceptance.py:299-311`) in the manifest, in `rejected-components.md:53`, and in `feedback.py:14`. | doc + doc-in-code |
| 4 | `legacy_path`/`legacy_symbol` extended to `src/feedback/service.py` and `src/config.py:125-129` (F-20), which are where `MAX_FACTOR_DELTA`, `PER_REASON_BUMP` and the `min(max_delta, bump*count)` expression actually came from. | doc |
| 5 | `behavior_rejected` records the two `service.py` steps the port dropped — per-factor clamping into a band around baseline, and vector renormalization. Presently an unrecorded loss, and the substance of F-25. | doc + decision |
| 6 | The minimum-decision floor's stated rationale matches what it enforces (F-23) — either count declines, or say it counts decisions and why. | code or doc |
| 7 | `characterization_tests` set to `n/a` with the reason. Per F-18/F-19 parity is not merely absent, it is inexpressible: the vocabularies do not overlap enough for a parity case to be written. | doc |
| 8 | F-24, F-25 addressed (§4.5, §4.6). | code |

**MM-001 stays `verified`; F-1, F-2, F-3 are worked but do not gate it.** The
reviewer flagged the verdict as a judgement call at the boundary and published
the evidence for downgrading. That was the right call and this plan does not
revisit it — but see §4.2, which disagrees with the manifest's *disposition* of
F-1.

### 3.2 Corrections outside the manifest

Consolidated so nothing is missed. Every line here asserts something the review
disproved.

| File | Line | Finding |
|---|---|---|
| `docs/migration/rejected-components.md` | 53 | F-22 |
| `docs/migration/rejected-components.md` | 54 | F-21 |
| `docs/testing/scaffold-verification.md` | 74 | F-13 |
| `python/smartmatch_domain/smartmatch_domain/eli.py` | 10, 19 | F-4, F-10 |
| `python/smartmatch_domain/smartmatch_domain/ingest.py` | 172 | F-12 |
| `python/smartmatch_domain/smartmatch_domain/feedback.py` | 6, 14, 70 | F-18/F-19, F-22, F-21 |
| `docs/plans/remaining-foundation-r1-work.md` | F9 row | says "F-1..F-27"; there are 29 |

### 3.3 Two manifest-schema changes worth making while it is open

**Add a `behavior_introduced` field.** The schema has `behavior_retained` and
`behavior_rejected` and no third box. That is why MM-003's genuine improvement —
real time-based recency decay, which the legacy did not have — was filed under
"retained", producing F-4's softer half. The same gap pushed MM-004's escalation
of a warning to an error into `behavior_rejected` as an "Added:" sentence, which
is where F-12 went wrong. A port that improves on the legacy has nowhere truthful
to say so, and claims migrate to the nearest available field. This is a small
change that removes a recurring failure mode rather than one instance of it.

**Stop stating test counts in prose, or have CI check them.** F-5 and F-14 are
the same defect twice: a number written once, never recomputed, wrong within a
day. Two options —

- *Remove the counts.* `target_tests` names the file. Whether it has 13 or 14
  cases is a fact about the file, discoverable in a second, and worthless
  written down.
- *Machine-check them.* A test reads the manifest, and for each entry asserts the
  named test files exist and their collected case count matches the stated
  number. `pytest --collect-only -q` gives the count including parametrized
  expansion; an AST walk does not, and would be wrong for the parametrized files.

Recommend removing the counts and adding the cheaper half of the check — that
every path named in `characterization_tests` and `target_tests` exists. That
alone would have caught F-13, which is a High finding, at the moment it was
written. Counts are the part that rots; existence is the part that matters.

### 3.4 F-29

`docs/plans/orchestrator-handoff.md` records that the 5 dispatcher failures were
an artifact of reading the file while another agent was mid-edit, and that the
suite is green (26 dispatcher tests passing). If that is confirmed by a clean
run, F-29 should be marked **stale** in the review, not fixed. It was accurate
when written; the review was right to record it and right to put it out of scope.
Do not silently delete it — a finding that turned out to be an artifact is itself
worth leaving on the record, marked.

---

## 4. Track C — code defects, with severity argued

Ordered by this plan's severity, not the review's. Three assessments differ; each
is argued rather than asserted, and the argument is the point — a reader who
disagrees should be able to see exactly where.

### 4.1 F-15 — raised from Medium to High

`validate_columns` derives the present-column set from `rows[0]` alone. Two
datasets with identical rows in different order get opposite `is_usable`
verdicts.

The review rated this Medium alongside four other code defects. It is worse than
those, for three reasons that compound:

1. **It fails open, not closed.** If `rows[0]` happens to be complete, a dataset
   in which every other row lacks a required column is reported usable and
   proceeds to the quarantine-and-review path (v1.1 §1.5). Every other code
   defect in this set produces a wrong number; this one produces a wrong
   *verdict*, in the permissive direction, from a control whose docstring says
   "here the import fails closed."
2. **The triggering condition is not under anyone's control.** Row order in an
   import is whatever the exporter emitted. A JSON-lines export that omits null
   keys, a spreadsheet that drops trailing empty cells, a partial re-export — all
   ordinary, none reviewable. There is no operator discipline that avoids this.
3. **It is a regression against the legacy.** The legacy's DataFrame took the
   union of keys and did not have this behavior. MM-004's disposition is `ADAPT`.
   A port that silently loses a correctness property of the thing it adapts is
   the precise category the manifest exists to detect, and this one got past it.

The fix is not simply "take the union", because the union hides the raggedness
rather than reporting it: a dataset where half the rows lack `metro_region` is
not clean, it is ragged, and the coordinator needs to know. Design:

- Derive `present` as the union of normalized keys across all rows.
- Add a distinct finding — `ragged_rows` — when row key sets differ, naming the
  columns that are absent from some rows and the count of rows affected.
- Decide its severity. `WARNING` treats raggedness as a quality signal; `ERROR`
  treats it as unusable. Recommend `WARNING` for optional columns and `ERROR`
  when a *required* column is missing from any row, which is the reading most
  consistent with `nullable: False` in the legacy and with fail-closed.

Cost is one pass over the rows, which the entirely-blank check already performs —
`validate_columns` is already O(rows × columns) through `_get_normalized`.

### 4.2 F-1 — severity unchanged, disposition disputed

The manifest defers F-1 to R2 "alongside the delivery path that will actually
send these invites." This plan disagrees, and the disagreement is cheap to
settle.

There are two ways to make the document conformant. Adding `ORGANIZER` and
`ATTENDEE` cannot be done now: there is no organizer identity to name (domain
registration is open decision 8 / backlog D4, which is exactly why the UID
namespace is `smartmatch.invalid`) and no attendee model. **Deleting the
`METHOD:REQUEST` line can be done now, restores the legacy's behavior in this
respect, and is one line.**

The argument for doing it now rather than at R2 is the module's own: this
codebase's discipline is that an artifact must not assert what its data does not
support. A fabricated date was rejected for that reason. `METHOD:REQUEST` is an
assertion that this document is an iTIP scheduling request from an identified
organizer to identified attendees, and it is not one. Carrying an untrue
self-description for a release because the true version is expensive is the
habit the port exists to end, and the cheap truthful state — no `METHOD` — is
available today. Add `METHOD` back in R2 when there is an organizer to put in it.

Two adjacent observations, recorded rather than raised as findings:
`STATUS:CONFIRMED` is emitted unconditionally, which is defensible given
`generate_ics` requires a resolved instant but is not derived from anything; and
`test_document_structure_matches_legacy_shape` says the envelope is "unchanged
from the legacy output" while `METHOD`, `STATUS` and `PRODID` all changed. The
test is not wrong, its docstring is. Both are for the re-reviewer to settle.

### 4.3 F-6 — severity unchanged, reasoning replaced

`compute_eli` stores `utilization=round(utilization, 4)`; `evaluate_cap` tests
the rounded value with `> 1.0`. 100.000 %–100.005 % of declared capacity reports
`WITHIN_CAP`.

Taken as a quantity this is nothing: 0.005 % of a 40-hour capacity is about seven
seconds of engagement time. No professional is protected or harmed by seven
seconds, and a plan that argued otherwise would not be believed.

What makes it worth fixing at Medium is **the coupling, not the window.** A hard
eligibility constraint — one that architecture v1.1 §1.3 makes overridable only
by an authorized, expiring override — has its threshold parameterized by a
constant chosen for readability, in a field whose own docstring describes it as
existing "so the explanation can show how far over capacity a professional is."
The rounding is a presentation decision. Presentation decisions get revisited by
people who have no reason to believe they are touching an eligibility boundary.
Round to 2 dp for a nicer explanation — an entirely reasonable change — and the
window widens a hundredfold to 0.5 % of capacity, twelve minutes on a 40-hour
cap, and **not one test fails.** The defect is that a safety control reads a
display value; its current width is incidental.

Fix: `evaluate_cap` decides on the unrounded utilization. Keep the rounded value
in the snapshot for explanation, or drop the rounding and round at render. The
test that matters is not "40.002 h is over cap" but a test that the cap decision
is *insensitive to the display precision* — parametrize the rounding and assert
the boundary does not move.

### 4.4 F-7 — severity unchanged, mechanism corrected

The review says an idle professional with only a blackout acquires "a load score
of 4.0 and a non-zero Stage B penalty." The score is right; the penalty claim
does not hold, and the correction matters because it moves the defect into a
worse category rather than a milder one.

`evaluate_cap` checks `MANUAL_BLACKOUT` first and returns `BLACKED_OUT`, so a
blacked-out professional is ineligible at Stage A and never reaches Stage B in
that snapshot. **The effect on the matching outcome is nil, not small.** The
`load_penalty` of 0.0016 is computable but unreachable.

The damage is to the recorded number, which is worse:

- `EliSnapshot` is what gets persisted, versioned by `ELI_FORMULA_VERSION`
  against v1.1 §2.2's `eli_snapshot.formula_version`. A stored snapshot asserts
  measured workload of 4.0 for a professional who has done no work.
- It is what the coordinator-facing explanation renders, and what any
  "underutilized" view reads — the control-center view backlog M5 feeds (V6,
  repeatedly selected vs underutilized). A professional who blocked out a fortnight
  looks marginally busier than an identical colleague who did not, in the exact
  view built to find people who are not being used.
- v1.1 §5.1 gives the professional the right to see and correct the workload data
  used about them. There is nothing here to correct. The 4.0 does not correspond
  to any engagement, and no amount of data correction removes it.

So: a truthfulness defect in a persisted, human-facing record, not an optimizer
defect. Same severity, and the fix is the same one line — exclude
`MANUAL_BLACKOUT` from `modifier_points`; it already has its own branch in
`evaluate_cap` and does not need a second expression through the score. Keep it
in `snapshot.modifiers` so the explanation still shows it. Extend
`test_manual_blackout_wins_over_spare_capacity` to assert `score == 0.0`, which
the review noted it deliberately does not.

### 4.5 F-25 — raised from Low to Medium

Six factors may each be proposed to move +0.08, +0.48 in aggregate, against
weights that must sum to 1, with no normalization in the proposal.

The review rated it Low on the grounds that each individual delta respects its
bound, which is what the manifest claims. The reason to raise it is not the size
of 0.48. It is that **the number a human approves is not the number that gets
applied.** Weights are normalized somewhere — `factor_registry.normalize_weights`
exists — so after normalization a proposed +0.08 on one factor is not a +0.08
change in effective weight, and the more factors move together the further apart
the two numbers get. The entire safety argument for this module is that a human
approves the change. An approval control whose displayed quantities do not
correspond to the effect of approving is weaker than it looks, and it is weak in
the direction that is hardest to notice: everything renders plausibly.

The legacy did both steps the port drops — clamp each factor into a band around
its baseline, then renormalize the vector. Dropping them may well be right; it is
not recorded (that is F-20's other half).

The remedy is partly a decision and not only code, which is why it is sequenced
rather than done now: the proposal's *application semantics* — normalize on
apply, or bound the sum at proposal time, or both — must be settled before any
consumer exists, and the consumer arrives with weight sets in M1/M8, behind gate
G1. Until then, record in the manifest that the proposal is un-normalized and
that its application semantics are unspecified, and add a test asserting whatever
bound is chosen. Do not add a sum bound picked arbitrarily now; that would
manufacture a number with no more provenance than the one it replaces.

### 4.6 F-24 — what a real test of the shadow-mode control looks like

`test_proposal_always_requires_human_approval` asserts `requires_approval is
True` against a property whose body is `return True`. It passes against an empty
implementation. It is the only test of the control the entry's `security_review`
line rests on.

The useful thing here is that **the real test has already been written — it is in
the review document instead of the test suite.** The reviewer made four separate
attempts to defeat the control and recorded the outcomes:

| Attempt | Outcome | What it proves |
|---|---|---|
| `p.requires_approval = False` | `TypeError` | `frozen=True` |
| `object.__setattr__(p, 'requires_approval', False)` | `AttributeError: property has no setter` | no setter, and `slots=True` removed the `__dict__` that would absorb it |
| `WeightProposal(..., requires_approval=False)` | `TypeError: unexpected keyword` | not a constructor field |
| `dataclasses.replace(p, requires_approval=False)` | `TypeError: unexpected keyword` | not reachable through the dataclass API |
| `__slots__`, `has __dict__: False` | — | the absorbing surface is genuinely absent |

A real test is those five probes as five `pytest.raises` cases, plus an assertion
that `WeightProposal.requires_approval.fset is None`. Each fails if someone
removes `frozen=True`, or `slots=True`, or converts the property to a field —
which is exactly the set of edits that would silently turn a structural control
into a settable flag. The current test survives all of them.

F-27 belongs with it: add `@typing.final` and a case asserting the subclass route
is closed, or — if `final` is judged too strong — a case pinning the current
behavior so the gap is recorded rather than implied.

This generalizes. The review executed probes for F-6, F-7, F-8, F-12, F-15, F-23
and F-25 and published transcripts for each. Those transcripts are executable
evidence sitting in a Markdown file. **Porting them into the test suite is the
single highest-value item in this whole plan**, and §5 explains why: it converts
claims that must be re-checked by a person into mechanisms that are re-checked by
CI, which is the only durable answer to the re-review problem.

### 4.7 F-8 — lowered from Medium to Low

`compute_eli` scores `len(inputs.modifiers)` on the raw sequence while the
snapshot reports `frozenset(inputs.modifiers)`, so a list with duplicates yields
a score of 20 beside an explanation naming one modifier.

Lowered, for one reason: `mypy --strict` runs over these packages in CI, and
`LoadInputs.modifiers` is annotated `frozenset[LoadModifier]`. Any in-repo caller
passing a list is a type error that fails the build. The residual exposure is
untyped boundaries — rows deserialized from persistence, an API payload — and
none of those exist for this module yet.

The severity is lower than the review's; the priority is not. The fix is to
compute `modifiers = frozenset(inputs.modifiers)` once and use that value for
both the score and the snapshot, which is one line, removes the entire class
rather than the instance, and costs nothing to review. There is no case for
deferring it. The review is right that it weakens the "closed input structure"
security claim, and the manifest's `security_review` line should be softened to
say the structure closes the field set, not the field types.

### 4.8 The remainder

| Finding | Disposition |
|---|---|
| F-2 | Rewrite the golden test to assert the property that is actually true — that the API admits no unresolved date — or rename it so the docstring does not promise a parsing test. The underlying property (impossible by construction) is stronger than a runtime check and worth saying so. |
| F-9 | **A decision before a fix.** If `EngagementRecord` means "completed *or committed*", the window must include future-dated records, and ELI becomes a forward-looking capacity measure — which is what "prevent over-commitment" implies. If it means completed only, the docstring is wrong. Either way the branch needs a test; today it has none. Migration owner decides, engineering implements. |
| F-16 | Decision: whether `null`/`none`/`nan` are blank depends on what the column holds, and `Null` and `None` are real names. Options are a per-column opt-out, restricting the rule to non-name columns, or accepting it and documenting the trade. Accepting it is defensible; leaving it undocumented is not. |
| F-17 | Report the coordinator's original header alongside the normalized name. Separately, two headers that normalize to the same column are accepted silently with one shadowing the other — that should be a finding of its own, and it is a data-loss path, not a cosmetic one. |
| F-23 | See MM-005 condition 6. Either count declines (matching the stated rationale) or restate the rationale. Counting declines is the stricter reading and matches "the legacy would learn from a single click". |
| F-26 | Reject a blank `match_run_id` at construction, consistent with the reason/decision invariants next to it. |
| F-27 | With F-24. |

---

## 5. Re-verification: making a corrected manifest mean something

§6 of the orchestrator contract forbids an agent approving its own port. Applied
literally it only bars the author of MM-003 from re-reviewing MM-003. The problem
here is a step removed and worse: **the corrections in §3 are being written by
the same party whose original claims failed.** If the migration owner rewrites
`behavior_retained` and then a review confirms the manifest now matches the code,
nothing has been established that a careful reader could not have established by
reading the code. The manifest would be internally consistent and evidentially
empty — which is a worse state than the current one, because it looks settled.

Four measures, in order of how much they actually buy.

**1. Make the evidence executable (§4.6).** The strongest guarantee against
self-approval is not a person, it is a mechanism. A claim that is a passing test
in CI is re-verified on every push by something with no stake in the outcome. Do
this first, because it changes what the human re-review has to do: instead of
re-deriving seven behavioral claims from the legacy source, the reviewer checks
that the tests encode the claims and that they fail when the behavior changes.
Concretely, before requesting re-review:

- the F-24 probe suite (five cases);
- the F-6 boundary table as a parametrized case, including insensitivity to the
  display rounding;
- the F-15 row-order pair — the same rows in two orders, asserting the same
  verdict;
- the F-7 idle-plus-blackout case asserting `score == 0.0`;
- the F-12 legacy transcript as MM-004's characterization cases, if route (a) is
  chosen;
- the manifest-path existence check from §3.3.

**2. Separate the corrector from the re-reviewer, and say so in the entry.** The
manifest already carries `reviewer`. It needs to distinguish *who corrected* from
*who verified*, because the correcting author is now part of the entry's
provenance. Add a `corrections` field naming the finding IDs addressed, the
commit, and the author. A re-reviewer who cannot see what changed since the
rejection has to re-review everything or trust the summary; neither is what is
wanted.

**3. Constrain the re-review's method.** The failure mode is a reviewer who reads
the corrected entry and confirms it. Require instead: re-derive each corrected
claim from the legacy source at `bdce024` and the target source *before* reading
the corrected text, then compare. For F-21 specifically — a claimed defect that
does not reproduce — the only acceptable evidence is a fresh search of the legacy
tree, not agreement with the first review. Two reviews reaching the same
conclusion from the same source is worth something; the second review reading the
first is worth much less.

**4. Require a "what could not be verified" section.** The first review's is its
most credible section. Make it mandatory rather than a habit of one reviewer. A
re-review returning an empty one should be treated as incomplete.

**And state the ceiling plainly.** F-28 caps what any re-review can conclude.
Architecture contract v1.1 is not in this repository, so no `contract_refs` value
on any entry can be checked — including the §1.3 reference that justifies ELI's
two-stage cap and the Appendix B reference that justifies shadow mode. **Even
with every correction in §3 and every fix in §4, the best honest verdict
available is "verified except `contract_refs`."** Reaching a clean `verified`
requires a decision that is not engineering's:

- place v1.1 (or a pinned, hash-referenced copy) in the repository, or
- redefine `contract_refs` as author-asserted and not evidence, and stop reading
  it as though it were.

Recommend the first. The second is honest but it removes the traceability the
field exists for. Either way it is a decision the program owner owes the
re-review, and it should be made before the re-review is requested rather than
discovered inside it — otherwise the re-review returns the same F-28 and the
cycle repeats.

---

## 6. F7 — widening the schema drift test

**Status: landed, in `f6980ef`.** The design below was written prospectively;
this note records what actually shipped and the two places the implementation
deliberately went beyond or differed from the design as written. Everything
else in §6.1–§6.4 landed close to as designed: the four comparisons in §6.2,
the two deliberate omissions in §6.3, and the ADR-0004 amendment in §6.4.

**Where it differs from the design:**

1. **The tenant-anchoring check enumerates from the database, not from
   `schema.py`.** §6.2 does not say which side `test_every_tenant_scoped_table_is_anchored_by_a_composite_key`
   should walk, and the first implementation attempt derived the table list
   from `schema.py` — the side already under test. That was a quiet regression
   against the hard-coded five-table list it replaced: simplifying a composite
   key in the mirror removed the table from the derived list, deleting the
   very case that should have caught it, and the suite went green one test
   lighter. The design did not anticipate that the derived list could shrink.
   The landed version enumerates every table **in the live database** that
   carries a `tenant_id` column, which cannot be shrunk by editing the side
   being interrogated.
2. **Positional correspondence of `tenant_id` is asserted, not just
   membership in the composite key.** §6.2's item 1 talks about comparing
   "referred table and columns", which a design reading literally would accept
   a composite key on `(tenant_id, user_id)` referencing
   `user_account (id, tenant_id)` — composite, and it does contain
   `tenant_id`, and it enforces nothing at all, because the columns are
   swapped against the referred side. The landed test requires `tenant_id` to
   line up with the parent's `tenant_id` positionally. An earlier version of
   the test passed against exactly the swapped-column shape above; ADR-0004's
   amendment records that near-miss.

Both differences are recorded in ADR-0004's amendment (19 August 2026) as well
as here; this entry exists so a reader working from this plan alone, without
opening the ADR, still finds them next to the design they diverge from.

### 6.1 What is actually wrong

`org_unit.tenant_id` is the instance ADR-0004 names. It is not the extent of it.
Every foreign key from a tenant-owned table to `tenant` is declared in
`schema.py` without an `ondelete`:

| Table | Migration | `schema.py` |
|---|---|---|
| `org_unit`, `user_account`, `job`, `idempotency_record`, `tenant_budget`, `concurrency_lease` | `RESTRICT` | *(none — NO ACTION)* |
| `rate_limit_counter` | **`CASCADE`** | *(none — NO ACTION)* |

Seven foreign keys, two deliberately different intents, flattened to one default
in the mirror. The mirror cannot presently distinguish "a tenant with live data
must not vanish" from "these counters go with it" — and
`tests/integration/conftest.py` documents the first intent in a comment while
`schema.py` does not express it.

**Be precise about the consequence, because overstating it invites dismissal.**
`METADATA` is never used to create a database — the only consumers are query
construction and the drift test itself — so today the divergence has no runtime
effect, and `NO ACTION` and `RESTRICT` both refuse the delete in PostgreSQL
(they differ on deferrability). The database is correct. What is wrong is that
the hand-written mirror is the artifact people read to learn the schema, and it
is wrong about seven constraints; and that ADR-0004 tells readers the drift test
is the guard, so the wrongness is invisible in exactly the way the ADR says it is.

**A second gap is more urgent than the `ondelete` one.** The drift test compares
table names, column-name sets, composite-FK *presence* on five hard-coded tables,
and asserts three named unique constraints exist in the database. It compares
**no constraint definitions at all**, in either direction. A unique constraint
added to a migration but never mirrored into `schema.py` — or mirrored but never
migrated — fails nothing. Wave C's identity work (globally unique
`external_subject`) is described in `docs/plans/orchestrator-handoff.md` as
needing the mirror updated because "the drift test will catch it otherwise."
**As written, it will not.** The change adds no column, so the column-name test
does not fire, and no test compares unique constraints as a set. That makes F7 a
prerequisite for Wave C rather than a parallel cleanup.

Related, and cheap to close at the same time: `idempotency.py:114` and
`rate_limit.py:172-173` pass constraint names to `on_conflict_*` as string
literals. `uq_idempotency_scope` has a test asserting it exists;
`pk_rate_limit_counter` does not, and `schema.py` does not name that primary key
at all. A constraint name referenced by a query is an interface, and one of the
two is unasserted.

### 6.2 What is worth checking

Design, in descending value. All of it lives in the integration lane, since it
needs a migrated database — same as today's test.

**1. Foreign key actions and targets.** PostgreSQL's inspector returns
`options["ondelete"]` from `get_foreign_keys` (confirmed in SQLAlchemy 2.0.52's
dialect); code-side it is `ForeignKeyConstraint.ondelete`. Normalize case and
treat `None`/absent as `NO ACTION`. Compare referred table and columns at the
same time, which generalizes `test_tenant_scoped_children_use_composite_foreign_keys`
from a hard-coded five-table list to the whole schema — so a future composite key
silently simplified in *either* definition fails, without anyone remembering to
extend a list. Small, no dialect-shape problems, and it catches the defect that
started this item. **Do this one.**

**2. Nullability.** `get_columns` returns `nullable`; compare against
`column.nullable`. A few lines, no normalization needed, and it works even for
the `ltree` columns because nullability is reflected regardless of whether the
type is recognized. Catches the class where the mirror thinks a column is
optional and inserts built from it fail only at runtime. **Do this one.**

**3. Constraint *names*, as sets, both directions.** `get_pk_constraint`,
`get_unique_constraints`, `get_check_constraints` against the names declared in
`schema.py`. This subsumes the three hand-written named-constraint tests, closes
the Wave C gap, and makes the two names used as string literals in queries into
asserted facts. It requires two small `schema.py` edits: name the
`rate_limit_counter` primary key `pk_rate_limit_counter` (the name the rate
limiter already passes), and decide whether to mirror the CHECK constraints by
name. **Do this one**, and mirror the CHECK names — a name costs a line and this
is how the Wave C failure mode is closed for good.

**4. Column types, with one stated exception.** Compile both sides against the
PostgreSQL dialect — `column.type.compile(dialect=postgresql.dialect())` — rather
than comparing `str(type)`. Verified against this schema: `TEXT`, `UUID`,
`TIMESTAMP WITH TIME ZONE`, `NUMERIC(12, 4)`, `JSONB`, `BIGINT`, `INTEGER`,
`BOOLEAN` all normalize identically on both sides, which removes the
generic-versus-dialect mismatch that makes naive type comparison flaky.

The exception is real and must be handled explicitly rather than by a broad
`try/except`. The inspector does not know `ltree` — that is ADR-0004's documented
wart and the source of the two `SAWarning` lines — and returns `NullType`, whose
`.compile()` raises `CompileError` rather than returning a string. So exactly two
columns, `org_unit.path` and `membership.granted_path`, need a separate
assertion: the code side is an `LTree`, and the database side is checked with a
targeted catalog query (`information_schema.columns.udt_name = 'ltree'`) instead
of through the inspector. Two hard-coded exceptions in a test is a smell; two
hard-coded exceptions that correspond exactly to a limitation an ADR already
documents is a record. Keep the warnings unfiltered, as ADR-0004 argues. **Do
this one**, with the exception written out and commented, not swallowed.

### 6.3 What is not worth checking, and why

**Server default expressions.** Reflection returns them as PostgreSQL renders
them — `now()`, `'1'::integer`, `false`, `'pending'::text`, `'0'::numeric` —
against a code side that mixes `sa.text("now()")` with bare strings `"1"`, `"0"`,
`"pending"`. Comparing those requires a normalizer that strips casts and quotes:
string munging, false failures on a PostgreSQL version bump, and the predictable
end state of an assertion nobody trusts. The payoff is small — a diverged default
surfaces the first time a row is inserted without that column, which the
integration suite already does.

**Recommend the cheap half instead:** compare *presence*, not expression —
`column.server_default is not None` against the reflected default being present.
That catches the harmful direction (the mirror believes the database fills a
column in and it does not) for a few lines and no normalization.

**Index comparison.** `schema.py` declares no indexes, deliberately: queries
compile without index objects. Comparing index sets means either mirroring every
index into `schema.py` — a second copy of information nobody reads, with the
GiST/`postgresql_using` shape being precisely what reflection reports awkwardly —
or maintaining an allowlist of index names, which is the same list in a different
file with the same drift problem one level up.

**Recommend instead: assert by name only the indexes that back a correctness
claim.** `ix_org_unit_path_gist` and `ix_membership_path_gist` must exist and be
`gist` — ADR-0004's case for `ltree` over `TEXT` is that subtree operators need
them, so if they are gone the ADR's claim is false and the authorization path
degrades to a scan. Performance indexes need no test.

**CHECK constraint expressions.** PostgreSQL normalizes them on the way in:
`effect IN ('allow','deny')` comes back as
`effect = ANY (ARRAY['allow'::text, 'deny'::text])`. Comparing expression text is
the most brittle item available. Names are covered by item 3; **behavior should
be asserted by an integration test that attempts the forbidden write**, which is
a better test in any case because it proves the constraint works rather than that
it exists.

### 6.4 Cost, stated plainly

One test module of roughly 120–180 lines, replacing and absorbing the three
named-constraint tests. A small `schema.py` change: seven `ondelete` values, one
named primary key, the CHECK constraint names. Two hard-coded `ltree` exceptions
that will need touching if a third `ltree` column appears. It runs only where a
migrated database is available, so it does not protect the unit lane — the
existing arrangement has that property too, and this does not change it.

The ongoing cost is that `schema.py` grows the constraint names it currently
omits, so a schema change becomes a slightly larger edit. That is the friction
ADR-0004 already chose and defended; this makes the drift test actually cover the
surface the ADR says the friction is buying.

**ADR-0004 must be amended when this lands.** Its "Cost, stated plainly"
paragraph states the narrow coverage as current fact, and names `org_unit` as
though it were the only divergence. Both stop being true. That amendment is part
of F7, not a follow-up — an ADR that describes a guard that has since been
widened is the same class of defect as everything in §3.

---

## 7. F8 — ADR index

`docs/architecture/decisions/` holds ADR-0001..0007, discoverable only by listing
the directory. Add `docs/architecture/decisions/README.md`: number, title,
status, date, one line of what it decides, and — the part that earns its keep —
what it supersedes or is superseded by, so the list stays truthful when one is
replaced. All seven are currently `Accepted`.

Two entries deserve a pointer rather than a bare title, because they are the ones
people will be looking for: ADR-0004 for the structural tenant-isolation
mechanism (recorded inside it, deliberately, and therefore invisible in a
filename), and ADR-0005 for the outbox claim.

Independent of everything else in this plan. Do it whenever.

---

## 8. A5 — `job.owning_unit_id`

### 8.1 What exists

`services/api/smartmatch_api/routers/jobs.py::_authorize_job_read` documents this
limitation in full and does not paper over it. Two routes call it — job status
(line 153) and the SSE stream (line 206). Today the rule is: suspended is refused
first and unconditionally; the job's actor may read it; a holder of an oversight
role may read it; everything else is denied. There is no unit scoping, because
`job` has no owning unit, and the docstring says inventing a unit path to feed
the policy would be fabricating authorization data rather than enforcing it.
That is the right call and A5 is the work that retires it.

The target shape already exists next door: `routers/imports.py:112-128` loads the
org unit, builds `Resource(..., owning_unit_path=OrgPath.parse(unit.path))` and
calls `assert_allowed` with `required_roles`. `policy.evaluate` then tests
`membership.granted_path.contains(resource.owning_unit_path)`. A5 is making job
reads able to do the same thing.

### 8.2 Sequence

**Expand.** Migration `0004` adds `job.owning_unit_id UUID NULL` with a
**composite** foreign key `(tenant_id, owning_unit_id) → org_unit(tenant_id, id)`
— single-column would break the structural isolation rule ADR-0004 exists to
protect, and `org_unit` already carries `uq_org_unit_tenant_id` to reference.
`ondelete` is a decision: `RESTRICT` matches the other tenant-parent keys and
refuses to delete a unit that owns jobs; `SET NULL` would silently return those
jobs to the unscoped state, quietly reopening S-006 for them. **Recommend
`RESTRICT`.** Mirror it in `schema.py` *including the `ondelete`* — which only
becomes CI-visible once §6 lands.

**Populate.** `submit_command` writes `owning_unit_id` for command types that
have one. For `import.create` the value is already in hand at the exact point the
job row is created: the router has loaded and authorized the unit, and
`unit_id` is already in the command payload. Command types with no owning unit
leave it `NULL`, which is a modelled state and not a gap.

**Backfill.** Existing rows: derive from `payload.unit_id` where the command type
has one — only `import.create` today — or leave `NULL`. Nothing is deployed and
no production data exists, so this is currently free. **It stops being free the
moment anything is deployed**, which is an argument for doing A5 before
deployment rather than after, and the strongest scheduling argument A5 has.

**Enforce.** `_authorize_job_read` gains a branch: keep "the actor may read their
own job" first — without it, a coordinator who submits a job and then changes
units loses access to their own job, which would be a regression — then build
`Resource(resource_type="job", resource_id=str(job.id), tenant_id=…,
owning_unit_path=…)` and call `assert_allowed` with the oversight roles. Reading
the path needs an `org_unit` lookup per job read, or a join in the job load;
`principals.py:104` has the `sa.cast(…, sa.Text)` pattern for reading an `ltree`
out.

**The `NULL` branch is the part to get right.** While `owning_unit_id IS NULL`,
fall back to today's actor-or-oversight rule, label the fallback explicitly in
the code, and give it its own denial/allow reason code (`unscoped_job`) so the
remaining exposure appears in audit records rather than being implied by absence.
Two code versions running side by side over a nullable new column is exactly the
migrate phase v1.1 §4.2 and ADR-0004 describe.

**Contract.** Once every row is populated and the release is fully promoted, make
the column `NOT NULL` and delete the fallback branch. The fallback branch is the
thing that must not become permanent; it is the residue of S-006.

### 8.3 Interactions

- **F7 comes first.** The new composite FK and its `ondelete` are precisely what
  the widened drift test protects, and `job` will need adding to the composite-FK
  assertion — which comes free if F7 generalizes that test off its hard-coded
  list, and is one more thing to remember if it does not.
- **A4 (authorization matrix) comes after.** A5 changes the job-read rule.
  Negative tests for job reads written before A5 get rewritten by it.
  `docs/plans/orchestrator-handoff.md` records that a test asserting unit-scoped
  job reads had to be removed because the control did not exist; A5 is when that
  test comes back, and it should come back as part of A5, not be rediscovered.
- **Wave C (identity) touches the same migration lane.** Both add migrations and
  both edit `schema.py`. Sequence them; do not run them concurrently.
- **The SSE route authorizes once, at stream open.** A membership that expires
  mid-stream is not re-checked. Out of A5's scope, but A5 is when someone is
  looking at this code with authorization in mind, so decide it there rather than
  leaving it for a reader to notice later.

---

## 9. Consolidated dependency order

Grouped by what unblocks what, not by size.

| Order | Work | Blocked by | Unblocks |
|---|---|---|---|
| 1 | **F7** — widen the drift test; amend ADR-0004 | — | Wave C, A5 |
| 2 | **Code fixes, per module** — `ingest.py` (F-15, F-16, F-17), `eli.py` (F-6, F-7, F-8, F-9, F-10), `feedback.py` (F-23, F-25, F-26, F-27), `ics.py` (F-1, F-3) | — | the three re-reviews |
| 3 | **Evidence tests** — port the review's probe transcripts (§4.6), including the F-24 suite | 2, since the tests assert the fixed behavior | the re-reviews, permanently |
| 4 | **Manifest + docstring corrections** (§3.1, §3.2), plus the schema changes in §3.3 | — (parallel with 2 and 3, but same files as 2 — stage per module) | the re-reviews |
| 5 | **The F-28 decision** — put v1.1 in the repository, or redefine `contract_refs` | program owner | a clean `verified` |
| 6 | **Request re-review** of MM-003, MM-004, MM-005 under §5 | 2, 3, 4; ceiling set by 5 | the Foundation gate |
| 7 | **A5** — `job.owning_unit_id`, expand → populate → enforce | 1 | A4 |
| 8 | **F8** — ADR index | — | nothing |

F8 is independent of all of it and can be done at any point by anyone.

---

## 10. Assumptions

1. **The review's factual observations are taken as given** where they were
   demonstrated by execution — counts, transcripts, reproductions. The severity
   *ratings* are not: §4 re-argues six of them, and three differ. Where this plan
   disagrees, the argument is written out so the disagreement can be adjudicated
   rather than voted on.
2. **The manifest's authority to make claims about the legacy is unchanged.** The
   legacy at `bdce024` is read-only evidence and remains reachable. If it does
   not, F-21 and F-12 cannot be re-verified by anybody and the corrections become
   unfalsifiable — which would be a finding in its own right.
3. **None of the four ported modules has a production caller.** Confirmed by
   search: outside their own tests the only references anywhere are
   `smartmatch_domain.jobs` and `smartmatch_domain.consent`, which are different
   modules. Every code defect in §4 is therefore latent. **This lowers urgency
   and raises the argument for fixing them now**, while the change is free of
   compatibility obligations and no caller encodes the wrong behavior.
4. **F-29 is stale**, per `orchestrator-handoff.md`. Confirm with a clean run
   before marking it; that document also says its own claims should be
   re-verified.
5. **Nothing here is deployed.** A5's backfill being free, and the code fixes
   having no migration story, both depend on that and stop being true when it
   changes.

---

## 11. Open questions

Each needs a named decision, not a default.

| # | Question | Owner |
|---|---|---|
| 1 | Does `EngagementRecord` mean completed **or committed** (F-9)? Including future commitments makes ELI forward-looking, which is what "prevent over-commitment" implies, and changes every score. | Migration owner, with the program owner if it touches open decision 2 |
| 2 | Is dropping the legacy's per-column dtype validation intended (F-11)? The target performs no type checking on imported cells at all. | Migration owner |
| 3 | Should a weight proposal be normalized at proposal time, at application time, or bounded in aggregate (F-25)? Cannot be settled without the consumer, which is gated on G1. | Program owner + engineering |
| 4 | Does `null`/`none`/`nan` remain blank in every column (F-16)? `Null` and `None` are real names. | Migration owner |
| 5 | Is `ragged_rows` a warning or an error when a **required** column is missing from some rows but not all (§4.1)? | Engineering, with the import contract owner |
| 6 | For A5: resolve the owning unit's path at read time, or snapshot it on the job? Resolve-at-read means a reorganization changes who can read historical jobs — usually right, occasionally surprising in an audit. Recommend resolve-at-read; record the alternative. | Engineering |
| 7 | F-28: v1.1 in the repository, or `contract_refs` demoted to author-asserted? Until this is answered no entry can reach a clean `verified`. | Program owner |
| 8 | Does correcting a manifest entry require a new `completion_commit`, or does the entry keep pointing at `7b5ab9f` with the corrections recorded separately? §5's `corrections` field assumes the latter. | Migration owner |
