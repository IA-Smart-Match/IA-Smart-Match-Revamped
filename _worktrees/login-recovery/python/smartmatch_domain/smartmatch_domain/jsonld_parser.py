"""Parse JSON-LD `schema.org/Event` markup into ADR-0010 temporal types.

The sibling of `smartmatch_domain.ical_parser`, for the other machine-readable
source shape the discovery roadmap's Stage 0 targets. Where a calendar feed
hands over a flat list of `VEVENT` blocks, an embedded JSON-LD block hands over
an arbitrary object graph, so most of the work here is deciding *which* nodes
are events at all.

**Why `ParsedSourceEvent` is reused rather than re-declared.** Every field the
iCal parser records has an exact `schema.org` counterpart — `SUMMARY`/`name`,
`UID`/`@id`, `URL`/`url`, `LOCATION`/`location`, `ORGANIZER;CN`/`organizer.name`,
`DESCRIPTION`/`description`, `CATEGORIES`/`keywords`, `STATUS:CANCELLED`/
`eventStatus`, `RRULE`/`eventSchedule` — and nothing in JSON-LD needs a field
iCalendar lacks. A parallel type would therefore differ from the existing one
only in its name, and would force every downstream consumer to branch on which
parser produced a record, which is precisely the thing a downstream consumer
should not care about. Importing the type also keeps the two parsers honest: a
field added for one is a field the other must decide about. `ical_parser` is not
modified by this module.

**Purity.** No transport, no file access, no environment. The caller supplies
the document as text, so this module stays inside the domain's import contract
(`pyproject.toml` forbids `os`, `pathlib`, `socket` here) and can be exercised
entirely against committed fixtures. Fetching is a worker concern gated behind
R3; nothing here reaches a network.

**The invariant.** ADR-0010: a source that does not state a time does not
acquire one. A date-only `startDate` (`"2026-09-20"`) becomes `DateOnlyTime`,
never an instant at midnight — that collapse is the defect ADR-0010 exists to
prevent, and JSON-LD walks into it more easily than iCalendar does, because
`datetime.fromisoformat` will happily turn a bare date into midnight if asked.
An absent, blank, or unparseable `startDate` becomes `UnresolvedTime`, which
`resolve_identity_key` turns into "no identity key" rather than a fabricated
one.

The same rule binds one rung up, where it is easier to miss. `fromisoformat`
zero-fills whatever a partial timestamp omits, so `"2026-09-20T12"` would become
an exact `12:00:00` the source never stated, and an ISO *week* designator
(`"2026-W39"`) would become a specific Monday when the source named a whole
week. Both are the midnight collapse wearing different clothes. So `startDate`
is full-matched against an explicit grammar (`_DATE_PATTERN`,
`_DATE_TIME_PATTERN`) before any parsing: calendar dates and complete
date-times are accepted, and week designators, ordinal designators, partial
timestamps, and anything with trailing data become `UnresolvedTime`. A
list-valued `startDate` naming two different days is a contradiction rather
than a preference, and is also `UnresolvedTime`; a list repeating one value is
that value.

**Why `source_time_zone` is required, and why an ISO offset is not one.**
`resolved_date` converts an instant into a zone to produce the date ADR-0012
keys on, so the zone decides the date. `"2026-04-16T02:00:00Z"` and
`"2026-04-16T02:00:00+05:00"` both carry unambiguous instants, and neither says
where the event happens: both fall on 15 April in Los Angeles. ADR-0010 rule 1
is explicit that an offset is not acceptable in a zone's place — an offset is a
fact about one instant, and an event moved across a DST boundary silently
shifts. So the offset is preserved on the instant and is never promoted to
`time_zone`; the zone comes from the source registry, as a declared fact about
the source, and the parser refuses to run without one.

A *floating* local time has the opposite problem: it needs the declared zone to
become an instant at all, and twice a year that conversion has no single answer.
A local time inside a DST gap names an instant that does not exist, and one
inside a DST fold names two. Both become `UnresolvedTime` rather than a silently
chosen branch — the same discipline `ical_parser` applies to a `DTSTART` with no
`TZID`.

**Resource limits are failures, not empty results.** `json.loads` recurses over
nesting, so roughly 90KB of brackets is enough to raise `RecursionError` out of
this module — an unhandled worker crash on untrusted input, and a violation of
the documented `Raises: ValueError` contract. Every resource-limit failure is
therefore restated as `ValueError`: `_load` catches `RecursionError`, and
`_require_within_depth` refuses a document nested deeper than `_MAX_DEPTH`
before any walking begins, which is what makes every recursive helper below
bounded by construction. Refusing is deliberate in preference to truncating: a
truncated walk returns a short tuple, `tuple[ParsedSourceEvent, ...]` has
nowhere to carry a "there was more" flag, and G3 §7 MP-5 forbids reporting a
capped response as complete.

**MP-4 — personal contact data. What is enforced, and what is not.** G3 §7
forbids emitting personal contact data while P9's contact-field decision is
open. State the boundary precisely, because an overstated security claim is
worse than none — it makes reviewers stop looking.

Enforced here, at two levels:

1. *Structurally.* `schema.org/Event` carries `email`, `telephone`, and
   `contactPoint` on organizers, performers, and postal addresses, and this
   module reads none of them: `_organizer_name` takes `name` alone, and
   `_address_text` enumerates an explicit allowlist of postal components rather
   than serializing whatever the address object happens to hold.
2. *By content.* Property-level omission is not enough on its own, because free
   text carries contact data too — a `description` reading "email
   advisor@example.edu or call 909-555-0177", a `streetAddress` reading "contact
   evil@x.edu", an `organizer.name` reading "Dr. Rios (rios@example.edu)". So
   every emitted string — `title`, `location`, `description`, `organizer_name`,
   `raw_tags`, `source_url`, and `source_uid` — is passed through `_redact`,
   which replaces structurally-detectable email addresses and telephone numbers
   with `_REDACTION_MARKER`. The marker is deliberately visible and
   non-reversible: a silent deletion would leave plausible prose that no
   reviewer could tell had been altered. A value that is *entirely* contact data
   is not a redacted value but an absent one — `organizer_name` becomes `None`
   (a redaction is not a name) and such a tag is dropped. `source_url` must also
   carry an `http`/`https` scheme; `mailto:` and every other scheme are refused
   outright rather than redacted.

**Not** enforced here, and deliberately so: personal *names* in prose. "Dr.
Rios is hosting" is contact-adjacent personal data that no pattern can
distinguish from "Rios Hall is hosting", so an absolute no-personal-data
guarantee is not honestly implementable at this layer. It is not claimed. Names
in free text remain the MP-4 evaluation boundary's problem for as long as P9
Gate B is open, and this module's guarantee is exactly the two levels above:
contact *properties* are never read, and email and phone *patterns* are redacted
from emitted text.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any, Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from smartmatch_domain.events import (
    DateOnlyTime,
    EventTime,
    ExactTime,
    UnresolvedTime,
)
from smartmatch_domain.ical_parser import ParsedSourceEvent

__all__ = [
    "JSONLD_PARSER_VERSION",
    "ParsedSourceEvent",
    "parse_jsonld",
]

#: Recorded on `EventProvenance.extractor_version` by callers, so a stored
#: observation can be traced to the exact parser that produced it. Bump on any
#: change to parsing behaviour. Distinct from `ICAL_PARSER_VERSION` even though
#: both parsers emit the same value type — the version identifies the code that
#: produced a record, not the shape of the record.
JSONLD_PARSER_VERSION: Final = "jsonld_parser/2"

#: The `@type` values treated as events. An explicit set, not a heuristic:
#: `schema.org` has no runtime type hierarchy in a JSON-LD document, so "is this
#: a subtype of Event" cannot be *computed* from the document — it can only be
#: looked up. Guessing from a suffix (`*Event`) would admit `EventReservation`
#: and `EventVenue`, which are not events; guessing from the presence of
#: `startDate` would admit every invented vendor type that happens to carry a
#: date. An unrecognized `@type` is therefore skipped, which is MP-1's rule
#: applied at the node level: not extracting is a pass, inventing is a fail.
#: Adding a term here is a deliberate change.
_EVENT_TYPES: Final = frozenset(
    {
        "Event",
        "EventSeries",
        "BusinessEvent",
        "ChildrensEvent",
        "ComedyEvent",
        "CourseInstance",
        "DanceEvent",
        "DeliveryEvent",
        "EducationEvent",
        "ExhibitionEvent",
        "Festival",
        "FoodEvent",
        "Hackathon",
        "LiteraryEvent",
        "MusicEvent",
        "PublicationEvent",
        "SaleEvent",
        "ScreeningEvent",
        "SocialEvent",
        "SportsEvent",
        "TheaterEvent",
        "VisualArtsEvent",
    }
)

#: Hosts whose IRIs name `schema.org` terms. The closed `@type` set above is
#: only closed if the *namespace* is checked too: comparing local names alone
#: accepts `https://evil.example/Event` and `evil:Event` as schema.org Events,
#: which is precisely the closed-set posture failing open. A publisher may write
#: a term bare (`"Event"`), prefixed (`"schema:Event"`), or as a full IRI, and
#: all three are recognized — anything else is not a term this parser knows.
_SCHEMA_HOSTS: Final = frozenset({"schema.org", "www.schema.org"})

#: Compact-IRI prefixes accepted as `schema.org`. `schema` is the conventional
#: binding; `sdo` appears in the wild. A prefix outside this set is refused
#: rather than resolved, because resolving it would mean trusting the
#: document's own `@context` to say what it means.
_SCHEMA_PREFIXES: Final = frozenset({"schema", "sdo", "schemaorg"})

#: Postal address components that may be emitted. An allowlist rather than a
#: denylist: `PostalAddress` frequently carries `telephone` and `email`, and MP-4
#: forbids emitting those. Enumerating what may be read means a component added
#: to `schema.org` later cannot leak through by default.
_ADDRESS_PARTS: Final = (
    "streetAddress",
    "addressLocality",
    "addressRegion",
    "postalCode",
)

#: Properties whose presence on an `eventSchedule` node marks it as an actual
#: `Schedule` rather than an arbitrary object. Checked alongside the `@type`,
#: because a truthiness test alone flags `{"garbage": 1}` as a recurring series
#: and tells a downstream consumer its single occurrence is incomplete when it
#: is not.
_SCHEDULE_PROPERTIES: Final = frozenset(
    {
        "repeatFrequency",
        "repeatCount",
        "byDay",
        "byMonth",
        "byMonthDay",
        "byMonthWeek",
        "startDate",
        "endDate",
        "startTime",
        "endTime",
        "duration",
        "exceptDate",
        "scheduleTimezone",
    }
)

#: How deep any walk of the document will descend, and — enforced once by
#: `_require_within_depth` before any walking starts — how deep the document
#: itself may be. A JSON document parsed by `json.loads` is a tree, so it cannot
#: contain a reference cycle and no visited-set is needed to guarantee
#: termination. The cap exists for the other failure: a deeply or adversarially
#: nested document driving recursion into a `RecursionError`. Checking the whole
#: document once, iteratively, is what makes that guarantee real — bounding only
#: the node walk left `_first_text`, `_named_text`, `_location_text`, and
#: `_name_values` free to recurse over nested arrays without a bound, and
#: `json.loads` itself unbounded above them. Real markup nests events a handful
#: of levels at most; a document past this is refused, not truncated.
_MAX_DEPTH: Final = 32

_DATE_TIME_SEPARATORS: Final = ("T", "t", " ")

#: `YYYY-MM-DD`, and nothing else that `date.fromisoformat` would also accept.
#: Python 3.11 widened it to the full ISO 8601 set, which means `"2026-W39"` and
#: `"2026-263"` parse — a week and an ordinal day silently acquiring calendar
#: precision the source never stated.
_DATE_PATTERN: Final = re.compile(r"\d{4}-\d{2}-\d{2}\Z")

#: A complete local time, with optional seconds, optional fractional seconds,
#: and an optional offset. Minutes are required: `"2026-09-20T12"` states an
#: hour, and `fromisoformat` would zero-fill it into an exact `12:00:00`.
_DATE_TIME_PATTERN: Final = re.compile(
    r"\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:[Zz]|[+-]\d{2}(?::?\d{2})?)?\Z"
)

#: Replaces detected contact data in emitted text. Fixed, visible, and carrying
#: none of the original: a reader and a reviewer can both see that something was
#: removed, and nothing about the removed value survives.
_REDACTION_MARKER: Final = "[contact removed]"

_EMAIL_PATTERN: Final = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")

#: Separated telephone forms only — `909-555-0177`, `(909) 555-0177`,
#: `+1-909-555-0199`, `+44 20 7946 0958`. Deliberately not a bare run of digits:
#: an unseparated 10-to-15-digit run is far more often an identifier inside a
#: URL than a phone number, and redacting one would corrupt a `source_url` to
#: remove nothing. That is a stated gap, not an oversight.
_PHONE_PATTERNS: Final = (
    re.compile(
        r"(?<![\w])(?:\+\d{1,3}[\s.-]?)?(?:\(\d{3}\)[\s.-]?|\d{3}[\s.-])\d{3}[\s.-]\d{4}(?!\d)"
    ),
    re.compile(r"(?<![\w])\+\d{1,3}(?:[\s.-]\d{2,4}){2,4}(?!\d)"),
)

_ALLOWED_URL_SCHEMES: Final = ("http://", "https://")


def parse_jsonld(
    text: str,
    *,
    source_time_zone: str,
) -> tuple[ParsedSourceEvent, ...]:
    """Decode a JSON-LD document into parsed events.

    Args:
        text: The full JSON-LD block, as extracted from a page's
            `<script type="application/ld+json">` by a caller. This module does
            no HTML parsing and no fetching.
        source_time_zone: IANA zone the source declares for its events, from the
            source registry. Used as the zone a floating local `startDate` is
            read in, as the display zone for date-only values, and — always — as
            the zone `resolved_date` keys on. Never guessed, and never taken
            from an ISO offset in the document.

    Returns:
        One `ParsedSourceEvent` per event node, in document order, parents
        before their sub-events. A document with no event nodes returns an empty
        tuple rather than raising — an empty feed is a legitimate answer and must
        stay distinguishable from a fetch failure.

    Raises:
        ValueError: If `source_time_zone` is blank or not a known IANA zone; if
            `text` is not valid JSON, including a document too deeply nested for
            the decoder; if the document nests deeper than `_MAX_DEPTH`; or if
            an event node states no usable `name`. Every one of these is a real
            failure, and none is flattened into an empty or partial result — a
            broken feed must not look like an empty one, and a capped read must
            not look like a complete one (G3 §7 MP-5).
    """
    zone = _require_known_zone(source_time_zone)
    document = _load(text)
    _require_within_depth(document)
    collected: list[ParsedSourceEvent] = []
    _collect(document, 0, collected, source_time_zone, zone)
    return tuple(collected)


def _require_known_zone(name: str) -> ZoneInfo:
    """Resolve an IANA zone name, rejecting blanks and unknown names.

    Mirrors `ical_parser._require_known_zone` and `events._require_known_time_zone`:
    a real-but-misspelled zone is caught here rather than left for an adapter to
    notice later.
    """
    if not name or not name.strip():
        raise ValueError("source_time_zone must not be blank")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"unknown IANA time zone: {name!r}") from exc


def _load(text: str) -> Any:
    """Decode the document, restating any decode failure in this module's terms.

    `RecursionError` is caught alongside `JSONDecodeError` because `json.loads`
    recurses over nesting and is not depth-bounded: `"[" * 60000 + "]" * 60000`
    is about 90KB of attacker-supplied text that takes the interpreter's stack
    out, and letting that escape is an unhandled worker crash rather than the
    documented `ValueError`.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"document is not valid JSON: {exc}") from exc
    except RecursionError as exc:
        raise ValueError("document nests too deeply to decode") from exc


