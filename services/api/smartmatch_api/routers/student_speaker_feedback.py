"""Students rate speakers; Connectors read an aggregate that never names one.

Customer §§15-16, implementing OQ-CBA-003 as decided on 6 September 2026 by
Danny Tran, program owner of record. Five routes:

* ``POST   /v1/units/{unit_id}/student/events/{event_id}/speakers/{speaker_id}/feedback``
  — submit a rating, or amend the one already there.
* ``DELETE /v1/units/{unit_id}/student/events/{event_id}/speakers/{speaker_id}/feedback``
  — withdraw it.
* ``GET    /v1/units/{unit_id}/student/events/{event_id}/speaker-feedback``
  — what this student has already said about speakers at this event.
* ``GET    /v1/units/{unit_id}/speakers/{speaker_id}/feedback-summary``
  — the Connector's read, for one speaker.
* ``GET    /v1/units/{unit_id}/speaker-feedback-summary``
  — the Connector's read, pooled over the unit. Suppressed by the same
  threshold *and* by a residual rule, because a unit number published beside
  the per-speaker numbers can be differenced against them.

Where the anonymity actually lives
====================================
Here. The row stores ``student_id`` — see migration ``0031`` for why dropping it
would break retraction, de-duplication and abuse tracing at once — and **this
module is what keeps it off a Connector's screen.**

Three structural facts do that, in preference to a rule somebody has to
remember:

1. The Connector route's only read is
   :meth:`StudentSpeakerFeedbackRepository.submitted_ratings`, which selects one
   column and returns ``list[int]``. There is no ``student_id`` in the result
   set to forget to strip.
2. :class:`SpeakerFeedbackSummaryResponse` has no field one could be assigned
   to, and neither does
   :class:`~smartmatch_domain.student_speaker_feedback.SpeakerFeedbackAggregate`.
3. The two student-facing views return the caller's *own* rows only, and do not
   carry the column either — a caller reading their own feedback learns nothing
   from being told who they are, and a field that exists nowhere in this module
   cannot be copied onto the Connector's response later.

There is deliberately **no route that lists individual ratings to a Connector**,
with or without names. A list of thirty rows carrying timestamps and free text
re-identifies its authors in a class of thirty whether or not a column says so,
and §16 asks for feedback a Connector can view, not for a transcript.

Comments are not in the aggregate either
==========================================
:class:`SpeakerFeedbackSummaryResponse` carries a mean, a count and a sentence.
It does not carry the free-text comments, and that is the one place this surface
is narrower than the decision strictly requires. A comment is written in a
student's own voice and is the most re-identifying field on the row; a route
returning thirty of them to a speaker's advocate has published the transcript by
another name. Whether Connectors should see comments at all, and under what
threshold, is **OQ-CBA-054** — raised rather than answered, because the decision
settled aggregation and said nothing about free text.

Suppression is the domain's, not a query's
============================================
Below three responses the summary carries no mean **and no count**, and reads
"not enough responses yet". That rule lives in
:func:`~smartmatch_domain.student_speaker_feedback.aggregate_speaker_feedback`
with a unit test, not in a ``HAVING`` clause here — a privacy rule in a query
plan is a privacy rule nobody can read.

ADR-0011 rule 1 is why the empty case is suppressed rather than zeroed: a
speaker nobody has rated and a speaker rated 0.0 are different claims, and only
one of them is true.

Eligibility, and the join that does not exist
===============================================
A student may rate a speaker only at an event they **attended** — not merely
registered for. The check is
:meth:`StudentSpeakerFeedbackRepository.eligibility`, and the same fact is a
composite foreign key on the row, so a route that skipped the check would get an
``IntegrityError`` rather than a bad row. The check exists so the refusal is a
worded ``403`` instead of a ``500``.

The speaker half is weaker, and the weakness is in the schema rather than here:
**nothing in this database records which speaker appeared at which event.**
``cba_invitation_batch`` names its event in free text and cannot be joined. This
module requires the speaker to be on the unit's §13 roster, which is the nearest
available evidence and is not the same claim. **OQ-CBA-051.**

Two routers, two capabilities
===============================
The student routes are gated by ``EVENT_READS`` — the surface is reached from an
event a student attended, and it is the capability ``routers/student_events.py``
already mounts the rest of that journey under. The Connector summary is gated by
``SPEAKER_CONTACT_MANAGEMENT`` instead: it is a fact about a roster contact,
reached from the contact, and a deployment that has turned the roster off should
not be answering questions about who is on it. Mounting both halves under one
capability would make one of those two statements false.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Annotated, Final

from fastapi import APIRouter, Path, Response, status
from pydantic import BaseModel, Field
from smartmatch_authz import OrgPath, Resource, assert_allowed
from smartmatch_domain.student_speaker_feedback import (
    MAX_COMMENT_LENGTH,
    MAX_RATING,
    MIN_RATING,
    MIN_RESPONSES_FOR_AGGREGATE,
    EditWindow,
    Rating,
    aggregate_speaker_feedback,
    aggregate_unit_feedback,
    resolve_edit_window,
)
from smartmatch_persistence.rate_limit import RateLimit
from smartmatch_persistence.student_speaker_feedback import (
    FeedbackRow,
    StudentSpeakerFeedbackRepository,
)
from sqlalchemy.orm import Session

from smartmatch_api.dependencies import CurrentPrincipal, DbSession, charge_quota
from smartmatch_api.errors import ApiError
from smartmatch_api.units import load_unit_or_404
from smartmatch_api.utils import utc_now

#: The student's own surface, mounted beside ``routers/student_events.py``'s.
router = APIRouter(prefix="/v1/units", tags=["student-speaker-feedback"])

#: The Connector's read. A second router rather than a second route on the one
#: above, because the two are gated by different product capabilities — see the
#: module docstring.
connector_router = APIRouter(prefix="/v1/units", tags=["student-speaker-feedback"])

#: The one writer of ``student_speaker_feedback``. Module-level and stateless,
#: the arrangement ``routers/student_events.py`` uses for its own repository.
_feedback = StudentSpeakerFeedbackRepository()

#: Who may submit, amend or withdraw a rating. ``student`` alone.
#:
#: Customer §15 names the Student and nobody else, and under deny-by-default the
#: absence of a permit is a denial rather than an invitation to guess. ``admin``
#: and ``coordinator`` are deliberately absent, and not merely by omission: a
#: coordinator who could write a rating could manufacture the evidence they are
#: about to read, and the n=3 threshold would be three keystrokes away from any
#: number they wanted.
#:
#: A literal ``frozenset`` rather than an import of
#: ``routers/student_events.py``'s, for the reason
#: ``tests/authz/test_route_roles.py`` gives about its own ledger: two role sets
#: agreeing today is not a reason a widening of one should silently widen the
#: other.
_STUDENT_FEEDBACK_WRITE_ROLES: Final[frozenset[str]] = frozenset({"student"})

#: Who may read their own ratings back. ``student`` alone, and equal to the
#: write set today.
#:
#: A second literal for the reason above, and the widening is a real one to
#: imagine: OQ-CBA-019 asks whether a Connector should be able to preview the
#: student surface, and an answer of "yes" must not also hand them the ability to
#: write a rating. Reads and writes are different questions even when the answer
#: happens to match.
_STUDENT_FEEDBACK_READ_ROLES: Final[frozenset[str]] = frozenset({"student"})

#: Who may read the aggregate. §16: "Speaker Connectors/admin users must be able
#: to view the feedback."
#:
#: Role-gated rather than membership-gated. ``routers/metrics.py`` reads its
#: aggregate on membership alone, and that shape is deliberately not copied: the
#: artifact authorising it is the ratified metrics decision, this is a different
#: surface, and under deny-by-default the narrower gate is the one that needs no
#: new authorisation. ``student`` is absent — a student reads their own rows,
#: not the class's average.
_SPEAKER_FEEDBACK_SUMMARY_ROLES: Final[frozenset[str]] = frozenset({"admin", "coordinator"})

#: Who may read the unit-level pool. The same pair, and a second literal.
#:
#: Not an alias of the constant above, and the reason is sharper here than the
#: usual ledger argument. These two surfaces are the pair a differencing attack
#: is run across: the unit number is the one a reader subtracts a published
#: per-speaker number from. A widening of one set would reach both sides of that
#: subtraction at once, and the residual rule assumes exactly one thing about
#: its reader — that what they can subtract is what this API published to them.
#:
#: No ``tenant_wide_roles``, for the reason above and one more: pooling a whole
#: tenant's ratings from one department would be a wider claim than the
#: per-speaker read makes, and this surface follows ``routers/engagement.py``'s
#: attendance summary rather than ``routers/metrics.py``'s tenant-wide shape.
_UNIT_FEEDBACK_SUMMARY_ROLES: Final[frozenset[str]] = frozenset({"admin", "coordinator"})

#: The per-caller quota on feedback writes.
#:
#: Charged on the two writes and on neither read, and 30 a minute is
#: ``routers/student_events.py``'s write allowance reused rather than a second
#: number invented here. Well above what a person can click: this is a defence
#: against a loop, not against a student changing their mind twice — and because
#: both writes are idempotent, a caller who hits the limit has already achieved
#: whatever their repeated request was asking for.
STUDENT_FEEDBACK_RATE_LIMIT: Final[RateLimit] = RateLimit(
    operation="student_speaker_feedback.write", max_requests=30, window=timedelta(minutes=1)
)


# ---------------------------------------------------------------------------
# Request and response models
# ---------------------------------------------------------------------------


class FeedbackSubmission(BaseModel):
    """What a student says about one speaker.

    Two fields. There are no sub-criteria: OQ-CBA-003 approved one overall
    dimension and customer §16 says not to over-design the requirement, so a
    second axis is a product decision rather than a field.
    """

    rating: int = Field(
        ge=MIN_RATING,
        le=MAX_RATING,
        description=(
            "Overall rating, 1 to 5. Required. There is no zero on this scale: a "
            "speaker nobody rated has no row, which is a different fact from a "
            "speaker rated badly."
        ),
    )
    comment: str | None = Field(
        default=None,
        max_length=MAX_COMMENT_LENGTH,
        description=(
            "Optional free text. Absent means the student wrote nothing; a blank "
            "or whitespace-only value is normalized to absent rather than stored, "
            "so there is no third state between 'wrote nothing' and 'wrote "
            "something'."
        ),
    )


class EditWindowView(BaseModel):
    """When this rating stops being its author's to change."""

    state: str = Field(
        description=(
            "'open', 'closed', or 'unknown'. 'unknown' means the event carries no "
            "resolved date, so no cutoff can be measured — which is not the same "
            "as a cutoff that has not arrived, and not the same as one that has."
        )
    )
    closes_at: str | None = Field(
        default=None,
        description=(
            "When the window shuts, ISO-8601. Null when the state is 'unknown'. "
            "Never a fabricated date: a surface with no cutoff to show says so."
        ),
    )


