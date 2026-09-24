"""The Speaker's opt-in path and the Speaker-wins rule (B26 T6b-3 plan §3.2)."""

from __future__ import annotations

import re

import pytest
from smartmatch_domain.consent import STATE_TRANSITIONS, ContactState, can_transition
from smartmatch_domain.speaker_channel_consent import (
    OPT_IN_START_STATES,
    SELF_SERVICE_EVIDENCE,
    SELF_SERVICE_REASON,
    SPEAKER_OPTED_IN,
    SPEAKER_OPTED_OUT,
    SpeakerChoice,
    connector_transition_conflict,
    opt_in_path,
)

_S = ContactState


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        (
            _S.RELATIONSHIP_RECORDED,
            ((_S.RELATIONSHIP_RECORDED, _S.CONSENTED), (_S.CONSENTED, _S.ACTIVE_CANDIDATE)),
        ),
        (_S.CONSENTED, ((_S.CONSENTED, _S.ACTIVE_CANDIDATE),)),
        (_S.ACTIVE_CANDIDATE, ()),
        (_S.DISCOVERED, None),
        (_S.CORROBORATED, None),
        (_S.REVIEWED, None),
        (_S.REJECTED, None),
        (_S.STALE, None),
    ],
)
def test_opt_in_path(current: ContactState, expected: object) -> None:
    assert opt_in_path(current) == expected
    assert (current in OPT_IN_START_STATES) == (expected is not None)


def test_opt_in_path_covers_every_state() -> None:
    assert len(ContactState) == 8
    assert OPT_IN_START_STATES == {_S.RELATIONSHIP_RECORDED, _S.CONSENTED, _S.ACTIVE_CANDIDATE}


@pytest.mark.parametrize("current", list(ContactState))
def test_every_opt_in_move_is_a_legal_edge(current: ContactState) -> None:
    path = opt_in_path(current)
    if path is None:
        return
    for prev, nxt in path:
        assert can_transition(prev, nxt)
    if path:
        assert path[0][0] is current
        assert path[-1][1] is _S.ACTIVE_CANDIDATE
        for (_, a), (b, _) in zip(path, path[1:], strict=False):
            assert a is b


_LEGAL_MOVES = [(cur, req) for cur, allowed in STATE_TRANSITIONS.items() for req in sorted(allowed)]


@pytest.mark.parametrize("latest", [None, SpeakerChoice.OPT_IN, SpeakerChoice.OPT_OUT])
@pytest.mark.parametrize(("current", "requested"), _LEGAL_MOVES)
def test_connector_conflict(
    latest: SpeakerChoice | None, current: ContactState, requested: ContactState
) -> None:
    code = connector_transition_conflict(latest, current, requested)
    if latest is SpeakerChoice.OPT_OUT and requested in {_S.CONSENTED, _S.ACTIVE_CANDIDATE}:
        assert code == SPEAKER_OPTED_OUT
    elif latest is SpeakerChoice.OPT_IN and current is _S.ACTIVE_CANDIDATE:
        assert code == SPEAKER_OPTED_IN
    else:
        assert code is None


def test_conflict_codes() -> None:
    assert SPEAKER_OPTED_OUT == "speaker_contact_channel_speaker_opted_out"
    assert SPEAKER_OPTED_IN == "speaker_contact_channel_speaker_opted_in"


def test_evidence_and_reason_carry_no_address_or_id() -> None:
    for text in (SELF_SERVICE_EVIDENCE, SELF_SERVICE_REASON):
        assert text.strip() == text and text
        assert "@" not in text
        assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}", text)
        assert not re.search(r"\d", text)
    assert SELF_SERVICE_EVIDENCE == "Speaker portal opt-in by the signed-in Speaker"
    assert SELF_SERVICE_REASON == "Speaker opted in through the Speaker portal"
