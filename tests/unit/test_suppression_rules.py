"""The suppression rank model and the Speaker's lift rule (B26 T6b-3 plan §3.1).

``suppression_record`` keeps one row per address. These tests prove that the
single row, merged by rank, answers every lift question exactly as a model that
kept one row per source would, for both kinds of address: the Speaker's login
address (where an unsubscribe may be lifted) and any other address (where only
the Speaker's own opt-out may be).
"""

from __future__ import annotations

import itertools
import re
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

import pytest
from smartmatch_domain.suppression import (
    LIFTABLE_BY_SPEAKER,
    NEVER_LIFTED,
    SOURCE_RANK,
    LiftOutcome,
    MergeAction,
    SuppressionSource,
    SuppressionState,
    SuppressionWrite,
    liftable_sources,
    merge_suppression,
    speaker_facing_reason,
    speaker_lift_verdict,
)
from smartmatch_persistence import schema

_T0 = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
_SEND = uuid.UUID("00000000-0000-0000-0000-00000000abcd")


def _check_sql(name: str) -> str:
    for constraint in schema.suppression_record.constraints:
        if constraint.name == name:
            return str(constraint.sqltext)  # type: ignore[attr-defined]
    raise AssertionError(f"no constraint {name}")


def _quoted(text: str) -> set[str]:
    return set(re.findall(r"'([a-z_]+)'", text))


def _active(source: SuppressionSource, at: datetime = _T0) -> SuppressionState:
    return SuppressionState(source=source, suppressed_at=at, lifted_at=None, origin_send_id=None)


def _lifted(source: SuppressionSource, at: datetime = _T0) -> SuppressionState:
    return SuppressionState(
        source=source, suppressed_at=at, lifted_at=at + timedelta(hours=1), origin_send_id=None
    )


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------


def test_source_vocabulary_matches_the_check() -> None:
    assert {s.value for s in SuppressionSource} == _quoted(
        _check_sql("ck_suppression_record_source")
    )
    assert {s.value for s in LIFTABLE_BY_SPEAKER} == _quoted(
        _check_sql("ck_suppression_record_lift_source")
    )
    assert set(SOURCE_RANK) == set(SuppressionSource)
    assert frozenset(SuppressionSource) - LIFTABLE_BY_SPEAKER == NEVER_LIFTED
    assert {
        SuppressionSource.BOUNCE,
        SuppressionSource.COMPLAINT,
        SuppressionSource.COORDINATOR,
    } == NEVER_LIFTED


@pytest.mark.parametrize("address_is_login", [True, False])
def test_liftable_sources_are_a_rank_prefix_for_both_address_kinds(address_is_login: bool) -> None:
    allowed = liftable_sources(address_is_login=address_is_login)
    threshold = max(SOURCE_RANK[s] for s in allowed)
    assert allowed == {s for s in SuppressionSource if SOURCE_RANK[s] <= threshold}
    assert allowed <= LIFTABLE_BY_SPEAKER
    if address_is_login:
        assert allowed == LIFTABLE_BY_SPEAKER
    else:
        assert allowed == {SuppressionSource.SPEAKER_PORTAL}


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("incoming", list(SuppressionSource))
def test_merge_onto_nothing_inserts(incoming: SuppressionSource) -> None:
    write = merge_suppression(None, incoming, at=_T0, origin_send_id=_SEND)
    assert write.action is MergeAction.INSERT
    assert (write.source, write.suppressed_at, write.origin_send_id) == (incoming, _T0, _SEND)


@pytest.mark.parametrize("existing", list(SuppressionSource))
@pytest.mark.parametrize("incoming", list(SuppressionSource))
def test_merge_onto_a_lifted_row_reopens(
    existing: SuppressionSource, incoming: SuppressionSource
) -> None:
    later = _T0 + timedelta(days=1)
    write = merge_suppression(_lifted(existing), incoming, at=later, origin_send_id=None)
    assert write.action is MergeAction.REOPEN
    assert (write.source, write.suppressed_at, write.origin_send_id) == (incoming, later, None)