class StudentFeedbackView(BaseModel):
    """One of the caller's own ratings.

    Carries no ``student_id``. Not because it would leak here — these are the
    caller's own rows — but because the field exists on no response model in this
    module, which is what stops one appearing on the Connector's by a later
    copy-paste.
    """

    speaker_professional_id: uuid.UUID
    status: str = Field(description="'submitted' or 'withdrawn'.")
    rating: int | None = Field(
        default=None,
        description=(
            "1 to 5, or null on a withdrawn rating. Null is an absence, never a "
            "zero — the rating was taken back, not scored badly."
        ),
    )
    comment: str | None = Field(
        default=None,
        description=(
            "The student's words, or null. Null both when they wrote none and "
            "after a withdrawal took them back: a retraction takes back the words "
            "as well as the number."
        ),
    )
    submitted_at: str
    updated_at: str
    edit_window: EditWindowView


class StudentFeedbackResponse(BaseModel):
    """The result of one submit or withdraw."""

    feedback: StudentFeedbackView | None = Field(
        default=None,
        description=(
            "The rating as it now stands. Null only from a withdrawal by a "
            "student who never rated this speaker, which stores nothing rather "
            "than manufacturing a pre-withdrawn row."
        ),
    )
    changed: bool = Field(
        description=(
            "Whether this request moved anything. False for a repeat of an "
            "identical submission and for a withdrawal with nothing to withdraw, "
            "so a response never claims an edit that did not happen."
        )
    )


