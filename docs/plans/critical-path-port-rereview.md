# Critical path: F9 port re-review, F-28, and leftover copies

**IDs:** CP-REREVIEW, CP-V11
**Parent:** [critical-path-plans.md](critical-path-plans.md)

The Foundation ports gate is not "fix the code". It is "an independent reader
can trust the manifest". Code and most YAML corrections are on
`claude/pr1-blockers-todos-er5heu`. Status is still `ported_unverified` on
purpose.

Planning only.

---

## 1. Situation

| Entry | 18 Aug review | After PR1 F9 | Still required |
|---|---|---|---|
| MM-001 ICS | `verified` with F-1..F-3 | F-1..F-3 fixed (`654e89f`) | None for the gate. Optional: re-reviewer glance at METHOD removal. |
| MM-003 ELI | rejected (F-4, F-6, …) | Code fixed; YAML corrected | Independent re-review. `eli.py:10` docstring still wrong. F-9/D2 decision. |
| MM-004 ingest | rejected (F-13, F-15, …) | Code fixed; YAML `characterization_tests: n/a` | Re-review. Route (a) still better. `ingest.py` F-12 copy OPEN. F-11 decision OPEN. |
| MM-005 feedback | rejected (F-18, F-19, F-21, …) | Code fixed except **F-25** | Re-review. Must not promote while F-25 unspecified. Docstring copies OPEN. F-21 re-derive from `bdce024`. |

Sources: `docs/migration/port-verification.md` (on PR1: additive 26 Aug
amendment + F-30); `docs/plans/defect-remediation.md`;
`docs/migration/migration-manifest.yaml`; orchestrator contract §6;
`docs/plans/pr1-blockers-handoff.md` §3.2.

**F-29** is superseded (dispatcher failures were a mid-edit artifact). Closing
it fully means running the integration lane and saying so, not deleting the
finding.

**F-30:** the review's F-24 probe table attributed `p.requires_approval = False`
to `frozen=True`; it proves nothing about frozen. The PR1 test avoided the
hole. `defect-remediation.md` §4.6 still copies the wrong table — fix in the
docs wave.

---

## 2. CP-V11 — F-28, do this *before* requesting re-review

### (a) What / where

Architecture v1.1 is cited everywhere (`README.md`, every ADR, every
`contract_refs`) and is not in the tree. No reviewer can check that §1.3
requires the two-stage ELI cap or that Appendix B requires shadow mode.

`port-verification.md` "What could not be verified" §1;
`defect-remediation.md` §5 last paragraphs;
`stakeholder-audit-integration.md` §1.1.

### (b) Status

Open. Program owner. PR1 adds `contract_refs_status: UNVERIFIABLE` — labels
the ceiling, does not raise it.

### (c) Plan

Pick one:

1. **Recommended.** Place v1.1 (or a pinned, hash-referenced copy) under
   `docs/architecture/` (e.g. `docs/architecture/v1.1/`). Record SHA. Add a
   cheap test: every `contract_refs` section token exists in that file.
2. Redefine `contract_refs` as author-asserted, not evidence. Honest; destroys
   the field's purpose.

Do not request CP-REREVIEW hoping the reviewer will ignore F-28. They will
return it and the cycle repeats (`defect-remediation.md` §5).

### (d) Dependencies

Program owner. Unblocks a clean `verified`. Does not unblock matching (G1).

### (e) Acceptance

Either the contract file is tracked and `contract_refs` are machine-checkable,
or the manifest schema and review checklist say the field is not evidence.
Every entry's `contract_refs_status` updated to match.

### (f) Priority

Immediately before CP-REREVIEW, parallel with CP-PR1 merge politics.

---

## 3. CP-REREVIEW — independent verification

### (a) What a re-review is for

§6 forbids an agent approving its own port. `defect-remediation.md` §5 extends
that: the *corrector* of a failed claim is also not the re-reviewer. A review
that only confirms "YAML now matches code" is evidentially empty.

### (b) Status

Corrector ≠ original port author, but still not an independent verifier of the
legacy claims. On 26 Aug the legacy clone was **missing** from the PR1
environment; corrections of F-11, F-12, F-18, F-19, F-20, F-21, F-22 restated
the first review's transcripts. Measure 3 of §5 forbids a re-review that
agrees with the first review instead of re-searching `bdce024`.

### (c) Execution plan

**Preconditions**

1. CP-PR1 merged (or re-review against the PR1 tip, named in the review header).
2. CP-V11 decided.
3. Legacy repository readable at `bdce024de1a9bf488c6bd9a7c24a3c87e03ffa42`.
   Verify with `git cat-file -t` + `git log -1`. Read-only. `git status
   --porcelain` clean after.
4. Re-reviewer is not the F9 corrector and not the original porter.

**Method (defect-remediation.md §5)**

1. For each corrected *legacy* claim, re-derive from `bdce024` **before**
   reading the corrected YAML. Especially F-21 (claimed substring matcher):
   fresh search of the legacy tree.
2. For each code fix, check the test encodes the claim and fails when behaviour
   changes. Prefer the already-ported probe tests (F-6, F-7, F-15, F-24, F-12
   if route (a) is taken).
3. Include module docstrings in scope (`eli.py`, `ingest.py`, `feedback.py`).
   A YAML-only pass leaves the falsehood in the package.
