"""Event temporal model and tag vocabulary.

Architecture v1.1 §1.5, §3.1, §3.6 N1, gate G3. Implements the pure domain
logic pinned by two Accepted ADRs — the `event` and `event_tag` tables
themselves are not implemented here; they are deferred to R2 behind open
decisions D6-D8 (`docs/architecture/engagement-model.md`), and the vocabulary's
actual terms are deferred to S5 behind gate G3. This module is the contract
those land against.

**ADR-0010 — an event carries an instant, a zone, and a precision.** The
stakeholder test log of 19-20 August 2026 found events rendered at 3 AM and
7 AM (Fix #6) and events with no resolved date at all, silently fabricated
into one anyway (Fix #4, and see `docs/plans/frontend-migration.md:231`,
finding H21, for the legacy's `date: "See link for details"`). A nullable
`starts_at` can express only "known" or "unknown"; it cannot express
`date_only`, which is what "Thursday 14 September, on campus" actually is, and
inferring `date_only` from a midnight timestamp mislabels events that
genuinely start at midnight. `TimePrecision` and the three `EventTime`
variants below make the distinction a type, not an inference — the same
discipline `ics.generate_ics` already applies to its own output
(`UnschedulableEventError`), generalized so every future caller inherits it
instead of re-deriving it.

**ADR-0012 — deterministic identity, structured provenance, closed
vocabulary.** Three defects, all properties of an extraction pipeline that
does not exist yet (`MM-A08` is `REPLACE`/archived, deferred to R3): the same
event inserted twice because two pages described it; a title carrying the name
of the page it was scraped from; and an open-ended tag set that could not be
compared week to week. This module provides the deterministic identity key
(`resolve_identity_key`), a provenance type that cannot be smuggled into a
title (`EventProvenance`), and a versioned-vocabulary mapping that makes an
unmapped tag value unconstructible as a matchable one (`resolve_tag`,
`MappedTag`, `QuarantinedTag`).

What this module deliberately does **not** decide, because ADR-0012 does not
decide it either:

* The vocabulary's actual 10-12 terms. "Picking them in an ADR would be
  exactly the kind of silent decision this document exists to prevent" —
  `TagVocabulary` is the mechanism that decision plugs into once S5 makes it.
* Whether "role" tags and "type" tags (the ADR's own words) are drawn from one
  shared vocabulary or two separate ones. Construct one `TagVocabulary` per
  namespace if and when that split is made; nothing here assumes either
  answer.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import TypeAlias

__all__ = [
    "DateOnlyTime",
    "EventIdentityKey",
    "EventProvenance",
    "EventTime",
    "ExactTime",
    "MappedTag",
    "QuarantinedTag",
    "TagResolution",
    "TagVocabulary",
    "TimePrecision",
    "UnresolvedTime",
    "is_resolved",
    "matchable_tags",
    "normalize_tag_value",
    "normalize_title",
    "precision_of",
    "quarantined_tags",
    "resolve_identity_key",
    "resolve_tag",
    "resolved_date",
]


# ---------------------------------------------------------------------------
# Shared validation helpers
# ---------------------------------------------------------------------------


def _require_non_blank(value: str, field: str) -> None:
    """Reject an empty or whitespace-only string."""
    if not value or not value.strip():
        raise ValueError(f"{field} must be a non-blank string")


def _require_aware_datetime(value: datetime, field: str) -> None:
    """Reject a naive datetime.

    Mirrors `ics._require_aware`'s rule for the same reason: a naive datetime
    treated as a real instant silently claims a timezone (usually UTC) it
    never carried. Not imported from `ics` directly — that module's
    `UnschedulableEventError` is specific to invite generation, and event
    construction here is a different concern that fails with a plain
    `ValueError` instead.
    """
    if not isinstance(value, datetime):
        raise ValueError(f"{field} must be a datetime; got {type(value).__name__}")
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(
            f"{field} must be timezone-aware. A naive value treated as an instant "
            "silently claims a timezone it never carried."
        )


def _fold(text: str) -> str:
    """Case-fold, then collapse every run of non-alphanumeric characters to one space.

    The technique `ingest.normalize_header` already uses for column headers,
    reused here for the same reason: replacing punctuation with a boundary
    rather than deleting it outright avoids silently merging two words into
    one. `"AI-Panel"` and `"AI Panel"` must compare equal; deleting the hyphen
    instead of replacing it would turn the first into `"aipanel"` and produce
    a different result than the second's `"ai panel"`.

    Deliberately does not: fold Unicode accents/diacritics, stem, resolve
    synonyms, or otherwise approximate. ADR-0012 rejects fuzzy identity
    matching outright ("a threshold nobody can justify is a worse contract
    than a key anyone can recompute") — this is exact and reproducible, not a
    similarity measure, and the same discipline is applied here to tag
    matching even though the ADR's fuzzy-matching rejection was written about
    titles.
    """
    folded = text.casefold()
    boundary = "".join(ch if ch.isalnum() else " " for ch in folded)
    return " ".join(boundary.split())


def normalize_title(title: str) -> str:
    """Fold a title for identity comparison (ADR-0012).

    Case-folded, whitespace-collapsed, punctuation-stripped — the exact three
    steps ADR-0012 names for the identity key's title component, applied by
    `_fold`. Does not attempt to detect or strip a source-page name: ADR-0012
    keeps provenance out of the title by keeping it a separate field
    (`EventProvenance`) that this function does not even accept as a
    parameter, not by pattern-matching text back out of a title that should
    never have contained it in the first place.
    """
    _require_non_blank(title, "title")
    return _fold(title)


def normalize_tag_value(value: str) -> str:
    """Fold a raw extracted tag value the same way vocabulary terms compare.

    Same technique as `normalize_title` — see `_fold` for what folds together
    and what deliberately does not. Kept as a separate public function because
    tag matching and title identity are different concerns that happen to
    share an algorithm today; a future divergence should not force a change to
    both call sites.
    """
    _require_non_blank(value, "value")
    return _fold(value)


# ---------------------------------------------------------------------------
# ADR-0010 — temporal model
# ---------------------------------------------------------------------------


class TimePrecision(StrEnum):
    """How much of an event's instant is actually known (ADR-0010).

    Three states, not a nullable instant: a nullable `starts_at` can only say
    "known" or "unknown" and cannot express `DATE_ONLY`, which ADR-0010
    identifies as the case that produced the visible stakeholder-facing bug —
    events rendered at 3 AM / 7 AM from a date-only source collapsed to
    midnight and re-rendered in the wrong zone.
    """

    EXACT = "exact"
    DATE_ONLY = "date_only"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class ExactTime:
    """A real instant, plus the zone the event happens in (ADR-0010 rule 1).

    Attributes:
        starts_at: The instant. Must be timezone-aware — see
            `_require_aware_datetime`.
        time_zone: An IANA zone name, e.g. `"America/Los_Angeles"` — the
            event's own zone, never the viewer's or the server's. Checked only
            for being a non-blank string: validating it against the real IANA
            database needs `zoneinfo`, which reads tzdata from disk, and the
            domain layer performs no I/O (ADR-0002, the import-linter contract
            "Domain is pure"). A real-but-misspelled zone name is an
            adapter-layer concern to catch, not this one's.
    """

    starts_at: datetime
    time_zone: str

    def __post_init__(self) -> None:
        _require_aware_datetime(self.starts_at, "starts_at")
        _require_non_blank(self.time_zone, "time_zone")


@dataclass(frozen=True, slots=True)
class DateOnlyTime:
    """A calendar date with no clock time (ADR-0010).

    The honest representation of "Thursday 14 September, on campus" — real
    information that is not an instant. There is deliberately no `starts_at`
    field on this type: collapsing a date-only event to a midnight `datetime`
    is exactly the fabrication that produced the stakeholder-visible defect,
    and it cannot happen here because the field that would hold a fabricated
    instant does not exist on this type.
    """

    on_date: date
    time_zone: str

    def __post_init__(self) -> None:
        _require_non_blank(self.time_zone, "time_zone")


@dataclass(frozen=True, slots=True)
class UnresolvedTime:
    """No date could be resolved at all (ADR-0010).

    Carries no fields. There is nothing on this type a caller could
    accidentally read as a date or an instant — reaching one means holding an
    `ExactTime` or a `DateOnlyTime` instead, which means the date was actually
    resolved. `resolved_date` returns `None` for this case, and
    `resolve_identity_key` propagates that into "no identity key" (ADR-0012):
    "an `unresolved` event has no identity key and cannot be resolved against
    anything."
    """


#: An event's time, at whichever precision it is actually known. A discriminated
#: union rather than one class with optional fields, so a caller who has not
#: narrowed the type cannot reach `.starts_at` or `.on_date` at all — the
#: illegal state (treating an unresolved or date-only event as precise) does
#: not type-check, rather than merely being disallowed by a runtime check.
EventTime: TypeAlias = ExactTime | DateOnlyTime | UnresolvedTime


def precision_of(event_time: EventTime) -> TimePrecision:
    """The `TimePrecision` an `EventTime` value represents."""
    if isinstance(event_time, ExactTime):
        return TimePrecision.EXACT
    if isinstance(event_time, DateOnlyTime):
        return TimePrecision.DATE_ONLY
    return TimePrecision.UNRESOLVED


def is_resolved(event_time: EventTime) -> bool:
    """Whether `event_time` carries enough information to matter downstream.

    False only for `UnresolvedTime`. ADR-0010 rule 2: "An event at
    `unresolved` cannot reach a matchable or publishable state" — a
    generalization of the rule `ics.generate_ics` already enforced for its own
    output alone (`UnschedulableEventError`), now available to every caller
    instead of just that one.
    """
    return not isinstance(event_time, UnresolvedTime)


def resolved_date(event_time: EventTime) -> date | None:
    """The calendar date ADR-0012 folds into the identity key, or `None`.

    * `ExactTime` -> the date component of `starts_at`, taken exactly as
      given. This does **not** convert `starts_at` into `time_zone` before
      taking its date — that conversion needs the system timezone database,
      which is I/O the domain layer does not perform. Only very close to local
      midnight can the UTC date and the event's local date differ; a caller
      that needs the local calendar date must resolve that before constructing
      `ExactTime`. This module folds the date it is given; it deliberately
      does not try to see across a zone boundary it has no way to see across
      correctly.
    * `DateOnlyTime` -> `on_date`, unchanged.
    * `UnresolvedTime` -> `None`.
    """
    if isinstance(event_time, ExactTime):
        return event_time.starts_at.date()
    if isinstance(event_time, DateOnlyTime):
        return event_time.on_date
    return None


# ---------------------------------------------------------------------------
# ADR-0012 — deterministic identity and structured provenance
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EventProvenance:
    """Where an extracted event's data came from (ADR-0012).

    Recorded as its own structured value, never folded into a display string.
    This module has no function that accepts both a title (or a tag) and an
    `EventProvenance` and returns a combined string — "never part of the
    title" is therefore not a convention a caller has to remember to honor;
    there is no code path here that could smuggle one into the other.
    """

    source_url: str
    fetched_at: datetime
    extractor_version: str

    def __post_init__(self) -> None:
        _require_non_blank(self.source_url, "source_url")
        _require_non_blank(self.extractor_version, "extractor_version")
        _require_aware_datetime(self.fetched_at, "fetched_at")


@dataclass(frozen=True, slots=True)
class EventIdentityKey:
    """The deterministic key an extraction resolves against (ADR-0012).

    Two extractions producing an equal key are the same event; the second
    updates the first rather than inserting. Equality and hashing come from
    ordinary dataclass field comparison, so this can be used directly as a
    dict key or set member without a caller writing its own equality function
    — the same discipline `ics.generate_ics` already applies through its
    deterministic UID derivation.

    Attributes:
        host_org_unit: The org unit the event belongs to — not the page it
            was found on. Stripped of incidental leading/trailing whitespace
            only. Unlike `normalized_title`, this is not case-folded or
            otherwise semantically normalized: ADR-0012 specifies a folding
            rule for the title, not for the org unit, and an org unit is
            expected to be a stable identifier from another table rather than
            free text needing cosmetic normalization. Whatever folding rule
            (if any) that identifier scheme needs is not decided here.
        normalized_title: See `normalize_title`.
        resolved_date: See `resolved_date`.
    """

    host_org_unit: str
    normalized_title: str
    resolved_date: date


def resolve_identity_key(
    *, host_org_unit: str, title: str, event_time: EventTime
) -> EventIdentityKey | None:
    """Compute an event's identity key, or `None` when it has none.

    Returns `None` for `UnresolvedTime` — ADR-0012: "An event at `unresolved`
    precision has no identity key and cannot be resolved against anything."
    Modeled as an absence rather than a sentinel key, so a caller cannot
    accidentally treat two unresolved events as the same, or as comparable at
    all: there is no key value produced to compare in the first place.

    Takes no provenance parameter. Source provenance (URL, fetch time,
    extractor version — `EventProvenance`) never contributes to this key: two
    extractions of the same event from different pages (the university
    calendar, the department page, an aggregator) must resolve to the same
    key, which is the whole point of keying on host and title rather than
    source (ADR-0012's rationale for "host org unit, not source domain").

    Raises:
        ValueError: if `host_org_unit` is blank, or if `title` is blank (via
            `normalize_title`).
    """
    _require_non_blank(host_org_unit, "host_org_unit")
    when = resolved_date(event_time)
    if when is None:
        return None
    return EventIdentityKey(
        host_org_unit=host_org_unit.strip(),
        normalized_title=normalize_title(title),
        resolved_date=when,
    )


# ---------------------------------------------------------------------------
# ADR-0012 — closed, versioned tag vocabulary
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TagVocabulary:
    """A closed, versioned set of tag terms an extraction may map into (ADR-0012).

    The actual terms are a product decision this ADR explicitly declines to
    make ("picking them in an ADR would be exactly the kind of silent decision
    this document exists to prevent") — this type is the mechanism that
    decision plugs into once S5 settles it. Construct one instance per
    released vocabulary version; growing the vocabulary means constructing a
    new `TagVocabulary` with a new `version`, deliberately, never mutating an
    existing one (this type is frozen).

    Attributes:
        version: An opaque, non-blank version token. Carried forward onto
            every `MappedTag` and `QuarantinedTag` this vocabulary produces,
            so a stored tag stays interpretable against the vocabulary version
            that actually evaluated it, even after the vocabulary changes.
        terms: The closed set of valid terms, already normalized (see
            `normalize_tag_value`) — construction rejects a term that is not
            already in its own normalized form, so membership comparison in
            `resolve_tag` is exact equality against this set, never another
            fold applied inconsistently at two different times.
    """

    version: str
    terms: frozenset[str]

    def __post_init__(self) -> None:
        _require_non_blank(self.version, "version")
        if not self.terms:
            raise ValueError("a vocabulary must declare at least one term")
        for term in self.terms:
            _require_non_blank(term, "term")
            normalized = _fold(term)
            if term != normalized:
                raise ValueError(
                    f"vocabulary term {term!r} is not already normalized "
                    f"(expected {normalized!r}); store terms pre-normalized so "
                    "membership comparison is exact equality, not another fold "
                    "applied at resolution time"
                )


@dataclass(frozen=True, slots=True)
class MappedTag:
    """A tag value that resolved into the vocabulary. Matchable and renderable.

    Attributes:
        term: The canonical, normalized vocabulary term.
        vocabulary_version: The `TagVocabulary.version` this was resolved
            against.
    """

    term: str
    vocabulary_version: str


@dataclass(frozen=True, slots=True)
class QuarantinedTag:
    """A tag value the vocabulary did not recognize (ADR-0012).

    "A value that does not map is quarantined: stored with the event, visible
    to a human review queue, and never rendered and never matched on."
    Deliberately has no `term` field — there is nothing on this type that
    reads as a matchable or renderable value, so a caller cannot reach one
    from a `QuarantinedTag` by accident. The only way to obtain a `MappedTag`
    for this raw value is to call `resolve_tag` again against a vocabulary
    that has since added it — a deliberate, versioned change with a human in
    the loop, per the ADR.

    Attributes:
        raw_value: The extracted text exactly as received, unnormalized — a
            reviewer deciding whether to add this to the vocabulary needs to
            see what was actually on the page, casing and all, not the folded
            form.
        vocabulary_version: The `TagVocabulary.version` this was checked
            against and did not match.
    """

    raw_value: str
    vocabulary_version: str


#: The outcome of resolving one raw extracted value against one `TagVocabulary`.
TagResolution: TypeAlias = MappedTag | QuarantinedTag


def resolve_tag(raw_value: str, vocabulary: TagVocabulary) -> TagResolution:
    """Map a raw extracted value into `vocabulary`, or quarantine it (ADR-0012).

    "Extraction maps into it; it does not extend it." There is no parameter
    here that could add a term to `vocabulary` — growing the vocabulary
    happens by constructing a new `TagVocabulary`, deliberately, never as a
    side effect of resolving a tag.
    """
    _require_non_blank(raw_value, "raw_value")
    normalized = normalize_tag_value(raw_value)
    if normalized in vocabulary.terms:
        return MappedTag(term=normalized, vocabulary_version=vocabulary.version)
    return QuarantinedTag(raw_value=raw_value, vocabulary_version=vocabulary.version)


def matchable_tags(resolutions: Iterable[TagResolution]) -> tuple[MappedTag, ...]:
    """The subset of `resolutions` that may be rendered or matched on.

    ADR-0012: quarantined values are "never rendered and never matched on."
    Enforced by type rather than by remembering to call this filter —
    `QuarantinedTag` has no `term` attribute for a caller to reach even by
    skipping it.
    """
    return tuple(r for r in resolutions if isinstance(r, MappedTag))


def quarantined_tags(resolutions: Iterable[TagResolution]) -> tuple[QuarantinedTag, ...]:
    """The subset of `resolutions` awaiting human review (ADR-0012)."""
    return tuple(r for r in resolutions if isinstance(r, QuarantinedTag))
