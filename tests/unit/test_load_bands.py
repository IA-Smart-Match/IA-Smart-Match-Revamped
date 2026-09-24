"""The registry-side wrapper around ELI 2.0.0's band table (B26 T8c, plan §3.1).

``load_bands`` never edits T8b's types: it wraps ``Q7_LOAD_BAND_TABLE`` with who
decided it, renders it canonically for ``registry_hash``, and runs ``compute_eli``
once per subject with one ``as_of`` per run.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from smartmatch_domain.eli import (
    ELI_FORMULA_VERSION,
    Q7_LOAD_BAND_TABLE,
    Engagement,
    LoadAssessment,
    LoadBand,
    LoadBandTable,
    LoadReason,
)
from smartmatch_domain.load_bands import (
    ENGAGEMENT_LOAD_FACTOR_KEY,
    Q7_REGISTERED_LOAD_BANDS,
    AssessedLoad,
    LoadBandOwnership,
    LoadReviewStatus,
    RegisteredLoadBands,
    assess_pool_loads,
    canonical_load_bands,
    stage_a_load_excluded,
)

AS_OF = date(2026, 10, 6)


def _ownership(**changes: object) -> LoadBandOwnership:
    base = {
        "decided_by": "Danny Tran, Development Lead / program owner of record",
        "decided_on": "2026-09-22",
        "decision": "B26 Q7 = A (parent plan §9)",
        "review_status": LoadReviewStatus.PENDING_IA_WEST_REVIEW,
    }
    base.update(changes)
    return LoadBandOwnership(**base)  # type: ignore[arg-type]


def _engagement(ref: str, offset_days: int, hours: str | None, *, attended: bool) -> Engagement:
    return Engagement(
        ref=ref,
        event_date=AS_OF + timedelta(days=offset_days),
        duration=None if hours is None else timedelta(hours=float(Decimal(hours))),
        confirmed=True,
        attended=attended,
        cancelled=False,
    )


def _assessment(band: LoadBand) -> LoadAssessment:
    reason = LoadReason.MEASURED if band is not LoadBand.UNKNOWN else LoadReason.HOURS_UNKNOWN
    return LoadAssessment(
        band=band,
        reason=reason,
        measurable=reason is LoadReason.MEASURED,
        completed_hours=Decimal(0),
        confirmed_hours=Decimal(0),
        capacity_hours=Decimal(10),
        utilization=Decimal(0),
        unknown_hours_refs=(),
        formula_version=ELI_FORMULA_VERSION,
    )


def test_the_factor_key_and_the_declared_table():
    assert ENGAGEMENT_LOAD_FACTOR_KEY == "engagement_load"
    assert Q7_REGISTERED_LOAD_BANDS.table is Q7_LOAD_BAND_TABLE
    assert Q7_REGISTERED_LOAD_BANDS.eli_formula_version == ELI_FORMULA_VERSION == "2.0.0"
    ownership = Q7_REGISTERED_LOAD_BANDS.ownership
    assert ownership.decided_by == "Danny Tran, Development Lead / program owner of record"
    assert ownership.decided_on == "2026-09-22"
    assert ownership.decision == "B26 Q7 = A (parent plan §9)"
    assert ownership.review_status is LoadReviewStatus.PENDING_IA_WEST_REVIEW


# 11
@pytest.mark.parametrize(
    "changes",
    [
        {"decided_by": "  "},
        {"decided_by": ""},
        {"decision": " "},
        {"decided_on": ""},
        {"decided_on": "22 September 2026"},
        {"decided_on": "2026-02-30"},
        {"decided_on": "2026-9-22"},
        {"review_status": "reviewed"},
    ],
)
def test_ownership_rejects_blank_fields_and_bad_date(changes):
    with pytest.raises((ValueError, TypeError)):
        _ownership(**changes)


def test_registered_bands_refuse_a_foreign_table_or_blank_version():
    with pytest.raises(TypeError):
        RegisteredLoadBands(
            table="Q7",  # type: ignore[arg-type]
            eli_formula_version=ELI_FORMULA_VERSION,
            ownership=_ownership(),
        )
    with pytest.raises(ValueError):
        RegisteredLoadBands(
            table=Q7_LOAD_BAND_TABLE, eli_formula_version=" ", ownership=_ownership()
        )


def test_registered_bands_are_hashable_and_compare_by_value():
    copy = RegisteredLoadBands(
        table=Q7_LOAD_BAND_TABLE, eli_formula_version=ELI_FORMULA_VERSION, ownership=_ownership()
    )
    assert copy == Q7_REGISTERED_LOAD_BANDS
    assert hash(copy) == hash(Q7_REGISTERED_LOAD_BANDS)


# 12
def test_canonical_load_bands_normalizes_decimals():
    assert canonical_load_bands(Q7_REGISTERED_LOAD_BANDS) == {
        "eli_formula_version": "2.0.0",
        "full_above": "1",
        "heavy_from": "0.8",
        "moderate_from": "0.5",
        "multipliers": {"heavy": "0.7", "light": "1", "moderate": "0.9", "unknown": "1"},
    }
    # 0.5 and 0.50 are equal under LoadBandTable.__eq__, so they render alike.
    respelled = replace(
        Q7_REGISTERED_LOAD_BANDS,
        table=LoadBandTable(
            moderate_from=Decimal("0.5"),
            heavy_from=Decimal("0.800"),
            full_above=Decimal("1"),
            multipliers={
                LoadBand.LIGHT: Decimal("1"),
                LoadBand.MODERATE: Decimal("0.9"),
                LoadBand.HEAVY: Decimal("0.7000"),
                LoadBand.UNKNOWN: Decimal("1.0"),
            },
        ),
    )
    assert canonical_load_bands(respelled) == canonical_load_bands(Q7_REGISTERED_LOAD_BANDS)


def test_canonical_load_bands_leaves_ownership_out():
    reviewed = replace(
        Q7_REGISTERED_LOAD_BANDS, ownership=_ownership(review_status=LoadReviewStatus.REVIEWED)
    )
    assert canonical_load_bands(reviewed) == canonical_load_bands(Q7_REGISTERED_LOAD_BANDS)


# 13
def test_assess_pool_loads_reads_no_default_capacity():
    absent, stated_none, stated = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    work = (_engagement("r-1", -5, "30", attended=True),)
    loads = assess_pool_loads(
        [absent, stated_none, stated],
        capacities={stated_none: None, stated: Decimal("100.0")},
        engagements={absent: work, stated_none: work, stated: work},
        as_of=AS_OF,
        bands=Q7_REGISTERED_LOAD_BANDS,
    )
    for subject in (absent, stated_none):
        assessment = loads[subject].assessment
        assert assessment.band is LoadBand.UNKNOWN
        assert assessment.reason is LoadReason.CAPACITY_NOT_STATED
        assert assessment.capacity_hours is None
        assert assessment.utilization is None
    assert loads[stated].assessment.band is LoadBand.LIGHT
    assert loads[stated].assessment.utilization == Decimal("0.3")


def test_assess_pool_loads_reads_absent_engagements_as_none():
    subject = uuid.uuid4()
    loads = assess_pool_loads(
        [subject],
        capacities={subject: Decimal("10")},
        engagements={},
        as_of=AS_OF,
        bands=Q7_REGISTERED_LOAD_BANDS,
    )
    assert loads[subject].assessment.band is LoadBand.LIGHT
    assert loads[subject].assessment.completed_hours == 0
    assert loads[subject].assessment.confirmed_hours == 0


# 14
def test_assess_pool_loads_uses_one_as_of_for_every_subject():
    first, second = uuid.uuid4(), uuid.uuid4()
    loads = assess_pool_loads(
        [first, second],
        capacities={first: Decimal("10"), second: Decimal("10")},
        engagements={
            # Day -1 counts as completed only when as_of is 6 Oct: the same
            # engagement date must be judged against the same run date for both.
            first: (_engagement("a", -1, "6", attended=True),),
            second: (_engagement("b", -1, "6", attended=True),),
        },
        as_of=AS_OF,
        bands=Q7_REGISTERED_LOAD_BANDS,
    )
    assert {load.as_of for load in loads.values()} == {AS_OF}
    assert loads[first].assessment == loads[second].assessment
    assert loads[first].assessment.completed_hours == Decimal(6)


def test_assess_pool_loads_is_read_only_and_refuses_duplicates():
    subject = uuid.uuid4()
    loads = assess_pool_loads(
        [subject], capacities={}, engagements={}, as_of=AS_OF, bands=Q7_REGISTERED_LOAD_BANDS
    )
    with pytest.raises(TypeError):
        loads[uuid.uuid4()] = loads[subject]  # type: ignore[index]
    with pytest.raises(ValueError, match="duplicate"):
        assess_pool_loads(
            [subject, subject],
            capacities={},
            engagements={},
            as_of=AS_OF,
            bands=Q7_REGISTERED_LOAD_BANDS,
        )


def test_assessed_load_refuses_a_datetime_as_of():
    with pytest.raises(TypeError):
        AssessedLoad(as_of=datetime(2026, 10, 6), assessment=_assessment(LoadBand.LIGHT))


# 15
@pytest.mark.parametrize(
    ("band", "excluded"),
    [
        (LoadBand.LIGHT, False),
        (LoadBand.MODERATE, False),
        (LoadBand.HEAVY, False),
        (LoadBand.UNKNOWN, False),
        (LoadBand.FULL, True),
    ],
)
def test_stage_a_load_excluded_is_full_only(band, excluded):
    assert (
        stage_a_load_excluded(AssessedLoad(as_of=AS_OF, assessment=_assessment(band))) is excluded
    )


def test_stage_a_load_excluded_is_false_without_a_load():
    assert stage_a_load_excluded(None) is False
