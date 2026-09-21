"""``ProductScope.CLASS_EXERCISE`` and ``Capability.CLASS_EXERCISE`` (CE-SCOPE).

ADR-0025 D1 adds a *second product scope* for Ann Wang's Spring 2027 class
exercise. This file pins the three things that decision is worth only if they
are true:

1. The capability is granted **only** in its own scope, and the scope grants
   **nothing else**. Every capability that implies an authenticated CBA router
   or a CBA datum is explicitly ``False`` there, so the exercise process cannot
   serve a real record even by accident.
2. The CBA and ``IA_WEST_LEGACY`` columns are **bit-identical** to what they
   were before the scope existed. Adding a product must not re-decide another
   product, so the two pre-change columns are restated here as literals and
   compared value by value rather than trusted to a diff.
3. The fail-closed machinery is **not relaxed** to make room for the new column:
   an unclassified capability still fails the import, an unknown scope or
   capability name still raises :class:`CapabilityScopeError`, and
   ``DEFAULT_PRODUCT_SCOPE`` is still ``CBA`` — an unset
   ``SMARTMATCH_PRODUCT_SCOPE`` cannot enable the exercise.

The route-table claim (ADR-0025 D1: "in the exercise scope the authenticated CBA
routers are **not registered**, so ``get_current_principal`` is unreachable
rather than bypassed") is asserted against ``smartmatch_api.main.routers_for``,
which is the composition rule the running application is built from — and one
test here pins that it *is* what the application is built from, so the other two
cannot pass against a function nothing calls. Its twin — that the exercise routes
answer 404 under CBA — arrived with CE-ROUTERS, which wrote the first of them,
and lives beside that router in ``tests/unit/test_exercise_public_router.py``:
a test asserting the absence of something nobody had written would have passed
for the wrong reason, so it waited for something to be absent.

This track closes no row in
``docs/plans/open-questions/class-exercise-open-questions.md`` and no row there
gates it.
"""

from __future__ import annotations

from typing import Any

import pytest
from smartmatch_api.config import Settings
from smartmatch_domain.product_scope import (
    DEFAULT_PRODUCT_SCOPE,
    Capability,
    CapabilityScopeError,
    ProductScope,
    capability_decisions,
    enabled_capabilities,
    is_capability_enabled,
)


def _naming_rule() -> Any:
    """The scanner's own ``demo-mode-fallback`` rule.

    Imported rather than re-stated, so ADR-0025 D9's naming claim is checked
    against the gate that enforces it. ``tools`` is importable because the
    repository root is on ``pythonpath`` (``[tool.pytest.ini_options]``).
    """
    from tools.scan_forbidden import RULES

    rules = [rule for rule in RULES if rule.code == "demo-mode-fallback"]
    assert len(rules) == 1, "the scanner no longer has exactly one demo-mode rule"
    return rules[0]


#: The CBA column exactly as it stood before this track, restated as a literal.
#:
#: Deliberately not derived from ``Capability``: the point of this fixture is to
#: be a *second copy* of the pre-change decisions, written by hand, so that a
#: change to the policy has to disagree with something that was not changed with
#: it. A comprehension over the enum would agree with any edit at all.
_CBA_BEFORE: dict[str, bool] = {
    "authenticated_login": True,
    "event_reads": True,
    "speaker_request_intake": True,
    "speaker_contact_management": True,
    "match_runs": True,
    "discovery_metrics": True,
    "consented_outreach": True,
    "rewards_ledger": True,
    "operator_record_import": True,
    "external_speaker_acquisition": False,
    "cold_unknown_contact_outreach": False,
    "chapter_membership_dues": False,
    "member_inquiry_narrative": False,
}

#: The ``ia_west_legacy`` column exactly as it stood before this track.
_IA_WEST_LEGACY_BEFORE: dict[str, bool] = {name: True for name in _CBA_BEFORE}

#: Route-path prefixes that belong to authenticated CBA surfaces and must be
#: absent from a process running the exercise scope. The first two are served by
#: the *unconditional* infrastructure routers, which is the whole reason this
#: file has a composition section: the capability table alone did not make those
#: two go away, and every route behind them resolves a principal.
_AUTHENTICATED_CBA_PATH_PREFIXES = (
    "/v1/jobs",
    "/v1/review-items",
    "/v1/me",
    "/v1/auth",
    # Every tenant-scoped surface: events, match runs, metrics, rewards,
    # outreach, the roster, the funnel. All of them resolve a principal and
    # authorize against the unit in the path.
    "/v1/units",
)