def _require_within_depth(document: Any) -> None:
    """Refuse a document nested deeper than `_MAX_DEPTH`.

    Iterative on purpose — a recursive depth check on a pathological document is
    the very failure it exists to prevent. Running once, up front, is what lets
    every helper below recurse freely: none of them can be handed a value deeper
    than the cap.

    Refusing rather than truncating is the MP-5 call. Silently walking 32 levels
    of a 60-level document returns a tuple the caller cannot distinguish from a
    complete read, and `tuple[ParsedSourceEvent, ...]` has nowhere to carry the
    fact that there was more.
    """
    stack: list[tuple[Any, int]] = [(document, 0)]
    while stack:
        node, depth = stack.pop()
        if depth > _MAX_DEPTH:
            raise ValueError(f"document nests deeper than the {_MAX_DEPTH}-level cap")
        if isinstance(node, dict):
            stack.extend((value, depth + 1) for value in node.values())
        elif isinstance(node, list):
            stack.extend((item, depth + 1) for item in node)


# ---------------------------------------------------------------------------
# Node discovery
# ---------------------------------------------------------------------------


def _collect(
    node: Any,
    depth: int,
    out: list[ParsedSourceEvent],
    zone_name: str,
    zone: ZoneInfo,
) -> None:
    """Walk the graph, appending one parsed event per event node.

    Three shapes are handled by one rule rather than three special cases. A
    top-level array, an `@graph` array, and an event nested under a `WebPage`'s
    `mainEntity` are all "an event somewhere below a container", so containers
    are traversed generically: any node that is not itself an event has all of
    its values descended into. This is why no `@graph` key appears anywhere in
    this module — it needs no special handling, and neither will the next
    container key some publisher uses.

    An event node is the one place traversal is *narrowed*: only `subEvent` is
    followed. Descending into all of an event's values would follow
    `superEvent` upward and emit an ancestor the document merely referenced
    rather than described, and would pull `performer`/`sponsor` organizations
    into scope for no benefit.

    The depth guard is redundant with `_require_within_depth`, and kept as a
    second latch: the two would have to fail together for recursion to run away.
    """
    if depth > _MAX_DEPTH:
        raise ValueError(f"document nests deeper than the {_MAX_DEPTH}-level cap")
    if isinstance(node, list):
        for item in node:
            _collect(item, depth + 1, out, zone_name, zone)
        return
    if not isinstance(node, dict):
        return
    if _is_event(node):
        out.append(_parse_event(node, zone_name, zone))
        # Sub-events are emitted in their own right: `subEvent` describes a
        # distinct occurrence with its own name and start time, so dropping
        # them would lose real events the source did state — the opposite
        # failure from fabricating ones. Parent first, then children, so the
        # order matches the document.
        _collect(node.get("subEvent"), depth + 1, out, zone_name, zone)
        return
    for value in node.values():
        _collect(value, depth + 1, out, zone_name, zone)


