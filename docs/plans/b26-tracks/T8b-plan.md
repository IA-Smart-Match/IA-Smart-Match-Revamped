# B26 T8b — `eli.py` 2.0.0: centered utilization, bands, no default capacity (domain only)

**Next action:** rewrite `tests/unit/test_eli.py` per §6 and commit it red.

Parent: `docs/plans/2026-09-22-b26-self-service-availability-plan.md` header (Q1/D2, Q6, Q7,
Unknown load), §1 fact 3 and the `date_only` fact, §5.2, §7 row 10, §8 T8b, §11 risks 3–4.
Branch `feat/b26-t8b`, cut from `main`. Pure domain: no DB read, no registry edit, no scoring
change (all T8c).

**Owner rulings (final, 2026-09-23; they override the parent where the two differ)**

| # | Ruling | Where applied |
|---|---|---|
| R1 (C1) | A confirmed, not-cancelled booking in the forward window counts as upcoming whether attended or not. A booking on `as_of` already marked attended is upcoming, not completed. | §3, §6 tests 7, 10 |
| R2 | Window is exactly 90 days: completed = event local date in `[as_of − 45, as_of)`; confirmed = `[as_of, as_of + 44]`. `as_of` = UTC date of run creation. | §2, §3, §6 tests 6, 8, 9 |
| R3 (C2 = A) | Delete `LoadModifier` entirely; manual blackout lives in parent §5.1 availability. | §5 |
| R4 (C3 = A) | An engagement whose event date is unresolved → unknown hours (Unknown band). Lower-bound Full still applies when known hours alone exceed capacity. | §3, §4, §6 tests 12, 13, 18 |
| R5 | T8b does not depend on T2 or T8a. Branch from `main` and stay there. `cancelled` is a plain `bool` input, so T8b never needs migration `0040`. | §1, §2, §7 |

**Parent drift (not edited here; parent-plan owner updates it):** §5.2 lines 413–414
(`attended_at … NULL` and `[as_of, as_of + 45]`) vs R1 and R2; §7 row 10 line 509 (edges
`+45, +46`) vs R2 (`+44, +45`); §8 line 533 (T8b depends on T2) vs R5.

## 1. Files

| Path | Change |
|---|---|
| `python/smartmatch_domain/smartmatch_domain/eli.py` | Rewritten to formula 2.0.0 (§2–§5). Keeps the names `LoadInputs` and `compute_eli` (ADR-0002 line 50 cites both). |
| `tests/unit/test_eli.py` | Rewritten (§6). Keeps `test_prohibited_inputs_cannot_reach_the_computation`, pointed at the new fields. |

Nothing else changes. Verified at `origin/main` (`1909278f`):
`grep -rn 'smartmatch_domain.eli\|compute_eli\|evaluate_cap\|load_penalty\|LoadInputs\|LoadModifier\|EliSnapshot\|EngagementRecord\|CapDecision\|ELI_FORMULA_VERSION' python services tools tests`
finds only `eli.py` and `tests/unit/test_eli.py`. `MANUAL_BLACKOUT` / `manual_blackout` also
appear nowhere else, so deleting `LoadModifier` (R3) strands no caller. `factor_registry.py`
does not import `eli` and `eli` does not import `factor_registry`, so T8c can import `eli`
from the registry without a cycle.

Where things live today: `ELI_FORMULA_VERSION = "1.1.0"` `eli.py:62`; the `40.0` default
`eli.py:160` (`:77` and `:266` are the v1.1 §5.1 citations, not the default); decay
`:64-66, :216-223`; rolling window `:69`; `LoadModifier` `:72-86`, `_NON_LOAD_MODIFIERS`
`:94`; modifier points `:261-271`; `evaluate_cap` `:287-306`; `load_penalty` `:309-322`.
`ExactTime` / `DateOnlyTime` / `UnresolvedTime` / `resolved_date` `events.py:217-367`.
Attended implies confirmed in the DB: `ck_pipeline_record_stage_prefix` `schema.py:746-752`.

## 2. Types and signatures

