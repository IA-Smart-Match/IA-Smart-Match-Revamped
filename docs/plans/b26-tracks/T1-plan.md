# B26 T1 — availability verdict, `reason`, limits (domain only)

**Next action:** write `tests/unit/test_speaker_availability.py` (§3) and commit it red.

Parent: `docs/plans/2026-09-22-b26-self-service-availability-plan.md` §3.1, §3.4, §5.1, §7 row 1, §8 row T1.
Branch `feat/b26-t1`. Pure domain: no DB, no API, no registry change.

## 1. Files

| Path | Change |
|---|---|
| `python/smartmatch_domain/smartmatch_domain/eligibility.py` | `AvailabilityEvidence` (`:70-85`) gains `reason: AvailabilityReason \| None = None` as its **third** field (existing positional calls in `tests/unit/test_eligibility.py:24-131` keep working). `__post_init__` checks reason/state consistency. **`AvailabilityReason` is defined here** and added to `__all__`. `apply_availability_filter` (`:110-178`) unchanged. |
| `python/smartmatch_domain/smartmatch_domain/speaker_availability.py` | **New.** Re-exports `AvailabilityReason` from `eligibility.py`. Types, limits, `validate_availability_statement`, `event_local_span`, `availability_state_for_event`. |
| `tests/unit/test_speaker_availability.py` | **New.** §3 list. |
| `tests/unit/test_eligibility.py` | Add 3 tests for the new `reason` field only. |
| `docs/architecture/GLOSSARY.md`, `docs/architecture/domain-model.md:18` | Docs commit: "Availability statement" entry; add `availability_state_for_event` to the pure-functions row. |
| `docs/plans/2026-09-22-b26-self-service-availability-plan.md` §4.1 | **Done in this plan's commit** (orchestrator ruling): `capacity_invalid` → "≤ 0, > 720, not finite, or more than 1 decimal place"; `window_invalid` → "Order, span, horizon, or duplicate". |

Where things live today:

- `AvailabilityState` `AVAILABLE`/`BLACKED_OUT`/`UNKNOWN` — `eligibility.py:50-55`.
- `EligibilityOutcome` `ELIGIBLE`/`EXCLUDED`/`UNDETERMINED` — `eligibility.py:58-67`.
- `EligibilityDecision.reason` (free text, already exists) — `eligibility.py:88-107`.
- `TimePrecision`, `ExactTime(starts_at, time_zone, ends_at=None)`, `DateOnlyTime(on_date, time_zone)`, `UnresolvedTime`, `resolved_date` — `events.py:202-366`.
- DB shape: `ck_event_temporal_shape` and `ck_event_end_after_start` — `schema.py:1167-1190` (`ends_at` only at `exact`).
- Registry row `availability`, `ELIGIBILITY`, weight 0 — `factor_registry.py:380-394`; `REGISTRY_VERSION` `:154`. Not touched.

## 2. Contracts

```python
# eligibility.py (in __all__); re-exported by speaker_availability.py
class AvailabilityReason(StrEnum):
    CLEAR = "clear"  # AVAILABLE: row exists, nothing blocks
    PAUSED = "paused"  # BLACKED_OUT: invitations_paused_until >= as_of
    WINDOW = "window"  # BLACKED_OUT: a window overlaps an event date
    NOT_STATED = "not_stated"  # UNKNOWN: no speaker_availability row
    EVENT_UNRESOLVED = "event_unresolved"  # UNKNOWN: event has no local date


# speaker_availability.py
@dataclass(frozen=True, slots=True)
class UnavailableWindow:
    starts_on: date  # inclusive
    ends_on: date  # inclusive


@dataclass(frozen=True, slots=True)
class AvailabilityStatement:  # one speaker_availability row + its windows
    invitations_paused_until: date | None
    declared_capacity_hours_per_90_days: Decimal | None  # numeric(5,1); None = not stated
    unavailable: tuple[UnavailableWindow, ...] = ()
    # __post_init__: capacity is None or an instance of Decimal; anything else
    # (int, float, bool) -> TypeError. Range/finite/decimals are validation (below).


@dataclass(frozen=True, slots=True)
class AvailabilityAssessment:
    state: AvailabilityState
    reason: AvailabilityReason

    def to_evidence(self, subject_id: str) -> AvailabilityEvidence: ...


EventDateSpan: TypeAlias = tuple[date, date]  # (first, last) local dates, both inclusive


def event_local_span(event_time: EventTime) -> EventDateSpan | None: ...
def availability_state_for_event(
    statement: AvailabilityStatement | None,  # None = no row
    event_span: EventDateSpan | None,  # None = unresolved
    as_of: date,  # run or compose date, chosen by the caller (T4)
) -> AvailabilityAssessment: ...
```