def _mounted_paths_under(scope: ProductScope) -> frozenset[str]:
    """Every route path a process in ``scope`` would mount from a router.

    ``smartmatch_api.main`` decides its route set once, at import, from the
    settings the process booted with — a route set that changed per request
    would be a different application on every call. ``routers_for`` is that
    decision as a function, so this asks the composition rule the running app
    obeys rather than booting a second interpreter to observe its result.
    """
    from smartmatch_api.main import routers_for

    settings = Settings(product_scope=scope)
    return frozenset(
        route.path
        for router in routers_for(settings)
        for route in router.routes
        if hasattr(route, "path")
    )


#: The one route no composition rule accounts for: declared with ``@app.get`` and
#: ungated in every scope, because a liveness probe a product decision could
#: remove is a liveness probe a monitor cannot rely on.
_UNGATED_APP_ROUTES = frozenset({"/api/health"})


def _app_level_paths_under(scope: ProductScope) -> frozenset[str]:
    """Every path a process in ``scope`` serves from the application module itself.

    The residue: what is left of the served surface once ``routers_for`` has
    accounted for everything in ``routers/``. Asserted as an equality below,
    because the interesting failure is a route *appearing* here — a handler
    declared on the application escapes both the capability table and the
    exercise's scope isolation.
    """
    from smartmatch_api.main import app_level_routers_for

    settings = Settings(product_scope=scope)
    return _UNGATED_APP_ROUTES | frozenset(
        route.path
        for router in app_level_routers_for(settings)
        for route in router.routes
        if hasattr(route, "path")
    )


# ---------------------------------------------------------------------------
# The names
# ---------------------------------------------------------------------------


def test_the_scope_and_capability_exist_with_the_spelled_names() -> None:
    """Design spec §1 names both values, and the word in code is *exercise*."""
    assert ProductScope.CLASS_EXERCISE.value == "class_exercise"
    assert Capability.CLASS_EXERCISE.value == "class_exercise"


def test_no_name_in_the_policy_says_demo_or_trips_the_forbidden_scanner() -> None:
    """ADR-0025 D9: the word in code is *exercise*. Two assertions, both needed.

    The first version of this test asserted only ``"demo" not in name`` — its
    own substring rule, which agreed with ``tools/scan_forbidden.py`` by
    coincidence and would have kept agreeing if the tool's rule changed
    underneath it. Replacing it with the tool's regex alone was worse, and the
    security review caught it: ``demo-mode-fallback`` matches ``demo_mode``,
    ``DEMO_MODE``, ``load_fixture(`` and ``if demo``, so a capability named
    plainly ``demo`` — or ``cba_demo`` — would have passed this test *and*
    ``make scan``, leaving D9's naming rule guarded by nothing at all.

    So both run, and they are guarding different things. The substring rule is
    D9's actual claim about *this policy's vocabulary*: no scope or capability
    name contains the word, in any casing, however it is embedded. The regex is
    the claim that the names also survive the repository-wide gate, which is a
    weaker condition over a broader alphabet — a name can be fine by the gate
    and still wrong here.

    The control for the regex — that it fires on a synthetic offending string,
    so a rule matching nothing could not pass quietly — is deliberately not
    duplicated here. It is
    ``tests/unit/test_forbidden_scanner.py::test_catches_demo_mode_fallback``,
    which feeds the rule ``from src.demo_mode import load_fixture`` and asserts
    it fires. That file is the only one ``tools/scan_forbidden.py`` excludes
    from its own sweep, which is why the offending string lives there and not
    here. The bare word below is not such a string: none of the rule's four
    alternatives matches ``demo`` on its own, so writing it costs nothing and
    the file stays out of the scanner's exclusions.
    """
    rule = _naming_rule()
    names = [scope.value for scope in ProductScope] + [c.value for c in Capability]

    for name in names:
        assert "demo" not in name.lower(), f"{name!r} says demo; ADR-0025 D9 says exercise"
        assert rule.regex.search(name) is None, f"{name!r} trips {rule.code}"


# ---------------------------------------------------------------------------
# The decisions
# ---------------------------------------------------------------------------


def test_class_exercise_capability_is_granted_only_in_its_own_scope() -> None:
    """ADR-0025 D1 in one assertion."""
    assert is_capability_enabled(ProductScope.CLASS_EXERCISE, Capability.CLASS_EXERCISE)
    for scope in ProductScope:
        if scope is ProductScope.CLASS_EXERCISE:
            continue
        assert not is_capability_enabled(scope, Capability.CLASS_EXERCISE), (
            f"{scope} must not grant the class-exercise capability"
        )


def test_the_exercise_scope_grants_nothing_else() -> None:
    """Every CBA capability is explicitly off in the exercise scope.

    Not "most of them": a scope that kept ``event_reads`` or ``match_runs`` would
    be a process that can read a real catalog and score real records with no
    account in front of it. The exercise has its own data and its own ranker.
    """
    assert enabled_capabilities(ProductScope.CLASS_EXERCISE) == frozenset(
        {Capability.CLASS_EXERCISE}
    )
    decisions = capability_decisions(ProductScope.CLASS_EXERCISE)
    for capability in Capability:
        if capability is Capability.CLASS_EXERCISE:
            continue
        assert decisions[capability] is False, f"{capability} must be off under CLASS_EXERCISE"


