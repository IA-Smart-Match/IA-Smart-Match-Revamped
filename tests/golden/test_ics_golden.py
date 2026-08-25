"""Golden tests for the ICS port (migration manifest MM-001).

Legacy source: Nebiux-Team-IA-West-SmartMatch@bdce024:src/outreach/ics_generator.py

Two kinds of test live here:

* **Preserved behavior** — the legacy output shape that must survive the port,
  so the port is provably not a rewrite that lost something.
* **Corrected behavior** — the three legacy defects, each with a test that would
  have failed against the legacy implementation. These are the evidence that the
  port fixed a real problem rather than reformatting one.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from smartmatch_domain.ics import (
    CalendarInvite,
    UnschedulableEventError,
    generate_ics,
)

FIXED_NOW = datetime(2026, 8, 17, 12, 0, 0, tzinfo=UTC)
FIXED_START = datetime(2026, 9, 15, 17, 0, 0, tzinfo=UTC)


def _lines(document: str) -> list[str]:
    """Split an ICS document into unfolded-aware raw lines."""
    return document.split("\r\n")


# ---------------------------------------------------------------------------
# Preserved behavior
# ---------------------------------------------------------------------------


@pytest.mark.golden
def test_document_structure_matches_legacy_shape():
    """The VCALENDAR/VEVENT envelope is unchanged from the legacy output."""
    doc = generate_ics(
        CalendarInvite(event_name="Careers Panel", starts_at=FIXED_START),
        generated_at=FIXED_NOW,
    )
    lines = _lines(doc)

    assert lines[0] == "BEGIN:VCALENDAR"
    assert "VERSION:2.0" in lines
    assert "CALSCALE:GREGORIAN" in lines
    assert "BEGIN:VEVENT" in lines
    assert "END:VEVENT" in lines
    assert lines[-2] == "END:VCALENDAR"


@pytest.mark.golden
def test_crlf_line_endings_preserved():
    """RFC 5545 requires CRLF. The legacy got this right; the port keeps it."""
    doc = generate_ics(
        CalendarInvite(event_name="Careers Panel", starts_at=FIXED_START),
        generated_at=FIXED_NOW,
    )
    assert doc.endswith("\r\n")
    # No bare LF anywhere.
    assert "\n" not in doc.replace("\r\n", "")


@pytest.mark.golden
def test_uid_is_deterministic_for_identical_input():
    """Regenerating an unchanged invite yields the same UID, as the legacy did."""
    invite = CalendarInvite(event_name="Careers Panel", starts_at=FIXED_START)
    first = generate_ics(invite, generated_at=FIXED_NOW)
    second = generate_ics(invite, generated_at=FIXED_NOW + timedelta(hours=3))

    uid_first = next(ln for ln in _lines(first) if ln.startswith("UID:"))
    uid_second = next(ln for ln in _lines(second) if ln.startswith("UID:"))
    assert uid_first == uid_second


@pytest.mark.golden
def test_uid_differs_for_different_events():
    """Distinct events must not collide on UID."""
    a = generate_ics(
        CalendarInvite(event_name="Careers Panel", starts_at=FIXED_START),
        generated_at=FIXED_NOW,
    )
    b = generate_ics(
        CalendarInvite(event_name="Ethics Seminar", starts_at=FIXED_START),
        generated_at=FIXED_NOW,
    )
    uid_a = next(ln for ln in _lines(a) if ln.startswith("UID:"))
    uid_b = next(ln for ln in _lines(b) if ln.startswith("UID:"))
    assert uid_a != uid_b


@pytest.mark.golden
def test_optional_fields_omitted_when_absent():
    """LOCATION and DESCRIPTION are omitted, not emitted empty — legacy behavior."""
    doc = generate_ics(
        CalendarInvite(event_name="Careers Panel", starts_at=FIXED_START),
        generated_at=FIXED_NOW,
    )
    assert "LOCATION:" not in doc
    assert "DESCRIPTION:" not in doc


@pytest.mark.golden
def test_text_escaping_matches_rfc5545():
    """Backslash, semicolon, comma, and newline escaping is preserved."""
    doc = generate_ics(
        CalendarInvite(
            event_name="Panel: AI, Ethics; and You",
            starts_at=FIXED_START,
            description="Line one\nLine two\\end",
        ),
        generated_at=FIXED_NOW,
    )
    assert "SUMMARY:Panel: AI\\, Ethics\\; and You" in doc
    assert "Line one\\nLine two\\\\end" in doc


@pytest.mark.golden
def test_default_duration_is_one_hour():
    """Legacy default of a one-hour event is preserved."""
    doc = generate_ics(
        CalendarInvite(event_name="Careers Panel", starts_at=FIXED_START),
        generated_at=FIXED_NOW,
    )
    assert "DTSTART:20260915T170000Z" in doc
    assert "DTEND:20260915T180000Z" in doc


# ---------------------------------------------------------------------------
# Corrected behavior — each of these fails against the legacy implementation
# ---------------------------------------------------------------------------


@pytest.mark.golden
def test_no_start_time_is_ever_fabricated():
    """Legacy defect 1.

    ``generate_ics("Talk", "Every Tuesday")`` returned a confident invite for a
    date 30 days out that nobody chose. Architecture v1.1 §3.6 (N1) prohibits
    fabricating a slot.

    The property under test is *the absence of any path from an unresolved date
    to a DTSTART*, not merely that a ``str`` is refused. Asserting the type
    rejection alone would pass against an implementation that type-checks its
    input and then defaults the missing start — which is precisely the legacy
    behavior — so all three legs below are needed:

    1. ``starts_at`` has no default, so there is nothing for a fallback to
       fabricate from;
    2. the recurrence strings the legacy actually fabricated from are refused
       with the documented unschedulable signal, and no document is produced;
    3. the emitted DTSTART is the caller's instant, never a derived one.
    """
    # 1. No default start. A default of "now + 30 days" is exactly the legacy
    #    defect, and it would survive a test that only checks the type rejection.
    with pytest.raises(TypeError):
        CalendarInvite(event_name="Talk")  # type: ignore[call-arg]

    # 2. Every distinct value of the legacy events dataset's recurrence column —
    #    the column the legacy UI actually passed as date_str — is refused.
    for recurrence in (
        "Every Tuesday",
        "Annual",
        "Ongoing",
        "Ongoing series + pitch events",
        "Recurring each term/year",
        "Annual (often spring)",
    ):
        with pytest.raises(UnschedulableEventError, match="never infers a time slot"):
            CalendarInvite(event_name="Talk", starts_at=recurrence)  # type: ignore[arg-type]

    # 3. DTSTART is the supplied instant and nothing else. The legacy fabricated
    #    `now + 30 days`, which for FIXED_NOW would be 16 September 2026.
    doc = generate_ics(
        CalendarInvite(event_name="Talk", starts_at=FIXED_START),
        generated_at=FIXED_NOW,
    )
    fabricated = (FIXED_NOW + timedelta(days=30)).strftime("%Y%m%dT%H%M%SZ")
    assert "DTSTART:20260915T170000Z" in doc
    assert f"DTSTART:{fabricated}" not in doc


@pytest.mark.golden
def test_no_itip_method_is_asserted_without_an_organizer_and_attendee():
    """RFC 5546 §3.2.2 (port defect F-1).

    A VCALENDAR carrying ``METHOD:REQUEST`` is an iTIP scheduling message, and
    the VEVENT it carries must then have an ORGANIZER and at least one ATTENDEE.
    The port emitted ``METHOD:REQUEST`` with neither — a new defect, since the
    legacy emitted no METHOD at all. The document now asserts no scheduling
    method it cannot back up.
    """
    doc = generate_ics(
        CalendarInvite(event_name="Careers Panel", starts_at=FIXED_START),
        generated_at=FIXED_NOW,
    )
    lines = _lines(doc)
    methods = [ln for ln in lines if ln.startswith("METHOD:")]
    has_organizer = any(ln.startswith("ORGANIZER") for ln in lines)
    has_attendee = any(ln.startswith("ATTENDEE") for ln in lines)

    # The conformance invariant, stated so it still holds if METHOD returns once
    # there is a real organizer identity to name (open decision 8).
    if methods:
        assert has_organizer, f"{methods[0]} requires an ORGANIZER (RFC 5546 §3.2.2)"
        assert has_attendee, f"{methods[0]} requires an ATTENDEE (RFC 5546 §3.2.2)"

    # The fix chosen today: no METHOD, matching the legacy and leaving a plain
    # RFC 5545 calendar object rather than an unbacked scheduling request.
    assert methods == []


@pytest.mark.golden
def test_dtstamp_is_required_and_never_read_from_the_clock():
    """MM-001 claims implicit clock reads were removed (port finding F-3).

    ``generated_at`` used to default to ``datetime.now(UTC)``, so the claim was
    false and the defaulting branch had no test. It is now required: the module
    reads no clock, and identical inputs always produce an identical document.
    """
    invite = CalendarInvite(event_name="Careers Panel", starts_at=FIXED_START)

    with pytest.raises(TypeError):
        generate_ics(invite)  # type: ignore[call-arg]

    doc = generate_ics(invite, generated_at=FIXED_NOW)
    assert "DTSTAMP:20260817T120000Z" in doc
    assert doc == generate_ics(invite, generated_at=FIXED_NOW)


@pytest.mark.golden
def test_naive_datetime_is_rejected_rather_than_claimed_as_utc():
    """Legacy defect 2.

    The legacy formatted a naive datetime with a trailing ``Z``, asserting UTC
    for a value that carried no timezone and shifting the event by the local
    offset in every consuming calendar.
    """
    with pytest.raises(UnschedulableEventError, match="timezone-aware"):
        CalendarInvite(
            event_name="Careers Panel",
            starts_at=datetime(2026, 9, 15, 17, 0, 0),  # naive
        )


@pytest.mark.golden
def test_non_utc_timezone_is_converted_not_relabeled():
    """A Pacific-time event is converted to real UTC, not stamped Z as-is."""
    pacific = timezone(timedelta(hours=-7))
    doc = generate_ics(
        CalendarInvite(
            event_name="Careers Panel",
            starts_at=datetime(2026, 9, 15, 10, 0, 0, tzinfo=pacific),
        ),
        generated_at=FIXED_NOW,
    )
    # 10:00 at UTC-07:00 is 17:00 UTC.
    assert "DTSTART:20260915T170000Z" in doc


@pytest.mark.golden
def test_long_lines_are_folded_to_75_octets():
    """Legacy defect 3: RFC 5545 §3.1 line folding was absent entirely."""
    doc = generate_ics(
        CalendarInvite(
            event_name="A" * 200,
            starts_at=FIXED_START,
        ),
        generated_at=FIXED_NOW,
    )
    for line in _lines(doc):
        assert len(line.encode("utf-8")) <= 75, f"unfolded line: {line[:90]!r}"


@pytest.mark.golden
def test_folded_continuation_lines_begin_with_a_space():
    """Unfolding requires the continuation marker RFC 5545 specifies."""
    doc = generate_ics(
        CalendarInvite(event_name="B" * 200, starts_at=FIXED_START),
        generated_at=FIXED_NOW,
    )
    lines = _lines(doc)
    summary_index = next(i for i, ln in enumerate(lines) if ln.startswith("SUMMARY:"))
    # The next line is a continuation and must start with a single space.
    assert lines[summary_index + 1].startswith(" ")

    # Unfolding reconstructs the original value.
    unfolded = doc.replace("\r\n ", "")
    assert f"SUMMARY:{'B' * 200}" in unfolded


@pytest.mark.golden
def test_folding_never_splits_a_multibyte_codepoint():
    """Folding is defined over octets, so naive character folding corrupts UTF-8."""
    doc = generate_ics(
        CalendarInvite(event_name="é" * 100, starts_at=FIXED_START),
        generated_at=FIXED_NOW,
    )
    # If a codepoint had been split, decoding the document would already have
    # failed; assert round-trip explicitly and check the octet bound holds.
    assert doc.encode("utf-8").decode("utf-8") == doc
    for line in _lines(doc):
        assert len(line.encode("utf-8")) <= 75
    unfolded = doc.replace("\r\n ", "")
    assert f"SUMMARY:{'é' * 100}" in unfolded


@pytest.mark.golden
def test_end_before_start_is_rejected():
    """A negative-duration event was accepted by the legacy and is now refused."""
    with pytest.raises(ValueError, match="must not precede"):
        CalendarInvite(
            event_name="Careers Panel",
            starts_at=FIXED_START,
            ends_at=FIXED_START - timedelta(hours=1),
        )


@pytest.mark.golden
def test_blank_event_name_is_rejected():
    """A blank SUMMARY produces a technically-valid but useless invite."""
    with pytest.raises(ValueError, match="non-blank"):
        CalendarInvite(event_name="   ", starts_at=FIXED_START)
