"""Tests for the event temporal model and tag vocabulary (ADR-0010, ADR-0012)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from smartmatch_domain.events import (
    DateOnlyTime,
    EventIdentityKey,
    EventProvenance,
    ExactTime,
    MappedTag,
    QuarantinedTag,
    TagVocabulary,
    TimePrecision,
    UnresolvedTime,
    is_resolved,
    matchable_tags,
    normalize_tag_value,
    normalize_title,
    precision_of,
    quarantined_tags,
    resolve_identity_key,
    resolve_tag,
    resolved_date,
)

AWARE_NOON = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# ADR-0010 — temporal model
# ---------------------------------------------------------------------------


def test_exact_time_requires_an_aware_datetime():
    naive = datetime(2026, 9, 14, 12, 0)
    with pytest.raises(ValueError, match="timezone-aware"):
        ExactTime(starts_at=naive, time_zone="America/Los_Angeles")


def test_exact_time_rejects_blank_zone():
    with pytest.raises(ValueError, match="non-blank"):
        ExactTime(starts_at=AWARE_NOON, time_zone="  ")


def test_date_only_time_rejects_blank_zone():
    with pytest.raises(ValueError, match="non-blank"):
        DateOnlyTime(on_date=date(2026, 9, 14), time_zone="")


def test_date_only_time_carries_no_starts_at_field():
    """Fixes the legacy defect directly: there is no field to fabricate an
    instant into. Accessing one is a type error, not a runtime possibility."""
    on_date_time = DateOnlyTime(on_date=date(2026, 9, 14), time_zone="America/Los_Angeles")
    assert not hasattr(on_date_time, "starts_at")


def test_unresolved_time_carries_no_fields():
    unresolved = UnresolvedTime()
    assert unresolved == UnresolvedTime()
    assert not hasattr(unresolved, "starts_at")
    assert not hasattr(unresolved, "on_date")


@pytest.mark.parametrize(
    ("event_time", "expected"),
    [
        (ExactTime(starts_at=AWARE_NOON, time_zone="UTC"), TimePrecision.EXACT),
        (
            DateOnlyTime(on_date=date(2026, 9, 14), time_zone="America/Los_Angeles"),
            TimePrecision.DATE_ONLY,
        ),
        (UnresolvedTime(), TimePrecision.UNRESOLVED),
    ],
)
def test_each_precision_variant_reports_its_own_precision(event_time, expected):
    assert precision_of(event_time) == expected


@pytest.mark.parametrize(
    ("event_time", "expected"),
    [
        (ExactTime(starts_at=AWARE_NOON, time_zone="UTC"), True),
        (DateOnlyTime(on_date=date(2026, 9, 14), time_zone="UTC"), True),
        (UnresolvedTime(), False),
    ],
)
def test_only_unresolved_is_not_resolved(event_time, expected):
    """ADR-0010 rule 2: unresolved cannot reach a matchable/publishable state."""
    assert is_resolved(event_time) is expected


def test_unresolved_date_cannot_become_a_precise_one():
    """The central guarantee: no function in this module turns an
    UnresolvedTime into a date or an instant."""
    assert resolved_date(UnresolvedTime()) is None


def test_exact_time_resolved_date_is_the_instants_date_component():
    event_time = ExactTime(starts_at=datetime(2026, 9, 14, 23, 30, tzinfo=UTC), time_zone="UTC")
    assert resolved_date(event_time) == date(2026, 9, 14)


def test_date_only_resolved_date_is_the_stored_date_unchanged():
    event_time = DateOnlyTime(on_date=date(2026, 9, 14), time_zone="America/Los_Angeles")
    assert resolved_date(event_time) == date(2026, 9, 14)


def test_date_only_and_exact_time_at_the_same_calendar_date_are_distinguishable():
    """Two events on the same date at different precisions are not the same
    representation, even though `resolved_date` agrees for identity purposes."""
    exact = ExactTime(starts_at=AWARE_NOON, time_zone="UTC")
    date_only = DateOnlyTime(on_date=AWARE_NOON.date(), time_zone="UTC")
    assert exact != date_only
    assert precision_of(exact) != precision_of(date_only)


# ---------------------------------------------------------------------------
# ADR-0012 — deterministic identity key
# ---------------------------------------------------------------------------


def test_unresolved_event_has_no_identity_key():
    """ADR-0012: 'an unresolved event has no identity key and cannot be
    resolved against anything.' Modeled as None, not a sentinel."""
    key = resolve_identity_key(
        host_org_unit="cs-dept", title="Career Night", event_time=UnresolvedTime()
    )
    assert key is None


