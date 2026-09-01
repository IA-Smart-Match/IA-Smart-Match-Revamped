"""Contact-free public seam for Stage 0 event candidates (V3 / P6 offline ingestion).

Design authority: `docs/superpowers/specs/2026-08-31-ratification-and-feature-
delivery-design.md` §7, §3.3's "P6 Stage 0 scope" row, §13, §16. The unsigned
P6/R3 stop-gate (R3 T-07/T-13/T-19/T-23, and T-27-T-29) is **not** passed. Only
the safe exposed-wrapper design that row authorizes is implemented here:

```text
committed synthetic fixture
  -> internal iCal or JSON-LD parser
  -> private parsed representation
  -> allowlist projection
  -> ContactFreeEventCandidate public seam
```

`smartmatch_domain.ical_parser` and `smartmatch_domain.jsonld_parser` stay
internal. Their `ParsedSourceEvent` return type may observe organizer/contact
fields needed to parse the source format (`organizer_name` above, redacted
free-text elsewhere) — that is expected and is not modified by this module.

**The allowlist, not copy-then-delete.** `_project` below constructs a
`ContactFreeEventCandidate` by naming each safe field explicitly. It never
receives, copies, or introspects the private `ParsedSourceEvent` as a bag of
attributes; it reads exactly the fields it names and nothing else.
`ParsedSourceEvent.organizer_name` is simply never read. This is the entire
point of the design authorized in §7: an implementation that instead copied a
raw object and then deleted or masked known contact keys would leave the type
one omitted `del` away from a leak, and a *future* field added to
`ParsedSourceEvent` would cross into the public seam by default rather than by
deliberate choice. The allowlist inverts that failure mode — a future field on
`ParsedSourceEvent` crosses only if a maintainer edits `_project` to name it.

**The source UID is digested, not carried.** A source's own UID is routinely
address-shaped — RFC 5545 suggests a domain-qualified value, and every fixture
under `tests/fixtures/event_sources/` carries one (`synthetic-0001@example.edu`).
An opaque-but-verbatim UID would therefore walk an email address straight
through a seam whose entire claim is that it carries none, and no redaction
rule can be trusted to recognise every address-shaped identifier a source might
mint. This seam exposes `source_uid_digest` instead: a SHA-256 digest of the
raw UID. Equality is preserved, so the identity work a UID exists for —
recognising the same event across two reads of a source — still works, while
the address itself cannot survive the hash. The internal parsers keep emitting
the raw `source_uid`; digesting is this boundary's job, not theirs.

`ContactFreeEventCandidate` itself carries no organizer, no contact name, no
email, no phone, no verbatim source UID, and no generic catch-all / raw-
properties / extra-fields mapping that could carry any of those — no
`dict[str, Any]`, no `**extra`, no `raw` attribute. Its field set is fixed and
closed (`slots=True`, no default catch-all).

**Fail-closed, not exception-as-control-flow.** `parse_ical` and `parse_jsonld`
raise `ValueError` for a structurally malformed document (§13: "malformed
imports are not silently dropped"). This module is the boundary where that
raised exception is converted into a pure typed result — `CandidateRefusal`,
carrying a stable `CandidateRefusalReason` — so that a caller of this public
seam never needs to catch an exception to tell a refusal from a result. This is
boundary conversion of an already-typed failure, not exception-driven control
flow: the parser's own raise is untouched, and this module still runs no logic
inside a `try` block beyond the parser call it wraps.

**Bounded claim only (T-29).** T-29 leaves every post-fetch complexity limit
unquantified. This module makes **no claim of unbounded, arbitrary, or even
generally quantified input support**. The only demonstrated behavior is what
the committed synthetic fixtures under `tests/fixtures/event_sources/` and
`tests/unit/test_event_candidate.py` exercise. Any size, depth, or volume
guarantee beyond that is unverified and is not claimed here.

**No runtime caller.** This module recognizes and authenticates nothing about
where its `text` argument came from — it is not wired to a router, worker,
task, provider registry, or any other dispatch surface, and it must not be.
Nothing in this codebase may call `candidates_from_ical_fixture` or
`candidates_from_jsonld_fixture` outside of committed-fixture tests until the
P6/R3 gate is signed. No provider interface, fake provider adapter, or
arbitrary caller-supplied document ingestion surface is introduced by this
module.

**Boundary.** No persistence, no network access, no HTTP fetch, no model
dispatch, no review assignment, no publication, no UI action. This module
performs no I/O of any kind: it takes a `str` and `source_time_zone: str` and
returns a value: no filesystem, no socket, no subprocess, no environment
variable, no framework, no ORM. `pyproject.toml`'s import-linter contract
enforces the domain package's purity (`os`, `pathlib`, `socket`, `subprocess`,
`sqlalchemy`, `fastapi`, and friends are all forbidden here); this module's own
imports are limited to the standard library plus the two internal parser
modules and their shared `smartmatch_domain.events` types.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias

from smartmatch_domain.events import EventTime
from smartmatch_domain.ical_parser import ParsedSourceEvent as _ParsedSourceEvent
from smartmatch_domain.ical_parser import parse_ical as _parse_ical
from smartmatch_domain.jsonld_parser import parse_jsonld as _parse_jsonld

__all__ = [
    "CandidateOutcome",
    "CandidateRefusal",
    "CandidateRefusalReason",
    "ContactFreeEventCandidate",
    "candidates_from_ical_fixture",
    "candidates_from_jsonld_fixture",
]


class CandidateRefusalReason(StrEnum):
    """A stable reason code for a fail-closed refusal (spec §13).

    Deliberately not the parser's raw exception message: a stable, closed set
    of codes is a contract a caller can branch on, where a free-text message
    is not — and is not guaranteed to stay clear of source content either.
    """

    UNPARSEABLE_ICAL = "unparseable_ical"
    UNPARSEABLE_JSONLD = "unparseable_jsonld"


@dataclass(frozen=True, slots=True)
class CandidateRefusal:
    """A fail-closed refusal to produce candidates from a fixture.

    Carries a stable reason and nothing else — no partial candidate, no raw
    parser output, no exception object. §13: "malformed imports are not
    silently dropped" — a refusal is a first-class typed value, not a
    swallowed error and not an empty tuple standing in for a failure.
    """

    reason: CandidateRefusalReason


@dataclass(frozen=True, slots=True)
class ContactFreeEventCandidate:
    """A public, contact-free event candidate (V3 / P6 Stage 0 seam).

    Every field here is deliberately named and typed — there is no field on
    this type through which an organizer name, a contact name, an email
    address, a phone number, or any other value could pass unnoticed. In
    particular:

    * No `organizer_name` field. `ParsedSourceEvent.organizer_name` exists
      because both parsers must retain a source's declared organizer display
      name to parse the format faithfully (see their module docstrings on
      MP-4); this type omits it entirely rather than redacting it, because a
      redacted-but-present organizer field would still be an organizer field.
    * No generic catch-all. There is no `dict[str, Any]`, no `**extra`
      keyword, and no `raw` attribute anywhere on this type — nothing a future
      contact-bearing field on `ParsedSourceEvent` could flow through by
      default.

    `title`, `description`, `location`, and `raw_tags` are carried through
    exactly as the internal parser emitted them, including that parser's own
    email/phone redaction of free text (see `ical_parser`'s and
    `jsonld_parser`'s `_redact_contact_data`/`_redact`). This module adds no
    redaction of its own to those fields — it does not need to, because it
    never reads the one field (`organizer_name`) that both parsers leave
    unredacted by design, and personal names in free prose remain each
    parser's documented MP-4 evaluation-boundary limit, not something this
    seam claims to have fixed.

    Attributes:
        title: The event's title, contact-redacted free text.
        event_time: The `EventTime` ADR-0010 resolved for the event —
            `ExactTime`, `DateOnlyTime`, or `UnresolvedTime`. Carries no
            contact data by construction (see `smartmatch_domain.events`).
        source_uid_digest: A SHA-256 digest of the source's own identifier
            for the event, or `None` when the source declared none. Never the
            raw UID: a UID is routinely an email address (see the module
            docstring). Deterministic, so two reads of the same source event
            still compare equal.
        source_url: A source-declared URL for the event, or `None`,
            contact-redacted.
        location: The event's location, contact-redacted free text.
        description: The event's description, contact-redacted free text.
        raw_tags: Unresolved source tag values, contact-redacted, exactly as
            emitted by the parser (vocabulary resolution is a separate,
            later concern this seam does not perform).
        is_cancelled: Whether the source marked the event cancelled.
        has_unexpanded_recurrence: Whether the source declared a recurrence
            rule this parser did not expand into individual occurrences.
    """

    title: str
    event_time: EventTime
    source_uid_digest: str | None
    source_url: str | None
    location: str | None
    description: str | None
    raw_tags: tuple[str, ...]
    is_cancelled: bool
    has_unexpanded_recurrence: bool


#: The result of asking this seam for the candidates in one fixture document:
#: either the candidates it found (possibly none, for a structurally valid but
#: empty document), or a typed refusal. A discriminated union, in the same
#: style `smartmatch_domain.events.EventTime` and `TagResolution` already use,
#: so a caller narrows with `isinstance` rather than inspecting an ambiguous
#: sentinel value.
CandidateOutcome: TypeAlias = "tuple[ContactFreeEventCandidate, ...] | CandidateRefusal"


def _digest_source_uid(source_uid: str | None) -> str | None:
    """Return a SHA-256 digest of `source_uid`, or `None` for `None`.

    Not a redaction and not a truncation: a digest is the only transformation
    that preserves the equality a UID is kept for while making it impossible
    for an address-shaped UID to reach the public seam. The full 64-character
    hex digest is kept — a UID space is not enumerable in the way a truncated
    digest's collisions would matter here, and nothing downstream needs a
    shorter key.
    """
    if source_uid is None:
        return None
    return hashlib.sha256(source_uid.encode()).hexdigest()


def _project(parsed: _ParsedSourceEvent) -> ContactFreeEventCandidate:
    """Allowlist `parsed` into a `ContactFreeEventCandidate`.

    Names each safe field explicitly and reads nothing else from `parsed` —
    in particular, `parsed.organizer_name` is never referenced here. This is
    the allowlist projection the design in the module docstring requires: a
    field is copied because this function names it, never because it happened
    to be present on the source object.

    `source_uid` is the one named field that is transformed rather than
    carried: it is digested, because a raw UID is routinely an email address.
    """
    return ContactFreeEventCandidate(
        title=parsed.title,
        event_time=parsed.event_time,
        source_uid_digest=_digest_source_uid(parsed.source_uid),
        source_url=parsed.source_url,
        location=parsed.location,
        description=parsed.description,
        raw_tags=parsed.raw_tags,
        is_cancelled=parsed.is_cancelled,
        has_unexpanded_recurrence=parsed.has_unexpanded_recurrence,
    )


def candidates_from_ical_fixture(text: str, *, source_time_zone: str) -> CandidateOutcome:
    """Produce contact-free candidates from one committed iCalendar fixture.

    Args:
        text: The full iCalendar document text (e.g. a committed `.ics`
            fixture's contents). No file is opened here — the caller supplies
            the text.
        source_time_zone: IANA zone the source declares for its events, passed
            through unchanged to `ical_parser.parse_ical`.

    Returns:
        The candidates found, in document order (`()` for a structurally
        valid document with no events), or a `CandidateRefusal` naming
        `CandidateRefusalReason.UNPARSEABLE_ICAL` when `ical_parser.parse_ical`
        raises `ValueError` — a structurally malformed document, or a blank or
        unknown `source_time_zone`.
    """
    try:
        parsed_events = _parse_ical(text, source_time_zone=source_time_zone)
    except ValueError:
        return CandidateRefusal(reason=CandidateRefusalReason.UNPARSEABLE_ICAL)
    return tuple(_project(event) for event in parsed_events)


def candidates_from_jsonld_fixture(text: str, *, source_time_zone: str) -> CandidateOutcome:
    """Produce contact-free candidates from one committed JSON-LD fixture.

    Args:
        text: The full JSON-LD document text (e.g. a committed `.jsonld`
            fixture's contents). No file is opened here — the caller supplies
            the text.
        source_time_zone: IANA zone the source declares for its events, passed
            through unchanged to `jsonld_parser.parse_jsonld`.

    Returns:
        The candidates found, in document order (`()` for a structurally
        valid document with no event nodes), or a `CandidateRefusal` naming
        `CandidateRefusalReason.UNPARSEABLE_JSONLD` when
        `jsonld_parser.parse_jsonld` raises `ValueError` — invalid JSON, a
        document nested past the parser's depth limit, an event node with no
        usable name, or a blank or unknown `source_time_zone`.
    """
    try:
        parsed_events = _parse_jsonld(text, source_time_zone=source_time_zone)
    except ValueError:
        return CandidateRefusal(reason=CandidateRefusalReason.UNPARSEABLE_JSONLD)
    return tuple(_project(event) for event in parsed_events)
