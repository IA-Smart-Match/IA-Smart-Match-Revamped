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
table it names must carry the ``exercise_`` prefix. Five shapes are recognised,
because there are five ways to reach a table from this package — the first two
were all the original version checked, and the review pointed out that the
other three walked straight past it:

* ``sa.Table("some_name", ...)`` / ``sa.table(...)`` / a bare ``Table(...)`` —
  the string literal, as ``schema.py`` writes it.
* ``schema.some_name`` — how a repository reaches a table object.
* **Raw SQL**: any string constant handed to ``text(...)``, ``execute(...)`` or
  ``exec_driver_sql(...)``. Every identifier following ``FROM``, ``JOIN``,
  ``INTO``, ``UPDATE`` or ``TABLE`` must carry the prefix. ``session.execute(
  text("SELECT email FROM user_account"))`` touches no ``Table`` object at all
  and was previously invisible.
* **Importing a CBA table**: a name imported from ``smartmatch_persistence.schema``
  is bound locally and then used bare, so neither of the first two shapes sees
  it. Only ``METADATA`` may be imported from there; tables come from
  ``smartmatch_persistence.exercise.schema``.
* **``getattr`` on the schema module**: ``getattr(schema, "user_account")`` is
  the attribute walk with the name moved into a string.

A synthetic offender is asserted for each, so the walk is known to be capable
of failing rather than assumed to be.

Why an allow-list of one prefix rather than a denial list of CBA table names
===========================================================================

A denial list has to be maintained, and the failure mode of an unmaintained one
is silence: a CBA table added next month is not on it, so a repository that
joined to it would pass. The prefix is the rule ADR-0025 D2 actually states —
"tables prefixed ``exercise_``" — so a name that is not on the list is refused
by default, which is the direction ADR-0011 requires of an unknown.

What this still cannot see
==========================

**Dynamically assembled SQL.** A query built from pieces at runtime —
``text(f"SELECT * FROM {table}")``, a name read from a column, a string joined
in a loop — names no table in the source, and no source walk can follow it. The
same is true of ``operator.attrgetter``, ``vars()``, and an import written to
dodge this file deliberately. Those are review problems, not lint problems.

**The real control is not in Python at all.** Under OQ-CE-06 the exercise
deployment gets a database role with ``GRANT`` on the ``exercise_`` tables and
nothing else, at which point a query against ``user_account`` is refused by
PostgreSQL whether or not anybody could read it in a diff. This file is the
cheap, early half; the grant is the half that holds when the code is clever.
"""

from __future__ import annotations

import ast
import re
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


#: The only name an exercise module may import from the *shared* schema module.
#: Tables come from ``smartmatch_persistence.exercise.schema``; ``METADATA`` is
#: the registry every table in the process has to be attached to, so it is the
#: one legitimate reason to touch the shared module.
_SHARED_SCHEMA_MODULE = "smartmatch_persistence.schema"
_SHARED_SCHEMA_ALLOWED_NAMES = frozenset({"METADATA"})

#: Calls whose string arguments are SQL rather than prose.
_SQL_CARRYING_CALLS = frozenset({"text", "execute", "exec_driver_sql"})

#: The keywords a table name follows in SQL. Case-insensitive; ``\b`` on both
#: sides so ``FROM exercise_dataset`` matches and ``FROMAGE`` does not.
_SQL_TABLE_KEYWORDS = re.compile(
    r"\b(?:from|join|into|update|table)\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE
)

#: SQL keywords that can follow ``UPDATE``/``INTO`` in a way that is not a table
#: name. ``DELETE FROM ONLY x`` and ``INSERT INTO`` are the realistic ones.
_SQL_NON_TABLE_WORDS = frozenset({"only", "select"})


def _sql_table_names(tree: ast.Module) -> set[str]:
    """Table names inside string constants passed to SQL-carrying calls.

    Deliberately not every string in the module: a docstring or a log message
    containing the word "from" would flag, and a guard that cries wolf gets a
    blanket ignore rather than a fix. Only the arguments of ``text()``,
    ``execute()`` and ``exec_driver_sql()`` are read — which is every way raw
    SQL actually reaches the database from a repository.
    """
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
        if name not in _SQL_CARRYING_CALLS:
            continue
        for argument in node.args:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                found.update(
                    match.lower()
                    for match in _SQL_TABLE_KEYWORDS.findall(argument.value)
                    if match.lower() not in _SQL_NON_TABLE_WORDS
                )
    return found


def _shared_schema_imports(tree: ast.Module) -> set[str]:
    """Names imported from the shared schema module other than ``METADATA``.

    ``from smartmatch_persistence.schema import user_account`` binds the table
    to a bare local name, after which every later use is an ``ast.Name`` that
    the attribute walk cannot recognise. Catching it at the import is the only
    place it is still spelled.
    """
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == _SHARED_SCHEMA_MODULE:
            found.update(
                alias.name for alias in node.names if alias.name not in _SHARED_SCHEMA_ALLOWED_NAMES
            )
    return found


def _getattr_schema_names(tree: ast.Module) -> set[str]:
    """``getattr(schema, "user_account")`` — the attribute walk, as a string."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Name) and node.func.id == "getattr"):
            continue
        if len(node.args) < 2:
            continue
        target, name = node.args[0], node.args[1]
        reaches_schema = (isinstance(target, ast.Name) and target.id == _SCHEMA_MODULE_ALIAS) or (
            isinstance(target, ast.Attribute) and target.attr == _SCHEMA_MODULE_ALIAS
        )
        if (
            reaches_schema
            and isinstance(name, ast.Constant)
            and isinstance(name.value, str)
            and name.value not in _SCHEMA_NON_TABLE_NAMES
        ):
            found.add(name.value)
    return found