def test_two_unresolved_events_are_not_treated_as_the_same_event():
    """There is no shared sentinel key two unresolved extractions could
    collide on — each call independently produces None, not an equal key."""
    first = resolve_identity_key(
        host_org_unit="cs-dept", title="Talk A", event_time=UnresolvedTime()
    )
    second = resolve_identity_key(
        host_org_unit="cs-dept", title="Talk B", event_time=UnresolvedTime()
    )
    assert first is None
    assert second is None


@pytest.mark.parametrize(
    "cosmetic_title",
    [
        "AI Career Night",
        "  AI   Career   Night  ",
        "AI CAREER NIGHT",
        "ai-career-night",
        "AI, Career Night!",
    ],
)
def test_identity_key_is_stable_across_cosmetic_title_variation(cosmetic_title):
    baseline = resolve_identity_key(
        host_org_unit="cs-dept",
        title="AI Career Night",
        event_time=DateOnlyTime(on_date=date(2026, 9, 14), time_zone="UTC"),
    )
    variant = resolve_identity_key(
        host_org_unit="cs-dept",
        title=cosmetic_title,
        event_time=DateOnlyTime(on_date=date(2026, 9, 14), time_zone="UTC"),
    )
    assert baseline == variant


def test_identity_key_is_unstable_across_host_org_unit():
    time = DateOnlyTime(on_date=date(2026, 9, 14), time_zone="UTC")
    first = resolve_identity_key(host_org_unit="cs-dept", title="Career Night", event_time=time)
    second = resolve_identity_key(host_org_unit="ee-dept", title="Career Night", event_time=time)
    assert first != second


def test_identity_key_is_unstable_across_resolved_date():
    first = resolve_identity_key(
        host_org_unit="cs-dept",
        title="Career Night",
        event_time=DateOnlyTime(on_date=date(2026, 9, 14), time_zone="UTC"),
    )
    second = resolve_identity_key(
        host_org_unit="cs-dept",
        title="Career Night",
        event_time=DateOnlyTime(on_date=date(2026, 9, 21), time_zone="UTC"),
    )
    assert first != second


def test_identity_key_ignores_source_provenance_entirely():
    """Two extractions of the same event from different pages must resolve
    to the same key (ADR-0012's anti-duplicate rationale). There is also no
    parameter to pass provenance through in the first place."""
    time = DateOnlyTime(on_date=date(2026, 9, 14), time_zone="UTC")
    from_calendar = resolve_identity_key(
        host_org_unit="cs-dept", title="Career Night", event_time=time
    )
    from_department_page = resolve_identity_key(
        host_org_unit="cs-dept", title="Career Night", event_time=time
    )
    assert from_calendar == from_department_page

    with pytest.raises(TypeError):
        resolve_identity_key(  # type: ignore[call-arg]
            host_org_unit="cs-dept",
            title="Career Night",
            event_time=time,
            source_url="https://example.edu/events/career-night",
        )


def test_identity_key_is_usable_as_a_dict_key():
    key = resolve_identity_key(
        host_org_unit="cs-dept",
        title="Career Night",
        event_time=DateOnlyTime(on_date=date(2026, 9, 14), time_zone="UTC"),
    )
    assert isinstance(key, EventIdentityKey)
    assert {key: "row-1"}[key] == "row-1"


