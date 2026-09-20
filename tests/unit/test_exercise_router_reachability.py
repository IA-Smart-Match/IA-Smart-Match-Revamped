"""Exercise routers cannot *reach* the CBA request machinery, not merely not import it.

``make imports`` forbids the imports. It does not forbid the reaches that need no
import: ``request.app.state.session_factory`` is an attribute walk off an object
FastAPI hands every handler, and it arrives at the same connection pool a
repository would, with nothing in the module's import list to show for it. A
contract that bans the door and leaves the window is a contract about doors.

So this file walks the *source* of every exercise router and refuses a set of
names, whether they arrive by import or by attribute access.

The one sanctioned door
=======================

This is not a ban on the database. ADR-0025 D2 gives the exercise its own
``exercise_`` tables, and CE-WORKSPACE, CE-SIMULATION, CE-INGEST and
CE-INSTRUCTOR will read and write them. A rule with no door gets broken the
first time somebody needs a row, so the door is named here, before anybody needs
it: ``smartmatch_api.exercise_dependencies``, which exports
``get_exercise_session`` and the ``ExerciseSession`` annotation and holds nothing
else. Importing from that module is allowed; reaching a session any other way is
not.

What this file cannot see, and who does
=======================================

That a repository used behind ``get_exercise_session`` touches only
``exercise_``-prefixed tables. A source walk over the router cannot follow a
query into a repository, and pretending otherwise would be the more dangerous
half of a false guarantee. That half is stated in
``exercise_dependencies``'s module docstring and is the reviewer's, as ADR-0025
D2 leaves it.

The glob, and why it must match something
=========================================

Exercise router modules are enumerated by glob, so a module a later track adds
is covered the day it lands rather than the day somebody remembers to add it to
a list. The cost of a glob is that it passes vacuously when it matches nothing —
a renamed directory, a moved package, a typo in the pattern — so the first
assertion here is that it matched at all.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from smartmatch_api import exercise_dependencies
from smartmatch_api.routers import exercise_public

#: ``services/api/smartmatch_api/routers``.
_ROUTERS_DIR = Path(exercise_public.__file__).parent

#: Every exercise router module, now and later.
_EXERCISE_ROUTER_GLOB = "exercise_*.py"

#: The only module an exercise router may import a database session from.
_SANCTIONED_SESSION_MODULE = "smartmatch_api.exercise_dependencies"

#: Module prefixes an exercise router may not import. ``smartmatch_persistence``
#: is here as well as in ``pyproject.toml`` so a reader of this file sees the
#: whole rule; the two are deliberately redundant.
_FORBIDDEN_IMPORT_PREFIXES = (
    "smartmatch_authz",
    "smartmatch_persistence",
    "smartmatch_api.dependencies",
    "smartmatch_api.units",
    "smartmatch_api.job_authz",
    "smartmatch_api.main",
    "smartmatch_api.routers.auth",
)

#: Names that mean "this module reached the CBA request machinery", whether they
#: were imported or walked to off an object the framework supplied.
#:
#: ``state`` is the one worth naming out loud: ``request.app.state`` needs no
#: import at all, which is exactly why an import contract cannot see it.
#: ``session_factory`` is what sits on it, and ``get_session`` /
#: ``CurrentPrincipal`` / ``DbSession`` are the CBA dependency aliases an
#: exercise handler must never annotate with.
_FORBIDDEN_NAMES = frozenset(
    {
        "state",
        "session_factory",
        "get_session",
        "get_current_principal",
        "CurrentPrincipal",
        "DbSession",
        "smartmatch_authz",
        "assert_allowed",
        "ResolvedPrincipal",
        "charge_quota",
        "enforce_rate_limit",
        "get_token_verifier",
    }
)


def _exercise_router_modules() -> list[Path]:
    return sorted(_ROUTERS_DIR.glob(_EXERCISE_ROUTER_GLOB))


def _imported_modules(tree: ast.Module) -> set[str]:
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    return imported


def _getattr_string_dodges(tree: ast.Module) -> set[str]:
    """Banned names reached as a string through ``getattr(obj, "state")``.

    ``request.app.state`` is an :class:`ast.Attribute` and
    ``getattr(request.app, "state")`` is a string constant, and the two do the
    same thing. Without this the whole attribute guard is one builtin away from
    being decorative.

    Deliberately narrow — only the second positional argument of a call to
    ``getattr``. Matching every string constant in the module would flag a
    docstring-adjacent literal, a log message, or a column name, and a guard
    that cries wolf gets a blanket ignore rather than a fix. The remaining
    dodges (``vars()``, ``operator.attrgetter``, a name assembled from pieces)
    are not reachable by accident and would be a deliberate act, which is a
    review problem rather than a lint problem.
    """
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Name) and node.func.id == "getattr"):
            continue
        if len(node.args) < 2:
            continue
        second = node.args[1]
        if isinstance(second, ast.Constant) and second.value in _FORBIDDEN_NAMES:
            found.add(str(second.value))
    return found


def _referenced_names(tree: ast.Module) -> set[str]:
    """Every bare name and every attribute name the module mentions.

    Attributes are included because the reach this file exists to catch is an
    attribute chain, not a name: ``request.app.state.session_factory`` binds no
    name at all and appears in no import list.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            names.update((alias.asname or alias.name).split(".")[0] for alias in node.names)
    return names


