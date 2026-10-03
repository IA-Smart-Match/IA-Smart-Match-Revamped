---
agent: devin-local
session: exclusive-garnet
created: 2026-10-02T19:02:09Z
---
# Handoff: fix exercise matching factors to binary interest-fit and related-past-event count

The two student matching factors currently score Jaccard overlap, conflicting with the required binary interest-fit (any match → 1) and related-past-event count buckets (0→0, 1→0.5, 2+→1); this plan packages a complete multi-agent orchestration prompt for Claude plus the open decision points.

## Context

User wants the class-exercise student→event matching to score two factors differently than implemented. Repo: `C:\Users\thuys\Downloads\Smartmatch\IA-Smart-Match-Revamped`, branch `chau-10-02-update-matching-algorithm` (from latest origin/main).

### The conflict (verified against the code)

**Required by user:**

1. `stated_interest_overlap` — "said they are interested in this topic" (intention): **1** if any of the student's stated interests matches any of the event's topics, else **0**.
2. `past_event_topic_overlap` — "went to similar events before" (action): count past events that share **≥1 topic** with the new event → **0 related = 0, 1 related = 0.5, ≥2 related = 1**.

**Current implementation** (`python/smartmatch_domain/smartmatch_domain/student_factors/factors.py`):

- `stated_interest_overlap` returns `jaccard(card.normalized_interests, event.normalized_topics)` — fractional (e.g., 1 shared of 3 distinct terms → 0.3333); `None` when no card.
- `past_event_topic_overlap` returns `jaccard(union of all attended events' topics, event topics)`; `None` when `attended_event_topics is None` **or** when zero events attended.

**Not in conflict:** `same_major`, `career_goal_fit`, equal 0.25 weights, composition (unknown contributes nothing, no re-spread), tie-break, reason lines, markers — all stay.

### Decision points for the orchestrator (defaults recommended, confirm with Chau)

