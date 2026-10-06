---
agent: devin-local
session: exclusive-garnet
created: 2026-10-02T19:02:09Z
audited: 2026-10-04
---
# Handoff: fix exercise matching factors to binary interest-fit and related-past-event count

The two student matching factors currently score Jaccard overlap, conflicting with the required binary interest-fit (any match → 1) and related-past-event count buckets (0→0, 1→0.5, 2+→1); this plan packages a complete multi-agent orchestration prompt for Claude plus the open decision points.

## Context

User wants the class-exercise student→event matching to score two factors differently than implemented. Repo: `C:\Users\thuys\Downloads\Smartmatch\IA-Smart-Match-Revamped`, branch `chau-10-02-update-matching-algorithm` (from latest origin/main).

**Status 2026-10-05: executed on this branch.** Chau's rulings on D5: (1) remove the undecided half-fit rule everywhere, not only on Northline; (2) `exercise/simulation.py`'s mirrored rule goes with it, which overrides the "MUST NOT CHANGE" line below; (3) full removal of the plumbing, including `exercise_event.is_exploratory`; (4) the column is dropped in the same PR (migration `0044_drop_event_exploratory`). The frontend therefore did change, and the "Agent D" notes below are stale on both points. Record: [`class-exercise-factor-revisions-2026-10-02.md`](../decisions/class-exercise-factor-revisions-2026-10-02.md).

**Status 2026-10-04:** audited; decision points D1–D5 confirmed by Chau. D5 is in scope (same PR) but the implementing agent must get Chau's ruling on the 4b reading before writing code. Audit corrections are applied inline.

### The conflict (verified against the code)

**Required by user:**

1. `stated_interest_overlap` — "said they are interested in this topic" (intention): **1** if any of the student's stated interests matches any of the event's topics, else **0**.
2. `past_event_topic_overlap` — "went to similar events before" (action): count past events that share **≥1 topic** with the new event → **0 related = 0, 1 related = 0.5, ≥2 related = 1**.

**Current implementation** (`python/smartmatch_domain/smartmatch_domain/student_factors/factors.py`):

- `stated_interest_overlap` returns `jaccard(card.normalized_interests, event.normalized_topics)` — fractional (e.g., 1 shared of 3 distinct terms → 0.3333); `None` when no card.
- `past_event_topic_overlap` returns `jaccard(union of all attended events' topics, event topics)`; `None` when `attended_event_topics is None` **or** when zero events attended.

**Not in conflict:** `same_major`, equal 0.25 weights, composition (unknown contributes nothing, no re-spread), tie-break, reason lines, markers — all stay. `career_goal_fit` stays **except** for its undecided branch, pending D5.

### Decision points for the orchestrator — resolved (confirmed by Chau, 2026-10-04)

