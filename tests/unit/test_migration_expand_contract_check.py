"""Self-tests for ``tools/migration_expand_contract_check.py``.

The gate exists because ``scripts/vm/deploy.sh`` rolls back by rebuilding the
previous commit and never downgrades the schema. A gate that passed a
destructive ``upgrade()`` would let the next release break that rollback with a
green tick on it, so each destructive form is fixtured here and must fail, and
each way of being legitimately destructive — a marked contract revision, a
``downgrade()`` body, a grandfathered file — must pass.
"""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "migration_expand_contract_check",
    REPO_ROOT / "tools" / "migration_expand_contract_check.py",
)
assert _spec and _spec.loader
check = importlib.util.module_from_spec(_spec)
# Registered before execution: ``@dataclass`` resolves annotations through
# ``sys.modules[cls.__module__]``.
sys.modules[_spec.name] = check
_spec.loader.exec_module(check)

_HEADER = """
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "9001_fixture"
down_revision = "9000_fixture"
"""

_MARKER = """
# unused since: release 2026-10-06 (PR #337), which stopped reading the column
CONTRACT_PHASE = True
"""


def _migration(upgrade: str, *, downgrade: str = "pass", extra: str = "") -> str:
    return (
        textwrap.dedent(_HEADER)
        + textwrap.dedent(extra)
        + "\n\ndef upgrade() -> None:\n"
        + textwrap.indent(textwrap.dedent(upgrade).strip("\n"), "    ")
        + "\n\n\ndef downgrade() -> None:\n"
        + textwrap.indent(textwrap.dedent(downgrade).strip("\n"), "    ")
        + "\n"
    )


def _kinds(source: str) -> list[str]:
    return [operation.kind for operation in check.destructive_operations(source)]


# ---------------------------------------------------------------------------
# Additive revisions pass
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "upgrade",
    [
        'op.add_column("t", sa.Column("c", sa.Boolean, nullable=False, server_default="false"))',
        'op.create_table("t", sa.Column("id", sa.Integer))',
        'op.create_index("ix_t_c", "t", ["c"])',
        'op.alter_column("t", "c", nullable=True)',
        'op.alter_column("t", "c", server_default=sa.text("false"))',
        'op.execute("CREATE INDEX ix_t_c ON t (c)")',
        'op.execute("ALTER TABLE t ADD COLUMN c boolean NOT NULL DEFAULT false")',
        'op.execute("UPDATE t SET c = false WHERE c IS NULL")',
        "pass",
    ],
)
def test_an_additive_upgrade_reports_nothing(upgrade: str) -> None:
    assert _kinds(_migration(upgrade)) == []


def test_destructive_words_inside_quoted_sql_data_are_reported_on_purpose() -> None:
    """A known false positive, kept: quoted text is also how PL/pgSQL carries real DDL.

    ``EXECUTE 'ALTER TABLE t DROP COLUMN c'`` inside a ``DO`` block is a real
    drop, and it is indistinguishable here from a logged sentence. Failing a
    harmless statement costs a reword; passing a real drop costs a rollback.
    """
    harmless = "op.execute(\"INSERT INTO log (note) VALUES ('DROP TABLE old')\")"
    real = "op.execute(\"DO $$ BEGIN EXECUTE 'ALTER TABLE t DROP COLUMN c'; END $$\")"
    assert _kinds(_migration(harmless)) == ["execute(DROP)"]
    assert _kinds(_migration(real)) == ["execute(DROP)"]


def test_dropping_a_constraint_or_an_index_is_not_what_this_gate_is_for() -> None:
    """The previous release keeps working without either; see the module docstring."""
    source = _migration(
        """
        op.drop_constraint("t_c_check", "t")
        op.drop_index("ix_t_c")
        op.execute("ALTER TABLE t DROP CONSTRAINT t_c_check")
        op.execute("DROP INDEX ix_t_c")
        op.execute("ALTER TABLE t ALTER COLUMN c DROP NOT NULL")
        op.execute("ALTER TABLE t ALTER COLUMN c DROP DEFAULT")
        op.execute("ALTER TABLE t RENAME CONSTRAINT a TO b")
        """
    )
    assert _kinds(source) == []