def test_the_glob_matches_at_least_one_module() -> None:
    """A guard over an empty set is a green check that means nothing."""
    modules = _exercise_router_modules()
    assert modules, (
        f"no exercise router matched {_EXERCISE_ROUTER_GLOB!r} under {_ROUTERS_DIR}; "
        "the guard below would pass over nothing"
    )


def _module_ids() -> list[str]:
    return [path.name for path in _exercise_router_modules()]


@pytest.mark.parametrize("module_path", _exercise_router_modules(), ids=_module_ids())
def test_no_exercise_router_imports_the_cba_request_machinery(module_path: Path) -> None:
    """ADR-0025 D2's import half, over every exercise module the glob finds."""
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    offenders = sorted(
        name
        for name in _imported_modules(tree)
        for forbidden in _FORBIDDEN_IMPORT_PREFIXES
        if name == forbidden or name.startswith(f"{forbidden}.")
    )
    assert offenders == [], f"{module_path.name} imports {offenders}"


@pytest.mark.parametrize("module_path", _exercise_router_modules(), ids=_module_ids())
def test_no_exercise_router_reaches_a_session_or_a_principal(module_path: Path) -> None:
    """The half an import contract cannot express.

    ``app.state`` and ``session_factory`` are attribute walks. A module that
    needs a session takes ``ExerciseSession`` from
    :mod:`smartmatch_api.exercise_dependencies`; a module that does anything else
    to get one fails here.
    """
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    offenders = sorted((_referenced_names(tree) & _FORBIDDEN_NAMES) | _getattr_string_dodges(tree))
    assert offenders == [], (
        f"{module_path.name} reaches {offenders}; the only sanctioned database "
        f"access for an exercise router is {_SANCTIONED_SESSION_MODULE}."
    )


def test_the_reachability_guard_catches_the_shapes_it_claims_to() -> None:
    """Every real exercise module passes the guard, so prove the guard can fail.

    One case per shape: the attribute walk the import contract cannot see, the
    ``getattr`` string that the attribute walk alone would not see, and a
    handler annotating with a CBA dependency alias.
    """
    attribute_walk = ast.parse("def h(request):\n    return request.app.state.session_factory\n")
    assert _referenced_names(attribute_walk) & _FORBIDDEN_NAMES == {"state", "session_factory"}

    string_dodge = ast.parse('def h(request):\n    return getattr(request.app, "state")\n')
    assert _getattr_string_dodges(string_dodge) == {"state"}
    assert _referenced_names(string_dodge) & _FORBIDDEN_NAMES == set(), (
        "the attribute guard alone does not see the string form — which is why "
        "_getattr_string_dodges exists"
    )

    alias = ast.parse("def h(principal: CurrentPrincipal):\n    return principal\n")
    assert _referenced_names(alias) & _FORBIDDEN_NAMES == {"CurrentPrincipal"}

    # And the sanctioned shape is not flagged.
    sanctioned = ast.parse(
        "from smartmatch_api.exercise_dependencies import ExerciseSession\n"
        "def h(session: ExerciseSession):\n    return session\n"
    )
    assert _referenced_names(sanctioned) & _FORBIDDEN_NAMES == set()
    assert _getattr_string_dodges(sanctioned) == set()


