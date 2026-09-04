"""Executing ``outreach.send``: the only place a message actually leaves (card L5).

This module is the whole of the platform's send capability. Everything upstream
of it records intent — a draft is text somebody approved, a job is a command
somebody submitted — and nothing upstream can cause a message to be delivered.
That property is worth stating plainly, because it is what makes the rest of the
feature reviewable: to answer "under what conditions does this system email a
person", a reader has to read one function.

## The gate runs again here, and that is the point of the card

``smartmatch_domain.outreach.compose_draft`` already proved the recipient was
eligible when the draft was composed. This calls
:func:`~smartmatch_domain.outreach.assert_send_allowed` a second time, against
state read from the database at delivery time, because the first proof is about
a moment that has passed. ``CommandContext``'s own docstring makes the general
version of this argument — "a task can sit in the queue for minutes while
consent, budget, or approval change, so the delivery is treated as a
*notification that work exists*, never as a description of it" — and outreach is
the case where it bites hardest: an unsubscribe between approval and delivery
lands in exactly this window, and it is the ordinary operation of the link in
every message we send, not an edge case.

## Why this handler owns a second session

The executor rolls its session back whenever a handler raises
(``execution.py``: *"an exception cannot authorize staged business work"*). That
is correct for ordinary business work and wrong for two things here:

* the **reservation**, whose entire job is to stop a second attempt — a
  reservation discarded by the failure it was meant to survive stops nothing;
* the **refusal record**, because a blocked send must leave the same kind of
  trace an acceptance does. A refusal that wrote nothing is indistinguishable
  from a send that never happened, and "we declined to contact this person, for
  this reason, at this time" is precisely what an audit of a consent system asks
  for.

So those writes go on a handler-owned session that commits as it goes, exactly
as ``paid_extraction.py``'s spend reservation does and for the same reason: a
record that must outlive a later failure cannot share a transaction with it.

The **pipeline advance** deliberately does *not* go there. It is ordinary
business work, it should exist only if the job succeeded, and so it goes on
``context.session`` where the executor's rules apply.

## Failure classification is not cosmetic

* A consent, suppression, approval, or content refusal is a
  :class:`~smartmatch_worker.handlers.PolicyFailure` — ``failed_policy``, which
  is terminal. Re-driving it would refuse again, and offering an operator a
  button that cannot work is worse than saying so.
* A provider error is a :class:`~smartmatch_worker.handlers.ProviderFailure` —
  ``failed_provider``, which is re-drivable, and the reservation is what makes
  that re-drive safe.

Getting these backwards produces either a message retried against a withdrawn
consent, or a transient outage recorded as a permanent policy refusal.

## No spend reservation

Deliberate, and recorded as OQ-007. ADR-0015 A1 ratifies a synthetic reservation
for *paid extraction*; whether transactional email falls under the same ceiling
is a budget decision nobody has made. Reserving against the fixture provider —
which costs nothing — would be recording a spend that did not happen, which is
the fabricated-measurement shape ADR-0011 forbids. The live branch is where a
reservation would belong, and the live branch is refused for OQ-002 anyway.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, Final

from smartmatch_domain.consent import ConsentSource, ConsentViolationError, ContactState
from smartmatch_domain.jobs import JobState
from smartmatch_domain.outreach import (
    ContentStatus,
    DeliveryEventType,
    DraftRecipient,
    DraftStatus,
    SendDisposition,
    assert_send_allowed,
)
from smartmatch_domain.pipeline import PipelineStage
from smartmatch_persistence.outreach import OutreachRepository
from smartmatch_persistence.pipeline import PipelineRepository
from smartmatch_providers.base import EmailProvider, SendRequest
from sqlalchemy.orm import Session, sessionmaker

from smartmatch_worker.handlers import (
    CommandContext,
    CommandHandler,
    CommandRegistry,
    HandlerResult,
    PolicyFailure,
    ProviderFailure,
)

__all__ = [
    "SYNTHETIC_UNSUBSCRIBE_SECRET",
    "OutreachSendCommand",
    "build_outreach_send_handler",
    "unsubscribe_token",
    "with_outreach_send",
]

#: The HMAC key used when no real one is configured. Named, constant, and
#: obviously not a secret — which is the point: a token minted with it is
#: reproducible by anyone reading this file, so it must never be reachable from
#: an edition that can send to a real address. ``build_outreach_send_handler``
#: refuses to fall back to it in live mode. See OQ-005.
SYNTHETIC_UNSUBSCRIBE_SECRET: Final[str] = "synthetic-pilot-unsubscribe-key-not-a-secret"

#: How a delivery event says who wrote it, when the provider did not.
_OUR_OWN_EVENT: Final[None] = None


def _utcnow() -> datetime:
    """Injected into the handler so tests pin one clock. See ``paid_extraction``."""
    return datetime.now(UTC)


class OutreachSendCommand:
    """The persisted payload, read once and validated as a whole.

    A plain class rather than a dataclass only because it is constructed in one
    place; what matters is :meth:`read`, which collects *every* problem before
    raising. A payload rejected one field at a time makes an operator re-drive a
    job to discover the next thing wrong with it — and the payload is durable,
    so each re-drive fails identically.
    """

    __slots__ = ("draft_id", "pipeline_record_id")

    def __init__(self, *, draft_id: uuid.UUID, pipeline_record_id: uuid.UUID | None) -> None:
        self.draft_id = draft_id
        self.pipeline_record_id = pipeline_record_id

    @classmethod
    def read(cls, payload: Mapping[str, Any]) -> OutreachSendCommand:
        """Parse a persisted payload.

        Raises:
            PolicyFailure: ``invalid_command_payload``. Terminal, for the reason
                ``_read_match_run_command`` gives: the payload is durable, a
                re-drive re-reads the identical bytes, and ``failed_provider``
                would invite an operator to press a button that cannot work.
        """
        problems: list[str] = []

        draft_id = _read_uuid(payload.get("draft_id"), "draft_id", problems, required=True)
        pipeline_record_id = _read_uuid(
            payload.get("pipeline_record_id"), "pipeline_record_id", problems, required=False
        )

        if problems or draft_id is None:
            raise PolicyFailure(
                "the persisted outreach payload cannot be read: "
                + "; ".join(problems or ["no usable fields were found"]),
                reason="invalid_command_payload",
            )
        return cls(draft_id=draft_id, pipeline_record_id=pipeline_record_id)


def _read_uuid(raw: object, field: str, problems: list[str], *, required: bool) -> uuid.UUID | None:
    """Coerce one payload field to a UUID, recording rather than raising."""
    if raw is None:
        if required:
            problems.append(f"{field} is missing")
        return None
    if not isinstance(raw, str):
        problems.append(f"{field} must be a string, got {type(raw).__name__}")
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        problems.append(f"{field} is not a UUID")
        return None


def unsubscribe_token(secret: str, job_id: uuid.UUID) -> str:
    """Derive this send's unsubscribe token, reproducibly.

    An HMAC over the job id rather than a random value, and the reason is the
    re-drive. ``outreach_send`` stores only the token's **hash**, so a second
    execution cannot recover a random token from the row it finds — it would
    have to mint a new one, which the globally-unique hash column would then
    refuse, and the message would carry a link that unsubscribes nothing.
    Deriving it means every execution of the same command computes the same
    token without anything having to store it.

    The secret never leaves the process and the token is never stored, so an
    attacker with the database cannot forge a link and a reader of the database
    cannot use one.
    """
    return hmac.new(
        secret.encode("utf-8"), f"unsubscribe:{job_id}".encode(), hashlib.sha256
    ).hexdigest()


def _token_hash(token: str) -> str:
    """SHA-256 of the token, which is the only form ever stored."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def build_outreach_send_handler(
    *,
    session_factory: sessionmaker[Session],
    provider: EmailProvider,
    from_address: str,
    public_base_url: str,
    unsubscribe_secret: str | None,
    live_mode: bool,
    repository: OutreachRepository | None = None,
    pipeline: PipelineRepository | None = None,
    clock: Callable[[], datetime] = _utcnow,
) -> CommandHandler:
    """Build the handler that sends one approved draft.

    A factory rather than a bare function, for the reason
    ``build_paid_extraction_handler`` is one: the collaborators are passed in and
    captured, so nothing is read from a module-level global and a test
    constructs a different handler instead of patching one.

    Args:
        session_factory: Produces the handler-owned session the reservation, the
            delivery events, and the conclusion are written on. See the module
            docstring for why those cannot share the executor's transaction.
        provider: The adapter to call. Obtained through
            ``smartmatch_providers.registry.build_email_provider``, which is what
            refuses a live client under a fixture-only edition — this call site
            cannot widen that.
        from_address: The institutional From. No default: choosing one is an
            institutional identity claim, and OQ-001 records that nobody has
            made it. The composition root supplies ``noreply@example.invalid``
            for fixture mode.
        public_base_url: Origin the unsubscribe URLs are built against.
        unsubscribe_secret: HMAC key for :func:`unsubscribe_token`. ``None``
            falls back to :data:`SYNTHETIC_UNSUBSCRIBE_SECRET` — but only when
            ``live_mode`` is false. See below.
        live_mode: Whether this handler can reach a real mailbox. Drives the
            content-review gate in ``assert_send_allowed`` and the secret rule.
        repository: Injectable for tests; a default instance otherwise.
        pipeline: Injectable for tests; a default instance otherwise.
        clock: Returns "now". Injected for deterministic tests.

    Raises:
        ValueError: at *build* time, not send time, when ``live_mode`` is true
            and no ``unsubscribe_secret`` was configured. Failing at the
            composition root means a misconfigured deployment does not boot,
            rather than accepting commands it will refuse one at a time — and
            silently minting live unsubscribe links with a key printed in this
            file is the one outcome that must be impossible.
    """
    if live_mode and not unsubscribe_secret:
        raise ValueError(
            "a live outreach deployment must configure SMARTMATCH_UNSUBSCRIBE_SECRET. "
            "Falling back to the synthetic key would mint unsubscribe links anyone "
            "reading smartmatch_worker/outreach.py could forge (OQ-005)."
        )

    secret = unsubscribe_secret or SYNTHETIC_UNSUBSCRIBE_SECRET
    repo = repository or OutreachRepository()
    pipeline_repo = pipeline or PipelineRepository()
    base = public_base_url.rstrip("/")

    def handle_outreach_send(context: CommandContext) -> HandlerResult:
        """Send one approved draft, or record precisely why it was not sent."""
        payload = context.job.payload
        if payload is None:
            raise PolicyFailure(
                "the job carries no payload, so there is nothing to send. Nothing "
                "can recover it — the idempotency fingerprint is a one-way hash — "
                "so this cannot be re-driven into working.",
                reason="command_payload_missing",
            )

        command = OutreachSendCommand.read(payload)
        tenant_id = context.job.tenant_id
        now = clock()

        with session_factory() as own:
            draft = repo.get_draft(own, tenant_id=tenant_id, draft_id=command.draft_id)
            if draft is None:
                raise PolicyFailure(
                    f"no outreach draft {command.draft_id} in this tenant.",
                    reason="outreach_draft_not_found",
                )
            if draft.owning_unit_id != context.job.owning_unit_id:
                # The job's unit is what the route authorized against. A draft
                # filed under a different one is not a lookup miss — it is a
                # command whose authorization does not cover its target.
                raise PolicyFailure(
                    "the draft belongs to a different organizational unit than the "
                    "command was authorized for.",
                    reason="outreach_draft_unit_mismatch",
                )

            facts = repo.load_recipient(
                own, tenant_id=tenant_id, contact_channel_id=draft.contact_channel_id
            )
            if facts is None:
                raise PolicyFailure(
                    "the draft's contact channel no longer exists.",
                    reason="outreach_contact_not_found",
                )

            token = unsubscribe_token(secret, context.job.id)
            reservation = repo.reserve_send(
                own,
                tenant_id=tenant_id,
                owning_unit_id=draft.owning_unit_id,
                draft_id=draft.id,
                job_id=context.job.id,
                idempotency_key=f"outreach-send:{context.job.id}",
                recipient_address=facts.address,
                from_address=from_address,
                unsubscribe_token_hash=_token_hash(token),
            )
            own.commit()

            if reservation.was_already_reserved and reservation.disposition is not None:
                # A previous execution already reached an outcome. Reporting it
                # rather than re-sending is the entire purpose of the
                # reservation; a re-drive is a second delivery of one command,
                # not a second message.
                return _replayed(context, reservation.send_id, reservation.disposition)

            context.emit(
                {
                    "type": "progress",
                    "detail": "recipient resolved; rechecking consent at delivery time",
                    "send_id": str(reservation.send_id),
                }
            )
            repo.append_delivery_event(
                own,
                tenant_id=tenant_id,
                send_id=reservation.send_id,
                event_type=DeliveryEventType.QUEUED.value,
                occurred_at=now,
                provider_event_id=_OUR_OWN_EVENT,
            )
            own.commit()

            try:
                assert_send_allowed(
                    recipient=_recipient(facts),
                    draft_status=DraftStatus(draft.status),
                    content_status=ContentStatus(draft.content_status),
                    live_mode=live_mode,
                )
            except ConsentViolationError as exc:
                _record_refusal(
                    repo,
                    own,
                    tenant_id=tenant_id,
                    send_id=reservation.send_id,
                    event_type=DeliveryEventType.BLOCKED,
                    disposition=SendDisposition.BLOCKED,
                    reason=str(exc),
                    now=now,
                )
                raise PolicyFailure(
                    f"the send was refused at delivery time: {exc}",
                    reason="outreach_send_blocked",
                ) from exc

            request = SendRequest(
                to_address=facts.address,
                subject=draft.subject,
                body_text=draft.body,
                # The approval *is* the draft: an approved draft's text cannot
                # change (there is no APPROVED -> DRAFT edge), so the draft id
                # identifies exactly the thing that was signed off on.
                approval_id=str(draft.id),
                approved_draft_version=draft.version,
                # Stable across re-drives, which is what makes the retry safe
                # at the provider as well as in our own table.
                idempotency_key=f"outreach-send:{context.job.id}",
                list_unsubscribe_url=f"{base}/u/{token}",
                list_unsubscribe_post_url=f"{base}/v1/unsubscribe",
            )

            try:
                result = provider.send(request)
            except Exception as exc:
                _record_refusal(
                    repo,
                    own,
                    tenant_id=tenant_id,
                    send_id=reservation.send_id,
                    event_type=DeliveryEventType.FAILED,
                    disposition=SendDisposition.FAILED,
                    reason=f"{type(exc).__name__}: {exc}",
                    now=now,
                )
                raise ProviderFailure(
                    f"the email provider failed: {exc}",
                    reason="outreach_provider_failed",
                ) from exc

            repo.append_delivery_event(
                own,
                tenant_id=tenant_id,
                send_id=reservation.send_id,
                event_type=DeliveryEventType.ACCEPTED.value,
                occurred_at=now,
                provider_event_id=_OUR_OWN_EVENT,
                detail={"provider": result.provider},
            )
            repo.conclude_send(
                own,
                tenant_id=tenant_id,
                send_id=reservation.send_id,
                disposition=SendDisposition.ACCEPTED.value,
                concluded_at=now,
                provider=result.provider,
                provider_message_id=result.provider_message_id,
            )
            own.commit()

        contacted = _advance_pipeline(
            pipeline_repo,
            context.session,
            tenant_id=tenant_id,
            pipeline_record_id=command.pipeline_record_id,
            now=now,
        )

        context.emit(
            {
                "type": "progress",
                "detail": "provider accepted the message",
                "send_id": str(reservation.send_id),
            }
        )

        return HandlerResult(
            state=JobState.SUCCEEDED,
            summary={
                "send_id": str(reservation.send_id),
                # "accepted", never "sent" or "delivered". The provider took
                # custody; whether it arrives is a later delivery_event that may
                # never come (SendResult's own docstring makes the same point).
                "disposition": SendDisposition.ACCEPTED.value,
                "provider": result.provider,
                "provider_message_id": result.provider_message_id,
                "pipeline_contacted": contacted,
                "live_mode": live_mode,
            },
        )

    return handle_outreach_send


