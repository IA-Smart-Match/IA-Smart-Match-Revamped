"""Folding ``attendance_record`` counts into one unit-scoped summary.

Migration ``0009``'s docstring names ``attendance_record`` "the evidence, and
the only input to points". This module is the arithmetic over that evidence
that a coordinator's summary needs, kept out of both the router and the
browser: :func:`summarize_attendance` takes counts a caller already read and
returns an :class:`AttendanceSummary`, so the total is a fold over recorded
facts rather than a formula anybody can re-derive differently.

## Why this is not arithmetic in a browser, and not arithmetic in SQL either

Fix #9 is the defect where a student's headline number was computed in the
browser from two summary counters, with no server-side record behind it. The
correction ADR-0013 makes is not "move that formula to the server" but "the
number is a fold over rows, computed once, server-side". The same reasoning
applies one level up, to a coordinator's attendance summary: the counts come
from ``GROUP BY`` over real rows, and the *total* is the sum of exactly those
counts — computed here, once, from the same object the response carries, so a
response cannot report a total its own breakdown contradicts.

## Every method is reported, including the ones with no rows

``ck_attendance_record_method`` fixes a closed vocabulary of three mechanisms,
so a unit that has recorded nothing by ``import`` has a *measured* zero there,
not a missing key. :func:`summarize_attendance` fills the vocabulary out, which
is ADR-0011 rule 1 applied to a breakdown: an absent key is one ``?? 0`` away
from being read as a zero anyway, and the difference between "we counted none"
and "we did not look" should not be left to a client to reconstruct.

## What a summary deliberately does not carry

No subject ids, no names, no per-student rows, and no field one could be put
in. A unit-scoped summary is a count of evidence, and D8 — the
disclosure-consent policy — is the decision that has not been made about who
may see whose attendance (``docs/architecture/engagement-model.md`` §8). Counts
of a cohort are not a disclosure about a person; a list of that cohort is.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Final

__all__ = [
    "ATTENDANCE_METHODS",
    "AttendanceSummary",
    "summarize_attendance",
]

#: ``attendance_record.method``'s closed vocabulary, transcribed from
#: ``ck_attendance_record_method`` (migration ``0009``).
#:
#: A literal here rather than an import of
#: ``smartmatch_persistence.attendance.ATTENDANCE_METHODS``, for two reasons.
#: The layering contract runs one way — persistence may read domain, never the
#: reverse — so the import could only go the other direction, and this package
#: is the one that has no business knowing a storage module exists. And the
#: repo's own convention for a value two places must agree on is a literal on
#: each side plus a test that compares them (``tests/authz/test_route_roles.py``
#: states the rule: "two role sets agreeing today is not a reason a widening of
#: one should silently widen the other").
#: ``tests/unit/test_attendance_summary.py`` holds the two in step.
ATTENDANCE_METHODS: Final[frozenset[str]] = frozenset({"qr_scan", "coordinator_entry", "import"})


@dataclass(frozen=True, slots=True)
class AttendanceSummary:
    """What a unit's attendance evidence amounts to. Counts, never people.

    Attributes:
        total: Rows counted. Always the sum of :attr:`by_method`'s values —
            computed from it in :func:`summarize_attendance`, so the two cannot
            drift.
        by_method: Every member of :data:`ATTENDANCE_METHODS`, each mapped to
            its own count. Read-only, and complete: a method with no rows is
            present with ``0``.
        distinct_subjects: How many different accounts appear across those
            rows. A count, not a roster — see the module docstring.
        distinct_events: How many different events those rows attest to.
        first_recorded_at: The earliest ``created_at`` among them, or ``None``
            when there are none. Timezone-aware.
        last_recorded_at: The latest, or ``None`` when there are none.
    """

    total: int
    by_method: Mapping[str, int]
    distinct_subjects: int
    distinct_events: int
    first_recorded_at: datetime | None
    last_recorded_at: datetime | None


def summarize_attendance(
    *,
    method_counts: Mapping[str, int],
    distinct_subjects: int,
    distinct_events: int,
    first_recorded_at: datetime | None,
    last_recorded_at: datetime | None,
) -> AttendanceSummary:
    """Fold counts a caller already read into one summary.

    Args:
        method_counts: Counts by ``attendance_record.method``. May omit a
            method with no rows; may not name a method outside
            :data:`ATTENDANCE_METHODS`, because such a row cannot exist and a
            summary that reported one would be describing something else.
        distinct_subjects: Distinct ``subject_id`` count over the same rows.
        distinct_events: Distinct ``event_id`` count over the same rows.
        first_recorded_at: Earliest ``created_at``, or ``None`` for no rows.
        last_recorded_at: Latest ``created_at``, or ``None`` for no rows.

    Returns:
        The :class:`AttendanceSummary`, with :attr:`~AttendanceSummary.total`
        summed here and :attr:`~AttendanceSummary.by_method` completed over the
        whole vocabulary.

    Raises:
        ValueError: an unknown method, a negative count, a distinct count that
            exceeds the total it is drawn from, exactly one of the two bounds
            present, a bound present with no rows (or absent with rows), a
            naive bound, or a first bound later than the last. Every one of
            these describes rows that cannot exist, so the honest answer is a
            refusal rather than a summary asserting them.
    """
    unknown = sorted(set(method_counts) - ATTENDANCE_METHODS)
    if unknown:
        raise ValueError(
            f"method_counts names {unknown}, which ck_attendance_record_method "
            f"forbids; the vocabulary is {sorted(ATTENDANCE_METHODS)}"
        )
    negative = sorted(method for method, count in method_counts.items() if count < 0)
    if negative:
        raise ValueError(f"method_counts is negative for {negative}; a count of rows cannot be")

    by_method = MappingProxyType(
        {method: int(method_counts.get(method, 0)) for method in sorted(ATTENDANCE_METHODS)}
    )
    total = sum(by_method.values())

    _require_drawn_from_total("distinct_subjects", distinct_subjects, total)
    _require_drawn_from_total("distinct_events", distinct_events, total)
    _require_consistent_bounds(total, first_recorded_at, last_recorded_at)

    return AttendanceSummary(
        total=total,
        by_method=by_method,
        distinct_subjects=distinct_subjects,
        distinct_events=distinct_events,
        first_recorded_at=first_recorded_at,
        last_recorded_at=last_recorded_at,
    )


def _require_drawn_from_total(field: str, value: int, total: int) -> None:
    """Refuse a distinct count that could not have come from ``total`` rows.

    Distinct values over N rows lie in ``0..N``, and the bounds are checked in
    both directions rather than only against zero: a ``distinct_subjects`` above
    ``total`` means the two figures were read from different row sets, which is
    a bug worth surfacing at the fold rather than shipping as a summary whose
    parts disagree.
    """
    if value < 0:
        raise ValueError(f"{field} is {value}; a count of distinct values cannot be negative")
    if value > total:
        raise ValueError(
            f"{field} is {value} over {total} attendance rows; distinct values cannot "
            "outnumber the rows they were drawn from, so these two figures did not "
            "come from the same rows"
        )


def _require_consistent_bounds(
    total: int, first_recorded_at: datetime | None, last_recorded_at: datetime | None
) -> None:
    """Refuse time bounds that contradict the row count or each other."""
    present = [bound for bound in (first_recorded_at, last_recorded_at) if bound is not None]
    if len(present) == 1:
        raise ValueError(
            "first_recorded_at and last_recorded_at are both present or both absent; "
            "one alone describes a row set with a beginning and no end"
        )
    if total == 0 and present:
        raise ValueError("no attendance rows were counted, so there is no instant to report")
    if total > 0 and not present:
        raise ValueError(
            f"{total} attendance rows were counted, so both bounds must be present; "
            "every row carries a NOT NULL created_at"
        )
    for bound in present:
        if bound.tzinfo is None or bound.tzinfo.utcoffset(bound) is None:
            raise ValueError(
                f"{bound!r} is naive; ADR-0010 keeps every instant in this codebase "
                "timezone-aware, and a summary is not the place to invent a zone"
            )
    if (
        first_recorded_at is not None
        and last_recorded_at is not None
        and first_recorded_at > last_recorded_at
    ):
        raise ValueError(
            f"first_recorded_at {first_recorded_at.isoformat()} is after "
            f"last_recorded_at {last_recorded_at.isoformat()}"
        )
