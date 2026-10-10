> DRAFT — needs Danny decision. Nothing here is decided.

# #315 correction: the student recommender does not exist in code (draft)

Refs #315. Verified on branch `docs/sweep-2026-10-09-drafts` (based on main `122b01b0`).

## What the issue says vs what is in the tree

| Issue text | Finding | Evidence |
|---|---|---|
| "`content-1` serves" | False. `content-1` appears only in docs. No code, route, test or migration contains it. | `grep -rniE "ContentRanker\|LearnedRanker\|content-1" python services apps tests` returned no hits; doc hits: `docs/architecture/student-recommender-contracts.md:77,224,309`, `ADR-0024-staged-student-event-recommender.md:82,180` |
| "`LearnedRanker` exists shadow-only" | False. No class by that name. Only a doc planning a test, `tests/unit/test_learned_ranker_fallback.py`, which is not in the tree. | `student-recommender-contracts.md:524,634`; `ls tests/unit` has no `*ranker*` or `*recommend*` file |
| "ADR-0024 Accepted 2026-09-16" | Partly right. Status Accepted, drafted 14 Sep, ratified 16 Sep. The ADR says it "licenses no route, table, model artifact or scoring path". | `ADR-0024-staged-student-event-recommender.md:3-12` |
| OQ-SC-02, OQ-SE-01, OQ-SE-02 gate forward motion | Right. The ADR says all three "still need their named owners". | `ADR-0024:7`; `docs/decisions/student-recommender-decision-record.md:8` |
| Label path needs OQ-SE-19/20/21/22 | Right, as register rows added by the ADR. OQ-SE-20 is about promotion/rollback; 19, 21, 22 are labels, interaction matrix, propensity logging. | `student-recommender-decision-record.md:143,171,185,195`; `docs/plans/open-questions/student-engagement-deferred.md:59` |

## What exists in code

1. `python/smartmatch_domain/smartmatch_domain/student_factors/` (four pure factors, ADR-0025 D3). Its docstring says there is "no registry here, no ranker, no `rank_events_for_student`" because OQ-SE-01 and OQ-SE-02 are deferred (`student_factors/factors.py:1-9`, `student_factors/__init__.py:12`).
2. `StageBScore` in `python/smartmatch_domain/smartmatch_domain/scoring.py:161`, the speaker matcher's result type, which ADR-0024 plans to reuse unchanged (`ADR-0024` D1 interface list).
3. The class-exercise ranker `python/smartmatch_domain/smartmatch_domain/exercise/matching.py`, a separate fixed-weight list builder.

Not in code: `STUDENT_REGISTRY`, `StudentRanker`, `EligibilityFilter`, `FeedPolicy`, `ContentRanker`, `LearnedRanker`, any `student_profile` table or student feed route (greps across `python services apps tests`).

## What the docs claim

| Doc | Claim | Reality |
|---|---|---|
| ADR-0024 D1 | Stage A filter, Stage B `ContentRanker` V1 / `LearnedRanker` V2, Stage C policy (`ADR-0024:70-100`) | Design only |
| Contracts doc | Payload literal `ranker: "content-1" \| "ltr-1"` (`student-recommender-contracts.md:77`) | Design only |
| Decision record | Content-based "build first", LTR "architect toward; do not ship first" (`student-recommender-decision-record.md:51-52`) | Nothing built |

## Proposed corrected issue text

> **Title:** student→event recommender: ADR-0024 accepted, no code yet. Decide whether to start Stage A.
>
> ADR-0024 (Accepted 2026-09-16) fixes a three-stage design. No stage exists in code: there is no `ContentRanker` (`content-1`), no `LearnedRanker`, no registry and no student route. Only the four student factors exist (`student_factors/factors.py`). Starting any stage needs OQ-SC-02 (what may be stored), OQ-SE-01 (approve `STUDENT_REGISTRY` 0.1.0) and OQ-SE-02 (wildcard contract). A learned ranker also needs OQ-SE-19..22. Question: begin a Stage-A-only skeleton now, or leave the ADR as design until the gates close?

## Stage-A gate list

| Gate | What it decides | Owner (per sources) | Needed for Stage A skeleton? |
|---|---|---|---|
| OQ-SC-02 | May a student profile be stored | Program + records/privacy (`decision-record:82-91`); program owner confirmed 2026-09-16, awaits records/privacy co-signature | Only if Stage A reads a stored profile. A caller-supplied run needs no table. |
| OQ-SE-01 | Approve `STUDENT_REGISTRY` 0.1.0 | Program + scoring-registry owner (`decision-record:93`) | Stage B only |
| OQ-SE-02 | Wildcard contract | Program owner (`decision-record:107`) | Stage C only |
| OQ-SE-19 | Registration/attendance as training label | Records/privacy (`decision-record:143`) | Learned stages only |
| OQ-SE-20 | Who promotes and rolls back a learned ranker | BrooklynD23 per `decision-record:182` | Learned stages only |
| OQ-SE-21, OQ-SE-22 | Interaction matrix; logging with propensities | Records/privacy (`decision-record:185,195`) | Learned stages only |

Stage A is eligibility only: published, in window, modality-compatible, no quarantined tag, not already registered, with excluded events counted (`ADR-0024:77-80`, diagram).

## Optional minimal Stage-A skeleton (outline, no code)

- A pure `EligibilityFilter.apply(run, candidates) -> EligibilityResult` in `smartmatch_domain`, returning the eligible tuple plus a `Mapping[str, int]` of exclusion reasons (`ADR-0024` D1 interface list).
- Input is a caller-supplied run (modality, window, registered ids); nothing stored, so OQ-SC-02 stays untouched.
- Unit tests only: one per exclusion reason and one proving excluded events are counted, not dropped.
- No route, no table, no registry, no ranker.
- Risk: ADR-0024 says it "licenses a route, a table, a model artifact, or a scoring path" in no case (`ADR-0024:12`). Whether a pure filter counts as "scoring path" is a reading Danny must make.

## Open questions

1. Correct the issue text as above, or close #315 as stale? Danny.
2. Build the Stage-A skeleton now, or wait for the three gates? Danny (program owner role per ADR-0024 ratifiers: BrooklynD23).
3. Does a pure, storage-free filter fall inside ADR-0024's "licenses no scoring path" line? Danny/BrooklynD23.
4. Records/privacy co-signature on OQ-SC-02: who holds it and when? BrooklynD23 (named owner of records/privacy in `ADR-0024:5-6`).
5. Is the ledger's "stale" reading (no ContentRanker or LearnedRanker) the one to record on the issue? Danny.
