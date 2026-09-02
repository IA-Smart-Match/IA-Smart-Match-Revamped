"""JSON-LD `schema.org/Event` parsing into ADR-0010 types (Stage 0, fixture-only).

These tests are the specification for `smartmatch_domain.jsonld_parser`. They
are the sibling of `test_ical_parser.py` and hold the same line: every case runs
against a committed synthetic fixture — no network, no live provider, no
recorded third-party content. Stage 0 of the discovery roadmap
(`docs/plans/prep/campus-event-discovery-capability.md` §7) authorizes exactly
this: deterministic parser work against fixtures, with no transport, no
migration, and no route.

Two invariants run through the whole file:

* **ADR-0010** — a source that does not state a time does not acquire one.
  `UnresolvedTime` and `DateOnlyTime` are correct answers, not degraded ones.
* **G3 §7 MP-4** — never emit personal contact data. `schema.org/Event` carries
  `email`, `telephone`, and `contactPoint` far more readily than iCalendar does,
  so the omission is asserted directly rather than assumed.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from smartmatch_domain.events import (
    DateOnlyTime,
    ExactTime,
    TimePrecision,
    UnresolvedTime,
    precision_of,
    resolved_date,
)
from smartmatch_domain.jsonld_parser import JSONLD_PARSER_VERSION, parse_jsonld

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "event_sources"

#: The zone a source declares for itself, supplied by the caller from the source
#: registry. The parser never guesses one — see `TestSourceZoneIsRequired`.
SOURCE_ZONE = "America/Los_Angeles"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _parse(name: str):
    return parse_jsonld(_load(name), source_time_zone=SOURCE_ZONE)


def _all_text(event) -> str:
    """Every string this parsed event would carry downstream, concatenated."""
    parts: list[str] = []
    for field in dataclasses.fields(event):
        value = getattr(event, field.name)
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, tuple):
            parts.extend(str(item) for item in value)
    return "\n".join(parts)


class TestTemporalPrecision:
    """ADR-0010: three states, and no fabrication of the missing ones."""

    def test_full_date_time_yields_exact_time(self) -> None:
        (event,) = _parse("single_event.jsonld")
        assert isinstance(event.event_time, ExactTime)
        assert event.event_time.time_zone == SOURCE_ZONE
        assert event.event_time.starts_at.utcoffset() is not None
        assert resolved_date(event.event_time) == date(2026, 4, 15)

    def test_date_only_start_date_is_not_midnight(self) -> None:
        """A date-only source must not become an instant at 00:00."""
        (event,) = _parse("date_only.jsonld")
        assert isinstance(event.event_time, DateOnlyTime)
        assert event.event_time.on_date == date(2026, 9, 20)
        assert event.event_time.time_zone == SOURCE_ZONE
        # `not hasattr(..., "starts_at")` was guaranteed by the type system —
        # `DateOnlyTime` has no such field, so it could never fail. What matters
        # is that the *precision* stays date-only and that the resolved date is
        # the stated day rather than an instant at 00:00, so assert that.
        assert precision_of(event.event_time) is TimePrecision.DATE_ONLY
        assert resolved_date(event.event_time) == date(2026, 9, 20)

    def test_absent_start_date_yields_unresolved_not_a_guess(self) -> None:
        (event,) = _parse("no_start_date.jsonld")
        assert isinstance(event.event_time, UnresolvedTime)
        assert resolved_date(event.event_time) is None

    def test_unparseable_start_date_yields_unresolved(self) -> None:
        """Prose in `startDate` is not a date. MP-1: `unknown` is a pass."""
        (event,) = _parse("unparseable_start_date.jsonld")
        assert isinstance(event.event_time, UnresolvedTime)

    def test_floating_local_time_is_read_in_the_source_zone(self) -> None:
        (event,) = _parse("floating_local.jsonld")
        assert isinstance(event.event_time, ExactTime)
        assert event.event_time.starts_at == datetime(2026, 4, 15, 16, 0, tzinfo=UTC)
        assert resolved_date(event.event_time) == date(2026, 4, 15)


class TestZoneVersusOffset:
    """An ISO offset is an instant, not a zone. ADR-0010 rule 1."""

    def test_utc_instant_resolves_date_in_the_source_zone(self) -> None:
        """The date-shift trap: 02:00Z on 16 April is 15 April in Los Angeles.

        Keying on the UTC date would put this event on the wrong day and give it
        the wrong ADR-0012 identity. The instant is preserved exactly as given;
        the zone is the source's declared zone, never UTC-by-default.
        """
        (event,) = _parse("utc_date_shift.jsonld")
        assert isinstance(event.event_time, ExactTime)
        assert event.event_time.starts_at == datetime(2026, 4, 16, 2, 0, tzinfo=UTC)
        assert event.event_time.time_zone == SOURCE_ZONE
        assert resolved_date(event.event_time) == date(2026, 4, 15)

    def test_iso_offset_does_not_become_the_time_zone(self) -> None:
        """`+05:00` is a fact about one instant, not a zone the event happens in.

        The offset's own local date is 16 April. The declared source zone still
        governs the ADR-0012 identity date, which is 15 April. Adopting the
        offset as the zone would key this event a day late and would silently
        shift across a DST boundary (ADR-0010 rule 1).
        """
        (event,) = _parse("offset_date_shift.jsonld")
        assert isinstance(event.event_time, ExactTime)
        assert event.event_time.starts_at == datetime(
            2026, 4, 16, 2, 0, tzinfo=timezone(timedelta(hours=5))
        )
        assert event.event_time.time_zone == SOURCE_ZONE
        assert resolved_date(event.event_time) == date(2026, 4, 15)


class TestSourceZoneIsRequired:
    """The parser refuses to invent a zone, because the zone changes the date."""

    def test_blank_source_zone_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            parse_jsonld(_load("date_only.jsonld"), source_time_zone="   ")

    def test_unknown_source_zone_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            parse_jsonld(_load("date_only.jsonld"), source_time_zone="Mars/Olympus")


class TestDocumentShapes:
    """The structural variety that makes JSON-LD harder than iCalendar."""

    def test_single_event_object_at_the_root(self) -> None:
        events = _parse("single_event.jsonld")
        assert len(events) == 1
        assert events[0].title == "Spring Analytics Hackathon"

    def test_top_level_array_skips_non_events(self) -> None:
        """A `WebPage` beside an `Event` is normal, not an error."""
        events = _parse("array_mixed.jsonld")
        assert [e.title for e in events] == ["Transfer Student Mixer"]

    def test_graph_nodes_are_walked(self) -> None:
        events = _parse("graph_nodes.jsonld")
        assert [e.title for e in events] == ["Bronco Career Fair"]

    def test_event_nested_under_a_web_page_main_entity(self) -> None:
        events = _parse("webpage_main_entity.jsonld")
        assert [e.title for e in events] == ["Undergraduate Research Symposium"]

    def test_type_given_as_a_list_is_recognised(self) -> None:
        events = _parse("type_list.jsonld")
        assert [e.title for e in events] == ["Bronco Welcome Back Night"]

    def test_unknown_type_is_skipped_not_guessed(self) -> None:
        """An invented `@type` is not an Event just because it has a startDate."""
        assert _parse("unknown_type.jsonld") == ()

    def test_empty_but_valid_document_returns_no_events(self) -> None:
        """An empty feed must stay distinguishable from a fetch failure."""
        assert _parse("empty_array.jsonld") == ()

    def test_malformed_json_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            _parse("malformed.jsonld")


class TestNestedSubEvents:
    def test_sub_events_are_emitted_parent_first_in_document_order(self) -> None:
        events = _parse("nested_subevents.jsonld")
        assert [e.title for e in events] == [
            "Bronco Innovation Week",
            "Data Storytelling Workshop",
            "Innovation Week Closing Social",
            "Awards Announcement",
        ]

    def test_super_event_is_not_followed(self) -> None:
        """Walking upward would emit a parent series the document only referenced."""
        titles = [e.title for e in _parse("nested_subevents.jsonld")]
        assert "Parent Series That Must Not Be Emitted" not in titles

    def test_deeply_nested_document_is_refused_not_silently_truncated(self) -> None:
        """Recursion is depth-bounded, and hitting the bound is reported.

        This test previously asserted `== ()`, which locked in a silent
        truncation: a 60-deep chain returned 33 events and the caller could not
        tell 33-of-60 from 33-of-33. G3 §7 MP-5 forbids reporting a capped
        response as complete, and `tuple[ParsedSourceEvent, ...]` has nowhere to
        carry a "there was more" flag, so exceeding the cap raises instead.
        """
        depth = 400
        document = '{"@type": "Event", "name": "Deep", "startDate": "2026-09-20"}'
        for _ in range(depth):
            document = '{"@type": "WebPage", "mainEntity": ' + document + "}"
        with pytest.raises(ValueError):
            parse_jsonld(document, source_time_zone=SOURCE_ZONE)


class TestSourceFields:
    """Fields carried through for downstream identity and provenance."""

    def test_core_fields_are_extracted(self) -> None:
        (event,) = _parse("single_event.jsonld")
        assert event.title == "Spring Analytics Hackathon"
        assert event.source_uid == "https://example.edu/events/spring-analytics-hackathon#event"
        assert event.source_url == "https://example.edu/events/spring-analytics-hackathon"
        assert event.description is not None
        assert "build sprint" in event.description

    def test_place_object_contributes_name_and_address(self) -> None:
        (event,) = _parse("single_event.jsonld")
        assert event.location == ("Engineering Building, Room 101, 3801 W Temple Ave, Pomona, CA")

    def test_location_given_as_a_string(self) -> None:
        (event,) = _parse("location_string.jsonld")
        assert event.location == "University Library, Room 4431"

    def test_name_given_as_a_list_takes_the_first_value(self) -> None:
        (event,) = _parse("name_as_list.jsonld")
        assert event.title == "Bronco Wellness Fair"

    def test_absent_optional_fields_are_none_not_empty_string(self) -> None:
        (event,) = _parse("date_only.jsonld")
        assert event.location is None
        assert event.organizer_name is None
        assert event.source_url is None
        assert event.description is None
        assert event.raw_tags == ()

    def test_no_host_org_unit_is_chosen_by_extraction(self) -> None:
        """T-11 control C-4: extraction output must never pick an owning unit.

        Asserting `not hasattr(event, "host_org_unit")` alone was near-vacuous —
        the dataclass has no such field, so the type system already guaranteed
        it and the test could never fail. Pinning the *whole* field set is the
        assertion with teeth: it fails if anyone adds `host_org_unit`, and it
        also fails if anyone adds any other owning-unit-shaped field under a
        different name, which is the failure the control actually cares about.
        """
        (event,) = _parse("single_event.jsonld")
        assert {field.name for field in dataclasses.fields(event)} == {
            "title",
            "event_time",
            "source_uid",
            "source_url",
            "location",
            "organizer_name",
            "description",
            "raw_tags",
            "is_cancelled",
            "has_unexpanded_recurrence",
        }

    def test_parser_version_is_exported(self) -> None:
        assert JSONLD_PARSER_VERSION.startswith("jsonld_parser/")


class TestTagsStayRaw:
    """Tags arrive raw. Vocabulary resolution is S5's job, not the parser's."""

    def test_keyword_list_is_carried_verbatim(self) -> None:
        (event,) = _parse("single_event.jsonld")
        assert event.raw_tags == ("Competitions", "Student Life")

    def test_comma_separated_keywords_and_about_are_collected(self) -> None:
        (event,) = _parse("location_string.jsonld")
        assert event.raw_tags == (
            "Academics",
            "Study Skills",
            "Finals Preparation",
        )


class TestNoPersonalContactData:
    """G3 §7 MP-4: crawler/LLM extractors never emit personal contact data."""

    def test_organizer_name_only(self) -> None:
        (event,) = _parse("single_event.jsonld")
        assert event.organizer_name == "Computer Science Society"

    def test_organizer_given_as_a_string(self) -> None:
        (event,) = _parse("location_string.jsonld")
        assert event.organizer_name == "Bronco Tutoring Center"

    def test_no_email_or_telephone_reaches_any_field(self) -> None:
        text = _all_text(_parse("single_event.jsonld")[0])
        assert "noreply@example.edu" not in text
        assert "advisor@example.edu" not in text
        assert "909-555-0199" not in text
        assert "909-555-0177" not in text
        assert "909-555-0142" not in text


class TestStatusAndRecurrence:
    def test_cancelled_status_is_surfaced(self) -> None:
        """G3 §5: a same-source cancellation must unpublish immediately."""
        (event,) = _parse("cancelled.jsonld")
        assert event.is_cancelled is True

    def test_default_event_is_not_cancelled(self) -> None:
        (event,) = _parse("single_event.jsonld")
        assert event.is_cancelled is False

    def test_recurrence_is_flagged_and_never_expanded(self) -> None:
        """One node with an `eventSchedule` yields one event, not a whole series.

        Expanding the schedule here would invent occurrences the parser cannot
        verify. The flag tells a downstream consumer the series is incomplete,
        rather than letting it read one occurrence as the whole story.
        """
        events = _parse("recurring.jsonld")
        assert len(events) == 1
        assert events[0].has_unexpanded_recurrence is True
        assert isinstance(events[0].event_time, ExactTime)

    def test_non_recurring_event_is_not_flagged(self) -> None:
        (event,) = _parse("single_event.jsonld")
        assert event.has_unexpanded_recurrence is False


class TestParserPurity:
    def test_parsed_event_is_immutable(self) -> None:
        (event,) = _parse("date_only.jsonld")
        with pytest.raises(dataclasses.FrozenInstanceError):
            event.title = "mutated"  # type: ignore[misc]

    def test_parser_module_imports_no_ambient_state(self) -> None:
        """The domain import contract forbids `os`, `pathlib`, and `socket`."""
        import smartmatch_domain.jsonld_parser as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        for forbidden in ("import os", "import pathlib", "import socket"):
            assert forbidden not in source


# ---------------------------------------------------------------------------
# Regression suites for the defects found in the 28 August review.
# ---------------------------------------------------------------------------


class TestResourceLimitsRaiseValueError:
    """D1/D7 — every resource-limit failure is the documented `ValueError`.

    A `RecursionError` escaping this module is an unhandled worker crash from
    attacker-supplied text, and it breaks the documented `Raises:` contract.
    A truncated walk is worse than a crash in one respect: it is silent, and
    G3 §7 MP-5 forbids reporting a capped read as complete.
    """

    def test_bracket_bomb_raises_value_error_not_recursion_error(self) -> None:
        document = "[" * 60000 + "]" * 60000
        with pytest.raises(ValueError):
            parse_jsonld(document, source_time_zone=SOURCE_ZONE)

    def test_deeply_nested_property_value_raises_value_error(self) -> None:
        """A `startDate` buried under ~1200 arrays must not blow the stack."""
        depth = 1200
        buried = "[" * depth + '"2026-09-20"' + "]" * depth
        document = '{"@type": "Event", "name": "Deep Start", "startDate": ' + buried + "}"
        with pytest.raises(ValueError):
            parse_jsonld(document, source_time_zone=SOURCE_ZONE)

    def test_document_within_the_depth_cap_still_parses(self) -> None:
        document = '{"@type": "Event", "name": "Shallow", "startDate": "2026-09-20"}'
        for _ in range(5):
            document = '{"@type": "WebPage", "mainEntity": ' + document + "}"
        (event,) = parse_jsonld(document, source_time_zone=SOURCE_ZONE)
        assert event.title == "Shallow"


class TestCancellationSerializations:
    """D2 — a cancelled event must never read as scheduled (G3 §5)."""

    def test_event_status_as_a_node_reference_is_cancelled(self) -> None:
        (event,) = _parse("cancelled_node_reference.jsonld")
        assert event.is_cancelled is True

    def test_event_status_from_a_foreign_namespace_is_not_trusted(self) -> None:
        (event,) = _parse("spoofed_cancellation_namespace.jsonld")
        assert event.is_cancelled is False


class TestContactDataIsRedactedFromFreeText:
    """D3 — MP-4 enforced on content, not merely on property names."""

    def test_email_and_phone_are_redacted_from_every_emitted_string(self) -> None:
        (event,) = _parse("contact_in_free_text.jsonld")
        text = _all_text(event)
        leaked_values = (
            "advisor@example.edu",
            "909-555-0177",
            "evil@x.edu",
            "909-555-0142",
            "x@y.edu",
            "rios@example.edu",
        )
        for leaked in leaked_values:
            assert leaked not in text
        assert "[contact removed]" in text

    def test_redaction_is_visible_rather_than_a_silent_deletion(self) -> None:
        (event,) = _parse("contact_in_free_text.jsonld")
        assert event.description == "Questions? email [contact removed] or call [contact removed]."

    def test_surrounding_prose_survives_redaction(self) -> None:
        (event,) = _parse("contact_in_free_text.jsonld")
        assert event.organizer_name == "Dr. Rios ([contact removed])"
        assert event.location is not None
        assert event.location.startswith("Bldg 9 - call [contact removed]")
        assert "Pomona" in event.location

    def test_organizer_that_is_only_contact_data_is_none(self) -> None:
        """A redaction is not a name."""
        (event,) = _parse("contact_only_fields.jsonld")
        assert event.organizer_name is None

    def test_mailto_source_url_is_rejected(self) -> None:
        (event,) = _parse("contact_only_fields.jsonld")
        assert event.source_url is None

    def test_title_and_tags_carry_no_contact_data(self) -> None:
        (event,) = _parse("contact_only_fields.jsonld")
        assert event.title == "Alice [contact removed]"
        assert event.raw_tags == ("Advising",)
        assert "alice@example.edu" not in _all_text(event)

    def test_http_source_url_is_preserved(self) -> None:
        (event,) = _parse("contact_in_free_text.jsonld")
        assert event.source_url == "https://example.edu/events/advising-drop-in"


class TestUnstatedPrecisionIsNotAcquired:
    """D4 — `UnresolvedTime` is a correct answer, never a degraded one."""

    def test_hour_only_timestamp_is_unresolved(self) -> None:
        (event,) = _parse("partial_timestamp.jsonld")
        assert isinstance(event.event_time, UnresolvedTime)

    def test_iso_week_designator_is_unresolved(self) -> None:
        """A week is not a day; collapsing it picks a Monday nobody stated."""
        (event,) = _parse("iso_week_date.jsonld")
        assert isinstance(event.event_time, UnresolvedTime)

    def test_iso_ordinal_designator_is_unresolved(self) -> None:
        (event,) = _parse("iso_ordinal_date.jsonld")
        assert isinstance(event.event_time, UnresolvedTime)

    def test_trailing_data_is_unresolved(self) -> None:
        (event,) = _parse("trailing_data_start_date.jsonld")
        assert isinstance(event.event_time, UnresolvedTime)

    def test_two_stated_start_dates_are_a_contradiction(self) -> None:
        (event,) = _parse("start_date_list.jsonld")
        assert isinstance(event.event_time, UnresolvedTime)

    def test_one_value_repeated_in_a_list_is_still_that_value(self) -> None:
        (event,) = _parse("start_date_list_single.jsonld")
        assert isinstance(event.event_time, DateOnlyTime)
        assert event.event_time.on_date == date(2026, 9, 20)

    def test_floating_time_in_a_dst_gap_is_unresolved(self) -> None:
        """02:30 on 8 March 2026 does not exist in America/Los_Angeles."""
        (event,) = _parse("dst_gap.jsonld")
        assert isinstance(event.event_time, UnresolvedTime)

    def test_floating_time_in_an_ambiguous_fold_is_unresolved(self) -> None:
        """01:30 on 1 November 2026 happens twice; the source did not say which."""
        (event,) = _parse("dst_ambiguous.jsonld")
        assert isinstance(event.event_time, UnresolvedTime)


class TestMalformedShapesAreNotScavenged:
    """D5 — a wrong-schema document must not yield a plausible-looking event."""

    def test_a_node_whose_only_name_is_nested_yields_no_event(self) -> None:
        """The refusal is itself the evidence that nothing was mined.

        This node states a name and a date only inside nested arrays. Since
        neither is scavenged (D5), the node states no usable name at all and is
        rejected (D9). Had the title been mined, an event would exist instead —
        so `ValueError` is a stronger assertion than inspecting the title would
        be.
        """
        with pytest.raises(ValueError):
            _parse("scavenged_nested_arrays.jsonld")

    def test_a_nested_start_date_is_not_mined(self) -> None:
        """Date coverage, isolated from the nameless-node rule above."""
        (event,) = _parse("scavenged_nested_date.jsonld")
        assert event.title == "Bronco Robotics Showcase"
        assert isinstance(event.event_time, UnresolvedTime)

    def test_wrong_typed_schedule_does_not_flag_recurrence(self) -> None:
        (event,) = _parse("garbage_event_schedule.jsonld")
        assert event.has_unexpanded_recurrence is False


class TestNamespaceIsNotSpoofable:
    """D6 — the closed `@type` set is closed over the namespace too."""

    def test_foreign_namespace_event_types_are_skipped(self) -> None:
        assert _parse("spoofed_namespace.jsonld") == ()


class TestValueObjects:
    """D8 — `{"@value": ...}` is ordinary JSON-LD, not an absent value."""

    def test_value_objects_are_read_for_type_name_and_date(self) -> None:
        (event,) = _parse("value_objects.jsonld")
        assert event.title == "Real Title"
        assert event.description == "A described event."
        assert isinstance(event.event_time, ExactTime)


class TestBlankTitleDiscipline:
    """D9 — a nameless node is a known-unknown, not an empty string."""

    def test_event_node_without_a_name_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            _parse("no_name.jsonld")