**Arithmetic: `Decimal` capacity, `timedelta` durations, exact integer-microsecond band
tests. No float.** Capacity arrives as `Decimal` (`numeric(5,1)`, parent §3.1 line 120;
T1's `AvailabilityStatement` refuses anything else, `speaker_availability.py:108` on
`origin/feat/b26-t1`). A duration is `ends_at − starts_at`, a `timedelta` holding whole
microseconds, so sums are exact. The band test compares `Decimal(load_us)` with
`cut × capacity_us`, where `capacity_us = capacity × 3_600_000_000`, inside
`localcontext()` with the `Inexact` trap on, so any rounding raises instead of moving a
boundary. Float fails the parent's own edges: eight 6-minute engagements accumulated with
`+=` (`0.1 h` each) against 1.0 h give `0.7999999999999999`, which is Moderate; exact
arithmetic gives 0.8, Heavy. (Python 3.12+ `sum()` compensates and hides this; a loop does
not.) `utilization` and the hour totals are `Decimal` quotients kept for the explanation
only; no band decision reads them (the rule the old `EliSnapshot.utilization` docstring
already stated).

```python
ELI_FORMULA_VERSION: Final[str] = "2.0.0"
COMPLETED_WINDOW_DAYS: Final[int] = 45  # [as_of - 45, as_of): days -45 .. -1
CONFIRMED_WINDOW_DAYS: Final[int] = 45  # [as_of, as_of + 45): days 0 .. +44
# 45 + 45 = 90 days, the period declared capacity is stated over (R2).


class LoadBand(StrEnum):
    LIGHT = "light"
    MODERATE = "moderate"
    HEAVY = "heavy"
    FULL = "full"
    UNKNOWN = "unknown"


class LoadReason(StrEnum):
    MEASURED = "measured"  # capacity stated, every counted engagement has hours
    CAPACITY_NOT_STATED = "capacity_not_stated"
    HOURS_UNKNOWN = "hours_unknown"  # >= 1 counted engagement without hours or date
    FULL_BY_KNOWN_HOURS = "full_by_known_hours"  # known hours alone > full_above


@dataclass(frozen=True, slots=True)
class LoadBandTable:  # owned here; T8c stores one per registry version and hashes it
    moderate_from: Decimal  # u >= this -> at least Moderate
    heavy_from: Decimal  # u >= this -> at least Heavy
    full_above: Decimal  # u >  this -> Full
    multipliers: Mapping[LoadBand, Decimal]  # LIGHT, MODERATE, HEAVY, UNKNOWN; no FULL
    # __post_init__: all Decimal and finite; 0 < moderate_from < heavy_from <= full_above;
    # multipliers has exactly those 4 keys, each in (0, 1]; wrapped in MappingProxyType.


Q7_LOAD_BAND_TABLE: Final = LoadBandTable(
    moderate_from=Decimal("0.50"),
    heavy_from=Decimal("0.80"),
    full_above=Decimal("1.00"),
    multipliers={
        LoadBand.LIGHT: Decimal("1.00"),
        LoadBand.MODERATE: Decimal("0.90"),
        LoadBand.HEAVY: Decimal("0.70"),
        LoadBand.UNKNOWN: Decimal("1.00"),
    },
)


@dataclass(frozen=True, slots=True)
class Engagement:
    ref: str  # opaque pipeline_record id, so T8d can name what lacks hours
    event_date: date | None  # event's first local date; None = unresolved
    duration: timedelta | None  # None = unknown hours
    confirmed: bool
    attended: bool
    cancelled: bool  # plain input; T8c derives it from 0040's cancelled_at (R5)
    # __post_init__: ref non-blank; duration None or > 0; attended -> confirmed
    # (stage_prefix CHECK); cancelled -> confirmed (mirrors 0040's CHECK as a domain
    # rule; T8b does not import or need 0040). ValueError otherwise.

    @classmethod
    def from_event_time(
        cls, ref: str, event_time: EventTime, *, confirmed: bool, attended: bool, cancelled: bool
    ) -> Engagement: ...  # applies the §3 date and hours rules; T8c calls this


@dataclass(frozen=True, slots=True)
class LoadInputs:
    as_of: date  # T8c: UTC date of run creation (R2)
    engagements: tuple[Engagement, ...]
    declared_capacity_hours: Decimal | None  # REQUIRED keyword, no default (Q6)
    # No `modifiers` field: LoadModifier is deleted (R3).
    # __post_init__: capacity None or Decimal (int/float/bool -> TypeError);
    # a Decimal must be finite and > 0 (ValueError). Refs unique (ValueError).


@dataclass(frozen=True, slots=True)
class LoadAssessment:
    band: LoadBand
    reason: LoadReason
    measurable: bool  # reason is MEASURED
    completed_hours: Decimal  # known hours only
    confirmed_hours: Decimal  # known hours only; upcoming, attended or not (R1)
    capacity_hours: Decimal | None
    utilization: Decimal | None  # (completed + confirmed) / capacity; lower bound if not measurable
    unknown_hours_refs: tuple[str, ...]  # sorted
    formula_version: str


def compute_eli(
    inputs: LoadInputs, table: LoadBandTable = Q7_LOAD_BAND_TABLE
) -> LoadAssessment: ...
```

