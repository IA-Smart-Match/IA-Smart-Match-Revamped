"""Exercise persistence touches ``exercise_`` tables and nothing else (ADR-0025 D2).

This is the half that neither ``make imports`` nor
``tests/unit/test_exercise_router_reachability.py`` can see, and both of them
say so in their own docstrings: an exercise router reaches the database through
one sanctioned door, and a source walk over the *router* cannot follow a query
into a repository. The ADR leaves that half to the reviewer. This file takes it
off them.

The security review that asked for it (control D2) phrased the risk plainly: a
repository behind ``get_exercise_session`` that selected from ``user_account``,
``membership`` or ``event`` would be the process mixing ADR-0025 D1 exists to
prevent, and the import contract cannot tell the difference between that
repository and a correct one — both import ``smartmatch_persistence.exercise``
and both use SQLAlchemy.

So: every module in ``smartmatch_persistence.exercise`` is parsed, and every
table it names must carry the ``exercise_`` prefix. Two shapes are recognised,
because there are two ways to name a table in this package:

* ``sa.Table("some_name", ...)`` — the string literal in ``schema.py``.
* ``schema.some_name`` — how a repository reaches a table object.

Both are checked. A repository that wrote ``sa.table("user_account")`` or
imported a CBA table under an alias would fail, and the synthetic-offender test
proves the walk can fail rather than trusting that it would.

Why an allow-list of one prefix rather than a denial list of CBA table names
===========================================================================

A denial list has to be maintained, and the failure mode of an unmaintained one
is silence: a CBA table added next month is not on it, so a repository that
joined to it would pass. The prefix is the rule ADR-0025 D2 actually states —
"tables prefixed ``exercise_``" — so a name that is not on the list is refused
by default, which is the direction ADR-0011 requires of an unknown.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from smartmatch_persistence import exercise as exercise_package

#: ``python/smartmatch_persistence/smartmatch_persistence/exercise``.
_PACKAGE_DIR = Path(exercise_package.__file__).parent

#: The one prefix ADR-0025 D2 permits.
_REQUIRED_PREFIX = "exercise_"

#: The name a repository in this package binds the schema module to. Every
#: table object it uses arrives as an attribute of it — ``schema.exercise_dataset``
#: — which is what makes the attribute walk below sufficient.
_SCHEMA_MODULE_ALIAS = "schema"

#: Attributes of the schema module that are not tables. Named rather than
#: pattern-matched, so a helper added later has to be added here deliberately
#: instead of slipping past a rule about capital letters.
_SCHEMA_NON_TABLE_NAMES = frozenset(
    {
        "EXERCISE_TABLES",
        "EXERCISE_WITHHELD_FIELDS",
        "exercise_profile_public_columns",
    }
)


def _package_modules() -> list[Path]:
    return sorted(path for path in _PACKAGE_DIR.glob("*.py") if path.name != "__init__.py")


def _module_ids() -> list[str]:
    return [path.name for path in _package_modules()]


def _table_literals(tree: ast.Module) -> set[str]:
    """Every table name passed as the first argument to a ``Table(...)`` call."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        called = node.func
        name = (
            called.attr
            if isinstance(called, ast.Attribute)
            else called.id
            if isinstance(called, ast.Name)
            else ""
        )
        if name.lower() != "table" or not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            found.add(first.value)
    return found


def _schema_attributes(tree: ast.Module) -> set[str]:
    """Every ``schema.<name>`` a module reaches for."""
    return {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == _SCHEMA_MODULE_ALIAS
        and node.attr not in _SCHEMA_NON_TABLE_NAMES
    }


def _named_tables(tree: ast.Module) -> set[str]:
    return _table_literals(tree) | _schema_attributes(tree)


def test_the_package_is_not_empty() -> None:
    """A walk over no modules is a green check that means nothing."""
    modules = _package_modules()
    assert modules, f"no module found under {_PACKAGE_DIR}; the guard below would pass over nothing"


def test_the_walk_finds_tables_in_the_package_it_is_guarding() -> None:
    """And a walk that finds no *tables* is the same green check twice removed.

    The package could grow a module that names none — a pure helper — but if
    the whole package names none, the recogniser has stopped recognising and
    every assertion below is vacuous.
    """
    named: set[str] = set()
    for module_path in _package_modules():
        named |= _named_tables(ast.parse(module_path.read_text(encoding="utf-8")))
    assert named, "the walk recognised no table in the exercise persistence package"


@pytest.mark.parametrize("module_path", _package_modules(), ids=_module_ids())
def test_every_table_named_in_the_package_is_an_exercise_table(module_path: Path) -> None:
    """ADR-0025 D2 as an assertion rather than a review note."""
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    offenders = sorted(
        name for name in _named_tables(tree) if not name.startswith(_REQUIRED_PREFIX)
    )
    assert offenders == [], (
        f"{module_path.name} names {offenders}, which do not carry the "
        f"{_REQUIRED_PREFIX!r} prefix ADR-0025 D2 requires. The class exercise "
        "may not read or write a CBA table."
    )


def test_the_guard_catches_a_synthetic_offender() -> None:
    """Every real module passes, so prove the walk can fail.

    One case per recognised shape: the table declared by string literal, and
    the table reached as an attribute of the schema module.
    """
    declared = ast.parse('import sqlalchemy as sa\nuser_account = sa.Table("user_account", M)\n')
    assert _named_tables(declared) == {"user_account"}

    reached = ast.parse("def f(session):\n    return session.execute(schema.membership.select())\n")
    assert _named_tables(reached) == {"membership"}

    honest = ast.parse(
        "def f(session):\n    return session.execute(schema.exercise_team_workspace.select())\n"
    )
    assert {
        name for name in _named_tables(honest) if not name.startswith(_REQUIRED_PREFIX)
    } == set()


def test_the_schema_module_declares_every_table_it_exports() -> None:
    """The metadata half: the objects, not the source.

    ``EXERCISE_TABLES`` is the family by name, and it is what the rest of the
    codebase walks. If a table object existed in the package but not in that
    mapping, the source walk above would still pass and every metadata-based
    check elsewhere would miss it.
    """
    from smartmatch_persistence.exercise.schema import EXERCISE_TABLES

    assert EXERCISE_TABLES
    for name, table in EXERCISE_TABLES.items():
        assert name == table.name
        assert name.startswith(_REQUIRED_PREFIX), f"{name} is in EXERCISE_TABLES without the prefix"
