"""``event`` / ``event_tag`` / ``discovery_review_item`` write path (migration ``0017``).

Cards S4 (deterministic identity and upsert) and S5 (vocabulary, quarantine,
review queue) of `docs/plans/2026-08-28-g3-events-s3-s5-plan.md`. Migration
``0017`` created the tables; this is the only module that writes them.

**No production caller wires this module yet, and that is deliberate.** The
same posture ``smartmatch_persistence.pipeline`` and
``smartmatch_persistence.attendance`` already hold: there is no crawler, no
event route, and no live fetch in this repository, and G3's standing
constraints keep it that way ("All network activity is worker-side; API
handlers record commands and review decisions only", §9). What exists here is
the write path a synthetic fixture or a coordinator's manual entry lands
against, tested against every CHECK ``0017`` declares, and left uncalled by
production code until the card that legitimately calls it arrives.

The identity decision is made in the domain, not here
------------------------------------------------------
:meth:`EventRepository.upsert` calls
``smartmatch_domain.events.resolve_identity_key`` and branches on whether it
returned a key. That split is deliberate and matches
``jobs.JobRepository.transition`` against ``smartmatch_domain.jobs``: the rule
about *what* an identity is belongs to the pure layer where it can be tested
without a database, and this module only decides which statement expresses it.

Two statements, because unkeyed is a different write from keyed:

* **A resolved event** (`ExactTime` or `DateOnlyTime`) has a key, so the
  insert carries ``ON CONFLICT ON CONSTRAINT uq_event_identity DO UPDATE``.
  A second extraction of the same event — from the university calendar, the
  department page, an aggregator — computes the identical key and updates the
  row rather than inserting a second one. That is ADR-0012's whole point, and
  the reason the key is keyed on host org unit rather than source domain.
* **An unresolved event** has no key at all, and gets a plain insert. ADR-0012:
  "Two events with unknown dates are not evidence of being the same event, and
  a key that ignores the date would merge them." There is no ``ON CONFLICT``
  clause on that path, because there is no conflict to resolve —
  ``resolved_date`` is NULL and PostgreSQL's UNIQUE treats NULLs as distinct,
  so two such rows coexist by construction rather than by a branch anyone has
  to remember.

Provenance is written, never concatenated
-------------------------------------------
:meth:`upsert` takes ``title`` and ``provenance`` as separate parameters and
writes them to separate columns. There is no code path in this module, or in
``smartmatch_domain.events``, that produces a string combining the two — which
is how ADR-0012's "titles carrying their source" defect stays closed without
depending on a caller remembering a convention.

The quarantine path, and the counter it maintains
---------------------------------------------------
:meth:`record_tags` resolves every raw value through
``smartmatch_domain.events.resolve_tag`` and writes each outcome to
``event_tag``. A quarantined value additionally gets a
``discovery_review_item`` row — G3 §5's escalation destination, chosen there
over ``review_item`` because ``review_item`` cascades from ``import_batch``
and a discovery finding parked on it would be deleted with an unrelated
import.

It then writes ``event.quarantined_tag_count`` from a ``SELECT count(*)`` over
the tags it just wrote, rather than incrementing. Recomputing is what makes
the method idempotent: re-resolving the same extraction inserts no new tag
rows (both ``ON CONFLICT DO NOTHING``), and an increment would still raise the
counter, drifting the number away from the rows it is supposed to count and —
because ``ck_event_publishable`` reads it — silently making a clean event
unpublishable.

Publishing is refused, twice
------------------------------
:meth:`publish` checks the two ADR-pinned reasons in application code and
raises :class:`EventNotPublishableError` naming the constraint, then issues an
``UPDATE`` whose ``WHERE`` clause repeats both conditions.
``ck_event_publishable`` is what still holds the line if either guard were
skipped, wrong, or raced — the same three-layer arrangement
``pipeline.advance_stage`` uses against ``ck_pipeline_record_stage_order``.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from typing import Final, cast

import sqlalchemy as sa
from smartmatch_domain.events import (
    DateOnlyTime,
    EventProvenance,
    EventTime,
    ExactTime,
    MappedTag,
    QuarantinedTag,
    TagResolution,
    TagVocabulary,
    normalize_title,
    precision_of,
    resolve_identity_key,
    resolve_tag,
    resolved_date,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from smartmatch_persistence import schema

__all__ = [
    "EVENT_ORIGINS",
    "ORIGIN_COORDINATOR_ENTRY",
    "ORIGIN_EXTRACTION",
    "EventNotPublishableError",
    "EventRepository",
    "ProvenanceRequiredError",
    "quarantined_values",
]

#: A coordinator typed this event in. ADR-0012: "Manual event entry uses the
#: same key and the same vocabulary. A coordinator typing an event is not
#: exempt, or the duplicate class reopens through a second door."
ORIGIN_COORDINATOR_ENTRY: Final[str] = "coordinator_entry"

#: An extractor produced this event, and must say from where.
ORIGIN_EXTRACTION: Final[str] = "extraction"

#: ``event.origin``'s closed vocabulary — mirrors ``ck_event_origin`` exactly.
EVENT_ORIGINS: Final[frozenset[str]] = frozenset({ORIGIN_COORDINATOR_ENTRY, ORIGIN_EXTRACTION})


class ProvenanceRequiredError(ValueError):
    """An ``extraction`` event named no source, or a manual one named a source.

    The application-code twin of ``ck_event_provenance_evidence``. Raised
    before any statement is issued so a caller gets a message naming the
    constraint rather than a database round-trip that ends in
    ``IntegrityError`` — the same courtesy
    :meth:`~smartmatch_persistence.attendance.AttendanceRepository.record_attendance`
    extends for ``ck_attendance_record_method``.
    """


class EventNotPublishableError(ValueError):
    """The event cannot publish: its date is unresolved, or it has quarantined tags.

    ADR-0010 rule 2 and ADR-0012's quarantine rule, refused in application code
    before the ``UPDATE``. ``ck_event_publishable`` refuses the same write at
    the database, and that is the guarantee; this exception exists so the
    ordinary case is a catchable error naming which of the two reasons applied.
    """


def _temporal_columns(event_time: EventTime) -> dict[str, object]:
    """The four ADR-0010 columns an ``EventTime`` writes, and no others.

    Every branch names all four keys, including the ones it sets to ``None``.
    An ``UPDATE`` that omitted a column would leave the previous extraction's
    ``starts_at`` on a row that has since become ``date_only`` — a fabricated
    instant surviving a correction, which is exactly the class ADR-0010 closes.
    """
    if isinstance(event_time, ExactTime):
        return {
            "starts_at": event_time.starts_at,
            "on_date": None,
            "time_zone": event_time.time_zone,
            "time_precision": str(precision_of(event_time)),
        }
    if isinstance(event_time, DateOnlyTime):
        return {
            "starts_at": None,
            "on_date": event_time.on_date,
            "time_zone": event_time.time_zone,
            "time_precision": str(precision_of(event_time)),
        }
    return {
        "starts_at": None,
        "on_date": None,
        "time_zone": None,
        "time_precision": str(precision_of(event_time)),
    }


def _provenance_columns(origin: str, provenance: EventProvenance | None) -> dict[str, object]:
    """The three provenance columns, checked against ``origin`` first."""
    if origin not in EVENT_ORIGINS:
        raise ValueError(
            f"origin must be one of {sorted(EVENT_ORIGINS)}, not {origin!r} (ck_event_origin)"
        )
    if origin == ORIGIN_EXTRACTION and provenance is None:
        raise ProvenanceRequiredError(
            "an extraction event must carry EventProvenance — source URL, fetch time, and "
            "extractor version (ck_event_provenance_evidence). An extracted event that "
            "cannot say where it came from is the fabricated-field defect, not a lesser "
            "form of it."
        )
    if origin == ORIGIN_COORDINATOR_ENTRY and provenance is not None:
        raise ProvenanceRequiredError(
            "a coordinator_entry event must not carry EventProvenance "
            "(ck_event_provenance_evidence): a human typing an event has no source URL, "
            "and recording one would attribute their entry to a page nobody fetched."
        )
    if provenance is None:
        return {"source_url": None, "fetched_at": None, "extractor_version": None}
    return {
        "source_url": provenance.source_url,
        "fetched_at": provenance.fetched_at,
        "extractor_version": provenance.extractor_version,
    }


class EventRepository:
    """Writes ``event``, ``event_tag``, and ``discovery_review_item``.

    Takes a session per call, like every other repository in this package
    (``jobs.py``, ``review.py``, ``pipeline.py``, ``attendance.py``):
    transaction boundaries belong to the caller, and no method here commits.
    """

    def upsert(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        host_org_unit_id: uuid.UUID,
        title: str,
        event_time: EventTime,
        origin: str,
        provenance: EventProvenance | None = None,
        description: str | None = None,
    ) -> uuid.UUID:
        """Insert this event, or update the one its identity key already names.

        Computes ADR-0012's key with
        ``smartmatch_domain.events.resolve_identity_key`` and branches on the
        answer — see the module docstring for why the unkeyed path is a
        different statement rather than the same one with a NULL in it.

        ``host_org_unit_id`` is the key's host component and is passed to the
        domain as its string form. ADR-0012 specifies a folding rule for the
        title only and expects the org unit to be "a stable identifier from
        another table rather than free text", which a UUID is.

        Returns:
            ``event.id`` — freshly inserted, or the id of the row this event's
            identity key already named.

        Raises:
            ValueError: ``origin`` is outside :data:`EVENT_ORIGINS`, or
                ``title`` is blank (from the domain).
            ProvenanceRequiredError: ``origin`` and ``provenance`` disagree.
        """
        columns: dict[str, object] = {
            "tenant_id": tenant_id,
            "host_org_unit_id": host_org_unit_id,
            "title": title,
            "normalized_title": normalize_title(title),
            "description": description,
            "resolved_date": resolved_date(event_time),
            "origin": origin,
            **_temporal_columns(event_time),
            **_provenance_columns(origin, provenance),
        }

        identity = resolve_identity_key(
            host_org_unit=str(host_org_unit_id), title=title, event_time=event_time
        )
        insert = postgresql.insert(schema.event).values(id=uuid.uuid4(), **columns)

        if identity is None:
            # No key: ADR-0012 leaves this row unmatchable and distinct. A
            # plain insert, and nothing to conflict with.
            unkeyed = session.execute(insert.returning(schema.event.c.id)).scalar_one()
            return cast(uuid.UUID, unkeyed)

        # Keyed: the second extraction of the same event updates the first.
        # Every non-key column is refreshed, including the ones this call is
        # setting to NULL — see _temporal_columns.
        updated = {
            key: value
            for key, value in columns.items()
            # The four identity columns are what was matched on; rewriting
            # them with the same values would be noise, and rewriting them
            # with different ones is impossible by construction.
            if key not in ("tenant_id", "host_org_unit_id", "normalized_title", "resolved_date")
        }
        updated["updated_at"] = sa.func.now()
        keyed = session.execute(
            insert.on_conflict_do_update(constraint="uq_event_identity", set_=updated).returning(
                schema.event.c.id
            )
        ).scalar_one()
        return cast(uuid.UUID, keyed)

    def record_tags(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        event_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        raw_values: Iterable[str],
        vocabulary: TagVocabulary,
    ) -> tuple[TagResolution, ...]:
        """Resolve each raw value, store it, and escalate the unmapped ones.

        Every value goes through ``smartmatch_domain.events.resolve_tag``, so
        the mapped/quarantined decision is made in the pure layer and this
        method only persists it. Both inserts are ``ON CONFLICT DO NOTHING``
        against ``event_tag``'s two natural keys, so re-resolving the same
        extraction is a no-op rather than a duplicate row.

        A quarantined value also lands one ``discovery_review_item`` row —
        G3 §5's escalation destination. That insert is idempotent on
        ``uq_discovery_review_item_event_value``, so a re-resolved extraction
        does not re-queue a value a reviewer has already decided.

        Finally ``event.quarantined_tag_count`` is **recomputed** from the
        stored rows rather than incremented; see the module docstring for why
        an increment would drift.

        Returns:
            The resolutions, in the order the raw values arrived — so a caller
            can see which quarantined without re-reading the table.
        """
        resolutions: list[TagResolution] = [
            resolve_tag(raw_value, vocabulary) for raw_value in raw_values
        ]

        for resolution in resolutions:
            if isinstance(resolution, MappedTag):
                session.execute(
                    postgresql.insert(schema.event_tag)
                    .values(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        event_id=event_id,
                        resolution="mapped",
                        term=resolution.term,
                        raw_value=None,
                        vocabulary_version=resolution.vocabulary_version,
                    )
                    .on_conflict_do_nothing(constraint="uq_event_tag_term")
                )
                continue

            # No cast: the `isinstance(resolution, MappedTag)` branch above
            # ends in `continue`, so `TagResolution`'s union is already
            # narrowed to `QuarantinedTag` here and mypy says so.
            quarantined = resolution
            session.execute(
                postgresql.insert(schema.event_tag)
                .values(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    event_id=event_id,
                    resolution="quarantined",
                    term=None,
                    raw_value=quarantined.raw_value,
                    vocabulary_version=quarantined.vocabulary_version,
                )
                .on_conflict_do_nothing(constraint="uq_event_tag_raw_value")
            )
            session.execute(
                postgresql.insert(schema.discovery_review_item)
                .values(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    owning_unit_id=owning_unit_id,
                    event_id=event_id,
                    kind="unmapped_tag",
                    raw_value=quarantined.raw_value,
                    vocabulary_version=quarantined.vocabulary_version,
                )
                .on_conflict_do_nothing(constraint="uq_discovery_review_item_event_value")
            )

        self._refresh_quarantined_tag_count(session, tenant_id=tenant_id, event_id=event_id)
        return tuple(resolutions)

    def matchable_terms(
        self, session: Session, *, tenant_id: uuid.UUID, event_id: uuid.UUID
    ) -> tuple[str, ...]:
        """The event's mapped terms. A quarantined value cannot appear here.

        ADR-0012: a quarantined value is "never rendered and never matched on".
        The filter is ``resolution = 'mapped'``, and it is belt to
        ``ck_event_tag_resolution_shape``'s braces: a quarantined row's
        ``term`` column is NULL, so even a query that forgot this predicate
        would surface no term to match on.
        """
        rows = session.execute(
            sa.select(schema.event_tag.c.term)
            .where(
                schema.event_tag.c.tenant_id == tenant_id,
                schema.event_tag.c.event_id == event_id,
                schema.event_tag.c.resolution == "mapped",
            )
            .order_by(schema.event_tag.c.term)
        ).scalars()
        return tuple(str(term) for term in rows)

    def publish(self, session: Session, *, tenant_id: uuid.UUID, event_id: uuid.UUID) -> None:
        """Move the event to ``published``, or refuse and say which rule stopped it.

        Raises:
            EventNotPublishableError: the event's date is unresolved
                (ADR-0010 rule 2), it carries quarantined tags (ADR-0012), or
                no such event exists in this tenant.
        """
        row = session.execute(
            sa.select(schema.event.c.time_precision, schema.event.c.quarantined_tag_count).where(
                schema.event.c.tenant_id == tenant_id,
                schema.event.c.id == event_id,
            )
        ).one_or_none()
        if row is None:
            raise EventNotPublishableError(f"no event {event_id} in tenant {tenant_id} to publish")
        if row.time_precision == "unresolved":
            raise EventNotPublishableError(
                f"event {event_id} has no resolved date, so it cannot reach a publishable "
                "state (ADR-0010 rule 2, ck_event_publishable). It has no identity key "
                "either, and both are the same fact about it."
            )
        if row.quarantined_tag_count:
            raise EventNotPublishableError(
                f"event {event_id} carries {row.quarantined_tag_count} quarantined tag(s) "
                "awaiting review, so it cannot publish (ADR-0012, ck_event_publishable). "
                "A human resolves them through discovery_review_item."
            )

        # The WHERE clause repeats both conditions: between the SELECT above
        # and this UPDATE, a concurrent record_tags could have quarantined a
        # tag on this row. The database CHECK would refuse the write anyway;
        # repeating the predicate makes it a no-op rather than an
        # IntegrityError the caller has to interpret.
        session.execute(
            sa.update(schema.event)
            .where(
                schema.event.c.tenant_id == tenant_id,
                schema.event.c.id == event_id,
                schema.event.c.time_precision != "unresolved",
                schema.event.c.quarantined_tag_count == 0,
            )
            .values(publication_status="published", updated_at=sa.func.now())
        )

    def _refresh_quarantined_tag_count(
        self, session: Session, *, tenant_id: uuid.UUID, event_id: uuid.UUID
    ) -> None:
        """Set the counter to the number of quarantined tags actually stored."""
        count = (
            sa.select(sa.func.count())
            .select_from(schema.event_tag)
            .where(
                schema.event_tag.c.tenant_id == tenant_id,
                schema.event_tag.c.event_id == event_id,
                schema.event_tag.c.resolution == "quarantined",
            )
        )
        session.execute(
            sa.update(schema.event)
            .where(
                schema.event.c.tenant_id == tenant_id,
                schema.event.c.id == event_id,
            )
            .values(
                quarantined_tag_count=count.scalar_subquery(),
                updated_at=sa.func.now(),
            )
        )


def quarantined_values(resolutions: Sequence[TagResolution]) -> tuple[str, ...]:
    """The raw values among ``resolutions`` that did not map.

    A convenience over ``smartmatch_domain.events.quarantined_tags`` for
    callers that want the strings rather than the objects. Lives here rather
    than in the domain because the domain deliberately returns the typed
    values — a function handing back bare strings is the shape that lets a
    quarantined value be mistaken for a matchable one, and it belongs on the
    side of the boundary that already knows the difference.
    """
    return tuple(r.raw_value for r in resolutions if isinstance(r, QuarantinedTag))