def _is_event(node: dict[str, Any]) -> bool:
    """Whether a node declares a `@type` this parser recognizes as an event."""
    return any(name in _EVENT_TYPES for name in _type_names(node))


def _type_names(node: dict[str, Any]) -> tuple[str, ...]:
    """The `schema.org` local names of a node's `@type`.

    `@type` is legitimately written several ways — `"Event"`, `"schema:Event"`,
    `"https://schema.org/Event"`, a `{"@value": "Event"}` object, and a list
    mixing a base type with a subtype (`["Event", "SocialEvent"]`). All reduce
    to the same local names here, so recognition does not depend on which
    serialization a publisher chose. A term from any other namespace reduces to
    nothing, so it cannot impersonate a schema.org type.
    """
    raw = node.get("@type")
    values = raw if isinstance(raw, list) else [raw]
    return tuple(
        term for value in values if (text := _scalar_text(value)) and (term := _schema_term(text))
    )


def _schema_term(value: str) -> str | None:
    """The local name of a `schema.org` term, or `None` if it is not one.

    The namespace is checked rather than discarded. Stripping to the local part
    and comparing that alone is what lets `https://evil.example/Event` and
    `evil:Event` pass as schema.org Events — a closed set that anyone can add to
    from outside is not closed.
    """
    text = value.strip()
    if not text:
        return None
    if "://" in text:
        scheme, _, rest = text.partition("://")
        if scheme.lower() not in ("http", "https"):
            return None
        host, _, path = rest.partition("/")
        if host.lower() not in _SCHEMA_HOSTS or not path:
            return None
        return path.rsplit("/", 1)[-1].strip() or None
    if ":" in text:
        prefix, _, local = text.partition(":")
        if prefix.lower() not in _SCHEMA_PREFIXES:
            return None
        return local.strip() or None
    if "/" in text:
        return None
    return text


