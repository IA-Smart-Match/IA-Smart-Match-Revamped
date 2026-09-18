"""Storage for ``ProductScope.CLASS_EXERCISE``, with no tenancy in it.

ADR-0025 D2: the class exercise keeps its own tables, prefixed ``exercise_``
and keyed by ``(dataset, team)``. They carry no ``tenant_id``, no
``owning_unit_id``, and no foreign key to ``user_account`` or to any other
table outside this family. Modelling the class as an ``org_unit`` under the
CBA tenant was rejected because it would mint about 1,800 fake principals and
put synthetic rows one join from real ones.

What this package may import is part of the rule, not an accident of layout:
``smartmatch_domain`` for enums and rules, ``smartmatch_persistence.schema``
for the one shared ``MetaData`` the drift guard walks — and nothing else from
``smartmatch_persistence``. Not ``smartmatch_authz``, and not a tenant-scoped
repository. The ``pyproject.toml`` import-linter contract covers the first
half; ``tests/unit/test_exercise_schema.py`` covers the second as an
allow-list, so a repository written next year is refused without anyone having
to remember to extend a denial list.

This package holds table definitions only. Repositories, routers and the
spreadsheet ingest are later tracks.
"""

from smartmatch_persistence.exercise.schema import (
    EXERCISE_TABLES,
    EXERCISE_WITHHELD_FIELDS,
)

__all__ = ["EXERCISE_TABLES", "EXERCISE_WITHHELD_FIELDS"]
