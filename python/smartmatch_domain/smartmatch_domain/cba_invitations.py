"""Speaker invitations: batching a reviewed shortlist, and what a Speaker said back.

Customer §6 steps 7-8 and §13: a Speaker Connector reviews a ranked shortlist,
"sends speaker invitations", may "batch-invite candidates where supported", and
then "tracks invitation responses/acceptances". §14 gives the Speaker the other
half — viewing an invitation and accepting or declining it.

This module owns three rules, and each exists because getting it wrong produces
a specific, nameable harm.

## 1. A delivery receipt is not a person agreeing to come

:class:`SpeakerResponse` and the provider's
:class:`~smartmatch_domain.outreach.SendDisposition` describe different facts
about different actors. The provider's ``accepted`` means *a mail system took
custody of some bytes*. A Speaker's acceptance means *a human being said they
will come and talk to students*. An Event Host who is handed the first as though
it were the second books a room for nobody.

So the two vocabularies are **disjoint by construction**, not merely by
convention: no value of :data:`SPEAKER_RESPONSE_VALUES` appears in
:data:`DELIVERY_VOCABULARY`, which is why a Speaker's acceptance is spelled
``accepted_invitation`` and never ``accepted``.
:func:`assert_response_vocabulary_is_disjoint_from_delivery` states the property
as an executable assertion rather than as this paragraph, so a later value added
to either enum fails a test instead of silently making the two words collide.
The two facts also live in different columns of different tables — the
disposition on ``outreach_send``, the response on ``cba_invitation`` — so there
is no field either could be read out of by accident.

## 2. A batch reports who it left out, and why

:class:`RecipientOutcome` is either an invitation or a skip carrying a
:class:`SkipReason`. A batch that quietly shrank from twelve names to nine would
tell a Connector that nine people were invited and nothing about the three, and
the three are exactly the ones that need a decision — a suppressed address, a
contact nobody activated, a person with no channel at all. Every requested
recipient produces an outcome, and the skips are stored, not merely returned, so
a replay of the same batch reports the same three.

## 3. Nothing here advances consent

:func:`classify_recipient` reads a channel's lifecycle facts and answers whether
an invitation may address it. It has no way to *change* them, and that is the
point: track 19 closed the invite-to-consent loophole, and an invitation that
could nudge a contact toward ``active_candidate`` in order to be sendable would
reopen it with extra steps. An ineligible recipient is skipped with a reason, and
the reason is a thing a human then acts on through the contact-channel surface.

The eligibility question itself is not re-answered here: it is
``smartmatch_domain.consent.is_send_eligible``'s, asked once, with this module
adding only *which* of its three conditions failed so the skip can say so.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Protocol, TypeVar

from smartmatch_domain.consent import (
    ConsentSource,
    ContactState,
    is_send_eligible,
)
from smartmatch_domain.outreach import DeliveryEventType, SendDisposition

__all__ = [
    "DELIVERY_VOCABULARY",
    "INVITATION_TEMPLATE_ID",
    "MAX_BATCH_RECIPIENTS",
    "SPEAKER_RESPONSE_VALUES",
    "ChannelFacts",
    "InvitationResponseConflict",
    "InvitationStatus",
    "RecipientOutcome",
    "SkipReason",
    "SpeakerResponse",
    "assert_response_vocabulary_is_disjoint_from_delivery",
    "choose_invitation_channel",
    "classify_recipient",
    "record_response",
]


#: The one template a batch invitation composes from. Named here rather than
#: taken from the caller: "which words does an invitation use" is a decision
#: about copy, and the closed registry in ``smartmatch_domain.outreach`` is where
#: copy decisions are recorded. A caller choosing a template per batch would be a
#: caller choosing what the institution says.
INVITATION_TEMPLATE_ID: Final[str] = "cba.speaker_invitation.v1"

#: Most recipients one batch may name. §6 puts a shortlist at "approximately 2-3
#: speaker candidates", so this is not a capacity ceiling — it is far above the
#: shortlist — but it is the point past which a mistake stops being a handful of
#: messages somebody can review and starts being a list. Bounded here rather than
#: only at the route, for ``MAX_DRAFT_PAGE_SIZE``'s reason: a bound that lives in
#: a route stops applying the moment a second caller appears.
MAX_BATCH_RECIPIENTS: Final[int] = 25


class SpeakerResponse(StrEnum):
    """What the Speaker themselves said. **Never what a mail provider did.**

    Read the values: every one of them names the invitation, because the whole
    hazard this enum exists to prevent is a reader seeing ``accepted`` and not
    knowing which of two entirely different actors accepted what. See the module
    docstring, and :data:`DELIVERY_VOCABULARY` for the set these may not touch.
    """

    #: The invitation exists and the Speaker has not answered it. A real state,
    #: not a missing value: an unanswered invitation is the ordinary condition of
    #: every invitation for as long as it takes somebody to read their mail, and
    #: rendering it as a failure is the same defect as rendering a null
    #: disposition as one.
    AWAITING_RESPONSE = "awaiting_response"
    #: A human being agreed to speak.
    ACCEPTED_INVITATION = "accepted_invitation"
    #: A human being declined.
    DECLINED_INVITATION = "declined_invitation"


#: Every value :class:`SpeakerResponse` can take.
SPEAKER_RESPONSE_VALUES: Final[frozenset[str]] = frozenset(
    response.value for response in SpeakerResponse
)

#: Every word the *delivery* side of the system uses to describe what happened to
#: a message. Derived from the two enums that own those words rather than typed
#: out, so it cannot fall behind them: a new disposition or delivery event
#: automatically joins the set that :data:`SPEAKER_RESPONSE_VALUES` may not
#: intersect.
DELIVERY_VOCABULARY: Final[frozenset[str]] = frozenset(
    {disposition.value for disposition in SendDisposition}
    | {event.value for event in DeliveryEventType}
)


def assert_response_vocabulary_is_disjoint_from_delivery() -> None:
    """Raise if a Speaker's answer could ever be spelled like a delivery outcome.

    The module's first rule, made executable. Called by the tests and cheap
    enough to call anywhere; what matters is that the property is checked by
    something rather than asserted by a comment. A collision here would be a
    system in which "accepted" has two meanings and no reader can tell which one
    a given column holds.

    Raises:
        AssertionError: naming the colliding values.
    """
    collisions = SPEAKER_RESPONSE_VALUES & DELIVERY_VOCABULARY
    if collisions:  # pragma: no cover - the assertion is the product
        raise AssertionError(
            f"a Speaker's response and a delivery outcome share the value(s) "
            f"{sorted(collisions)}. A provider taking custody of bytes is not a "
            "person agreeing to speak, and the two must not be spellable alike."
        )


class InvitationStatus(StrEnum):
    """Where one requested recipient got to. Says nothing about the Speaker."""

    #: An invitation was composed and stored, and no send has been submitted.
    PENDING = "pending"
    #: A send command has been submitted for it. Whether a message was actually
    #: delivered is the ``outreach_send`` row's ``disposition`` to answer, and
    #: this value deliberately does not guess at it.
    DISPATCHED = "dispatched"
    #: The recipient was named and not invited. Carries a :class:`SkipReason`.
    SKIPPED = "skipped"


class SkipReason(StrEnum):
    """Why a named recipient produced no invitation.

    Every value is a fact about the recipient that a Connector can act on, and
    none of them is "an error occurred". A batch that answered "3 skipped" would
    be answering a question nobody asked; what a Connector needs is *which three
    and what to do about each*.
    """

    #: The id names nobody on this unit's §13 roster.
    NOT_ON_ROSTER = "not_on_roster"
    #: The person is on the roster and this unit holds no address for them. The
    #: ordinary case for a contact added through the §13 form, which writes no
    #: channel at all (OQ-CBA-011).
    NO_CONTACT_CHANNEL = "no_contact_channel"
    #: An address exists and somebody has told us to stop writing to it. Outranks
    #: every consent record and lifecycle state (v1.1 §1.8).
    CHANNEL_SUPPRESSED = "channel_suppressed"
    #: An address exists, is not suppressed, and nobody has activated it. The fix
    #: is a lifecycle transition made by a person, never by this batch.
    CHANNEL_NOT_ACTIVE_CANDIDATE = "channel_not_active_candidate"
    #: The channel is active but the consent behind it came from a source that
    #: can never authorize a send — scraped, purchased, inferred.
    CONSENT_SOURCE_NOT_APPROVED = "consent_source_not_approved"
    #: The same recipient was named twice in one request. Reported rather than
    #: silently folded, so the count a Connector sees matches the list they sent.
    DUPLICATE_IN_REQUEST = "duplicate_in_request"
    #: This batch was replayed under its original idempotency key and this
    #: recipient already holds an invitation from the first submission. Not an
    #: error and not a second invitation — see the batch route.
    ALREADY_INVITED = "already_invited"


class InvitationResponseConflict(ValueError):
    """A second, different answer arrived for an invitation already answered.

    Not a ``PermissionError``: the caller is entitled to answer, and the
    invitation is in a state where a *different* answer would overwrite a
    recorded fact about a person. Recorded as OQ-CBA-044 — whether a Speaker may
    change their mind is a product question, and the fail-closed reading until
    somebody answers it is that the first answer stands.
    """


class ChannelFacts(Protocol):
    """The three fields eligibility is decided from, however they were loaded.

    A protocol rather than an import of
    :class:`~smartmatch_persistence.contacts.ContactChannelRow`, because the
    domain layer may not reach into persistence — and because more than one row
    type carries these same three facts. Structural typing is what lets one rule
    serve every such caller without any of them converting anything.
    """

    @property
    def contact_state(self) -> str: ...

    @property
    def consent_source(self) -> str | None: ...

    @property
    def suppressed(self) -> bool: ...


#: Bound to the protocol so :func:`choose_invitation_channel` hands back the
#: caller's own row type rather than a widened one — a route that receives a
#: ``ContactChannelRow`` still needs its ``id`` and ``address``, which the
#: protocol deliberately does not declare.
ChannelT = TypeVar("ChannelT", bound=ChannelFacts)


@dataclass(frozen=True, slots=True)
class RecipientOutcome:
    """What one named recipient produced: an invitation, or a reason it did not.

    Both halves in one type rather than two lists assembled separately, so a
    recipient cannot fall out of both. ``skip_reason`` is set exactly when
    ``eligible`` is false, which ``__post_init__`` refuses to let drift.

    Attributes:
        professional_id: The recipient as the caller named them, echoed back so a
            partial outcome can be matched to the request that produced it.
        eligible: Whether an invitation may be composed for this person now.
        skip_reason: Why not, when not. ``None`` when ``eligible``.
    """

    professional_id: str
    eligible: bool
    skip_reason: SkipReason | None = None

    def __post_init__(self) -> None:
        if self.eligible and self.skip_reason is not None:
            raise ValueError("an eligible recipient cannot carry a skip reason")
        if not self.eligible and self.skip_reason is None:
            raise ValueError(
                "a skipped recipient must say why. A skip with no reason is the "
                "silent shrink this type exists to make impossible."
            )


def classify_recipient(channel: ChannelFacts) -> SkipReason | None:
    """Return why this channel may not be invited, or ``None`` when it may.

    The verdict is ``smartmatch_domain.consent.is_send_eligible``'s and is asked
    first, so this function cannot admit a channel the send gate would refuse.
    Everything after that call exists only to name *which* condition failed, in
    the order suppression → activation → source that
    :func:`~smartmatch_domain.consent.assert_send_eligible` uses, because
    suppression outranks the other two and a person who has said stop should be
    reported as such rather than as an un-activated contact.

    Args:
        channel: The channel's stored lifecycle facts, with its live suppression.

    Returns:
        ``None`` when an invitation may address this channel, otherwise the
        :class:`SkipReason` a Connector can act on.
    """
    state = ContactState(channel.contact_state)
    source = ConsentSource(channel.consent_source) if channel.consent_source is not None else None

    if is_send_eligible(state, consent_source=source, suppressed=channel.suppressed):
        return None

    if channel.suppressed:
        return SkipReason.CHANNEL_SUPPRESSED
    if state is not ContactState.ACTIVE_CANDIDATE:
        return SkipReason.CHANNEL_NOT_ACTIVE_CANDIDATE
    return SkipReason.CONSENT_SOURCE_NOT_APPROVED


#: How actionable each refusal is, lowest first. Used only to decide which of
#: several ineligible channels a Connector is pointed at: a person whose consent
#: source is wrong is one conversation away from being invitable, an un-activated
#: contact is one review away, and a suppression is not a step on the way to
#: anything and so is reported last.
_SKIP_SEVERITY: Final[dict[SkipReason, int]] = {
    SkipReason.CONSENT_SOURCE_NOT_APPROVED: 0,
    SkipReason.CHANNEL_NOT_ACTIVE_CANDIDATE: 1,
    SkipReason.CHANNEL_SUPPRESSED: 2,
}


def choose_invitation_channel(
    channels: Sequence[ChannelT],
) -> tuple[ChannelT | None, SkipReason | None]:
    """Pick the one channel an invitation should address, or say why none serves.

    A person may hold several channels — an address recorded during research and
    a second one they consented on — and only some of them may be written to. So
    the choice is not "the newest" or "the first": it is *an eligible one*, and
    when none is eligible the reason reported is the reason of the channel that
    came closest, which is the one a Connector should look at.

    Args:
        channels: Every channel this unit holds for one person. May be empty.

    Returns:
        ``(channel, None)`` when one may be invited, otherwise
        ``(None, reason)``. Never both, and never neither.
    """
    if not channels:
        return None, SkipReason.NO_CONTACT_CHANNEL

    reasons: list[SkipReason] = []
    for channel in channels:
        reason = classify_recipient(channel)
        if reason is None:
            return channel, None
        reasons.append(reason)

    return None, min(reasons, key=lambda reason: _SKIP_SEVERITY.get(reason, 99))


def record_response(
    current: SpeakerResponse, requested: SpeakerResponse
) -> tuple[SpeakerResponse, bool]:
    """Apply a Speaker's answer to an invitation, or refuse to overwrite one.

    Three cases, and the third is the one worth stating:

    * Unanswered, and an answer arrives — it is recorded.
    * Answered, and the *same* answer arrives again — nothing is written and the
      call succeeds. A Speaker clicking a link twice, or a mail client
      prefetching it, has not made an error, and showing them one would be
      alarming for no reason. This is ``suppress``'s posture on the unsubscribe
      path, for the same reason.
    * Answered, and a *different* answer arrives — refused. Overwriting
      ``accepted_invitation`` with ``declined_invitation`` erases a fact an Event
      Host may already have acted on by booking a room, and whether a Speaker may
      change their mind through this path is OQ-CBA-044, which nobody has
      answered. Fail closed until they do.

    Args:
        current: What is recorded now.
        requested: What is being recorded. ``AWAITING_RESPONSE`` is not an answer
            and is refused outright — "un-answering" an invitation is not a thing
            a Speaker can do, and offering it would be a way to clear a decline.

    Returns:
        ``(state, changed)``. ``changed`` is false for the idempotent repeat, so
        a caller can skip the write and the timestamp rather than redating an
        answer given earlier.

    Raises:
        InvitationResponseConflict: on a different second answer, or on an
            attempt to move back to ``AWAITING_RESPONSE``.
    """
    if requested is SpeakerResponse.AWAITING_RESPONSE:
        raise InvitationResponseConflict(
            "'awaiting_response' is the state an invitation starts in, not an "
            "answer a Speaker can give. There is no way to un-answer an "
            "invitation, because clearing a decline is indistinguishable from "
            "never having received one."
        )

    if current is SpeakerResponse.AWAITING_RESPONSE:
        return requested, True

    if current is requested:
        return current, False

    raise InvitationResponseConflict(
        f"this invitation is already {current.value!r} and cannot be changed to "
        f"{requested.value!r}. An Event Host may already have acted on the first "
        "answer; whether a Speaker may change their mind is OQ-CBA-044."
    )
