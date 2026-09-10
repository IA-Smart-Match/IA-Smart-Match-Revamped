"""Unit coverage for the synthetic pilot dataset's deterministic plan.

These tests are about the *shape* of the demo dataset, not about SQL. They
assert the two properties the generator's value rests on — that a seed
reproduces a plan exactly, and that a deliberate fraction of the plan carries
no evidence at all so ADR-0011's ``unknown`` states stay visible.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from smartmatch_api.zip_proximity import resolve_distance_from_campus
from smartmatch_domain import student_speaker_feedback as feedback
from smartmatch_domain.cba_role_categories import role_category_for_code
from smartmatch_domain.metrics import OpportunityCategoryShape, shape_opportunity_category
from smartmatch_domain.naics_sectors import sector_for_code
from smartmatch_domain.zcta_centroids import CA_ZCTA_CENTROIDS

from tools import pilot_dataset_plan as plan


def test_the_same_seed_reproduces_the_same_plan():
    """A demo that differs between runs cannot be debugged or discussed."""
    assert plan.build_professionals(120, seed=7) == plan.build_professionals(120, seed=7)
    assert plan.build_events(40, seed=7) == plan.build_events(40, seed=7)
    assert plan.build_students(80, seed=7) == plan.build_students(80, seed=7)


def test_a_different_seed_produces_a_different_plan():
    """The seed is real input, not decoration."""
    assert plan.build_professionals(120, seed=7) != plan.build_professionals(120, seed=8)


def test_each_stream_is_independent_of_the_others_size():
    """Asking for more events must not change which professionals were planned.

    One shared generator would make every downstream draw shift when an
    upstream count changed, so two runs of the same seed with different
    ``--events`` would disagree about data that has nothing to do with events.
    """
    baseline = plan.build_professionals(50, seed=11)
    plan.build_events(999, seed=11)
    assert plan.build_professionals(50, seed=11) == baseline


def test_professionals_have_distinct_names():
    """Two identical names would fold to one derived subject id, not two accounts."""
    planned = plan.build_professionals(250)
    assert len({person.name for person in planned}) == 250


def test_professional_names_pair_a_historical_given_name_with_an_invented_surname():
    """Nothing generated may read as a real person's record (G2/D8 are ungated)."""
    for person in plan.build_professionals(60):
        given, surname = person.name.split(" ", 1)
        assert given in plan._GIVEN_NAMES
        assert surname in plan._SURNAMES


def test_some_professionals_carry_no_topic_evidence_at_all():
    """``None`` is not ``()``: no expertise record is not an empty one.

    A dataset in which every professional had topics would hide the unknown
    branch of ``topic_relevance`` completely, which is the behaviour ADR-0011
    exists to guarantee.
    """
    planned = plan.build_professionals(250)
    without = [person for person in planned if person.topics is None]
    assert 15 <= len(without) <= 60
    assert all(person.topics != () for person in planned)


def test_some_professionals_carry_no_location_evidence_at_all():
    planned = plan.build_professionals(250)
    without = [person for person in planned if person.location is None]
    assert 10 <= len(without) <= 55


def test_professionals_are_spread_across_several_metro_regions():
    """A pool at one point scores identically on travel and decides nothing."""
    planned = plan.build_professionals(250)
    assert len({person.region for person in planned}) >= 8


def test_topics_are_weighted_rather_than_uniform():
    """A uniform draw would make every candidate score alike, which is noise."""
    counts = {term: 0 for term in plan._TOPICS}
    for person in plan.build_professionals(250):
        for term in person.topics or ():
            counts[term] += 1
    ordered = sorted(counts.values(), reverse=True)
    assert ordered[0] > ordered[-1] * 2


def test_events_span_roughly_six_months_ending_at_the_anchor():
    dates = [event.on_date for event in plan.build_events(60) if event.on_date is not None]
    assert max(dates) == plan.CALENDAR_ANCHOR
    assert (max(dates) - min(dates)).days >= 150


def test_the_calendar_anchor_is_a_fixed_literal_not_today():
    """A drifting anchor would make the event writer non-idempotent overnight."""
    assert date(2026, 9, 28) == plan.CALENDAR_ANCHOR


def test_some_events_have_no_resolvable_date():
    """ADR-0010 ``unresolved``: withheld from the calendar, never shown at midnight."""
    unresolved = [event for event in plan.build_events(60) if not event.resolved]
    assert unresolved
    assert all(event.exact_hour is None for event in unresolved)


