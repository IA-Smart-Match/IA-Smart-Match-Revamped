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
