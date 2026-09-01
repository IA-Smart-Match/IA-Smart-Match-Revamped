"""iCalendar parsing into ADR-0010 temporal types (Stage 0, fixture-only).

These tests are the specification for `smartmatch_domain.ical_parser`. Every
case runs against a committed synthetic fixture — no network, no live provider,
no recorded third-party content. Stage 0 of the discovery roadmap
(`docs/plans/prep/campus-event-discovery-capability.md` §7) authorizes exactly
this: deterministic parser work against fixtures, with no transport, no
migration, and no route.

The invariant under test throughout is ADR-0010's: a source that does not state
a time does not acquire one. `UnresolvedTime` and `DateOnlyTime` are correct
answers, not degraded ones.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from smartmatch_domain.events import (
    DateOnlyTime,
    ExactTime,
    UnresolvedTime,
    resolved_date,
)
from smartmatch_domain.ical_parser import parse_ical

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "event_sources"

#: The zone a source declares for itself, supplied by the caller from the source
#: registry. The parser never guesses one — see `TestSourceZoneIsRequired`.
SOURCE_ZONE = "America/Los_Angeles"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _parse(name: str):
    return parse_ical(_load(name), source_time_zone=SOURCE_ZONE)


class TestTemporalPrecision:
    """ADR-0010: three states, and no fabrication of the missing ones."""

    def test_dtstart_with_tzid_yields_exact_time(self) -> None:
        (event,) = _parse("exact_with_tzid.ics")
        assert isinstance(event.event_time, ExactTime)
        assert event.event_time.time_zone == "America/Los_Angeles"
        assert event.event_time.starts_at.utcoffset() is not None
        assert resolved_date(event.event_time) == date(2026, 4, 15)

    def test_value_date_yields_date_only_not_midnight(self) -> None:
        """A date-only source must not become an instant at 00:00."""
        (event,) = _parse("date_only.ics")
        assert isinstance(event.event_time, DateOnlyTime)
        assert event.event_time.on_date == date(2026, 9, 20)
        assert not hasattr(event.event_time, "starts_at")

    def test_absent_dtstart_yields_unresolved_not_a_guess(self) -> None:
        (event,) = _parse("no_dtstart.ics")
        assert isinstance(event.event_time, UnresolvedTime)
        assert resolved_date(event.event_time) is None

    def test_utc_instant_resolves_date_in_the_source_zone(self) -> None:
        """The date-shift trap: 02:00Z on 16 April is 15 April in Los Angeles.

        Keying on the UTC date would put this event on the wrong day and give it
        the wrong ADR-0012 identity. The instant is preserved exactly as given;
        the zone is the source's declared zone, never UTC-by-default.
        """
        (event,) = _parse("utc_no_tzid.ics")
        assert isinstance(event.event_time, ExactTime)
        assert event.event_time.starts_at == datetime(2026, 4, 16, 2, 0, tzinfo=UTC)
        assert event.event_time.time_zone == SOURCE_ZONE
        assert resolved_date(event.event_time) == date(2026, 4, 15)


class TestSourceZoneIsRequired:
    """The parser refuses to invent a zone, because the zone changes the date."""

    def test_blank_source_zone_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            parse_ical(_load("date_only.ics"), source_time_zone="   ")

    def test_unknown_source_zone_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            parse_ical(_load("date_only.ics"), source_time_zone="Mars/Olympus")


class TestTextDecoding:
    """RFC 5545 §3.1 unfolding and §3.3.11 unescaping."""

    def test_folded_line_is_unfolded(self) -> None:
        (event,) = _parse("folded_line.ics")
        assert event.title == (
            "A deliberately long event title that exceeds seventy-five octets "
            "and therefore continues on a folded line per RFC 5545"
        )

    def test_escaped_text_is_unescaped(self) -> None:
        (event,) = _parse("folded_and_escaped.ics")
        assert event.title == "Career Panel: Analytics, Data; and You"
        assert event.location == "Bronco Student Center, Ursa Major"
        assert event.description is not None
        assert "First line\nSecond line" in event.description
        assert "backslash \\" in event.description


class TestSourceFields:
    """Fields carried through for downstream identity and provenance."""

    def test_core_fields_are_extracted(self) -> None:
        (event,) = _parse("exact_with_tzid.ics")
        assert event.title == "Spring Analytics Hackathon"
        assert event.location == "Engineering Building, Room 101"
        assert event.organizer_name == "Computer Science Society"
        assert event.source_uid == "synthetic-0001@example.edu"
        assert event.source_url == "https://example.edu/events/spring-analytics-hackathon"

    def test_categories_are_raw_and_unresolved(self) -> None:
        """Tags arrive raw. Vocabulary resolution is S5's job, not the parser's."""
        (event,) = _parse("exact_with_tzid.ics")
        assert event.raw_tags == ("Competitions", "Student Life")

    def test_absent_optional_fields_are_none_not_empty_string(self) -> None:
        (event,) = _parse("date_only.ics")
        assert event.location is None
        assert event.organizer_name is None
        assert event.source_url is None


class TestStatusAndRecurrence:
    def test_cancelled_status_is_surfaced(self) -> None:
        """G3 §5: a same-source cancellation must unpublish immediately."""
        (event,) = _parse("cancelled.ics")
        assert event.is_cancelled is True

    def test_default_event_is_not_cancelled(self) -> None:
        (event,) = _parse("exact_with_tzid.ics")
        assert event.is_cancelled is False

    def test_recurrence_is_flagged_and_never_expanded(self) -> None:
        """One VEVENT with RRULE yields one parsed event, not COUNT of them.

        Expanding recurrence here would invent occurrences the parser cannot
        verify. The flag tells a downstream consumer the series is incomplete,
        rather than letting it read one occurrence as the whole story.
        """
        events = _parse("recurring.ics")
        assert len(events) == 1
        assert events[0].has_unexpanded_recurrence is True
        assert isinstance(events[0].event_time, ExactTime)

    def test_non_recurring_event_is_not_flagged(self) -> None:
        (event,) = _parse("exact_with_tzid.ics")
        assert event.has_unexpanded_recurrence is False


class TestParserPurity:
    def test_parsed_event_is_immutable(self) -> None:
        (event,) = _parse("date_only.ics")
        with pytest.raises(dataclasses.FrozenInstanceError):
            event.title = "mutated"  # type: ignore[misc]

    def test_empty_calendar_yields_no_events_not_an_error(self) -> None:
        assert (
            parse_ical(
                "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n",
                source_time_zone=SOURCE_ZONE,
            )
            == ()
        )


class TestContactDataRedaction:
    """MP-4, as far as it is honestly enforceable at this layer.

    Structural contact properties (`ORGANIZER`'s `mailto:` value, `ATTENDEE`)
    are never read. On top of that, email addresses and telephone numbers are
    redacted from every emitted string, because free-prose fields carry them
    routinely and `CN` is frequently an email address rather than a name.
    Personal *names* in prose are explicitly out of scope — see the parser's
    module docstring.
    """

    def test_organizer_cn_that_is_an_email_is_not_emitted_as_a_name(self) -> None:
        """The `CN` control did not hold: `CN` is often the address itself."""
        (event,) = _parse("organizer_email_as_cn.ics")
        assert event.organizer_name is None

    def test_organizer_cn_that_is_a_phone_number_is_not_emitted_as_a_name(self) -> None:
        (event,) = _parse("organizer_phone_as_cn.ics")
        assert event.organizer_name is None

    def test_emails_and_phones_are_redacted_from_free_text(self) -> None:
        (event,) = _parse("organizer_email_as_cn.ics")
        for text in (event.title, event.location, event.description):
            assert text is not None
            assert "@example.edu" not in text
            assert "909-555-0100" not in text
        assert event.description is not None
        assert "[redacted]" in event.description

    def test_redaction_is_visible_rather_than_silent_deletion(self) -> None:
        """A reader must be able to tell something was removed."""
        (event,) = _parse("organizer_email_as_cn.ics")
        assert event.description is not None
        assert event.description.startswith("Call Alice at [redacted]")

    def test_raw_tags_and_source_url_are_redacted_too(self) -> None:
        (event,) = _parse("organizer_email_as_cn.ics")
        assert all("555-0142" not in tag for tag in event.raw_tags)
        assert event.source_url is not None
        assert "alice@example.edu" not in event.source_url

    def test_a_plain_display_name_survives_untouched(self) -> None:
        """Redaction is structural, not a blanket scrub of organizer names."""
        (event,) = _parse("exact_with_tzid.ics")
        assert event.organizer_name == "Computer Science Society"


class TestNoFabricatedInstants:
    """A stated-but-unresolvable time is `UnresolvedTime`, never a substitute."""

    def test_unknown_tzid_is_unresolved_not_a_fallback_zone(self) -> None:
        """The source named a zone. Substituting a different one invents data."""
        (event,) = _parse("unknown_tzid.ics")
        assert isinstance(event.event_time, UnresolvedTime)

    def test_local_time_in_a_dst_gap_is_unresolved(self) -> None:
        """02:30 on 2026-03-08 does not exist in Los Angeles."""
        (event,) = _parse("dst_gap.ics")
        assert isinstance(event.event_time, UnresolvedTime)

    def test_ambiguous_local_time_at_the_dst_fold_is_unresolved(self) -> None:
        """01:30 on 2026-11-01 happens twice; picking one is a guess."""
        (event,) = _parse("dst_fold.ics")
        assert isinstance(event.event_time, UnresolvedTime)


class TestGrammarIsFullyMatched:
    """No prefix slicing: trailing data is a parse failure, not a suffix to drop."""

    def test_numeric_utc_offset_is_honoured_and_shifts_the_identity_date(self) -> None:
        """`+0900` is a stated instant. Discarding it changes the ADR-0012 key."""
        (event,) = _parse("offset_dtstart.ics")
        assert isinstance(event.event_time, ExactTime)
        assert event.event_time.starts_at == datetime(2026, 4, 15, 0, 0, tzinfo=UTC)
        assert event.event_time.time_zone == SOURCE_ZONE
        assert resolved_date(event.event_time) == date(2026, 4, 14)

    def test_trailing_garbage_after_a_date_is_rejected(self) -> None:
        (event,) = _parse("date_only_trailing_garbage.ics")
        assert isinstance(event.event_time, UnresolvedTime)

    def test_value_date_carrying_a_time_is_unresolved_not_truncated(self) -> None:
        """Contradictory input. Silently dropping the time invents precision."""
        (event,) = _parse("date_value_with_time.ics")
        assert isinstance(event.event_time, UnresolvedTime)


class TestNestedComponentsDoNotLeak:
    def test_valarm_properties_do_not_overwrite_the_events(self) -> None:
        """A `VALARM` `DESCRIPTION` is alarm text, and an MP-4 leak path."""
        (event,) = _parse("alarm_in_event.ics")
        assert event.description == (
            "Employers from the region meet students in the Bronco Student Center."
        )
        assert event.title == "Industry Night"
        assert event.raw_tags == ("Career",)


class TestMalformedInputIsDistinguishable:
    """A truncated feed must not read as 'all the events disappeared'."""

    def test_unterminated_vevent_raises(self) -> None:
        with pytest.raises(ValueError):
            _parse("truncated.ics")

    def test_stray_end_vevent_raises(self) -> None:
        with pytest.raises(ValueError):
            _parse("stray_end_vevent.ics")

    def test_nested_vevent_raises(self) -> None:
        with pytest.raises(ValueError):
            _parse("nested_vevent.ics")