class StudentFeedbackListResponse(BaseModel):
    """What this student has said about speakers at one event."""

    unit_id: uuid.UUID
    event_id: uuid.UUID
    feedback: list[StudentFeedbackView]


class SpeakerFeedbackSummaryResponse(BaseModel):
    """What a Connector is told about one speaker.

    Three numbers and a sentence, and **no field that can name a student**. That
    is part 1 of OQ-CBA-003 held as a type rather than as a discipline.
    """

    speaker_professional_id: uuid.UUID
    suppressed: bool = Field(
        description=(
            "True when fewer than the threshold of students have rated this "
            "speaker. Both numbers below are then null."
        )
    )
    response_count: int | None = Field(
        default=None,
        description=(
            "How many ratings the mean was computed from, or null when "
            "suppressed. Withheld along with the mean rather than published "
            "beside it: in a class of thirty, 'two students rated this speaker' "
            "narrows the field considerably."
        ),
    )
    mean_rating: float | None = Field(
        default=None,
        description=(
            "The average, to two decimals, or null when suppressed. Null and "
            "never 0.0 — ADR-0011 rule 1: a value with no evidence is unknown, "
            "and a speaker nobody rated must not read as a speaker rated zero."
        ),
    )
    display_text: str = Field(
        description=(
            "What to render. 'not enough responses yet' when suppressed — a "
            "sentence rather than a dash or a zero, so a reader can tell 'we are "
            "not telling you' from 'the answer is nothing'."
        )
    )
    minimum_responses: int = Field(
        description=(
            "The threshold below which nothing is published, so a surface can "
            "explain the suppression without hard-coding the number."
        )
    )


