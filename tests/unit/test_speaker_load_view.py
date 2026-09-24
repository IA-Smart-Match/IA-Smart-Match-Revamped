"""The current load band a Speaker and a Connector read (B26 T8d §4, U1–U8).

:func:`~smartmatch_api.speaker_load.speaker_load_view` turns one
:class:`~smartmatch_domain.load_bands.AssessedLoad` and the labels of the
engagements without an end time into the wire's ``load`` block. No database:
every assessment here comes from T8b's ``compute_eli`` on hand-built
engagements, through T8c's ``assess_pool_loads``, the path a 3.x run takes.

What is pinned:

* each band and reason reaches the view unchanged;
* the band table is the current registry's when it has one, else the Q7 table
  3.0.0 declares, and ``used_in_matching`` says which (OQ-1);
* the Speaker sees every title; a Connector sees no title, date or record id of
  another unit's engagement (plan-gate MED 1);
* the view carries no number at all (OQ-CBA-005).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from smartmatch_api import speaker_load
from smartmatch_api.routers.speaker_availability_models import (
    EngagementWithoutEndTimeView,
    SpeakerLoadView,
)
from smartmatch_api.speaker_load import (
    MAX_LISTED_WITHOUT_END_TIME,
    display_load_bands,
    speaker_load_view,
)
from smartmatch_domain import factor_registry
from smartmatch_domain.eli import Engagement, LoadBand, LoadReason
from smartmatch_domain.factor_registry import CBA_REGISTRY_3
from smartmatch_domain.load_bands import (
    Q7_REGISTERED_LOAD_BANDS,
    AssessedLoad,
    assess_pool_loads,
)
from smartmatch_persistence.engagement_labels import EngagementLabel

AS_OF = date(2026, 10, 6)
SUBJECT = uuid.UUID("00000000-0000-4000-8000-0000000000a1")
VIEWER_UNIT = uuid.UUID("00000000-0000-4000-8000-0000000000b1")
OTHER_UNIT = uuid.UUID("00000000-0000-4000-8000-0000000000b2")


@pytest.fixture(autouse=True)
def _current_registry_is_the_shipped_one() -> Iterator[None]:
    """Every test starts on the shipped current registry (2.0.0)."""
    assert factor_registry.current_cba_registry().load_bands is None
    yield


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _booking(
    ref: str,
    *,
    offset_days: int,
    hours: int | None,
    attended: bool = False,
    dated: bool = True,
) -> Engagement:
    return Engagement(
        ref=ref,
        event_date=(AS_OF + timedelta(days=offset_days)) if dated else None,
        duration=None if hours is None else timedelta(hours=hours),
        confirmed=True,
        attended=attended,
        cancelled=False,
    )


def _assess(capacity: Decimal | None, *engagements: Engagement) -> AssessedLoad:
    return assess_pool_loads(
        [SUBJECT],
        capacities={SUBJECT: capacity},
        engagements={SUBJECT: tuple(engagements)},
        as_of=AS_OF,
        bands=Q7_REGISTERED_LOAD_BANDS,
    )[SUBJECT]


def _label(
    record_id: uuid.UUID | None = None,
    *,
    event: bool = True,
    title: str = "Corporate treasury guest lecture",
    host: uuid.UUID = VIEWER_UNIT,
    origin: str = "coordinator_entry",
    precision: str = "date_only",
    resolved: date | None = AS_OF,
) -> EngagementLabel:
    if not event:
        return EngagementLabel(
            record_id=record_id or uuid.uuid4(),
            event_id=None,
            title=None,
            resolved_date=None,
            time_precision=None,
            host_org_unit_id=None,
            origin=None,
        )
    return EngagementLabel(
        record_id=record_id or uuid.uuid4(),
        event_id=uuid.uuid4(),
        title=title,
        resolved_date=resolved,
        time_precision=precision,
        host_org_unit_id=host,
        origin=origin,
    )


def _view(
    assessed: AssessedLoad,
    labels: list[EngagementLabel] | None = None,
    *,
    viewer: uuid.UUID | None = None,
    used: bool = False,
    has_more: bool = False,
) -> SpeakerLoadView:
    return speaker_load_view(
        assessed,
        labels or [],
        has_more=has_more,
        used_in_matching=used,
        viewer_unit_id=viewer,
    )


# ---------------------------------------------------------------------------
# U1 — each band and reason
# ---------------------------------------------------------------------------

_CAPACITY = Decimal("100")

_CASES: list[tuple[str, Decimal | None, tuple[Engagement, ...], LoadBand, LoadReason]] = [
    (
        "light",
        _CAPACITY,
        (_booking("a", offset_days=3, hours=10),),
        LoadBand.LIGHT,
        LoadReason.MEASURED,
    ),
    (
        "moderate",
        _CAPACITY,
        (_booking("a", offset_days=-10, hours=60, attended=True),),
        LoadBand.MODERATE,
        LoadReason.MEASURED,
    ),
    (
        "heavy",
        _CAPACITY,
        (_booking("a", offset_days=3, hours=85),),
        LoadBand.HEAVY,
        LoadReason.MEASURED,
    ),
    (
        "full measured",
        _CAPACITY,
        (_booking("a", offset_days=3, hours=120),),
        LoadBand.FULL,
        LoadReason.MEASURED,
    ),
    (
        "full by known hours",
        _CAPACITY,
        (_booking("a", offset_days=3, hours=120), _booking("b", offset_days=4, hours=None)),
        LoadBand.FULL,
        LoadReason.FULL_BY_KNOWN_HOURS,
    ),
    (
        "capacity not stated",
        None,
        (_booking("a", offset_days=3, hours=10),),
        LoadBand.UNKNOWN,
        LoadReason.CAPACITY_NOT_STATED,
    ),
    (
        "hours unknown",
        _CAPACITY,
        (_booking("a", offset_days=3, hours=None),),
        LoadBand.UNKNOWN,
        LoadReason.HOURS_UNKNOWN,
    ),
]


@pytest.mark.parametrize(
    ("capacity", "engagements", "band", "reason"),
    [case[1:] for case in _CASES],
    ids=[case[0] for case in _CASES],
)
def test_each_band_and_reason_maps_to_the_view(
    capacity: Decimal | None,
    engagements: tuple[Engagement, ...],
    band: LoadBand,
    reason: LoadReason,
) -> None:
    """U1: the view carries T8b's band and reason, and the run's as_of."""
    assessed = _assess(capacity, *engagements)
    assert (assessed.assessment.band, assessed.assessment.reason) == (band, reason)

    view = _view(assessed)

    assert view.band == band.value
    assert view.reason == reason.value
    assert view.as_of == AS_OF
    assert view.used_in_matching is False


# ---------------------------------------------------------------------------
# U2, U3 — the band table and used_in_matching follow the current registry
# ---------------------------------------------------------------------------


def test_display_bands_are_q7_while_current_is_2_0_0_and_the_registry_s_after_a_flip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """U2: Q7 while 2.0.0 is current; the current registry's own table after a flip."""
    assert display_load_bands() is Q7_REGISTERED_LOAD_BANDS

    monkeypatch.setattr(factor_registry, "CURRENT_CBA_REGISTRY", CBA_REGISTRY_3)

    assert CBA_REGISTRY_3.load_bands is not None
    assert display_load_bands() is CBA_REGISTRY_3.load_bands