def test_some_resolved_events_are_date_only():
    """A day with no clock time is real information that is not an instant."""
    planned = plan.build_events(60)
    assert [event for event in planned if event.resolved and event.exact_hour is None]


def test_some_events_carry_a_tag_outside_the_ratified_vocabulary():
    """Without these, ``/tag-quarantine`` is empty and proves nothing."""
    quarantined = [event for event in plan.build_events(60) if event.off_vocabulary_tags]
    assert quarantined
    assert all(not event.publishable for event in quarantined)


def test_an_event_publishes_only_when_resolved_and_unquarantined():
    """Both halves of ``ck_event_publishable``, restated without a database."""
    for event in plan.build_events(60):
        assert event.publishable == (event.resolved and not event.off_vocabulary_tags)


def test_the_planned_categories_agree_with_the_ratified_counting_rule():
    """The single most load-bearing assertion in this file.

    ``opportunities_rows_v1`` counts accepted review rows whose category is
    in-list per ``shape_opportunity_category``, and
    ``pipeline_provisioning._provision_event`` opens journeys only for those
    same rows. Plausible-sounding categories — ``"Technology"``,
    ``"Innovation"``, ``"Networking"``, the ones
    ``docs/pilot-data/fixtures/events_clean.json`` actually uses — are every one
    of them *out-of-list* under the closed P8 decision. A dataset built from
    those produces a measured ``opportunities`` count of zero and opens no
    journey on accept, which is indistinguishable from a broken metric. This
    test is what stops that from happening again.
    """
    for category in plan.IN_LIST_CATEGORIES:
        assert shape_opportunity_category(category) is OpportunityCategoryShape.IN_LIST
    for category in plan.OUT_OF_LIST_CATEGORIES:
        assert shape_opportunity_category(category) is OpportunityCategoryShape.OUT_OF_LIST


def test_every_planned_event_category_is_classifiable_either_way():
    """No planned category may land in ``ABSENT`` — a blank is not a label."""
    for event in plan.build_events(60):
        assert shape_opportunity_category(event.category) is not OpportunityCategoryShape.ABSENT


def test_most_planned_events_are_in_list():
    """The demo's headline number needs a majority of countable rows behind it."""
    planned = plan.build_events(60)
    in_list = [
        event
        for event in planned
        if shape_opportunity_category(event.category) is OpportunityCategoryShape.IN_LIST
    ]
    assert len(in_list) > len(planned) // 2


def test_some_events_are_filed_under_an_out_of_list_category():
    """An accepted out-of-list row must not count toward ``opportunities``."""
    planned = plan.build_events(60)
    out_of_list = [event for event in planned if event.category in plan.OUT_OF_LIST_CATEGORIES]
    assert out_of_list
    assert len(out_of_list) < len(planned) // 2


def test_event_titles_are_distinct():
    """ADR-0012 keys on the normalized title; a repeat would upsert onto itself."""
    assert len({event.title for event in plan.build_events(60)}) == 60


def test_attendance_clusters_rather_than_spreading():
    """Real attendance thins out; a flat draw makes every balance look alike."""
    counts = [student.attendances for student in plan.build_students(120)]
    assert counts.count(0) > sum(1 for value in counts if value >= 5)
    assert max(counts) >= 5


def test_some_students_attended_nothing_at_all():
    """A measured zero balance, which is a fact and not the absence of one."""
    assert any(student.attendances == 0 for student in plan.build_students(120))


def test_some_attending_students_are_left_uncredited():
    """The one shape ``_fold_balance_for`` answers with an *unknown* balance."""
    planned = plan.build_students(120)
    uncredited = [student for student in planned if student.attendances and not student.credited]
    assert uncredited
    assert len(uncredited) < len(planned) // 4


def test_a_student_who_attended_nothing_is_never_reported_as_uncredited():
    """Nothing to credit is not the same as a credit withheld."""
    assert all(s.credited for s in plan.build_students(120) if s.attendances == 0)


def test_student_suffixes_are_distinct():
    assert len({student.external_suffix for student in plan.build_students(120)}) == 120


def test_plan_summary_counts_what_was_deliberately_left_unmeasured():
    summary = plan.plan_summary(
        plan.build_professionals(250), plan.build_events(60), plan.build_students(120)
    )

    assert summary.professionals == 250
    assert summary.events == 60
    assert summary.students == 120
    assert summary.professionals_without_topics > 0
    assert summary.professionals_without_location > 0
    assert summary.events_unresolved > 0
    assert summary.events_quarantined > 0
    assert summary.events_out_of_list_category > 0
    assert summary.students_without_attendance > 0
    assert summary.students_uncredited > 0
    assert summary.events_publishable < summary.events


