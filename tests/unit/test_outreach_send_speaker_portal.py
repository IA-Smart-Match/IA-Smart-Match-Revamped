"""The outreach worker's Speaker portal gate and late-bound link (B26 T6b-1 plan §6).

Fakes for every collaborator and a fixed clock: the gate is pure logic over
what the repositories return. Secret-shaped values are built at runtime.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from smartmatch_domain.jobs import JobState
from smartmatch_domain.outreach import OUTREACH_SEND_COMMAND_TYPE
from smartmatch_domain.speaker_portal import (
    ACTIVATION_URL_SENTINEL,
    INVITE_TEMPLATE_ID,
    derive_token,
    token_hash,
)
from smartmatch_persistence.jobs import JobRecord
from smartmatch_persistence.outreach import DraftRow, RecipientFacts, SendReservation
from smartmatch_persistence.speaker_portal import InvitationForSend
from smartmatch_providers.fixtures import FixtureEmailProvider
from smartmatch_worker import outreach as worker_outreach
from smartmatch_worker.handlers import CommandContext, PolicyFailure
from smartmatch_worker.outreach import build_outreach_send_handler

_NOW = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)
_BASE = "https://portal.example.invalid"
_SECRET = secrets.token_urlsafe(40)
_TENANT = uuid.uuid4()
_UNIT = uuid.uuid4()
_CHANNEL = uuid.uuid4()
_INVITATION = uuid.uuid4()
_OTHER_TEMPLATE = "pilot.event_invitation.v1"


class _Session:
    def __enter__(self) -> _Session:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def commit(self) -> None:
        return None


@dataclass
class _Repo:
    draft: DraftRow
    concluded: list[tuple[str, str | None]]

    def get_draft(self, session: Any, *, tenant_id: uuid.UUID, draft_id: uuid.UUID) -> DraftRow:
        return self.draft

    def load_recipient(self, session: Any, **kwargs: Any) -> RecipientFacts:
        return RecipientFacts(
            contact_channel_id=_CHANNEL,
            professional_id=uuid.uuid4(),
            owning_unit_id=_UNIT,
            address="dana@example.invalid",
            contact_state="active_candidate",
            consent_source="in_person",
            suppressed=False,
        )

    def reserve_send(self, session: Any, **kwargs: Any) -> SendReservation:
        return SendReservation(
            send_id=uuid.uuid4(),
            was_already_reserved=False,
            recipient_address="dana@example.invalid",
            disposition=None,
        )

    def append_delivery_event(self, session: Any, **kwargs: Any) -> None:
        return None

    def conclude_send(self, session: Any, *, disposition: str, **kwargs: Any) -> None:
        self.concluded.append((disposition, kwargs.get("failure_reason")))


@dataclass
class _Portal:
    invitation: InvitationForSend | None
    asked: list[uuid.UUID]

    def get_for_send(
        self, session: Any, *, tenant_id: uuid.UUID, invitation_id: uuid.UUID
    ) -> InvitationForSend | None:
        self.asked.append(tenant_id)
        return self.invitation


class _Pipeline:
    def __getattr__(self, name: str) -> Any:  # pragma: no cover - unused without a record id
        raise AssertionError(name)


def _draft(template_id: str = INVITE_TEMPLATE_ID, **overrides: Any) -> DraftRow:
    body = (
        f"Hello Dana,\n\nChoose a password here: {ACTIVATION_URL_SENTINEL}\n"
        if template_id == INVITE_TEMPLATE_ID
        else "Hello Dana,\n"
    )
    row = DraftRow(
        id=uuid.uuid4(),
        tenant_id=_TENANT,
        owning_unit_id=_UNIT,
        contact_channel_id=_CHANNEL,
        template_id=template_id,
        content_status="synthetic",
        subject="Your Speaker Portal account",
        body=body,
        status="approved",
        version=1,
        created_by=uuid.uuid4(),
        created_at=_NOW,
        approved_by=uuid.uuid4(),
        approved_at=_NOW,
        superseded_by_draft_id=None,
    )
    return replace(row, **overrides)


def _invitation(**overrides: Any) -> InvitationForSend:
    row = InvitationForSend(
        id=_INVITATION,
        owning_unit_id=_UNIT,
        contact_channel_id=_CHANNEL,
        token_hash=token_hash(derive_token(_SECRET, _INVITATION)),
        expires_at=_NOW + timedelta(days=7),
        accepted_at=None,
        revoked_at=None,
    )
    return replace(row, **overrides)


def _run(
    *,
    draft: DraftRow | None = None,
    invitation: InvitationForSend | str | None = "default",
    with_invitation_id: bool = True,
    enabled: bool = True,
    secret: str | None = _SECRET,
    job_unit: uuid.UUID = _UNIT,
) -> tuple[FixtureEmailProvider, _Repo, _Portal, Any]:
    provider = FixtureEmailProvider()
    repo = _Repo(draft=draft or _draft(), concluded=[])
    portal = _Portal(
        invitation=_invitation() if invitation == "default" else invitation,  # type: ignore[arg-type]
        asked=[],
    )
    handler = build_outreach_send_handler(
        session_factory=lambda: _Session(),  # type: ignore[arg-type,return-value]
        provider=provider,
        from_address="noreply@example.invalid",
        public_base_url=_BASE,
        unsubscribe_secret=None,
        live_mode=False,
        repository=repo,  # type: ignore[arg-type]
        pipeline=_Pipeline(),  # type: ignore[arg-type]
        portal=portal,  # type: ignore[arg-type]
        speaker_portal_token_secret=secret,
        speaker_portal_enabled=enabled,
        clock=lambda: _NOW,
    )
    payload: dict[str, Any] = {"draft_id": str(repo.draft.id)}
    if with_invitation_id:
        payload["speaker_portal_invitation_id"] = str(_INVITATION)
    context = CommandContext(
        job=JobRecord(
            id=uuid.uuid4(),
            tenant_id=_TENANT,
            command_type=OUTREACH_SEND_COMMAND_TYPE,
            status=JobState.RUNNING,
            owning_unit_id=job_unit,
            payload=payload,
            actor_id=uuid.uuid4(),
            created_at=_NOW,
            updated_at=_NOW,
        ),
        emit=lambda event: 1,
        session=_Session(),  # type: ignore[arg-type]
    )
    try:
        outcome: Any = handler(context)
    except PolicyFailure as failure:
        outcome = failure
    return provider, repo, portal, outcome


def test_worker_renders_the_activation_link_at_send_only() -> None:
    provider, _, portal, outcome = _run()
    assert not isinstance(outcome, PolicyFailure), outcome
    [sent] = provider.sent
    expected = f"{_BASE}/s/{derive_token(_SECRET, _INVITATION)}"
    assert sent.body_text.count(expected) == 1
    assert ACTIVATION_URL_SENTINEL not in sent.body_text
    assert expected not in sent.subject
    assert portal.asked == [_TENANT]


def test_draft_body_is_unchanged_after_send() -> None:
    draft = _draft()
    before = draft.body
    _, repo, _, _ = _run(draft=draft)
    assert repo.draft.body == before
    assert ACTIVATION_URL_SENTINEL in repo.draft.body


_GATE_CASES = {
    "speaker_portal_disabled": {"enabled": False},
    "speaker_portal_secret_missing": {"secret": None},
    "speaker_portal_invitation_pairing": {"with_invitation_id": False},
    "speaker_portal_invitation_not_found": {"invitation": None},
    "speaker_portal_invitation_unit_mismatch": {
        "invitation": _invitation(owning_unit_id=uuid.uuid4())
    },
    "speaker_portal_invitation_not_live": {"invitation": _invitation(revoked_at=_NOW)},
    "speaker_portal_invitation_expired": {"invitation": _invitation(expires_at=_NOW)},
    "speaker_portal_channel_mismatch": {"invitation": _invitation(contact_channel_id=uuid.uuid4())},
    "speaker_portal_sentinel_invalid": {
        "draft": _draft(body=f"{ACTIVATION_URL_SENTINEL} twice {ACTIVATION_URL_SENTINEL}")
    },
    "speaker_portal_token_mismatch": {"invitation": _invitation(token_hash=b"\x00" * 32)},
}


@pytest.mark.parametrize("reason", sorted(_GATE_CASES))
def test_every_gate_refusal_is_terminal_and_sends_nothing(reason: str) -> None:
    provider, repo, _, outcome = _run(**_GATE_CASES[reason])
    assert isinstance(outcome, PolicyFailure)
    assert outcome.reason == reason
    assert provider.sent == []
    assert repo.concluded == [("blocked", reason)]


def test_pairing_also_refuses_an_invitation_id_on_another_template() -> None:
    provider, _, _, outcome = _run(draft=_draft(template_id=_OTHER_TEMPLATE))
    assert isinstance(outcome, PolicyFailure)
    assert outcome.reason == "speaker_portal_invitation_pairing"
    assert provider.sent == []


def test_other_templates_are_untouched() -> None:
    draft = _draft(template_id=_OTHER_TEMPLATE)
    provider, _, portal, outcome = _run(
        draft=draft, with_invitation_id=False, enabled=False, secret=None
    )
    assert not isinstance(outcome, PolicyFailure), outcome
    assert [sent.body_text for sent in provider.sent] == [draft.body]
    assert portal.asked == []


def test_sentinel_in_another_template_is_inert() -> None:
    draft = _draft(template_id=_OTHER_TEMPLATE, body=f"typed {ACTIVATION_URL_SENTINEL}")
    provider, _, _, outcome = _run(draft=draft, with_invitation_id=False)
    assert not isinstance(outcome, PolicyFailure), outcome
    assert provider.sent[0].body_text == draft.body


def test_worker_and_api_derive_the_same_token() -> None:
    """One import, one label: the worker has no second derivation."""
    from smartmatch_domain import speaker_portal

    assert worker_outreach.derive_token is speaker_portal.derive_token
    assert not hasattr(worker_outreach, "TOKEN_DERIVATION_LABEL") or (
        worker_outreach.TOKEN_DERIVATION_LABEL is speaker_portal.TOKEN_DERIVATION_LABEL
    )
