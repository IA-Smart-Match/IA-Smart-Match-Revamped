"""A team reads "asking", never "refreshing", in the exercise's sentences.

The product's word for design spec §13's once-only step is *asking* ("Ask them
now", "Your team has already asked", "Ask for every team"). Three server
sentences still said "refreshing" or "refresh", and the results page shows a
refusal in the server's own words, so a class read both terms for one button.

User-facing text only: the route path, the error codes, the response field
names and the database columns keep ``refresh``.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import smartmatch_api
import smartmatch_domain.exercise
import smartmatch_persistence.exercise
from fastapi.testclient import TestClient
from smartmatch_domain.exercise.simulation import SimulationCoefficients

from tests.unit.exercise_results_router.support import (
    _FINAL_BODY,
    _HEADER,
    _REFRESH,
    _RESULTS,
    _Fakes,
    _seed_choice,
)

#: Keyword arguments whose string is a sentence a person reads.
_SENTENCE_KEYWORDS = frozenset({"message", "refusal"})


def _exercise_sources() -> Iterator[Path]:
    api = Path(smartmatch_api.__file__).parent
    yield from sorted(api.glob("exercise_*.py"))
    yield from sorted((api / "routers").glob("exercise_*.py"))
    yield from sorted(Path(smartmatch_domain.exercise.__file__).parent.glob("*.py"))
    yield from sorted(Path(smartmatch_persistence.exercise.__file__).parent.glob("*.py"))


def _literal(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            part.value
            for part in node.values
            if isinstance(part, ast.Constant) and isinstance(part.value, str)
        )
    return None


def _sentences() -> Iterator[tuple[str, str]]:
    for path in _exercise_sources():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg in _SENTENCE_KEYWORDS:
                    text = _literal(keyword.value)
                    if text is not None:
                        yield f"{path.name}:{keyword.value.lineno}", text


def test_the_scan_reads_the_sentences_it_guards() -> None:
    found = dict(_sentences())
    assert len(found) > 20
    assert "Your team has already asked the people it invited." in found.values()


def test_no_exercise_sentence_says_refresh() -> None:
    offenders = [(where, text) for where, text in _sentences() if "refresh" in text.lower()]
    assert offenders == []


def test_asking_before_choosing_is_refused_in_the_products_words(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    fakes.unlock("round-one")
    client.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER)

    response = client.post(_REFRESH, json={}, headers=_HEADER)

    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "exercise_asking_not_chosen",
        "message": "Pick a way of asking first.",
    }


def test_asking_before_the_first_round_is_refused_in_the_products_words(
    fakes: _Fakes,
    client: TestClient,
) -> None:
    _seed_choice(fakes, 1)

    response = client.post(_REFRESH, json={}, headers=_HEADER)

    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "exercise_no_first_round_results",
        "message": "Run the first round's results before asking.",
    }
