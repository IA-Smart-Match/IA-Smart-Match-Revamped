"""The results screen's routes: the approval, the lock, the final setting.

Split by topic from ``tests/unit/test_exercise_results_router.py`` (past
the 800-line cap); shared fakes are in ``support.py`` and fixtures in
``conftest.py`` beside this file. Together the ``test_exercise_results_*``
files here pin the routes of CE-RESULTS-API (design spec §9–§13).

What is pinned here, in the order the failures would hurt:

1. **The three rules.** A locked event refuses; a second run is refused with the
   sentence design spec §9 writes out, byte for byte; a refresh needs the choice
   and is allowed once.
2. **The refusal path survives the approval.** With no coefficient set the run
   route refuses with the domain's own sentence (the shipped set is approved,
   wave-2 decision D7, so this is patched in). Every test
   that needs a result injects a clearly-labelled test-only coefficient set
   through ``monkeypatch``; no value is written into any source file.
3. **Determinism and the shared seed.** The same inputs and the same seed give
   the same panels, and "email everyone" agrees with the team's own list on
   every profile they share — which is what makes them a comparison.
4. **Isolation.** One team's refresh changes one team's overlay.
5. **Nothing a response may never carry**: a schema walk over every model in
   both modules, over the handlers' docstrings — FastAPI publishes those as
   operation descriptions — and over the whole exercise-scope OpenAPI document,
   refusing ``hidden_true_interests`` (ADR-0025 D6) and anything score-shaped
   (D8).

The database half — the one-run rule as a UNIQUE constraint against two
concurrent runs, the lock order, and a reset clearing the rows it says it clears
— is in ``tests/integration/test_exercise_results_persistence.py``. A fake
repository cannot prove a constraint.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from smartmatch_api.main import routers_for
from smartmatch_api.routers import (
    exercise_results,
)
from smartmatch_api.routers.exercise_results_models import (
    EXERCISE_ROUNDS,
    FIRST_ROUND,
    round_of,
)
from smartmatch_domain.exercise.simulation import (
    SimulationCoefficients,
)
from smartmatch_persistence.exercise.results_repository import (
    ALREADY_RUN_SENTENCE,
)

from tests.unit.exercise_results_router.support import (
    _BASE,
    _EVENTS,
    _FINAL,
    _FINAL_BODY,
    _FINAL_SETTING_SENTENCE,
    _HEADER,
    _INVITE_LIMIT,
    _MODELS_SOURCE,
    _REFRESH_SOURCE,
    _RESULTS,
    _ROUTER_SOURCE,
    _ROWS,
    _TRACK_SOURCES,
    _entered,
    _Fakes,
    _settings,
)

# ---------------------------------------------------------------------------
# The shipped set is approved (D7); the refusal path still works
# ---------------------------------------------------------------------------


def test_a_run_refuses_while_the_rule_has_no_confirmed_coefficients(
    fakes: _Fakes, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal path, kept working: with no coefficient set the route refuses.

    The exercise ships the approved set (D7, closing OQ-CE-03), so ``None`` is
    patched in here rather than being what ships.
    """
    monkeypatch.setattr(
        "smartmatch_domain.exercise.simulation.EXERCISE_SIMULATION_COEFFICIENTS", None
    )
    fakes.unlock("round-one")

    response = client.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER)

    assert response.status_code == 409
    body = response.json()["error"]
    assert body["code"] == "exercise_results_rule_not_confirmed"
    assert body["message"] == "The results rule has no confirmed coefficients yet."
    assert "OQ-CE-" not in body["message"], "a register ID is not a sentence for a team"
    assert fakes.results.runs == {}, "a refused run must store nothing"


def test_no_module_in_this_track_writes_down_a_coefficient_or_a_share() -> None:
    """The eight coefficients and the three shares are Ann's, not this track's."""
    for source_file in _TRACK_SOURCES:
        source = source_file.read_text(encoding="utf-8")
        for guess in ("0.30", "0.55", "0.80", "0.15", "= 0.5", "base_signup_rate ="):
            assert guess not in source, f"{source_file.name} writes down {guess!r}"


