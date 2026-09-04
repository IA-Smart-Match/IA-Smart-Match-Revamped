"""Executable fail-closed contracts for gated product surfaces.

G1 (matching/scoring), G3 (crawler/event catalog), and D6 (shippable rewards)
remain intentionally closed until named human decisions land. These tests pin
the absence of HTTP capability and domain guards without substituting for
workshop approval.

## The G3 event-catalog flip (card P-EVENTS-API)

Two read-only routes now exist where this file previously asserted none:
``GET /v1/units/{unit_id}/events`` and
``GET /v1/units/{unit_id}/tag-quarantine``. That is a deliberate flip, made in
the commit that lands the capability, which is the rule
``docs/plans/2026-08-28-plan-portfolio-index.md`` states for this file — "each
deliberate flip happens in the commit that lands the gated capability", naming
P6·S6b among the four that would do it — and the shape card S6b prescribes:
"routes, policy-matrix rows, OpenAPI regeneration, and the deliberate flip of
the fail-closed scan, all in one commit."

## The G1 match-run flip (card P-MATCH-API)

Two routes now exist where this file previously asserted that no match/score/
rank path could: ``POST /v1/units/{unit_id}/match-runs`` and
``GET /v1/units/{unit_id}/match-runs/{match_run_id}``. That is a deliberate
flip made in the commit that lands the capability, on the authority of three
committed artifacts and no judgement of this file's own:

* ``docs/plans/workshops/g1-workshop-output-worksheet.md`` — gate G1's output,
  ratified 2026-09-03 by the named program owner, fixing the factor list, the
  weights, the golden-case ADR-0011 classifications, and the presentation rules
  (2-3 speakers, no percentage display).
* ``docs/plans/2026-08-28-g1-matching-m1-m10-plan.md`` card **M8b** — the card
  that authorizes routes at all, and which states the rule this file is being
  changed under: "Update the fail-closed OpenAPI scan in the same commit the
  routes land — that is its deliberate flip."
* ``smartmatch_domain.factor_registry`` at ``REGISTRY_STATUS == "approved"``
  with ``assert_scoring_ready()`` passing, which card M6j made the condition
  for scoring to run at all.

The flip is **narrower than the gate it opens**, in the same shape card
P-EVENTS-API used. :data:`_G1_FORBIDDEN_SEGMENTS` is *widened* rather than
relaxed — ``match-run`` and ``match-runs`` are added to it, so the two paths
below are refused by the segment rule and admitted only by name — and
:data:`G1_AUTHORIZED_MATCH_RUN_PATHS` is an exact, literal allowlist of two
paths. A third match-run path, or a ``/v1/units/{unit_id}/matches``, fails here
whether or not anyone regenerated the contract.
:func:`test_the_match_run_router_declares_exactly_the_authorized_routes` holds
the router to the same list from the other side, and
:func:`test_the_match_run_router_exposes_one_command_and_one_read` pins the
methods, because "a coordinator may ask for a shortlist and read one back" is
what was authorized — not a surface that could grow a decision endpoint.

What the flip does **not** open is the part G3 actually gates. The forbidden
segment families below are untouched: no ``crawl``, ``crawler``, ``crawlers``
or ``discovery`` path may exist, ``POST /api/crawler/start`` remains a named
non-goal, and ``tests/unit/test_fixture_ingest_wiring.py`` still holds the API
away from the ingest reader entirely. The two routes admitted here read rows a
worker already wrote from committed fixtures; they trigger nothing, accept no
URL, and make no network call. :data:`G3_AUTHORIZED_EVENT_PATHS` is an exact,
literal allowlist of two paths rather than a loosened pattern, and
:func:`test_the_authorized_event_routes_are_read_only` holds them to being
reads — so this gate cannot widen into a command surface without failing here.
"""

from __future__ import annotations

import json
from pathlib import Path

from smartmatch_api.routers import engagement, events, match_runs
from smartmatch_domain.factor_registry import (
    REGISTRY_STATUS,
    assert_registry_approved,
)

OPENAPI_PATH = Path(__file__).resolve().parents[2] / "contracts" / "openapi" / "smartmatch.json"

# G1 — forbidden path segments until D1/G1 program owner approves the registry.
# ``match-run``/``match-runs`` are listed even though card P-MATCH-API landed
# exactly those paths, and that is the point: the allowlist below is what admits
# them, so it is load-bearing rather than decorative. Without these two entries
# ``/v1/units/{unit_id}/match-runs`` would sail past this scan on the technicality
# that ``"match-runs" != "match"``, and every future match-run path would too.
_G1_FORBIDDEN_SEGMENTS = frozenset(
    {
        "match",
        "match-run",
        "match-runs",
        "match_run",
        "match_runs",
        "matches",
        "matching",
        "score",
        "scores",
        "scoring",
        "rank",
        "ranks",
        "ranking",
    }
)

