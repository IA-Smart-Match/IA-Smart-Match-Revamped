#!/usr/bin/env python3
"""A release only adds to the schema: the expand/contract gate for migrations.

``scripts/vm/deploy.sh`` rolls a failed deployment back by rebuilding the
previous commit. It never downgrades the schema. So the previous release has to
keep working against the schema the new release migrated to, and that holds
only if the new release's migrations *added* to the schema and removed nothing
the previous release reads or writes. ``db/migrations/script.py.mako`` has said
so since the first revision — expand, migrate, contract, with the destructive
step in a later release — and until this gate nothing checked it.

What fails
----------
A migration whose ``upgrade()`` — or a module-level helper ``upgrade()`` calls,
however indirectly — contains one of:

* ``drop_column``, ``drop_table``, ``rename_table`` (on ``op`` or a batch);
* ``alter_column(..., new_column_name=...)``;
* raw SQL passed to ``execute`` / ``exec_driver_sql`` that drops a table,
  column, view, materialized view, type or schema, or renames anything but a
  constraint or an index.

``downgrade()`` is exempt: it is not run by a deployment or by its rollback.
Dropping a constraint, an index, a default or ``NOT NULL`` is not reported: the
previous release reads and writes the same columns without them.

How a contract migration passes
-------------------------------
The destructive step belongs in a later release, once the release that stopped
using the object is promoted and stable. Such a revision says so at module
level, and names that release in a comment on the marker's line or directly
above it::

    # unused since: release 2026-10-06 (PR #337), which stopped reading the column
    CONTRACT_PHASE = True

The marker without the ``unused since:`` comment fails, and so does a comment
that names nothing: the release has to carry a digit — a date, a pull request
number, a version or a commit — so ``TBD`` is not a release. The comment is the
claim a reviewer checks; the marker alone is a switch.

Scope: every migration, with a closed baseline
----------------------------------------------
Every file in ``db/migrations/versions`` is checked on every run. There is no
"changed in this pull request" filter to get wrong: such a filter needs the
merge base, and a shallow clone, a push to ``main`` or a missing remote ref
would each turn it into a check of nothing.

The revisions that were already destructive when this gate landed are listed in
:data:`BASELINE` with the exact operations they contain, target included
(``drop_column point_ledger_entry.reverses_entry_id``). A listed file passes
with those operations and no others, so *changing* an old migration to drop
something more, or something else, fails exactly as a new migration would. The baseline is closed
at :data:`BASELINE_HEAD_PREFIX`: a newer revision takes the marker, never an
entry (``tests/unit/test_migration_expand_contract_check.py`` holds both).

Known limits
------------
This reads source; it does not run it. SQL is followed through literals,
f-strings, ``+``, ``%``, ``.format()``, wrapping calls such as ``sa.text`` and
names bound at module level or in a function ``upgrade()`` reaches, and helpers
are followed through module-level aliases. SQL built from a function
*argument*, read from a file, or produced by code this cannot evaluate is not
seen. Review still owns those.

Destructive words inside quoted SQL data are reported, on purpose: quoting is
also how a ``DO`` block's ``EXECUTE '...'`` carries real DDL, and the two are
indistinguishable here. A false alarm costs a reword; a missed drop costs a
rollback.

Stdlib only. Usage::

    python tools/migration_expand_contract_check.py

Exit codes: ``0`` clean, ``1`` violations found.
"""

from __future__ import annotations

import argparse
import ast
import io
import re
import sys
import tokenize
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR: Final[Path] = REPO_ROOT / "db" / "migrations" / "versions"

MARKER_NAME: Final[str] = "CONTRACT_PHASE"

#: The four-digit prefix of the head revision when this gate landed. No file
#: with a later prefix may appear in :data:`BASELINE`.
BASELINE_HEAD_PREFIX: Final[str] = "0043"

#: Revisions that were destructive in ``upgrade()`` before this gate existed,
#: with the :attr:`Operation.signature` of each operation they contain. They
#: shipped; failing them now would protect nothing. Closed — see the module
#: docstring.
BASELINE: Final[Mapping[str, tuple[str, ...]]] = {
    "0015_remove_unauthorized_ledger_reversal.py": (
        "drop_column point_ledger_entry.reverses_entry_id",
    ),
}

_DIRECT_OPERATIONS: Final[frozenset[str]] = frozenset({"drop_column", "drop_table", "rename_table"})
_EXECUTE_METHODS: Final[frozenset[str]] = frozenset({"execute", "exec_driver_sql"})

