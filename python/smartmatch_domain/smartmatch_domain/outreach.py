"""Outreach composition, the draft lifecycle, and the send-time re-check (R4, G4).

This module is what ``outreach_dryrun.py`` was a rehearsal for. The rehearsal's
central claim — *the gate runs before any message text exists* — is unchanged
and still implemented here; what changes is that a composed draft is now
allowed to become a real send, through the durable command path, against a
provider adapter the domain layer still cannot see.

## What moved, and what deliberately did not

The template registry, the renderer, and the eligibility-gated composition live
here now. ``outreach_dryrun.py`` re-exports them and adds nothing, so there is
exactly **one** implementation of the eligibility rules in the codebase rather
than a dry-run copy that drifts from the send copy. A second copy would be the
worst possible place for a divergence: the dry run is what a coordinator is
shown before approving, and if it applied a different rule than the send did,
the approval would be for a decision that never got made.

What did not move is the rule itself. Everything about *who may be contacted*
is still :mod:`smartmatch_domain.consent`'s, and this module calls it rather
than restating it. Search this file for the list of approved consent sources
and you will not find one.

## Three checks, at three different times, and none of them is redundant

1. :func:`compose_draft` calls
   :func:`~smartmatch_domain.consent.assert_send_eligible` **before rendering**.
   An ineligible recipient never has a message composed about them.
2. :func:`assert_draft_transition` gates approval. A draft that was never
   approved, or that has been superseded by a later revision, cannot be sent
   even if its recipient is perfectly eligible.
3. :func:`assert_send_allowed` runs at **delivery time**, in the worker,
   against state read fresh from the database.

The third is the one that looks redundant and is not. A durable command can sit
in a queue for minutes; ``smartmatch_worker.handlers.CommandContext`` says
exactly this about its own job payload — "a task can sit in the queue while
consent, budget, or approval change, so the delivery is treated as a
notification that work exists, never as a description of it". Consent withdrawn
after a draft is approved and before it is sent is not an edge case, it is the
normal operation of an unsubscribe link. A draft is a record that someone
*intended* to send; it is never a standing permission to send later.

## Live mode, and why a template can be composable but not sendable

:class:`ContentStatus` splits "this template renders" from "a lawyer has read
it". The shipped templates are :attr:`ContentStatus.SYNTHETIC`: they compose,
they store, they send through the fixture provider, and
:func:`assert_send_allowed` refuses them when ``live_mode`` is true. That is
what lets the pilot exercise this entire path end to end without anyone being
able to put unreviewed copy in front of a real recipient (OQ-003 in
``docs/plans/open-questions/r4-outreach-deferred.md``).

The check is a positive one — live mode requires ``REVIEWED`` — rather than a
list of statuses to refuse. A status added later is therefore refused by
default in live mode, which is the direction an unknown should fail in.

## Still no invite-to-consent, and still no way to leave

``consent.py``'s rationale is unchanged and load-bearing: *"an email asking a
scraped address to opt in is itself prohibited outreach"*. So the registry
below is closed, every entry declares ``presumes_existing_consent``, and adding
an entry that solicits consent would break a test rather than merely be
regrettable. Making the registry writable, or accepting free-form body text
from a caller, would each reopen that hole by a different door; neither is
offered.

## Domain purity

Nothing here imports ``os``, ``socket``, ``httpx``, ``requests``, or
``smartmatch_providers``, and the import-linter contract "Domain is pure" in the
root ``pyproject.toml`` is what makes that a guarantee rather than a habit. This
module decides *whether* a message may be sent and *what it says*; the worker
builds the ``SendRequest`` and the adapter performs the send, and the boundary
between those two facts is the reason a composition bug cannot become an
accidental delivery.
"""

from __future__ import annotations

import string
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from smartmatch_domain.consent import (
    APPROVED_CONSENT_SOURCES,
    ConsentSource,
    ConsentViolationError,
    ContactState,
    assert_send_eligible,
)