def _recipient(facts: Any) -> DraftRecipient:
    """Turn stored text into the domain's own vocabulary.

    Coercion happens here, at the boundary, rather than in the repository: the
    persistence layer may not import domain enums for a lifecycle it does not
    own, and a handler that compared raw strings would be re-deriving a
    vocabulary the domain already states.

    A value the domain does not recognize raises ``ValueError`` out of the enum,
    which the executor classifies as an unexpected exception — the right
    outcome, because a ``contact_state`` no enum member matches means the
    database and the code disagree about what the lifecycle *is*, and no send
    should proceed while that is true.
    """
    return DraftRecipient(
        address=facts.address,
        contact_state=ContactState(facts.contact_state),
        consent_source=(
            ConsentSource(facts.consent_source) if facts.consent_source is not None else None
        ),
        suppressed=facts.suppressed,
    )


def _record_refusal(
    repo: OutreachRepository,
    session: Session,
    *,
    tenant_id: uuid.UUID,
    send_id: uuid.UUID,
    event_type: DeliveryEventType,
    disposition: SendDisposition,
    reason: str,
    now: datetime,
) -> None:
    """Write the refusal durably, then let the caller raise.

    Committed here rather than left to the executor, which rolls back on any
    handler exception. A refusal that vanished with the failure it explains
    would leave no answer to "why did this person not receive the message they
    were meant to", which is the question a consent system exists to be able to
    answer.
    """
    repo.append_delivery_event(
        session,
        tenant_id=tenant_id,
        send_id=send_id,
        event_type=event_type.value,
        occurred_at=now,
        provider_event_id=_OUR_OWN_EVENT,
        detail={"reason": reason},
    )
    repo.conclude_send(
        session,
        tenant_id=tenant_id,
        send_id=send_id,
        disposition=disposition.value,
        concluded_at=now,
        failure_reason=reason,
    )
    session.commit()