#: Stands in for a value this check cannot read (a function argument, an
#: attribute). An identifier, so the SQL around it still parses as SQL.
_UNKNOWN: Final[str] = " __X__ "

_SQL_LINE_COMMENT: Final[re.Pattern[str]] = re.compile(r"--[^\n]*")
_SQL_BLOCK_COMMENT: Final[re.Pattern[str]] = re.compile(r"/\*.*?\*/", re.DOTALL)
_DROP_OBJECT: Final[re.Pattern[str]] = re.compile(
    r"\bDROP\s+(TABLE|COLUMN|VIEW|MATERIALIZED\s+VIEW|TYPE|SCHEMA)\b"
)
_ALTER_TABLE: Final[re.Pattern[str]] = re.compile(r"\bALTER\s+TABLE\b")
#: Inside ``ALTER TABLE``, ``DROP <name>`` drops a column: ``COLUMN`` is
#: optional in PostgreSQL. What follows ``DROP`` otherwise is one of these.
_ALTER_TABLE_DROP: Final[re.Pattern[str]] = re.compile(
    r"\bDROP\s+(?!CONSTRAINT\b|NOT\s+NULL\b|DEFAULT\b|IDENTITY\b|EXPRESSION\b)\S"
)
_ALTER_INDEX: Final[re.Pattern[str]] = re.compile(r"^\s*ALTER\s+INDEX\b")
_RENAME: Final[re.Pattern[str]] = re.compile(r"\bRENAME\s+(?!CONSTRAINT\b)\S")

#: A release is named by something with a digit in it: a date, a pull request
#: number, a version, a commit. ``TBD`` and "the last release" are not names.
_RELEASE_COMMENT: Final[re.Pattern[str]] = re.compile(
    r"unused\s+since\s*:?\s*\S[^\n]*\d", re.IGNORECASE
)

_FORMAT_FIELD: Final[re.Pattern[str]] = re.compile(r"\{(\w*)[^{}]*\}")
_PERCENT_FIELD: Final[re.Pattern[str]] = re.compile(r"%(?:\((\w+)\))?[-#0 +]*\d*(?:\.\d+)?[sdrif]")
_WHITESPACE: Final[re.Pattern[str]] = re.compile(r"\s+")


@dataclass(frozen=True)
class Operation:
    """One destructive operation reachable from ``upgrade()``.

    Attributes:
        kind: What it is, e.g. ``drop_column`` or ``execute(DROP)``.
        line: The 1-based line of the call.
        target: What it acts on, as far as the source says: ``table.column``
            for a direct operation, the statement for raw SQL.
    """

    kind: str
    line: int
    target: str = ""

    @property
    def signature(self) -> str:
        """Kind and target together — the spelling :data:`BASELINE` records."""
        return f"{self.kind} {self.target}".strip()


@dataclass(frozen=True)
class Marker:
    """What a migration says about being a contract-phase revision.

    Attributes:
        declared: ``CONTRACT_PHASE = True`` is assigned at module level.
        release_named: An ``unused since: <release>`` comment sits on that
            line or in the comment block directly above it.
    """

    declared: bool
    release_named: bool


@dataclass(frozen=True)
class Violation:
    """One reason the gate fails.

    Attributes:
        path: The migration's file name.
        line: The 1-based line, or ``0`` when the whole file is at fault.
        message: What is wrong and what to do about it.
    """

    path: str
    line: int
    message: str


# ---------------------------------------------------------------------------
# What upgrade() reaches
# ---------------------------------------------------------------------------


def _module_functions(tree: ast.Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }


