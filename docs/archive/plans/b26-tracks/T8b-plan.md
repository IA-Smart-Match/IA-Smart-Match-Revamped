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
| R3 (C2 = A) | Delete `LoadModifier` entirely; manual blackout lives in parent §5.1 availability. | §5, §6 test 23 |
| R4 (C3 = A) | An engagement whose event date is unresolved → unknown hours (Unknown band). Lower-bound Full still applies when known hours alone exceed capacity. | §3, §4, §6 tests 13, 14, 20 |
| R5 | T8b does not depend on T2 or T8a. Branch from `main` and stay there. `cancelled` is a plain `bool` input, so T8b never needs migration `0040`. | §1, §2, §7 |

**Parent drift:** the parent plan predated R1–R3 and R5 in six places. They are fixed
on this branch by the plan-review round 1 commit, so they ship in the T8b PR (§1 row 4, §1.2).

## 1. Files

| # | Path | Change |
|---|---|---|
| 1 | `python/smartmatch_domain/smartmatch_domain/eli.py` | Rewritten to formula 2.0.0 (§2–§5). Keeps the names `LoadInputs` and `compute_eli` (ADR-0002 line 50 cites both). |
| 2 | `tests/unit/test_eli.py` | Rewritten (§6). Keeps `test_prohibited_inputs_cannot_reach_the_computation`, pointed at the new fields. |
| 3 | `docs/migration/migration-manifest.yaml` | MM-003 entry (`:125-255`) updated for 2.0.0 (§1.1). |
| 4 | `docs/plans/2026-09-22-b26-self-service-availability-plan.md` | **Already edited on this branch** (plan-review round 1): lines 413–419, 424–425, 511, 535, 543–544, 546 aligned with R1, R2, R3, R5 (§1.2). The implementer re-checks them against the final code and commits no further change unless the code differs. |

No other file changes. Verified at `origin/main` (`1909278f`):
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

### 1.1 Migration manifest, MM-003 (`docs/migration/migration-manifest.yaml`)

The entry describes 1.1.0 symbols that 2.0.0 deletes. The corrections below are
**appended as dated 2.0.0 notes**, and the dated 26 Aug text stays as it is. `status` stays
`ported_unverified`, because an author does not approve their own entry (`:225-226`).

| Line | Today | Change |
|---|---|---|
| `:130` `target_symbol` | `compute_eli, evaluate_cap, load_penalty, LoadInputs, EliSnapshot` | `compute_eli, LoadInputs, Engagement, LoadAssessment, LoadBandTable, Q7_LOAD_BAND_TABLE` |
| `:133-151` `behavior_retained` | Says the score combines assignment pressure and travel burden, and names the modifiers | Append: 2.0.0 keeps workload pressure only. Travel counts 0 (D3). The modifiers are deleted (R3). The output is a band, not a score. |
| `:160-184` `behavior_introduced` | (1) decay, (2) future-dated records rejected, (3) Stage A on unrounded utilization | Append (4): B26 formula 2.0.0 (D2). Centered 90-day window, R1 upcoming rule, Q7 bands, Unknown, no default capacity. It supersedes (1), (2) and the modifier half of (3); (2)'s open D2 question is answered by Q1/D2. |
| `:186-196` `data_provenance`, `:203-221` `security_review` | Name the `LoadInputs` / `EngagementRecord` field sets | Change `EngagementRecord` to `Engagement`. The closed-field-set claim still holds, and test 24 enforces it. |
| `:198-202` `target_tests` | "22 cases", measured 26 Aug | Append the 2.0.0 count, measured after milestone 2 with `$VENV/bin/pytest tests/unit/test_eli.py --collect-only -q \| tail -1`, never estimated. |
| `:244-254` `notes` | Decay, window and modifier weighting are "proposed defaults" (open decision 2); 91-day inclusive window; `1e-9` capacity passes | Append: open decision 2 answered by Q1/D2 and Q7. The window is now exactly 90 days (R2), which closes the 91-day observation. The tiny-capacity observation still holds inside `eli.py` (`Decimal("1E-9")` is finite and > 0). The DB CHECK (parent §3.1 lines 127–128) and T1 bound it before it reaches ELI. |

`:997` (`counts_method`) is a dated measurement against `6a2f0ec`, so it stays unchanged. The new count
lives in `target_tests` only.

### 1.2 Parent plan lines (`docs/plans/2026-09-22-b26-self-service-availability-plan.md`)

Done on this branch. Left column = line on `main` (`1909278f`), then the new line numbers.

