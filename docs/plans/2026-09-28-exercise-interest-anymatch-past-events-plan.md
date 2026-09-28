# Plan: any-match interest and related-event count (OQ-CE-17)

**Verdict:** two formula swaps in one shared file, a rulebook version bump, and
re-pinned goldens. About 1 working day, no migration, no API shape change.
Ranks move (22 of 30 names stay on each default list); every reason line on
both default top-30 lists becomes a tie line.

**Status:** plan only. Nothing here is built. Jaccard stays in force until
track T1 merges.
**Date:** 2026-09-28.
**Source:** Dr. Wang's reply to Chau, 2026-09-28 —
[`../decisions/stakeholder-correspondence-2026-09.md` §D](../decisions/stakeholder-correspondence-2026-09.md#d-chau-and-dr-wang-how-two-factors-score).
**Register row:** OQ-CE-17 in
[`open-questions/class-exercise-open-questions.md`](open-questions/class-exercise-open-questions.md).
**Rule owner:** Chau ("Chau (matching and results)", requirements §"Who does
what"). Chau decides the rules; Danny builds the machinery.

Paths below are shortened:

- `domain/` = `python/smartmatch_domain/smartmatch_domain/`
- `api/` = `services/api/smartmatch_api/routers/`
- `web/` = `apps/web/legacy-frontend/src/app/pages/exercise/`

---

## 1. What is built today

| What | Where | Today's rule |
|---|---|---|
| "said they are interested in this topic" | `domain/student_factors/factors.py:127-154` (`stated_interest_overlap`) | `jaccard(card interests, event topics)` at `:146`; `None` with no card (`:139-144`); an empty card is a measured `0.0` |
| "went to similar events before" | `domain/student_factors/factors.py:206-242` (`past_event_topic_overlap`) | `jaccard(union of all attended events' topics, event topics)` at `:234`; `None` when no event was attended (`:222-233`) |
| Jaccard itself | `domain/student_factors/terms.py:44-63` (`jaccard`); re-exported at `domain/student_factors/__init__.py:42`, `:55` | Size of A ∩ B over size of A ∪ B; `0.0` on an empty union |
| Union of past topics | `domain/student_factors/evidence.py:154-162` (`normalized_attended_topics`) | Flattens every attended event into one set, so the per-event count is lost here but kept on `attended_event_topics` (`:125`, one tuple per event) |
| Composition | `domain/exercise/matching.py:218-239` | Weighted sum; unknown adds nothing and its weight is not re-spread |
| Rulebook | `domain/exercise/registry.py:105` `EXERCISE_REGISTRY_VERSION = "exercise-0.1.0"`; labels `:141-148`; rationale `:173-192`; approver `:113` | Composition version `domain/exercise/matching.py:110` `"1.0.0-exercise"` |
| Reason lines | `domain/exercise/reasons.py:197-239`; "contributes" = known, above zero, weight above zero (`matching.py:400-415`) | A factor at 0.5 or 1 is named with the same label. "Nothing else on file" is the marker `MAJOR_ONLY` (`reasons.py:235-236`), not a factor value |
| Undecided half (OQ-CE-14) | `domain/student_factors/factors.py:81`, `:177-186`; flag `matching.py:418-430`; label `registry.py:155-160` | The pattern a "one related event" label would copy |

The shared module is shared on purpose: ADR-0025 D3 ("One student-factor
module, two registries") maps `stated_interest_overlap` to ADR-0024's
`student_interest_overlap` "(Jaccard over the G3 vocabulary)". No
`STUDENT_REGISTRY` exists in code today; the exercise is the only caller.

## 2. New definitions

### 2.1 "said they are interested in this topic" (intention)

```
value = None  if no card
        1.0   if normalized(card interests) ∩ normalized(event topics) ≠ ∅
        0.0   otherwise
```

### 2.2 "went to similar events before" (action)

```
related = number of attended events e with normalized(topics(e)) ∩ normalized(event topics) ≠ ∅
value   = None  if no event attended (no record, or an empty record)
          0.0   if related == 0
          0.5   if related == 1
          1.0   if related >= 2
```

Named constants, not literals: `ONE_RELATED_PAST_EVENT_FIT = 0.5`,
`RELATED_PAST_EVENTS_FOR_FULL_FIT = 2` in `domain/student_factors/factors.py`.
The count reads `ProfileEvidence.attended_event_topics` per event, **not**
`normalized_attended_topics` (which unions them).

### 2.3 Edge cases

| Case | Interest | Past events | Why |
|---|---|---|---|
| No card | `None` (unknown) | — | Unchanged. ADR-0011: unknown is never `0` |
| Card with no interests | `0.0` measured | — | Unchanged three-state rule (`evidence.py:18-26`) |
| No attendance, or a record naming no event | — | `None` (unknown) | Unchanged (`factors.py:224`) |
| Event with no topics | `0.0` | `0.0` if attended ≥ 1 | Nothing can be related to no topic |
| Past event key the file does not carry | — | Counts as attended, never related | `api/exercise_matching_models.py:278` maps it to `()` |
| Duplicate topics on either side | No effect | No effect | `normalized_terms` folds case and duplicates (`terms.py:32-41`); an event counts once however many topics it shares |
| Two different past events with the same topics | — | Count as two | They are two events |
| Same event attended twice (`E01;E01`) | — | Counts once | Ingest folds it: `domain/exercise/ingest.py:443-446`. Ann's word is "count of related past **events**". Confirm on Teams (Q2) |
| An exercise event (E11/E12) in the past list | — | Impossible | Ingest refuses it: `ingest.py:561-584` |
| Round-two refresh (Northline attendees) | — | Northline counts as **one** attended event | The refresh writes Northline's topics once to `added_event_topics` (`python/smartmatch_persistence/smartmatch_persistence/exercise/results_repository.py:589`), claimed once per team (`refreshed_at IS NULL`, same method); `api/exercise_matching_models.py:279-280` appends it as one entry. The count reads it with no change |
| Round two is Harbor | — | Northline is **never related** to Harbor | E11 topics `Technology / information systems`; E12 topics `Retail / consumer goods`, `Supply chain / logistics / operation`; no shared topic. The refresh still moves Northline attendees from "major only" to "major plus events" (tie-break rank), as today |
| Undecided half (OQ-CE-14) | Unaffected | Unaffected | It lives on `career_goal_fit`. `_goal_fit_is_undecided_half` (`matching.py:418-430`) reads only that key, so a past-event 0.5 cannot trip it |
| Hidden true interests | Never read | Never read | ADR-0025 D6; `tests/unit/test_student_factors.py` walks the source |

### 2.4 Reason lines (plain words, no numbers — ADR-0025 D8)

| Value | Interest | Past events |
|---|---|---|
| 0 | Not named (did not count) | Not named |
| 0.5 | — | **Proposed:** "went to a similar event before". Safe default: Ann's label, unchanged |
| 1 | "said they are interested in this topic" | "went to similar events before" |

Example sentences, through `phrase_as_sentence`:

- 1 related: "What counted: same major and went to a similar event before."
- 2+ related: "What counted: same major and went to similar events before."
- Nothing counted, card or events on file: "Nothing on file matches this
  event." (unchanged, `reasons.py:123`)
- Major only: "Same major; nothing else on file." (unchanged)

Why propose a singular label: this codebase already refuses a label that is
false for the name beside it ("career goal fits" is not said of an Undecided
card, `registry.py:150-155`). On Northline and Harbor every contributing
profile has exactly **one** related event (§4), so the plural would always be
the one printed. Needs Ann's words (Q4) before it ships.

## 3. Blast radius

### 3.1 Must change with the code (T1)

| # | What | Where | Change |
|---|---|---|---|
| 1 | Formulas | `domain/student_factors/factors.py:127-154`, `:206-242`; module table `:10-15` | §2.1, §2.2 |
| 2 | Rulebook version | `domain/exercise/registry.py:105` | `exercise-0.1.0` → `exercise-0.2.0`; approver `:113` adds "and Dr. Wang's reply to Chau, 2026-09-28"; rationale `:179-190` rewritten. `EXERCISE_STAGE_B_FORMULA_VERSION` (`matching.py:110`) **stays**: the composition is unchanged |
| 3 | Version pins | `tests/unit/test_exercise_registry.py:115`; `tests/unit/test_exercise_registry_isolation.py:28`; `tests/golden/exercise/test_exercise_matching_golden.py:130` | New string |
| 4 | Factor goldens | `tests/golden/exercise/test_exercise_matching_golden.py:79-111` | G-CE-03 `1.0` → `0.875` (one related event is 0.5); G-CE-05 `0.5` → `0.375`; G-CE-06 `0.3333…` → `0.5` |
| 5 | Factor unit tests | `tests/unit/test_student_factors.py:89` (Jaccard index → 1.0), `:201` (union → two related events → 1.0), `:226` (`jaccard` has no caller left) | Rewrite; add cases for 0/1/2/3 related, empty card, event with no topics, unknown past key |
| 6 | Ann-file golden | `tests/golden/exercise/test_exercise_ann_dataset_golden.py:331-354` | P197 moves from 30th to 15th on Northline and its line becomes "Tied; placed in a fixed order that never changes." The test's point (an Undecided card is never told its goal fits) needs a weighting where a "What counted" line shows |

**Saved settings and result runs store no version.** `exercise_saved_setting`
holds `weights` JSONB keyed by factor key
(`python/smartmatch_persistence/smartmatch_persistence/exercise/schema.py:354-371`);
`exercise_result_run` holds the invited/signed-up/attended profile numbers
(`schema.py:397-423`). No migration. Consequences:

- A saved setting re-ranks under the new rule the next time it is opened.
- A result run already recorded keeps its lists; round two shows round one as
  run.
- **Keep the factor keys.** Renaming `stated_interest_overlap` would orphan every
  saved setting's weights, the weight query parameters
  (`api/exercise_matching.py:362`, `:442`), and the frontend key list
  (`apps/web/legacy-frontend/src/lib/exerciseClient.ts:146-148`). The keys are
  never shown; the labels are.

### 3.2 P004 (OQ-CE-15, decision record D9)

Any-match does **not** change the "not above when turned off" half. Measured
on Ann's full file, Northline (E11):

| Weighting | P004 old | P004 new | Plain Accounting P231 / P257 |
|---|---|---|---|
| Equal defaults | 5 | 4 | 295 / 161 (both) |
| Interest up (1.0, others 0.25) | 4 | 4 | 295 / 161 |
| Interest off | 6 | 6 | 295 / 161 |
| Interest and goal off | 58 | 58 | 295 / 161 |

On the 20-profile sample the four P004 goldens (`:161`, `:170`, `:178`, `:188`)
give identical ranks old and new (1, 2, 4 against 17 and 20). D9's "4th to
6th" still holds. On Harbor, P004 jumps from 86th to 25th at equal weights:
one of its interests is a Harbor topic, and any-match no longer divides that by
the size of its card.

### 3.3 The results rule (`domain/exercise/simulation.py`)

Not an assumption either way — **question Q1 for Ann.** What it does today:

- True interests are **already any-match**: `simulation.py:535`
  `if topics & {true interests}` earns the interest share.
- Past events are **any past event, related or not**: `simulation.py:551`
  `past_event_count >= frequent_attender_events` (1) adds the attender lift
  ("some", +0.10, D7).
- `past_event_count` is `len(row.past_event_keys)`
  (`api/exercise_results_models.py:202`), so the round-two refresh's Northline
  attendance is **not** counted by the results rule today. Separate from this
  change; flagged so nobody "fixes" it by accident.

If Ann says the rule follows, the attender lift becomes related-count graded
(0 / half / full lift) and D7's numbers plus
`tests/golden/exercise/test_exercise_simulation_golden.py` and
`test_exercise_results_rule_sample_golden.py` move. That is track T4, gated.

### 3.4 The tie-break: binary scores make more ties

| | Northline old | Northline new | Harbor old | Harbor new |
|---|---|---|---|---|
| Distinct composite values over 300 | 16 | 6 | 17 | 6 |
| Value at the 30th place | 0.160725 | 0.25 | 0.25 | 0.25 |
| Profiles at that value | 1 | 27 | 64 | 71 |
| …of whom inside the top 30 | 1 | 19 | 16 | 13 |
| Top-30 lines "What counted: …" | 5 | **0** | 5 | **0** |
| Top-30 lines "Tied; placed in a fixed order…" | 22 | 21 | 20 | 23 |
| Top-30 lines "Tied on what counted; ordered by year." | 2 | 9 | 5 | 7 |

The last three rows are the cost. OQ-CE-12 lets a tie line win over every
other line (`reasons.py:118`), and at equal weights every name in both default
top-30 lists now ties with a neighbour. The requirement "a reason next to each
name" still holds; "what counted" disappears from the default lists. Teams see
it again as soon as they move a weight. Raised with Chau as an internal
question (Q-T2), not with Ann.

### 3.5 Frontend

- Labels come from the server's `factor_labels`
  (`api/exercise_matching_models.py:652-656`); `web/WeightsControls.tsx:5-7`
  and `web/RankedList.tsx:275-277` keep no copy. **No frontend change** unless
  the singular past-event label ships.
- If it ships (T3): a list-entry flag beside `undecided_goal_half`
  (`domain/exercise/matching.py:166`), a `factor_labels` entry beside
  `UNDECIDED_GOAL_HALF_LABEL_KEY` (`api/exercise_matching_models.py:656`), the
  swap in `web/RankedList.tsx:279-300` and its type in
  `apps/web/legacy-frontend/src/lib/exerciseClient.ts:79`, `:154-158`. Pattern
  and tests to copy: `web/RankedList.undecidedLabel.test.tsx`,
  `tests/unit/test_exercise_undecided_label.py`,
  `tests/unit/test_exercise_undecided_goal_flag.py`,
  `tests/unit/test_exercise_list_shape.py`.
- `web/ExerciseEventPicker.tsx:164` explains what "went to similar events
  before" reads; one sentence may need "an event counts when it shares a
  topic".

### 3.6 Docs

| Doc | Where | Change |
|---|---|---|
| Requirements | `docs/product/class-exercise-requirements.md:199` ("Matching" row), `:288-290` (Chau's item 1), "Changed since 15 September" `:405` | State both rules in plain words; add a dated change line |
| Design spec | `docs/superpowers/specs/2026-09-16-class-exercise-design.md:152`, `:154` (§4.2 table) | Replace "Jaccard" rows |
| ADR-0025 | `docs/architecture/decisions/ADR-0025-class-exercise-scope-shares-the-matching-mechanism.md:80` (D3 table) | Amendment note: the shared functions are any-match / related-count from 2026-09-28; ADR-0024's `student_interest_overlap` is no longer "the same function" unless its owner adopts it (owner question below) |
| Decision record | `docs/decisions/class-exercise-decisions-2026-09-25.md` | New D17 when OQ-CE-17 closes |
| DESIGN.md | `docs/design/class-exercise/DESIGN.md` §6.7 (`:441-458`) | Only with T3: the singular label, as the Undecided swap is described |
| Justin's plain-words write-up | Not written yet (correspondence row 7) | It covers the results rule, the three choices and the refresh, not matching. Changes only if Q1 is "yes". Tell Justin the matching rule changed so his Session 2 reveal does not contradict the list |
| Module docstrings | `domain/student_factors/factors.py:10-15`, `domain/student_factors/terms.py:1-14`, `domain/exercise/registry.py:173-192` | Match the code |

## 4. Before and after on Ann's 300

Read-only run of `tests/fixtures/exercise/SmartMatch_Student_Body_300.xlsx`
through the production path (`parse_exercise_file` → `rankable_set` →
`exercise_ranked_list`, as `tests/golden/exercise/test_exercise_ann_dataset_golden.py`
does), equal default weights, `tiebreak_order` from the file, invite limit 30,
with the two factor functions swapped for §2's formulas. The throwaway script
is not committed; T1 step 6 pins these numbers as a golden.

| | Northline (E11) | Harbor (E12) |
|---|---|---|
| **Top-30 overlap, old vs new** | **22 of 30** | **22 of 30** |
| Dropped | P002, P086, P127, P193, P211, P213, P241, P297 | P018, P033, P090, P118, P131, P169, P208, P264 |
| Added | P013, P132, P163, P169, P239, P249, P262, P265 | P004, P016, P098, P108, P122, P192, P268, P289 |
| Ties at the cutoff (value / at it / inside) | old 0.160725 / 1 / 1 → new 0.25 / 27 / 19 | old 0.25 / 64 / 16 → new 0.25 / 71 / 13 |
| P004 rank | 5 → 4 | 86 → 25 |
| P197 (Undecided card) rank | 30 → 15 | 82 → 89 |
| Top-30 composite groups, new | 0.75 ×2, 0.5 ×5, 0.375 ×4, 0.25 ×19 | 0.875 ×2, 0.5 ×6, 0.375 ×9, 0.25 ×13 |
| New interest values (300) | 1: 15, 0: 55, unknown: 230 | 1: 24, 0: 46, unknown: 230 |
| New past-event values (300) | 0.5: 16, 0: 84, unknown: 200 | 0.5: 11, 0: 89, unknown: 200 |

Three facts the numbers show:

1. **Who counts does not change; how much does.** Jaccard is above zero exactly
   when any-match is 1, and the union Jaccard is above zero exactly when at
   least one event is related. So every name's list of factors that counted is
   the same old and new; only the composite moves.
2. **Nobody reaches full credit for past events on either exercise event.**
   Related past events per profile, over the 100 who attended any: Northline
   0 → 84, 1 → 16; Harbor 0 → 89, 1 → 11. No one has 2. On the ten past
   events, E01, E02, E03, E06, E07 and E10 do have profiles with 2–4 related
   events, so the 1.0 branch is live data, not dead code. Q3 asks Ann whether
   half credit at most on both exercise events is what she wants.
3. **Cards hold 1–4 interests** (4: 34 cards, 3: 19, 2: 16, 1: 1). Under
   Jaccard a 4-interest card with one hit on a 1-topic event scored 0.25; now 1.

## 5. Implementation tracks

TDD throughout: write the failing test, run it red, implement, run green.
Run targeted test files one at a time on `/mnt/c`; CI runs the suite.

| Track | Owner | Hours | Gate | Merge order |
|---|---|---|---|---|
| T0 Send Q1–Q5 to Ann on Teams; approve §2 and §2.4 wording | Chau | 0.5 | none | first |
| T1 Formulas, version bump, goldens, docs | builder (Danny or an Opus agent), Chau reviews the rules | 5–6 | owner answer on the shared module (below) | PR 1 |
| T2 Reason precedence at equal weights (§3.4) | Chau decides; builder | 0–3 | Chau's call; may be "no change" | after PR 1, own PR |
| T3 Singular past-event label | builder | 4–5 (2 backend, 2–3 frontend incl. Vitest) | Ann's wording (Q4) | after PR 1, own PR |
| T4 Results rule follows | builder, Chau sets numbers | 3–4 | Ann says yes (Q1) | after PR 1, own PR |

### T1 steps (one PR)

1. **Red — factors.** In `tests/unit/test_student_factors.py`: any-match is
   1.0 for one hit among many interests; 0.0 for none; `None` with no card;
   0.0 for an empty card and for an event with no topics. Past events: 0, 1,
   2, 3 related → 0.0, 0.5, 1.0, 1.0; two events with identical topics count
   twice; an unknown past key counts as attended and unrelated; `None` with no
   attendance. Delete the two Jaccard tests (`:89`, `:201`).
2. **Green — factors.** Implement §2 in `domain/student_factors/factors.py`
   with the two named constants; delete `jaccard` from `terms.py` and
   `__init__.py` once nothing imports it, with its test (`:226`).
3. **Red/green — version.** Bump `EXERCISE_REGISTRY_VERSION` to
   `exercise-0.2.0`; update the three pins (§3.1 row 3), approver and
   rationale.
4. **Factor goldens.** G-CE-03 → 0.875, G-CE-05 → 0.375, G-CE-06 → 0.5; add
   G-CE-07 "two related past events" (1.0 on that factor).
5. **Ann-file golden.** Re-pin the P197 test (`:331-354`) to a weighting where
   the "What counted" line shows (e.g. `_GOAL_ONLY`), keeping its assertion
   that an Undecided card is never told its goal fits. Confirm the four P004
   tests pass unchanged.
6. **New golden** in `tests/golden/exercise/test_exercise_ann_dataset_golden.py`:
   pin §4's top-30 overlap sets, P004 ranks (E11 4 / 4 / 6 / 58), and "no
   profile has two related past events for E11 or E12", so a data change is
   loud.
7. **Docs** in the same PR: §3.6 rows for requirements, design spec, ADR-0025
   amendment note, module docstrings.
8. **Check:** `ruff`, `mypy`, and the six test files named in §3.1, one pytest
   at a time.

### T3 steps (if Q4 is yes)

1. Red: `tests/unit/test_exercise_reasons.py` — a past-event value of 0.5
   renders the singular label; 1.0 renders Ann's.
2. Green: `ONE_SIMILAR_EVENT_LABEL(_KEY)` in `domain/exercise/registry.py`
   beside `:155-160`; flag on `ExerciseListEntry` (`matching.py:143-166`);
   `reasons.py` `_factor_phrase` swap.
3. API: add the label to `_RESPONSE_FACTOR_LABELS`
   (`api/exercise_matching_models.py:656`) and the flag to the entry model;
   update `tests/unit/test_exercise_list_shape.py`.
4. Frontend: `exerciseClient.ts` type and key; `RankedList.tsx` swap; a
   `RankedList.oneSimilarEvent.test.tsx` beside the Undecided one. Run with
   `vitest run --pool=threads <file>`.
5. DESIGN.md §6.7 line.

## 6. Questions

### For Dr. Wang, on Teams (Chau sends)

1. **Does the results rule follow?** The simulated sign-ups already treat
   true interests as yes/no. For past events they give the "some" lift to
   anyone who attended any past event, related or not. Should that lift also
   count only related events, scored 0 / half / full like matching?
2. **Does attending the same event twice count as two?** The data file lists
   each event once per student, and we count it once. OK?
3. **Half credit at most on both exercise events.** In the 300, nobody has two
   past events related to Northline or Harbor (16 and 11 students have one).
   So "went to similar events before" can give at most half credit on both
   events. Is that what you want?
4. **Wording for one related event.** May the reason line say "went to a
   similar event before" when a student has one related event, and "went to
   similar events before" for two or more?
5. **Northline in round two.** Students who attended Northline pick up its
   topics. Northline and Harbor share no topic, so Northline never counts as
   "related" for Harbor. It still moves those students up the "how much we
   know" order. OK?

### For the owner (Danny) before T1

- **Change the shared functions in place, or add exercise-only ones?**
  Recommendation: in place. `STUDENT_REGISTRY` does not exist and OQ-SE-01/02
  are deferred, so the exercise is the only caller; two versions of one factor
  with no second caller is the drift ADR-0025 D3 was written to prevent. Cost:
  an amendment note on ADR-0025 D3 saying ADR-0024's `student_interest_overlap`
  is no longer Jaccard unless its owner re-decides.

### For Chau (internal, Q-T2)

- At equal weights every name on both default top-30 lists now gets a tie
  line, so "What counted" never shows on the default list (§3.4). Keep
  OQ-CE-12's precedence, or show what counted beside the tie?

## 7. Next action

Chau sends Q1–Q5 to Dr. Wang on Teams.