def test_the_sanctioned_door_exists_and_is_importable_by_an_exercise_router() -> None:
    """The names a later track will write, pinned now so they are not re-invented."""
    assert exercise_dependencies.__name__ == _SANCTIONED_SESSION_MODULE
    assert {"ExerciseSession", "get_exercise_session"} <= set(exercise_dependencies.__all__)
    assert callable(exercise_dependencies.get_exercise_session)


def test_the_door_exports_nothing_that_could_resolve_a_principal() -> None:
    """The names grew (CE-WORKSPACE); the rule about what they may be did not.

    The original assertion here was an equality over ``__all__``, which said
    "these two names and no others". CE-WORKSPACE needed the door to widen —
    it is where the exercise repositories, the workspace cookie and its two
    refusals are injected from, so that a router imports this module and
    nothing else — and an equality would have been edited into a longer
    equality on every exercise track, which is a list nobody reads.

    What the equality was actually protecting is stated directly instead: no
    name this module exports may be one of the CBA request machinery's, and the
    names it does export are the exercise's own. A principal, a quota or an
    authorizer appearing here is the failure; a fourth workspace helper is not.
    """
    forbidden = {
        "CurrentPrincipal",
        "DbSession",
        "ResolvedPrincipal",
        "charge_quota",
        "enforce_rate_limit",
        "get_current_principal",
        "get_session",
        "get_token_verifier",
    }
    assert set(exercise_dependencies.__all__) & forbidden == set()
    for name in exercise_dependencies.__all__:
        assert hasattr(exercise_dependencies, name), f"{name} is exported but does not exist"


#: Modules an ``exercise_dependencies`` export may have come from.
#:
#: The exercise's own two, plus the libraries whose types an annotation is built
#: out of. Everything else — and ``smartmatch_api.dependencies`` and
#: ``smartmatch_authz`` above all — is a name that travelled through the door
#: from the wrong side.
_PERMITTED_EXPORT_MODULES = frozenset(
    {
        "smartmatch_api.exercise_dependencies",
        "smartmatch_api.exercise_errors",
        "smartmatch_persistence.exercise.workspace_repository",
        # CE-INSTRUCTOR. The door injects three exercise repositories now, and
        # the value types and write refusals they hand back travel through it
        # with them — a router that may not import ``smartmatch_persistence``
        # may not import a dataclass out of it either. Each is named, and each
        # is inside ``smartmatch_persistence.exercise``: the family ADR-0025 D2
        # permits, never the tenant-scoped rest of the package.
        "smartmatch_persistence.exercise.dataset_repository",
        "smartmatch_persistence.exercise.instructor_repository",
        # CE-MATCHING-API, as two modules after review round 1: the saved
        # settings, and the team's own view of the profiles (design spec §2's
        # ``base row ⟕ overlay``). Two origins because they are two questions.
        "smartmatch_persistence.exercise.settings_repository",
        "smartmatch_persistence.exercise.team_view_repository",
        "typing",
        "builtins",
        # ``ExerciseSession`` wraps SQLAlchemy's ``Session``. Admitted
        # deliberately, which is the point of the list: the door's whole job is
        # to hand an exercise router a session *without* the principal
        # machinery beside it, so a session type arriving from SQLAlchemy is
        # the design working rather than a leak.
        "sqlalchemy.orm.session",
    }
)

#: Modules no export may come from, whatever the allow-list says. Stated
#: separately so the failure message can say *which* rule was broken, and so
#: that widening the allow-list can never accidentally admit one of these.
_FORBIDDEN_EXPORT_MODULES = ("smartmatch_api.dependencies", "smartmatch_authz")


def _module_of(obj: object) -> set[str]:
    """The module an object was defined in, as a set so "none" composes."""
    module = getattr(obj, "__module__", None)
    return {module} if isinstance(module, str) else set()


