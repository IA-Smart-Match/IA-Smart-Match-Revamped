"""Unit coverage for the synthetic pilot dataset's deterministic plan.

These tests are about the *shape* of the demo dataset, not about SQL. They
assert the two properties the generator's value rests on — that a seed
reproduces a plan exactly, and that a deliberate fraction of the plan carries
no evidence at all so ADR-0011's ``unknown`` states stay visible.
"""

from __future__ import annotations

from datetime import date

import pytest
from smartmatch_domain.metrics import OpportunityCategoryShape, shape_opportunity_category

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