def _reachable_from_upgrade(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """``upgrade`` and every module-level function it calls, however indirectly."""
    functions = _module_functions(tree)
    if "upgrade" not in functions:
        return []
    aliases = _bindings(tree, [])
    reached = ["upgrade"]
    followed: set[str] = set()
    pending: list[ast.AST] = [functions["upgrade"]]
    while pending:
        for node in ast.walk(pending.pop()):
            if not isinstance(node, ast.Name):
                continue
            # Any mention of a module-level function counts, not only a direct
            # call: ``for step in (_a, _b): step()`` reaches both.
            if node.id in functions:
                if node.id not in reached:
                    reached.append(node.id)
                    pending.append(functions[node.id])
            # ``STEP = _retire`` at module level, then ``STEP()``: follow the
            # name to whatever it was bound to.
            elif node.id in aliases and node.id not in followed:
                followed.add(node.id)
                pending.extend(aliases[node.id])
    return [functions[name] for name in reached]


def _bindings(
    tree: ast.Module, functions: Sequence[ast.FunctionDef | ast.AsyncFunctionDef]
) -> dict[str, list[ast.expr]]:
    """Every expression a plain name is bound to, at module level or in ``functions``.

    Deliberately flow-insensitive: a name bound twice resolves to both values,
    so SQL assigned on either branch of an ``if`` is read.
    """
    found: dict[str, list[ast.expr]] = {}

    def record(target: ast.expr, value: ast.expr | None) -> None:
        if isinstance(target, ast.Name) and value is not None:
            found.setdefault(target.id, []).append(value)

    def collect(nodes: Iterator[ast.AST]) -> None:
        for node in nodes:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    record(target, node.value)
            elif isinstance(node, ast.AnnAssign | ast.NamedExpr):
                record(node.target, node.value)
            elif isinstance(node, ast.For | ast.AsyncFor | ast.comprehension):
                record(node.target, node.iter)

    collect(iter(tree.body))
    for function in functions:
        collect(ast.walk(function))
    return found


def _text_of(node: ast.AST, bindings: Mapping[str, list[ast.expr]], active: frozenset[str]) -> str:
    """The SQL text an expression evaluates to, as far as it can be read statically."""
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else _UNKNOWN
    if isinstance(node, ast.JoinedStr):
        return "".join(_text_of(value, bindings, active) for value in node.values)
    if isinstance(node, ast.FormattedValue):
        return _text_of(node.value, bindings, active)
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Mod):
            return _percent_formatted(node, bindings, active)
        return _text_of(node.left, bindings, active) + _text_of(node.right, bindings, active)
    if isinstance(node, ast.Name):
        if node.id in active or node.id not in bindings:
            return _UNKNOWN
        nested = active | {node.id}
        return " ; ".join(_text_of(value, bindings, nested) for value in bindings[node.id])
    if isinstance(node, ast.Tuple | ast.List | ast.Set):
        return " ; ".join(_text_of(element, bindings, active) for element in node.elts)
    if isinstance(node, ast.Dict):
        return " ; ".join(_text_of(value, bindings, active) for value in node.values)
    if isinstance(node, ast.Starred):
        return _text_of(node.value, bindings, active)
    if isinstance(node, ast.IfExp):
        return " ; ".join(_text_of(branch, bindings, active) for branch in (node.body, node.orelse))
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute) and node.func.attr == "format":
            return _str_formatted(node, node.func.value, bindings, active)
        # ``sa.text("...")``, ``textwrap.dedent("...")``, ``sa.text("...").bindparams()``.
        parts = [*node.args, *(keyword.value for keyword in node.keywords)]
        if isinstance(node.func, ast.Attribute):
            parts.insert(0, node.func.value)
        return " ".join(_text_of(part, bindings, active) for part in parts)
    return _UNKNOWN


def _filled(
    template: str, pattern: re.Pattern[str], positional: Sequence[str], named: Mapping[str, str]
) -> str:
    """``template`` with each replacement field swapped for the value it takes."""
    automatic = iter(positional)

    def value(match: re.Match[str]) -> str:
        field = match.group(1) or ""
        if field.isdigit():
            index = int(field)
            return positional[index] if index < len(positional) else _UNKNOWN
        if field:
            return named.get(field, _UNKNOWN)
        return next(automatic, _UNKNOWN)

    return pattern.sub(value, template)


def _str_formatted(
    call: ast.Call,
    template: ast.expr,
    bindings: Mapping[str, list[ast.expr]],
    active: frozenset[str],
) -> str:
    """``"DROP {kind} old".format(kind="TABLE")`` as the string it produces."""
    positional = [_text_of(argument, bindings, active) for argument in call.args]
    named = {
        keyword.arg: _text_of(keyword.value, bindings, active)
        for keyword in call.keywords
        if keyword.arg is not None
    }
    return _filled(_text_of(template, bindings, active), _FORMAT_FIELD, positional, named)