def _named_tables(tree: ast.Module) -> set[str]:
    """Every table this module reaches, by any of the five recognised shapes."""
    return (
        _table_literals(tree)
        | _schema_attributes(tree)
        | _sql_table_names(tree)
        | _shared_schema_imports(tree)
        | _getattr_schema_names(tree)
    )


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


def test_the_guard_catches_raw_sql_that_touches_a_cba_table() -> None:
    """M5. ``text("SELECT ... FROM user_account")`` names no ``Table`` object.

    It was invisible to the original walk, which is the dodge that mattered
    most: it is the shortest way for a repository to read a CBA row and the one
    a reviewer skimming imports would not notice.
    """
    raw = ast.parse(
        'def f(session):\n    return session.execute(text("SELECT email FROM user_account"))\n'
    )
    assert "user_account" in _named_tables(raw)

    joined = ast.parse(
        "def f(session):\n"
        "    return session.execute(\n"
        '        text("SELECT 1 FROM exercise_profile JOIN membership ON true")\n'
        "    )\n"
    )
    offenders = {name for name in _named_tables(joined) if not name.startswith(_REQUIRED_PREFIX)}
    assert offenders == {"membership"}

    into = ast.parse('def f(c):\n    return c.exec_driver_sql("INSERT INTO event VALUES (1)")\n')
    assert "event" in _named_tables(into)

    update = ast.parse('def f(c):\n    return c.execute(text("UPDATE user_account SET x = 1"))\n')
    assert "user_account" in _named_tables(update)

    # Honest raw SQL against an exercise table is not flagged.
    fine = ast.parse('def f(c):\n    return c.execute(text("SELECT 1 FROM exercise_dataset"))\n')
    assert {name for name in _named_tables(fine) if not name.startswith(_REQUIRED_PREFIX)} == set()

    # Prose is not SQL: a docstring naming a table must not flag.
    prose = ast.parse('"""This module never selects from user_account."""\n')
    assert _named_tables(prose) == set()


def test_the_guard_catches_a_table_imported_from_the_shared_schema() -> None:
    """A bare local name defeats the attribute walk; the import is where it is spelled."""
    smuggled = ast.parse("from smartmatch_persistence.schema import user_account\n")
    assert _named_tables(smuggled) == {"user_account"}

    aliased = ast.parse("from smartmatch_persistence.schema import membership as m\n")
    assert _named_tables(aliased) == {"membership"}

    # METADATA is the one legitimate reason to touch the shared module.
    allowed = ast.parse("from smartmatch_persistence.schema import METADATA\n")
    assert _named_tables(allowed) == set()


def test_the_guard_catches_getattr_on_the_schema_module() -> None:
    """The attribute walk with the name moved into a string."""
    dodge = ast.parse('def f():\n    return getattr(schema, "user_account")\n')
    assert _named_tables(dodge) == {"user_account"}

    honest = ast.parse('def f():\n    return getattr(schema, "exercise_dataset")\n')
    assert {
        name for name in _named_tables(honest) if not name.startswith(_REQUIRED_PREFIX)
    } == set()


def test_the_exercise_package_imports_only_metadata_from_the_shared_schema() -> None:
    """Asserted of the real modules, not only of a synthetic offender.

    ``workspace_repository.py`` takes its tables from
    ``smartmatch_persistence.exercise.schema``; ``schema.py`` imports
    ``METADATA`` from the shared module because every table in the process must
    attach to one registry. Nothing else may cross that line.
    """
    for module_path in _package_modules():
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        assert _shared_schema_imports(tree) == set(), (
            f"{module_path.name} imports a name other than METADATA from {_SHARED_SCHEMA_MODULE}"
        )


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
