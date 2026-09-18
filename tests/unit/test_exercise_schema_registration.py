"""How the exercise tables reach the shared ``METADATA``, pinned in subprocesses.

``smartmatch_persistence.exercise.schema`` registers its eight tables on
``smartmatch_persistence.schema.METADATA`` as an import side effect. That makes
membership of the shared mirror *import-order dependent* in the narrow sense
that a process which never imports the module never sees the tables — the
question this file settles is whether that dependency can produce two different
answers, and whether importing the two modules in either order works at all.

It cannot be settled inside the pytest process. By the time any test runs,
``tests/unit/test_exercise_schema.py`` has already imported the exercise module
and ``METADATA`` holds all eight; an in-process assertion about "the package
root alone" would be asserting about a module that is already loaded. Every
check below therefore runs in a **fresh subprocess** with the same
``PYTHONPATH`` the suite itself uses.

What the checks establish, and why the registration was left lazy:

* Both orders — package root first, exercise module first — import cleanly and
  produce the *same* table set. There is no circular-import hazard in either
  direction and no order-dependent difference in what is defined.
* Importing only ``smartmatch_persistence`` leaves the eight tables off
  ``METADATA``. That is the documented contract rather than a defect: eager
  registration was considered and rejected on the evidence. Nothing iterates
  ``METADATA`` for structure — ``db/migrations/env.py`` sets
  ``target_metadata = None`` (so Alembic never autogenerates against it),
  ``smartmatch_persistence/rewards.py`` tests one unrelated name for
  membership, and no module anywhere calls ``create_all``/``drop_all``. The
  one consumer that walks the whole mirror,
  ``tests/integration/test_schema_matches_migration.py``, imports the exercise
  module by name for exactly this reason and says so in a comment. Adding a
  side-effect import to the persistence package ``__init__`` would make every
  consumer of the package load the exercise family to fix a problem no
  consumer has.

If a consumer that *does* iterate ``METADATA`` for structure ever lands —
``create_all`` in a fixture, or Alembic autogenerate — this file is the place
that decision gets revisited, and the last test below is what fails if the
docstring stops saying so.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")

from smartmatch_persistence.exercise import schema as exercise_schema

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The same entries ``[tool.pytest.ini_options] pythonpath`` puts on ``sys.path``.
#: pytest inserts them into the running interpreter, not into the environment,
#: so a subprocess has to be told separately.
_PACKAGE_PATHS = (
    "python/smartmatch_domain",
    "python/smartmatch_authz",
    "python/smartmatch_providers",
    "python/smartmatch_persistence",
)

EXPECTED_EXERCISE_TABLES = frozenset(exercise_schema.EXERCISE_TABLES)


def _run(import_statements: str) -> dict[str, object]:
    """Import in a fresh interpreter and report what landed on ``METADATA``."""
    script = (
        f"{import_statements}\n"
        "from smartmatch_persistence import schema as core\n"
        "import json, sys\n"
        "json.dump(sorted(core.METADATA.tables), sys.stdout)\n"
    )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT / path) for path in _PACKAGE_PATHS])
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(REPO_ROOT),
        env=environment,
    )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _tables(import_statements: str) -> list[str]:
    outcome = _run(import_statements)
    assert outcome["returncode"] == 0, (
        f"importing in this order failed:\n{import_statements}\n{outcome['stderr']}"
    )
    return list(json.loads(str(outcome["stdout"])))


ROOT_FIRST = "import smartmatch_persistence\nimport smartmatch_persistence.exercise.schema\n"
EXERCISE_FIRST = "import smartmatch_persistence.exercise.schema\nimport smartmatch_persistence\n"
ROOT_ONLY = "import smartmatch_persistence\n"


def test_both_import_orders_give_the_same_table_set():
    """Neither order raises, and neither defines a table the other does not."""
    assert _tables(ROOT_FIRST) == _tables(EXERCISE_FIRST)


@pytest.mark.parametrize(
    ("label", "statements"),
    [("root first", ROOT_FIRST), ("exercise first", EXERCISE_FIRST)],
)
def test_the_exercise_tables_are_registered_under_either_order(label: str, statements: str):
    """Once the module is imported, all eight are on the shared mirror."""
    assert set(_tables(statements)) >= EXPECTED_EXERCISE_TABLES, label


def test_importing_the_package_root_alone_does_not_register_the_exercise_tables():
    """The documented contract, pinned so a silent change to it fails here.

    This is not an aspiration — it is the current, deliberate behaviour, and
    the module docstring of ``exercise/schema.py`` tells a consumer that needs
    the tables to import the module. If eager registration is ever adopted,
    this test is the one that has to be rewritten on purpose.
    """
    registered = set(_tables(ROOT_ONLY))
    assert not (registered & EXPECTED_EXERCISE_TABLES), (
        "the exercise tables are now registered by the package root; if that is "
        "intended, update this test and the schema module docstring together"
    )


def test_the_schema_module_documents_that_consumers_must_import_it():
    """The decision above is only useful where the reader of the module is."""
    source = Path(exercise_schema.__file__).read_text(encoding="utf-8")
    assert "import side effect" in source
    assert "smartmatch_persistence.exercise.schema" in source
