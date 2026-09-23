"""The ``cba.speaker_portal_invite.v1`` template and the system-only set (B26 T6b-1)."""

from __future__ import annotations

from smartmatch_domain.consent import ConsentSource, ContactState
from smartmatch_domain.outreach import (
    SYSTEM_ONLY_TEMPLATES,
    TEMPLATES,
    ContentStatus,
    DraftRecipient,
    compose_draft,
)
from smartmatch_domain.speaker_portal import ACTIVATION_URL_SENTINEL, INVITE_TEMPLATE_ID


def test_invite_template_is_in_the_closed_registry() -> None:
    assert INVITE_TEMPLATE_ID == "cba.speaker_portal_invite.v1"
    template = TEMPLATES[INVITE_TEMPLATE_ID]
    assert template.placeholders == frozenset(
        {"professional_name", "unit_name", "expires_on", "activation_url"}
    )
    # Unreviewed copy: assert_send_allowed refuses it in live mode.
    assert template.content_status is ContentStatus.SYNTHETIC


def test_invite_template_is_system_only() -> None:
    assert frozenset({INVITE_TEMPLATE_ID}) == SYSTEM_ONLY_TEMPLATES
    assert SYSTEM_ONLY_TEMPLATES <= set(TEMPLATES)


def test_composed_body_carries_the_sentinel_exactly_once_and_not_in_subject() -> None:
    composed = compose_draft(
        recipient=DraftRecipient(
            address="dana@example.org",
            contact_state=ContactState.ACTIVE_CANDIDATE,
            consent_source=ConsentSource.IN_PERSON,
            suppressed=False,
        ),
        template_id=INVITE_TEMPLATE_ID,
        values={
            "professional_name": "Dana Reyes",
            "unit_name": "College of Business",
            "expires_on": "9 November 2026",
            "activation_url": ACTIVATION_URL_SENTINEL,
        },
    )
    assert composed.body.count(ACTIVATION_URL_SENTINEL) == 1
    assert ACTIVATION_URL_SENTINEL not in composed.subject
    assert "/s/" not in composed.body