# ---------------------------------------------------------------------------
# Each destructive form fails
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("upgrade", "kind"),
    [
        ('op.drop_column("t", "c")', "drop_column"),
        ('op.drop_table("t")', "drop_table"),
        ('op.rename_table("t", "u")', "rename_table"),
        ('op.alter_column("t", "c", new_column_name="d")', "alter_column(new_column_name)"),
        ('op.execute("ALTER TABLE t DROP COLUMN c")', "execute(DROP)"),
        ('op.execute("ALTER TABLE t DROP c")', "execute(DROP)"),
        ('op.execute("ALTER TABLE t DROP IF EXISTS c")', "execute(DROP)"),
        ('op.execute("alter table t drop column c")', "execute(DROP)"),
        ('op.execute("DROP TABLE t")', "execute(DROP)"),
        ('op.execute("DROP TABLE IF EXISTS t CASCADE")', "execute(DROP)"),
        ('op.execute("DROP VIEW v")', "execute(DROP)"),
        ('op.execute("DROP MATERIALIZED VIEW v")', "execute(DROP)"),
        ('op.execute("DROP TYPE mood")', "execute(DROP)"),
        ('op.execute("DROP SCHEMA s")', "execute(DROP)"),
        ('op.execute("ALTER TABLE t RENAME TO u")', "execute(RENAME)"),
        ('op.execute("ALTER TABLE t RENAME COLUMN c TO d")', "execute(RENAME)"),
        ('op.execute("ALTER TABLE t RENAME c TO d")', "execute(RENAME)"),
        ('op.execute(sa.text("ALTER TABLE t DROP COLUMN c"))', "execute(DROP)"),
        ('op.get_bind().execute(sa.text("DROP TABLE t"))', "execute(DROP)"),
        ('op.execute("ALTER TABLE t " "DROP COLUMN c")', "execute(DROP)"),
        ('op.execute("ALTER TABLE t " + "DROP COLUMN c")', "execute(DROP)"),
        ('op.execute(f"ALTER TABLE {_TABLE} DROP COLUMN {_COLUMN}")', "execute(DROP)"),
        ("op.execute(_SQL)", "execute(DROP)"),
    ],
)
def test_a_destructive_upgrade_is_reported(upgrade: str, kind: str) -> None:
    extra = """
    _TABLE = "t"
    _COLUMN = "c"
    _SQL = "ALTER TABLE t DROP COLUMN c"
    """
    assert _kinds(_migration(upgrade, extra=extra)) == [kind]


def test_a_batch_operation_is_reported() -> None:
    source = _migration(
        """
        with op.batch_alter_table("t") as batch_op:
            batch_op.drop_column("c")
        """
    )
    assert _kinds(source) == ["drop_column"]


def test_a_drop_inside_a_helper_upgrade_calls_is_reported() -> None:
    """Moving the drop into a helper must not be a way round the gate."""
    extra = """

    def _retire() -> None:
        _really_retire()


    def _really_retire() -> None:
        op.drop_column("t", "c")
    """
    assert _kinds(_migration("_retire()", extra=extra)) == ["drop_column"]


def test_a_drop_inside_a_helper_reached_through_a_module_level_alias_is_reported() -> None:
    extra = """

    def _retire() -> None:
        op.drop_table("old")


    STEP = _retire
    STEPS = {"retire": [STEP]}
    """
    assert _kinds(_migration("STEP()", extra=extra)) == ["drop_table"]
    assert _kinds(_migration('STEPS["retire"][0]()', extra=extra)) == ["drop_table"]