# ---------------------------------------------------------------------------
# Node decoding
# ---------------------------------------------------------------------------


def _parse_event(
    node: dict[str, Any],
    zone_name: str,
    zone: ZoneInfo,
) -> ParsedSourceEvent:
    """Decode one event node.

    Deliberately does not read `organizer.email`, `organizer.telephone`,
    `contactPoint`, `performer`, or `attendee`, and passes every string it does
    emit through `_redact` — see the module docstring's MP-4 note for exactly
    what that does and does not guarantee. Deliberately produces no
    `host_org_unit`: `ParsedSourceEvent` has no such field, so T-11 control C-4
    ("extraction output must never choose an owning unit") is enforced by the
    type rather than by remembering the rule.
    """
    return ParsedSourceEvent(
        title=_title(node),
        event_time=_event_time(node.get("startDate"), zone_name, zone),
        source_uid=_redacted(_first_text(node.get("@id")) or _first_text(node.get("identifier"))),
        source_url=_source_url(node.get("url")),
        location=_redacted(_location_text(node.get("location"))),
        organizer_name=_organizer_name(node.get("organizer")),
        description=_redacted(_first_text(node.get("description"))),
        raw_tags=_raw_tags(node),
        is_cancelled=_is_cancelled(node.get("eventStatus")),
        has_unexpanded_recurrence=_has_recurrence(node),
    )