def test_no_module_in_this_track_writes_down_a_class_year_or_a_major() -> None:
    """The vocabularies live in ``smartmatch_domain.exercise.vocabulary``; the
    routers restate none of them, so there is one list to change."""
    for source_file in _TRACK_SOURCES:
        source = source_file.read_text(encoding="utf-8")
        for guess in ("Senior", "Junior", "Sophomore", "Freshman", "Finance", "Marketing"):
            assert guess not in source, f"{source_file.name} writes down {guess!r}"


def test_no_exercise_router_puts_a_register_id_in_a_refusal() -> None:
    """CE-INSTRUCTOR-UNLOCK: "(OQ-CE-03)" reached students in a refusal.

    Register IDs belong in comments and docstrings, where the next engineer
    reads them, and never in a sentence a team or the instructor reads. Every
    literal passed as ``message=`` in an exercise router is checked.
    """
    routers = Path(exercise_results.__file__).parent
    offenders: list[str] = []
    for source_file in sorted(routers.glob("exercise_*.py")):
        tree = ast.parse(source_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.keyword) or node.arg != "message":
                continue
            for part in ast.walk(node.value):
                if isinstance(part, ast.Constant) and "OQ-CE-" in str(part.value):
                    offenders.append(f"{source_file.name}:{part.lineno}")
    assert offenders == []


def test_no_exercise_exception_raised_below_the_routers_carries_a_register_id() -> None:
    """The leak that happened: a domain exception's text passed on as ``str(error)``.

    The routers pass domain and persistence refusal text through verbatim, so
    every string literal inside a ``raise`` in those two packages is a sentence
    somebody may read.
    """
    from smartmatch_domain.exercise import simulation
    from smartmatch_persistence.exercise import instructor_repository

    offenders: list[str] = []
    for package in (Path(simulation.__file__).parent, Path(instructor_repository.__file__).parent):
        for source_file in sorted(package.glob("*.py")):
            tree = ast.parse(source_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Raise) or node.exc is None:
                    continue
                for part in ast.walk(node.exc):
                    if isinstance(part, ast.Constant) and "OQ-CE-" in str(part.value):
                        offenders.append(f"{package.name}/{source_file.name}:{part.lineno}")
    assert offenders == []


def test_the_closed_questions_left_no_placeholder_marker() -> None:
    for source in (_MODELS_SOURCE, _ROUTER_SOURCE):
        assert "PLACEHOLDER (OQ-CE-03)" not in source.read_text(encoding="utf-8"), "D7"
    refresh_source = _REFRESH_SOURCE.read_text(encoding="utf-8")
    assert "PLACEHOLDER (OQ-CE-04)" not in refresh_source, "OQ-CE-04 closed 2026-09-25"
    assert "round half up" in refresh_source


# ---------------------------------------------------------------------------
# The lock and the one-run rule (design spec §9)
# ---------------------------------------------------------------------------