@pytest.mark.parametrize(
    "upgrade",
    [
        'op.execute("DROP {kind} old".format(kind="TABLE"))',
        'op.execute("DROP {} old".format("TABLE"))',
        'op.execute("{1} {0} old".format("TABLE", "DROP"))',
        'op.execute("ALTER TABLE {t} DROP COLUMN {c}".format(t=_TABLE, c=_COLUMN))',
        'op.execute("DROP %s old" % "TABLE")',
        'op.execute("%s %s old" % ("DROP", "TABLE"))',
        'op.execute("DROP %(kind)s old" % {"kind": "TABLE"})',
        'op.execute(sa.text("DROP {kind} old".format(kind="TABLE")))',
    ],
)
def test_sql_assembled_with_format_or_percent_is_read_as_assembled(upgrade: str) -> None:
    extra = """
    _TABLE = "t"
    _COLUMN = "c"
    """
    assert _kinds(_migration(upgrade, extra=extra)) == ["execute(DROP)"]


def test_a_formatted_statement_that_drops_nothing_reports_nothing() -> None:
    upgrade = 'op.execute("CREATE INDEX {name} ON t (c)".format(name="ix_t_c"))'
    assert _kinds(_migration(upgrade)) == []


@pytest.mark.parametrize(
    ("upgrade", "signature"),
    [
        ('op.drop_column("t", "c")', "drop_column t.c"),
        ("op.drop_column(_TABLE, _COLUMN)", "drop_column t.c"),
        ('op.drop_table("t")', "drop_table t"),
        ('op.rename_table("t", "u")', "rename_table t.u"),
        (
            'op.alter_column("t", "c", new_column_name="d")',
            "alter_column(new_column_name) t.c.d",
        ),
        (
            'op.execute("ALTER TABLE t  /* why */   DROP COLUMN c  -- gone")',
            "execute(DROP) ALTER TABLE T DROP COLUMN C",
        ),
    ],
)
def test_an_operation_names_what_it_removes(upgrade: str, signature: str) -> None:
    extra = """
    _TABLE = "t"
    _COLUMN = "c"
    """
    (operation,) = check.destructive_operations(_migration(upgrade, extra=extra))
    assert operation.signature == signature


def test_a_drop_inside_a_branch_or_a_loop_is_reported() -> None:
    source = _migration(
        """
        for column in ("a", "b"):
            if column:
                op.drop_column("t", column)
        """
    )
    assert _kinds(source) == ["drop_column"]


def test_the_line_reported_is_the_line_of_the_call() -> None:
    source = _migration('op.add_column("t", sa.Column("c", sa.Text))\nop.drop_table("u")')
    (operation,) = check.destructive_operations(source)
    assert source.splitlines()[operation.line - 1].strip() == 'op.drop_table("u")'


# ---------------------------------------------------------------------------
# Downgrade bodies are exempt
# ---------------------------------------------------------------------------


def test_a_drop_only_in_downgrade_reports_nothing() -> None:
    source = _migration(
        'op.add_column("t", sa.Column("c", sa.Boolean))',
        downgrade='op.drop_column("t", "c")\nop.execute("DROP TABLE u")',
    )
    assert _kinds(source) == []


def test_a_helper_only_downgrade_calls_is_exempt() -> None:
    extra = """

    def _undo() -> None:
        op.drop_table("t")
    """
    source = _migration('op.create_table("t")', downgrade="_undo()", extra=extra)
    assert _kinds(source) == []


def test_a_file_with_no_upgrade_function_reports_nothing() -> None:
    assert _kinds("import os\n") == []


# ---------------------------------------------------------------------------
# The contract marker
# ---------------------------------------------------------------------------


def test_a_marked_contract_revision_is_recognised() -> None:
    source = _migration('op.drop_column("t", "c")', extra=_MARKER)
    assert check.contract_marker(source) == check.Marker(declared=True, release_named=True)