4. Mandatory "what could not be verified" section. Empty = incomplete.
5. Distinguish `reviewer` (this pass) from who corrected. Prefer a `corrections`
   field (finding IDs, commit, author) if the schema was added on PR1; if not,
   put it in `verification_notes` rather than inventing a schema mid-review.

**Per-entry checklist** (from PR1 `port-verification.md` amendment)

**MM-003**

- [ ] `behavior_retained` does not claim event cadence.
- [ ] Time-based recency decay is **introduced**, not retained.
- [ ] `eli.py` module docstring matches (F-4 copy; `a48408a` may have done
      part of this — verify, do not assume).
- [ ] F-6: cap uses unrounded utilization; test insensitive to display rounding.
- [ ] F-7: blackout not in measured score; `score == 0.0` for idle+blackout.
- [ ] F-8: one `frozenset` for score and snapshot.
- [ ] F-9: future-dated records **refused** (current decision: completed only).
      Re-reviewer may disagree; disagreement goes to D2, not a silent code flip.
- [ ] `security_review` claims field **set**, not field **types**.

**MM-004**

- [ ] Decide route (a) characterization tests vs route (b) `n/a`. Route (a)
      is cheaper than it looks: F-12 transcript (empty → issue; whitespace →
      was healthy, now blocking; literal `nan` → issue) plus
      `blank_sentinels=("nan",)` after F-16.
- [ ] F-11: dropping dtype/null-count/nullability recorded; **intent** of
      dropping dtype validation decided.
- [ ] F-15: union of keys; `ragged_rows`; required-column missing on any row
      is ERROR (or documented otherwise).
- [ ] F-16: caller-declared sentinels, default off.
- [ ] F-17: original headers reported; colliding normalized headers are findings.
- [ ] `ingest.py` comment that restates F-12 corrected.

**MM-005**

- [ ] Vocabulary and mapping recorded as **replaced**, with the two-disagreeing-legacy-mappings justification.
- [ ] Substring-matching claim gone from YAML, `rejected-components.md`, **and**
      `feedback.py:70`. Re-derive F-21 from legacy.
- [ ] Demo-fixture fallback attributed to `render_feedback_sidebar`.
- [ ] `legacy_path` includes `service.py` / `config.py`.
- [ ] Dropped clamp + renormalization recorded (F-25 substance).
- [ ] Decision floor matches stated rationale (F-23).
- [ ] F-24 real probes in CI (not `return True`). Mind F-30: probe a **field**
      for frozen, not the property.
- [ ] F-26 blank `match_run_id` rejected; F-27 `@final` or pinned gap.
- [ ] **F-25 remains open.** Do not promote the entry as if application
      semantics were specified. Manifest must say the proposal is un-normalized
      and unspecified on apply.

**MM-001 (non-gating)**

- [ ] F-1: `METHOD:REQUEST` removed (cheap truthful state) unless R2 added
      ORGANIZER/ATTENDEE.
- [ ] F-2 golden test renamed or actually about the construction invariant.
- [ ] F-3: default clock branch tested or claim dropped.

**Process artifacts**

- [ ] Manifest path-existence check (defect-remediation §3.3) if not already
      on PR1.
- [ ] Test counts not restated in prose, or CI-checked. PR1 measured new
      counts; do not write them from memory.

### (d) Dependencies

CP-PR1, CP-V11 (for clean verified), legacy `bdce024`, leftover docstring
edits (can be a small engineering commit immediately before review).
**Unblocks** Foundation "included ports are verified" gate.

Does **not** require G1, A5, or frontend.

### (e) Acceptance

- Independent review document (amend `port-verification.md` additively, or a
  sibling `port-rereview.md`) naming reviewer, date, commit.
- MM-003, MM-004, MM-005 status `verified` or `verified except contract_refs`
  with `contract_refs_status` consistent with CP-V11.
- MM-005 notes F-25 still unspecified if still true.
- "What could not be verified" non-empty unless v1.1 is in-repo and every
  other item was actually checked.
- Corrector ≠ reviewer, recorded.

### (f) Priority

After merge and the F-28 decision. Before claiming Foundation ports closed.

---

## 4. Leftover copies — small engineering commit before review

Do not leave these for the reviewer to trip over. File set from
`defect-remediation.md` §3.2 plus PR1 amendment:

| File | Finding |
|---|---|
| `python/smartmatch_domain/smartmatch_domain/eli.py` | F-4, F-10 (partially addressed in `a48408a`) |
| `python/smartmatch_domain/smartmatch_domain/ingest.py` | F-12 |
| `python/smartmatch_domain/smartmatch_domain/feedback.py` | F-18, F-19, F-22, F-21 |
| `docs/plans/defect-remediation.md` §4.6 | F-30 table |
| `docs/plans/remaining-foundation-r1-work.md` F9 row | still says "F-1..F-27" in places; there are 30 findings now |

Stage **per module** with any remaining code nits so two agents do not contend
for `eli.py` (`defect-remediation.md` §1).

---

## 5. What must not happen

- Do not flip `status: verified` in the same commit as the YAML correction.
- Do not rewrite A4's 18 August transcripts to match 26 August reality.
  Annotate (`port-verification.md` amendment notice explains why).
- Do not add an F-25 aggregate bound "to finish the entry". An earlier agent
  did; it was reverted (`pr1-blockers-handoff.md`).
- Do not treat F-21 as closed because the first review and the corrector agree.