| Line on `main` → now | Was | Now |
|---|---|---|
| 413–414 → 413–414, 418–419 | `confirmed  = Σ event hours, confirmed_at set, attended_at and cancelled_at NULL,` / `event local date in [as_of, as_of + 45]` | `confirmed  = Σ event hours, confirmed_at set, cancelled_at NULL (attended or not),` / `event local date in [as_of, as_of + 44]`, then a bullet: "The window is 90 days: `[as_of − 45, as_of)` + `[as_of, as_of + 44]`. An event on `as_of` that is already attended counts as confirmed (owner, 2026-09-23)." |
| 422–423 → 424–425 | `` `LoadModifier` stops adding points (manual blackout now lives in §5.1). `` | `` `LoadModifier` is deleted (manual blackout now lives in §5.1). `` |
| 509 → 511 | `centered window edges (day −45, −1, 0, +45, +46)` | `centered window edges (day −46, −45, −1, 0, +44, +45)` |
| 533 → 535 | T8b "Depends on" `T2` | `—` (pure domain; branches from `main`) |
| 541 → 543–544 | `2. T1 → T2 → T8b → T8c → T8d — 7 days of work` | `2. T1 → T2 → T8c → T8d — 6 days of work, with T8b (1 day) in parallel from day one` |
| 544 → 546 | `T1–T5, T6a, T7 and T8a can run in parallel from day one.` | `T1–T5, T6a, T7, T8a and T8b can run in parallel from day one.` |

## 2. Types and signatures

**Arithmetic: `Decimal` capacity, `timedelta` durations, exact integer-microsecond band
tests. No float.** Capacity arrives as `Decimal` (`numeric(5,1)`, parent §3.1 line 120;
T1's `AvailabilityStatement` refuses anything else, `speaker_availability.py:108` on
`origin/feat/b26-t1`). A duration is `ends_at − starts_at`, a `timedelta` holding whole
microseconds, so sums are exact. The band test compares `Decimal(load_us)` with
`cut × capacity_us`, where `capacity_us = capacity × 3_600_000_000`. **Only those
comparisons** run inside `localcontext()` with the `Inexact` trap on, so any rounding in
them raises instead of moving a boundary. They are products of short `Decimal`s and
integers, so they are always exact. The hour totals (`us / 3_600_000_000`) and
`utilization` (`known / capacity`) are quotients that are often inexact: 1 h against
3.0 h is 1/3. They are computed **outside** the trapped context, in the default 28-digit
context, and would raise if they were inside it. Float fails the parent's own edges: eight 6-minute engagements accumulated with
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
class LoadBandTable:  # cut points + multipliers only; no ownership field (see below)
    moderate_from: Decimal  # u >= this -> at least Moderate
    heavy_from: Decimal  # u >= this -> at least Heavy
    full_above: Decimal  # u >  this -> Full
    # LIGHT, MODERATE, HEAVY, UNKNOWN; no FULL. hash=False: a MappingProxyType is
    # unhashable, so without it hash(table) raises TypeError. It still takes part in ==.
    multipliers: Mapping[LoadBand, Decimal] = field(hash=False)
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
    unknown_hours_refs: tuple[str, ...]  # sorted; filled even when capacity is None
    formula_version: str


def compute_eli(
    inputs: LoadInputs, table: LoadBandTable = Q7_LOAD_BAND_TABLE
) -> LoadAssessment: ...
```

**Hand-off to T8c.** T8b owns `LoadBand`, `LoadBandTable`, `Q7_LOAD_BAND_TABLE` and
`compute_eli`. **`ownership` is not in `eli.py`.** Parent §5.2 item 2 lists
"cut points, ownership, multipliers" for the registry's band table. T8c adds ownership
(approver, approval status) in a registry-side wrapper that holds a `LoadBandTable`, so T8c
never edits `eli.py`'s type. The table's identity in `registry_hash` is T8c's canonical
serialization of the cut points and multipliers, not Python `hash()`. `hash=False` on
`multipliers` only keeps `hash(table)` from raising. T8c attaches the wrapper to
`FactorRegistry` (3.0.0 gets `Q7_LOAD_BAND_TABLE`), adds it to `registry_hash`, gathers `Engagement`s from the DB via
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
| Unknown hours | An engagement joins `unknown_hours_refs` only when (a) it **satisfies the completed or confirmed row above** and `duration is None`, or (b) it is `confirmed`, not `cancelled`, and `event_date is None` (`UnresolvedTime`), wherever it might fall (R4). An engagement that counts in neither, such as a confirmed-not-attended booking at `d <= −1` or anything outside both windows, never makes the band Unknown, whatever its hours. Unknown hours add nothing to the known sums. |
| Travel | Not an input. 0 by D3 (no route provider); the module docstring says so. |
| `as_of` | Caller-supplied `date`. T8c passes the UTC date of run creation (R2). |

## 4. Band classification

With `cap_us = capacity × 3_600_000_000` and `known_us` = completed + confirmed microseconds:

1. `capacity is None` → `UNKNOWN`, `CAPACITY_NOT_STATED`, `utilization None`, even with large
   known hours (no capacity means no bound). The hour totals and `unknown_hours_refs` are
   still computed and filled, so T8d can name the gaps before capacity is stated.
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
cancelled=False)` builds an `Engagement` dated `AS_OF + offset_days` (`hours=None` → unknown).
It converts `Decimal` hours with `us = hours * 3_600_000_000`, asserts
`us == us.to_integral_value()` (so a fixture can never round silently), then builds
`timedelta(microseconds=int(us))`.