**Hand-off to T8c.** T8b owns `LoadBand`, `LoadBandTable`, `Q7_LOAD_BAND_TABLE` and
`compute_eli`. T8c attaches a `LoadBandTable` to `FactorRegistry` (3.0.0 gets
`Q7_LOAD_BAND_TABLE`), adds it to `registry_hash`, gathers `Engagement`s from the DB via
`Engagement.from_event_time` (with `cancelled = cancelled_at IS NOT NULL` once T8a's `0040`
exists), passes `as_of` = the UTC date of run creation, calls
`compute_eli(inputs, registry.load_bands)`, removes FULL before the solve, applies
`table.multipliers[band]` to the composite, and writes the explanation `load` block from
`LoadAssessment`. The edge semantics (`>=` into Moderate and Heavy, `>` into Full) are code,
not table data, so a table cannot change which side an edge falls on.

## 3. Window rules

`d` = `event_date − as_of` in days.

| Rule | Definition |
|---|---|
| Counted at all? | Only `confirmed` and not `cancelled`. `cancelled` → never, whatever else is set. Not `confirmed` → never (and cannot be `attended`). |
| completed | `attended`, not `cancelled`, `−45 <= d <= −1` (i.e. `[as_of − 45, as_of)`). |
| confirmed (upcoming) | `confirmed`, not `cancelled`, `0 <= d <= 44` (i.e. `[as_of, as_of + 44]`), **whether `attended` or not** (R1). An attended booking on `as_of` is upcoming, not completed. |
| Neither | confirmed-not-attended with `d <= −1` (C10); any `d <= −46` or `d >= 45`. |
| Window length | 45 + 45 = 90 days, matching capacity per 90 days (R2). The two windows are disjoint by date, so no engagement counts twice. |
| Hours | `ExactTime` with `ends_at`: `ends_at − starts_at`. `ExactTime` without `ends_at`, and `DateOnlyTime`: unknown (`None`). ADR-0011: never 0. |
| Event date | `resolved_date(event_time)`: the `starts_at` local date in the event's zone, or `on_date`. For a multi-day event this is its **first** local date, the same value as T1's `event_local_span(...)[0]` (`speaker_availability.py:164` on `origin/feat/b26-t1`); `resolved_date` is on `main` today, so T8b does not wait for T1. |
| Unknown hours | A counted engagement joins `unknown_hours_refs` when (a) `event_date` is in a window and `duration is None`, or (b) `event_date is None` (`UnresolvedTime`), wherever it might fall (R4). Its hours add nothing to the known sums. |
| Travel | Not an input. 0 by D3 (no route provider); the module docstring says so. |
| `as_of` | Caller-supplied `date`. T8c passes the UTC date of run creation (R2). |

## 4. Band classification

With `cap_us = capacity × 3_600_000_000` and `known_us` = completed + confirmed microseconds:

1. `capacity is None` → `UNKNOWN`, `CAPACITY_NOT_STATED`, `utilization None`, even with large
   known hours (no capacity means no bound).
2. `known_us > full_above × cap_us` → `FULL`. Reason `MEASURED` if `unknown_hours_refs` is
   empty, else `FULL_BY_KNOWN_HOURS` (a certain lower bound, allowed by ADR-0011; parent
   §5.2; R4 keeps it for unresolved dates too).
3. `unknown_hours_refs` non-empty → `UNKNOWN`, `HOURS_UNKNOWN`; `utilization` is the known
   lower bound, flagged by `measurable = False`.
4. `known_us >= heavy_from × cap_us` → `HEAVY` (exactly 80% and exactly 100% are Heavy).
5. `known_us >= moderate_from × cap_us` → `MODERATE` (exactly 50% is Moderate).
6. Otherwise `LIGHT` (includes no engagements: `utilization = 0`, `MEASURED`).

