"""Source guards for B26's top risk: a send path that ignores ``lifted_at`` (T6b-3 plan §8).

Every read of ``suppression_record`` goes through
``smartmatch_persistence.suppression`` (``active_suppression_exists`` and
``SuppressionRepository``), which is the one place that knows "active" means
``lifted_at IS NULL``. These AST checks over ``python/``, ``services/`` and
``tools/`` (not tests, not migrations) keep it that way:

1. Only the suppression module (and the schema mirror) touches the table.
2. Only the suppression module writes ``lifted_at``.
3. Every caller of an eligibility read is a known consumer with a lifted_at
   contract test (``tests/contract/test_suppression_lift_send_paths.py``).
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCANNED = ("python", "services", "tools")

SUPPRESSION_MODULE = "python/smartmatch_persistence/smartmatch_persistence/suppression.py"
SCHEMA_MODULE = "python/smartmatch_persistence/smartmatch_persistence/schema.py"
ALLOWED_TABLE_MODULES = frozenset({SUPPRESSION_MODULE, SCHEMA_MODULE})


#: Methods whose result carries a suppression flag or is one.
_UNIQUE_ELIGIBILITY_METHODS = frozenset({"load_recipient", "is_suppressed", "list_for_speaker"})
_CONTACT_REPOSITORY_METHODS = frozenset({"get", "list_for_unit", "list_for_professional"})
#: ``lock_for_address`` and ``states_for_addresses`` return lifted rows too; a
#: caller must read ``.active``, so every caller is tracked.
_SUPPRESSION_REPOSITORY_METHODS = frozenset(
    {"is_active", "lock_for_address", "states_for_addresses"}
)

#: (file, enclosing function) -> the ``SEND_PATHS`` id whose lifted_at contract
#: test covers it. A new caller fails ``test_every_eligibility_consumer_is_known``
#: until it is listed here **and** its id has a ``SEND_PATHS`` entry in
#: ``tests/contract/test_suppression_lift_send_paths.py``
#: (``test_every_known_consumer_has_a_send_path``).
_OUTREACH = "services/api/smartmatch_api/routers/outreach.py"
_CBA_CHANNELS = "services/api/smartmatch_api/routers/cba_contact_channels.py"
_CONTACTS = "services/api/smartmatch_api/routers/outreach_contacts.py"
_SELF = "services/api/smartmatch_api/speaker_channel_consent.py"
KNOWN_ELIGIBILITY_CONSUMERS: dict[tuple[str, str], str] = {
    # R3 delegates to SuppressionRepository.is_active; its callers are C7.
    (
        "python/smartmatch_persistence/smartmatch_persistence/outreach.py",
        "OutreachRepository.is_suppressed",
    ): "C7",
    # R1 read-back after a transition (C8 and the generic route, C9).
    (
        "python/smartmatch_persistence/smartmatch_persistence/contacts.py",
        "ContactChannelRepository.apply_transition",
    ): "C8",
    (_CBA_CHANNELS, "list_speaker_contact_channels"): "C6",
    (_CBA_CHANNELS, "register_speaker_contact_channel"): "C7",
    (_CBA_CHANNELS, "_load_channel_or_404"): "C8",
    ("services/api/smartmatch_api/routers/cba_invitations.py", "_compose_one"): "C4",
    ("services/api/smartmatch_api/routers/cba_invitations.py", "dispatch_invitation_batch"): "C5",
    (_OUTREACH, "create_draft"): "C2",
    # Reads the address only (plan §5.1 "not a send-eligibility read").
    (_OUTREACH, "_address_for"): "C3",
    (_OUTREACH, "send_draft"): "C3",
    (_CONTACTS, "list_contacts"): "C9",
    (_CONTACTS, "_load_or_404"): "C9",
    (_CONTACTS, "register_contact"): "C9",
    (_CONTACTS, "update_contact"): "C9",
    (_SELF, "_facts"): "C11",
    (_SELF, "list_channels"): "C11",
    (_SELF, "read_channel"): "C11",
    (_SELF, "_locked_channel"): "C11",
    ("services/api/smartmatch_api/routers/speaker_portal.py", "invite_to_portal"): "C10",
    (
        "services/worker/smartmatch_worker/outreach.py",
        "build_outreach_send_handler.handle_outreach_send",
    ): "C1",
}
SEND_PATHS_FILE = ROOT / "tests" / "contract" / "test_suppression_lift_send_paths.py"


def _source_files() -> Iterator[tuple[str, ast.Module]]:
    for top in SCANNED:
        for path in sorted((ROOT / top).rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            parts = set(rel.split("/"))
            if "tests" in parts or "migrations" in parts or ".venv" in parts:
                continue
            if "node_modules" in parts or "worktrees" in parts:
                continue
            yield rel, ast.parse(path.read_text(encoding="utf-8"), filename=rel)


def _docstring_ids(tree: ast.Module) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ids.add(id(body[0].value))
    return ids


def _string_literals(tree: ast.Module) -> Iterator[ast.Constant]:
    docstrings = _docstring_ids(tree)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            yield node


# ---------------------------------------------------------------------------
# 1. One module touches the table
# ---------------------------------------------------------------------------


_TABLE = "suppression_record"
_LIFT_COLUMNS = frozenset({"lifted_at", "lifted_by_user_id"})


def _table_offenders(rel: str, tree: ast.Module) -> list[str]:
    """Every way a module can name the table, outside a docstring.

    Attribute (``schema.suppression_record``), bare name or import
    (``from ...schema import suppression_record``), and any string literal that
    contains the name (raw SQL in any case, f-string parts, ``sa.table("...")``,
    ``METADATA.tables["..."]``). Comments are not in the AST.
    """
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == _TABLE:
            found.append(f"{rel}:{node.lineno} .{_TABLE}")
        elif isinstance(node, ast.Name) and node.id == _TABLE:
            found.append(f"{rel}:{node.lineno} name {_TABLE}")
        elif isinstance(node, ast.alias) and _TABLE in (node.name, node.asname):
            found.append(f"{rel}:{getattr(node, 'lineno', 0)} import {_TABLE}")
    for const in _string_literals(tree):
        if _TABLE in str(const.value).lower():
            found.append(f"{rel}:{const.lineno} string naming {_TABLE}")
    return found


def _lift_writer_offenders(rel: str, tree: ast.Module) -> list[str]:
    """Every way a module can name a lift column, outside a docstring.

    ``.c.lifted_at``, a ``lifted_at=`` keyword to ``.values(...)``, and any
    string literal containing a lift column (dict keys, ``c["lifted_at"]``, raw
    SQL in any case).
    """
    found: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr in _LIFT_COLUMNS
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "c"
        ):
            found.append(f"{rel}:{node.lineno} .c.{node.attr}")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "values"
        ):
            found.extend(
                f"{rel}:{node.lineno} .values({kw.arg}=...)"
                for kw in node.keywords
                if kw.arg in _LIFT_COLUMNS
            )
    for const in _string_literals(tree):
        text = str(const.value).lower()
        if any(column in text for column in _LIFT_COLUMNS):
            found.append(f"{rel}:{const.lineno} string naming a lift column")
    return found


def test_only_the_suppression_module_touches_the_table() -> None:
    offenders = [
        hit
        for rel, tree in _source_files()
        if rel not in ALLOWED_TABLE_MODULES
        for hit in _table_offenders(rel, tree)
    ]
    assert not offenders, (
        "Read suppression_record only through smartmatch_persistence.suppression "
        "(active_suppression_exists / SuppressionRepository):\n" + "\n".join(offenders)
    )


_TABLE_PROBES = (
    'Q = "SELECT 1 FROM suppression_record WHERE address = :a"',
    'Q = "select 1 from suppression_record where address = :a"',
    'Q = f"SELECT 1 FROM {x}suppression_record"',
    "from smartmatch_persistence.schema import suppression_record",
    "from smartmatch_persistence.schema import suppression_record as s",
    'T = METADATA.tables["suppression_record"]',
    'T = sa.table("suppression_record", sa.column("address"))',
    "T = schema.suppression_record",
    # The module's private table alias, imported instead of the table itself.
    "from smartmatch_persistence.suppression import _TABLE as S",
    "from .suppression import _TABLE",
)


def test_the_guard_catches_a_raw_reader() -> None:
    """Every probe trips guard 1; prose in a docstring does not."""
    for probe in _TABLE_PROBES:
        assert _table_offenders("probe.py", ast.parse(probe)), probe
    prose = ast.parse(
        '"""a join against ``suppression_record``"""\n'
        "def f() -> None:\n"
        '    """computed from suppression_record at read time"""\n'
    )
    assert _table_offenders("probe.py", prose) == []


# ---------------------------------------------------------------------------
# 2. One module writes lifted_at
# ---------------------------------------------------------------------------


def test_lifted_at_is_written_only_by_the_suppression_module() -> None:
    offenders = [
        hit
        for rel, tree in _source_files()
        if rel not in ALLOWED_TABLE_MODULES
        for hit in _lift_writer_offenders(rel, tree)
    ]
    assert not offenders, "lifted_at is written only by SuppressionRepository:\n" + "\n".join(
        offenders
    )


_LIFT_PROBES = (
    "q = sa.update(t).values(lifted_at=now)",
    'q = sa.update(t).values({"lifted_at": now})',
    'q = sa.update(t).values({t.c["lifted_by_user_id"]: u})',
    "w = t.c.lifted_at.is_(None)",
    'Q = "update x set lifted_at = now()"',
    'Q = "UPDATE x SET lifted_by_user_id = :u"',
    "vals = dict(lifted_at=now)\nq = sa.update(t).values(**vals)",
    "w = t.columns.lifted_at.is_(None)",
)


def test_the_speakers_lift_call_is_not_a_writer() -> None:
    """``lift(lifted_by_user_id=...)`` is the one sanctioned way to lift."""
    call = "repo.lift(s, tenant_id=t, address=a, allowed_sources=x, lifted_by_user_id=u)"
    assert _lift_writer_offenders("probe.py", ast.parse(call)) == []


def test_the_guard_catches_a_raw_lift_writer() -> None:
    for probe in _LIFT_PROBES:
        assert _lift_writer_offenders("probe.py", ast.parse(probe)), probe


# ---------------------------------------------------------------------------
# 3. Every eligibility consumer is known
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Call:
    file: str
    function: str
    method: str
    line: int


def _bound_names(tree: ast.Module, classes: frozenset[str]) -> set[str]:
    """Names assigned an instance of, or annotated as, one of ``classes``."""

    def mentions(node: ast.AST | None) -> bool:
        if node is None:
            return False
        return any(
            (isinstance(n, ast.Name) and n.id in classes)
            or (isinstance(n, ast.Attribute) and n.attr in classes)
            for n in ast.walk(node)
        )

    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and mentions(node.value):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if mentions(node.annotation) or mentions(node.value):
                names.add(node.target.id)
        elif isinstance(node, ast.arg) and mentions(node.annotation):
            names.add(node.arg)
    return names


@dataclass(frozen=True)
class _Bindings:
    file: str
    contact_names: frozenset[str]
    suppression_names: frozenset[str]


def _is_eligibility_call(call: ast.Call, bindings: _Bindings, klass: str | None) -> bool:
    if not isinstance(call.func, ast.Attribute):
        return False
    method = call.func.attr
    receiver = call.func.value
    name = receiver.id if isinstance(receiver, ast.Name) else None
    if method in _UNIQUE_ELIGIBILITY_METHODS:
        return True
    if method in _CONTACT_REPOSITORY_METHODS:
        return (
            name in bindings.contact_names
            or (name == "self" and klass == "ContactChannelRepository")
            or (method == "get" and any(kw.arg == "contact_channel_id" for kw in call.keywords))
        )
    if method in _SUPPRESSION_REPOSITORY_METHODS:
        return name in bindings.suppression_names
    return False


def _visit(
    node: ast.AST, bindings: _Bindings, scope: tuple[str, ...], klass: str | None
) -> Iterator[_Call]:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.ClassDef):
            yield from _visit(child, bindings, (*scope, child.name), child.name)
            continue
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
            yield from _visit(child, bindings, (*scope, child.name), klass)
            continue
        if isinstance(child, ast.Call) and _is_eligibility_call(child, bindings, klass):
            assert isinstance(child.func, ast.Attribute)
            yield _Call(bindings.file, ".".join(scope) or "<module>", child.func.attr, child.lineno)
        yield from _visit(child, bindings, scope, klass)


def _eligibility_calls() -> Iterator[_Call]:
    for rel, tree in _source_files():
        bindings = _Bindings(
            file=rel,
            contact_names=frozenset(_bound_names(tree, frozenset({"ContactChannelRepository"}))),
            suppression_names=frozenset(_bound_names(tree, frozenset({"SuppressionRepository"}))),
        )
        yield from _visit(tree, bindings, (), None)


def test_every_eligibility_consumer_is_known() -> None:
    calls = list(_eligibility_calls())
    # The repositories' own delegation inside the suppression-aware modules is
    # not a consumer.
    found = {
        (c.file, c.function)
        for c in calls
        if not (c.file == SUPPRESSION_MODULE and c.function.startswith("SuppressionRepository."))
    }
    unknown = sorted(found - set(KNOWN_ELIGIBILITY_CONSUMERS))
    stale = sorted(set(KNOWN_ELIGIBILITY_CONSUMERS) - found)
    assert not unknown, (
        "New eligibility read(s). List each in KNOWN_ELIGIBILITY_CONSUMERS and give it a "
        "lifted_at contract test in SEND_PATHS:\n"
        + "\n".join(
            f"{c.file}:{c.line} {c.function} -> .{c.method}()"
            for c in calls
            if (c.file, c.function) in set(unknown)
        )
    )
    assert not stale, f"KNOWN_ELIGIBILITY_CONSUMERS lists callers that no longer read: {stale}"


def _send_path_ids() -> set[str]:
    tree = ast.parse(SEND_PATHS_FILE.read_text(encoding="utf-8"))
    for node in tree.body:
        target = node.target if isinstance(node, ast.AnnAssign) else None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
        if (
            isinstance(target, ast.Name)
            and target.id == "SEND_PATHS"
            and isinstance(node.value, ast.Dict)  # type: ignore[union-attr]
        ):
            return {
                k.value
                for k in node.value.keys  # type: ignore[union-attr]
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            }
    raise AssertionError("SEND_PATHS not found")


@pytest.mark.parametrize(
    "probe",
    [
        "SuppressionRepository().lock_for_address(s, tenant_id=t, address=a)",
        "self._repo.states_for_addresses(s, tenant_id=t, addresses=a)",
    ],
)
def test_a_lock_or_state_read_is_tracked_on_any_receiver(probe: str) -> None:
    """Both names are unique to ``SuppressionRepository``: any receiver counts."""
    bindings = _Bindings(file="probe.py", contact_names=frozenset(), suppression_names=frozenset())
    assert len(list(_visit(ast.parse(probe), bindings, (), None))) == 1


def test_every_known_consumer_has_a_send_path() -> None:
    ids = _send_path_ids()
    missing = {site: cid for site, cid in KNOWN_ELIGIBILITY_CONSUMERS.items() if cid not in ids}
    assert not missing, f"consumers whose SEND_PATHS id has no lifted_at test: {missing}"


# ---------------------------------------------------------------------------
# 4. Every lifecycle move checks the Speaker's choice
# ---------------------------------------------------------------------------

#: Every ``apply_transition`` call site, and the Speaker-wins check it must make.
#: A Connector route: ``connector_transition_conflict``. The Speaker's own
#: opt-in: it *is* the Speaker's choice, and appends to the log.
GUARDED_APPLY_TRANSITION_SITES: dict[tuple[str, str], str] = {
    (
        "services/api/smartmatch_api/routers/cba_contact_channels.py",
        "transition_speaker_contact_channel",
    ): "connector_transition_conflict",
    (
        "services/api/smartmatch_api/routers/outreach_contacts.py",
        "transition_contact",
    ): "connector_transition_conflict",
    # The Speaker's own walk: it *is* the Speaker's choice, so what it must do
    # is re-ask the domain; the channel lock is pinned by the test below.
    (
        "services/api/smartmatch_api/speaker_channel_consent.py",
        "_walk_to_active",
    ): "assert_transition",
}
_SPEAKER_SITES = frozenset(
    {("services/api/smartmatch_api/speaker_channel_consent.py", "_walk_to_active")}
)


def _functions(tree: ast.Module) -> Iterator[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    def walk(node: ast.AST, scope: tuple[str, ...]) -> Iterator[tuple[str, Any]]:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                yield from walk(child, (*scope, child.name))
            elif isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                name = (*scope, child.name)
                yield ".".join(name), child
                yield from walk(child, name)

    yield from walk(tree, ())


def _called_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            if isinstance(sub.func, ast.Attribute):
                names.add(sub.func.attr)
            elif isinstance(sub.func, ast.Name):
                names.add(sub.func.id)
    return names


def test_apply_transition_call_sites_are_guarded() -> None:
    sites: dict[tuple[str, str], set[str]] = {}
    for rel, tree in _source_files():
        # One level through this module's own helpers (e.g. a loader that locks).
        local = {
            node.name: _called_names(node)
            for node in tree.body
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        }
        for qualname, fn in _functions(tree):
            direct = {
                sub
                for sub in ast.walk(fn)
                if isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Attribute)
                and sub.func.attr == "apply_transition"
            }
            nested = {
                sub
                for inner in ast.walk(fn)
                if inner is not fn and isinstance(inner, ast.FunctionDef | ast.AsyncFunctionDef)
                for sub in ast.walk(inner)
            }
            if direct - nested and not qualname.startswith("ContactChannelRepository."):
                called = _called_names(fn)
                for name in list(called):
                    called |= local.get(name, set())
                sites[(rel, qualname)] = called
    assert set(sites) == set(GUARDED_APPLY_TRANSITION_SITES), (
        "apply_transition call sites changed; each must check the Speaker's choice: "
        f"{sorted(set(sites) ^ set(GUARDED_APPLY_TRANSITION_SITES))}"
    )
    for site, required in GUARDED_APPLY_TRANSITION_SITES.items():
        assert required in sites[site], f"{site} moves a channel without {required}()"
        if site not in _SPEAKER_SITES:
            assert "lock" in sites[site], f"{site} moves a channel without locking it first"


def test_the_speaker_walk_runs_only_under_the_channel_lock() -> None:
    """``_walk_to_active`` is called only by ``opt_in``, after ``_locked_channel``."""
    rel = "services/api/smartmatch_api/speaker_channel_consent.py"
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    callers = {name for name, fn in _functions(tree) if "_walk_to_active" in _called_names(fn)} - {
        "_walk_to_active"
    }
    assert callers == {"opt_in"}
    opt_in = dict(_functions(tree))["opt_in"]
    order = [
        sub.func.id
        for sub in ast.walk(opt_in)
        if isinstance(sub, ast.Call)
        and isinstance(sub.func, ast.Name)
        and sub.func.id in {"_locked_channel", "_walk_to_active"}
    ]
    assert order == ["_locked_channel", "_walk_to_active"]
    locked = dict(_functions(tree))["_locked_channel"]
    assert "lock" in _called_names(locked)