1. `test_formula_version_is_2_0_0`.
2. `test_capacity_has_no_default`: `LoadInputs(as_of=AS_OF, engagements=())` → `TypeError`.
3. `test_capacity_rejects_float_int_bool`; `test_capacity_rejects_zero_negative_nan_infinity`.
4. `test_capacity_none_is_unknown`: no engagements, then 500 known hours, then one in-window unknown-hours engagement. All three give `UNKNOWN`, `CAPACITY_NOT_STATED` and `utilization is None`. The third also has `unknown_hours_refs == (ref,)`, because refs are filled even without capacity.
5. `test_no_engagements_is_light_measured_zero`.
6. `test_completed_day_minus_46_ignored` / `test_completed_day_minus_45_counts` / `test_completed_day_minus_1_counts` (R2).
7. `test_day_0_confirmed_counts_as_confirmed` / `test_day_0_attended_counts_as_confirmed_not_completed` / `test_attended_future_booking_counts_as_confirmed` (R1).
8. `test_confirmed_day_plus_44_counts` / `test_confirmed_day_plus_45_ignored` (R2).
9. `test_window_spans_exactly_90_days` (R2): one 1-h engagement per day `d = −46 … +45` (attended when `d < 0`, confirmed-not-attended when `d >= 0`), capacity 90.0 → completed 45 h, confirmed 45 h, `utilization == 1`, `HEAVY`.
10. `test_confirmed_not_attended_in_past_counts_in_neither`; `test_cancelled_confirmed_future_counts_in_neither`; `test_cancelled_attended_past_counts_in_neither`; `test_cancelled_attended_day_0_counts_in_neither` (R1 does not override cancellation); `test_cancelled_unknown_hours_does_not_make_unknown`.
11. `test_unknown_hours_in_window_is_unknown` (lists the ref, `measurable False`, `utilization` = known lower bound) / `_outside_window_stays_measurable` (day −46 and day +45).
12. `test_confirmed_not_attended_past_unknown_hours_stays_measurable`: `d = −5`, confirmed, not attended, `hours=None`, plus 30 h attended at `d = −10`, capacity 100.0 → `MEASURED`, `LIGHT` (from the 30 known hours), `unknown_hours_refs == ()`.
13. `test_lower_bound_full`: capacity 10.0, known 10.5 h + 1 unknown-hours engagement → `FULL`, `FULL_BY_KNOWN_HOURS` (R4).
14. `test_known_exactly_at_capacity_plus_unknown_is_unknown` (C4, settled by R4's "exceed").
15. `test_band_edges` (parametrized, capacity 100.0): 49.99 / 50.00 / 79.99 / 80.00 / 100.00 / 100.01 → Light / Moderate / Moderate / Heavy / Heavy / Full.
16. `test_band_edges_are_exact_not_float`: eight 6-minute engagements, capacity 1.0 → `HEAVY` (float `+=` gives Moderate).
17. `test_inexact_quotients_do_not_raise`: 1 h against capacity 3.0 → no exception, `LIGHT`, `utilization == Decimal(1) / Decimal(3)` (default context). One 7-minute engagement → `confirmed_hours == Decimal(420_000_000) / Decimal(3_600_000_000)`, no exception.
18. `test_from_event_time`: `ExactTime` with end → exact duration; without end → `None`; `DateOnlyTime` → `None`, date `on_date`; `UnresolvedTime` → date `None`, duration `None`.
19. `test_event_date_is_first_local_date`: 2-day `ExactTime`, `America/Los_Angeles`, starting 23:30 local (UTC next day) → the local start date.
20. `test_unresolved_confirmed_engagement_is_unknown` (R4: ref listed, `HOURS_UNKNOWN`) / `test_unresolved_with_known_hours_over_capacity_is_full` (R4: `FULL_BY_KNOWN_HOURS`) / `test_unresolved_unconfirmed_or_cancelled_is_ignored`.
21. `test_engagement_rejects_attended_without_confirmed`, `cancelled_without_confirmed`, zero duration, blank ref; `test_inputs_reject_duplicate_refs`.
22. `test_q7_table_values` (0.50 / 0.80 / 1.00; 1.00 / 0.90 / 0.70 / 1.00; no FULL key); `test_band_table_rejects_bad_order_and_missing_keys`; `test_custom_table_moves_cut_points_not_edge_semantics`; `test_band_table_is_hashable_and_compares_multipliers` (`hash()` works; two tables that differ only in a multiplier are `!=`).
23. `test_load_modifier_is_gone` (R3): `eli` exposes no `LoadModifier`, `LoadInputs` has no `modifiers` field.
24. `test_prohibited_inputs_cannot_reach_the_computation`: kept, over `fields(LoadInputs) | fields(Engagement)`.

Run: `PYTHONPATH=… $VENV/bin/pytest tests/unit/test_eli.py -q` only (no full suite on `/mnt/c`).

## 7. Commit milestones

Base stays `main` (R5): never merge or rebase `feat/b26-t2`, `feat/b26-t8a` or `0040` into
this branch.

1. `test: T8b eli 2.0.0 tests (red)`: §6 file. The red state is a **collection error**:
   the file imports `LoadBand`, `Engagement` and other names 1.1.0 does not have, so pytest
   stops at `ImportError` before running any test. The commit body quotes that error line
   and says the test count is not measurable until the imports resolve.
2. `feat: eli 2.0.0 centered utilization and load bands`: §2–§5, `LoadModifier` deleted;
   `test_eli.py` green; `ruff check` + `ruff format` on both files.
3. `docs: eli 2.0.0 module docstring`: rewrite `eli.py:1-36` **in part**. Keep the MM-003
   provenance paragraphs (`:3-24`: the legacy replacement, what was retained, the F-4
   event-cadence correction and what was rejected). Add one line that 2.0.0 counts travel
   as 0 (D3) and deletes the modifiers that `:16-17` mention (R3). Keep the
   `PROHIBITED_INPUTS` paragraph (`:26-28`) unchanged. Replace only the Stage A / Stage B
   text (`:30-36`) and any formula text. The new text states the D2 rule
   with R1's upcoming rule, R2's 90-day window (`[as_of − 45, as_of)` + `[as_of, as_of + 44]`),
   the bands, Unknown (including unresolved dates, R4), and travel 0 (D3).
4. `docs: MM-003 for eli 2.0.0`: §1.1 manifest edits, with `target_tests` measured by
   `--collect-only`. Re-check the §1.2 parent lines against the code (already edited).
5. Push; PR `feat: B26 T8b eli 2.0.0` against `main`, template sections filled.

## 8. Contradictions

**Settled by owner rulings (2026-09-23)**

| # | Issue | Ruling |
|---|---|---|
| C1 | An event on `as_of` already marked attended counted in neither window under §5.2's literal text. | **Settled, R1:** confirmed window counts confirmed-not-cancelled whatever `attended` says. Tests 7, 10. |
| C2 | §5.2 says `LoadModifier` "stops adding points"; keeping it leaves a dead field. | **Settled, R3 (A):** deleted. Tests 23, 24. |
| C3 | Parent silent on a counted engagement whose event is `unresolved`. | **Settled, R4 (A):** unknown hours → `UNKNOWN`; lower-bound Full still applies. Test 20. |
| C4 | Known hours exactly 100% plus one unknown engagement is certainly over 100%, yet the rule says "exceed". | **Settled, R4 wording:** Full needs known hours to *exceed* capacity, so this is `UNKNOWN`. Test 14. |
| C5 | Old windows spanned **91** days against a 90-day capacity. | **Settled, R2:** confirmed window ends at `as_of + 44`; 90 days. Tests 6, 8, 9. |
| C9 | Parent §8 lists T8b as depending on T2. | **Settled, R5:** no T2 or T8a dependency; branch from `main`; `cancelled` is a plain input. Parent lines fixed on this branch (§1.2). |

**Still open (none blocks T8b)**

| # | Issue | Owner of the follow-up |
|---|---|---|
| C6 | `as_of` is a UTC date (R2); event dates are local. An LA evening run can be a day ahead of the local date, moving one day across the window seam. | T8c (accepted as R2 states it; surface in the explanation if it matters). |
| C7 | A multi-day exact event counts `ends_at − starts_at` in full (a 3-day event = 72 h), all on its first date. | Literal §5.2; T8d surfaces it. |
| C8 | Travel is unknown but counts 0 (D3), while unknown event hours make the band `UNKNOWN`. | Owner-fixed in §5.2; docstring says so. |
| C10 | Past confirmed bookings never marked attended count in neither window, so missing attendance data reads as low load. Unknown hours on such a booking do not make the band Unknown either (§3, test 12). | Parent §11 risk 4; T8d visibility. |