def test_every_capability_is_classified_for_the_new_scope() -> None:
    """Silence is still impossible — including in the column just added."""
    assert set(capability_decisions(ProductScope.CLASS_EXERCISE)) == set(Capability)


def test_the_cba_column_is_bit_identical_to_before_this_track() -> None:
    """Adding a product must not re-decide another product."""
    decisions = capability_decisions(ProductScope.CBA)
    assert {
        capability.value: enabled
        for capability, enabled in decisions.items()
        if capability is not Capability.CLASS_EXERCISE
    } == _CBA_BEFORE


def test_the_legacy_column_is_bit_identical_to_before_this_track() -> None:
    decisions = capability_decisions(ProductScope.IA_WEST_LEGACY)
    assert {
        capability.value: enabled
        for capability, enabled in decisions.items()
        if capability is not Capability.CLASS_EXERCISE
    } == _IA_WEST_LEGACY_BEFORE


def test_the_only_new_capability_is_the_exercise_one() -> None:
    assert {c.value for c in Capability} == set(_CBA_BEFORE) | {"class_exercise"}


# ---------------------------------------------------------------------------
# Fail-closed, unrelaxed
# ---------------------------------------------------------------------------


def test_default_product_scope_is_still_cba() -> None:
    """An unset ``SMARTMATCH_PRODUCT_SCOPE`` cannot enable the exercise."""
    assert DEFAULT_PRODUCT_SCOPE is ProductScope.CBA
    assert not is_capability_enabled(DEFAULT_PRODUCT_SCOPE, Capability.CLASS_EXERCISE)


def test_an_unclassified_capability_still_fails_the_import() -> None:
    """The validation that makes omission impossible is not relaxed for the new column."""
    from smartmatch_domain.product_scope import _classified

    with pytest.raises(CapabilityScopeError):
        _classified({Capability.CLASS_EXERCISE: True})


def test_unknown_scope_and_capability_names_still_raise() -> None:
    with pytest.raises(CapabilityScopeError):
        enabled_capabilities("class_excercise")  # type: ignore[arg-type]
    with pytest.raises(CapabilityScopeError):
        is_capability_enabled(ProductScope.CLASS_EXERCISE, "class_exercize")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_settings_parses_the_new_scope_value() -> None:
    settings = Settings(product_scope="class_exercise")  # type: ignore[arg-type]
    assert settings.product_scope is ProductScope.CLASS_EXERCISE
    assert settings.capability_enabled(Capability.CLASS_EXERCISE)
    assert settings.enabled_capabilities() == frozenset({Capability.CLASS_EXERCISE})


def test_settings_default_still_refuses_the_exercise_capability() -> None:
    assert Settings().capability_enabled(Capability.CLASS_EXERCISE) is False


def test_the_new_scope_changes_no_provider_isolation() -> None:
    """Scope is not Edition, and the new scope is no exception."""
    from smartmatch_providers import Edition

    settings = Settings(edition=Edition.CLASSROOM, product_scope=ProductScope.CLASS_EXERCISE)
    assert settings.use_fixture_providers is True


# ---------------------------------------------------------------------------
# Composition — ADR-0025 D1's route-table claim
# ---------------------------------------------------------------------------


