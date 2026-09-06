"""What a student's event registration is, and what it refuses to be.

Customer §15: a student browses their unit's events and *registers* for the ones
they intend to go to. Migration ``0026`` is where that intent is stored; this
module is the vocabulary and the two transitions over it, kept out of both the
router and the repository so the rules can be exercised with no database and no
HTTP client.

Nothing here reads, writes, or fetches anything. Turning a transition into rows
is ``smartmatch_persistence.event_registration``'s job, and deciding who may
register is ``smartmatch_authz``'s.

A registration is not an attendance, and this module is one of the places that
stays true
==============================================================================
``attendance_record`` says a student *was there*. ADR-0013 makes it the only
input to points and ``ck_point_ledger_entry_kind`` derives every
``attendance_credit`` from a ``source_attendance_id``, so anything written into
that table is by construction a thing points can be computed from. A
registration is a statement about the future made by the student, and crediting
it would pay a student for an event they had not attended.

So this module names no attendance method, imports nothing from
:mod:`smartmatch_domain.attendance`, and offers no function that turns one of
these into the other. The separation is the feature: "registered but did not
attend" stays a question two tables can answer, rather than one that needs
archaeology.

Two statuses, and why there is no third
=========================================
:data:`REGISTRATION_STATUSES` transcribes ``ck_event_registration_status``
exactly — ``registered`` and ``cancelled``. A literal here rather than an import
from the persistence package, for the reason
:mod:`smartmatch_domain.attendance` gives about its own vocabulary: the layering
contract runs one way, persistence may read domain and never the reverse, so the
import could only go the wrong direction.

``waitlisted`` is the value a reader expects and it is deliberately absent.
A waitlist is overflow from a capacity, and no capacity exists anywhere in this
schema — ``event`` carries no seat count. A status no writer could legitimately
produce would be a vocabulary invented ahead of the decision that gives it
meaning, which is what migration ``0012`` refused to do for ``board_role``. It is
recorded as **OQ-CBA-029** rather than guessed at.

The two transitions are total, and that is what makes them idempotent
=======================================================================
:func:`registering` and :func:`cancelling` accept *any* current state, including
"no row yet" (``None``) and "already in the state you are asking for", and each
returns the state afterwards together with whether anything moved. Neither
raises.

That is deliberate, and it is the whole of this card's idempotency requirement.
A student who double-clicks Register has not made an error worth reporting;
their second click means exactly what their first one did. A student who cancels
a registration they never made is asking for a state they are already in.
Modelling either as an exception would push an API layer into answering ``409``
for a request whose *outcome* is the one the caller wanted — the failure mode
``routers/speaker_requests.py`` argues against at length when it explains why a
re-filed request is the same request rather than a conflict.

``changed`` exists so a caller can still tell the two apart where it matters:
migration ``0026``'s ``updated_at`` is "when the status last moved", and a
no-op re-registration must not move it, or a row would claim a transition that
never happened.

What this module deliberately does not decide
===============================================
* **Whether the caller may register at all.** That is the authorizer's, and it
  is unit-scoped and self-scoped — see ``routers/student_events.py``.
* **Whether the event is in the past.** Refusing a late registration is a
  product rule nobody has stated, and inventing one here would mean a student
  could not record that they had gone to something. If it is ever wanted it is a
  rule about ``event.resolved_date``, argued in the card that wants it.
* **Capacity.** See above; OQ-CBA-029.
* **Anything about points.** See above; ADR-0013.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

__all__ = [
    "REGISTRATION_STATUSES",
    "STATUS_CANCELLED",
    "STATUS_REGISTERED",
    "RegistrationTransition",
    "cancelling",
    "is_active",
    "registering",
]

#: ``event_registration.status`` — the student intends to attend.
STATUS_REGISTERED: Final[str] = "registered"

#: ``event_registration.status`` — they registered and then withdrew. A row, not
#: an absence: "they cancelled" and "they never registered" are different facts
#: and migration ``0026`` refuses to collapse them into one missing row.
STATUS_CANCELLED: Final[str] = "cancelled"

#: Both, mirroring ``ck_event_registration_status`` exactly. See the module
#: docstring on why ``waitlisted`` is not here.
REGISTRATION_STATUSES: Final[frozenset[str]] = frozenset({STATUS_REGISTERED, STATUS_CANCELLED})


@dataclass(frozen=True, slots=True)
class RegistrationTransition:
    """The state after a register or cancel, and whether it moved.

    Attributes:
        status: The status the row should hold afterwards. Always a member of
            :data:`REGISTRATION_STATUSES`; there is no transition in this module
            that produces anything else.
        changed: ``True`` when this call moved the row — a first registration, a
            cancellation of an active one, or a re-registration after a
            cancellation. ``False`` when the row was already in the requested
            state, or when a cancel found no row at all.

            A caller uses this for two things and should use it for both: to
            decide whether to write ``updated_at`` (migration ``0026`` defines it
            as "when the status last moved", so a no-op must not touch it), and
            to keep a response from claiming a transition that did not happen.
        created: ``True`` only when there was no row before this call. Distinct
            from ``changed``, which is also true of a re-registration that moved
            an existing cancelled row back. The register route needs the narrower
            fact to choose between ``201`` and ``200`` honestly.
    """

    status: str
    changed: bool
    created: bool


def is_active(status: str | None) -> bool:
    """Whether this status means the student currently holds a place.

    ``None`` — no row — is not active, and neither is ``cancelled``. Written as
    one function because several call sites would otherwise each spell out
    ``status == STATUS_REGISTERED``, and the day a third status exists they would
    each have to be found again.
    """
    return status == STATUS_REGISTERED


def registering(current: str | None) -> RegistrationTransition:
    """What registering does to a row currently in ``current``.

    Total and non-raising — see the module docstring. Three inputs, three
    answers:

    * ``None`` — no row yet. A new registration: ``changed`` and ``created``.
    * ``cancelled`` — they withdrew and have come back. The row moves to
      ``registered``; ``changed``, not ``created``, because migration ``0026``'s
      uniqueness on ``(tenant_id, subject_id, event_id)`` means there is exactly
      one row per student per event and this is still it. ``registered_at`` does
      not move either: it says when the place was first taken, which is what
      makes it able to say how late a subsequent cancellation was.
    * ``registered`` — already registered. Nothing moves, and that is a success:
      the caller asked for a state the row is in.

    Args:
        current: The row's status, or ``None`` when no row exists.

    Returns:
        The state afterwards. Never raises, including on a status this module
        does not recognise — an unknown value is treated as "not currently
        registered", so the transition repairs the row rather than refusing to
        act on it. ``ck_event_registration_status`` is what keeps an unknown
        value out in the first place; this function is not a second gate on the
        same question.
    """
    return RegistrationTransition(
        status=STATUS_REGISTERED,
        changed=not is_active(current),
        created=current is None,
    )


def cancelling(current: str | None) -> RegistrationTransition:
    """What cancelling does to a row currently in ``current``.

    Total and non-raising, for the same reason :func:`registering` is.

    * ``registered`` — the ordinary case. The row moves to ``cancelled`` and
      keeps its ``registered_at``.
    * ``cancelled`` — already cancelled. Nothing moves; a repeated cancel is the
      same cancel.
    * ``None`` — there is no row. ``changed`` is ``False`` and the reported
      status is ``cancelled``, which is what a caller should render, but a
      repository must **not** read this as an instruction to insert a
      pre-cancelled row. A student who never registered has no registration, and
      writing one to record that they did not want one would put a row in the
      table for every stray click. :attr:`RegistrationTransition.created` is
      ``False`` here and is the flag that says so.

    Args:
        current: The row's status, or ``None`` when no row exists.

    Returns:
        The state afterwards.
    """
    return RegistrationTransition(
        status=STATUS_CANCELLED,
        changed=is_active(current),
        created=False,
    )