def _percent_formatted(
    node: ast.BinOp, bindings: Mapping[str, list[ast.expr]], active: frozenset[str]
) -> str:
    """``"DROP %s old" % "TABLE"`` as the string it produces."""
    positional: list[str] = []
    named: dict[str, str] = {}
    if isinstance(node.right, ast.Tuple):
        positional = [_text_of(element, bindings, active) for element in node.right.elts]
    elif isinstance(node.right, ast.Dict):
        named = {
            key.value: _text_of(value, bindings, active)
            for key, value in zip(node.right.keys, node.right.values, strict=True)
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        }
    else:
        positional = [_text_of(node.right, bindings, active)]
    return _filled(_text_of(node.left, bindings, active), _PERCENT_FIELD, positional, named)


def _drops(statement: str) -> bool:
    if _DROP_OBJECT.search(statement):
        return True
    return bool(_ALTER_TABLE.search(statement) and _ALTER_TABLE_DROP.search(statement))


def _renames(statement: str) -> bool:
    return bool(_RENAME.search(statement) and not _ALTER_INDEX.search(statement))


def _normalized_sql(sql: str) -> str:
    """SQL without comments, upper-cased, on one line."""
    stripped = _SQL_BLOCK_COMMENT.sub(" ", _SQL_LINE_COMMENT.sub(" ", sql))
    return _WHITESPACE.sub(" ", stripped).strip().upper()


def _sql_kinds(normalized: str) -> list[str]:
    """Which destructive kinds one piece of normalized SQL contains, each at most once."""
    statements = normalized.split(";")
    kinds: list[str] = []
    if any(_drops(statement) for statement in statements):
        kinds.append("execute(DROP)")
    if any(_renames(statement) for statement in statements):
        kinds.append("execute(RENAME)")
    return kinds


def _renames_a_column(call: ast.Call) -> bool:
    return any(
        keyword.arg == "new_column_name"
        and not (isinstance(keyword.value, ast.Constant) and keyword.value.value is None)
        for keyword in call.keywords
    )


def _object_named(call: ast.Call, bindings: Mapping[str, list[ast.expr]]) -> str:
    """``table.column`` (or whatever the call names), from its arguments in order."""
    arguments = [*call.args, *(keyword.value for keyword in call.keywords)]
    parts = (_text_of(argument, bindings, frozenset()).strip() for argument in arguments)
    return ".".join(part for part in parts if part)


def _call_operations(
    call: ast.Call, bindings: Mapping[str, list[ast.expr]]
) -> list[tuple[str, str]]:
    """``(kind, target)`` for each destructive thing one call does."""
    if not isinstance(call.func, ast.Attribute):
        return []
    method = call.func.attr
    if method in _DIRECT_OPERATIONS:
        return [(method, _object_named(call, bindings))]
    if method == "alter_column" and _renames_a_column(call):
        return [("alter_column(new_column_name)", _object_named(call, bindings))]
    if method in _EXECUTE_METHODS:
        arguments = [*call.args, *(keyword.value for keyword in call.keywords)]
        sql = " ; ".join(_text_of(argument, bindings, frozenset()) for argument in arguments)
        normalized = _normalized_sql(sql)
        return [(kind, normalized) for kind in _sql_kinds(normalized)]
    return []


def destructive_operations(source: str) -> list[Operation]:
    """Every destructive operation ``upgrade()`` reaches in one migration's source.

    Args:
        source: The migration file's text.

    Returns:
        The operations in line order. Empty for an additive migration and for
        a file with no ``upgrade`` function.

    Raises:
        SyntaxError: The source is not valid Python.
    """
    tree = ast.parse(source)
    functions = _reachable_from_upgrade(tree)
    bindings = _bindings(tree, functions)
    found = {
        (node.lineno, node.col_offset, kind, target)
        for function in functions
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        for kind, target in _call_operations(node, bindings)
    }
    return [
        Operation(kind=kind, line=line, target=target) for line, _, kind, target in sorted(found)
    ]


# ---------------------------------------------------------------------------
# The contract marker
# ---------------------------------------------------------------------------


def _marker_line(tree: ast.Module) -> int | None:
    """The line of a module-level ``CONTRACT_PHASE = True``, if there is one."""
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets: list[ast.expr] = list(node.targets)
            value: ast.expr | None = node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        else:
            continue
        named = any(isinstance(target, ast.Name) and target.id == MARKER_NAME for target in targets)
        if named and isinstance(value, ast.Constant) and value.value is True:
            return node.lineno
    return None