def _replayed(context: CommandContext, send_id: uuid.UUID, disposition: str) -> HandlerResult:
    """Report a command that a previous execution already concluded.

    A re-drive of a send that was *blocked* still succeeds as a job, which reads
    oddly until you separate the two questions. "Did this command execute" and
    "did a message go out" are different, and the second is answered by
    ``disposition`` — reported in the summary, never flattened into the job
    state. Failing the job again would re-run a terminal refusal for no
    additional information.
    """
    context.emit(
        {
            "type": "progress",
            "detail": "this command was already executed; reporting the recorded outcome",
            "send_id": str(send_id),
        }
    )
    return HandlerResult(
        state=JobState.SUCCEEDED,
        summary={
            "send_id": str(send_id),
            "disposition": disposition,
            "replayed": True,
        },
    )


def _advance_pipeline(
    pipeline: PipelineRepository,
    session: Session,
    *,
    tenant_id: uuid.UUID,
    pipeline_record_id: uuid.UUID | None,
    now: datetime,
) -> bool:
    """Move a funnel row to Contacted, when the command named one.

    **Conditional, and that is deliberate.** ``pipeline_record`` is the *student*
    journey: its ``subject_id`` is a ``user_account`` and its stages describe a
    student moving toward attending an event. An outreach message to a
    professional is not a step in that journey by itself, so this handler does
    not invent a funnel row for one — creating a journey nobody asked for in
    order to have something to advance would inflate every funnel metric that
    counts records reaching a stage.

    So the Contacted stage is recorded only when the submitting route explicitly
    names the journey this message is part of, and skipped otherwise. Skipped is
    reported in the summary rather than silently, because "no pipeline row was
    advanced" is a fact a coordinator reading the job may need.

    Written on ``context.session``, not the handler's own: unlike the send
    record, this is ordinary business work that should exist only if the job
    succeeded.

    Returns:
        Whether a stage was advanced by this call. ``False`` covers three
        distinct cases — no journey was named, no such row exists, and the row
        had already reached Contacted — and the caller reports the boolean
        rather than asserting on it, because none of the three is an error.
    """
    if pipeline_record_id is None:
        return False

    outcome = pipeline.advance_stage(
        session,
        tenant_id=tenant_id,
        record_id=pipeline_record_id,
        stage=PipelineStage.CONTACTED,
        reached_at=now,
    )
    return outcome.transitioned


def with_outreach_send(
    registry: CommandRegistry, handler: CommandHandler, command_type: str
) -> CommandRegistry:
    """Return ``registry`` plus the outreach handler.

    A new registry rather than a mutation, mirroring
    ``paid_extraction.with_paid_extraction``: ``CommandRegistry`` is frozen so
    that what a worker can execute is decided once at the composition root and
    cannot drift afterwards.
    """
    return CommandRegistry(handlers={**registry.handlers, command_type: handler})
