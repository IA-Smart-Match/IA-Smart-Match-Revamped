"""``login_accounts`` is the only writer of ``pilot_credential`` (B26 T6b-5 plan §3.3, R-G).

Parent plan §11 risk 2b: a future account-creation path that inserts a second
credential for an address would make ``load_by_email`` refuse both logins. The
guard is structural: every credential insert, update and delete goes through
``smartmatch_persistence.login_accounts``, and this file fails if any other
module in ``python/``, ``services/``, ``tools/``, ``scripts/`` or ``db/`` spells
one. ``tests/`` is not scanned: fixtures write rows directly.

The detector is tested on planted snippets first (the shape of
``test_the_router_shape_guard_would_actually_catch_each_shape`` in
``tests/authz/test_policy_matrix.py``), so a guard that silently matches nothing
cannot pass.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SCANNED = ("python", "services", "tools", "scripts", "db")
_TABLE = "pilot_credential"
_WRITER = Path("python/smartmatch_persistence/smartmatch_persistence/login_accounts.py")

_SQL_BY_VERB: dict[str, re.Pattern[str]] = {
    "insert": re.compile(rf"(?i)\binsert\s+into\s+{_TABLE}\b"),
    "update": re.compile(rf"(?i)\bupdate\s+{_TABLE}\b"),
    "delete": re.compile(rf"(?i)\bdelete\s+from\s+{_TABLE}\b"),
}
_ADDRESS_LOCK = "pg_advisory_xact_lock"
_ADDRESS_WORDS = re.compile(r"(?i)email|address")


def _callee_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _names_the_table(node: ast.expr) -> bool:
    return (isinstance(node, ast.Name) and node.id == _TABLE) or (
        isinstance(node, ast.Attribute) and node.attr == _TABLE
    )


def _verb_matches(name: str | None, verb: str) -> bool:
    return name is not None and (name == verb or name.endswith(f"_{verb}"))


def python_hits(source: str, verb: str) -> list[int]:
    """Line numbers where ``source`` writes ``pilot_credential`` with ``verb``."""
    hits: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            name = _callee_name(node.func)
            if not _verb_matches(name, verb):
                continue
            # insert(pilot_credential), sa.insert(schema.pilot_credential), pg_insert(...),
            # or schema.pilot_credential.insert().
            first_argument = bool(node.args) and _names_the_table(node.args[0])
            receiver = isinstance(node.func, ast.Attribute) and _names_the_table(node.func.value)
            if first_argument or receiver:
                hits.append(node.lineno)
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and _SQL_BY_VERB[verb].search(node.value)
        ):
            hits.append(node.lineno)
    return hits


def text_hits(source: str, verb: str) -> list[int]:
    """Line numbers where shell or SQL text writes ``pilot_credential`` with ``verb``."""
    pattern = _SQL_BY_VERB[verb]
    return [number for number, line in enumerate(source.splitlines(), 1) if pattern.search(line)]


def address_lock_hits(source: str) -> list[int]:
    """Calls whose source spells an advisory transaction lock over an email or address."""
    hits: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        segment = ast.get_source_segment(source, node) or ""
        if _ADDRESS_LOCK in segment and _ADDRESS_WORDS.search(segment):
            hits.append(node.lineno)
    return sorted(set(hits))


def _files(*suffixes: str) -> Iterator[Path]:
    for top in _SCANNED:
        for path in sorted((_ROOT / top).rglob("*")):
            if (
                path.suffix in suffixes
                and path.is_file()
                and "node_modules" not in path.parts
                and "__pycache__" not in path.parts
            ):
                yield path


def _offenders(verbs: tuple[str, ...]) -> list[str]:
    found: list[str] = []
    for path in _files(".py"):
        relative = path.relative_to(_ROOT)
        if relative == _WRITER:
            continue
        source = path.read_text(encoding="utf-8")
        for verb in verbs:
            found.extend(f"{relative}:{line} ({verb})" for line in python_hits(source, verb))
    for path in _files(".sh", ".sql"):
        source = path.read_text(encoding="utf-8", errors="replace")
        for verb in verbs:
            found.extend(
                f"{path.relative_to(_ROOT)}:{line} ({verb})" for line in text_hits(source, verb)
            )
    return found


def test_the_writer_exists_and_does_write() -> None:
    """The allow-listed file is real, and really holds the three verbs."""
    source = (_ROOT / _WRITER).read_text(encoding="utf-8")
    for verb in ("insert", "update", "delete"):
        assert python_hits(source, verb), f"login_accounts.py no longer spells a {verb}"


def test_only_login_accounts_inserts_pilot_credential() -> None:
    assert _offenders(("insert",)) == [], (
        "every pilot_credential insert must go through "
        "smartmatch_persistence.login_accounts.find_or_add_role (R-G)"
    )


def test_only_login_accounts_updates_or_deletes_pilot_credential() -> None:
    assert _offenders(("update", "delete")) == [], (
        "every pilot_credential update or delete must go through "
        "smartmatch_persistence.login_accounts (rotate_own_password, retire_login)"
    )


def test_no_module_calls_a_credential_upsert() -> None:
    from smartmatch_persistence.pilot_auth import PilotCredentialRepository

    assert not hasattr(PilotCredentialRepository, "upsert")
    offenders = [
        str(path.relative_to(_ROOT))
        for path in _files(".py")
        if "PilotCredentialRepository" in (text := path.read_text(encoding="utf-8"))
        and ".upsert(" in text
    ]
    assert offenders == []


_PLANTED_HITS = {
    "sa_insert": "import sqlalchemy as sa\nsa.insert(schema.pilot_credential).values(id=1)\n",
    "pg_insert": (
        "from sqlalchemy.dialects.postgresql import insert as pg_insert\n"
        "pg_insert(schema.pilot_credential).values(id=1)\n"
    ),
    "imported_name": (
        "from smartmatch_persistence.schema import pilot_credential\n"
        "from sqlalchemy import insert\ninsert(pilot_credential)\n"
    ),
    "f_string": 'table = "x"\nsql = f"INSERT INTO pilot_credential (id) VALUES ({table})"\n',
    "table_method": "schema.pilot_credential.insert().values(id=1)\n",
}
_PLANTED_SHELL = "psql <<'SQL'\ninsert   into PILOT_CREDENTIAL (id) values (1);\nSQL\n"
_PLANTED_CLEAN = {
    "select": "sa.select(schema.pilot_credential.c.id)\n",
    "other_table": "sa.insert(schema.pilot_session).values(id=1)\n",
}


@pytest.mark.parametrize("name", sorted(_PLANTED_HITS))
def test_the_guard_catches_each_shape(name: str) -> None:
    assert python_hits(_PLANTED_HITS[name], "insert"), name


def test_the_guard_catches_shell_and_update_delete_shapes() -> None:
    assert text_hits(_PLANTED_SHELL, "insert") == [2]
    assert python_hits("sa.update(schema.pilot_credential)\n", "update") == [1]
    assert python_hits("sa.delete(pilot_credential)\n", "delete") == [1]
    assert python_hits('q = "DELETE FROM pilot_credential WHERE x"\n', "delete") == [1]
    assert python_hits('q = "UPDATE pilot_credential SET x = 1"\n', "update") == [1]


@pytest.mark.parametrize("name", sorted(_PLANTED_CLEAN))
def test_the_guard_passes_clean_shapes(name: str) -> None:
    for verb in ("insert", "update", "delete"):
        assert python_hits(_PLANTED_CLEAN[name], verb) == [], name


def test_only_login_accounts_takes_an_address_lock() -> None:
    offenders = [
        f"{path.relative_to(_ROOT)}:{line}"
        for path in _files(".py")
        if path.relative_to(_ROOT) != _WRITER
        for line in address_lock_hits(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], "lock an address only through login_accounts.lock_address"
    assert address_lock_hits(
        'session.execute(sa.text("SELECT pg_advisory_xact_lock(hashtext(:email))"))\n'
    ) == [1]
    assert address_lock_hits("session.execute(sa.func.pg_advisory_xact_lock(KEY))\n") == []