def test_a_locked_event_is_refused_with_a_sentence(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    response = client.post(_RESULTS, json={}, headers=_HEADER)

    assert response.status_code == 409
    body = response.json()["error"]
    assert body["code"] == "exercise_results_locked"
    # Ann, 2026-10-02: "Results for Harbor are not open yet. Ask your
    # instructor." — her sentence, with the event named as the file spells it.
    assert body["message"] == "Results for The first round are not open yet. Ask your instructor."
    assert fakes.results.runs == {}


def test_an_unlocked_event_runs_and_stores_the_three_panels(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    fakes.unlock("round-one")

    response = client.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["event_key"] == "round-one"
    assert body["round"] == FIRST_ROUND
    assert body["setting_name"] == _FINAL
    assert body["team"]["invited_count"] == _INVITE_LIMIT
    assert body["email_everyone"]["invited_count"] == len(_ROWS)
    assert body["round_one"] is None, "round one has no earlier round to compare with"
    assert len(fakes.results.runs) == 1


def test_a_second_run_is_refused_with_the_specs_own_sentence(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    """Design spec §9 writes this sentence out; it is compared byte for byte."""
    fakes.unlock("round-one")
    assert client.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER).status_code == 201

    response = client.post(_RESULTS, json={}, headers=_HEADER)

    assert response.status_code == 409
    body = response.json()["error"]
    assert body["code"] == "exercise_results_already_run"
    assert body["message"] == "This team has already run results for this event."
    assert body["message"] == ALREADY_RUN_SENTENCE


def test_a_team_that_already_ran_is_told_so_after_results_are_closed_again(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    """D16 amendment, 2026-10-06: already run is answered before locked.

    Results can be closed again. A team that ran while they were open has had
    its one run; "not open yet" would tell it to wait for a second one.
    """
    fakes.unlock("round-one")
    assert client.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER).status_code == 201
    fakes.lock("round-one")

    again = client.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER)

    assert again.status_code == 409
    assert again.json()["error"]["code"] == "exercise_results_already_run"
    assert again.json()["error"]["message"] == ALREADY_RUN_SENTENCE
    assert len(fakes.results.runs) == 1


def test_closing_results_again_refuses_a_new_run_and_keeps_a_stored_one_readable(
    fakes: _Fakes, confirmed: SimulationCoefficients
) -> None:
    """Closing deletes nothing: only a team that has not run is turned away."""
    fakes.unlock("round-one")
    with _entered(fakes, 1) as ran, _entered(fakes, 2) as late:
        stored = ran.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER)
        assert stored.status_code == 201
        fakes.lock("round-one")

        refused = late.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER)
        kept = ran.get(_RESULTS)

    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "exercise_results_locked"
    assert refused.json()["error"]["message"] == (
        "Results for The first round are not open yet. Ask your instructor."
    )
    assert kept.status_code == 200
    assert kept.json()["team"] == stored.json()["team"]


def test_a_close_that_lands_while_a_run_is_computing_still_refuses_the_run(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    """Review round 2: the route reads "open" once, before the rule runs.

    The close here lands right after that read, as an instructor's press does
    while a team's run is computing. The write re-reads the state under the
    results key, so the run is refused with the same sentence and nothing is
    stored. The real interleaving is the integration file's.
    """
    fakes.unlock("round-one")
    read_open = fakes.results.results_unlocked

    def open_then_closed(session: object, **where: object) -> bool:
        answer = read_open(session, **where)  # type: ignore[arg-type]
        fakes.lock("round-one")
        return answer

    fakes.results.results_unlocked = open_then_closed  # type: ignore[method-assign]

    response = client.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER)

    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "exercise_results_locked",
        "message": "Results for The first round are not open yet. Ask your instructor.",
    }
    assert "refresh" not in response.json()["error"]["message"].lower()
    assert fakes.results.runs == {}, "a refused run must store nothing"


def test_the_sentence_is_the_repositorys_and_is_not_restated_in_the_router() -> None:
    """One copy of the words, so a reword cannot change the spec in one place."""
    assert "already run results" not in _ROUTER_SOURCE.read_text(encoding="utf-8")


def test_a_past_event_is_not_one_of_the_rounds(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    """``exercise_result_run.round`` admits 1 and 2, so a past event has nothing
    to store — and that is a sentence rather than a constraint violation."""
    fakes.unlock("past-analytics")

    response = client.post(f"{_BASE}/events/past-analytics/results", json={}, headers=_HEADER)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "exercise_event_is_not_a_round"


def test_an_event_from_another_data_file_is_not_found(
    client: TestClient, confirmed: SimulationCoefficients
) -> None:
    response = client.post(f"{_BASE}/events/not-in-this-file/results", json={}, headers=_HEADER)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "exercise_event_unknown"


def test_the_round_is_read_off_the_data_file_rather_than_from_a_name() -> None:
    """Round one is the first exercise event by sequence; no name is written down."""
    assert round_of(_EVENTS, "round-one") == 1
    assert round_of(_EVENTS, "round-two") == EXERCISE_ROUNDS
    assert round_of(_EVENTS, "past-analytics") is None
    # Shuffled input, same answer: the order comes from `sequence`, not from the
    # order the repository happened to return.
    assert round_of(tuple(reversed(_EVENTS)), "round-one") == 1


# ---------------------------------------------------------------------------
# The final setting (Ann to Chau, Discord, 2026-09-24)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [{}, {"setting_name": None}, {"setting_name": ""}, {"setting_name": "   "}],
    ids=["left-out", "null", "empty", "blank"],
)
def test_a_run_without_a_final_setting_is_refused_with_a_sentence(
    fakes: _Fakes,
    client: TestClient,
    confirmed: SimulationCoefficients,
    body: Mapping[str, object],
) -> None:
    """Step three of the owner's flow: the team chooses one final setting.

    There is no longer a run on the course's starting values. A team that wants
    them saves them under a name, which is the same act as choosing any other
    final setting.
    """
    fakes.unlock("round-one")

    response = client.post(_RESULTS, json=body, headers=_HEADER)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "exercise_final_setting_required"
    assert error["message"] == _FINAL_SETTING_SENTENCE
    assert fakes.results.runs == {}, "a refused run must store nothing"