def test_used_in_matching_follows_the_current_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """U3: false while 2.0.0 is current; true when a registry with bands is."""
    assert speaker_load.load_used_in_matching() is False

    monkeypatch.setattr(factor_registry, "CURRENT_CBA_REGISTRY", CBA_REGISTRY_3)

    assert speaker_load.load_used_in_matching() is True


def test_the_shipped_current_registry_is_untouched() -> None:
    """Guardrail: T8d reads the pointer; 2.0.0 stays current."""
    assert factor_registry.CURRENT_CBA_REGISTRY is factor_registry.CBA_REGISTRY
    assert factor_registry.current_cba_registry().version == factor_registry.REGISTRY_VERSION


# ---------------------------------------------------------------------------
# U4, U5 — labels per viewer
# ---------------------------------------------------------------------------


def _gaps() -> AssessedLoad:
    return _assess(
        _CAPACITY,
        _booking("a", offset_days=3, hours=None),
        _booking("b", offset_days=4, hours=None),
        _booking("c", offset_days=5, hours=None),
    )


def test_speaker_viewer_sees_every_title_and_nothing_is_editable() -> None:
    """U4: the Speaker's own engagements, every unit's, all titled; none editable."""
    own = _label(title="Corporate treasury guest lecture", host=VIEWER_UNIT)
    other = _label(title="Audit committee panel", host=OTHER_UNIT, origin="extraction")

    view = _view(_gaps(), [own, other], viewer=None)

    items = view.engagements_without_end_time
    assert [item.shown for item in items] == ["event", "event"]
    assert [item.event_title for item in items] == [
        "Corporate treasury guest lecture",
        "Audit committee panel",
    ]
    assert [item.engagement_id for item in items] == [own.record_id, other.record_id]
    assert all(item.editable_here is False for item in items)
    assert [item.local_date for item in items] == [AS_OF, AS_OF]
    assert [item.time_precision for item in items] == ["date_only", "date_only"]


