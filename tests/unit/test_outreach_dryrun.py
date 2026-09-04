"""The outreach dry run composes only for the eligible, and sends nothing.

`test_consent.py` already covers the lifecycle rules themselves. What is
covered here is the composition layer on top of them: that the gate is actually
called (and called *before* any message text exists), that a successful result
is structured evidence rather than a receipt, and that the template registry
offers no way to solicit consent from someone who has not given it.
"""

from __future__ import annotations

import pytest
from smartmatch_domain.consent import (
    APPROVED_CONSENT_SOURCES,
    ConsentSource,
    ConsentViolationError,
    ContactState,
)
from smartmatch_domain.outreach_dryrun import (
    DRY_RUN_DISPOSITION,
    ELIGIBILITY_RULE,
    TEMPLATES,
    DryRunRecipient,
    OutreachCompositionError,
    compose_dry_run,
    get_template,
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


def _recipient(**overrides: object) -> DryRunRecipient:
    """An eligible synthetic recipient, unless a test says otherwise."""
    base: dict[str, object] = {
        "address": _SYNTHETIC_ADDRESS,
        "contact_state": ContactState.ACTIVE_CANDIDATE,
        "consent_source": ConsentSource.SELF_SERVICE,
        "suppressed": False,
    }
    base.update(overrides)
    return DryRunRecipient(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Research-discovered addresses are refused
# ---------------------------------------------------------------------------


class TestRefusal:
    """Nothing is composed for a recipient who may not be contacted."""

    @pytest.mark.parametrize(
        "state",
        [
            ContactState.DISCOVERED,
            ContactState.CORROBORATED,
            ContactState.REVIEWED,
            ContactState.RELATIONSHIP_RECORDED,
            ContactState.REJECTED,
            ContactState.CONSENTED,
            ContactState.STALE,
        ],
    )
    def test_a_recipient_short_of_active_candidate_is_refused(self, state: ContactState):
        """Research evidence about a person is never permission to contact them."""
        with pytest.raises(ConsentViolationError, match="not 'active_candidate'"):
            compose_dry_run(
                recipient=_recipient(contact_state=state),
                template_id=_TEMPLATE_ID,
                values=_VALUES,
            )

    @pytest.mark.parametrize(
        "source",
        [ConsentSource.SCRAPED, ConsentSource.PURCHASED, ConsentSource.INFERRED],
    )
    def test_an_unapproved_consent_source_is_refused(self, source: ConsentSource):
        with pytest.raises(ConsentViolationError, match="is not approved"):
            compose_dry_run(
                recipient=_recipient(consent_source=source),
                template_id=_TEMPLATE_ID,
                values=_VALUES,
            )

    def test_a_missing_consent_source_is_refused_rather_than_assumed(self):
        """Unknown is not "probably fine" (ADR-0011)."""
        with pytest.raises(ConsentViolationError, match="is not approved"):
            compose_dry_run(
                recipient=_recipient(consent_source=None),
                template_id=_TEMPLATE_ID,
                values=_VALUES,
            )

    def test_a_suppressed_recipient_is_refused_despite_approved_consent(self):
        with pytest.raises(ConsentViolationError, match="suppressed"):
            compose_dry_run(
                recipient=_recipient(suppressed=True),
                template_id=_TEMPLATE_ID,
                values=_VALUES,
            )

    def test_the_gate_runs_before_the_template_is_even_resolved(self):
        """An ineligible recipient never reaches composition at all.

        Both inputs are bad here. The consent failure is the one that surfaces,
        which is only true if eligibility is asserted first — so this pins the
        ordering, not just the outcome.
        """
        with pytest.raises(ConsentViolationError):
            compose_dry_run(
                recipient=_recipient(consent_source=ConsentSource.SCRAPED),
                template_id="does.not.exist",
                values={},
            )


# ---------------------------------------------------------------------------
# A successful dry run is structured evidence, never a receipt
# ---------------------------------------------------------------------------


class TestSuccessfulDryRun:
    """What an eligible recipient produces."""

    def test_the_disposition_is_would_send_and_never_sent(self):
        result = compose_dry_run(recipient=_recipient(), template_id=_TEMPLATE_ID, values=_VALUES)

        assert result.disposition == DRY_RUN_DISPOSITION == "would_send"
        assert result.disposition != "sent"

    def test_the_result_carries_recipient_subject_template_and_body(self):
        result = compose_dry_run(recipient=_recipient(), template_id=_TEMPLATE_ID, values=_VALUES)

        assert result.recipient_address == _SYNTHETIC_ADDRESS
        assert result.template_id == _TEMPLATE_ID
        assert result.subject == "Spring Showcase on Friday, 12 June"
        assert "Hello Sam Rivera," in result.body
        assert "Northside Robotics" in result.body
        # Nothing left unresolved: a half-rendered message is a defect, not a draft.
        assert "$" not in result.subject
        assert "$" not in result.body

    def test_the_result_carries_the_eligibility_evidence_it_was_gated_by(self):
        result = compose_dry_run(
            recipient=_recipient(consent_source=ConsentSource.IN_PERSON),
            template_id=_TEMPLATE_ID,
            values=_VALUES,
        )

        assert result.evidence.contact_state is ContactState.ACTIVE_CANDIDATE
        assert result.evidence.consent_source is ConsentSource.IN_PERSON
        assert result.evidence.consent_source_is_approved is True
        assert result.evidence.suppressed is False
        assert result.evidence.checked_by == ELIGIBILITY_RULE

    def test_a_synthetic_address_is_recorded_as_such(self):
        result = compose_dry_run(recipient=_recipient(), template_id=_TEMPLATE_ID, values=_VALUES)

        assert result.recipient_address_is_reserved_invalid is True

    def test_a_deliverable_looking_address_is_flagged_but_not_a_gate(self):
        """The reserved-TLD flag is evidence, not permission.

        A consented recipient at a real-looking address still composes; the
        result simply records that the address is not on the reserved TLD. The
        consent lifecycle is the gate, and it is the only gate.
        """
        result = compose_dry_run(
            recipient=_recipient(address="person@example.edu"),
            template_id=_TEMPLATE_ID,
            values=_VALUES,
        )

        assert result.recipient_address_is_reserved_invalid is False

    @pytest.mark.parametrize("source", sorted(APPROVED_CONSENT_SOURCES))
    def test_every_approved_consent_source_composes(self, source: ConsentSource):
        result = compose_dry_run(
            recipient=_recipient(consent_source=source),
            template_id=_TEMPLATE_ID,
            values=_VALUES,
        )

        assert result.evidence.consent_source is source

    def test_the_result_is_immutable(self):
        """A composed dry run cannot be edited into something else afterwards."""
        result = compose_dry_run(recipient=_recipient(), template_id=_TEMPLATE_ID, values=_VALUES)

        with pytest.raises((AttributeError, TypeError)):
            result.disposition = "sent"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# The template registry is closed, and contains no consent solicitation
# ---------------------------------------------------------------------------


class TestTemplates:
    """What can and cannot be composed at all."""

    def test_an_unknown_template_is_refused_rather_than_treated_as_text(self):
        with pytest.raises(OutreachCompositionError, match="unknown outreach template"):
            compose_dry_run(recipient=_recipient(), template_id="free.form", values=_VALUES)

    def test_every_template_presumes_consent_already_exists(self):
        """No "invite to consent" path, by construction.

        `consent.py`: an email asking a scraped address to opt in is itself
        prohibited outreach. This asserts the registry offers no such message
        today and fails if one is ever added.
        """
        assert TEMPLATES
        assert all(template.presumes_existing_consent for template in TEMPLATES.values())

    @pytest.mark.parametrize("template_id", sorted(TEMPLATES))
    def test_no_template_text_solicits_consent(self, template_id: str):
        template = get_template(template_id)
        text = f"{template.subject}\n{template.body}".lower()

        for solicitation in ("opt in", "opt-in", "subscribe", "sign up", "consent"):
            assert solicitation not in text

    @pytest.mark.parametrize("template_id", sorted(TEMPLATES))
    def test_a_templates_declared_placeholders_match_its_text(self, template_id: str):
        """The declared contract and the actual `$name` uses cannot drift."""
        template = get_template(template_id)
        text = f"{template.subject} {template.body}"

        for name in template.placeholders:
            assert f"${name}" in text

        # And the text introduces nothing the contract does not declare: with
        # exactly the declared names supplied, rendering resolves completely.
        rendered = compose_dry_run(
            recipient=_recipient(),
            template_id=template_id,
            values=dict.fromkeys(template.placeholders, "x"),
        )
        assert "$" not in rendered.subject
        assert "$" not in rendered.body

    def test_missing_placeholder_values_are_refused_not_left_blank(self):
        partial = {k: v for k, v in _VALUES.items() if k != "event_date"}

        with pytest.raises(OutreachCompositionError, match=r"missing \['event_date'\]"):
            compose_dry_run(recipient=_recipient(), template_id=_TEMPLATE_ID, values=partial)

    def test_unexpected_placeholder_values_are_refused(self):
        with pytest.raises(OutreachCompositionError, match=r"unexpected \['smuggled'\]"):
            compose_dry_run(
                recipient=_recipient(),
                template_id=_TEMPLATE_ID,
                values={**_VALUES, "smuggled": "value"},
            )

    def test_the_registry_cannot_be_mutated_by_a_caller(self):
        with pytest.raises(TypeError):
            TEMPLATES["pilot.rogue.v1"] = get_template(_TEMPLATE_ID)  # type: ignore[index]