@pytest.mark.parametrize("count", [0, 1, 2])
def test_small_counts_do_not_raise(count: int):
    """A degenerate size must degrade, not divide by zero."""
    plan.build_professionals(count)
    plan.build_events(count)
    plan.build_students(count)


def test_a_negative_count_is_refused():
    with pytest.raises(ValueError):
        plan.build_professionals(-1)
    with pytest.raises(ValueError):
        plan.build_events(-1)
    with pytest.raises(ValueError):
        plan.build_students(-1)


def test_more_professionals_than_distinct_names_is_refused_rather_than_duplicated():
    """Silently reusing a name would silently merge two identities into one."""
    with pytest.raises(ValueError, match="distinct names"):
        plan.build_professionals(len(plan._GIVEN_NAMES) * len(plan._SURNAMES) + 1)


def test_initials_come_from_the_generated_name():
    person = plan.build_professionals(1)[0]
    given, surname = person.name.split(" ", 1)
    assert person.initials == (given[0] + surname[0]).upper()


# ---------------------------------------------------------------------------
# Student speaker feedback — the plan whose arithmetic the aggregates depend on
# ---------------------------------------------------------------------------


def test_the_same_seed_reproduces_the_same_feedback_plan():
    """Who said what about whom must not wobble between two runs of one seed."""
    assert plan.build_speaker_feedback(seed=7) == plan.build_speaker_feedback(seed=7)


def test_a_different_seed_moves_the_ratings_and_the_silences():
    assert plan.build_speaker_feedback(seed=7) != plan.build_speaker_feedback(seed=8)


def test_every_planned_rating_is_on_the_approved_scale():
    """A rating off 1-5 is a 422 at the route and a CHECK violation beneath it."""
    for entry in plan.build_speaker_feedback(seed=7):
        assert entry.rating is None or feedback.MIN_RATING <= entry.rating <= feedback.MAX_RATING


def test_a_withheld_rating_is_an_absent_row_and_never_a_zero():
    """ADR-0011 rule 1, at the one surface where a zero is most tempting.

    A student who did not rate a speaker has said nothing, and nothing is not
    ``0``. The type makes that structural: ``rating`` is ``None`` and there is
    no other field a zero could be written into.
    """
    withheld = [e for e in plan.build_speaker_feedback(seed=7) if e.rating is None]
    assert withheld, "a plan with no silences cannot demonstrate a suppressed aggregate"
    assert all(entry.rating is None for entry in withheld)
    assert 0 not in {entry.rating for entry in plan.build_speaker_feedback(seed=7)}


def test_a_deliberate_fraction_of_the_opportunities_is_left_unmeasured():
    """The realized share tracks FEEDBACK_WITHHELD_SHARE within one rounding step."""
    summary = plan.feedback_plan_summary(plan.build_speaker_feedback(seed=7))
    assert summary.withheld > 0
    assert abs(summary.withheld_share - plan.FEEDBACK_WITHHELD_SHARE) < 0.1


def test_the_planned_shape_publishes_the_unit_aggregate():
    """The residual rule is satisfied, and not by accident.

    ``aggregate_unit_feedback`` publishes only when the pool clears the
    threshold AND the residual — pool minus every published per-speaker count —
    is zero or itself above it. A shape that missed this would suppress the unit
    number and the demo would show nothing where it meant to show something.
    """
    summary = plan.feedback_plan_summary(plan.build_speaker_feedback(seed=7))
    assert summary.unit_publishes
    assert (
        summary.unit_residual == 0 or summary.unit_residual >= feedback.MIN_RESPONSES_FOR_AGGREGATE
    )


def test_the_planned_shape_also_suppresses_at_least_one_speaker():
    """Both states must be reachable, or the demo only ever shows one of them."""
    summary = plan.feedback_plan_summary(plan.build_speaker_feedback(seed=7))
    assert summary.speakers_published >= 1
    assert summary.speakers_suppressed >= 1