class UnitFeedbackSummaryResponse(BaseModel):
    """What a Connector is told about a whole unit's ratings.

    The model above with ``unit_id`` in place of ``speaker_professional_id``,
    and **nothing else added**. In particular there is no per-speaker
    breakdown, no count of how many speakers were rated, and no list of speaker
    ids: every extra number here is a handle a reader can difference the pooled
    one against, which is the attack the domain's residual rule exists to close.
    Publishing the pool and then handing back its parts would undo it in the
    response model.

    Nothing here is a score, a weight or a factor. Whether student ratings
    should ever reach matching is **OQ-CBA-053**, and it is open — a field name
    that implied otherwise would answer it by accident.
    """

    unit_id: uuid.UUID
    suppressed: bool = Field(
        description=(
            "True when the unit's pooled ratings are withheld — either because "
            "fewer than the threshold exist, or because publishing them would "
            "let a reader subtract an already-published speaker's aggregate and "
            "recover the ratings of a speaker whose own aggregate is suppressed. "
            "Both numbers below are then null."
        )
    )
    response_count: int | None = Field(
        default=None,
        description=(
            "How many ratings across the unit the mean was computed from, or "
            "null when suppressed. Withheld along with the mean rather than "
            "published beside it, for the reason the per-speaker summary gives."
        ),
    )
    mean_rating: float | None = Field(
        default=None,
        description=(
            "The unit's average, to two decimals, over the pooled ratings — not "
            "an average of per-speaker averages, which would weight a speaker "
            "rated once like a speaker rated ten times. Null when suppressed, "
            "and never 0.0: ADR-0011 rule 1."
        ),
    )
    display_text: str = Field(
        description=(
            "What to render. 'not enough responses yet' when suppressed — which "
            "here can also mean 'enough responses, but publishing them would "
            "expose an individual speaker's raters'. The sentence is the same "
            "because the reader is owed the same thing: a statement that we are "
            "not telling them, rather than a dash or a zero."
        )
    )
    minimum_responses: int = Field(
        description=(
            "The threshold below which nothing is published, and the same "
            "threshold the residual test uses, so a surface can explain the "
            "suppression without hard-coding the number."
        )
    )


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


def _authorize_student_feedback_write(
    session: Session,
    principal: CurrentPrincipal,
    unit_id: uuid.UUID,
) -> None:
    """Load the unit and authorize a student's feedback write against it.

    The unit is loaded first and authorization runs against *that row's* path
    rather than anything from the request; ``load_unit_or_404`` scopes the lookup
    by the caller's own tenant, so a foreign unit is a ``404`` rather than a
    ``403`` that would confirm the id names something real.

    What this does **not** check is that the caller is rating as *themselves*. It
    could not — the policy engine has no concept of a self-scope. That guarantee
    is structural instead: every route here takes ``student_id`` from
    ``principal.user_id``, and no route accepts one in a body or a path, so there
    is no request field for MM-A01's caller-selected identity to enter through.
    """
    unit = load_unit_or_404(session, tenant_id=principal.tenant_id, unit_id=unit_id)
    assert_allowed(
        principal.principal,
        Resource(
            resource_type="org_unit",
            resource_id=str(unit_id),
            tenant_id=str(principal.tenant_id),
            owning_unit_path=OrgPath.parse(unit.path),
        ),
        at=utc_now(),
        required_roles=_STUDENT_FEEDBACK_WRITE_ROLES,
    )