def _title(node: dict[str, Any]) -> str:
    """The event's name, which a node must actually state.

    `ParsedSourceEvent.title` is `str`, not `str | None`, so — unlike every
    other field here — it has nowhere to record "the source said nothing". The
    old `... or ""` filled that hole with an empty string, which is a value the
    source never wrote and which `events.normalize_title` rejects: a
    known-unknown at parse time turned into a `ValueError` later, at identity
    time, far from the document that caused it. Raising here reports the same
    fact at the point it is known.

    The honest fix is to widen `ParsedSourceEvent.title` to `str | None` so a
    nameless node can be recorded as one, but that type is shared with
    `ical_parser` and is out of this change's scope; see the accompanying
    report.
    """
    title = _redacted(_first_text(node.get("name")))
    if title is None:
        raise ValueError("event node states no usable name")
    return title


def _scalar_text(value: Any) -> str | None:
    """A single string value, whether written bare or as a `@value` object.

    `{"@value": "Real Title", "@language": "en"}` is ordinary JSON-LD and is how
    multilingual markup is usually written; treating it as absent silently loses
    the title.
    """
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        inner = value.get("@value")
        if isinstance(inner, str):
            return inner.strip() or None
    return None


def _first_text(value: Any) -> str | None:
    """The first non-blank string in a value that may be a string or a list.

    `name` and `description` are routinely serialized as lists when a publisher
    carries several language variants or an alternate title. Taking the first is
    the only choice that does not invent a preference the document did not
    state; nothing here concatenates them, which would produce a title no source
    ever wrote.

    A list's *items* are read as scalars and not descended into. Recursing until
    some string turns up scavenges a plausible title and a plausible date out of
    a document whose shape is wrong — `[[["Scavenged Title"]]]` is not a
    `schema.org` `name`, and reading one out of it makes a malformed document
    look like a well-formed one.

    Blank becomes `None` rather than `""` so a caller cannot mistake "the source
    said nothing" for "the source said empty".
    """
    if isinstance(value, list):
        for item in value:
            text = _scalar_text(item)
            if text is not None:
                return text
        return None
    return _scalar_text(value)


