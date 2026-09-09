"""Source contract for the Connector weights panel (TRACK 6).

``docs/plans/open-questions/cba-phase-deferred.md`` §"Connector weights UI"
deferred this surface in writing and, in the same breath, named what a later
panel owes. This file is that entry turned into assertions, because the entry's
central warning is about a mistake nobody makes deliberately:

    "must not print a registry default as a placeholder — the response's
    ``modes`` is where an effective weight comes from, and a placeholder typed
    into a form would be the duplicated default this whole card exists to
    prevent."

A weight typed into a form's ``placeholder`` or ``defaultValue`` looks like a
courtesy and is in fact a second copy of the registry, one that keeps showing
yesterday's approved figure the day ADR-0016 revises it. So the strongest check
here is lexical and blunt: **no float literal anywhere in the panel's code.**
There is no honest reason for one — every number this page renders arrived in a
response.

The other three obligations, in the entry's own order:

* **``expected_version`` round-trips.** Read from ``GET``, sent on ``PATCH``,
  and a ``409 matching_weights_stale`` surfaced as a conflict the Connector
  resolves — never a silent retry with a refreshed version, which is the lost
  update the refusal exists to prevent.
* **``ignored_factor_keys`` is rendered.** A key the unit stored that no current
  registry model admits is reported by the server rather than dropped; a panel
  that drops it re-hides what the route went out of its way to surface.
* **The modes come from the response.** ``modes`` is derived server-side per
  request and deliberately never persisted. The browser renders it and does not
  recompute, renormalize, or total it.

Plus the standing rules this repository already keeps: no match percentage
(OQ-CBA-005), no ``fetchSpecialists``/``/api/data/*``, no fake success
(``docs/plans/frontend-broken-buttons.md``), and a UI gate that is not
authorization — the route is ``{admin, coordinator}`` server-side and a ``403``
is an answer to render, not a control to hide.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src"

API_LIB = FRONTEND_SRC / "lib" / "api.ts"
WEIGHTS_PAGE = FRONTEND_SRC / "app" / "pages" / "coordinator" / "CoordinatorMatchingWeights.tsx"
ROUTES = FRONTEND_SRC / "app" / "routes.tsx"


#: A float literal in the program text — the shape a weight takes.
#:
#: The lookbehind keeps Tailwind's own decimals out of it (``gap-1.5``,
#: ``opacity-0.5`` are always preceded by a hyphen) and keeps dotted
#: identifiers out too, so this fires on a number and not on a class name.
_FLOAT_LITERAL = re.compile(r"(?<![\w.\-/])\d+\.\d+")


def _code_only(source: str) -> str:
    """Strip block comments and line comments. Prose is not code."""
    without_blocks = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return "\n".join(
        line for line in without_blocks.splitlines() if not line.lstrip().startswith("//")
    )


def _helper_body(source: str, name: str) -> str:
    """The source of one exported helper, from its signature to its closing brace."""
    marker = f"export async function {name}"
    assert marker in source, f"api.ts is missing {name}"
    return source.split(marker, 1)[1].split("\n}", 1)[0]


def _interface_body(source: str, name: str) -> str:
    marker = f"export interface {name}"
    assert marker in source, f"api.ts is missing the {name} type"
    return source.split(marker, 1)[1].split("\n}", 1)[0]


# ---------------------------------------------------------------------------
# The client helpers
# ---------------------------------------------------------------------------


def test_api_lib_reads_the_weights_and_the_version_it_is_editing() -> None:
    source = API_LIB.read_text(encoding="utf-8")
    helper = _helper_body(source, "fetchMatchingWeights")

    assert "/matching-weights" in helper
    assert "encodeURIComponent(unitId)" in helper, (
        "the unit id must be encoded into the path, never concatenated raw"
    )
    assert 'method: "GET"' in helper
    assert "authenticated: true" in helper, (
        "the route is admin/coordinator only; the helper must send the bearer token"
    )


def test_api_lib_sends_the_expected_version_on_the_write() -> None:
    source = API_LIB.read_text(encoding="utf-8")
    helper = _helper_body(source, "updateMatchingWeights")

    assert "/matching-weights" in helper
    assert 'method: "PATCH"' in helper, "the route is a PATCH; a PUT is a different contract"
    assert "authenticated: true" in helper

    payload = _interface_body(source, "MatchingWeightsUpdatePayload")
    assert "overrides" in payload
    assert "expected_version" in payload, (
        "without expected_version the write is last-write-wins and the 409 can never fire"
    )


def test_the_response_type_mirrors_what_the_route_returns() -> None:
    """Every field the panel owes a rendering of must exist on the type."""
    source = API_LIB.read_text(encoding="utf-8")
    body = _interface_body(source, "MatchingWeights")

    for field in (
        "unit_id",
        "registry_version",
        "configurable_factors",
        "overrides",
        "modes",
        "version",
        "ignored_factor_keys",
    ):
        assert field in body, f"MatchingWeights is missing {field!r}"

    mode = _interface_body(source, "ScoringModeWeights")
    for field in ("scoring_mode", "registry_version", "weights"):
        assert field in mode, f"ScoringModeWeights is missing {field!r}"


def test_the_client_types_carry_no_weight_literal() -> None:
    """No ``= 0.25`` default hiding in a client type."""
    source = _code_only(API_LIB.read_text(encoding="utf-8"))
    for name in ("MatchingWeights", "ScoringModeWeights", "MatchingWeightsUpdatePayload"):
        body = _interface_body(source, name)
        assert _FLOAT_LITERAL.search(body) is None, (
            f"{name} carries a numeric literal; a weight belongs to the registry and to the "
            "unit's stored overrides, never to a client type"
        )


# ---------------------------------------------------------------------------
# The panel — no default may be printed here
# ---------------------------------------------------------------------------


def test_the_panel_exists() -> None:
    assert WEIGHTS_PAGE.exists(), f"expected the Connector weights panel at {WEIGHTS_PAGE}"


def test_the_panel_contains_no_weight_literal() -> None:
    """The deferral entry's central prohibition, checked lexically.

    A float in this file is either a placeholder default, a renormalization
    constant, or a percentage — and all three are forbidden. There is no fourth
    kind, so the whole class is refused rather than each instance argued about.
    Copy is scanned along with code: "the industry weight is normally 0.30"
    prints the default just as effectively as an input's ``placeholder`` does.
    """
    code = _code_only(WEIGHTS_PAGE.read_text(encoding="utf-8"))
    found = _FLOAT_LITERAL.findall(code)
    assert found == [], (
        f"the weights panel contains numeric literal(s) {found}; every weight it shows must "
        "come from the server's response, and a printed default is the duplication the "
        "matching-weights card exists to prevent"
    )


def test_the_panel_never_placeholders_or_defaults_an_input() -> None:
    """An unset override reads as unset. It is not pre-filled with a guess."""
    code = _code_only(WEIGHTS_PAGE.read_text(encoding="utf-8"))
    assert "placeholder=" not in code, (
        "a placeholder on a weight input is exactly the printed registry default the "
        "deferral entry forbids"
    )
    assert "defaultValue" not in code, (
        "a defaultValue seeds the form with something the server did not send"
    )


def test_the_panel_states_that_an_unset_factor_is_unset() -> None:
    source = WEIGHTS_PAGE.read_text(encoding="utf-8")
    assert re.search(r"[Nn]ot set|\bunset\b", source), (
        "a factor with no stored override must be shown as unset rather than filled in"
    )


def test_the_panel_round_trips_the_expected_version() -> None:
    code = _code_only(WEIGHTS_PAGE.read_text(encoding="utf-8"))
    assert "fetchMatchingWeights" in code
    assert "updateMatchingWeights" in code
    assert "expected_version" in code, "the PATCH must carry the version the read returned"
    assert ".version" in code, "the version sent must be the one the response carried"


def test_the_panel_surfaces_the_stale_conflict_rather_than_retrying() -> None:
    """409 is a conflict a person resolves, not a retry a page performs."""
    code = _code_only(WEIGHTS_PAGE.read_text(encoding="utf-8"))
    assert "matching_weights_stale" in code, (
        "the panel must recognise the 409 by its code and say what happened"
    )
    assert "409" in code
    for forbidden in ("retry", "retryCount", "reapplyAutomatically"):
        assert forbidden not in code, (
            f"{forbidden!r} suggests the panel re-sends the write with a refreshed version; "
            "that is the lost update the 409 exists to prevent"
        )


def test_the_panel_renders_the_servers_own_validation_message() -> None:
    code = _code_only(WEIGHTS_PAGE.read_text(encoding="utf-8"))
    assert "invalid_matching_weights" in code, (
        "the 422 names every offending field at once; the panel renders that message"
    )
    assert "ApiRequestError" in code
    assert "cause.message" in code or "error.message" in code, (
        "the refusal shown must be the server's own words, not a message composed here"
    )


def test_the_panel_renders_ignored_factor_keys() -> None:
    code = _code_only(WEIGHTS_PAGE.read_text(encoding="utf-8"))
    assert "ignored_factor_keys" in code, (
        "the server reports retired keys rather than dropping them; a panel that drops them "
        "re-hides what the route surfaced"
    )


def test_the_panel_renders_modes_from_the_response_without_recomputing() -> None:
    code = _code_only(WEIGHTS_PAGE.read_text(encoding="utf-8"))
    assert "modes" in code, "the effective weights are read from the response's modes"
    for forbidden in ("normalize", "renormalize", "reduce(", "Math.round", "toFixed", "* 100"):
        assert forbidden not in code, (
            f"{forbidden!r} computes a weight in the browser; effective weights are derived "
            "server-side and deliberately never persisted"
        )


def test_the_panel_shows_no_percentage_and_no_legacy_reads() -> None:
    code = _code_only(WEIGHTS_PAGE.read_text(encoding="utf-8"))
    assert "%" not in code, "OQ-CBA-005: no percentage rendering on a CBA surface"
    for forbidden in ("fetchSpecialists", "/api/data", "AgenticOutreachPanel", "match_score"):
        assert forbidden not in code, f"{forbidden!r} has no place on a CBA path"


def test_the_panel_confirms_from_the_response_and_says_no_run_moves() -> None:
    """No fake success, and no implied re-scoring.

    A stored ``match_run`` carries the weights it was scored with and nothing in
    the route touches it. A Connector who changes a weight and is not told that
    must be assumed to think their shortlist just changed.
    """
    source = WEIGHTS_PAGE.read_text(encoding="utf-8")
    assert re.search(r"does not (re-?run|change|alter)", source, re.IGNORECASE), (
        "the panel must say that changing weights does not re-run or alter a stored match run"
    )
    code = _code_only(source)
    assert "await updateMatchingWeights" in code, (
        "the saved state must come from the awaited server response, never from the form"
    )


def test_the_panel_treats_a_refusal_as_an_answer_not_a_hidden_control() -> None:
    """A UI gate is display only; the permit is ``_authorize_matching_weights``."""
    code = _code_only(WEIGHTS_PAGE.read_text(encoding="utf-8"))
    assert "403" in code, "the server's refusal is rendered rather than pre-empted"


# ---------------------------------------------------------------------------
# The route
# ---------------------------------------------------------------------------


def test_the_route_is_mounted_in_the_connector_portal() -> None:
    routes = ROUTES.read_text(encoding="utf-8")
    assert "CoordinatorMatchingWeights" in routes
    assert "matching-weights" in routes