**Why a span, not a date list:** an event's dates are always contiguous, so `(first, last)` holds any length in constant size; a 5-year exact event would otherwise be ~1,800 dates. Chosen form: a plain 2-tuple alias (not a dataclass), so the function itself validates it at step 0 and test 14 can pass malformed values.

Dependency direction: `speaker_availability.py` → `eligibility.py`, and `eligibility.py` imports nothing new. No cycle. Allowed pairs, enforced in `AvailabilityEvidence.__post_init__`: `AVAILABLE`↔`CLEAR`; `BLACKED_OUT`↔`PAUSED|WINDOW`; `UNKNOWN`↔`NOT_STATED|EVENT_UNRESOLVED`. `reason=None` stays legal (back-compat).

**Verdict order** (parent §5.1 order; first match wins):

0. Argument check, before any shortcut, even when `statement is None`: `event_span` must be `None` or a 2-tuple of `date` (a `datetime` is refused) with `first <= last`; otherwise `ValueError`. `()`, a 1- or 3-tuple, and `first > last` are all malformed.
1. `statement is None` → `UNKNOWN / NOT_STATED`.
2. `event_span is None` → `UNKNOWN / EVENT_UNRESOLVED` (wins over an active pause, §6 C1).
3. `invitations_paused_until is not None and invitations_paused_until >= as_of` → `BLACKED_OUT / PAUSED`.
4. Any window with `w.starts_on <= last and w.ends_on >= first` (interval overlap, inclusive) → `BLACKED_OUT / WINDOW`.
5. Otherwise → `AVAILABLE / CLEAR` (includes a row with no windows and no pause).

`apply_availability_filter` then maps state → outcome exactly as today.

**Event local span** (`event_local_span`), the only place dates are derived:

- `DateOnlyTime` → `(on_date, on_date)`. No end exists at this precision.
- `ExactTime`, no `ends_at` → `(d, d)` with `d = resolved_date(t)` — start date in the event's own zone.
- `ExactTime` with `ends_at` → `(resolved_date(t), (ends_at.astimezone(UTC) - timedelta(microseconds=1)).astimezone(ZoneInfo(time_zone)).date())`. The end is exclusive; no midnight special case. Subtract in UTC: on a `ZoneInfo` datetime Python does wall-clock arithmetic, which gives a different date across a DST transition at local midnight (Santiago, Havana). The span is therefore the same whether `ends_at` is supplied as UTC, a `ZoneInfo` datetime or a fixed offset (tests 20a-20c plus the zone-representation tests). `ExactTime` requires `ends_at > starts_at`, so `first <= last` always holds.
- `UnresolvedTime` → `None`.

**Limits** (constants, `Final`):

| Constant | Value | Rule |
|---|---|---|
| `MAX_WINDOWS` | 20 | `len(unavailable) <= 20` |
| `WINDOW_MAX_SPAN_DAYS` | 366 | `(ends_on - starts_on).days <= 366` — same as the T2 CHECK |
| `WINDOW_HORIZON_MONTHS` | 18 | `ends_on <= add_months(today, 18)` |
| `PAUSE_HORIZON_MONTHS` | 12 | `today <= paused_until <= add_months(today, 12)` |
| `CAPACITY_MIN_EXCLUSIVE` / `CAPACITY_MAX` | 0 / 720 | `capacity.is_finite()` and `0 < capacity <= 720` and `capacity == capacity.quantize(Decimal("0.1"))` (§6 C3). NaN, sNaN, ±Infinity rejected — check `is_finite()` first, so no comparison ever touches a NaN (sNaN comparison raises `InvalidOperation`). |

`add_months` clamps the day with `calendar.monthrange(year, month)[1]` (2026-08-31 + 18 months = 2028-02-29; 2027-08-31 + 18 = 2029-02-28; 2028-02-29 + 12 = 2029-02-28). Past windows are allowed (a PATCH resends the full list).

**Validation:** `validate_availability_statement(statement: AvailabilityStatement, today: date) -> None`,
raises `AvailabilityStatementInvalid(code: AvailabilityErrorCode, field: str, index: int | None)`.
Checks run in a fixed order; the first failure raises. T3 maps `code` 1:1 onto §4.1 (all 422):

| Order | `AvailabilityErrorCode` | §4.1 code | `field` |
|---|---|---|---|
| 1 | `CAPACITY_INVALID` | `speaker_availability_capacity_invalid` | `declared_capacity_hours_per_90_days` |
| 2 | `PAUSE_INVALID` (past or > 12 months) | `speaker_availability_pause_invalid` | `invitations_paused_until` |
| 3 | `TOO_MANY_WINDOWS` (> 20) | `speaker_availability_too_many_windows` | `unavailable` |
| 4 | `WINDOW_INVALID` (order, span, horizon, duplicate) | `speaker_availability_window_invalid` | `unavailable`, `index` set; for a duplicate, the **later** index |