def _authorize_student_feedback_read(
    session: Session,
    principal: CurrentPrincipal,
    unit_id: uuid.UUID,
) -> None:
    """Load the unit and authorize a student reading their own ratings back.

    A separate function from :func:`_authorize_student_feedback_write`, and the
    separation is the point rather than an accident of drafting: routing a read
    through the write authorizer would make
    ``tests/authz/test_policy_matrix.py``'s ``authorizer`` column say something
    false about this route, and the matrix reads that column out of the source
    precisely so it cannot.
    """
    unit = load_unit_or_404(session, tenant_id=principal.tenant_id, unit_id=unit_id)
    assert_allowed(
        principal.principal,
        Resource(
            resource_type="org_unit",
            resource_id=str(unit_id),
            tenant_id=str(principal.tenant_id),
            owning_unit_path=OrgPath.parse(unit.path),
        ),
        at=utc_now(),
        required_roles=_STUDENT_FEEDBACK_READ_ROLES,
    )


def _authorize_speaker_feedback_summary_read(
    session: Session,
    principal: CurrentPrincipal,
    unit_id: uuid.UUID,
) -> None:
    """Load the unit and authorize a Connector's read of the aggregate."""
    unit = load_unit_or_404(session, tenant_id=principal.tenant_id, unit_id=unit_id)
    assert_allowed(
        principal.principal,
        Resource(
            resource_type="org_unit",
            resource_id=str(unit_id),
            tenant_id=str(principal.tenant_id),
            owning_unit_path=OrgPath.parse(unit.path),
        ),
        at=utc_now(),
        required_roles=_SPEAKER_FEEDBACK_SUMMARY_ROLES,
    )


def _authorize_unit_feedback_summary_read(
    session: Session,
    principal: CurrentPrincipal,
    unit_id: uuid.UUID,
) -> None:
    """Load the unit and authorize a Connector's read of the unit-level pool.

    A fourth name in this module rather than a call into the one above, even
    though the two role sets are identical today. The per-speaker aggregate and
    the unit aggregate are the two numbers a differencing attack is computed
    from, and a single authorizer would make one widening reach both of them —
    the one widening the residual rule cannot survive, because that rule assumes
    the only thing a reader can subtract is what this API published to *them*.

    No ``tenant_wide_roles``, so a membership must contain this unit's path.
    """
    unit = load_unit_or_404(session, tenant_id=principal.tenant_id, unit_id=unit_id)
    assert_allowed(
        principal.principal,
        Resource(
            resource_type="org_unit",
            resource_id=str(unit_id),
            tenant_id=str(principal.tenant_id),
            owning_unit_path=OrgPath.parse(unit.path),
        ),
        at=utc_now(),
        required_roles=_UNIT_FEEDBACK_SUMMARY_ROLES,
    )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _view(row: FeedbackRow, window: EditWindow) -> StudentFeedbackView:
    """Render one of the caller's own ratings, with the window that governs it."""
    return StudentFeedbackView(
        speaker_professional_id=row.speaker_professional_id,
        status=row.status,
        rating=row.rating,
        comment=row.comment,
        submitted_at=row.submitted_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
        edit_window=EditWindowView(
            state=window.state.value,
            closes_at=None if window.closes_at is None else window.closes_at.isoformat(),
        ),
    )