def _all_texts(value: Any) -> list[str]:
    """Every non-blank scalar string in a value that may be a string or a list."""
    if isinstance(value, list):
        return [text for item in value if (text := _scalar_text(item))]
    text = _scalar_text(value)
    return [text] if text else []


def _named_text(value: Any, depth: int = 0) -> str | None:
    """Text from a value that may be a string, a list, or a node with a `name`.

    Reads `name` and nothing else from an object. An organization node carries
    contact fields alongside its name, and MP-4 forbids emitting those.

    `depth` shares `_MAX_DEPTH` with every other walk in this module, so a
    nested-array property cannot drive this into a `RecursionError` even if
    `_require_within_depth` were somehow bypassed.
    """
    if depth > _MAX_DEPTH:
        raise ValueError(f"document nests deeper than the {_MAX_DEPTH}-level cap")
    if isinstance(value, dict) and "@value" not in value:
        return _first_text(value.get("name"))
    if isinstance(value, list):
        for item in value:
            text = _named_text(item, depth + 1)
            if text is not None:
                return text
        return None
    return _scalar_text(value)


def _organizer_name(value: Any) -> str | None:
    """The organizer's display name, and nothing else about the organizer.

    The counterpart of `ical_parser._organizer_name`, which takes the `CN`
    parameter and deliberately discards the `mailto:` value half. The same rule
    binds harder here: a `schema.org` organizer is a full `Organization` or
    `Person` node whose `email`, `telephone`, and `contactPoint` are personal
    contact data, and MP-4 forbids emitting that while P9 Gate B is open. Only
    `name` is read.

    Reading only `name` is not sufficient on its own, because publishers put
    contact data *inside* the name (`"Dr. Rios (rios@example.edu)"`), so the
    value is redacted as well. A name that is *entirely* contact data becomes
    `None`: a redaction marker is not a name, and emitting one would assert the
    source named an organizer when what it gave was an address.
    """
    text = _named_text(value)
    if text is None or _is_only_contact(text):
        return None
    return _redact(text)


def _source_url(value: Any) -> str | None:
    """The event's canonical URL, if the source gave something that is one.

    A `mailto:` URL is an email address wearing a `url` property, and every
    other non-web scheme (`tel:`, `javascript:`, `data:`) is either contact data
    or something a downstream renderer should never be handed. Refused outright
    rather than redacted, because a scheme-stripped URL is not a URL.
    """
    text = _first_text(value)
    if text is None:
        return None
    if not text.lower().startswith(_ALLOWED_URL_SCHEMES):
        return None
    return _redact(text)


def _location_text(value: Any, depth: int = 0) -> str | None:
    """A human-readable place, from a string or a `Place` node.

    A `Place` node's `name` and its postal address are both real, and neither
    subsumes the other — "Engineering Building, Room 101" locates the event on
    campus, the street address locates the campus. They are joined rather than
    one being chosen, so no stated fact is discarded. Address components come
    from `_ADDRESS_PARTS`, which excludes contact fields (MP-4); the joined
    result is redacted by the caller, because a publisher will write a phone
    number into a `name` or a `streetAddress` given the chance.
    """
    if depth > _MAX_DEPTH:
        raise ValueError(f"document nests deeper than the {_MAX_DEPTH}-level cap")
    if isinstance(value, list):
        for item in value:
            text = _location_text(item, depth + 1)
            if text is not None:
                return text
        return None
    if isinstance(value, dict) and "@value" not in value:
        parts = [part for part in (_first_text(value.get("name")), _address_text(value)) if part]
        return ", ".join(parts) or None
    return _scalar_text(value)


def _address_text(place: dict[str, Any]) -> str | None:
    """The postal components of a place, in `_ADDRESS_PARTS` order."""
    address = place.get("address")
    if isinstance(address, str):
        return address.strip() or None
    if not isinstance(address, dict):
        return None
    parts = [part for key in _ADDRESS_PARTS if (part := _first_text(address.get(key)))]
    return ", ".join(parts) or None