def test_the_release_may_be_named_on_the_same_line() -> None:
    extra = "\nCONTRACT_PHASE = True  # unused since: release 2026-10-06 (PR #337)\n"
    source = _migration('op.drop_column("t", "c")', extra=extra)
    assert check.contract_marker(source) == check.Marker(declared=True, release_named=True)


@pytest.mark.parametrize(
    "extra",
    [
        "\nCONTRACT_PHASE = True\n",
        "\n# a contract step\nCONTRACT_PHASE = True\n",
        "\n# unused since:\nCONTRACT_PHASE = True\n",
        "\n# unused since: TBD\nCONTRACT_PHASE = True\n",
        "\n# unused since: the last release\nCONTRACT_PHASE = True\n",
        "\nCONTRACT_PHASE = True  # unused since: TODO\n",
        "\n# unused since: release 2026-10-06\n\nOTHER = 1\nCONTRACT_PHASE = True\n",
    ],
)
def test_a_marker_without_a_named_release_is_declared_but_incomplete(extra: str) -> None:
    source = _migration('op.drop_column("t", "c")', extra=extra)
    assert check.contract_marker(source) == check.Marker(declared=True, release_named=False)


@pytest.mark.parametrize(
    "extra",
    [
        "",
        "\nCONTRACT_PHASE = False\n",
        '\nCONTRACT_PHASE = "yes"\n',
        "\n# CONTRACT_PHASE = True  # unused since: release 2026-10-06\n",
        '\nNOTE = "CONTRACT_PHASE = True  # unused since: release 2026-10-06"\n',
    ],
)
def test_anything_but_a_module_level_true_is_not_a_marker(extra: str) -> None:
    source = _migration('op.drop_column("t", "c")', extra=extra)
    assert check.contract_marker(source).declared is False


@pytest.mark.parametrize(
    "release",
    ["release 2026-10-06", "PR #337", "v1.4.0", "commit 6de70905", "2026-10-06 (#337)"],
)
def test_a_release_is_named_by_a_date_a_number_or_a_commit(release: str) -> None:
    extra = f"\n# unused since: {release}\nCONTRACT_PHASE = True\n"
    source = _migration('op.drop_column("t", "c")', extra=extra)
    assert check.contract_marker(source).release_named is True


def test_a_marker_set_inside_a_function_is_not_a_marker() -> None:
    source = _migration('CONTRACT_PHASE = True  # unused since: release X\nop.drop_table("t")')
    assert check.contract_marker(source).declared is False


# ---------------------------------------------------------------------------
# The whole directory
# ---------------------------------------------------------------------------


def _write(directory: Path, name: str, source: str) -> None:
    (directory / name).write_text(source, encoding="utf-8")


def test_an_additive_directory_is_clean(tmp_path: Path) -> None:
    _write(tmp_path, "0001_add.py", _migration('op.add_column("t", sa.Column("c", sa.Text))'))
    assert check.check(tmp_path, baseline={}) == []


def test_an_unmarked_destructive_revision_is_a_violation(tmp_path: Path) -> None:
    _write(tmp_path, "0002_drop.py", _migration('op.drop_column("t", "c")'))
    (violation,) = check.check(tmp_path, baseline={})
    assert violation.path == "0002_drop.py"
    assert "drop_column" in violation.message
    assert "CONTRACT_PHASE" in violation.message


def test_a_marked_destructive_revision_passes(tmp_path: Path) -> None:
    _write(tmp_path, "0002_drop.py", _migration('op.drop_column("t", "c")', extra=_MARKER))
    assert check.check(tmp_path, baseline={}) == []


def test_a_marker_without_a_named_release_is_a_violation(tmp_path: Path) -> None:
    extra = "\nCONTRACT_PHASE = True\n"
    _write(tmp_path, "0002_drop.py", _migration('op.drop_column("t", "c")', extra=extra))
    (violation,) = check.check(tmp_path, baseline={})
    assert "unused since" in violation.message