def _require_eligible_and_open(
    session: Session,
    principal: CurrentPrincipal,
    *,
    unit_id: uuid.UUID,
    event_id: uuid.UUID,
    speaker_id: uuid.UUID,
) -> EditWindow:
    """Refuse, in words, every reason this student may not write this rating.

    Order matters. The event's existence is checked first, then the speaker's
    presence on the roster, then the caller's attendance, then the window. Each
    refusal is about a fact the caller either already has or is entitled to —
    they are asking about an event in their own unit, about a speaker on that
    unit's roster, and about their own attendance — so none of the four is an
    existence oracle.

    Returns:
        The edit window, so the caller does not resolve it twice.

    Raises:
        ApiError: ``404 event_not_found`` when no such event exists in this
            tenant; ``404 speaker_contact_not_found`` when the speaker is not on
            this unit's roster; ``403 student_feedback_not_eligible`` when the
            caller has no attendance record for the event;
            ``409 student_feedback_window_closed`` once the cutoff has passed.
    """
    facts = _feedback.eligibility(
        session,
        tenant_id=principal.tenant_id,
        owning_unit_id=unit_id,
        student_id=principal.user_id,
        event_id=event_id,
        speaker_professional_id=speaker_id,
    )

    if not facts.event_exists:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="event_not_found",
            message="No such event in this tenant.",
        )
    if not facts.speaker_on_roster:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="speaker_contact_not_found",
            message="No such speaker on this unit's roster.",
        )
    if not facts.attended:
        raise ApiError(
            status_code=status.HTTP_403_FORBIDDEN,
            code="student_feedback_not_eligible",
            message=(
                "Feedback is limited to speakers at events you attended, and there "
                "is no attendance record for you at this event."
            ),
        )

    window = resolve_edit_window(anchor=facts.anchor, now=utc_now())
    if not window.permits_change:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="student_feedback_window_closed",
            message="The window for changing feedback on this event has closed.",
            details={
                "closed_at": None if window.closes_at is None else window.closes_at.isoformat()
            },
        )
    return window


# ---------------------------------------------------------------------------
# Submit or amend a rating
# ---------------------------------------------------------------------------


@router.post(
    "/{unit_id}/student/events/{event_id}/speakers/{speaker_id}/feedback",
    response_model=StudentFeedbackResponse,
    summary="Rate a speaker at an event you attended, or amend your rating",
)
def submit_speaker_feedback(
    principal: CurrentPrincipal,
    session: DbSession,
    body: FeedbackSubmission,
    response: Response,
    unit_id: Annotated[uuid.UUID, Path()],
    event_id: Annotated[uuid.UUID, Path()],
    speaker_id: Annotated[uuid.UUID, Path()],
) -> StudentFeedbackResponse:
    """Record this student's rating, or amend the one already there.

    One route for both, because it is one row: the natural key
    ``(tenant, student, event, speaker)`` means a second submission is an edit of
    the caller's own rating rather than a second vote. Editing is part 3 of
    OQ-CBA-003 and needs no separate verb.

    ``201`` when this created the rating, ``200`` when it amended or repeated
    one. A repeat that changes nothing writes nothing and reports
    ``changed: false``, so ``updated_at`` keeps meaning "when this last moved".

    Raises:
        403: ``forbidden`` for a caller who is not a student in this unit;
            ``student_feedback_not_eligible`` for a student with no attendance
            record at this event.
        404: ``unit_not_found``, ``event_not_found``, or
            ``speaker_contact_not_found``.
        409: ``student_feedback_window_closed`` once the cutoff has passed.
        422: ``invalid_request`` for a rating off the 1-5 scale.
        429: over the write quota.
    """
    charge_quota(session, principal, STUDENT_FEEDBACK_RATE_LIMIT)
    _authorize_student_feedback_write(session, principal, unit_id)
    window = _require_eligible_and_open(
        session, principal, unit_id=unit_id, event_id=event_id, speaker_id=speaker_id
    )

    result = _feedback.submit(
        session,
        tenant_id=principal.tenant_id,
        owning_unit_id=unit_id,
        # From the verified principal, never from the body or the path. There is
        # no request field a caller could put somebody else's id in.
        student_id=principal.user_id,
        event_id=event_id,
        speaker_professional_id=speaker_id,
        rating=Rating(value=body.rating, comment=body.comment),
    )

    # The one commit. Without it `get_session`'s unconditional rollback discards
    # the rating and this route returns a clean 201 having stored nothing.
    session.commit()

    if result.created:
        response.status_code = status.HTTP_201_CREATED
    if result.row is None:  # pragma: no cover - a submit always leaves a row
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="student_feedback_not_stored",
            message="The rating could not be read back after writing.",
        )
    return StudentFeedbackResponse(feedback=_view(result.row, window), changed=result.changed)


# ---------------------------------------------------------------------------
# Withdraw a rating
# ---------------------------------------------------------------------------