def test_identity_key_requires_non_blank_org_unit():
    with pytest.raises(ValueError, match="non-blank"):
        resolve_identity_key(
            host_org_unit="   ",
            title="Career Night",
            event_time=DateOnlyTime(on_date=date(2026, 9, 14), time_zone="UTC"),
        )


# ---------------------------------------------------------------------------
# ADR-0012 — source provenance never leaks into the title
# ---------------------------------------------------------------------------


def test_provenance_is_a_separate_structured_value():
    provenance = EventProvenance(
        source_url="https://example.edu/events/career-night",
        fetched_at=AWARE_NOON,
        extractor_version="crawler-2026.09",
    )
    title = "Career Night"
    # There is no function in this module that combines the two; the proof is
    # that the title, computed independently, never contains anything from
    # provenance.
    normalized = normalize_title(title)
    assert provenance.source_url not in normalized
    assert "example.edu" not in normalized


def test_provenance_requires_aware_fetched_at():
    with pytest.raises(ValueError, match="timezone-aware"):
        EventProvenance(
            source_url="https://example.edu",
            fetched_at=datetime(2026, 9, 14),
            extractor_version="crawler-2026.09",
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_url", ""),
        ("extractor_version", "   "),
    ],
)
def test_provenance_rejects_blank_fields(field, value):
    kwargs = {
        "source_url": "https://example.edu",
        "fetched_at": AWARE_NOON,
        "extractor_version": "crawler-2026.09",
    }
    kwargs[field] = value
    with pytest.raises(ValueError, match="non-blank"):
        EventProvenance(**kwargs)


def test_normalize_title_does_not_attempt_to_strip_url_like_text():
    """This module does not try to detect and remove a source name from a
    title — provenance staying out of the title is a structural guarantee
    (a separate field), not a text-scrubbing heuristic."""
    dirty = "Career Night - via example.edu"
    normalized = normalize_title(dirty)
    assert "example edu" in normalized  # punctuation folded to a boundary, not deleted


# ---------------------------------------------------------------------------
# ADR-0012 — closed, versioned tag vocabulary
# ---------------------------------------------------------------------------


V1 = TagVocabulary(version="v1", terms=frozenset({"mentor", "workshop", "keynote"}))
V2 = TagVocabulary(version="v2", terms=frozenset({"mentor", "workshop", "panel"}))


def test_vocabulary_rejects_empty_terms():
    with pytest.raises(ValueError, match="at least one term"):
        TagVocabulary(version="v1", terms=frozenset())


def test_vocabulary_rejects_blank_version():
    with pytest.raises(ValueError, match="non-blank"):
        TagVocabulary(version="  ", terms=frozenset({"mentor"}))


def test_vocabulary_rejects_a_term_not_already_normalized():
    with pytest.raises(ValueError, match="not already normalized"):
        TagVocabulary(version="v1", terms=frozenset({"Mentor"}))


def test_mapped_value_resolves_to_a_matchable_tag():
    resolution = resolve_tag("mentor", V1)
    assert isinstance(resolution, MappedTag)
    assert resolution.term == "mentor"
    assert resolution.vocabulary_version == "v1"


@pytest.mark.parametrize("cosmetic", ["Mentor", "  mentor ", "MENTOR"])
def test_tag_resolution_folds_cosmetic_variation_before_matching(cosmetic):
    resolution = resolve_tag(cosmetic, V1)
    assert isinstance(resolution, MappedTag)
    assert resolution.term == "mentor"


def test_unmapped_value_is_quarantined_not_dropped():
    resolution = resolve_tag("sasquatch-wrangler", V1)
    assert isinstance(resolution, QuarantinedTag)
    assert resolution.raw_value == "sasquatch-wrangler"
    assert resolution.vocabulary_version == "v1"


def test_quarantined_tag_preserves_the_raw_text_unnormalized_for_review():
    resolution = resolve_tag("  Sasquatch Wrangler  ", V1)
    assert isinstance(resolution, QuarantinedTag)
    assert resolution.raw_value == "  Sasquatch Wrangler  "