__all__ = [
    "DRAFT_STATE_TRANSITIONS",
    "DRY_RUN_DISPOSITION",
    "ELIGIBILITY_RULE",
    "MAX_RENDERED_BODY_CHARS",
    "MAX_RENDERED_SUBJECT_CHARS",
    "OUTREACH_SEND_COMMAND_TYPE",
    "RESERVED_INVALID_SUFFIX",
    "TEMPLATES",
    "ComposedDraft",
    "ContentStatus",
    "DeliveryEventType",
    "DraftRecipient",
    "DraftStatus",
    "EligibilityEvidence",
    "OutreachCompositionError",
    "OutreachDraftStateError",
    "OutreachTemplate",
    "SendDisposition",
    "assert_draft_transition",
    "assert_send_allowed",
    "can_transition_draft",
    "compose_draft",
    "get_template",
]

#: The durable command type the API submits and the worker routes. A constant
#: rather than a literal in two files, for the same reason
#: ``MATCH_RUN_COMMAND_TYPE`` is one: the router and the registry must agree,
#: and a typo in either would produce a job nothing can execute.
OUTREACH_SEND_COMMAND_TYPE: Final[str] = "outreach.send"

#: The dotted name of the consent check every composition and every send was
#: gated by, recorded on the evidence so an audit reads the rule rather than
#: trusting the caller.
ELIGIBILITY_RULE: Final[str] = "smartmatch_domain.consent.assert_send_eligible"

#: Retained for ``outreach_dryrun.compose_dry_run``, whose result must keep
#: saying ``"would_send"``. Nothing on the send path uses it — see
#: :class:`SendDisposition` for what a real send reports.
DRY_RUN_DISPOSITION: Final[str] = "would_send"

#: Reserved TLD (RFC 2606) used by every synthetic pilot address. Recorded as
#: evidence, never used as a gate: a real-looking address is not thereby
#: eligible, and a reserved one is not thereby exempt from consent.
RESERVED_INVALID_SUFFIX: Final[str] = ".invalid"

#: Bounds on what composition may produce. Not deliverability tuning — a bound
#: that exists so a template plus caller-supplied values cannot render into
#: something the storage layer must either truncate or refuse *after* the
#: recipient has already been told their message was drafted. Refusing at
#: composition time means the failure names the template, not a column.
MAX_RENDERED_SUBJECT_CHARS: Final[int] = 200
MAX_RENDERED_BODY_CHARS: Final[int] = 20_000


class OutreachCompositionError(ValueError):
    """Raised when a message cannot be composed from the inputs given.

    A ``ValueError``, unlike
    :class:`~smartmatch_domain.consent.ConsentViolationError`: this is a
    malformed request, not an authorization failure. The two are deliberately
    distinct so a caller can never treat a blocked send as a typo — and so the
    API can map one to a 400 and the other to a terminal policy refusal without
    inspecting a message string.
    """


class OutreachDraftStateError(ValueError):
    """Raised when a draft is moved between states in a way the lifecycle forbids.

    Separate from :class:`OutreachCompositionError` because it answers a
    different question. A composition error says the inputs were wrong; this
    says the inputs were fine and the draft is not in a state where the
    operation means anything — approving an already-superseded draft, say.
    """


class DraftStatus(StrEnum):
    """Where a draft sits in its approval lifecycle.

    Deliberately three states and not four. There is no ``sent``: a draft is
    not consumed by being sent, because a send is a separate row with its own
    lifecycle (``outreach_send``), and collapsing the two would make "this
    draft was approved" and "this draft was delivered" the same fact. They are
    not — a send can fail at the provider while the approval remains perfectly
    valid, and re-driving it must not require re-approval.
    """

    #: Composed, editable, not sendable.
    DRAFT = "draft"
    #: A named actor approved this exact rendered text. Sendable.
    APPROVED = "approved"
    #: Replaced by a later revision. Terminal, and never sendable again.
    SUPERSEDED = "superseded"