Edge table (capacity 100.0 h): 49.99 → Light · 50.00 → Moderate · 79.99 → Moderate ·
80.00 → Heavy · 100.00 → Heavy · 100.01 → Full.

## 5. Old API

| 1.1.0 item | 2.0.0 |
|---|---|
| `LoadInputs.declared_capacity_hours: float = 40.0` | `Decimal \| None`, required, no default. |
| `EngagementRecord` (past-only, `travel_hours`, future-dated rejected) | Removed; `Engagement` replaces it. Future engagements now count (D2). |
| `_DECAY_HALF_LIFE_DAYS`, `_ROLLING_WINDOW_DAYS`, `_decay_weight` | Removed (D2: "no horizon or weight parameter"). The 90-day span is now the two 45-day window constants (R2). |
| `LoadModifier`, `_NON_LOAD_MODIFIERS`, `LoadInputs.modifiers`, modifier points, `MANUAL_BLACKOUT` branch | **Deleted** (R3). Manual blackout lives in parent §5.1 availability. Nothing replaces them in `eli.py`. |
| `EliSnapshot`, `CapDecision`, `evaluate_cap`, `load_penalty` | Removed: `LoadAssessment.band` and the table multipliers replace them. |
| `ELI_FORMULA_VERSION = "1.1.0"` | `"2.0.0"`. No stored snapshot or caller references 1.1.0 (§1 grep). |

## 6. TDD list (`tests/unit/test_eli.py`, rewritten)

`AS_OF = date(2026, 8, 17)`; `_eng(offset_days, hours, *, confirmed=True, attended=False,
cancelled=False)` builds an `Engagement` dated `AS_OF + offset_days` with `Decimal` hours
converted to a `timedelta` (`hours=None` → unknown).