def test_a_downgrade_only_drop_passes(tmp_path: Path) -> None:
    source = _migration('op.create_table("t")', downgrade='op.drop_table("t")')
    _write(tmp_path, "0003_create.py", source)
    assert check.check(tmp_path, baseline={}) == []


def test_a_grandfathered_revision_passes_with_exactly_its_recorded_operations(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "0001_old.py", _migration('op.drop_column("t", "c")'))
    assert check.check(tmp_path, baseline={"0001_old.py": ("drop_column t.c",)}) == []


def test_a_grandfathered_revision_changed_to_drop_more_is_a_violation(tmp_path: Path) -> None:
    """A CHANGED migration is checked too: the baseline records operations, not a name."""
    source = _migration('op.drop_column("t", "c")\nop.drop_table("u")')
    _write(tmp_path, "0001_old.py", source)
    (violation,) = check.check(tmp_path, baseline={"0001_old.py": ("drop_column t.c",)})
    assert violation.path == "0001_old.py"
    assert "drop_table" in violation.message


def test_a_second_drop_of_the_same_kind_in_a_grandfathered_file_is_a_violation(
    tmp_path: Path,
) -> None:
    source = _migration('op.drop_column("t", "c")\nop.drop_column("t", "d")')
    _write(tmp_path, "0001_old.py", source)
    assert len(check.check(tmp_path, baseline={"0001_old.py": ("drop_column t.c",)})) == 1


def test_a_grandfathered_revision_changed_to_drop_something_else_is_a_violation(
    tmp_path: Path,
) -> None:
    """Same kind, different column: the baseline records the target, not only the kind."""
    _write(tmp_path, "0001_old.py", _migration('op.drop_column("t", "still_used")'))
    (violation,) = check.check(tmp_path, baseline={"0001_old.py": ("drop_column t.c",)})
    assert "drop_column t.still_used" in violation.message


def test_a_file_that_does_not_parse_is_a_violation_not_a_pass(tmp_path: Path) -> None:
    _write(tmp_path, "0004_broken.py", "def upgrade(:\n")
    (violation,) = check.check(tmp_path, baseline={})
    assert violation.path == "0004_broken.py"
    assert "parse" in violation.message


def test_a_missing_directory_is_an_error_not_a_pass(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        check.check(tmp_path / "absent", baseline={})


# ---------------------------------------------------------------------------
# The repository itself
# ---------------------------------------------------------------------------


def test_the_repository_passes_its_own_gate() -> None:
    assert check.check(check.MIGRATIONS_DIR, baseline=check.BASELINE) == []


def test_every_baseline_entry_names_a_migration_that_exists_and_still_needs_it() -> None:
    """A stale entry is an exemption nobody is using, waiting for a file to reuse the name."""
    for name, recorded in check.BASELINE.items():
        path = check.MIGRATIONS_DIR / name
        assert path.is_file(), name
        found = sorted(
            operation.signature
            for operation in check.destructive_operations(path.read_text(encoding="utf-8"))
        )
        assert found == sorted(recorded), name


def test_no_grandfathered_migration_is_newer_than_the_baseline_head() -> None:
    """The baseline is closed: a new destructive revision takes the marker, not an entry."""
    for name in check.BASELINE:
        assert name[:4] <= check.BASELINE_HEAD_PREFIX, name


def test_main_exits_zero_on_the_repository(capsys: pytest.CaptureFixture[str]) -> None:
    assert check.main([]) == 0
    assert "clean" in capsys.readouterr().out


def test_main_exits_one_and_names_the_file_and_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, "0002_drop.py", _migration('op.drop_column("t", "c")'))
    assert check.main([], migrations_dir=tmp_path, baseline={}) == 1
    assert "0002_drop.py:" in capsys.readouterr().err


def test_main_takes_no_option_that_could_switch_the_gate_off() -> None:
    with pytest.raises(SystemExit):
        check.main(["--no-baseline"])