class ContentStatus(StrEnum):
    """Whether a template's copy has been through legal review.

    Orthogonal to :class:`DraftStatus` on purpose: a coordinator approving a
    draft is approving *this message to this person*, which is not the same act
    as an institution approving the standing wording of a template. Conflating
    them would let a coordinator's click stand in for a review they have no
    standing to perform.
    """

    #: Pilot copy. Composes and sends against the fixture provider; refused in
    #: live mode. See OQ-003.
    SYNTHETIC = "synthetic"
    #: Reviewed for a named institution. No shipped template is this yet.
    REVIEWED = "reviewed"


class DeliveryEventType(StrEnum):
    """The vocabulary of the append-only delivery stream (v1.1 §1.8).

    Delivery status is a **projection over these events**, never a flag on the
    send row. The distinction matters because the events are not ordered by
    anything we control: a provider can report ``delivered`` and then
    ``complained`` hours later, and a boolean column would have to choose which
    one to forget.

    ``blocked`` is ours rather than a provider's: it records a send the worker
    refused at the last moment — withdrawn consent, a suppression — so that a
    refusal leaves the same kind of trace an acceptance does. A refusal that
    wrote nothing would be indistinguishable from a send that never happened.
    """

    QUEUED = "queued"
    BLOCKED = "blocked"
    ACCEPTED = "accepted"
    DELIVERED = "delivered"
    BOUNCED = "bounced"
    COMPLAINED = "complained"
    UNSUBSCRIBED = "unsubscribed"
    FAILED = "failed"


class SendDisposition(StrEnum):
    """What a send attempt concluded, as the worker reports it.

    Note what is absent: anything meaning "delivered". The provider's
    acknowledgement is :attr:`ACCEPTED` — it accepted custody of the message —
    and delivery is a later event that may never arrive. ``SendResult``'s own
    docstring makes the same point: *"a provider message id only means the
    provider accepted the message"*. A disposition of ``sent`` would quietly
    promise more than any adapter can know.
    """

    #: The provider took custody. The only success value.
    ACCEPTED = "accepted"
    #: A gate refused at delivery time. Terminal; re-driving would refuse again.
    BLOCKED = "blocked"
    #: The provider failed. May succeed on a re-drive.
    FAILED = "failed"


#: Legal moves in the draft lifecycle. Written in the shape of
#: ``consent.STATE_TRANSITIONS`` so a reader who has understood one has
#: understood both.
#:
#: ``APPROVED -> SUPERSEDED`` exists and ``SUPERSEDED -> anything`` does not:
#: an approved draft may be replaced by a revision, and a superseded one is
#: finished. There is deliberately no ``APPROVED -> DRAFT`` edge — "un-approving"
#: by editing would let the text change under an approval that still reads as
#: current, and the whole point of pinning an approval to rendered text is that
#: the text cannot move afterwards. A correction is a new draft that supersedes
#: this one, exactly as a corrected match run is a new run (migration ``0018``).
DRAFT_STATE_TRANSITIONS: Final[Mapping[DraftStatus, frozenset[DraftStatus]]] = MappingProxyType(
    {
        DraftStatus.DRAFT: frozenset({DraftStatus.APPROVED, DraftStatus.SUPERSEDED}),
        DraftStatus.APPROVED: frozenset({DraftStatus.SUPERSEDED}),
        DraftStatus.SUPERSEDED: frozenset(),
    }
)


@dataclass(frozen=True, slots=True)
class OutreachTemplate:
    """One composable message shape.

    Attributes:
        template_id: Stable identifier, recorded on every draft.
        subject: ``string.Template`` source for the subject line.
        body: ``string.Template`` source for the plain-text body.
        placeholders: Exactly the names ``subject`` and ``body`` between them
            require. Declared rather than derived, so a template whose text and
            whose contract disagree is caught by a test instead of by a
            half-rendered message.
        content_status: Whether this copy has been reviewed. See
            :class:`ContentStatus`.
        presumes_existing_consent: Always ``True``. Present as an explicit,
            assertable field rather than as a comment, so "no template solicits
            consent" is a property of the data a test can read.
    """

    template_id: str
    subject: str
    body: str
    placeholders: frozenset[str]
    content_status: ContentStatus = ContentStatus.SYNTHETIC
    presumes_existing_consent: bool = True


