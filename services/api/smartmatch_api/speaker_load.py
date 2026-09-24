"""A Speaker's current load band, computed at request time (B26 T8d §4.2).

Both availability routes — the Connector's
``/v1/units/{unit_id}/speaker-contacts/{professional_id}/availability`` (T3)
and the Speaker's own ``/v1/me/availability`` (T6b-2) — carry a ``load`` block.
It is computed here, on every ``GET`` and ``PATCH``, with the exact code a 3.x
run uses: T8c's :class:`~smartmatch_persistence.engagement_load.EngagementLoadRepository`
and :func:`~smartmatch_domain.load_bands.assess_pool_loads`, which call T8b's
``compute_eli``. So the panel and the next run agree.

## Registry 3.0.0 is proposed, and this module only reads the pointer

The band table is the current registry's when it has one, else the Q7 table
3.0.0 declares (:data:`~smartmatch_domain.load_bands.Q7_REGISTERED_LOAD_BANDS`).
``used_in_matching`` is ``current_cba_registry().load_bands is not None``:
false today, so every surface says "Matching does not use workload yet"
(OQ-1). Nothing here makes 3.0.0 current or scores anything.

## Unit privacy

The load read is tenant-wide (T8c OQ2): every unit's booking of the person
counts. The Speaker sees all of their own engagements. A Connector sees an
engagement another unit hosts only as "other_unit": no title, date, precision
or record id (plan-gate MED 1).

## Query cost

One statement for the engagements, and one more only when some engagement has
no end time (the labels). Two at most.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Final

from smartmatch_domain.availability_verdict import as_of_utc
from smartmatch_domain.factor_registry import current_cba_registry
from smartmatch_domain.load_bands import (
    Q7_REGISTERED_LOAD_BANDS,
    AssessedLoad,
    RegisteredLoadBands,
    assess_pool_loads,
)
from smartmatch_persistence.engagement_labels import EngagementLabel, EngagementLabelRepository
from smartmatch_persistence.engagement_load import EngagementLoadRepository
from sqlalchemy.orm import Session

from smartmatch_api.routers.speaker_availability_models import (
    EngagementWithoutEndTimeView,
    SpeakerLoadView,
)

__all__ = [
    "MAX_LISTED_WITHOUT_END_TIME",
    "current_speaker_load",
    "display_load_bands",
    "load_used_in_matching",
    "speaker_load_view",
]

#: At most this many engagements without an end time are listed per response.
MAX_LISTED_WITHOUT_END_TIME: Final[int] = 20

#: The only origin whose event time a Connector can edit (``manual_events.py``).
_EDITABLE_ORIGIN: Final[str] = "coordinator_entry"

_engagement_load: Final[EngagementLoadRepository] = EngagementLoadRepository()
_engagement_labels: Final[EngagementLabelRepository] = EngagementLabelRepository()


def display_load_bands() -> RegisteredLoadBands:
    """The current registry's band table, else the Q7 table 3.0.0 declares (D2)."""
    bands = current_cba_registry().load_bands
    return Q7_REGISTERED_LOAD_BANDS if bands is None else bands


def load_used_in_matching() -> bool:
    """Whether the registry new runs score under applies engagement load. Read only."""
    return current_cba_registry().load_bands is not None


def current_speaker_load(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    professional_id: uuid.UUID,
    capacity: Decimal | None,
    viewer_unit_id: uuid.UUID | None,
    now: datetime,
) -> SpeakerLoadView:
    """One Speaker's load band as of ``now``'s UTC date, labelled for the viewer.

    Args:
        session: The caller's session; never committed.
        tenant_id: The tenant; every unit's bookings in it count (T8c OQ2).
        professional_id: The Speaker.
        capacity: The stored declared capacity, or ``None`` (never a default, Q6).
        viewer_unit_id: The Connector's unit, or ``None`` for the Speaker.
        now: The handler's one ``utc_now()``.

    Returns:
        The ``load`` block: band, reason, date, whether matching uses it, and
        the engagements without an end time.
    """
    as_of = as_of_utc(now)
    engagements = _engagement_load.engagements_for(
        session, tenant_id=tenant_id, professional_ids=[professional_id], as_of=as_of
    )
    assessed = assess_pool_loads(
        [professional_id],
        capacities={professional_id: capacity},
        engagements=engagements,
        as_of=as_of,
        bands=display_load_bands(),
    )[professional_id]
    refs = assessed.assessment.unknown_hours_refs
    labels: tuple[EngagementLabel, ...] = ()
    if refs:
        labels = _engagement_labels.labels_for(
            session,
            tenant_id=tenant_id,
            record_ids=[uuid.UUID(ref) for ref in refs],
            limit=MAX_LISTED_WITHOUT_END_TIME + 1,
        )
    return speaker_load_view(
        assessed,
        labels[:MAX_LISTED_WITHOUT_END_TIME],
        has_more=len(labels) > MAX_LISTED_WITHOUT_END_TIME,
        used_in_matching=load_used_in_matching(),
        viewer_unit_id=viewer_unit_id,
    )


def speaker_load_view(
    assessed: AssessedLoad,
    labels: Sequence[EngagementLabel],
    *,
    has_more: bool,
    used_in_matching: bool,
    viewer_unit_id: uuid.UUID | None,
) -> SpeakerLoadView:
    """Render one assessment and its labels as the wire's ``load`` block. Pure.

    Labels keep the repository's order; at most
    :data:`MAX_LISTED_WITHOUT_END_TIME` are listed, and ``truncated`` is set when
    more exist.
    """
    assessment = assessed.assessment
    return SpeakerLoadView(
        band=assessment.band.value,
        reason=assessment.reason.value,
        as_of=assessed.as_of,
        used_in_matching=used_in_matching,
        engagements_without_end_time=[
            _item(label, viewer_unit_id) for label in labels[:MAX_LISTED_WITHOUT_END_TIME]
        ],
        engagements_without_end_time_truncated=(
            has_more or len(labels) > MAX_LISTED_WITHOUT_END_TIME
        ),
    )


def _item(label: EngagementLabel, viewer_unit_id: uuid.UUID | None) -> EngagementWithoutEndTimeView:
    """One label as this viewer may see it (plan §4.2 label table)."""
    if label.event_id is None:
        return EngagementWithoutEndTimeView(
            engagement_id=label.record_id,
            shown="event_missing",
            event_title=None,
            local_date=None,
            time_precision=None,
            editable_here=False,
        )
    hosted_here = viewer_unit_id is not None and label.host_org_unit_id == viewer_unit_id
    if viewer_unit_id is not None and not hosted_here:
        # Another unit's engagement, seen by a Connector: counted, never named.
        return EngagementWithoutEndTimeView(
            engagement_id=None,
            shown="other_unit",
            event_title=None,
            local_date=None,
            time_precision=None,
            editable_here=False,
        )
    return EngagementWithoutEndTimeView(
        engagement_id=label.record_id,
        shown="event",
        event_title=label.title,
        local_date=label.resolved_date,
        time_precision=label.time_precision,  # type: ignore[arg-type]
        editable_here=hosted_here and label.origin == _EDITABLE_ORIGIN,
    )