1. `test_formula_version_is_2_0_0`.
2. `test_capacity_has_no_default`: `LoadInputs(as_of=AS_OF, engagements=())` → `TypeError`.
3. `test_capacity_rejects_float_int_bool`; `test_capacity_rejects_zero_negative_nan_infinity`.
4. `test_capacity_none_is_unknown`: no engagements, then 500 known hours: both `UNKNOWN`, `CAPACITY_NOT_STATED`, `utilization is None`.
5. `test_no_engagements_is_light_measured_zero`.
6. `test_completed_day_minus_46_ignored` / `test_completed_day_minus_45_counts` / `test_completed_day_minus_1_counts` (R2).
7. `test_day_0_confirmed_counts_as_confirmed` / `test_day_0_attended_counts_as_confirmed_not_completed` / `test_attended_future_booking_counts_as_confirmed` (R1).
8. `test_confirmed_day_plus_44_counts` / `test_confirmed_day_plus_45_ignored` (R2).
9. `test_window_spans_exactly_90_days` (R2): one 1-h engagement per day `d = −46 … +45` (attended when `d < 0`, confirmed-not-attended when `d >= 0`), capacity 90.0 → completed 45 h, confirmed 45 h, `utilization == 1`, `HEAVY`.
10. `test_confirmed_not_attended_in_past_counts_in_neither`; `test_cancelled_confirmed_future_counts_in_neither`; `test_cancelled_attended_past_counts_in_neither`; `test_cancelled_attended_day_0_counts_in_neither` (R1 does not override cancellation); `test_cancelled_unknown_hours_does_not_make_unknown`.
11. `test_unknown_hours_in_window_is_unknown` (lists the ref, `measurable False`, `utilization` = known lower bound) / `_outside_window_stays_measurable` (day −46 and day +45).
12. `test_lower_bound_full`: capacity 10.0, known 10.5 h + 1 unknown-hours engagement → `FULL`, `FULL_BY_KNOWN_HOURS` (R4).
13. `test_known_exactly_at_capacity_plus_unknown_is_unknown` (C4, settled by R4's "exceed").
14. `test_band_edges` (parametrized, capacity 100.0): 49.99 / 50.00 / 79.99 / 80.00 / 100.00 / 100.01 → Light / Moderate / Moderate / Heavy / Heavy / Full.
15. `test_band_edges_are_exact_not_float`: eight 6-minute engagements, capacity 1.0 → `HEAVY` (float `+=` gives Moderate).
16. `test_from_event_time`: `ExactTime` with end → exact duration; without end → `None`; `DateOnlyTime` → `None`, date `on_date`; `UnresolvedTime` → date `None`, duration `None`.
17. `test_event_date_is_first_local_date`: 2-day `ExactTime`, `America/Los_Angeles`, starting 23:30 local (UTC next day) → the local start date.
18. `test_unresolved_confirmed_engagement_is_unknown` (R4: ref listed, `HOURS_UNKNOWN`) / `test_unresolved_with_known_hours_over_capacity_is_full` (R4: `FULL_BY_KNOWN_HOURS`) / `test_unresolved_unconfirmed_or_cancelled_is_ignored`.
19. `test_engagement_rejects_attended_without_confirmed`, `cancelled_without_confirmed`, zero duration, blank ref; `test_inputs_reject_duplicate_refs`.
20. `test_q7_table_values` (0.50 / 0.80 / 1.00; 1.00 / 0.90 / 0.70 / 1.00; no FULL key); `test_band_table_rejects_bad_order_and_missing_keys`; `test_custom_table_moves_cut_points_not_edge_semantics`.
21. `test_load_modifier_is_gone` (R3): `eli` exposes no `LoadModifier`, `LoadInputs` has no `modifiers` field.
22. `test_prohibited_inputs_cannot_reach_the_computation`: kept, over `fields(LoadInputs) | fields(Engagement)`.

Run: `PYTHONPATH=… $VENV/bin/pytest tests/unit/test_eli.py -q` only (no full suite on `/mnt/c`).

## 7. Commit milestones

Base stays `main` (R5): never merge or rebase `feat/b26-t2`, `feat/b26-t8a` or `0040` into
this branch.

1. `test: T8b eli 2.0.0 tests (red)`: §6 file; record the failing count in the body.
2. `feat: eli 2.0.0 centered utilization and load bands`: §2–§5, `LoadModifier` deleted;
   `test_eli.py` green; `ruff check` + `ruff format` on both files.
3. `docs: eli 2.0.0 module docstring`: docstring states the D2 rule with R1's upcoming
   rule and R2's 90-day window (`[as_of − 45, as_of)` + `[as_of, as_of + 44]`), the bands,
   Unknown (incl. unresolved dates, R4), travel 0 (D3); nothing else.
4. Push; PR `feat: B26 T8b eli 2.0.0` against `main`, template sections filled.

## 8. Contradictions

**Settled by owner rulings (2026-09-23)**

| # | Issue | Ruling |
|---|---|---|
| C1 | An event on `as_of` already marked attended counted in neither window under §5.2's literal text. | **Settled, R1:** confirmed window counts confirmed-not-cancelled whatever `attended` says. Tests 7, 10. |
| C2 | §5.2 says `LoadModifier` "stops adding points"; keeping it leaves a dead field. | **Settled, R3 (A):** deleted. Tests 21, 22. |
| C3 | Parent silent on a counted engagement whose event is `unresolved`. | **Settled, R4 (A):** unknown hours → `UNKNOWN`; lower-bound Full still applies. Test 18. |
| C4 | Known hours exactly 100% plus one unknown engagement is certainly over 100%, yet the rule says "exceed". | **Settled, R4 wording:** Full needs known hours to *exceed* capacity, so this is `UNKNOWN`. Test 13. |
| C5 | Old windows spanned **91** days against a 90-day capacity. | **Settled, R2:** confirmed window ends at `as_of + 44`; 90 days. Tests 6, 8, 9. |
| C9 | Parent §8 lists T8b as depending on T2. | **Settled, R5:** no T2 or T8a dependency; branch from `main`; `cancelled` is a plain input. |

**Still open (none blocks T8b)**

| # | Issue | Owner of the follow-up |
|---|---|---|
| C6 | `as_of` is a UTC date (R2); event dates are local. An LA evening run can be a day ahead of the local date, moving one day across the window seam. | T8c (accepted as R2 states it; surface in the explanation if it matters). |
| C7 | A multi-day exact event counts `ends_at − starts_at` in full (a 3-day event = 72 h), all on its first date. | Literal §5.2; T8d surfaces it. |
| C8 | Travel is unknown but counts 0 (D3), while unknown event hours make the band `UNKNOWN`. | Owner-fixed in §5.2; docstring says so. |
| C10 | Past confirmed bookings never marked attended count in neither window, so missing attendance data reads as low load. | Parent §11 risk 4; T8d visibility. |
| — | Parent plan text drifts from R1, R2, R5 (lines 413–414, 509, 533). | Parent-plan owner; not this track's file. |
