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


# ---------------------------------------------------------------------------
# The names
# ---------------------------------------------------------------------------


def test_the_scope_and_capability_exist_with_the_spelled_names() -> None:
    """Design spec §1 names both values, and the word in code is *exercise*."""
    assert ProductScope.CLASS_EXERCISE.value == "class_exercise"
    assert Capability.CLASS_EXERCISE.value == "class_exercise"


def test_no_name_in_the_policy_says_demo() -> None:
    """ADR-0025 D9 and ``tools/scan_forbidden.py``: the scope is called *exercise*."""
    for name in [scope.value for scope in ProductScope] + [c.value for c in Capability]:
        assert "demo" not in name.lower()


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
    # Exactly the exercise's own public route, and nothing else. CE-ROUTERS
    # mounted it (`routers/exercise_public.py`); every later exercise track adds
    # its own path to this set, and a CBA `/v1` path appearing in it is the
    # failure this guards. Stated as an equality rather than a containment so
    # that a router mounted under the wrong capability cannot slip in unnamed.
    assert exercise_paths == frozenset({"/v1/exercise"})


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
    # The only served paths `routers_for` does not account for are the three
    # declared on the application itself: liveness, and the two token-addressed
    # HTML pages. Nothing else may appear without going through the rule.
    assert served - mounted == {"/api/health", "/u/{token}", "/i/{token}"}


def test_the_legacy_scope_is_untouched_by_the_gating() -> None:
    """The one other scope that has authenticated login keeps every route."""
    assert _mounted_paths_under(ProductScope.IA_WEST_LEGACY) >= _mounted_paths_under(
        ProductScope.CBA
    )