def _template(
    template_id: str, *, subject: str, body: str, placeholders: frozenset[str]
) -> OutreachTemplate:
    return OutreachTemplate(
        template_id=template_id, subject=subject, body=body, placeholders=placeholders
    )


#: Placeholders every shipped template takes. One set, so the templates cannot
#: drift into subtly different call contracts.
_PILOT_PLACEHOLDERS: Final[frozenset[str]] = frozenset(
    {
        "professional_name",
        "unit_name",
        "event_name",
        "event_date",
        "coordinator_name",
    }
)

#: The invitation template's contract: the five above plus the one thing an
#: invitation needs that no other message does — somewhere for the recipient to
#: answer. Derived from ``_PILOT_PLACEHOLDERS`` rather than typed out, so the
#: five shared names cannot drift apart between templates.
#:
#: ``response_url`` is **server-composed**, never a caller's string. A route that
#: accepted a URL here would be accepting an arbitrary link to put in an
#: institutional email over an already-consented address, which is a phishing
#: primitive rather than a placeholder; ``routers/cba_invitations.py`` builds it
#: from the configured public origin and the invitation's own token.
_INVITATION_PLACEHOLDERS: Final[frozenset[str]] = _PILOT_PLACEHOLDERS | {"response_url"}

#: The closed set of templates. Every entry addresses someone who has *already*
#: consented through an approved source; none asks anyone to opt in.
#:
#: A ``MappingProxyType`` rather than a dict, so a caller cannot add an entry at
#: runtime. That is not paranoia about a malicious caller — it is that a
#: registry mutable from application code is a registry whose contents depend on
#: what has run, and "which messages can this system compose" must be answerable
#: by reading this file.
TEMPLATES: Final[Mapping[str, OutreachTemplate]] = MappingProxyType(
    {
        template.template_id: template
        for template in (
            _template(
                "pilot.event_invitation.v1",
                subject="$event_name on $event_date",
                body=(
                    "Hello $professional_name,\n\n"
                    "$unit_name is hosting $event_name on $event_date, and you are "
                    "on the list of professionals who agreed to hear about "
                    "opportunities like it.\n\n"
                    "$coordinator_name\n"
                ),
                placeholders=_PILOT_PLACEHOLDERS,
            ),
            _template(
                "pilot.visit_confirmation.v1",
                subject="Confirming $event_name on $event_date",
                body=(
                    "Hello $professional_name,\n\n"
                    "Confirming your visit to $unit_name for $event_name on "
                    "$event_date.\n\n"
                    "$coordinator_name\n"
                ),
                placeholders=_PILOT_PLACEHOLDERS,
            ),
            # Third template, added with this slice. Not a new *kind* of
            # message: it addresses the same already-consented professional
            # about the same already-agreed visit, and says the event moved.
            # Worth having because a schedule change is the one message a
            # coordinator will certainly need to send during the pilot, and the
            # alternative to a template is free-form body text — which is the
            # one door back to unreviewed copy this module does not open.
            _template(
                "pilot.schedule_change.v1",
                subject="Updated: $event_name is now $event_date",
                body=(
                    "Hello $professional_name,\n\n"
                    "$event_name at $unit_name has moved. The new date is "
                    "$event_date. Nothing else about your visit has changed, and "
                    "you do not need to do anything to confirm.\n\n"
                    "$coordinator_name\n"
                ),
                placeholders=_PILOT_PLACEHOLDERS,
            ),
            # Fourth template, added by CBA-INVITATIONS for customer §6 step 7
            # and §13's "send speaker invitations". Like the other three it
            # addresses somebody who is already an `active_candidate` with an
            # approved source — it asks a professional who agreed to hear about
            # opportunities whether they will take *this* one, which is the
            # thing they agreed to be asked.
            #
            # What makes it a distinct template rather than a reuse of
            # `pilot.event_invitation.v1`: this one carries a way to answer. An
            # invitation with no answer path is a message that produces replies
            # into a mailbox nobody reads, which is how "track speaker
            # responses" degenerates into a coordinator retyping what they were
            # told on the phone.
            _template(
                "cba.speaker_invitation.v1",
                subject="Invitation to speak at $event_name on $event_date",
                body=(
                    "Hello $professional_name,\n\n"
                    "$unit_name is hosting $event_name on $event_date, and "
                    "$coordinator_name would like to invite you to speak with "
                    "our students.\n\n"
                    "You can accept or decline here: $response_url\n\n"
                    "If neither suits you, you can simply ignore this message.\n\n"
                    "$coordinator_name\n"
                ),
                placeholders=_INVITATION_PLACEHOLDERS,
            ),
        )
    }
)