@pytest.mark.parametrize("existing", list(SuppressionSource))
@pytest.mark.parametrize("incoming", list(SuppressionSource))
def test_merge_onto_an_active_row_escalates_only_upward(
    existing: SuppressionSource, incoming: SuppressionSource
) -> None:
    later = _T0 + timedelta(days=1)
    write = merge_suppression(_active(existing), incoming, at=later, origin_send_id=_SEND)
    if SOURCE_RANK[incoming] > SOURCE_RANK[existing]:
        assert write.action is MergeAction.ESCALATE
        assert write.source is incoming
        assert write.origin_send_id == _SEND
        # "When did they first ask us to stop" is kept.
        assert write.suppressed_at == _T0
    else:
        assert write.action is MergeAction.NOOP
        assert write.source is existing
        assert write.suppressed_at == _T0


# ---------------------------------------------------------------------------
# The Speaker's lift verdict (OQ-3)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("source", list(SuppressionSource))
@pytest.mark.parametrize("row", ["none", "active", "lifted"])
@pytest.mark.parametrize("address_is_login", [True, False])
def test_speaker_lift_verdict(source: SuppressionSource, row: str, address_is_login: bool) -> None:
    existing = {"none": None, "active": _active(source), "lifted": _lifted(source)}[row]
    verdict = speaker_lift_verdict(existing, address_is_login=address_is_login)
    if row != "active":
        assert verdict.outcome is LiftOutcome.NOTHING_TO_LIFT
        assert verdict.reason is None
        return
    if source is SuppressionSource.SPEAKER_PORTAL:
        assert verdict.outcome is LiftOutcome.LIFT
    elif source in {SuppressionSource.UNSUBSCRIBE_LINK, SuppressionSource.ONE_CLICK}:
        if address_is_login:
            assert verdict.outcome is LiftOutcome.LIFT
        else:
            assert verdict.outcome is LiftOutcome.REFUSED
            assert verdict.reason == "unverified_address"
    elif source is SuppressionSource.COORDINATOR:
        assert verdict.outcome is LiftOutcome.REFUSED
        assert verdict.reason == "connector"
    else:
        assert verdict.outcome is LiftOutcome.REFUSED
        assert verdict.reason == "delivery"
    if verdict.outcome is LiftOutcome.LIFT:
        assert verdict.allowed_sources == liftable_sources(address_is_login=address_is_login)
        assert source in verdict.allowed_sources
    else:
        assert verdict.allowed_sources == frozenset()


@pytest.mark.parametrize(
    "source", [SuppressionSource.UNSUBSCRIBE_LINK, SuppressionSource.ONE_CLICK]
)
def test_unsubscribe_sources_lift_only_on_the_login_address(source: SuppressionSource) -> None:
    assert speaker_lift_verdict(_active(source), address_is_login=True).outcome is LiftOutcome.LIFT
    refused = speaker_lift_verdict(_active(source), address_is_login=False)
    assert (refused.outcome, refused.reason) == (LiftOutcome.REFUSED, "unverified_address")


@pytest.mark.parametrize("source", sorted(NEVER_LIFTED))
@pytest.mark.parametrize("address_is_login", [True, False])
def test_never_lifted_sources_are_refused_everywhere(
    source: SuppressionSource, address_is_login: bool
) -> None:
    verdict = speaker_lift_verdict(_active(source), address_is_login=address_is_login)
    assert verdict.outcome is LiftOutcome.REFUSED


