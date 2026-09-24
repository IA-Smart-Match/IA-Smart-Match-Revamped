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
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCANNED = ("python", "services", "tools")

SUPPRESSION_MODULE = "python/smartmatch_persistence/smartmatch_persistence/suppression.py"
SCHEMA_MODULE = "python/smartmatch_persistence/smartmatch_persistence/schema.py"
ALLOWED_TABLE_MODULES = frozenset({SUPPRESSION_MODULE, SCHEMA_MODULE})

_SQL_KEYWORDS = re.compile(r"\b(SELECT|FROM|JOIN|INSERT|UPDATE|DELETE)\b")
_SQL_WRITE_KEYWORDS = re.compile(r"\b(INSERT|UPDATE|SET)\b")

#: Methods whose result carries a suppression flag or is one.
_UNIQUE_ELIGIBILITY_METHODS = frozenset({"load_recipient", "is_suppressed", "list_for_speaker"})
_CONTACT_REPOSITORY_METHODS = frozenset({"get", "list_for_unit", "list_for_professional"})
_SUPPRESSION_REPOSITORY_METHODS = frozenset({"is_active"})

#: (file, enclosing function) for every eligibility read. A new caller fails
#: ``test_every_eligibility_consumer_is_known`` until it is listed here **and**
#: has a ``SEND_PATHS`` entry in the send-path contract test.
KNOWN_ELIGIBILITY_CONSUMERS: frozenset[tuple[str, str]] = frozenset(
    {
        # R3 delegates to SuppressionRepository.is_active.
        (
            "python/smartmatch_persistence/smartmatch_persistence/outreach.py",
            "OutreachRepository.is_suppressed",
        ),
        # R1 read-back after a transition.
        (
            "python/smartmatch_persistence/smartmatch_persistence/contacts.py",
            "ContactChannelRepository.apply_transition",
        ),
        # C6 list, C7 register refusal and read-back, C8 transition load.
        (
            "services/api/smartmatch_api/routers/cba_contact_channels.py",
            "list_speaker_contact_channels",
        ),
        (
            "services/api/smartmatch_api/routers/cba_contact_channels.py",
            "register_speaker_contact_channel",
        ),
        ("services/api/smartmatch_api/routers/cba_contact_channels.py", "_load_channel_or_404"),
        # C4 batch creation, C5 dispatch.
        ("services/api/smartmatch_api/routers/cba_invitations.py", "_compose_one"),
        ("services/api/smartmatch_api/routers/cba_invitations.py", "dispatch_invitation_batch"),
        # C2 compose, C3 send; `_address_for` reads the address only.
        ("services/api/smartmatch_api/routers/outreach.py", "create_draft"),
        ("services/api/smartmatch_api/routers/outreach.py", "_address_for"),
        ("services/api/smartmatch_api/routers/outreach.py", "send_draft"),
        # C9 list, read (`_load_or_404`), register and update read-backs.
        ("services/api/smartmatch_api/routers/outreach_contacts.py", "list_contacts"),
        ("services/api/smartmatch_api/routers/outreach_contacts.py", "_load_or_404"),
        ("services/api/smartmatch_api/routers/outreach_contacts.py", "register_contact"),
        ("services/api/smartmatch_api/routers/outreach_contacts.py", "update_contact"),
        # C11 the Speaker's own view and opt-in / opt-out (B26 T6b-3).
        ("services/api/smartmatch_api/speaker_channel_consent.py", "list_channels"),
        ("services/api/smartmatch_api/speaker_channel_consent.py", "read_channel"),
        ("services/api/smartmatch_api/speaker_channel_consent.py", "_locked_channel"),
        # C10 T6b-1 portal invite eligibility.
        ("services/api/smartmatch_api/routers/speaker_portal.py", "invite_to_portal"),
        # C1 the worker's delivery-time re-check.
        (
            "services/worker/smartmatch_worker/outreach.py",
            "build_outreach_send_handler.handle_outreach_send",
        ),
    }
)


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


def test_only_the_suppression_module_touches_the_table() -> None:
    offenders: list[str] = []
    for rel, tree in _source_files():
        if rel in ALLOWED_TABLE_MODULES:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "suppression_record":
                offenders.append(f"{rel}:{node.lineno} schema.suppression_record")
        for const in _string_literals(tree):
            text = str(const.value)
            if "suppression_record" in text and _SQL_KEYWORDS.search(text):
                offenders.append(f"{rel}:{const.lineno} SQL naming suppression_record")
    assert not offenders, (
        "Read suppression_record only through smartmatch_persistence.suppression "
        "(active_suppression_exists / SuppressionRepository):\n" + "\n".join(offenders)
    )


def test_the_guard_catches_a_raw_reader() -> None:
    """The heuristic itself: SQL in a literal trips it, prose in a docstring does not."""
    tree = ast.parse(
        '"""a join against ``suppression_record``"""\n'
        'Q = "SELECT 1 FROM suppression_record WHERE address = :a"\n'
        'P = "computed from suppression_record at read time"\n'
    )
    hits = [
        c.lineno
        for c in _string_literals(tree)
        if "suppression_record" in str(c.value) and _SQL_KEYWORDS.search(str(c.value))
    ]
    assert hits == [2]


# ---------------------------------------------------------------------------
# 2. One module writes lifted_at
# ---------------------------------------------------------------------------


def test_lifted_at_is_written_only_by_the_suppression_module() -> None:
    offenders: list[str] = []
    for rel, tree in _source_files():
        if rel in ALLOWED_TABLE_MODULES:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr in {"lifted_at", "lifted_by_user_id"}
                and isinstance(node.value, ast.Attribute)
                and node.value.attr == "c"
            ):
                offenders.append(f"{rel}:{node.lineno} .c.{node.attr}")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "values"
            ):
                for kw in node.keywords:
                    if kw.arg in {"lifted_at", "lifted_by_user_id"}:
                        offenders.append(f"{rel}:{node.lineno} .values({kw.arg}=...)")
        for const in _string_literals(tree):
            text = str(const.value)
            if "lifted_at" in text and _SQL_WRITE_KEYWORDS.search(text):
                offenders.append(f"{rel}:{const.lineno} SQL writing lifted_at")
    assert not offenders, "lifted_at is written only by SuppressionRepository:\n" + "\n".join(
        offenders
    )


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
    unknown = sorted(found - KNOWN_ELIGIBILITY_CONSUMERS)
    stale = sorted(KNOWN_ELIGIBILITY_CONSUMERS - found)
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
    (
        "services/api/smartmatch_api/speaker_channel_consent.py",
        "opt_in",
    ): "opt_in_path",
}


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
        assert "lock" in sites[site], f"{site} moves a channel without locking it first"