- **D1 — zero attendance: CONFIRMED.** `past_event_keys` is `NOT NULL` default `[]`, so production always sends `attended_event_topics=()`. Keep `None` (unknown) for zero attended events — consistent with the requirements doc ("counts only for profiles that have that information") and ADR-0011. `None`-record stays unknown regardless. Unknown and measured-0 contribute the same 0 to the composite value, but they still differ in marker (`major_only` vs `major_plus_events`), the information tie-break, `unknown_factor_keys`, and the reason line.
- **D2 — keep factor keys: CONFIRMED, unchanged.** `stated_interest_overlap` / `past_event_topic_overlap` stay: they are API query-param names, saved-settings DB keys, and frontend label keys; labels ("said they are interested…", "went to similar events before") remain accurate.
- **D3 — versioning: CONFIRMED, with a correction.** Bump `EXERCISE_REGISTRY_VERSION` `exercise-0.1.0` → `exercise-0.2.0` (rulebook contents changed) and `EXERCISE_STAGE_B_FORMULA_VERSION` → `1.1.0-exercise`. Update the `tests/golden` pin of `"exercise-0.1.0"`. `EXERCISE_APPROVER` follows the existing convention at `python/smartmatch_domain/smartmatch_domain/exercise/registry.py` (~line 113, currently `"Ann Wang, class-exercise requirements 2026-09-15"`) → `"Ann Wang, progress check and revisions 2026-10-02"`. Note: Ann's Oct-2 revisions approve the factor changes; the 0.5 middle bucket for related past events is Chau's own refinement and is not in Ann's document, so the decision record must credit it to Chau.
- **D4 — deferred STUDENT_REGISTRY: CONFIRMED, accepted as written.** Docs (ADR-0024/design spec) describe the future student track as Jaccard-based; changing the shared `student_factors` functions changes what that track inherits. Accepted — flag it in the decision record.
- **D5 — RESOLVED: item 4b is in scope (same PR, Chau 2026-10-04), but the implementing agent must confirm the reading with Chau before writing code.** Ann's 2026-10-02 revision item 4b, verbatim (`docs/10-2-2026/SmartMatch_Progress_and_Revisions_10022026.docx` §4b): *"It is being counted as fitting a 'broad event.' That rule is not in the plan, and Northline is not a broad event. Please remove it."* This reverses OQ-CE-14 — Ann's own Sept-25 ruling that put `UNDECIDED_EXPLORATORY_GOAL_FIT = 0.5` in `career_goal_fit` (`python/smartmatch_domain/smartmatch_domain/student_factors/factors.py` ~lines 177–186) and marked both Northline and Harbor exploratory ("treat both… as exploratory, since they are company events" — `python/smartmatch_domain/smartmatch_domain/exercise/vocabulary.py` ~line 41; both are `Employer talk`). Two readings, very different diffs:
  - **(a) Remove the undecided rule everywhere** — the plainer reading of "that rule is not in the plan." `UNDECIDED_EXPLORATORY_GOAL_FIT` and the `career_goal_undecided` branch in `career_goal_fit` go; undecided becomes a measured `0.0` on every event. `UNDECIDED_GOAL_HALF_LABEL` (`exercise/registry.py` ~line 150) and the "undecided goal suits a broad event" reason phrase become dead. `exercise/simulation.py`'s mirrored rule (~line 539) presumably follows — Ann's Sept-25 email bound the two together — but that flips a file this plan lists as MUST NOT CHANGE, so get Chau's explicit word.
  - **(b) Northline only** — harder than it looks: `is_exploratory` is derived from `event_type` through `EXERCISE_EVENT_TYPES` (`vocabulary.py` ~line 236, `exercise/ingest.py` ~line 367) and Northline and Harbor share `Employer talk`, so unmarking the type also strips Harbor. Northline-only needs a per-event override or a new event type — uglier, and leaves Harbor undecided at 0.5, which Ann's wording does not clearly ask for. **Correction (2026-10-05):** this overstates the cost. Ann's file spells the two types `"Employer talk (exercise event 1)"` and `"Employer talk (exercise event 2)"`, which are separate keys in `EXERCISE_EVENT_TYPES` (`vocabulary.py:166-167`); flipping event 1 to `False` and re-uploading the dataset is Northline-only. Also add `test_on_the_goal_alone_every_fitting_goal_outranks_every_undecided_one` (`tests/golden/exercise/test_exercise_ann_dataset_golden.py:317`) to the golden pins that move under reading (a). See [`2026-10-05-oct-2-review-conflict-analysis.md`](2026-10-05-oct-2-review-conflict-analysis.md) §1 C1, and the past-event bucket risk in C7.
  - Golden pins that move either way: `test_northline_and_harbor_give_undecided_half_and_a_fitting_goal_the_whole` (UNDECIDED_CARDS `0.5` → `0` on E11, and E12 too under reading a), `test_an_undecided_card_on_northline_is_never_told_its_goal_fits` (P197's rank-30 pin and reason line); `test_undecided_earns_nothing_from_an_event_that_is_not_exploratory` still passes as-is.
  - Also flagged: revision item 4c (one reason line per name — remove the second FactorNames line) is separate frontend work; and the Northline refresh appends Northline's own topics to attendees' `attended_event_topics`, which under the count rule makes prior Northline attendance count as "related" when Northline is ranked again.

---

## THE HANDOFF — paste everything below into Claude

```markdown
# Orchestration task: fix two class-exercise matching factors

Repo root: `IA-Smart-Match-Revamped` (Python domain + FastAPI + React). Work on the
current branch. Do NOT merge; produce one PR-sized change set. Python tests run with
`pytest` from repo root; the domain package lives in `python/smartmatch_domain/smartmatch_domain/`.

## Before writing code (required)

Ask Chau these questions and wait for her answers — do not start Agent A without them:

1. Item 4b reading: remove the undecided half-fit rule entirely, or only on
   Northline? Northline and Harbor share the `Employer talk` event type, so
   "Northline only" needs a per-event override, not a flag flip. (Full context
   in decision D5, outside this block.)
2. Does `exercise/simulation.py`'s mirrored undecided rule (~line 539) change
   with it? It is listed below as MUST NOT CHANGE; item 4b may override that.

## Goal

Two of the four shared student factors must change formula — plus a possible
third change to `career_goal_fit`'s undecided branch, gated on Chau's 4b
answer above. Keys, labels, weights, composition, tie-break, markers, and
reason sentences do NOT change.

1. `stated_interest_overlap` ("said they are interested in this topic", intention):
   - New rule: `1.0` if the profile card's normalized interests ∩ the event's
     normalized topics is non-empty, else measured `0.0`.
   - `None` (unknown) when `profile.card is None` — unchanged.
   - Empty card → measured `0.0` — unchanged.
   - Replaces: `jaccard(interests, event.normalized_topics)`.

2. `past_event_topic_overlap` ("went to similar events before", action):
   - New rule: `related =` number of attended events whose normalized topic set
     shares ≥1 term with `event.normalized_topics`. Then: `related == 0 → 0.0`,
     `related == 1 → 0.5`, `related >= 2 → 1.0`.
   - `None` (unknown) when `profile.attended_event_topics is None` OR when the
     record exists but names zero events — BOTH stay unknown (decision D1, matches
     requirements doc "counts only for profiles that have that information").
   - Replaces: `jaccard(union-of-attended-topics, event.normalized_topics)`.

Per-event relatedness must normalize each attended event's topics independently
(`normalized_terms(topics) & event.normalized_topics` non-empty → counts as 1).
Do NOT union the topics first — one past event covering one topic counts the same
as one covering all topics.

## Files to change

### Core (Agent A)
- `python/smartmatch_domain/smartmatch_domain/student_factors/factors.py`
  - Rewrite `stated_interest_overlap` and `past_event_topic_overlap` per above.
  - Update the module docstring table (lines ~10–16) and each function docstring.
  - Keep `FACTOR_SCORE_PRECISION` rounding; keep basis strings truthful (e.g.
    "N of M stated interests match an event topic" / "N related past events attended").
- `python/smartmatch_domain/smartmatch_domain/student_factors/evidence.py`
  - Update the docstring paragraph stating both absence kinds "read as unknown
    for past_event_topic_overlap" — it stays true (zero attended → unknown), but
    the rationale ("no topic set to compare") should now read "a count of related
    events has no events to count".
- `python/smartmatch_domain/smartmatch_domain/exercise/registry.py`
  - Bump `EXERCISE_REGISTRY_VERSION` to `"exercise-0.2.0"`; set
    `EXERCISE_APPROVER` to `"Ann Wang, progress check and revisions 2026-10-02"`
    and `EXERCISE_APPROVED_ON` to `"2026-10-02"` (D3 — Ann's Oct-2 revisions
    approve the change; the 0.5 middle bucket is Chau's own refinement and is
    credited to Chau in the decision record).
  - Update `_RATIONALE[PAST_EVENT_TOPIC_OVERLAP_FACTOR_KEY]` to describe the
    0 / 0.5 / 1 related-count rule.
- `python/smartmatch_domain/smartmatch_domain/exercise/matching.py`
  - Bump `EXERCISE_STAGE_B_FORMULA_VERSION` to `"1.1.0-exercise"`. No other change.
- `services/api/smartmatch_api/routers/exercise_matching_models.py` (~line 239)
  - Update the docstring claiming both absence kinds "read as unknown" only if
    D1 wording needs it — verify it still matches `factors.py`.

### Tests (Agent B — after Agent A)
- `tests/unit/test_student_factors.py`
  - `test_stated_interest_overlap_is_the_jaccard_index` → rename/rewrite: assert
    `1.0` for any-overlap and `0.0` for none (keep the no-card/empty-card tests).
  - `test_past_event_topic_overlap_unions_the_attended_events_topics` → rewrite:
    two related attended events → `1.0`; add cases: 1 related of several → `0.5`,
    0 related → `0.0` (already covered by the measured-zero test), empty record →
    `None` (existing), `None` record → `None` (existing).
- `tests/unit/test_exercise_matching.py` — audit composite expectations.
  Correction to the earlier draft: `_full_card` does NOT stay 1.0 under the new
  rule — it has exactly 1 attended event (~line 58), so its past-event factor
  becomes `0.5` and its composite `0.875`; the fixture is used at ~lines 80,
  89 (the explicit `== 1.0` check), 139, 252, 326, 327, 357, 533. Chau's
  confirmed resolution: extend the fixture with
  a second related past event — e.g. add `("analytics",)` to
  `attended_event_topics` — so it stays `1.0`. Then check any case assuming
  fractional overlap.
- `tests/golden/exercise/test_exercise_matching_golden.py` — confirmed
  FACTOR_CASES values:
  - G-CE-01 "major only": `0.25` (unchanged).
  - G-CE-02 "major misses, nothing else on file": `0` (unchanged).
  - G-CE-04 "empty card is measured, past events unknown": `0.25` (unchanged).
  - G-CE-03 "every factor known and perfect": stays `1.0` — the fixture gets a
    second related past event, e.g.
    `attended_event_topics=(("analytics", "careers"), ("analytics",))`
    (Chau-confirmed).
  - G-CE-05 "past events only": `0.5` → `0.375` (1 related event → `0.5 × 0.25`
    + `0.25` major).
  - G-CE-06 "card with a partial interest overlap": → `0.5` (binary interest:
    1 of its topics matches → full `0.25` + `0.25` major); keep the
    "1 of 3 interests" profile as-is, but update the pinned expression
    `0.25 + 0.25 * 0.3333` and the `# …: 1/3.` comment (~lines 103–109).
  - New G-CE-16 — Marketing + 2 related past events, no card → `0.5` (pins the
    ≥2 bucket).
  - New G-CE-17 — Marketing + 1 attended event with no shared topic → `0.25`
    (pins measured-0 vs unknown: marker becomes `major_plus_events` not
    `major_only`, wins the information tie-break at equal value, and the factor
    is absent from `unknown_factor_keys` — verify against `derive_marker` in
    `python/smartmatch_domain/smartmatch_domain/exercise/markers.py`).
  - ID note: G-CE-01…G-CE-15 are all taken — 01–06 are FACTOR_CASES and
    `test_g_ce_07`…`test_g_ce_15` cover tie-breaks, determinism, and registry
    isolation — so the two new factor cases take G-CE-16 and G-CE-17; also
    update the block header comment (~line 59, "G-CE-01 … G-CE-06: every
    factor, known and unknown") to name them.
  - Recompute every ranked-order golden; update the
    `registry_version == "exercise-0.1.0"` pin to `"exercise-0.2.0"`.
- `tests/unit/test_exercise_registry.py` (~line 115) — pins the
  `exercise-0.1.0` version string → `exercise-0.2.0`.
- `tests/unit/test_exercise_registry_isolation.py` (~line 28) — `EXERCISE_PIN`
  constant → `exercise-0.2.0`.
- `tests/golden/exercise/test_exercise_ann_dataset_golden.py` and
  `tests/golden/exercise/test_exercise_results_rule_sample_golden.py` — ranked
  orders on Ann's dataset will shift under the new values; recompute.
- Docstrings naming `exercise-0.1.0`:
  `python/smartmatch_domain/smartmatch_domain/exercise/registry.py`
  (~lines 14, 26, 241) and
  `python/smartmatch_domain/smartmatch_domain/exercise/matching.py`
  (~lines 3, 204) — update to the new version string.
- `tests/integration/exercise_class_driver.py` and any `tests/golden/exercise/`
  ranked-list fixtures: recompute expected orders under the new factor values
  (any-overlap → 1.0 boosts interest-matching carded profiles; related-count
  buckets change partial-attendance scores).
- `tests/unit/test_exercise_event_interest_fit_csv.py` — owned by Agent C
  (B and C run in parallel; do not touch it here).
- Note for spot-checks: with binary interest and bucketed past-events, more
  profiles tie on composite → more "tied on major; ordered by year" / "tied on
  what counted; ordered by year" reason lines — include this in the P004 and
  300-profile spot-checks.

### Data tooling + docs (Agent C — parallel with B)
- Bring `tools/compute_event_interest_fit.ps1` and
  `test_data/event_interest_fit.csv` onto this branch — they already exist at
  the correct paths on `origin/chau-0925-matching` (commit e7ff7b95), so the
  earlier "move from the workspace root" instruction is stale:
  `git checkout origin/chau-0925-matching -- test_data/event_interest_fit.csv
  tools/compute_event_interest_fit.ps1` and commit them, alongside the
  committed `tools/compute_event_major_fit.ps1` + `test_data/event_major_fit.csv`
  pair.
- `tests/unit/test_exercise_event_interest_fit_csv.py` is not on this branch —
  check out `origin/chau-0925-matching`'s version (commit eae720e0) or write it
  mirroring `tests/unit/test_exercise_event_major_fit_csv.py`. Its docstring
  must be REWRITTEN, not kept: the committed version says it is "deliberately
  not the app's Jaccard `stated_interest_overlap` factor", which is now false —
  after this change the CSV's binary rule IS the app's rule for carded
  profiles, while no-card stays unknown (not 0).
- `docs/superpowers/specs/2026-09-16-class-exercise-design.md` §4.2 table:
  replace the Jaccard rows with the binary and related-count rules.
- `docs/architecture/decisions/ADR-0025-*.md` factor table (~line 80): update
  the `stated_interest_overlap`/`past_event_topic_overlap` descriptions.
- `docs/product/class-exercise-requirements.md` "Matching" row (~line 199):
  update the parenthetical for "went to similar events before" to the
  related-event count rule if the current wording implies union-overlap.
- Add a short decision record under `docs/decisions/` (match existing naming)
  recording: binary interest fit replaces Jaccard; related-past-event count
  (0/0.5/1) replaces Jaccard-of-union; approver "Ann Wang, progress check and
  revisions 2026-10-02" — but the 0.5 middle bucket is Chau's own refinement,
  not in Ann's document, so credit it to Chau (per D3); note D4 —
  the deferred STUDENT_REGISTRY track inherits these formulas.
- Optional: a `compute_event_related_past_fit.ps1` + CSV + drift-guard test in
  the same pattern, if Chau wants the second factor also CSV-verified.

### API/surface audit (Agent D — parallel, mostly verification)
- Confirm no contract change: weight query params in
  `services/api/smartmatch_api/routers/exercise_matching.py` and
  `exercise_matching_weights.py` key on factor keys — unchanged.
- Frontend `apps/web/legacy-frontend` uses label keys only — unchanged; grep
  it for any stale "Jaccard" wording in comments (no hit expected —
  `RankedList.tsx` ~line 276 checked clean).
- `exercise/simulation.py` MUST NOT CHANGE: it is the hidden-truth results rule
  (`past_event_count >= 1` threshold, hidden true interests), a separate
  requirement, not a matching factor.
- `student_factors/terms.py`: `jaccard` MUST stay exported even if factors stop
  using it — `python/smartmatch_domain/smartmatch_domain/student_factors/__init__.py`
  re-exports it and `tests/unit/test_student_factors.py` imports it
  (~lines 25, 226). Removing it breaks the package.

## Constraints (all agents)
- ADR-0011/0016: unknown stays `None`, never `0.0`; unknown factors contribute
  nothing and their weight is never re-spread. Do not touch the composition.
- ADR-0025 D8: no numeric score may reach a screen-facing type.
- PROHIBITED_INPUTS / hidden true interests: nothing in `student_factors` may
  reference them; `test_student_factors.py` walks the AST to enforce this.
- Do not rename factor keys or labels.
- Do not modify `scoring.py`, `factor_registry.py` CBA constants, or
  `exercise/reasons.py` sentences (Ann-approved verbatim, OQ-CE-12).

## Suggested orchestration
1. Agent A (domain core) lands first — everything else depends on it.
2. Agents B (tests), C (tooling/docs), D (API audit) run in parallel.
3. Integrator: run `pytest tests/unit/test_student_factors.py
   tests/unit/test_exercise_matching.py tests/golden/exercise
   tests/unit/test_exercise_event_interest_fit_csv.py` then the full
   `pytest tests/unit tests/golden tests/integration` suite; fix fallout.

## Acceptance
- Any-overlap interest → factor `1.0`; none → `0.0`; no card → `None`.
- 0 related past events → `0.0`; exactly 1 → `0.5`; ≥2 → `1.0`;
  zero attended events or no record → `None`.
- All tests green, including the committed CSV drift-guard test for
  `event_interest_fit.csv`.
```

## Verification (for whoever implements)
- `pytest tests/unit/test_student_factors.py tests/unit/test_exercise_matching.py tests/golden/exercise`
- `pytest tests/unit/test_exercise_event_interest_fit_csv.py` (after the CSV/PS1 are checked out from `origin/chau-0925-matching` and the test is written)
- `pytest tests/unit tests/golden tests/integration` — full sweep for ranking fallout

## Risks
- The registry-version bump re-labels new scores; any stored exercise runs pinned to `exercise-0.1.0` become non-reproducible (acceptable pre-class, flag to Chau if the DB already holds runs). More composite ties also mean the year and fixed-order tie-breaks fire more often — verify the ranked-list goldens and the Ann-dataset spot checks.
- On Ann's current dataset no event has 2 related past events (Northline E11 relates only to E08; Harbor E12 only to E05), so the past-event factor caps at 0.5 for every profile in class — 16 profiles reach 0.5 on Northline, 11 on Harbor. Flag to Ann before class so the "went to similar events" slider isn't expected to move names as much as the other three.
- Rankings will visibly shift (partial Jaccard credit disappears; binary 1.0 rewards any single interest match) — expected, but worth a spot-check on Ann's P004 case and the full 300-profile dataset before class.
