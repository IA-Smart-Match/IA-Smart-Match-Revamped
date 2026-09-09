import pytest
from smartmatch_domain.speaker_invitations import can_correct, can_transition


@pytest.mark.parametrize(
    ("role", "current", "target"),
    [
        ("admin", "not_emailed_yet", "awaiting_response"),
        ("admin", "awaiting_response", "declined"),
        ("admin", "awaiting_response", "ready_for_handoff"),
        ("admin", "ready_for_handoff", "handed_off"),
        ("coordinator", "handed_off", "awaiting_final_confirmation"),
        ("coordinator", "awaiting_final_confirmation", "confirmed"),
        ("coordinator", "awaiting_final_confirmation", "withdrawn"),
        ("coordinator", "confirmed", "withdrawn"),
        ("coordinator", "confirmed", "attended"),
    ],
)
def test_approved_transitions(role, current, target):
    assert can_transition(role, current, target)


def test_roles_cannot_cross_ownership_boundary():
    assert not can_transition("coordinator", "awaiting_response", "ready_for_handoff")
    assert not can_transition("admin", "handed_off", "awaiting_final_confirmation")


@pytest.mark.parametrize("target", ["attended", "did_not_attend", "event_cancelled"])
def test_corrections_cannot_fabricate_terminal_event_evidence(target):
    assert not can_correct("confirmed", target)


def test_cancelled_record_cannot_be_corrected():
    assert not can_correct("event_cancelled", "confirmed")