def test_connector_viewer_hides_other_units_titles_and_marks_only_own_coordinator_entry_events_editable():  # noqa: E501
    """U5: own coordinator_entry editable; own extraction not; another unit anonymized."""
    own_entry = _label(title="Corporate treasury guest lecture", precision="exact")
    own_extracted = _label(title="Risk management seminar", origin="extraction")
    elsewhere = _label(title="Audit committee panel", host=OTHER_UNIT)

    view = _view(_gaps(), [own_entry, own_extracted, elsewhere], viewer=VIEWER_UNIT)

    first, second, third = view.engagements_without_end_time
    assert (first.shown, first.editable_here, first.engagement_id) == (
        "event",
        True,
        own_entry.record_id,
    )
    assert first.time_precision == "exact"
    assert (second.shown, second.editable_here, second.engagement_id) == (
        "event",
        False,
        own_extracted.record_id,
    )
    assert third.model_dump() == {
        "engagement_id": None,
        "shown": "other_unit",
        "event_title": None,
        "local_date": None,
        "time_precision": None,
        "editable_here": False,
    }

    as_speaker = _view(_gaps(), [own_entry, own_extracted, elsewhere], viewer=None)
    assert [item.engagement_id for item in as_speaker.engagements_without_end_time] == [
        own_entry.record_id,
        own_extracted.record_id,
        elsewhere.record_id,
    ]


# ---------------------------------------------------------------------------
# U6 — missing events, order and truncation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("viewer", [None, VIEWER_UNIT], ids=["speaker", "connector"])
def test_missing_event_is_event_missing(viewer: uuid.UUID | None) -> None:
    missing = _label(event=False)

    (item,) = _view(_gaps(), [missing], viewer=viewer).engagements_without_end_time

    assert item.model_dump() == {
        "engagement_id": missing.record_id,
        "shown": "event_missing",
        "event_title": None,
        "local_date": None,
        "time_precision": None,
        "editable_here": False,
    }


def test_labels_keep_repository_order_and_truncate_at_20() -> None:
    labels = [
        _label(title=f"Lecture {chr(ord('a') + index)}")
        for index in range(MAX_LISTED_WITHOUT_END_TIME + 1)
    ]

    view = _view(_gaps(), labels, viewer=None)

    assert MAX_LISTED_WITHOUT_END_TIME == 20
    assert [item.engagement_id for item in view.engagements_without_end_time] == [
        label.record_id for label in labels[:20]
    ]
    assert view.engagements_without_end_time_truncated is True
    assert _view(_gaps(), labels[:20]).engagements_without_end_time_truncated is False
    assert _view(_gaps(), labels[:3], has_more=True).engagements_without_end_time_truncated


def test_unresolved_event_keeps_its_title_and_has_no_date() -> None:
    unresolved = _label(precision="unresolved", resolved=None)

    (item,) = _view(_gaps(), [unresolved], viewer=VIEWER_UNIT).engagements_without_end_time

    assert (item.shown, item.local_date, item.time_precision) == ("event", None, "unresolved")


# ---------------------------------------------------------------------------
# U7 — no number anywhere in the load schema
# ---------------------------------------------------------------------------


def _types(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        kind = node.get("type")
        if isinstance(kind, str):
            yield kind
        elif isinstance(kind, list):
            yield from (k for k in kind if isinstance(k, str))
        for value in node.values():
            yield from _types(value)
    elif isinstance(node, list):
        for value in node:
            yield from _types(value)


@pytest.mark.parametrize("model", [SpeakerLoadView, EngagementWithoutEndTimeView])
def test_the_load_schema_holds_no_number(model: type[Any]) -> None:
    """U7: OQ-CBA-005 — a band word's inputs only; no integer, no number."""
    kinds = set(_types(model.model_json_schema()))
    assert "number" not in kinds
    assert "integer" not in kinds


# ---------------------------------------------------------------------------
# U8 — capacity None is never defaulted
# ---------------------------------------------------------------------------


def test_capacity_none_is_never_defaulted() -> None:
    """U8: no capacity → unknown / capacity_not_stated; the refs are still listed."""
    assessed = _assess(None, _booking("a", offset_days=3, hours=None))
    assert assessed.assessment.unknown_hours_refs == ("a",)

    view = _view(assessed, [_label()], viewer=None)

    assert (view.band, view.reason) == ("unknown", "capacity_not_stated")
    assert len(view.engagements_without_end_time) == 1