def test_a_run_with_no_body_at_all_is_refused_with_the_same_sentence(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    fakes.unlock("round-one")

    response = client.post(_RESULTS, headers=_HEADER)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "exercise_final_setting_required"
    assert fakes.results.runs == {}


def test_the_final_setting_is_trimmed_before_it_is_looked_up_and_stored(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    fakes.unlock("round-one")

    response = client.post(_RESULTS, json={"setting_name": f"  {_FINAL} "}, headers=_HEADER)

    assert response.status_code == 201, response.text
    assert response.json()["setting_name"] == _FINAL


# -- the order of the refusals ------------------------------------------------
#
# The event's own state is answered first, whatever the body says: a sentence
# about the body is only useful once the event can actually be run. The body is
# answered before the missing-coefficients refusal, which (if the approved set
# were ever removed) would refuse every run — after it, the team's own step
# would be unreachable.


def test_an_unknown_event_is_answered_before_a_missing_final_setting(
    client: TestClient, confirmed: SimulationCoefficients
) -> None:
    response = client.post(f"{_BASE}/events/not-in-this-file/results", json={}, headers=_HEADER)

    assert response.json()["error"]["code"] == "exercise_event_unknown"


def test_a_past_event_is_answered_before_a_missing_final_setting(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    fakes.unlock("past-analytics")

    response = client.post(f"{_BASE}/events/past-analytics/results", json={}, headers=_HEADER)

    assert response.json()["error"]["code"] == "exercise_event_is_not_a_round"


def test_a_locked_event_is_answered_before_a_missing_final_setting(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    """Choosing a setting would not open the event; the lock is the true answer."""
    response = client.post(_RESULTS, json={}, headers=_HEADER)

    assert response.json()["error"]["code"] == "exercise_results_locked"


def test_an_event_already_run_is_answered_before_a_missing_final_setting(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    """Asking a team that has run to choose a setting would invite a second try."""
    fakes.unlock("round-one")
    assert client.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER).status_code == 201

    response = client.post(_RESULTS, json={}, headers=_HEADER)

    assert response.json()["error"]["code"] == "exercise_results_already_run"


def test_a_missing_final_setting_is_answered_before_the_unconfirmed_rule(
    fakes: _Fakes, client: TestClient
) -> None:
    """No ``confirmed`` fixture: this is the order a team meets on this deployment."""
    fakes.unlock("round-one")

    response = client.post(_RESULTS, json={}, headers=_HEADER)

    assert response.json()["error"]["code"] == "exercise_final_setting_required"


def test_the_published_request_names_the_final_setting_as_required() -> None:
    """The contract a client is generated from says what the route enforces."""
    app = FastAPI()
    for router in routers_for(_settings()):
        app.include_router(router)
    document = app.openapi()
    schema = document["components"]["schemas"]["RunResultsRequest"]
    operation = document["paths"]["/v1/exercise/workspaces/current/events/{event_key}/results"][
        "post"
    ]

    assert operation["requestBody"]["required"] is True
    assert operation["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/RunResultsRequest"
    }
    assert schema["required"] == ["setting_name"]
    assert schema["properties"]["setting_name"]["type"] == "string"
    assert schema["properties"]["setting_name"]["minLength"] == 1
    assert "starting values" not in schema["properties"]["setting_name"]["description"]