- **D1 — zero attendance:** `past_event_keys` is `NOT NULL` default `[]`, so production always sends `attended_event_topics=()`. Keep `None` (unknown) for zero attended events — consistent with the requirements doc ("counts only for profiles that have that information") and ADR-0011; composite is numerically identical either way since unknown and measured-0 both contribute nothing. `None`-record stays unknown regardless.
- **D2 — keep factor keys** `stated_interest_overlap` / `past_event_topic_overlap` unchanged: they are API query-param names, saved-settings DB keys, and frontend label keys; labels ("said they are interested…", "went to similar events before") remain accurate.
- **D3 — versioning:** bump `EXERCISE_REGISTRY_VERSION` `exercise-0.1.0` → `exercise-0.2.0` (rulebook contents changed; approver = Chau's refined rule, dated 2026-10-02) and `EXERCISE_STAGE_B_FORMULA_VERSION` → `1.1.0-exercise`. Update `tests/golden` pin of `"exercise-0.1.0"`.
- **D4 — deferred STUDENT_REGISTRY:** docs (ADR-0024/design spec) describe the future student track as Jaccard-based; changing the shared `student_factors` functions changes what that track inherits. Acceptable — flag it in the decision record.

---

## THE HANDOFF — paste everything below into Claude

```markdown
# Orchestration task: fix two class-exercise matching factors

Repo root: `IA-Smart-Match-Revamped` (Python domain + FastAPI + React). Work on the
current branch. Do NOT merge; produce one PR-sized change set. Python tests run with
`pytest` from repo root; the domain package lives in `python/smartmatch_domain/smartmatch_domain/`.

## Goal

Two of the four shared student factors must change formula. Keys, labels, weights,
composition, tie-break, markers, and reason sentences do NOT change.

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
  - Bump `EXERCISE_REGISTRY_VERSION` to `"exercise-0.2.0"`; update
    `EXERCISE_APPROVER`/`EXERCISE_APPROVED_ON` to record Chau's refined scoring
    rule dated 2026-10-02 (check repo conventions for the exact wording style).
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
- `tests/unit/test_exercise_matching.py` — audit composite expectations;
  `_full_card` stays 1.0; check any case assuming fractional overlap.
- `tests/golden/exercise/test_exercise_matching_golden.py`
  - G-CE-06: card `("analytics","sports")` vs topics `{analytics,careers}` now
    scores interest `1.0` → expected composite `0.25 + 0.25 = 0.5`, not
    `0.25 + 0.25*0.3333`.
  - Recompute every FACTOR_CASES entry and every ranked-order golden;
    update the `registry_version == "exercise-0.1.0"` pin to `"exercise-0.2.0"`.
- `tests/integration/exercise_class_driver.py` and any `tests/golden/exercise/`
  ranked-list fixtures: recompute expected orders under the new factor values
  (any-overlap → 1.0 boosts interest-matching carded profiles; related-count
  buckets change partial-attendance scores).
- `tests/unit/test_exercise_event_interest_fit_csv.py` — update the docstring:
  after this change the CSV's binary rule IS the app's rule for carded profiles
  (no-card stays unknown, not 0 — keep noting that difference).

### Data tooling + docs (Agent C — parallel with B)
- Move `compute_event_interest_fit.ps1` (currently at the workspace root beside
  the repo) into `tools/` and `event_interest_fit.csv` into `test_data/`,
  mirroring the committed `tools/compute_event_major_fit.ps1` +
  `test_data/event_major_fit.csv` pair. Fix the CSV output path in the script
  to match the major-fit precedent's location. The test at
  `tests/unit/test_exercise_event_interest_fit_csv.py` expects exactly these paths.
- `docs/superpowers/specs/2026-09-16-class-exercise-design.md` §4.2 table:
  replace the Jaccard rows with the binary and related-count rules.
- `docs/architecture/decisions/ADR-0025-*.md` factor table (~line 80): update
  the `stated_interest_overlap`/`past_event_topic_overlap` descriptions.
- `docs/product/class-exercise-requirements.md` "Matching" row (~line 199):
  update the parenthetical for "went to similar events before" to the
  related-event count rule if the current wording implies union-overlap.
- Add a short decision record under `docs/decisions/` (match existing naming)
  recording: binary interest fit replaces Jaccard; related-past-event count
  (0/0.5/1) replaces Jaccard-of-union; approver Chau, 2026-10-02; note D4 —
  the deferred STUDENT_REGISTRY track inherits these formulas.
- Optional: a `compute_event_related_past_fit.ps1` + CSV + drift-guard test in
  the same pattern, if Chau wants the second factor also CSV-verified.

### API/surface audit (Agent D — parallel, mostly verification)
- Confirm no contract change: weight query params in
  `services/api/smartmatch_api/routers/exercise_matching.py` and
  `exercise_matching_weights.py` key on factor keys — unchanged.
- Frontend `apps/web/legacy-frontend` uses label keys only — unchanged; check
  `RankedList.tsx` ~line 276 comment for stale Jaccard wording.
- `exercise/simulation.py` MUST NOT CHANGE: it is the hidden-truth results rule
  (`past_event_count >= 1` threshold, hidden true interests), a separate
  requirement, not a matching factor.
- `student_factors/terms.py`: `jaccard` may become unused by factors; keep it
  exported (shared vocabulary) or remove per repo lint conventions — check
  whether anything still imports it.

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
- `pytest tests/unit/test_exercise_event_interest_fit_csv.py` (after CSV/PS1 are moved into `test_data/`/`tools/`)
- `pytest tests/unit tests/golden tests/integration` — full sweep for ranking fallout

## Risks
- The registry-version bump re-labels new scores; any stored exercise runs pinned to `exercise-0.1.0` become non-reproducible (acceptable pre-class, flag to Chau if the DB already holds runs).
- Rankings will visibly shift (partial Jaccard credit disappears; binary 1.0 rewards any single interest match) — expected, but worth a spot-check on Ann's P004 case and the full 300-profile dataset before class.