@dataclass(frozen=True, slots=True)
class DraftRecipient:
    """The consent-relevant facts about one addressee.

    Every field is required. There is no default for ``consent_source`` or
    ``suppressed``: an unknown consent source is not an approved one, and an
    unknown suppression is not "not suppressed" (ADR-0011 — unknown is never
    silently zero).

    Note what this type does *not* carry: a name, a professional id, or
    anything else about the person. It is the consent record's shape, not the
    contact's, because the only question anything in this module asks about a
    recipient is whether they may be written to.
    """

    address: str
    contact_state: ContactState
    consent_source: ConsentSource | None
    suppressed: bool


@dataclass(frozen=True, slots=True)
class EligibilityEvidence:
    """Why this recipient was judged send-eligible, recorded with the result.

    The point is auditability: a result carries the facts the decision was made
    from, so a reviewer can re-derive the decision without rerunning anything —
    and, more usefully, so a reviewer looking at a send that should not have
    happened can see what the system believed at the time rather than what the
    database says now.
    """

    contact_state: ContactState
    consent_source: ConsentSource
    consent_source_is_approved: bool
    suppressed: bool
    checked_by: str = ELIGIBILITY_RULE


@dataclass(frozen=True, slots=True)
class ComposedDraft:
    """A rendered message and the proof its recipient could be written to.

    Not a send, and not a promise of one. This is what a coordinator reviews
    and approves; whether it is ever delivered depends on three later things —
    an approval, a durable command, and the worker's own re-check — none of
    which this object can speak for.

    Attributes:
        recipient_address: Where it would go.
        template_id: Which entry of :data:`TEMPLATES` produced it.
        content_status: The template's review status, copied onto the draft so
            a stored draft carries it without a lookup back into the registry.
            A template's status could change; what was composed did not.
        subject: Rendered subject line.
        body: Rendered plain-text body.
        evidence: The eligibility facts this composition was gated by.
        recipient_address_is_reserved_invalid: Whether the address is in the
            RFC 2606 reserved space. Recorded, never a gate — see
            :data:`RESERVED_INVALID_SUFFIX`.
    """

    recipient_address: str
    template_id: str
    content_status: ContentStatus
    subject: str
    body: str
    evidence: EligibilityEvidence
    recipient_address_is_reserved_invalid: bool


def get_template(template_id: str) -> OutreachTemplate:
    """Return the named template.

    Raises:
        OutreachCompositionError: if ``template_id`` is not in the closed
            :data:`TEMPLATES` registry. Unknown ids are refused rather than
            treated as free-form text, so no caller can compose a message this
            module has not reviewed.
    """
    template = TEMPLATES.get(template_id)
    if template is None:
        raise OutreachCompositionError(
            f"unknown outreach template {template_id!r}; known templates are {sorted(TEMPLATES)}"
        )
    return template


