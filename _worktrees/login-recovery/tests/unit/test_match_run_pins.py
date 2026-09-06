"""The pure half of card M8a: what a run is pinned to, and how it is fingerprinted.

Nothing here needs a database. The properties under test are the ones a stored
``match_run`` row depends on being true — that identical inputs fingerprint
identically, that different inputs do not, and that a blank pin is refused
before it can reach a column — plus the payload reading that stands between a
persisted command and the write.

Every digest is derived at runtime and asserted structurally. Pinning one to a
hex literal would make this file a transcription exercise: the assertion would
pass or fail on whether somebody copied 64 characters correctly, and it would
have to be re-copied every time an unrelated field moved.
"""

from __future__ import annotations

import pytest
from smartmatch_domain.match_run import (
    MATCH_RUN_COMMAND_TYPE,
    ROUTE_ESTIMATE_SOURCES,
    MatchRunPins,
    inputs_fingerprint,
    weights_fingerprint,
)
from smartmatch_worker.handlers import PolicyFailure, _read_match_run_command, default_registry

#: A synthetic need and pool. The values are invented for this file and mean
#: nothing outside it, which is the standing rule for pilot fixtures.
NEED = "need-synthetic-1"
POOL_SUBJECTS = ("prof-synthetic-a", "prof-synthetic-b", "prof-synthetic-c")
POOL_UTILITIES = (0.82, 0.4, 0.61)
WEIGHTS = {"topic_relevance": 0.6, "travel_burden": 0.4}

#: ``"sha256:"`` plus 64 hex characters.
_DIGEST_LENGTH = 71


def _fingerprint(**overrides: object) -> str:
    """Fingerprint the synthetic pool, with named fields replaced."""
    arguments: dict[str, object] = {
        "event_need_id": NEED,
        "candidate_subject_ids": POOL_SUBJECTS,
        "candidate_utilities": POOL_UTILITIES,
        "portfolio_size": 2,
        "random_seed": 0,
        "weights": WEIGHTS,
    }
    arguments.update(overrides)
    return inputs_fingerprint(**arguments)  # type: ignore[arg-type]


def _pins(**overrides: str) -> MatchRunPins:
    """Build a valid pin record, with named fields replaced."""
    fields = {
        "registry_version": "1.1.1-approved-g1-m6j",
        "registry_hash": weights_fingerprint(WEIGHTS),
        "optimizer_model_version": "1.0.0-cpsat",
        "solver_name": "ortools-cpsat",
        "solver_version": "9.99.0",
        "route_estimate_source": "straight_line",
        "route_estimate_version": "1.0.0-straight-line",
    }
    fields.update(overrides)
    return MatchRunPins(**fields)


# ---------------------------------------------------------------------------
# Fingerprints
# ---------------------------------------------------------------------------


def test_a_digest_names_its_algorithm():
    """A bare hex string is a hash of nothing in particular; the prefix is the claim."""
    digest = _fingerprint()
    assert digest.startswith("sha256:")
    assert len(digest) == _DIGEST_LENGTH


def test_identical_inputs_fingerprint_identically():
    """The property the whole column exists for."""
    assert _fingerprint() == _fingerprint()


def test_pool_order_does_not_change_the_fingerprint():
    """`solve_portfolio` is order-independent, so the digest must be too.

    Two callers listing the same pool in different orders are posing the
    identical problem. A digest that disagreed would report a difference the
    solver does not have, and every scenario comparison built on it would show a
    coordinator two runs as unlike when they are the same run.
    """
    assert (
        _fingerprint(
            candidate_subject_ids=tuple(reversed(POOL_SUBJECTS)),
            candidate_utilities=tuple(reversed(POOL_UTILITIES)),
        )
        == _fingerprint()
    )


def test_a_reshuffled_pairing_is_a_different_problem():
    """Order-independence is about the *pairs*, not the two lists separately.

    Reversing the subjects while leaving the utilities in place gives every
    candidate somebody else's score. That is a genuinely different problem and
    must fingerprint differently — a digest that folded the two lists in
    separately would call it the same one.
    """
    assert _fingerprint(candidate_subject_ids=tuple(reversed(POOL_SUBJECTS))) != _fingerprint()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("event_need_id", "need-synthetic-2"),
        ("portfolio_size", 3),
        ("random_seed", 7),
        ("candidate_subject_ids", POOL_SUBJECTS[:2]),
        ("weights", {"topic_relevance": 0.7, "travel_burden": 0.3}),
    ],
)
def test_every_input_moves_the_fingerprint(field, value):
    """Each argument is an input the answer actually depends on.

    ``candidate_subject_ids`` is shortened in step with its utilities, so that
    case reads as "a smaller pool" rather than as a length mismatch.
    """
    overrides: dict[str, object] = {field: value}
    if field == "candidate_subject_ids":
        overrides["candidate_utilities"] = POOL_UTILITIES[:2]
    assert _fingerprint(**overrides) != _fingerprint()


def test_a_weight_change_in_the_fourth_decimal_is_visible():
    """Rounding before hashing would make the MM-005 weight gate unenforceable.

    The worksheet gates every weight change behind shadow evaluation. A digest
    that collapsed near-identical weights would let a change through the gate
    while the stored pins claimed nothing had changed.
    """
    nudged = {"topic_relevance": 0.6001, "travel_burden": 0.3999}
    assert weights_fingerprint(nudged) != weights_fingerprint(WEIGHTS)


def test_weight_order_does_not_change_the_fingerprint():
    """`active_weights` returns a mapping; its iteration order is not a fact about the run."""
    reordered = {"travel_burden": 0.4, "topic_relevance": 0.6}
    assert weights_fingerprint(reordered) == weights_fingerprint(WEIGHTS)