`TypeError` for a non-`Decimal` capacity is raised at `AvailabilityStatement` construction, not mapped to a 422 code.

**Hand-off notes**

- **T3:** parse the JSON capacity with `Decimal(str(v))` before building `AvailabilityStatement` (a float or int passed straight in raises `TypeError`).
- **T3/T5:** an expired pause (`invitations_paused_until < today`) that a PATCH resends unchanged is **dropped by the API** (stored as `NULL`), not rejected with `pause_invalid`. T3 owns that rule; T1's validator still rejects a past pause.

## 3. TDD list — `tests/unit/test_speaker_availability.py`

Verdict (§5.1 rows):
1. `test_no_row_is_unknown_not_stated`
2. `test_no_row_with_unresolved_event_is_still_not_stated`
3. `test_unresolved_event_is_unknown_event_unresolved`
4. `test_pause_until_after_as_of_is_blacked_out_paused`
5. `test_pause_until_equal_as_of_is_blacked_out_paused` (inclusive edge)
6. `test_pause_until_day_before_as_of_is_not_paused` (asserts exactly `AVAILABLE / CLEAR`)
7. `test_unresolved_event_wins_over_active_pause` (§6 C1: `UNKNOWN / EVENT_UNRESOLVED`)
8. `test_pause_wins_over_window_reason`
9. `test_window_overlapping_event_date_is_blacked_out_window`
10. `test_window_starting_on_event_date_blocks` / `test_window_ending_on_event_date_blocks`
11. `test_window_ending_day_before_event_does_not_block` / `test_window_starting_day_after_event_does_not_block` (both assert exactly `AVAILABLE / CLEAR`)
12. `test_row_with_no_windows_and_no_pause_is_available_clear`
13. `test_non_overlapping_windows_only_is_available_clear`
14. `test_inverted_span_with_no_statement_raises_value_error` / `test_inverted_span_with_active_pause_raises_value_error` / `test_inverted_span_with_ordinary_statement_raises_value_error` (`first > last`)
14a. `test_malformed_span_raises_value_error`, parametrized over `()`, a 1-tuple, a 3-tuple, and a `(datetime, datetime)` pair, each with no statement
15. `test_verdict_maps_through_apply_availability_filter` (AVAILABLE→ELIGIBLE, BLACKED_OUT→EXCLUDED, UNKNOWN→UNDETERMINED)
16. `test_capacity_does_not_affect_verdict`

Event span / multi-day / DST:
17. `test_date_only_event_yields_on_date` → `(on_date, on_date)`
18. `test_exact_event_without_end_yields_local_start_date` (`2026-09-15T06:30Z` LA → `(14th, 14th)`)
19. `test_exact_event_across_local_midnight_yields_two_dates`
20. `test_exact_event_ending_at_local_midnight_excludes_next_day`
20a. `test_exact_event_ending_at_skipped_midnight_excludes_next_day`: `America/Santiago`, `2026-09-05T23:00-04:00` → `2026-09-06T04:00Z` gives `(2026-09-05, 2026-09-05)`
20b. `test_exact_event_across_fall_back_yields_two_dates`: LA, `2026-10-31T22:00-07:00` → `2026-11-01T02:00-08:00` gives `(2026-10-31, 2026-11-01)`
20c. `test_exact_event_across_spring_forward_yields_local_dates`: LA, `2026-03-07T22:00-08:00` → `2026-03-08T03:30-07:00` gives `(2026-03-07, 2026-03-08)`
21. `test_three_day_event_blocked_by_window_on_middle_day_only`
21a. `test_long_exact_event_overlap_is_interval_based`: a 5-year exact event, one window in year 3 → `BLACKED_OUT / WINDOW`
22. `test_multi_day_event_uses_event_zone_not_utc` (`Asia/Tokyo`)
23. `test_unresolved_event_yields_none`