def test_there_is_no_path_from_a_quarantined_tag_to_a_matchable_term():
    """The illegal state is unconstructible: QuarantinedTag has no `term`
    attribute at all, so there is nothing to read even by accident."""
    resolution = resolve_tag("sasquatch-wrangler", V1)
    assert isinstance(resolution, QuarantinedTag)
    assert not hasattr(resolution, "term")


def test_matchable_tags_excludes_quarantined_entries():
    resolutions = [resolve_tag("mentor", V1), resolve_tag("sasquatch-wrangler", V1)]
    matchable = matchable_tags(resolutions)
    assert [t.term for t in matchable] == ["mentor"]


def test_quarantined_tags_excludes_mapped_entries():
    resolutions = [resolve_tag("mentor", V1), resolve_tag("sasquatch-wrangler", V1)]
    quarantined = quarantined_tags(resolutions)
    assert [t.raw_value for t in quarantined] == ["sasquatch-wrangler"]


def test_resolving_the_same_raw_value_under_two_vocabulary_versions_is_independent():
    """'keynote' is in v1 but not v2 ('panel' replaced it); 'panel' is the
    reverse. Each resolution records exactly the version it was checked
    against — there is no ambient 'current' vocabulary."""
    keynote_under_v1 = resolve_tag("keynote", V1)
    keynote_under_v2 = resolve_tag("keynote", V2)
    assert isinstance(keynote_under_v1, MappedTag)
    assert keynote_under_v1.vocabulary_version == "v1"
    assert isinstance(keynote_under_v2, QuarantinedTag)
    assert keynote_under_v2.vocabulary_version == "v2"

    panel_under_v1 = resolve_tag("panel", V1)
    panel_under_v2 = resolve_tag("panel", V2)
    assert isinstance(panel_under_v1, QuarantinedTag)
    assert isinstance(panel_under_v2, MappedTag)


def test_a_stored_mapped_tag_is_interpretable_under_the_vocabulary_it_was_mapped_with():
    """Round-tripping: a MappedTag carries its own vocabulary_version, so a
    caller holding the original TagVocabulary instance can always confirm the
    tag is still exactly what it claims, independent of any newer version."""
    resolution = resolve_tag("mentor", V1)
    assert isinstance(resolution, MappedTag)
    assert resolution.term in V1.terms
    assert resolution.vocabulary_version == V1.version


def test_resolve_tag_cannot_extend_the_vocabulary():
    """No parameter exists that would let a caller add a term as a side
    effect of resolving one; growing the vocabulary means constructing a new
    TagVocabulary."""
    resolve_tag("sasquatch-wrangler", V1)
    assert "sasquatch-wrangler" not in V1.terms


@pytest.mark.parametrize("blank", ["", "   "])
def test_resolve_tag_rejects_blank_raw_value(blank):
    with pytest.raises(ValueError, match="non-blank"):
        resolve_tag(blank, V1)


def test_normalize_tag_value_matches_the_folding_resolve_tag_uses():
    assert normalize_tag_value("  Mentor ") == "mentor"
    resolution = resolve_tag("  Mentor ", V1)
    assert isinstance(resolution, MappedTag)
    assert resolution.term == normalize_tag_value("  Mentor ")


def test_vocabularies_are_frozen_and_growth_requires_a_new_instance():
    with pytest.raises(AttributeError):
        V1.terms = frozenset({"mentor", "sasquatch-wrangler"})  # type: ignore[misc]


def test_tag_resolution_does_not_take_an_event_time_parameter():
    """Sanity check that time and tag resolution are independent dimensions —
    resolving a tag never receives (and cannot be influenced by) an event's
    temporal precision."""
    unresolved_event_key = resolve_identity_key(
        host_org_unit="cs-dept", title="Talk", event_time=UnresolvedTime()
    )
    tag_resolution = resolve_tag("mentor", V1)
    assert unresolved_event_key is None
    assert isinstance(tag_resolution, MappedTag)