def test_a_pool_whose_lists_disagree_is_refused():
    """Silently zipping to the shorter list would fingerprint a pool nobody submitted."""
    with pytest.raises(ValueError, match="same length"):
        _fingerprint(candidate_utilities=POOL_UTILITIES[:2])


# ---------------------------------------------------------------------------
# Pins
# ---------------------------------------------------------------------------


def test_valid_pins_construct():
    assert _pins().route_estimate_source in ROUTE_ESTIMATE_SOURCES


@pytest.mark.parametrize(
    "field",
    [
        "registry_version",
        "registry_hash",
        "optimizer_model_version",
        "solver_name",
        "solver_version",
        "route_estimate_version",
    ],
)
def test_a_blank_pin_is_refused_rather_than_stored(field):
    """ADR-0011 at the assembly point: an unknown version is not an empty string.

    Whitespace rather than ``""`` deliberately — a NOT NULL column accepts both,
    and a writer that trimmed nothing would store a value that looks present.
    """
    with pytest.raises(ValueError, match=f"{field}: must not be empty or blank"):
        _pins(**{field: "   "})


def test_every_blank_pin_is_named_at_once():
    """A caller fixing an assembly defect should see the whole list."""
    with pytest.raises(ValueError) as raised:
        _pins(registry_version="", solver_name="")
    message = str(raised.value)
    assert "registry_version" in message
    assert "solver_name" in message


def test_an_unrecognised_route_estimate_source_is_refused():
    """The vocabulary is closed so a stored run cannot claim a provider that never ran.

    ``route_matrix`` names the deferred D3 provider. A run recording some third
    value would be unreadable the day D3 lands, which is the point of recording
    it at all.
    """
    with pytest.raises(ValueError, match="route_estimate_source"):
        _pins(route_estimate_source="a-provider-that-does-not-exist")


def test_pins_are_frozen():
    """A pin that could be reassigned after assembly is not a pin."""
    pins = _pins()
    with pytest.raises(AttributeError):
        pins.registry_version = "2.0.0"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Reading a persisted payload
# ---------------------------------------------------------------------------


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "event_need_id": NEED,
        "portfolio_size": 2,
        "random_seed": 0,
        "candidates": [
            {"subject_id": subject, "utility": utility}
            for subject, utility in zip(POOL_SUBJECTS, POOL_UTILITIES, strict=True)
        ],
    }
    payload.update(overrides)
    return payload


def test_a_well_formed_payload_reads():
    command = _read_match_run_command(_payload())
    assert command.event_need_id == NEED
    assert command.portfolio_size == 2
    assert [candidate.subject_id for candidate in command.candidates] == list(POOL_SUBJECTS)


def test_the_payload_carries_no_unit_id():
    """The unit is an authorization input and comes from the job row, never the body.

    Asserted as an absence because that is what the guarantee is: if a
    ``unit_id`` ever appears on ``MatchRunCommand``, somebody has made a caller
    able to name the subtree their own run is filed under, and therefore who may
    later read it.
    """
    command = _read_match_run_command(_payload())
    assert not hasattr(command, "unit_id")


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"event_need_id": "  "}, "event_need_id"),
        ({"portfolio_size": "two"}, "portfolio_size"),
        ({"portfolio_size": 0}, "portfolio_size"),
        # bool is a subclass of int, and `True` would otherwise read as 1.
        ({"portfolio_size": True}, "portfolio_size"),
        ({"random_seed": -1}, "random_seed"),
        ({"candidates": []}, "candidates"),
        ({"candidates": "prof-synthetic-a"}, "candidates"),
        ({"candidates": [{"subject_id": "prof-synthetic-a"}]}, "utility"),
        ({"candidates": [{"subject_id": "prof-synthetic-a", "utility": True}]}, "utility"),
        ({"candidates": [{"subject_id": "prof-synthetic-a", "utility": 1.5}]}, "utility"),
        ({"candidates": [{"utility": 0.5}]}, "subject_id"),
    ],
)
def test_an_unreadable_payload_is_a_terminal_policy_failure(overrides, expected):
    """Terminal, not re-drivable: the payload is durable and a retry re-reads it."""
    with pytest.raises(PolicyFailure) as raised:
        _read_match_run_command(_payload(**overrides))
    assert raised.value.reason == "invalid_command_payload"
    assert expected in str(raised.value)


def test_a_duplicate_candidate_is_refused_as_a_payload_problem():
    """PortfolioRequest would raise on this; catching it here names the field."""
    duplicated = [
        {"subject_id": "prof-synthetic-a", "utility": 0.8},
        {"subject_id": "prof-synthetic-a", "utility": 0.2},
    ]
    with pytest.raises(PolicyFailure, match="duplicate subject_id"):
        _read_match_run_command(_payload(candidates=duplicated))


def test_every_bad_candidate_is_reported_not_just_the_first():
    """One bad entry must not hide the next; a pool of forty needs the whole list."""
    with pytest.raises(PolicyFailure) as raised:
        _read_match_run_command(
            _payload(
                candidates=[
                    {"subject_id": "prof-synthetic-a", "utility": 2.0},
                    {"subject_id": "prof-synthetic-b", "utility": "high"},
                ]
            )
        )
    message = str(raised.value)
    assert "candidates[0]" in message
    assert "candidates[1]" in message


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


def test_the_shipped_registry_can_execute_a_match_run():
    """Registered before its routes exist, because it can genuinely execute or refuse.

    Card M8b adds the HTTP surface. Registering the handler opens none: no route
    submits this command type, so the only way to create one is to insert a job
    directly, which is what the integration tests do.
    """
    assert MATCH_RUN_COMMAND_TYPE in default_registry().command_types
