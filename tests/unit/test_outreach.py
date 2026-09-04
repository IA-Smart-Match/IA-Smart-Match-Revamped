"""The outreach domain: composition, the draft lifecycle, and the send-time gate.

`test_consent.py` covers the lifecycle rules themselves and
`test_outreach_dryrun.py` covers composition through the dry-run view. What is
covered here is what R4 added on top of both: the draft approval state machine,
and `assert_send_allowed` — the check the worker runs at delivery time, which is
the one that has to hold when the facts have changed since a coordinator looked
at them.

The emphasis throughout is on the *second* look. A composition-time check proves
something was true when a message was drafted; almost every test below is about
a moment after that, because that is where a send path can go wrong in a way
nobody sees until a real person receives a real email.
"""

from __future__ import annotations

import pytest
from smartmatch_domain.consent import (
    ConsentSource,
    ConsentViolationError,
    ContactState,
)
from smartmatch_domain.outreach import (
    DRAFT_STATE_TRANSITIONS,
    MAX_RENDERED_SUBJECT_CHARS,
    OUTREACH_SEND_COMMAND_TYPE,
    TEMPLATES,
    ContentStatus,
    DeliveryEventType,
    DraftRecipient,
    DraftStatus,
    OutreachCompositionError,
    OutreachDraftStateError,
    SendDisposition,
    assert_draft_transition,
    assert_send_allowed,
    can_transition_draft,
    compose_draft,
)

#: RFC 2606 reserved TLD, matching `synthetic_pilot.synthetic_professional_email`.
#: No test in this file can address anything deliverable.
_SYNTHETIC_ADDRESS = "professional-0000@synthetic.invalid"

_TEMPLATE_ID = "pilot.event_invitation.v1"

_VALUES = {
    "professional_name": "Sam Rivera",
    "unit_name": "Northside Robotics",
    "event_name": "Spring Showcase",
    "event_date": "Friday, 12 June",
    "coordinator_name": "Alex Chen",
}


