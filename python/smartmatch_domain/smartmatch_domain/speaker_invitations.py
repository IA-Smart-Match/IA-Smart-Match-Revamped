"""Role-owned invitation lifecycle rules."""

from __future__ import annotations

CONNECTOR_TRANSITIONS = {
    "not_emailed_yet": frozenset({"awaiting_response"}),
    "awaiting_response": frozenset({"declined", "ready_for_handoff"}),
    "ready_for_handoff": frozenset({"handed_off"}),
}
HOST_TRANSITIONS = {
    "handed_off": frozenset({"awaiting_final_confirmation"}),
    "awaiting_final_confirmation": frozenset({"confirmed", "withdrawn"}),
    "confirmed": frozenset({"withdrawn", "attended"}),
}
TERMINAL_STATUSES = frozenset(
    {"declined", "withdrawn", "attended", "did_not_attend", "event_cancelled"}
)
UNSAFE_CORRECTION_TARGETS = frozenset({"attended", "did_not_attend", "event_cancelled"})


def can_transition(role: str, current: str, target: str) -> bool:
    rules = (
        CONNECTOR_TRANSITIONS
        if role == "admin"
        else HOST_TRANSITIONS
        if role == "coordinator"
        else {}
    )
    return target in rules.get(current, frozenset())


def can_correct(current: str, target: str) -> bool:
    return current != "event_cancelled" and target not in UNSAFE_CORRECTION_TARGETS
