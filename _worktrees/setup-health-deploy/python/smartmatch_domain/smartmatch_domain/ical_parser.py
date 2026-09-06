"""Parse iCalendar text into ADR-0010 temporal types.

The inverse direction from `smartmatch_domain.ics`, which *renders* invites.
This module reads a calendar document and produces `ParsedSourceEvent` values
for the discovery pipeline.

**Purity.** No transport, no file access, no environment. The caller supplies
the document as text, so this module stays inside the domain's import contract
(`pyproject.toml` forbids `os`, `pathlib`, `socket` here) and can be exercised
entirely against committed fixtures. Fetching is a worker concern gated behind
R3; nothing here reaches a network.

**The invariant.** ADR-0010: a source that does not state a time does not
acquire one. `DTSTART;VALUE=DATE` becomes `DateOnlyTime`, never an instant at
midnight — that collapse is the defect ADR-0010 exists to prevent. An absent or
unparseable `DTSTART` becomes `UnresolvedTime`, which `resolve_identity_key`
turns into "no identity key" rather than a fabricated one. `UnresolvedTime` is a
correct answer, never a degraded one: where a value is stated but cannot be
resolved without inventing something — an unknown `TZID`, a wall time that does
not exist or that happens twice, a value with trailing junk — the answer is
`UnresolvedTime` rather than a plausible substitute.

**Malformed versus empty.** A calendar with zero `VEVENT`s returns `()`. A
document that is structurally broken — an unterminated, mismatched, or nested
`VEVENT` — raises `ValueError`. A truncated feed that silently returned `()`
would be indistinguishable from "the source published nothing today", which is
exactly the failure this parser must keep visible.

**MP-4, stated precisely.** This module enforces two things, and claims no more:

1. Structural contact properties are never read. The `mailto:` value of
   `ORGANIZER`, and `ATTENDEE` lines entirely, are dropped rather than emitted.
2. Email addresses and telephone numbers matching `_EMAIL_PATTERN` and
   `_PHONE_PATTERN` are replaced with `_REDACTION_MARKER` in every emitted
   string field. The marker is deliberately visible and non-reversible; silent
   deletion would leave prose that still reads as complete.

What it does **not** enforce: personal *names* in free prose. "Call Alice at
[redacted]" still names Alice, and no pattern available at this layer finds that
reliably. Names remain the MP-4 evaluation boundary's problem while P9 Gate B is
open. That limit is written out rather than glossed because the project's own
prompt-injection assessment (§2.1, on `_sanitize_for_prompt`) records what
happens otherwise: a security comment claiming more than the code delivers makes
reviewers stop looking.

**Why `source_time_zone` is required.** `resolved_date` converts an instant into
a zone to produce the date ADR-0012 keys on, so the zone decides the date. A
`DTSTART` ending in `Z` carries an unambiguous instant but says nothing about
where the event happens: 2026-04-16T02:00Z is 15 April in Los Angeles.
Defaulting to UTC would silently key such events one day late. The zone
therefore comes from the source registry, as a declared fact about the source,
and the parser refuses to run without one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from smartmatch_domain.events import (
    DateOnlyTime,
    EventTime,
    ExactTime,
    UnresolvedTime,
)

__all__ = [
    "ICAL_PARSER_VERSION",
    "ParsedSourceEvent",
    "parse_ical",
]

#: Recorded on `EventProvenance.extractor_version` by callers, so a stored
#: observation can be traced to the exact parser that produced it. Bump on any
#: change to parsing behaviour.
ICAL_PARSER_VERSION: Final = "ical_parser/2"

#: `DATE`, per RFC 5545 §3.3.4. Anchored: a value with anything after the eighth
#: digit is not a date, and slicing a prefix off it would accept `20260920junk`.
_DATE_GRAMMAR: Final = re.compile(r"\A(?P<date>\d{8})\Z")

#: `DATE-TIME`, per RFC 5545 §3.3.5, plus the numeric UTC offset real feeds emit
#: in defiance of it. Anchored for the same reason as `_DATE_GRAMMAR`: the old
#: `raw[:15]` slice silently discarded a stated `+0900`, which moved the instant
#: and with it the ADR-0012 identity date.
_DATE_TIME_GRAMMAR: Final = re.compile(r"\A(?P<naive>\d{8}T\d{6})(?P<suffix>Z|[+-]\d{2}:?\d{2})?\Z")

#: What replaces a matched email address or telephone number. Fixed, visible,
#: and carrying no part of the original — see the module docstring on MP-4.
_REDACTION_MARKER: Final = "[redacted]"

#: Addr-spec, narrowed to what appears in calendar prose. Not RFC 5322-complete;
#: it does not need to be, because over-matching here costs a redaction marker
#: while under-matching costs an emitted address.
_EMAIL_PATTERN: Final = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

#: Telephone numbers in the separated forms campus pages use: `909-555-0100`,
#: `(909) 555-0100`, `+1 909.555.0100`. A separator between groups is required
#: and the match is fenced by non-digits, so timestamps (`20260415T090000`),
#: ISO dates (`2026-04-15`) and long numeric UIDs are left alone. An unseparated
#: run of ten digits is deliberately *not* matched: at this layer it is not
#: distinguishable from an identifier, and redacting UIDs would break identity.
_PHONE_PATTERN: Final = re.compile(
    r"(?<![\d-])(?:\+\d{1,3}[\s.-]?)?(?:\(\d{3}\)\s?|\d{3}[\s.-])\d{3}[\s.-]\d{4}(?!\d)"
)


@dataclass(frozen=True, slots=True)
class ParsedSourceEvent:
    """One `VEVENT`, decoded but not yet interpreted.

    Deliberately *not* a domain `Event`. Tags stay raw because mapping them to
    the closed vocabulary is card S5's job and the vocabulary is owner-approved;
    a parser that resolved tags would be choosing terms. Likewise there is no
    `host_org_unit` here: that is resolved from a human-curated mapping, never
    from source content (T-11 control C-4).
    """

    title: str
    event_time: EventTime
    source_uid: str | None = None
    source_url: str | None = None
    location: str | None = None
    organizer_name: str | None = None
    description: str | None = None
    raw_tags: tuple[str, ...] = ()
    is_cancelled: bool = False
    has_unexpanded_recurrence: bool = False


def parse_ical(
    text: str,
    *,
    source_time_zone: str,
) -> tuple[ParsedSourceEvent, ...]:
    """Decode an iCalendar document into parsed events.

    Args:
        text: The full calendar document. `CRLF` and bare `LF` line endings are
            both accepted; real feeds vary.
        source_time_zone: IANA zone the source declares for its events, from the
            source registry. Used when a `DTSTART` carries no `TZID`, and as the
            display zone for date-only values. Never guessed.

    Returns:
        One `ParsedSourceEvent` per `VEVENT`, in document order. A *valid*
        calendar with no events returns an empty tuple rather than raising — an
        empty feed is a legitimate answer and must stay distinguishable from a
        fetch failure. A structurally broken document raises instead, so that a
        truncated feed cannot masquerade as an empty one.

    Raises:
        ValueError: If `source_time_zone` is blank or not a known IANA zone, or
            if the document is structurally malformed — an unterminated `VEVENT`,
            an `END` that does not match its `BEGIN`, or a nested `VEVENT`.
    """
    zone = _require_known_zone(source_time_zone)
    return tuple(
        _parse_vevent(block, source_time_zone, zone) for block in _vevent_blocks(_unfold(text))
    )


def _require_known_zone(name: str) -> ZoneInfo:
    """Resolve an IANA zone name, rejecting blanks and unknown names.

    Mirrors `events._require_known_time_zone`: a real-but-misspelled zone is
    caught here rather than left for an adapter to notice later.
    """
    if not name or not name.strip():
        raise ValueError("source_time_zone must not be blank")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"unknown IANA time zone: {name!r}") from exc


def _unfold(text: str) -> list[str]:
    """Undo RFC 5545 §3.1 line folding.

    A line beginning with a space or tab continues the previous one. Feeds fold
    at 75 octets, so long titles and descriptions arrive split; a parser that
    skipped this would truncate them.
    """
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _vevent_blocks(lines: list[str]) -> list[list[str]]:
    """Group unfolded lines into `VEVENT` blocks, ignoring other components.

    `VTIMEZONE` and calendar-level properties are skipped: this parser reads the
    zone from `TZID` parameters and the caller's declared zone, and does not
    interpret embedded timezone definitions.

    Child components of a `VEVENT` — `VALARM` above all — are skipped whole
    rather than flattened into the event. Flattening let a `VALARM`'s
    `DESCRIPTION` overwrite the event's under last-occurrence-wins, which is both
    wrong and an MP-4 leak path, since alarm text is where "call N at <number>"
    lives.

    Raises:
        ValueError: On an unterminated `VEVENT`, an `END` that does not match the
            innermost open `BEGIN`, or a nested `VEVENT`.
    """
    blocks: list[list[str]] = []
    current: list[str] | None = None
    nested: list[str] = []
    for line in lines:
        marker = line.strip().upper()
        begins = marker.startswith("BEGIN:")
        ends = marker.startswith("END:")

        if current is None:
            if marker == "END:VEVENT":
                raise ValueError("END:VEVENT with no matching BEGIN:VEVENT")
            if marker == "BEGIN:VEVENT":
                current = []
            continue

        if nested:
            if begins:
                nested.append(marker[len("BEGIN:") :])
            elif ends:
                closing = marker[len("END:") :]
                if closing != nested[-1]:
                    raise ValueError(f"END:{closing} does not close BEGIN:{nested[-1]}")
                nested.pop()
            continue

        if marker == "BEGIN:VEVENT":
            raise ValueError("nested BEGIN:VEVENT")
        if begins:
            nested.append(marker[len("BEGIN:") :])
        elif marker == "END:VEVENT":
            blocks.append(current)
            current = None
        elif ends:
            raise ValueError(f"{marker} does not close BEGIN:VEVENT")
        else:
            current.append(line)

    if current is not None:
        raise ValueError("unterminated BEGIN:VEVENT")
    return blocks


@dataclass(frozen=True, slots=True)
class _Property:
    """One content line, split into its name, parameters, and value."""

    name: str
    params: dict[str, str] = field(default_factory=dict)
    value: str = ""


def _parse_property(line: str) -> _Property | None:
    """Split `NAME;PARAM=value:the value` into its parts.

    Returns `None` for a line with no colon, which is not a content line.
    """
    head, separator, value = line.partition(":")
    if not separator:
        return None
    name, _, param_text = head.partition(";")
    params: dict[str, str] = {}
    for chunk in param_text.split(";") if param_text else []:
        key, _, param_value = chunk.partition("=")
        if key:
            params[key.strip().upper()] = param_value.strip().strip('"')
    return _Property(name.strip().upper(), params, value)


def _parse_vevent(
    lines: list[str],
    zone_name: str,
    zone: ZoneInfo,
) -> ParsedSourceEvent:
    properties: dict[str, _Property] = {}
    categories: list[str] = []
    for line in lines:
        prop = _parse_property(line)
        if prop is None:
            continue
        if prop.name == "ATTENDEE":
            # Wholly contact data. Never read, so no later change to the emitted
            # field set can start emitting it by accident (MP-4).
            continue
        if prop.name == "CATEGORIES":
            categories.extend(_split_categories(prop.value))
        else:
            # Last occurrence wins. RFC 5545 allows repeats for some properties;
            # none of the single-valued ones read here benefit from the first.
            properties[prop.name] = prop

    summary = properties.get("SUMMARY")
    status = properties.get("STATUS")

    return ParsedSourceEvent(
        title=_redact_contact_data(_unescape(summary.value)) if summary else "",
        event_time=_event_time(properties.get("DTSTART"), zone_name, zone),
        source_uid=_optional(properties, "UID", redact=False),
        source_url=_optional(properties, "URL", redact=True),
        location=_optional(properties, "LOCATION", redact=True),
        organizer_name=_organizer_name(properties.get("ORGANIZER")),
        description=_optional(properties, "DESCRIPTION", redact=True),
        raw_tags=tuple(categories),
        is_cancelled=status is not None and status.value.strip().upper() == "CANCELLED",
        has_unexpanded_recurrence="RRULE" in properties or "RDATE" in properties,
    )


def _optional(
    properties: dict[str, _Property],
    name: str,
    *,
    redact: bool,
) -> str | None:
    """An unescaped property value, or `None` when absent or blank.

    Blank becomes `None` rather than `""` so a caller cannot mistake "the source
    said nothing" for "the source said empty".

    Args:
        properties: The event's collected properties.
        name: The property to read.
        redact: Whether to strip contact data from the value. `True` for every
            field a human ever reads. `False` only for `UID`, which is an opaque
            identifier: campus feeds routinely mint UIDs that *look* like
            addresses (`synthetic-0001@example.edu`), and rewriting one would
            destroy the ADR-0012 identity it exists to carry without protecting
            anybody — nothing renders a UID as prose.
    """
    prop = properties.get(name)
    if prop is None:
        return None
    value = _unescape(prop.value).strip()
    if redact:
        value = _redact_contact_data(value)
    return value or None


def _redact_contact_data(value: str) -> str:
    """Replace email addresses and telephone numbers with `_REDACTION_MARKER`.

    This is the whole of the MP-4 control on emitted prose, and its limits are
    exactly the limits of the two patterns: an address or number in a shape
    neither pattern describes survives, and a personal name always survives. See
    the module docstring — the boundary is stated there rather than implied here.

    The marker is left in place of the match, never dropped, so a reader can see
    that the sentence is incomplete rather than reading a mangled one as whole.
    """
    return _PHONE_PATTERN.sub(_REDACTION_MARKER, _EMAIL_PATTERN.sub(_REDACTION_MARKER, value))


def _organizer_name(prop: _Property | None) -> str | None:
    """The organizer's display name from the `CN` parameter, or `None`.

    The value half is a `mailto:` URI and is never returned — it is contact data
    outright.

    `CN` is *not* automatically a name either, which is what made the previous
    version of this control ineffective: feeds very commonly set
    `CN=alice@example.edu`, so returning `CN` verbatim emitted an address while
    the docstring claimed addresses were withheld. So `CN` is redacted like any
    other emitted text, and if what remains holds no word characters at all —
    the whole parameter was an address or a number — the answer is `None`. A
    redaction marker is not a display name, and emitting `"[redacted]"` as one
    would be worse than admitting the source gave none.
    """
    if prop is None:
        return None
    common_name = _redact_contact_data(_unescape(prop.params.get("CN", "")).strip())
    without_markers = common_name.replace(_REDACTION_MARKER, "")
    if not re.search(r"\w", without_markers):
        return None
    return common_name or None


def _split_categories(value: str) -> list[str]:
    """Split a `CATEGORIES` value on unescaped commas.

    Values stay raw and unnormalized — resolving them against the closed
    vocabulary is card S5's responsibility — but "raw" does not extend to contact
    data: tags are emitted text like any other, and feeds do put phone numbers in
    them. Redaction happens here, before S5 ever sees the value.
    """
    return [
        redacted
        for chunk in re.split(r"(?<!\\),", value)
        if (redacted := _redact_contact_data(_unescape(chunk).strip()))
    ]


def _unescape(value: str) -> str:
    """Reverse RFC 5545 §3.3.11 TEXT escaping.

    Handled in one pass so an escaped backslash cannot have its output
    re-interpreted as the start of another escape.
    """
    out: list[str] = []
    index = 0
    while index < len(value):
        char = value[index]
        if char == "\\" and index + 1 < len(value):
            nxt = value[index + 1]
            out.append("\n" if nxt in ("n", "N") else nxt)
            index += 2
            continue
        out.append(char)
        index += 1
    return "".join(out)


def _event_time(
    prop: _Property | None,
    zone_name: str,
    zone: ZoneInfo,
) -> EventTime:
    """Map `DTSTART` onto ADR-0010's three temporal states.

    Every failure path returns `UnresolvedTime`. There is deliberately no branch
    that produces an instant the source did not state.
    """
    if prop is None or not prop.value.strip():
        return UnresolvedTime()

    raw = prop.value.strip()

    declared_value_type = prop.params.get("VALUE", "").upper()

    if declared_value_type == "DATE":
        # `VALUE=DATE` carrying a clock time is contradictory input. The old code
        # sliced eight characters off the front and dropped the rest, which threw
        # away a time the source did state; neither reading is safe to pick, so
        # the honest answer is that the time is unresolved.
        parsed_date = _parse_date(raw)
        return (
            DateOnlyTime(on_date=parsed_date, time_zone=zone_name)
            if parsed_date is not None
            else UnresolvedTime()
        )

    if not declared_value_type and (bare_date := _parse_date(raw)) is not None:
        # Bare `DTSTART:20260920` — a date, with no `VALUE` parameter to say so.
        return DateOnlyTime(on_date=bare_date, time_zone=zone_name)

    instant = _parse_timestamp(raw, prop.params.get("TZID"), zone)
    if instant is None:
        return UnresolvedTime()
    return ExactTime(starts_at=instant, time_zone=zone_name)


def _parse_date(raw: str) -> date | None:
    """A `DATE` value, or `None` if the *whole* value is not one."""
    if _DATE_GRAMMAR.fullmatch(raw) is None:
        return None
    try:
        return datetime.strptime(raw, "%Y%m%d").date()
    except ValueError:
        return None


def _parse_timestamp(
    raw: str,
    tzid: str | None,
    source_zone: ZoneInfo,
) -> datetime | None:
    """Parse a `DATE-TIME` value into an aware datetime, or `None`.

    `None` means "this cannot be resolved without inventing something", and the
    caller turns it into `UnresolvedTime`. Four forms:

    - trailing `Z` — UTC. The instant is preserved exactly; the *display* zone is
      the caller's declared source zone, set by `_event_time`.
    - a trailing numeric offset (`+0900`, `-07:00`) — also a stated instant, and
      honoured as one. An offset is not a zone, so the recorded `time_zone` stays
      the declared source zone; this is the `Z` rule generalised. Dropping the
      offset and re-reading the wall time in the source zone, as the old prefix
      slice did, moved the instant by hours and with it the ADR-0012 identity
      date.
    - a `TZID` parameter — local time in that named zone. An unknown or
      unresolvable name yields `None`. It previously fell back to the source's
      declared zone, which is the one answer that cannot be right: the source
      named a zone, the name meant nothing here, and answering in a *different*
      zone states an instant the source never gave.
    - neither — floating local time in the source's declared zone.

    Both zone-relative forms go through `_unambiguous_instant`, because a wall
    time is an instant only when exactly one instant matches it.
    """
    match = _DATE_TIME_GRAMMAR.fullmatch(raw)
    if match is None:
        return None

    try:
        naive = datetime.strptime(match.group("naive"), "%Y%m%dT%H%M%S")
    except ValueError:
        return None

    suffix = match.group("suffix")
    if suffix == "Z":
        return naive.replace(tzinfo=UTC)
    if suffix:
        return naive.replace(tzinfo=_fixed_offset(suffix))

    if tzid:
        try:
            named_zone = ZoneInfo(tzid)
        except (ZoneInfoNotFoundError, ValueError):
            return None
        return _unambiguous_instant(naive, named_zone)

    return _unambiguous_instant(naive, source_zone)


def _fixed_offset(suffix: str) -> timezone:
    """Turn a `+HHMM` / `-HH:MM` suffix into a fixed-offset tzinfo.

    The grammar has already matched, so the digits are known to be well-formed.
    """
    sign = -1 if suffix[0] == "-" else 1
    digits = suffix[1:].replace(":", "")
    hours, minutes = int(digits[:2]), int(digits[2:])
    return timezone(sign * timedelta(hours=hours, minutes=minutes))


def _unambiguous_instant(naive: datetime, zone: ZoneInfo) -> datetime | None:
    """Attach `zone` to a wall time, but only where that names exactly one instant.

    A local time is not always an instant. On a DST spring-forward day the stated
    wall time may not exist at all (02:30 on 2026-03-08 in Los Angeles); on a
    fall-back day it may happen twice (01:30 on 2026-11-01), where `fold=0`
    silently picks one of the two. Either way an `ExactTime` would state a
    precision the source does not have, so both yield `None` and the event
    becomes `UnresolvedTime` — ADR-0010's answer for "the time is not known",
    which is precisely the situation.

    Detected by round-tripping rather than by reading transition tables: the two
    `fold` readings must agree on the UTC offset (or the wall time is ambiguous),
    and converting to UTC and back must return the wall time that was asked for
    (or the wall time does not exist).
    """
    attached = naive.replace(tzinfo=zone, fold=0)
    if attached.utcoffset() != naive.replace(tzinfo=zone, fold=1).utcoffset():
        return None
    if attached.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != naive:
        return None
    return attached
