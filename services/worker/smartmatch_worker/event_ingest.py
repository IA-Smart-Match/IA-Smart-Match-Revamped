"""The worker-side seam that carries fixture ingest into event persistence.

Three pieces existed and did not touch each other:

* ``smartmatch_domain.event_candidate`` — the Stage 0 parsers behind the
  contact-free wrapper, pure and I/O-free.
* ``smartmatch_providers.fixture_ingest`` — reads committed documents out of
  the checkout, runs them through those parsers, and resolves ADR-0012
  identity keys and tag vocabulary. It reaches no database, by design and by
  assertion.
* ``smartmatch_persistence.events`` — the only writer of ``event``,
  ``event_tag`` and ``discovery_review_item`` (migration ``0017``), which
  until now had no production caller at all.

This module is the join, and it is the *only* join: it imports the reader and
the writer and nothing else of consequence, so "how does a fixture become a
row" has one answer in one file rather than being distributed across whichever
caller happened to need it.

## Worker-side, and still not a command

G3 §9 puts every network action on the worker and leaves API handlers
"commands and review decisions only". This module honours the first half by
living here — but it deliberately does **not** register a command type in
``handlers.default_registry``. A routed ``events.ingest`` command would be an
HTTP-reachable trigger for extraction, which card S6b makes conditional on a
signed artifact calling for one, and no signed artifact does. So this is a
function an operator or a test calls directly against a session, and
``tests/unit/test_outreach_dryrun_wiring.py`` pins the shipped registry to
exactly ``test.noop`` and ``import.create`` — a guard this module leaves
intact rather than edits.

## No egress, still structurally

Nothing here imports an HTTP client, and the one input it accepts is a
directory underneath a caller-supplied root, which
``fixture_ingest.read_fixture_document`` refuses to interpret as a URL before
it touches the filesystem. ``ALLOW_LIVE_PROVIDERS`` is not consulted because
there is no live provider path to gate: the absence of a fetch function is the
control.

## Provenance names the document that was read, not the URL it advertises

Every fixture in the tree carries a ``URL:`` / ``"url"`` field pointing at
``example.edu`` — an IANA-reserved documentation domain that resolves to
nothing and that this process has never contacted. Writing that string into
``event.source_url`` would record a fetch that did not happen, which is
precisely the fabricated-evidence class ADR-0012's structured provenance
exists to close. So :data:`FIXTURE_URL_SCHEME` prefixes the document's path
*relative to the ingest root* instead: ``fixture:department/seminar_series.jsonld``
is a claim this repository can actually substantiate, and it stays true when
the checkout moves because it names no absolute path.

The candidate's own advertised URL is not discarded silently either — it is
already carried on ``ContactFreeEventCandidate.source_url`` and is simply not
what provenance means here. Nothing in this module concatenates provenance
into a title or a description; ``EventRepository.upsert`` takes ``title`` and
``provenance`` as separate parameters and writes them to separate columns.

## Unknown is not zero, and a refusal is not an empty document (ADR-0011)

:class:`IngestSummary` reports five numbers, and the split between them is the
point. ``documents_refused`` is not folded into ``documents_read``; an unkeyed
event is counted rather than dropped; and ``quarantined_tags`` is reported
separately from ``events_written`` so "everything landed cleanly" and
"everything landed and half of it needs a human" cannot produce the same
summary. A caller that reads only ``events_written`` still cannot mistake a
refused feed for a source that published nothing today, because
``documents_refused`` is a field it had to ignore on purpose.

## Nothing published

``EventRepository.publish`` is never called from here. G3 §5's review policy is
that "every first-seen event requires human approval", and an ingest that
published its own output would be the approval step deleting itself. Rows land
``unpublished``/``pending``, which is what ``event``'s server defaults already
say, and the coordinator routes in ``smartmatch_api.routers.events`` are where
a human sees them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

from smartmatch_domain.event_vocabulary import G3_VOCABULARY
from smartmatch_domain.events import EventProvenance, QuarantinedTag, TagVocabulary
from smartmatch_persistence.events import ORIGIN_EXTRACTION, EventRepository
from smartmatch_providers.fixture_ingest import (
    IngestedEvent,
    IngestReport,
    ingest_fixture_directory,
)
from sqlalchemy.orm import Session

__all__ = [
    "EXTRACTOR_VERSION",
    "FIXTURE_URL_SCHEME",
    "IngestSummary",
    "ingest_fixture_directory_into_events",
]

#: Stamped onto every row this path writes, as ``event.extractor_version``.
#: Names the *reader* that produced the row rather than a release of the
#: repository: a stored event should say which extraction behaviour it came out
#: of, and "the parsers plus the fixture reader, at this contract" is the honest
#: scope of that claim. Bumping it is a deliberate edit, the same way
#: ``VOCABULARY_VERSION`` is, so two rows carrying different values really were
#: produced by different code.
EXTRACTOR_VERSION: Final[str] = "fixture-ingest-1"

#: Prefix for the ``source_url`` this path records — see the module docstring.
#: A scheme rather than a bare path so the value is self-describing in a
#: database anyone might read later: ``fixture:campus_calendar.ics`` cannot be
#: mistaken for something that was fetched, and ``https://example.edu/...``
#: could be.
FIXTURE_URL_SCHEME: Final[str] = "fixture:"


@dataclass(frozen=True, slots=True)
class IngestSummary:
    """What one run of :func:`ingest_fixture_directory_into_events` did.

    Every field is a count of something that actually happened, and no field is
    derivable from another — which is what stops a caller reconstructing a
    reassuring total from a partial one.

    Attributes:
        documents_read: Recognized source documents that parsed. A document
            whose suffix names no format was skipped by the walk and is counted
            nowhere, because it was never a source.
        documents_refused: Recognized source documents the Stage 0 parsers
            refused as malformed. Separate from ``documents_read`` on purpose:
            a truncated feed that produced no events must not read as a feed
            that published none.
        events_written: Rows inserted or updated in ``event``. An update is
            counted here too — a second extraction of the same event is work
            this run did, and ADR-0012's whole point is that it resolves onto
            the first row rather than creating a second.
        events_unkeyed: Events whose source stated no resolvable date, so
            ADR-0012 gives them no identity key. Written, never dropped, and
            counted separately because they are the population that cannot
            de-duplicate and cannot publish (ADR-0010 rule 2).
        quarantined_tags: Tag values that did not map into the vocabulary and
            were escalated to ``discovery_review_item``. G3 §6.1 treats a
            non-zero count here as measurement, not failure.
    """

    documents_read: int
    documents_refused: int
    events_written: int
    events_unkeyed: int
    quarantined_tags: int


def _provenance(report: IngestReport, *, fetched_at: datetime) -> EventProvenance:
    """Build the provenance every event found in one document shares.

    ``report.source`` is the document's path relative to the ingest root,
    POSIX-style, which is what makes the recorded URL stable across machines
    and checkouts. See the module docstring for why the document's *own*
    advertised URL is not used.

    ``EventProvenance`` rejects a naive ``fetched_at`` itself, so this function
    performs no validation of its own — a second check here would be a second
    place for the rule to drift from the one the domain actually enforces.
    """
    return EventProvenance(
        source_url=f"{FIXTURE_URL_SCHEME}{report.source}",
        fetched_at=fetched_at,
        extractor_version=EXTRACTOR_VERSION,
    )


def _write_one(
    repository: EventRepository,
    session: Session,
    ingested: IngestedEvent,
    *,
    tenant_id: uuid.UUID,
    host_org_unit_id: uuid.UUID,
    provenance: EventProvenance,
    vocabulary: TagVocabulary,
) -> int:
    """Write one ingested event and its tags. Returns how many tags quarantined.

    ``origin=ORIGIN_EXTRACTION`` with provenance attached is the only shape
    ``ck_event_provenance_evidence`` admits for a row a parser produced, and
    ``EventRepository`` raises ``ProvenanceRequiredError`` before issuing a
    statement rather than letting the database answer. That exception is left
    to propagate: an extraction that cannot say where it came from is a defect
    in this seam, not a row to skip quietly.

    ``record_tags`` re-resolves each raw value through the domain rather than
    being handed ``ingested.mapped_tags``/``ingested.quarantined``. That is
    deliberate: the stored resolution and the ``quarantined_tag_count`` that
    ``ck_event_publishable`` reads must both come from the call that writes
    them, and passing a pre-resolved list would let this module's view of the
    vocabulary and the repository's diverge without either noticing.
    """
    candidate = ingested.candidate
    event_id = repository.upsert(
        session,
        tenant_id=tenant_id,
        host_org_unit_id=host_org_unit_id,
        title=candidate.title,
        event_time=candidate.event_time,
        origin=ORIGIN_EXTRACTION,
        provenance=provenance,
        description=candidate.description,
    )
    resolutions = repository.record_tags(
        session,
        tenant_id=tenant_id,
        event_id=event_id,
        owning_unit_id=host_org_unit_id,
        raw_values=candidate.raw_tags,
        vocabulary=vocabulary,
    )
    return sum(1 for resolution in resolutions if isinstance(resolution, QuarantinedTag))


def ingest_fixture_directory_into_events(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    host_org_unit_id: uuid.UUID,
    directory: str | Path,
    root: str | Path,
    source_time_zone: str,
    fetched_at: datetime,
    vocabulary: TagVocabulary = G3_VOCABULARY,
) -> IngestSummary:
    """Ingest every committed source document under ``directory`` into ``event``.

    Reads through ``smartmatch_providers.fixture_ingest`` — which refuses a URL
    before it touches the filesystem and refuses a path resolving outside
    ``root``, symlinks included — and writes through
    ``smartmatch_persistence.events.EventRepository``, the only module
    permitted to write these tables.

    Does not commit. Transaction boundaries belong to the caller here for the
    same reason they do in every repository in ``smartmatch_persistence``: a
    partial ingest committed halfway is worse than one rolled back whole, and
    the caller is the only party that knows what else is in the transaction.

    Args:
        session: An open session. Not committed and not rolled back here.
        tenant_id: The tenant every row is written under.
        host_org_unit_id: The org unit that hosts these events. This is
            ADR-0012's identity-key host component, supplied by the caller and
            deliberately never read out of the document — which is what makes
            two documents describing the same event resolve to one row.
        directory: The subtree of source documents to walk, absolute or
            relative to ``root``.
        root: The fixture tree everything must live under.
        source_time_zone: The IANA zone the sources declare, passed through to
            the Stage 0 parsers unchanged. An unknown zone is a parser refusal,
            never a substitution (ADR-0010 rule 1).
        fetched_at: The timezone-aware instant recorded as ``event.fetched_at``.
            Required rather than defaulted to "now": a caller replaying an
            ingest should be able to say when the reading happened, and a naive
            value is rejected by ``EventProvenance``.
        vocabulary: The closed tag vocabulary. Defaults to
            :data:`~smartmatch_domain.event_vocabulary.G3_VOCABULARY`, the
            twelve terms G3 §6.2 approved — a caller passing its own is
            expected to be a test, since growing the real one is a signed code
            change and not a parameter.

    Returns:
        An :class:`IngestSummary`. A refused document contributes to
        ``documents_refused`` and to nothing else; it does not raise, because
        one malformed feed beside three good ones is not a reason to write none
        of them.

    Raises:
        smartmatch_providers.fixture_ingest.FixtureRejected: ``directory`` is a
            URL, resolves outside ``root``, or is not a directory.
        ValueError: ``EventProvenance`` refused ``fetched_at`` as naive, or a
            candidate carried a blank title.
    """
    repository = EventRepository()
    reports = ingest_fixture_directory(
        directory,
        root=root,
        source_time_zone=source_time_zone,
        host_org_unit=str(host_org_unit_id),
        vocabulary=vocabulary,
    )

    documents_read = 0
    documents_refused = 0
    events_written = 0
    events_unkeyed = 0
    quarantined_tags = 0

    for report in reports:
        if report.refused:
            documents_refused += 1
            continue
        documents_read += 1
        provenance = _provenance(report, fetched_at=fetched_at)
        for ingested in report.events:
            quarantined_tags += _write_one(
                repository,
                session,
                ingested,
                tenant_id=tenant_id,
                host_org_unit_id=host_org_unit_id,
                provenance=provenance,
                vocabulary=vocabulary,
            )
            events_written += 1
            if not ingested.is_keyed:
                events_unkeyed += 1

    return IngestSummary(
        documents_read=documents_read,
        documents_refused=documents_refused,
        events_written=events_written,
        events_unkeyed=events_unkeyed,
        quarantined_tags=quarantined_tags,
    )