def _recipient(**overrides: object) -> DraftRecipient:
    """An eligible synthetic recipient, unless a test says otherwise."""
    base: dict[str, object] = {
        "address": _SYNTHETIC_ADDRESS,
        "contact_state": ContactState.ACTIVE_CANDIDATE,
        "consent_source": ConsentSource.SELF_SERVICE,
        "suppressed": False,
    }
    base.update(overrides)
    return DraftRecipient(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# compose_draft
# ---------------------------------------------------------------------------


class TestComposeDraft:
    """Composition is gated first and rendered second."""

    def test_an_eligible_recipient_gets_a_rendered_draft(self):
        draft = compose_draft(recipient=_recipient(), template_id=_TEMPLATE_ID, values=_VALUES)

        assert draft.recipient_address == _SYNTHETIC_ADDRESS
        assert draft.template_id == _TEMPLATE_ID
        assert draft.subject == "Spring Showcase on Friday, 12 June"
        assert "Sam Rivera" in draft.body
        assert "$" not in draft.body, "an unresolved placeholder reached the body"

    def test_the_gate_runs_before_the_template_is_even_resolved(self):
        """An ineligible recipient plus a nonsense template raises the *consent* error.

        The ordering is the assertion. If the template were resolved first, this
        would raise `OutreachCompositionError` for the unknown id — and a
        research-discovered address would have got as far as having a lookup
        performed on its behalf.
        """
        with pytest.raises(ConsentViolationError):
            compose_draft(
                recipient=_recipient(contact_state=ContactState.DISCOVERED),
                template_id="no.such.template",
                values={},
            )

    @pytest.mark.parametrize(
        "source",
        [ConsentSource.SCRAPED, ConsentSource.PURCHASED, ConsentSource.INFERRED],
    )
    def test_research_evidence_is_never_composed_for(self, source: ConsentSource):
        with pytest.raises(ConsentViolationError):
            compose_draft(
                recipient=_recipient(consent_source=source),
                template_id=_TEMPLATE_ID,
                values=_VALUES,
            )

    def test_the_draft_carries_the_templates_content_status(self):
        """A stored draft must not have to look the template back up.

        The template's status can change; what was composed did not.
        """
        draft = compose_draft(recipient=_recipient(), template_id=_TEMPLATE_ID, values=_VALUES)

        assert draft.content_status is ContentStatus.SYNTHETIC

    def test_the_draft_carries_the_evidence_it_was_gated_by(self):
        draft = compose_draft(recipient=_recipient(), template_id=_TEMPLATE_ID, values=_VALUES)

        assert draft.evidence.contact_state is ContactState.ACTIVE_CANDIDATE
        assert draft.evidence.consent_source is ConsentSource.SELF_SERVICE
        assert draft.evidence.consent_source_is_approved is True
        assert draft.evidence.suppressed is False
        assert draft.evidence.checked_by == "smartmatch_domain.consent.assert_send_eligible"

    def test_an_oversized_rendering_is_refused_at_composition(self):
        """Refused where the failure can name the template, not a column.

        A rendering that exceeded storage would otherwise fail on INSERT, after
        the caller had already been told the draft composed.
        """
        with pytest.raises(OutreachCompositionError, match="subject"):
            compose_draft(
                recipient=_recipient(),
                template_id=_TEMPLATE_ID,
                values={**_VALUES, "event_name": "x" * (MAX_RENDERED_SUBJECT_CHARS + 1)},
            )

    def test_a_draft_is_immutable(self):
        draft = compose_draft(recipient=_recipient(), template_id=_TEMPLATE_ID, values=_VALUES)

        with pytest.raises((AttributeError, TypeError)):
            draft.subject = "something else"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# The draft lifecycle
# ---------------------------------------------------------------------------


class TestDraftLifecycle:
    """Three states, and no way back from either terminal one."""

    def test_a_draft_may_be_approved(self):
        assert can_transition_draft(DraftStatus.DRAFT, DraftStatus.APPROVED)
        assert_draft_transition(DraftStatus.DRAFT, DraftStatus.APPROVED)

    def test_an_approved_draft_may_be_superseded(self):
        assert_draft_transition(DraftStatus.APPROVED, DraftStatus.SUPERSEDED)

    def test_an_approved_draft_cannot_be_returned_to_draft(self):
        """Editing after approval would move the text under a live approval.

        The whole value of pinning an approval to rendered text is that the text
        cannot change afterwards. A correction is a new draft that supersedes
        this one.
        """
        with pytest.raises(OutreachDraftStateError, match="approved"):
            assert_draft_transition(DraftStatus.APPROVED, DraftStatus.DRAFT)

    @pytest.mark.parametrize("target", list(DraftStatus))
    def test_superseded_is_terminal(self, target: DraftStatus):
        with pytest.raises(OutreachDraftStateError):
            assert_draft_transition(DraftStatus.SUPERSEDED, target)

    def test_no_state_transitions_to_itself(self):
        """A no-op transition is a caller that did not check, not a legal move."""
        for state, targets in DRAFT_STATE_TRANSITIONS.items():
            assert state not in targets

    def test_the_error_names_the_moves_that_were_available(self):
        with pytest.raises(OutreachDraftStateError, match=r"\['superseded'\]"):
            assert_draft_transition(DraftStatus.APPROVED, DraftStatus.DRAFT)

    def test_the_transition_table_covers_every_state(self):
        """A state absent from the table would raise KeyError, not refuse."""
        assert set(DRAFT_STATE_TRANSITIONS) == set(DraftStatus)


# ---------------------------------------------------------------------------
# assert_send_allowed — the delivery-time gate
# ---------------------------------------------------------------------------


def _allow(**overrides: object) -> None:
    """Call the send gate with a fully permitted set of facts, minus overrides."""
    kwargs: dict[str, object] = {
        "recipient": _recipient(),
        "draft_status": DraftStatus.APPROVED,
        "content_status": ContentStatus.SYNTHETIC,
        "live_mode": False,
    }
    kwargs.update(overrides)
    assert_send_allowed(**kwargs)  # type: ignore[arg-type]


class TestSendGate:
    """What the worker checks again, at the moment of delivery."""

    def test_an_approved_draft_to_an_eligible_recipient_is_allowed(self):
        _allow()

    def test_consent_withdrawn_after_approval_blocks_the_send(self):
        """The whole reason this gate exists a second time.

        The draft was composed and approved while the recipient was eligible.
        By the time the command is executed they have unsubscribed. Nothing
        about the draft changed; the send must still be refused.
        """
        with pytest.raises(ConsentViolationError, match="suppressed"):
            _allow(recipient=_recipient(suppressed=True))

    def test_a_recipient_moved_out_of_active_candidate_blocks_the_send(self):
        with pytest.raises(ConsentViolationError, match="active_candidate"):
            _allow(recipient=_recipient(contact_state=ContactState.STALE))

    @pytest.mark.parametrize("status", [DraftStatus.DRAFT, DraftStatus.SUPERSEDED])
    def test_only_an_approved_draft_may_be_sent(self, status: DraftStatus):
        with pytest.raises(ConsentViolationError, match="approved"):
            _allow(draft_status=status)

    def test_synthetic_content_is_refused_in_live_mode(self):
        with pytest.raises(ConsentViolationError, match="synthetic"):
            _allow(live_mode=True)

    def test_reviewed_content_is_permitted_in_live_mode(self):
        _allow(live_mode=True, content_status=ContentStatus.REVIEWED)

    def test_synthetic_content_is_permitted_against_the_fixture_provider(self):
        """The pilot exercises the whole path; only a *live* send needs review."""
        _allow(live_mode=False, content_status=ContentStatus.SYNTHETIC)

    def test_every_refusal_is_the_same_exception_type(self):
        """A caller must not be able to treat "not approved" as recoverable.

        The worker maps `ConsentViolationError` to a terminal `PolicyFailure`.
        If an unapproved draft raised something else, a re-drive could be
        offered for a condition retrying cannot fix.
        """
        for kwargs in (
            {"recipient": _recipient(suppressed=True)},
            {"draft_status": DraftStatus.DRAFT},
            {"live_mode": True},
        ):
            with pytest.raises(ConsentViolationError):
                _allow(**kwargs)


# ---------------------------------------------------------------------------
# The vocabularies the rest of the slice is built on
# ---------------------------------------------------------------------------


class TestVocabularies:
    """Constants other layers pin themselves to."""

    def test_the_command_type_is_stable(self):
        """The router submits this string and the registry routes it.

        Pinned as a literal here so a rename has to come through a test diff,
        not just through two files that happen to agree.
        """
        assert OUTREACH_SEND_COMMAND_TYPE == "outreach.send"

    def test_no_send_disposition_claims_delivery(self):
        """A provider accepting custody is not a recipient receiving anything."""
        assert {d.value for d in SendDisposition} == {"accepted", "blocked", "failed"}
        assert "sent" not in {d.value for d in SendDisposition}
        assert "delivered" not in {d.value for d in SendDisposition}

    def test_the_delivery_stream_can_express_refusal_as_well_as_acceptance(self):
        """A blocked send must leave a trace; silence would look like no send."""
        assert DeliveryEventType.BLOCKED in set(DeliveryEventType)
        assert DeliveryEventType.DELIVERED in set(DeliveryEventType)
        assert DeliveryEventType.BOUNCED in set(DeliveryEventType)

    def test_every_shipped_template_is_synthetic_until_someone_reviews_it(self):
        """OQ-003. A template marked reviewed without a review is the hazard."""
        assert TEMPLATES
        assert all(
            template.content_status is ContentStatus.SYNTHETIC for template in TEMPLATES.values()
        )
