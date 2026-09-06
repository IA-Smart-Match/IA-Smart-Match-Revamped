"""RFC 5545 iCalendar generation.

Ported from Nebiux-Team-IA-West-SmartMatch@bdce024:src/outreach/ics_generator.py
under migration manifest entry MM-001. Pure string building, no external
library, no IO — the property that made the legacy implementation worth keeping.

Architecture v1.1 §3.1 makes ICS the *only* supported calendar artifact until an
institutional Calendar authorization model is approved (open decision 4, gate
G5). §3.6 additionally requires that a calendar failure be visible as
unsynchronized rather than silently substituted.

Three defects in the legacy implementation are fixed here, each covered by a
golden test in ``tests/golden/test_ics_golden.py``:

1. **Fabricated dates.** ``_parse_date`` silently returned "30 days from now"
   for any unparseable input, so ``generate_ics("Talk", "Every Tuesday")``
   produced a confident, entirely invented meeting slot. Architecture v1.1 §3.6
   prohibits fabricating a slot (N1). :func:`generate_ics` now requires an
   explicit ``datetime`` and raises on ambiguity — callers must resolve a real
   time or surface "unscheduled" to the user.

2. **False UTC claims.** The legacy formatted naive datetimes with a trailing
   ``Z``, asserting UTC for a value parsed without any timezone. A 09:00 local
   event was emitted as ``T090000Z``, shifting it by the local offset in every
   consuming calendar. Timezone-aware input is now required and converted to
   real UTC.

3. **Missing line folding.** RFC 5545 §3.1 caps content lines at 75 octets and
   requires continuation lines to begin with a space. The legacy emitted
   arbitrarily long ``SUMMARY``/``DESCRIPTION`` lines, which strict parsers
   reject. :func:`_fold_line` now folds on octet boundaries, correctly handling
   multi-byte UTF-8.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

__all__ = [
    "ICS_CONTENT_TYPE",
    "CalendarInvite",
    "UnschedulableEventError",
    "generate_ics",
]

ICS_CONTENT_TYPE: Final[str] = "text/calendar; charset=utf-8"

#: RFC 5545 §3.1: content lines are folded at 75 octets, excluding the CRLF.
_MAX_LINE_OCTETS: Final[int] = 75

#: Stable UID namespace. Not a routable hostname — RFC 5545 only requires the
#: UID be globally unique, and using a real domain would imply mail routing that
#: does not exist (domain registration is open decision 8).
_UID_NAMESPACE: Final[str] = "smartmatch.invalid"


class UnschedulableEventError(ValueError):
    """Raised when an invite is requested without a resolvable start time.

    Architecture v1.1 §3.6 (N1) prohibits fabricating a time slot. Callers must
    handle this by surfacing an explicit unscheduled/unsynchronized state rather
    than substituting a plausible-looking date.
    """


@dataclass(frozen=True, slots=True)
class CalendarInvite:
    """A single VEVENT to render.

    Attributes:
        event_name: Rendered as SUMMARY. Required and non-blank.
        starts_at: Timezone-aware start. Naive datetimes are rejected, because
            emitting one as UTC is the legacy timezone defect.
        ends_at: Timezone-aware end. Defaults to one hour after ``starts_at``.
        location: Optional LOCATION.
        description: Optional DESCRIPTION.
        uid: Optional explicit UID. When omitted a deterministic UID is derived
            from the event name and start instant, so regenerating an invite for
            the same event updates it in the recipient's calendar rather than
            creating a duplicate.
    """

    event_name: str
    starts_at: datetime
    ends_at: datetime | None = None
    location: str | None = None
    description: str | None = None
    uid: str | None = None

    def __post_init__(self) -> None:
        if not self.event_name or not self.event_name.strip():
            raise ValueError("event_name must be a non-blank string")
        _require_aware(self.starts_at, "starts_at")
        if self.ends_at is not None:
            _require_aware(self.ends_at, "ends_at")
            if self.ends_at < self.starts_at:
                raise ValueError("ends_at must not precede starts_at")


def _require_aware(value: datetime, field: str) -> None:
    """Reject naive datetimes.

    Fixes legacy defect 2: a naive datetime formatted with a trailing ``Z``
    claims UTC for a value that never carried a timezone.
    """
    if not isinstance(value, datetime):
        raise UnschedulableEventError(
            f"{field} must be a timezone-aware datetime; got {type(value).__name__}. "
            "SmartMatch never infers a time slot (architecture v1.1 §3.6)."
        )
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise UnschedulableEventError(
            f"{field} must be timezone-aware. A naive datetime emitted as UTC "
            "silently shifts the event by the local offset."
        )


def _escape_text(text: str) -> str:
    """Escape per RFC 5545 §3.3.11 TEXT rules.

    Backslash first, so escapes introduced below are not re-escaped. Carriage
    returns are normalized away rather than escaped, since RFC 5545 represents a
    line break in TEXT as the two-character sequence ``\\n``.
    """
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\r", "\\n")
        .replace("\n", "\\n")
    )


def _fold_line(line: str) -> str:
    """Fold one content line to RFC 5545 §3.1 octet limits.

    Fixes legacy defect 3. Folding is defined over *octets*, not characters, so
    a naive character-count fold splits multi-byte UTF-8 and can emit invalid
    sequences. This encodes first and folds on the byte string, then walks back
    to a codepoint boundary.

    Continuation lines begin with a single space, which the parser strips when
    unfolding.
    """
    encoded = line.encode("utf-8")
    if len(encoded) <= _MAX_LINE_OCTETS:
        return line

    pieces: list[str] = []
    remaining = encoded
    limit = _MAX_LINE_OCTETS
    while len(remaining) > limit:
        cut = limit
        # Walk back off a UTF-8 continuation byte (0b10xxxxxx) so we never split
        # a codepoint across a fold.
        while cut > 0 and (remaining[cut] & 0xC0) == 0x80:
            cut -= 1
        pieces.append(remaining[:cut].decode("utf-8"))
        remaining = remaining[cut:]
        # Continuation lines spend one octet on the leading space.
        limit = _MAX_LINE_OCTETS - 1
    pieces.append(remaining.decode("utf-8"))

    return "\r\n ".join(pieces)


def _format_utc(value: datetime) -> str:
    """Render a timezone-aware datetime as an RFC 5545 UTC timestamp."""
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _derive_uid(event_name: str, starts_at: datetime) -> str:
    """Derive a deterministic UID from event identity and start instant.

    Deterministic so that regenerating the invite for an unchanged event yields
    the same UID, letting calendar clients treat it as an update.
    """
    raw = f"{event_name}|{_format_utc(starts_at)}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    return f"{digest}@{_UID_NAMESPACE}"


def generate_ics(
    invite: CalendarInvite,
    *,
    generated_at: datetime,
) -> str:
    """Render a ``CalendarInvite`` as an RFC 5545 VCALENDAR document.

    Args:
        invite: The event to render.
        generated_at: DTSTAMP instant. Required and injected: this module reads
            no clock at all, so the same inputs always produce the same
            document. The parameter was previously optional and defaulted to
            ``datetime.now(UTC)``, which left one implicit clock read in a
            package whose purity is otherwise enforced by import contracts, and
            left the defaulting branch untestable without freezing time — which
            would need a dependency the domain package may not have.

    Returns:
        The .ics document, CRLF-terminated, folded to 75 octets per line.

    Raises:
        UnschedulableEventError: if ``generated_at`` is naive.
    """
    _require_aware(generated_at, "generated_at")

    ends_at = invite.ends_at or (invite.starts_at + timedelta(hours=1))
    uid = invite.uid or _derive_uid(invite.event_name, invite.starts_at)

    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//IA West SmartMatch//Event Invite//EN",
        "CALSCALE:GREGORIAN",
        # No METHOD. A VCALENDAR carrying METHOD:REQUEST is an iTIP scheduling
        # message, and RFC 5546 §3.2.2 makes ORGANIZER and at least one ATTENDEE
        # mandatory on the VEVENT it carries. SmartMatch has neither: there is no
        # organizer identity to name (mail-domain registration is open decision
        # 8, which is also why the UID namespace is a .invalid TLD) and no
        # attendee model. The two conformant options were to drop METHOD or to
        # require an organizer and attendees before emitting it; the second
        # cannot be satisfied without inventing an address, and inventing a value
        # the data does not support is the defect class this port exists to end
        # (see the fabricated dates above). Dropping METHOD also restores the
        # legacy behavior — it emitted none — and leaves a plain RFC 5545
        # calendar object, which is what an .ics download actually is. Re-add
        # METHOD in the release that has a real organizer to put in it.
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{_format_utc(generated_at)}",
        f"DTSTART:{_format_utc(invite.starts_at)}",
        f"DTEND:{_format_utc(ends_at)}",
        f"SUMMARY:{_escape_text(invite.event_name)}",
    ]

    if invite.location is not None:
        lines.append(f"LOCATION:{_escape_text(invite.location)}")
    if invite.description is not None:
        lines.append(f"DESCRIPTION:{_escape_text(invite.description)}")

    lines += ["STATUS:CONFIRMED", "END:VEVENT", "END:VCALENDAR"]

    return "".join(f"{_fold_line(line)}\r\n" for line in lines)