def _raw_tags(node: dict[str, Any]) -> tuple[str, ...]:
    """Tag-ish values, raw and unresolved.

    Collected from `keywords`, `about`, and `eventType` — the three places a
    publisher puts what the iCalendar side calls `CATEGORIES`. Values stay
    exactly as written: not case-folded, not deduplicated by meaning, not mapped.
    Resolving them against the closed vocabulary is card S5's responsibility and
    the vocabulary is owner-approved (ADR-0012); a parser that resolved tags
    would be choosing terms.

    "Exactly as written" has one exception, and it is MP-4's: contact data
    inside a tag is redacted, and a tag that is *entirely* contact data is
    dropped rather than reduced to a bare marker — an email address is not a
    subject, so `("[contact removed]",)` would be a tag that means nothing.

    A `keywords` *string* is split on commas, because that is the serialization
    `schema.org` documents for it. A `keywords` *list* is not split: its elements
    are already the publisher's own units, and splitting one would fabricate a
    boundary inside a value the source wrote whole.
    """
    values: list[str] = list(_keyword_values(node.get("keywords")))
    for key in ("about", "eventType"):
        values.extend(_name_values(node.get(key)))
    # Order-preserving de-duplication: a value repeated across `keywords` and
    # `about` is one tag, not two, and dropping the repeat loses nothing.
    # De-duplication runs *after* redaction so two tags that differ only in the
    # contact data they carried do not both survive as the same marker text.
    seen: set[str] = set()
    kept: list[str] = []
    for value in values:
        if _is_only_contact(value):
            continue
        redacted = _redact(value)
        if redacted not in seen:
            seen.add(redacted)
            kept.append(redacted)
    return tuple(kept)


def _keyword_values(value: Any) -> list[str]:
    """`keywords` as a list of raw values. See `_raw_tags` for the split rule."""
    if isinstance(value, str):
        return [chunk.strip() for chunk in value.split(",") if chunk.strip()]
    return _name_values(value)


def _name_values(value: Any) -> list[str]:
    """Every named value in a property that may be a scalar, a node, or a list."""
    if isinstance(value, list):
        return [text for item in value if (text := _named_text(item))]
    text = _named_text(value)
    return [text] if text else []


def _is_cancelled(value: Any) -> bool:
    """Whether `eventStatus` says `EventCancelled`.

    G3 §5: a same-source cancellation must unpublish immediately, so the status
    is carried through rather than being treated as a reason to skip the node —
    a skipped node looks identical to an event that simply vanished from the
    feed, and only one of those is a cancellation. That makes a missed
    cancellation a wrong value with a safety consequence, which is the failure
    mode MP-1 ranks worst, so every serialization a publisher may use has to be
    read: a plain string, a `@value` object, and — the standard and by far the
    most common form for an enumeration member — a node reference,
    `{"@type": "EventStatusType", "@id": "https://schema.org/EventCancelled"}`.

    The namespace is checked like any other term: `https://evil.example/
    EventCancelled` is not `schema.org`'s cancellation and does not unpublish
    anything.
    """
    return any(_schema_term(text) == "EventCancelled" for text in _status_texts(value))


def _status_texts(value: Any, depth: int = 0) -> list[str]:
    """Every term an `eventStatus` value could be naming."""
    if depth > _MAX_DEPTH:
        raise ValueError(f"document nests deeper than the {_MAX_DEPTH}-level cap")
    if isinstance(value, list):
        texts: list[str] = []
        for item in value:
            texts.extend(_status_texts(item, depth + 1))
        return texts
    if isinstance(value, dict):
        return [text for key in ("@id", "@value", "name") if (text := _scalar_text(value.get(key)))]
    text = _scalar_text(value)
    return [text] if text else []


def _has_recurrence(node: dict[str, Any]) -> bool:
    """Whether the node describes a repeating series this parser did not expand.

    The counterpart of `RRULE`/`RDATE`. One node yields one parsed event, never
    the occurrences a `Schedule` implies: expanding it would invent occurrences
    the parser cannot verify. The flag tells a downstream consumer the series is
    incomplete, rather than letting it read one occurrence as the whole story.

    The recognition is by shape, not by truthiness. `bool(node.get(...))` sets
    the flag for any truthy value of any type, so `{"garbage": 1}` reported a
    one-off event as an unexpanded series — telling a consumer its data is
    incomplete when it is not is still a wrong answer.
    """
    return (
        _is_schedule(node.get("eventSchedule"))
        or _first_text(node.get("repeatFrequency")) is not None
    )


def _is_schedule(value: Any) -> bool:
    """Whether a value is recognizably a `schema.org` `Schedule`."""
    if isinstance(value, list):
        return any(_is_schedule(item) for item in value)
    if isinstance(value, dict):
        if "Schedule" in _type_names(value):
            return True
        return any(key in _SCHEDULE_PROPERTIES for key in value)
    return _scalar_text(value) is not None


# ---------------------------------------------------------------------------
# MP-4 redaction
# ---------------------------------------------------------------------------


def _redact(text: str) -> str:
    """Replace detected email addresses and telephone numbers with the marker.

    See the module docstring for the guarantee's exact boundary: this catches
    structurally-detectable contact data, and does not catch personal names in
    prose, which are not machine-detectable and remain out of scope at this
    layer.
    """
    redacted = _EMAIL_PATTERN.sub(_REDACTION_MARKER, text)
    for pattern in _PHONE_PATTERNS:
        redacted = pattern.sub(_REDACTION_MARKER, redacted)
    return redacted


def _redacted(text: str | None) -> str | None:
    """`_redact` for an optional value, preserving `None`."""
    return None if text is None else _redact(text)