def _origin_modules(exported: object) -> set[str]:
    """Every module an exported object was assembled from.

    ``Annotated[Session, Depends(get_exercise_session)]`` is unwrapped rather
    than read directly, and that is not a detail: reading ``__module__`` off an
    ``Annotated`` alias gives a *different answer on different interpreters* —
    some proxy attribute access through to the wrapped type, some do not — so a
    check written that way passes locally and fails in CI, which is exactly what
    happened to the first version of this test. Unwrapping asks the question
    the test actually means, and asks it the same way everywhere.

    What comes back for an annotation is the wrapped type's module plus the
    module of every ``Depends(...)`` callable attached to it — which is the
    pair that matters here, since a dependency callable is what would reach the
    principal machinery.
    """
    metadata = getattr(exported, "__metadata__", None)
    if metadata is None:
        return _module_of(exported)
    modules = set()
    origin = getattr(exported, "__origin__", None)
    if origin is not None:
        modules |= _module_of(origin)
    for item in metadata:
        dependency = getattr(item, "dependency", None)
        if dependency is not None:
            modules |= _module_of(dependency)
    return modules


def test_every_name_the_door_exports_came_from_a_permitted_module() -> None:
    """The denial list above says what may not be exported; this says what may.

    A denial list only catches the names somebody thought to write down.
    ``CurrentPrincipal`` is on it; a CBA helper added next month under a name
    nobody predicted is not. Asking instead where each exported object was
    *defined* catches the whole class: an object defined in
    ``smartmatch_api.dependencies`` fails here no matter what it is called, and
    a ``Depends(...)`` on a CBA callable fails even wrapped in an annotation.

    Modules are read rather than names, because re-exporting under an alias is
    exactly how a forbidden name would arrive looking innocent.
    """
    checked = 0
    for name in exercise_dependencies.__all__:
        for origin in _origin_modules(getattr(exercise_dependencies, name)):
            checked += 1
            assert not origin.startswith(_FORBIDDEN_EXPORT_MODULES), (
                f"{name} is built from {origin}; the door does not re-export "
                "the CBA request machinery"
            )
            assert origin in _PERMITTED_EXPORT_MODULES, (
                f"{name} is built from {origin}, which is not on the permitted "
                "list. If that module is legitimate, add it deliberately — the "
                "point of the list is that widening it is a decision somebody "
                "makes."
            )
    assert checked, "no export resolved to a module; the check passed over nothing"


def test_the_export_check_unwraps_annotations_rather_than_trusting_them() -> None:
    """The regression that broke CI, pinned so it cannot come back quietly.

    ``ExerciseSession`` must resolve to SQLAlchemy's session module on every
    interpreter, and the ``Depends`` callable inside it must resolve to this
    module — neither of which is what ``__module__`` on the alias reliably
    reports.
    """
    modules = _origin_modules(exercise_dependencies.ExerciseSession)
    assert "sqlalchemy.orm.session" in modules
    assert _SANCTIONED_SESSION_MODULE in modules

    # And a forbidden dependency inside an annotation is caught, not hidden.
    from typing import Annotated

    from fastapi import Depends

    def _pretend_cba_dependency() -> None:  # pragma: no cover - never called
        return None

    _pretend_cba_dependency.__module__ = "smartmatch_api.dependencies"
    smuggled = Annotated[str, Depends(_pretend_cba_dependency)]
    assert "smartmatch_api.dependencies" in _origin_modules(smuggled)


def test_the_sanctioned_door_is_not_on_the_forbidden_list() -> None:
    """The rule permits the door it names, and would fail loudly if it stopped.

    Without this, a later edit could add ``smartmatch_api.exercise_dependencies``
    to the forbidden prefixes and leave the exercise with no legal way to reach
    its own tables — which is how a boundary turns into a reason to work around
    the boundary.
    """
    assert not any(
        forbidden == _SANCTIONED_SESSION_MODULE
        or _SANCTIONED_SESSION_MODULE.startswith(f"{forbidden}.")
        for forbidden in _FORBIDDEN_IMPORT_PREFIXES
    )


def test_the_sanctioned_door_hands_back_a_session_and_rolls_it_back() -> None:
    """``get_exercise_session`` yields from the app factory, queries nothing, rolls back."""

    class _Session:
        def __init__(self) -> None:
            self.rolled_back = False
            self.closed = False

        def rollback(self) -> None:
            self.rolled_back = True

        def close(self) -> None:
            self.closed = True

    class _State:
        session_factory = _Session

    class _App:
        state = _State()

    class _Request:
        app = _App()

    generator = exercise_dependencies.get_exercise_session(_Request())  # type: ignore[arg-type]
    session = next(generator)
    assert isinstance(session, _Session)
    with pytest.raises(StopIteration):
        next(generator)
    assert session.rolled_back and session.closed