def _render(source: str, values: Mapping[str, str]) -> str:
    """Substitute ``$name`` placeholders, refusing anything left unresolved.

    ``substitute`` rather than ``safe_substitute``, deliberately: the safe
    variant leaves an unresolved ``$placeholder`` in the output, which would
    reach a recipient as literal template syntax. A message that renders
    partially is worse than one that refuses to render at all.
    """
    try:
        return string.Template(source).substitute(values)
    except (KeyError, ValueError) as exc:
        raise OutreachCompositionError(f"could not render template text: {exc}") from exc


def _validated_values(template: OutreachTemplate, values: Mapping[str, str]) -> Mapping[str, str]:
    """Return ``values`` iff it is exactly the template's declared placeholders.

    Exactly, not "at least": an unexpected key is refused rather than ignored,
    because a caller supplying ``coordinator`` when the template wants
    ``coordinator_name`` has made a mistake that silence would turn into a
    missing-placeholder error one layer down, naming the wrong thing.
    """
    supplied = frozenset(values)
    missing = template.placeholders - supplied
    unexpected = supplied - template.placeholders
    if missing or unexpected:
        raise OutreachCompositionError(
            f"template {template.template_id!r} takes {sorted(template.placeholders)}; "
            f"missing {sorted(missing)}, unexpected {sorted(unexpected)}"
        )
    return values


def _assert_within_bounds(subject: str, body: str, template_id: str) -> None:
    """Refuse a rendering that exceeds what storage and transport will take."""
    if len(subject) > MAX_RENDERED_SUBJECT_CHARS:
        raise OutreachCompositionError(
            f"template {template_id!r} rendered a subject of {len(subject)} characters; "
            f"the limit is {MAX_RENDERED_SUBJECT_CHARS}."
        )
    if len(body) > MAX_RENDERED_BODY_CHARS:
        raise OutreachCompositionError(
            f"template {template_id!r} rendered a body of {len(body)} characters; "
            f"the limit is {MAX_RENDERED_BODY_CHARS}."
        )


def compose_draft(
    *,
    recipient: DraftRecipient,
    template_id: str,
    values: Mapping[str, str],
) -> ComposedDraft:
    """Compose the message intended for ``recipient``, and send nothing.

    The consent gate runs first, before any message text exists, so an
    ineligible recipient never has a body composed about them. That ordering is
    the point of this function and not an implementation detail: composing
    first and checking after would leave rendered text about a person who never
    agreed to be written to sitting in a log, a traceback, or an error
    response.

    Args:
        recipient: The addressee's consent-relevant facts.
        template_id: A key of the closed :data:`TEMPLATES` registry.
        values: Exactly the template's declared placeholders.

    Returns:
        A :class:`ComposedDraft`. Composing does not create a draft *record* —
        that is the persistence layer's job — and it does not approve one.

    Raises:
        ConsentViolationError: if the recipient is not send-eligible. Raised by
            :func:`~smartmatch_domain.consent.assert_send_eligible`, which owns
            this rule; this module does not restate it.
        OutreachCompositionError: if the template is unknown, the placeholder
            values do not match it exactly, or the rendering exceeds its bounds.
    """
    assert_send_eligible(
        recipient.contact_state,
        consent_source=recipient.consent_source,
        suppressed=recipient.suppressed,
    )
    consent_source = recipient.consent_source
    if consent_source is None:  # pragma: no cover - assert_send_eligible refuses None
        raise OutreachCompositionError("send-eligible recipient without a consent source")

    template = get_template(template_id)
    checked_values = _validated_values(template, values)

    subject = _render(template.subject, checked_values)
    body = _render(template.body, checked_values)
    _assert_within_bounds(subject, body, template.template_id)

    return ComposedDraft(
        recipient_address=recipient.address,
        template_id=template.template_id,
        content_status=template.content_status,
        subject=subject,
        body=body,
        evidence=EligibilityEvidence(
            contact_state=recipient.contact_state,
            consent_source=consent_source,
            consent_source_is_approved=consent_source in APPROVED_CONSENT_SOURCES,
            suppressed=recipient.suppressed,
        ),
        recipient_address_is_reserved_invalid=recipient.address.endswith(RESERVED_INVALID_SUFFIX),
    )