@router.delete(
    "/{unit_id}/student/events/{event_id}/speakers/{speaker_id}/feedback",
    response_model=StudentFeedbackResponse,
    summary="Withdraw your rating of a speaker",
)
def withdraw_speaker_feedback(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
    event_id: Annotated[uuid.UUID, Path()],
    speaker_id: Annotated[uuid.UUID, Path()],
) -> StudentFeedbackResponse:
    """Take this student's rating back.

    The row survives and its status moves — a withdrawal is a transition, not a
    ``DELETE``, so "withdrawn" and "never rated" stay distinguishable. Both the
    rating and the comment are cleared, because a retraction that took back the
    number and left the words would be half-honoured.

    Withdrawing something that was never rated is not an error: it writes nothing
    and reports ``changed: false`` with a null ``feedback``. Answering ``409`` to
    a request whose outcome is already the one the caller wanted would be a worse
    surface than saying "there is nothing there".

    Raises:
        403: ``forbidden``, or ``student_feedback_not_eligible``.
        404: ``unit_not_found``, ``event_not_found``, or
            ``speaker_contact_not_found``.
        409: ``student_feedback_window_closed`` — a locked rating cannot be
            withdrawn either, which is what "then locked" means.
        429: over the write quota.
    """
    charge_quota(session, principal, STUDENT_FEEDBACK_RATE_LIMIT)
    _authorize_student_feedback_write(session, principal, unit_id)
    window = _require_eligible_and_open(
        session, principal, unit_id=unit_id, event_id=event_id, speaker_id=speaker_id
    )

    result = _feedback.withdraw(
        session,
        tenant_id=principal.tenant_id,
        student_id=principal.user_id,
        event_id=event_id,
        speaker_professional_id=speaker_id,
    )

    # The one commit, for the reason the submit route states. A withdrawal that
    # is rolled back returns 200 and leaves the rating standing, which is the
    # worst possible outcome for a student who asked for it to stop existing.
    session.commit()

    return StudentFeedbackResponse(
        feedback=None if result.row is None else _view(result.row, window),
        changed=result.changed,
    )


# ---------------------------------------------------------------------------
# A student reads their own ratings back
# ---------------------------------------------------------------------------


@router.get(
    "/{unit_id}/student/events/{event_id}/speaker-feedback",
    response_model=StudentFeedbackListResponse,
    summary="What you have already said about speakers at this event",
)
def list_my_speaker_feedback(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
    event_id: Annotated[uuid.UUID, Path()],
) -> StudentFeedbackListResponse:
    """This caller's own ratings at one event, whatever their status.

    Withdrawn rows are returned too. The form has to render "you withdrew this"
    differently from "you have not rated this speaker", and dropping withdrawn
    rows here would make the two indistinguishable on the one surface that has to
    tell them apart.

    Scoped to the caller by ``principal.user_id``, so this route cannot be aimed
    at another student: there is no parameter to aim it with.

    One window is resolved for the whole listing rather than one per row: the
    cutoff depends on the event, not on the speaker, so resolving it per row
    would issue N identical queries to reach N identical answers.

    Raises:
        403: ``forbidden`` for a caller who is not a student in this unit.
        404: ``unit_not_found`` or ``event_not_found``.
    """
    _authorize_student_feedback_read(session, principal, unit_id)

    event_exists, anchor = _feedback.event_anchor(
        session, tenant_id=principal.tenant_id, event_id=event_id
    )
    if not event_exists:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="event_not_found",
            message="No such event in this tenant.",
        )
    window = resolve_edit_window(anchor=anchor, now=utc_now())

    rows = _feedback.list_for_student_event(
        session,
        tenant_id=principal.tenant_id,
        student_id=principal.user_id,
        event_id=event_id,
    )
    return StudentFeedbackListResponse(
        unit_id=unit_id,
        event_id=event_id,
        feedback=[_view(row, window) for row in rows],
    )


# ---------------------------------------------------------------------------
# The Connector's aggregate read
# ---------------------------------------------------------------------------


