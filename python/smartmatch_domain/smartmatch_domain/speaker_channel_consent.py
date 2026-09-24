"""The Speaker's own consent on a contact channel (B26 T6b-3 plan §3.2).

A signed-in Speaker may opt in or opt out on each of their channels.

* **Opt-out** writes a ``speaker_portal`` suppression and does not move the
  lifecycle, so a later opt-in restores sending without research moves.
* **Opt-in** lifts what the Speaker may lift (``smartmatch_domain.suppression``)
  and walks the lifecycle to ``active_candidate`` with ``self_service`` consent,
  every move re-asked through ``consent.assert_transition``. The state graph is
  unchanged: a channel in a research state, ``rejected`` or ``stale`` has no
  edge to ``consented``, and the opt-in is refused (OQ-1).

**The Speaker wins.** A Connector may not undo the Speaker's latest choice:
after an opt-out it may not escalate the channel, and after an opt-in it may
not move it away from ``active_candidate`` (:func:`connector_transition_conflict`).
The Speaker's choice log decides these refusals only; suppression stays the one
send gate.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from smartmatch_domain.consent import ContactState, is_escalation

__all__ = [
    "OPT_IN_START_STATES",
    "SELF_SERVICE_EVIDENCE",
    "SELF_SERVICE_REASON",
    "SPEAKER_OPTED_IN",
    "SPEAKER_OPTED_OUT",
    "SPEAKER_WINS_MESSAGES",
    "OptInPath",
    "SpeakerChoice",
    "connector_transition_conflict",
    "opt_in_path",
]


class SpeakerChoice(StrEnum):
    """One entry of ``contact_channel_speaker_choice.choice``."""

    OPT_IN = "opt_in"
    OPT_OUT = "opt_out"


#: The states an opt-in may start from; any other state is ``409 opt_in_unavailable``.
OPT_IN_START_STATES: Final[frozenset[ContactState]] = frozenset(
    {ContactState.RELATIONSHIP_RECORDED, ContactState.CONSENTED, ContactState.ACTIVE_CANDIDATE}
)

#: Fixed server text, with no address and no id. The actor is on the row already.
SELF_SERVICE_EVIDENCE: Final[str] = "Speaker portal opt-in by the signed-in Speaker"
SELF_SERVICE_REASON: Final[str] = "Speaker opted in through the Speaker portal"

#: The Speaker-wins 409 codes, shared by every Connector surface that moves a channel.
SPEAKER_OPTED_OUT: Final[str] = "speaker_contact_channel_speaker_opted_out"
SPEAKER_OPTED_IN: Final[str] = "speaker_contact_channel_speaker_opted_in"

#: What a Connector reads with each code. No address, no id.
SPEAKER_WINS_MESSAGES: Final[Mapping[str, str]] = MappingProxyType(
    {
        SPEAKER_OPTED_OUT: (
            "The Speaker opted out of this address in the Speaker portal. A Connector "
            "may not move it toward a send; only the Speaker's own opt-in can."
        ),
        SPEAKER_OPTED_IN: (
            "The Speaker opted in to this address in the Speaker portal. A Connector "
            "may not suppress it, change its consent evidence or move it away from "
            "'active_candidate'; the Speaker can opt out themselves."
        ),
    }
)

OptInPath = tuple[tuple[ContactState, ContactState], ...]

_PATHS: Final[dict[ContactState, OptInPath]] = {
    ContactState.RELATIONSHIP_RECORDED: (
        (ContactState.RELATIONSHIP_RECORDED, ContactState.CONSENTED),
        (ContactState.CONSENTED, ContactState.ACTIVE_CANDIDATE),
    ),
    ContactState.CONSENTED: ((ContactState.CONSENTED, ContactState.ACTIVE_CANDIDATE),),
    ContactState.ACTIVE_CANDIDATE: (),
}


def opt_in_path(current: ContactState) -> OptInPath | None:
    """The lifecycle moves an opt-in makes from ``current``, or ``None`` when unavailable.

    An empty tuple means the channel is already ``active_candidate``: the
    opt-in only lifts, if a suppression stands.
    """
    return _PATHS.get(current)


def connector_transition_conflict(
    latest: SpeakerChoice | None, current: ContactState, requested: ContactState
) -> str | None:
    """The Speaker-wins code a Connector move hits, or ``None`` when today's rules apply.

    * Latest ``opt_out``: no move to ``consented`` or ``active_candidate``.
    * Latest ``opt_in``: no move away from ``active_candidate``.
    """
    if latest is SpeakerChoice.OPT_OUT and is_escalation(requested):
        return SPEAKER_OPTED_OUT
    if (
        latest is SpeakerChoice.OPT_IN
        and current is ContactState.ACTIVE_CANDIDATE
        and requested is not ContactState.ACTIVE_CANDIDATE
    ):
        return SPEAKER_OPTED_IN
    return None