def test_the_plans_verdict_matches_the_shipped_aggregate():
    """The residual rule is restated in the plan; this is what stops it drifting.

    ``feedback_plan_summary`` may not import the shipped aggregate without
    making a pure plan depend on it, so the rule is written twice. Here the two
    are run against the same data and required to agree — per speaker and for
    the unit — so a change to either one that the other did not follow fails.
    """
    planned = plan.build_speaker_feedback(seed=7)
    summary = plan.feedback_plan_summary(planned)

    by_speaker: dict[int, list[int]] = {}
    for entry in planned:
        if entry.rating is not None:
            by_speaker.setdefault(entry.speaker_rank, []).append(entry.rating)

    per_speaker = {
        rank: feedback.aggregate_speaker_feedback(ratings) for rank, ratings in by_speaker.items()
    }
    assert (
        sum(1 for agg in per_speaker.values() if not agg.suppressed) == summary.speakers_published
    )
    assert sum(1 for agg in per_speaker.values() if agg.suppressed) == summary.speakers_suppressed

    keyed = {uuid.uuid5(uuid.NAMESPACE_OID, str(rank)): r for rank, r in by_speaker.items()}
    unit = feedback.aggregate_unit_feedback(keyed)
    assert unit.suppressed is not summary.unit_publishes


def test_the_cohort_is_large_enough_for_the_planned_shape():
    """The widest speaker's pool must fit in the cohort that holds the tokens."""
    widest = max(plan._feedback_opportunities(n) for n in plan.FEEDBACK_SPEAKER_RESPONSE_SHAPE)
    assert widest <= plan.FEEDBACK_STUDENT_COUNT


def test_a_shape_wider_than_the_cohort_is_refused_rather_than_narrowed():
    """Narrowing silently would change the residual arithmetic with nothing said."""
    with pytest.raises(ValueError, match="distinct students"):
        plan.build_speaker_feedback(shape=(plan.FEEDBACK_STUDENT_COUNT * 2,), seed=7)


def test_an_empty_or_negative_shape_is_refused():
    with pytest.raises(ValueError):
        plan.build_speaker_feedback(shape=(), seed=7)
    with pytest.raises(ValueError):
        plan.build_speaker_feedback(shape=(-1,), seed=7)


def test_a_feedback_students_token_and_subject_are_derived_from_its_rank_alone():
    """The rebuild script computes this map before any database exists."""
    principals = plan.feedback_dev_principals()
    assert len(principals) == plan.FEEDBACK_STUDENT_COUNT
    assert principals[plan.feedback_student_token(1)] == plan.feedback_student_external_subject(1)
    assert len(set(principals.values())) == len(principals)


def test_a_rank_outside_the_cohort_is_refused():
    """A token mapped to an unseeded subject authenticates as nobody and 401s."""
    with pytest.raises(ValueError):
        plan.feedback_student_token(0)
    with pytest.raises(ValueError):
        plan.feedback_student_external_subject(plan.FEEDBACK_STUDENT_COUNT + 1)


# ---------------------------------------------------------------------------
# Contact channels — a fraction reachable, a deliberate remainder not
# ---------------------------------------------------------------------------


def test_the_contact_channel_rule_matches_its_declared_share():
    """The constant and the function must not drift apart."""
    reached = sum(1 for index in range(100) if plan.records_contact_channel(index))
    assert abs(reached / 100 - plan.CONTACT_CHANNEL_SHARE) < 0.02


def test_a_deliberate_remainder_of_the_roster_holds_no_channel():
    """`no_contact_channel` must stay a reachable skip on a composed batch.

    A roster where everybody is addressable asserts a consent coverage no real
    programme has, and it would hide the one outcome the invitations surface
    exists to report honestly — that a shortlisted person cannot be written to.
    """
    unreachable = [index for index in range(100) if not plan.records_contact_channel(index)]
    assert unreachable
    assert len(unreachable) < 100


def test_which_roster_members_are_reachable_is_a_function_of_the_index_alone():
    """Two runs of one seed must agree about who an invitation could address."""
    first = [plan.records_contact_channel(index) for index in range(100)]
    second = [plan.records_contact_channel(index) for index in range(100)]
    assert first == second


def test_a_negative_roster_index_is_refused():
    with pytest.raises(ValueError):
        plan.records_contact_channel(-1)


# ---------------------------------------------------------------------------
# The Speaker Request evidence every seeded event has to carry
# ---------------------------------------------------------------------------