# G3 — forbidden path segments until G3 control decision + R3 threat-model sign-off.
_G3_FORBIDDEN_SEGMENTS = frozenset(
    {
        "crawl",
        "crawler",
        "crawlers",
        "discovery",
    }
)

# D6 — forbidden path segments until D6/D7 budget owners ratify catalog + S6/S7 exist.
_D6_FORBIDDEN_SEGMENTS = frozenset(
    {
        "reward",
        "rewards",
        "redemption",
        "redemptions",
        "balance",
        "balances",
        "catalog",
    }
)


# G3 — the exact unit-scoped event paths card P-EVENTS-API authorizes, and no
# others. A literal set rather than a prefix or a pattern: a pattern would
# admit whatever a future route happened to hang under `/v1/units/*/events`,
# including a POST that triggered extraction, and the point of a fail-closed
# scan is that widening it is a visible edit to a named list. Both are reads,
# which `test_the_authorized_event_routes_are_read_only` checks rather than
# assumes.
G3_AUTHORIZED_EVENT_PATHS = frozenset(
    {
        "/v1/units/{unit_id}/events",
        "/v1/units/{unit_id}/tag-quarantine",
    }
)


# G1 — the exact unit-scoped match-run paths card P-MATCH-API authorizes, and
# no others. Every segment family this gate guards is *still* forbidden, these
# two paths included: `_G1_FORBIDDEN_SEGMENTS` names `match-runs`, so admitting
# them is a deliberate, by-name exception rather than a gap in the pattern. A
# third match-run path fails here, and so does a path that differs from one of
# these by a single segment.
G1_AUTHORIZED_MATCH_RUN_PATHS = frozenset(
    {
        "/v1/units/{unit_id}/match-runs",
        "/v1/units/{unit_id}/match-runs/{match_run_id}",
    }
)


def _path_segments(path: str) -> list[str]:
    """Return literal path segments, ignoring ``{param}`` placeholders."""
    return [
        segment for segment in path.strip("/").split("/") if segment and not segment.startswith("{")
    ]


def _forbidden_gate_for_path(path: str) -> str | None:
    """Return the gate id blocking ``path``, or None when the path is allowed."""
    segments = [segment.lower() for segment in _path_segments(path)]

    # The by-name exception comes first, and is the single place a match-run
    # path is admitted. G1's allowlist has to precede the segment loop rather
    # than follow it (as G3's does) because `_G1_FORBIDDEN_SEGMENTS`
    # deliberately contains `match-runs`: the loop below refuses these paths.
    # A path not spelled out here gets no such exception, which is the property
    # that keeps the flip narrow.
    if path in G1_AUTHORIZED_MATCH_RUN_PATHS:
        return None

    for segment in segments:
        if segment in _G1_FORBIDDEN_SEGMENTS:
            return "G1"
        if segment in _G3_FORBIDDEN_SEGMENTS:
            return "G3"
        if segment in _D6_FORBIDDEN_SEGMENTS:
            return "D6"

    # The two reads card P-EVENTS-API landed. Checked before the rule below
    # and by exact path, so every *other* unit-scoped event path stays refused
    # — including one that differed from these by a single segment.
    if path in G3_AUTHORIZED_EVENT_PATHS:
        return None

    # G3 unit-scoped event catalog — distinct from durable-command job lifecycle events.
    if "units" in segments:
        unit_index = segments.index("units")
        if unit_index + 1 < len(segments) and segments[unit_index + 1] == "events":
            return "G3"

    return None


def test_registry_status_is_approved():
    """G1 gate closed 2026-09-03 — Danny Tran ratified factor registry."""
    assert REGISTRY_STATUS == "approved"


def test_assert_registry_approved_succeeds():
    """G1 guard passes after program-owner approval."""
    assert_registry_approved()


def test_engagement_router_declares_no_handlers():
    """D6 is untouched by the G3 flip and still ships no handler at all."""
    assert engagement.router.routes == [], (
        "D6: engagement handlers must not ship before D6/D7 + S6/S7"
    )