def test_cba_authenticated_routes_are_absent_under_class_exercise() -> None:
    """``get_current_principal`` is unreachable in the exercise scope, not bypassed."""
    exercise_paths = _mounted_paths_under(ProductScope.CLASS_EXERCISE)
    offenders = sorted(
        path for path in exercise_paths if path.startswith(_AUTHENTICATED_CBA_PATH_PREFIXES)
    )
    assert offenders == [], (
        f"authenticated CBA routes still mounted under CLASS_EXERCISE: {offenders}"
    )
    # Exactly the exercise's own routes, and nothing else. CE-ROUTERS mounted
    # the first (`routers/exercise_public.py`), CE-WORKSPACE the two team
    # workspace routes (`routers/exercise_workspace.py` — the third, the
    # team-addressed reset, moved behind the instructor passcode by the owner
    # ruling of 2026-09-19), and CE-INSTRUCTOR the
    # instructor page (`routers/exercise_instructor.py`, two routers so the
    # session gate can sit on one of them); every later exercise
    # track adds its own path to this set, and a CBA `/v1` path appearing in it
    # is the failure this guards. Stated as an equality rather than a
    # containment so that a router mounted under the wrong capability cannot
    # slip in unnamed.
    assert exercise_paths == frozenset(
        {
            "/v1/exercise",
            "/v1/exercise/workspaces",
            "/v1/exercise/workspaces/current",
            "/v1/exercise/instructor/login",
            "/v1/exercise/instructor/logout",
            "/v1/exercise/instructor/datasets",
            "/v1/exercise/instructor/datasets/{dataset_id}",
            "/v1/exercise/instructor/datasets/{dataset_id}/repoint",
            "/v1/exercise/instructor/events/{event_key}/unlock",
            "/v1/exercise/instructor/workspaces",
            "/v1/exercise/instructor/workspaces/{team_number}",
            "/v1/exercise/instructor/workspaces/{team_number}/reset",
            "/v1/exercise/instructor/refresh-all",
            # CE-MATCHING-API. Every one of these is addressed by the workspace
            # cookie — `current`, never a team number or a workspace id — which
            # is why they sit under the same prefix as
            # `/v1/exercise/workspaces/current`.
            "/v1/exercise/workspaces/current/events",
            "/v1/exercise/workspaces/current/events/{event_key}/list",
            "/v1/exercise/workspaces/current/events/{event_key}/list.csv",
            "/v1/exercise/workspaces/current/events/{event_key}/settings",
            "/v1/exercise/workspaces/current/events/{event_key}/settings/compare",
            "/v1/exercise/workspaces/current/events/{event_key}/settings/{name}",
            # CE-RESULTS-API, team half (design spec §9-§13). Same addressing
            # again: `current`, never a team number or a workspace id.
            "/v1/exercise/workspaces/current/events/{event_key}/results",
            "/v1/exercise/workspaces/current/asking-choice",
            "/v1/exercise/workspaces/current/refresh",
        }
    )


def test_the_cba_scope_still_mounts_every_one_of_them() -> None:
    """The gating is scope-specific, not a deletion."""
    cba_paths = _mounted_paths_under(ProductScope.CBA)
    for prefix in _AUTHENTICATED_CBA_PATH_PREFIXES:
        assert any(path.startswith(prefix) for path in cba_paths), (
            f"{prefix} must still be mounted under CBA"
        )


def test_the_composition_function_describes_the_running_app() -> None:
    """``routers_for`` is not a parallel truth: the app is built from it.

    Without this, the two tests above could pass against a function nothing
    calls. The served contract under the default scope must be exactly what
    ``routers_for`` says it is.
    """
    from smartmatch_api.main import app

    served = set(app.openapi()["paths"])
    mounted = _mounted_paths_under(DEFAULT_PRODUCT_SCOPE)
    assert mounted <= served
    # The only served paths `routers_for` does not account for are the three the
    # application module declares: liveness, and the two token-addressed HTML
    # pages. Nothing else may appear without going through one of the two rules.
    assert served - mounted == _app_level_paths_under(DEFAULT_PRODUCT_SCOPE)
    assert served - mounted == {"/api/health", "/u/{token}", "/i/{token}"}


def test_the_token_pages_are_gated_on_the_capability_that_owns_them() -> None:
    """``/u/{token}`` and ``/i/{token}`` ride ``CONSENTED_OUTREACH``, not a scope literal.

    They are CBA outreach pages — the read half of the unsubscribe pair and the
    page a speaker invitation links to — and the tokens that address them are
    minted by the machinery ``CONSENTED_OUTREACH`` gates. The gate is that same
    capability rather than a comparison against ``ProductScope.CLASS_EXERCISE``,
    so a later scope with outreach gets them and a later scope without does not,
    with no edit to the composition.
    """
    from smartmatch_api.main import APP_LEVEL_ROUTERS

    assert [capability for _router, capability in APP_LEVEL_ROUTERS] == [
        Capability.CONSENTED_OUTREACH
    ]


def test_the_application_level_residue_under_the_default_scope_is_unchanged() -> None:
    """The CBA contract is untouched by moving the two pages behind a capability."""
    assert _app_level_paths_under(DEFAULT_PRODUCT_SCOPE) == {
        "/api/health",
        "/u/{token}",
        "/i/{token}",
    }
    assert _app_level_paths_under(ProductScope.IA_WEST_LEGACY) == {
        "/api/health",
        "/u/{token}",
        "/i/{token}",
    }


def test_the_exercise_scope_serves_no_cba_outreach_page() -> None:
    """ADR-0025 D1 reaches the application module too, not only ``routers/``.

    An equality, not a containment: the exercise process serves exactly one
    route from the application module — liveness — and a second one appearing
    here is a CBA surface that escaped the capability table by being declared
    one level up.
    """
    assert _app_level_paths_under(ProductScope.CLASS_EXERCISE) == {"/api/health"}


def test_the_legacy_scope_is_untouched_by_the_gating() -> None:
    """The one other scope that has authenticated login keeps every route."""
    assert _mounted_paths_under(ProductScope.IA_WEST_LEGACY) >= _mounted_paths_under(
        ProductScope.CBA
    )
