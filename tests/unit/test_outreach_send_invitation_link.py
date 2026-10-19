"""#287: the /i/ response link is rendered at send time, never stored in a draft."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass, replace
from typing import Any

import pytest
from smartmatch_domain.cba_invitations import (
    INVITATION_TEMPLATE_ID,
    RESPONSE_URL_SENTINEL,
    derive_response_token,
)
from smartmatch_domain.jobs import JobState
from smartmatch_domain.outreach import (
    OUTREACH_SEND_COMMAND_TYPE,
    SYSTEM_ONLY_TEMPLATES,
    TEMPLATES,
)
from smartmatch_persistence.jobs import JobRecord
from smartmatch_providers.fixtures import FixtureEmailProvider
from smartmatch_worker.handlers import CommandContext, PolicyFailure
from smartmatch_worker.outreach import build_outreach_send_handler

from tests.unit.test_outreach_send_speaker_portal import (
    _BASE,
    _NOW,
    _TENANT,
    _UNIT,
    _draft,
    _Pipeline,
    _Portal,
    _Repo,
    _Session,
)

_SECRET = secrets.token_urlsafe(40)
_INVITATION = uuid.uuid4()


@dataclass
class _Invitations:
    facts: tuple[uuid.UUID, str | None] | None

    def get_token_facts_for_draft(self, session: Any, **kwargs: Any):
        return self.facts


def _stored_hash(secret: str = _SECRET) -> str:
    token = derive_response_token(secret, _INVITATION)
    return hashlib.sha256(token.encode()).hexdigest()


def _send(
    body: str, facts: Any = "ok", secret: str | None = _SECRET
) -> tuple[FixtureEmailProvider, Any]:
    if facts == "ok":
        facts = (_INVITATION, _stored_hash())
    draft = replace(_draft(INVITATION_TEMPLATE_ID), body=body, subject="Panel invitation")
    provider = FixtureEmailProvider()
    handler = build_outreach_send_handler(
        session_factory=lambda: _Session(),  # type: ignore[arg-type,return-value]
        provider=provider,
        from_address="noreply@example.invalid",
        public_base_url=_BASE,
        unsubscribe_secret=None,
        live_mode=False,
        repository=_Repo(draft=draft, concluded=[]),  # type: ignore[arg-type]
        pipeline=_Pipeline(),  # type: ignore[arg-type]
        portal=_Portal(invitation=None, asked=[]),  # type: ignore[arg-type]
        invitations=_Invitations(facts),  # type: ignore[arg-type]
        invitation_token_secret=secret,
        clock=lambda: _NOW,
    )
    context = CommandContext(
        job=JobRecord(
            id=uuid.uuid4(),
            tenant_id=_TENANT,
            command_type=OUTREACH_SEND_COMMAND_TYPE,
            status=JobState.RUNNING,
            owning_unit_id=_UNIT,
            payload={"draft_id": str(draft.id)},
            actor_id=uuid.uuid4(),
            created_at=_NOW,
            updated_at=_NOW,
        ),
        emit=lambda event: 1,
        session=_Session(),  # type: ignore[arg-type]
    )
    try:
        return provider, handler(context)
    except PolicyFailure as failure:
        return provider, failure


def test_worker_send_renders_the_i_url() -> None:
    provider, outcome = _send(f"Answer here: {RESPONSE_URL_SENTINEL}\n")
    assert not isinstance(outcome, PolicyFailure), outcome
    [sent] = provider.sent
    token = derive_response_token(_SECRET, _INVITATION)
    assert f"{_BASE}/i/{token}" in sent.body_text
    assert RESPONSE_URL_SENTINEL not in sent.body_text


@pytest.mark.parametrize(
    ("body", "facts", "reason"),
    [
        (f"{RESPONSE_URL_SENTINEL} {RESPONSE_URL_SENTINEL}", "ok", "sentinel_invalid"),
        (RESPONSE_URL_SENTINEL, None, "not_found"),
        (RESPONSE_URL_SENTINEL, (_INVITATION, _stored_hash("another-secret-entirely")), "mismatch"),
    ],
)
def test_worker_refuses_what_it_cannot_render(body: str, facts: Any, reason: str) -> None:
    provider, outcome = _send(body, facts)
    assert isinstance(outcome, PolicyFailure)
    assert reason in str(outcome.reason)
    assert provider.sent == []


def test_worker_refuses_to_sign_without_a_secret() -> None:
    """#287: no key means no token and no send; never a public fallback key."""
    provider, outcome = _send(RESPONSE_URL_SENTINEL, secret=None)
    assert isinstance(outcome, PolicyFailure)
    assert "speaker_invitation_secret_unconfigured" in str(outcome.reason)
    assert provider.sent == []


def test_a_legacy_body_without_the_sentinel_is_sent_as_is() -> None:
    provider, outcome = _send("Answer at https://x.invalid/i/abc\n", facts=None)
    assert not isinstance(outcome, PolicyFailure), outcome
    assert provider.sent[0].body_text == "Answer at https://x.invalid/i/abc\n"


def test_invitation_template_is_system_only() -> None:
    assert INVITATION_TEMPLATE_ID in SYSTEM_ONLY_TEMPLATES
    assert INVITATION_TEMPLATE_ID in TEMPLATES