def test_every_planned_event_carries_at_least_one_industry_and_one_role_target():
    """The gap this file exists to keep closed: a seeded event with no targets.

    ``score_industry_match`` returns ``None`` with basis "speaker request names
    no industry sectors" when the request names none
    (``factors/industry_match.py``), ``score_role_match`` does the same, and
    ADR-0011 makes one unknown factor an unknown composite — so a match run
    against such an event can only answer
    ``match_run_insufficient_scorable_candidates``. Every seeded event sits in
    the coordinator's queue looking selectable, so every seeded event has to be
    one a run can actually score.

    Asserted over the *whole* calendar rather than a sample, and including the
    undated ones: an event with no resolvable date cannot be filed as a Speaker
    Request at all, but its targets are still planned, so the day it gets a date
    it is matchable rather than silently hollow.
    """
    for event in plan.build_events(120):
        assert event.industry_codes, f"event {event.index} ({event.title}) names no §7 sector"
        assert event.role_codes, f"event {event.index} ({event.title}) names no §8 role category"


def test_planned_event_targets_are_codes_the_released_taxonomies_name():
    """An unreleased code is a ``LookupError`` out of ``SpeakerRequestDraft``, not a row."""
    for event in plan.build_events(120):
        for code in event.industry_codes:
            sector_for_code(code)
        for code in event.role_codes:
            role_category_for_code(code)


def test_planned_event_targets_are_stated_once_each():
    """``SpeakerRequestDraft`` refuses a repeated selection; a seed may not write one."""
    for event in plan.build_events(120):
        assert len(set(event.industry_codes)) == len(event.industry_codes)
        assert len(set(event.role_codes)) == len(event.role_codes)


def test_the_calendar_does_not_target_one_sector_over_and_over():
    """A demo where every event wants the same sector is not a demo.

    Pinned as a floor on distinct target *sets* rather than on any particular
    assignment, so re-tuning the draw does not have to re-tune this test.
    """
    events = plan.build_events(60)
    industry_sets = {event.industry_codes for event in events}
    role_sets = {event.role_codes for event in events}
    assert len(industry_sets) >= 8
    assert len(role_sets) >= 5


def test_a_planned_events_targets_overlap_the_roster_the_run_would_score():
    """Targets nobody holds score every candidate the same defensible zero."""
    roster = plan.build_professionals(100)
    held_industries = {person.industry_code for person in roster}
    held_roles = {person.role_code for person in roster}

    matched = [
        event
        for event in plan.build_events(60)
        if set(event.industry_codes) & held_industries and set(event.role_codes) & held_roles
    ]
    assert len(matched) >= 30


def test_a_planned_physical_event_names_a_place_and_a_virtual_one_names_none():
    """``ck_event_virtual_has_no_location`` and §11, restated where the seed is built."""
    for event in plan.build_events(120):
        if event.is_virtual:
            assert event.location_city is None
            assert event.location_postal_code is None
        else:
            assert event.location_city or event.location_postal_code


def test_the_calendar_exercises_both_scoring_modes():
    """One mode seeded is one mode demonstrated; ``cba-physical-1`` is the one with Proximity."""
    events = plan.build_events(60)
    assert any(event.is_virtual for event in events)
    assert any(not event.is_virtual for event in events)


# ---------------------------------------------------------------------------
# Proximity: a located professional the centroid table can actually resolve
# ---------------------------------------------------------------------------


def test_every_located_professional_carries_a_postal_code():
    """Proximity is 30% of the physical model and reads exactly one column.

    ``match_run_evidence`` resolves ``speaker_profile.location_postal_code``
    against the OQ-CBA-024 centroid table; a profile without one is an
    ``unknown`` distance, an unknown composite (ADR-0011) and an unscorable
    candidate. ``location`` being present and the postal code being absent would
    be a coordinate nothing reads.
    """
    for person in plan.build_professionals(150):
        if person.location is None:
            assert person.postal_code is None
            assert person.city is None
        else:
            assert person.postal_code
            assert person.city


def test_every_planned_postal_code_is_in_the_released_centroid_table():
    """A ZIP the table does not name resolves to no coordinate, so Proximity stays unknown.

    This is the failure mode that looks fixed and is not: the column is
    populated, the factor still returns ``None``, and nothing about the refusal
    changes.
    """
    for person in plan.build_professionals(150):
        if person.postal_code is not None:
            assert person.postal_code in CA_ZCTA_CENTROIDS


def test_the_roster_is_spread_across_the_distance_bands():
    """A pool sitting at one distance decides the shortlist by tie-breaking."""
    located = [
        person for person in plan.build_professionals(100) if person.postal_code is not None
    ]
    distances = {
        resolve_distance_from_campus(person.postal_code).miles  # type: ignore[union-attr]
        for person in located
    }
    assert len(distances) >= 5
    assert max(distances) - min(distances) > 20.0