def can_transition_draft(current: DraftStatus, requested: DraftStatus) -> bool:
    """Return whether ``current -> requested`` is a legal draft lifecycle move."""
    return requested in DRAFT_STATE_TRANSITIONS[current]


def assert_draft_transition(current: DraftStatus, requested: DraftStatus) -> None:
    """Raise unless the draft lifecycle transition is legal.

    Raises:
        OutreachDraftStateError: naming the legal moves from ``current``, so a
            caller is told what it could have done rather than only that it was
            wrong.
    """
    if not can_transition_draft(current, requested):
        allowed = sorted(s.value for s in DRAFT_STATE_TRANSITIONS[current])
        raise OutreachDraftStateError(
            f"illegal draft transition {current.value!r} -> {requested.value!r}; "
            f"legal moves are {allowed or ['(terminal)']}"
        )


def assert_send_allowed(
    *,
    recipient: DraftRecipient,
    draft_status: DraftStatus,
    content_status: ContentStatus,
    live_mode: bool,
) -> None:
    """Raise unless this draft may be delivered to this recipient, right now.

    The worker's gate, called at delivery time against state read fresh from the
    database rather than against anything carried on the job payload. Four
    conditions, in an order chosen so the most consequential failure is reported
    first:

    1. **Consent**, delegated entirely to
       :func:`~smartmatch_domain.consent.assert_send_eligible`. Re-run here
       because the draft's own composition-time check proves what was true when
       a coordinator was looking at it, and a queued command is not looking at
       anything. An unsubscribe between approval and delivery lands exactly in
       this window, and it is the window that matters most.
    2. **Approval.** Only :attr:`DraftStatus.APPROVED` may be sent — not
       ``DRAFT`` (nobody signed off) and not ``SUPERSEDED`` (somebody replaced
       it, and sending the old text after a correction is worse than sending
       nothing).
    3. **Content review**, when ``live_mode``. See :class:`ContentStatus` and
       OQ-003. Written as "must be ``REVIEWED``" rather than "must not be
       ``SYNTHETIC``" so a status invented later is refused by default.
    4. Nothing else. In particular this function does not check a suppression
       list — :attr:`DraftRecipient.suppressed` is the caller's own read of it,
       and condition 1 is where it is enforced. A second suppression check here
       reading different state would be two rules with one name.

    Args:
        recipient: The addressee's consent facts, **re-read**, not replayed.
        draft_status: The draft's status as stored now.
        content_status: The draft's recorded content status.
        live_mode: Whether this send reaches a live provider. ``False`` for
            every fixture send.

    Raises:
        ConsentViolationError: when the recipient may not be contacted, or when
            the draft's approval or content status forbids this send. All four
            conditions raise the same type on purpose: the worker maps it to a
            terminal ``PolicyFailure``, and a caller must not be able to treat
            "not approved" as more recoverable than "not consented" — neither
            is fixed by retrying.
    """
    assert_send_eligible(
        recipient.contact_state,
        consent_source=recipient.consent_source,
        suppressed=recipient.suppressed,
    )

    if draft_status is not DraftStatus.APPROVED:
        raise ConsentViolationError(
            f"draft is {draft_status.value!r}, not 'approved'; send blocked. A draft "
            "records an intention to send, never a standing permission — the "
            "approval is what a named actor signed off on, and there is not one here."
        )

    if live_mode and content_status is not ContentStatus.REVIEWED:
        raise ConsentViolationError(
            f"draft content is {content_status.value!r}, and a live send requires "
            f"{ContentStatus.REVIEWED.value!r}; send blocked. The template's copy has "
            "not been through institutional review (OQ-003 in "
            "docs/plans/open-questions/r4-outreach-deferred.md). The fixture provider "
            "will send it; a real recipient will not receive it."
        )
