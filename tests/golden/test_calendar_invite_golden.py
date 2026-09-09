"""Golden tests for the ICS calendar-invite facade (finding F-003, gate G5).

`tests/golden/test_ics_golden.py` pins RFC 5545 rendering itself. What is
covered here is the narrower contract the facade adds on top of it, and the
fact that it adds *only* that: the document bytes must remain byte-identical to
what `generate_ics` produces, or the facade has quietly become a second
implementation of the rules F-003 exists to protect.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from smartmatch_domain.calendar_invite import (
    ICS_CONTENT_TYPE,
    ICS_ENCODING,
    UnschedulableEventError,
    build_invite_ics,
)
from smartmatch_domain.ics import CalendarInvite, generate_ics

FIXED_NOW = datetime(2026, 8, 17, 12, 0, 0, tzinfo=UTC)
FIXED_START = datetime(2026, 9, 15, 17, 0, 0, tzinfo=UTC)
FIXED_END = datetime(2026, 9, 15, 18, 30, 0, tzinfo=UTC)


def _build(**overrides: object) -> bytes:
    kwargs: dict[str, object] = {
        "title": "Careers Panel",
        "starts_at": FIXED_START,
        "ends_at": FIXED_END,
        "generated_at": FIXED_NOW,
    }
    kwargs.update(overrides)
    return build_invite_ics(**kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# The facade delegates rather than reimplements
# ---------------------------------------------------------------------------


@pytest.mark.golden
def test_bytes_are_exactly_the_generate_ics_document_utf8_encoded():
    """The one property that keeps this a facade.

    If folding, escaping, or UTC conversion were ever re-derived here, this
    equality is what breaks — before any consuming calendar sees the divergence.
    """
    expected = generate_ics(
        CalendarInvite(
            event_name="Panel: AI, Ethics; and You",
            starts_at=FIXED_START,
            ends_at=FIXED_END,
            location="Room 12",
            description="Line one\nLine two",
        ),
        generated_at=FIXED_NOW,
    )

    produced = _build(
        title="Panel: AI, Ethics; and You",
        location="Room 12",
        description="Line one\nLine two",
    )

    assert produced == expected.encode(ICS_ENCODING)


@pytest.mark.golden
def test_output_is_bytes_decodable_with_the_declared_charset():
    """The declared content type and the actual encoding must agree."""
    document = _build()

    assert isinstance(document, bytes)
    assert ICS_ENCODING in ICS_CONTENT_TYPE
    text = document.decode(ICS_ENCODING)
    assert text.startswith("BEGIN:VCALENDAR\r\n")
    assert text.endswith("END:VCALENDAR\r\n")


@pytest.mark.golden
def test_folding_still_holds_on_the_octet_stream():
    """Folding is an octet property, so assert it on the octets the caller gets."""
    document = _build(title="A" * 200, description="é" * 100)

    for line in document.split(b"\r\n"):
        assert len(line) <= 75, f"unfolded line: {line[:90]!r}"
    assert document.decode(ICS_ENCODING).encode(ICS_ENCODING) == document


@pytest.mark.golden
def test_a_non_utc_slot_is_converted_not_relabeled():
    pacific = timezone(timedelta(hours=-7))
    document = _build(
        starts_at=datetime(2026, 9, 15, 10, 0, 0, tzinfo=pacific),
        ends_at=datetime(2026, 9, 15, 11, 30, 0, tzinfo=pacific),
    )

    assert b"DTSTART:20260915T170000Z" in document
    assert b"DTEND:20260915T183000Z" in document


@pytest.mark.golden
def test_uid_is_deterministic_and_overridable():
    first = _build()
    later = _build(generated_at=FIXED_NOW + timedelta(hours=3))

    uid = next(ln for ln in first.split(b"\r\n") if ln.startswith(b"UID:"))
    assert uid in later.split(b"\r\n")

    assert b"UID:explicit@example.invalid" in _build(uid="explicit@example.invalid")


# ---------------------------------------------------------------------------
# The contract the facade adds: the slot must already be resolved (F-003)
# ---------------------------------------------------------------------------


@pytest.mark.golden
@pytest.mark.parametrize("field", ["starts_at", "ends_at"])
def test_an_unresolved_endpoint_is_refused_rather_than_filled_in(field: str):
    """`None` is the shape F-003's fabricated dates arrived in.

    `generate_ics` reads a missing `ends_at` as "one hour", which is correct for
    a port that must not change legacy output but is still a value the source
    data never contained. At this layer there is no such fallback.
    """
    with pytest.raises(UnschedulableEventError, match="unresolved"):
        _build(**{field: None})


@pytest.mark.golden
def test_no_document_is_produced_from_a_recurrence_string():
    """The legacy fabricated a slot from exactly these values."""
    for recurrence in ("Every Tuesday", "Annual", "Ongoing", "Recurring each term/year"):
        with pytest.raises(UnschedulableEventError, match="never infers a time slot"):
            _build(starts_at=recurrence)
        with pytest.raises(UnschedulableEventError, match="never infers a time slot"):
            _build(ends_at=recurrence)


@pytest.mark.golden
@pytest.mark.parametrize("field", ["starts_at", "ends_at", "generated_at"])
def test_a_naive_datetime_is_refused(field: str):
    """A naive value stamped `Z` shifts the event by the local offset."""
    with pytest.raises(UnschedulableEventError, match="timezone-aware"):
        _build(**{field: datetime(2026, 9, 15, 17, 0, 0)})


@pytest.mark.golden
def test_there_is_no_implicit_one_hour_default_to_fall_back_on():
    """Omitting `ends_at` is a TypeError, not a silently defaulted duration."""
    with pytest.raises(TypeError):
        build_invite_ics(  # type: ignore[call-arg]
            title="Careers Panel",
            starts_at=FIXED_START,
            generated_at=FIXED_NOW,
        )


@pytest.mark.golden
def test_a_backwards_slot_and_a_blank_title_are_refused():
    with pytest.raises(ValueError, match="must not precede"):
        _build(ends_at=FIXED_START - timedelta(hours=1))

    with pytest.raises(ValueError, match="non-blank"):
        _build(title="   ")


@pytest.mark.golden
def test_the_facade_reads_no_clock():
    """Identical inputs produce identical bytes; `generated_at` is injected."""
    assert _build() == _build()

    with pytest.raises(TypeError):
        build_invite_ics(  # type: ignore[call-arg]
            title="Careers Panel",
            starts_at=FIXED_START,
            ends_at=FIXED_END,
        )