Limits:
24. `test_twenty_windows_valid` / `test_twenty_one_windows_too_many`
25. `test_window_end_before_start_invalid` / `test_single_day_window_valid`
26. `test_window_span_366_valid` / `test_window_span_367_invalid`
27. `test_window_end_at_18_months_valid` / `test_window_end_day_after_18_months_invalid`
28. `test_18_month_horizon_clamps_month_end`, parametrized: 2026-08-31 → 2028-02-29; 2027-08-31 → 2029-02-28
28a. `test_12_month_pause_horizon_clamps_leap_day`: today 2028-02-29 → a pause of 2029-02-28 is valid, 2029-03-01 invalid
29. `test_duplicate_window_invalid_reports_later_index` (windows 0 and 3 identical → `index == 3`)
30. `test_past_window_valid`
31. `test_pause_today_valid` / `test_pause_yesterday_invalid`
32. `test_pause_at_12_months_valid` / `test_pause_day_after_12_months_invalid`
33. `test_capacity_zero_invalid` / `test_capacity_negative_invalid` / `test_capacity_0_1_valid`
34. `test_capacity_720_valid` / `test_capacity_720_1_invalid`
34a. `test_capacity_trailing_zero_decimals_valid` (`Decimal("24.00")` accepted) / `test_capacity_two_significant_decimals_invalid` (`Decimal("24.05")` rejected)
34b. `test_capacity_not_finite_invalid`, parametrized over `Decimal("NaN")`, `Decimal("sNaN")`, `Decimal("Infinity")`, `Decimal("-Infinity")` → `CAPACITY_INVALID`, no `InvalidOperation` escapes
34c. `test_capacity_non_decimal_raises_type_error`, parametrized over `24`, `24.0`, `True` (raised at `AvailabilityStatement` construction)
35. `test_capacity_none_and_pause_none_valid`
36. `test_first_failure_order_capacity_before_pause_before_windows`
37. `test_error_code_values_match_api_codes` (string values pinned)

Types: 38. `test_types_are_frozen`.
39. `test_to_evidence_carries_state_and_reason`, parametrized over all 5 pairs (`AVAILABLE/CLEAR`, `BLACKED_OUT/PAUSED`, `BLACKED_OUT/WINDOW`, `UNKNOWN/NOT_STATED`, `UNKNOWN/EVENT_UNRESOLVED`).
40. `test_to_evidence_rejects_blank_subject`, parametrized over `""` and `"   "` → `ValueError` (the `eligibility.py:83-85` rule). In `tests/unit/test_eligibility.py`: `test_evidence_reason_defaults_to_none`, `test_evidence_rejects_mismatched_reason`, `test_positional_evidence_still_constructs`.

Run: `$VENV/bin/python -m pytest tests/unit/test_speaker_availability.py -q`, then `tests/unit/test_eligibility.py`, one at a time. Plus `ruff check`, `ruff format --check`, `mypy` on the two source files, and `lint-imports`.

## 4. Commit milestones

1. `test: failing T1 availability verdict and limit tests` — both test files, red (ImportError is an acceptable red).
2. `feat: availability verdict, reason and limits in the domain` — `speaker_availability.py` + `eligibility.py`; both files green.
3. `docs: availability statement in glossary and domain model` — GLOSSARY + domain-model.

## 5. Out of scope

- No migration, table, repository or mirror (T2). No route, OpenAPI or `api.ts` (T3).
- No wiring into `create_match_run`, compose or dispatch (T4). `as_of` zone choice belongs to T4.
- No change to `factor_registry.py`: `REGISTRY_VERSION`, `registry_hash`, `inputs_fingerprint` unchanged.
- No change to `eli.py` (`CapDecision.BLACKED_OUT`, `LoadModifier`, the `40.0` default are T8b, §5.2). T1 does not use capacity in the verdict; it only validates the number.
- No change to `apply_availability_filter` output or its reason strings.

## 6. Contradictions and choices

| # | Issue | Options | Chosen here |
|---|---|---|---|
| C1 | §5.1 table lists "Event `unresolved`" above the pause row, while the pause compares with `as_of`, not the event date (§3.1). | (a) table order: unresolved → `UNDETERMINED` even when paused; (b) pause first. | **(a)**, orchestrator ruling: follow parent §5.1 order. Test 7 pins it. |
| C2 | §4.1 lists window failures as "order, span or horizon" only; T2's `uq_speaker_availability_window_range` would reject a duplicate as a DB error. | (a) map duplicate to `window_invalid`; (b) new code. | **(a)**, no new API code; parent §4.1 row updated. |
| C3 | `numeric(5,1)` silently rounds `24.05` to `24.1`; `Decimal` also admits NaN/sNaN/±Infinity. | (a) reject as `capacity_invalid`; (b) round. | **(a)**, orchestrator ruling: finite and `value == value.quantize(Decimal("0.1"))`; parent §4.1 row updated. |
| C5 | §5.1 says `event_dates`; a date list is unbounded. | (a) list; (b) `(first, last)` span. | **(b)**, reviewer ruling: interval overlap. |
| C4 | §5.1 names the function but not its return; `AvailabilityEvidence` needs a `subject_id` the function does not take. | Return `AvailabilityAssessment(state, reason)` + `to_evidence(subject_id)`. | As stated. |

---

**Next action (under two minutes):** create `tests/unit/test_speaker_availability.py` with tests 1–5.