def _is_only_contact(text: str) -> bool:
    """Whether a value is contact data and nothing else.

    A field whose entire content is an address has not stated the thing the
    field is for. Redacting it would leave a marker standing where a name or a
    tag should be, which reads as though the source supplied one.
    """
    stripped = text.strip()
    if not stripped:
        return False
    if _EMAIL_PATTERN.fullmatch(stripped):
        return True
    return any(pattern.fullmatch(stripped) for pattern in _PHONE_PATTERNS)


# ---------------------------------------------------------------------------
# ADR-0010 temporal mapping
# ---------------------------------------------------------------------------


def _event_time(
    value: Any,
    zone_name: str,
    zone: ZoneInfo,
) -> EventTime:
    """Map `startDate` onto ADR-0010's three temporal states.

    Every failure path returns `UnresolvedTime`. There is deliberately no branch
    that produces an instant or a day the source did not state — which is why
    the date-only case is decided by *looking for a time separator in the text*
    before any parsing happens, rather than by parsing first and inspecting the
    result. `datetime.fromisoformat("2026-09-20")` succeeds and returns
    midnight; routing that value through this function's date-time branch would
    reintroduce the exact collapse ADR-0010 exists to prevent, silently.

    Both branches then full-match an explicit grammar rather than trusting
    `fromisoformat`, which since Python 3.11 accepts the whole ISO 8601 set and
    zero-fills anything a value omits. `"2026-W39"` names a week and `"2026-09-
    20T12"` names an hour; accepting either would hand a downstream consumer a
    precision the source never claimed.
    """
    raw = _start_date_text(value)
    if raw is None:
        return UnresolvedTime()

    if not any(separator in raw for separator in _DATE_TIME_SEPARATORS):
        if not _DATE_PATTERN.fullmatch(raw):
            return UnresolvedTime()
        parsed_date = _parse_date(raw)
        if parsed_date is None:
            return UnresolvedTime()
        return DateOnlyTime(on_date=parsed_date, time_zone=zone_name)

    if not _DATE_TIME_PATTERN.fullmatch(raw):
        return UnresolvedTime()
    instant = _parse_timestamp(raw, zone)
    if instant is None:
        return UnresolvedTime()
    return ExactTime(starts_at=instant, time_zone=zone_name)


def _start_date_text(value: Any) -> str | None:
    """The single `startDate` the source stated, if it stated exactly one.

    A list-valued `startDate` naming two different days is a contradiction, not
    a preference, and picking the first invents a choice the document never
    made. A list repeating one value is still that value.
    """
    texts = _all_texts(value)
    if not texts:
        return None
    if len(set(texts)) > 1:
        return None
    return texts[0]


def _parse_date(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _parse_timestamp(raw: str, fallback_zone: ZoneInfo) -> datetime | None:
    """Parse an ISO 8601 date-time into an aware datetime.

    Two forms, and one thing deliberately not done with either:

    - **With an offset** (`Z`, `+05:00`, `-07:00`) — the instant is preserved
      exactly as written, offset and all. The offset is *not* adopted as the
      event's `time_zone`; see the module docstring. `Z` is rewritten to
      `+00:00` because `fromisoformat` accepts the military designator only from
      Python 3.11, and rewriting is cheaper than depending on that.
    - **Without one** — floating local time, interpreted in the source's
      declared zone, exactly as `ical_parser` treats a `DTSTART` with no `TZID`.
      Twice a year that interpretation has no single answer, so it is checked:
      see `_resolve_floating`.

    An unparseable value returns `None`, which `_event_time` turns into
    `UnresolvedTime`.
    """
    text = raw
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return _resolve_floating(parsed, fallback_zone)
    return parsed


def _resolve_floating(naive: datetime, zone: ZoneInfo) -> datetime | None:
    """Attach the source's zone to a floating local time, or refuse to guess.

    A local wall-clock time is not always an instant. On the spring-forward day
    an hour does not exist, so `02:30` names nothing; on the fall-back day an
    hour happens twice, so `01:30` names two instants an hour apart and the
    source did not say which. `ZoneInfo` answers both anyway — it picks a fold
    and moves on — and that answer is a fabricated instant of exactly the kind
    ADR-0010 forbids.

    Detected by round-tripping through UTC and accepting only when exactly one
    instant maps back to the stated wall clock: a gap fails the round trip, and
    an ambiguous time is caught by the two folds disagreeing on their offset.
    `UnresolvedTime` is the correct answer for both.
    """
    first = naive.replace(tzinfo=zone, fold=0)
    second = naive.replace(tzinfo=zone, fold=1)
    if first.utcoffset() != second.utcoffset():
        return None
    round_tripped = first.astimezone(ZoneInfo("UTC")).astimezone(zone)
    if round_tripped.replace(tzinfo=None) != naive:
        return None
    return first