def test_the_events_router_declares_exactly_the_authorized_routes():
    """The G3 flip is bounded by a list, not by the router's own contents.

    Before card P-EVENTS-API this asserted ``events.router.routes == []``. The
    honest successor is not "the events router may now declare things" — that
    would be a gate replaced by nothing — but an exact equality against
    :data:`G3_AUTHORIZED_EVENT_PATHS`. A third route added to this router fails
    here whether or not anyone regenerated the contract, which is the property
    the original assertion actually provided.
    """
    declared = {str(route.path) for route in events.router.routes}  # type: ignore[attr-defined]

    assert declared == G3_AUTHORIZED_EVENT_PATHS, (
        "G3: the events router declares routes outside the P-EVENTS-API "
        f"allowlist: {sorted(declared - G3_AUTHORIZED_EVENT_PATHS)}"
    )


def test_the_authorized_event_routes_are_read_only():
    """A read was authorized. A trigger was not.

    G3 §9 leaves API handlers "commands and review decisions only" and puts
    every network action worker-side, and card S6b makes an HTTP *command*
    surface conditional on a signed artifact calling for one — which none does.
    A ``POST`` under either of these paths would be that surface arriving
    without the artifact, so the methods are pinned rather than the paths
    alone.
    """
    offenders = sorted(
        f"{method} {route.path}"  # type: ignore[attr-defined]
        for route in events.router.routes
        for method in getattr(route, "methods", set())
        if method not in {"GET", "HEAD"}
    )

    assert offenders == [], f"G3: the events router is read-only; found {offenders}"


def test_the_match_run_router_declares_exactly_the_authorized_routes():
    """The G1 flip is bounded by a list, not by the router's own contents.

    The honest successor to "no match router exists" is not "a match router may
    now declare things" — that would be a gate replaced by nothing — but an
    exact equality against :data:`G1_AUTHORIZED_MATCH_RUN_PATHS`, exactly as
    :func:`test_the_events_router_declares_exactly_the_authorized_routes` does
    for G3. A third route added to this router fails here whether or not anyone
    regenerated the contract.
    """
    declared = {str(route.path) for route in match_runs.router.routes}  # type: ignore[attr-defined]

    assert declared == G1_AUTHORIZED_MATCH_RUN_PATHS, (
        "G1: the match-run router declares routes outside the P-MATCH-API "
        f"allowlist: {sorted(declared - G1_AUTHORIZED_MATCH_RUN_PATHS)}"
    )


def test_the_match_run_router_exposes_one_command_and_one_read():
    """One submission and one read — and nothing that decides anything.

    Card M8b authorizes routes that "submit the command and read the row back".
    A ``PATCH`` or ``PUT`` on a match run would contradict the snapshot's whole
    design (``0018``'s ``match_run_is_immutable`` trigger, and
    ``MatchRunRepository`` having no update method by construction); a
    ``DELETE`` would contradict it harder. Pinning the methods rather than the
    paths alone is what keeps a later card from hanging a decision endpoint off
    an already-admitted path.
    """
    observed = {
        (str(route.path), method)  # type: ignore[attr-defined]
        for route in match_runs.router.routes
        for method in getattr(route, "methods", set())
        if method not in {"HEAD", "OPTIONS"}
    }

    assert observed == {
        ("/v1/units/{unit_id}/match-runs", "POST"),
        ("/v1/units/{unit_id}/match-runs/{match_run_id}", "GET"),
    }, f"G1: unexpected match-run methods: {sorted(observed)}"


def test_a_match_run_path_outside_the_allowlist_is_still_refused():
    """The widened segment list is load-bearing, not decoration.

    If the first two assertions ever pass trivially — because ``match-runs``
    left :data:`_G1_FORBIDDEN_SEGMENTS` — then the allowlist above stopped
    admitting anything and started merely describing, and the next match-run
    path added would clear the scan without anyone naming it.
    """
    assert _forbidden_gate_for_path("/v1/units/{unit_id}/match-runs/{run_id}/decision") == "G1"
    assert _forbidden_gate_for_path("/v1/units/{unit_id}/matches") == "G1"
    assert _forbidden_gate_for_path("/v1/units/{unit_id}/match-runs") is None


def test_openapi_exposes_no_gated_product_surface_routes():
    """No HTTP surface for match/score/rank, crawl/discovery, or rewards until gates close."""
    document = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    paths = document.get("paths", {})
    for path in paths:
        gate = _forbidden_gate_for_path(path)
        assert gate is None, (
            f"forbidden route {path!r} in OpenAPI — gate {gate} not closed "
            f"(check path segments, not descriptions)"
        )