def _comments_by_line(source: str) -> dict[int, tuple[str, bool]]:
    """``{line: (comment text, whether the comment is the whole line)}``."""
    comments: dict[int, tuple[str, bool]] = {}
    lines = source.splitlines()
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            row, column = token.start
            comments[row] = (token.string, not lines[row - 1][:column].strip())
    return comments


def contract_marker(source: str) -> Marker:
    """What a migration's source says about being a contract-phase revision.

    Raises:
        SyntaxError: The source is not valid Python.
    """
    line = _marker_line(ast.parse(source))
    if line is None:
        return Marker(declared=False, release_named=False)
    comments = _comments_by_line(source)
    candidates = [comments[line][0]] if line in comments else []
    above = line - 1
    while above in comments and comments[above][1]:
        candidates.append(comments[above][0])
        above -= 1
    named = any(_RELEASE_COMMENT.search(comment) for comment in candidates)
    return Marker(declared=True, release_named=named)


# ---------------------------------------------------------------------------
# The whole directory
# ---------------------------------------------------------------------------

_HOW_TO_MARK: Final[str] = (
    "A release may only add to the schema: scripts/vm/deploy.sh rolls back by rebuilding "
    "the previous commit and never downgrades, so the previous release must still work "
    "against this schema. Ship the destructive step in a LATER release, and mark that "
    f"revision at module level with `{MARKER_NAME} = True` under a comment "
    "`# unused since: <the release that stopped using the object>`."
)


def _beyond_baseline(operations: Sequence[Operation], recorded: Sequence[str]) -> list[Operation]:
    """The operations a grandfathered file contains beyond the ones recorded for it."""
    allowance = Counter(recorded)
    extra: list[Operation] = []
    for operation in operations:
        if allowance[operation.signature] > 0:
            allowance[operation.signature] -= 1
        else:
            extra.append(operation)
    return extra


def _file_violations(
    name: str, source: str, baseline: Mapping[str, Sequence[str]]
) -> list[Violation]:
    try:
        operations = destructive_operations(source)
        marker = contract_marker(source)
    except (SyntaxError, tokenize.TokenError) as error:
        return [Violation(name, 0, f"does not parse, so it cannot be checked: {error}")]
    if name in baseline:
        return [
            Violation(
                name,
                operation.line,
                f"{operation.signature} in upgrade() is not one of the operations recorded for "
                f"this grandfathered revision. {_HOW_TO_MARK}",
            )
            for operation in _beyond_baseline(operations, baseline[name])
        ]
    if marker.declared and marker.release_named:
        return []
    if marker.declared:
        problem = (
            f"{MARKER_NAME} = True is set without naming the release: add "
            "`# unused since: <release>` on that line or directly above it, where the "
            "release is a date, a pull request number, a version or a commit."
        )
    else:
        problem = _HOW_TO_MARK
    return [
        Violation(name, operation.line, f"{operation.signature} in upgrade(). {problem}")
        for operation in operations
    ]


def check(migrations_dir: Path, *, baseline: Mapping[str, Sequence[str]]) -> list[Violation]:
    """Check every migration in a directory.

    Args:
        migrations_dir: The Alembic ``versions`` directory.
        baseline: ``{file name: operations}`` for the grandfathered revisions.

    Returns:
        The violations, in file then line order. Empty when the gate passes.

    Raises:
        FileNotFoundError: ``migrations_dir`` is not a directory. A gate
            pointed at nothing must not report that nothing is wrong.
    """
    if not migrations_dir.is_dir():
        raise FileNotFoundError(f"no migrations directory at {migrations_dir}")
    violations: list[Violation] = []
    for path in sorted(migrations_dir.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        violations.extend(_file_violations(path.name, source, baseline))
    return violations


def main(
    argv: Sequence[str] | None = None,
    *,
    migrations_dir: Path = MIGRATIONS_DIR,
    baseline: Mapping[str, Sequence[str]] = BASELINE,
) -> int:
    """Run the gate. Takes no options: there is nothing to switch off."""
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args(argv)
    violations = check(migrations_dir, baseline=baseline)
    if violations:
        print(
            f"{len(violations)} destructive migration step(s) outside a contract phase:\n",
            file=sys.stderr,
        )
        for violation in violations:
            print(f"{violation.path}:{violation.line}: {violation.message}\n", file=sys.stderr)
        return 1
    count = len(list(migrations_dir.glob("*.py")))
    print(f"clean: {count} migration(s) checked, {len(baseline)} grandfathered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