@connector_router.get(
    "/{unit_id}/speakers/{speaker_id}/feedback-summary",
    response_model=SpeakerFeedbackSummaryResponse,
    summary="How students rated a speaker, in aggregate",
)
def read_speaker_feedback_summary(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
    speaker_id: Annotated[uuid.UUID, Path()],
) -> SpeakerFeedbackSummaryResponse:
    """The mean and the count, or a sentence saying there are too few to publish.

    §16's "Speaker Connectors/admin users must be able to view the feedback",
    read as an aggregate rather than a transcript. **No student is named, and no
    individual rating is returned** — see the module docstring for why the list
    route a reader might expect does not exist.

    Below :data:`MIN_RESPONSES_FOR_AGGREGATE` responses both numbers are null and
    ``display_text`` reads "not enough responses yet". A speaker nobody has rated
    is suppressed for the same reason a speaker two people rated is: zero is not
    the average of nothing.

    A speaker who is not on this unit's roster is a ``404`` rather than an empty
    summary, so this route cannot be used to enumerate ids — an empty aggregate
    for every unknown id would answer "does this id exist here?" for free.

    Raises:
        403: ``forbidden`` for a caller who is not an admin or coordinator here.
        404: ``unit_not_found`` or ``speaker_contact_not_found``.
    """
    _authorize_speaker_feedback_summary_read(session, principal, unit_id)

    if not _feedback.speaker_on_roster(
        session,
        tenant_id=principal.tenant_id,
        owning_unit_id=unit_id,
        speaker_professional_id=speaker_id,
    ):
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="speaker_contact_not_found",
            message="No such speaker on this unit's roster.",
        )

    aggregate = aggregate_speaker_feedback(
        _feedback.submitted_ratings(
            session,
            tenant_id=principal.tenant_id,
            owning_unit_id=unit_id,
            speaker_professional_id=speaker_id,
        )
    )

    return SpeakerFeedbackSummaryResponse(
        speaker_professional_id=speaker_id,
        suppressed=aggregate.suppressed,
        response_count=aggregate.response_count,
        mean_rating=aggregate.mean_rating,
        display_text=aggregate.display_text,
        minimum_responses=MIN_RESPONSES_FOR_AGGREGATE,
    )


@connector_router.get(
    "/{unit_id}/speaker-feedback-summary",
    response_model=UnitFeedbackSummaryResponse,
    summary="How students rated this unit's speakers, pooled",
)
def read_unit_feedback_summary(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
) -> UnitFeedbackSummaryResponse:
    """One mean and one count for the whole unit, or a sentence saying no.

    The Connector dashboard's read. It exists because the same number cannot be
    computed in the browser: a suppressed per-speaker summary contributes
    ``null``, so a client-side total either drops it and undercounts or
    republishes what suppression withheld.

    **This is not a sum of the per-speaker aggregates, and it is not simply the
    pool with the same threshold applied.** The per-speaker route is public to
    the same reader, so a pooled ``n`` can be *differenced* against what that
    route already published: with one speaker at ``n=3`` and the unit at
    ``n=5``, ``5 - 3 = 2`` recovers a mean over two students, which is the
    statement the threshold exists to withhold. So the aggregate is published
    only when the pool clears the threshold **and** the residual — the pool
    minus every already-published speaker's count — is zero or itself at or
    above the threshold. A unit with a large pool can therefore be suppressed,
    and that is the rule working rather than failing.

    The arithmetic and the rule are
    :func:`~smartmatch_domain.student_speaker_feedback.aggregate_unit_feedback`'s,
    with a unit test matrix. Neither is a ``GROUP BY ... HAVING`` here, for the
    reason the module docstring gives: a privacy rule in a query plan is a
    privacy rule nobody can read.

    **No student, no speaker, no breakdown.** The response carries the unit's
    id, the two numbers or two nulls, the sentence and the threshold. A
    ``speakers: [...]`` list "for the chart" would be the per-speaker route
    again with its suppression decided in one place for all of them, and it
    would re-open exactly what the residual rule closes.

    Nothing here reads into a factor, a weight or a ``match_run``: whether
    student ratings should ever inform matching is **OQ-CBA-053**, and it is
    open.

    Raises:
        403: ``forbidden`` for a caller who is not an admin or coordinator here.
        404: ``unit_not_found``.
    """
    _authorize_unit_feedback_summary_read(session, principal, unit_id)

    aggregate = aggregate_unit_feedback(
        _feedback.submitted_ratings_by_speaker(
            session,
            tenant_id=principal.tenant_id,
            owning_unit_id=unit_id,
        )
    )

    return UnitFeedbackSummaryResponse(
        unit_id=unit_id,
        suppressed=aggregate.suppressed,
        response_count=aggregate.response_count,
        mean_rating=aggregate.mean_rating,
        display_text=aggregate.display_text,
        minimum_responses=MIN_RESPONSES_FOR_AGGREGATE,
    )