def test_speaker_opt_out_over_an_unsubscribe_elsewhere_does_not_hide_it() -> None:
    """Regression for the rank order: speaker_portal ranks below the unsubscribes."""
    state = _apply(
        None,
        merge_suppression(None, SuppressionSource.UNSUBSCRIBE_LINK, at=_T0, origin_send_id=None),
    )
    state = _apply(
        state,
        merge_suppression(state, SuppressionSource.SPEAKER_PORTAL, at=_T0, origin_send_id=None),
    )
    assert state is not None
    assert state.source is SuppressionSource.UNSUBSCRIBE_LINK
    verdict = speaker_lift_verdict(state, address_is_login=False)
    assert (verdict.outcome, verdict.reason) == (LiftOutcome.REFUSED, "unverified_address")


def test_speaker_facing_reason_covers_every_source() -> None:
    expected = {
        SuppressionSource.BOUNCE: "delivery",
        SuppressionSource.COMPLAINT: "delivery",
        SuppressionSource.COORDINATOR: "connector",
        SuppressionSource.UNSUBSCRIBE_LINK: "unsubscribed",
        SuppressionSource.ONE_CLICK: "unsubscribed",
        SuppressionSource.SPEAKER_PORTAL: "your_opt_out",
    }
    for source, reason in expected.items():
        assert speaker_facing_reason(_active(source)) == reason
        assert speaker_facing_reason(_lifted(source)) is None
    assert speaker_facing_reason(None) is None


# ---------------------------------------------------------------------------
# One row loses no lift decision: exhaustive comparison with a per-source model
# ---------------------------------------------------------------------------

_LIFT = "speaker_lift"
_EVENTS: tuple[SuppressionSource | str, ...] = (*SuppressionSource, _LIFT)


def _apply(state: SuppressionState | None, write: SuppressionWrite) -> SuppressionState | None:
    if write.action is MergeAction.NOOP:
        return state
    return SuppressionState(
        source=write.source,
        suppressed_at=write.suppressed_at,
        lifted_at=None,
        origin_send_id=write.origin_send_id,
    )


@dataclass(frozen=True)
class _Model:
    """One row per source: which sources stand right now."""

    active: frozenset[SuppressionSource] = frozenset()

    def verdict(self, *, address_is_login: bool) -> tuple[LiftOutcome, str | None]:
        if not self.active:
            return LiftOutcome.NOTHING_TO_LIFT, None
        allowed = liftable_sources(address_is_login=address_is_login)
        blocking = self.active - allowed
        if not blocking:
            return LiftOutcome.LIFT, None
        top = max(blocking, key=lambda s: SOURCE_RANK[s])
        reason = {
            SuppressionSource.BOUNCE: "delivery",
            SuppressionSource.COMPLAINT: "delivery",
            SuppressionSource.COORDINATOR: "connector",
        }.get(top, "unverified_address")
        return LiftOutcome.REFUSED, reason


@pytest.mark.parametrize("address_is_login", [True, False])
def test_single_row_merge_matches_the_per_source_model(address_is_login: bool) -> None:
    cases = 0
    for sequence in itertools.product(_EVENTS, repeat=4):
        cases += 1
        row: SuppressionState | None = None
        model = _Model()
        clock = _T0
        for event in sequence:
            clock += timedelta(minutes=1)
            if event == _LIFT:
                verdict = speaker_lift_verdict(row, address_is_login=address_is_login)
                expected = model.verdict(address_is_login=address_is_login)
                assert (verdict.outcome, verdict.reason) == expected, sequence
                if verdict.outcome is LiftOutcome.LIFT:
                    assert row is not None
                    assert row.source in verdict.allowed_sources
                    row = replace(row, lifted_at=clock)
                    model = _Model()
            else:
                assert isinstance(event, SuppressionSource)
                row = _apply(row, merge_suppression(row, event, at=clock, origin_send_id=None))
                model = _Model(model.active | {event})
            row_active = row is not None and row.lifted_at is None
            assert row_active == bool(model.active), sequence
            assert (
                speaker_lift_verdict(row, address_is_login=address_is_login).outcome
                == model.verdict(address_is_login=address_is_login)[0]
            ), sequence
    assert cases == 7**4
