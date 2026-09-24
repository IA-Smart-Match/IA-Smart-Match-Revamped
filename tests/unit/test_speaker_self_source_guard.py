"""Source guards over ``routers/speaker_self.py`` (B26 T6b-2 plan §7.5).

AST, not grep: each rule is about calls and keyword values, and a comment or a
docstring naming a forbidden helper must not trip it.
"""

from __future__ import annotations

import ast
from pathlib import Path

SOURCE = (
    Path(__file__).resolve().parents[2]
    / "services"
    / "api"
    / "smartmatch_api"
    / "routers"
    / "speaker_self.py"
)

#: The module-level repositories a handler may read or write through.
_REPOSITORIES = {"_portal", "_invites", "_availability", "_pipeline"}

#: Where ``principal.user_id`` may appear, and only as these keyword values.
_USER_ID_KEYWORDS = {"actor_user_id", "recorded_by_user_id", "account_user_id"}


def _tree() -> ast.Module:
    return ast.parse(SOURCE.read_text(encoding="utf-8"))


def _handlers() -> list[ast.FunctionDef]:
    """Every function decorated with ``@router.<method>``."""
    found = []
    for node in _tree().body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            if (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and isinstance(decorator.func.value, ast.Name)
                and decorator.func.value.id == "router"
            ):
                found.append(node)
    return found


def _names(tree: ast.AST) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


def _is_principal_user_id(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "user_id"
        and isinstance(node.value, ast.Name)
        and node.value.id == "principal"
    )


def test_there_are_five_handlers() -> None:
    assert len(_handlers()) == 5


def test_availability_goes_through_t3s_helper_only() -> None:
    tree = _tree()
    names = _names(tree)
    assert "validate_availability_statement" not in names
    assert "upsert" not in names
    assert "write_statement" in names
    source = ast.unparse(tree)
    assert "AvailabilitySource.CONNECTOR" not in source
    assert "AvailabilitySource.SPEAKER" in source


def test_every_handler_calls_the_authorizer_before_any_repository() -> None:
    for handler in _handlers():
        calls = [node for node in ast.walk(handler) if isinstance(node, ast.Call)]
        calls.sort(key=lambda node: (node.lineno, node.col_offset))
        authorizer_line = None
        for call in calls:
            func = call.func
            if isinstance(func, ast.Name) and func.id == "_authorize_speaker_self":
                authorizer_line = call.lineno
                break
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id in _REPOSITORIES
            ):
                raise AssertionError(f"{handler.name} reads a repository before authorizing")
        assert authorizer_line is not None, f"{handler.name} never calls _authorize_speaker_self"


def test_no_handler_reads_principal_user_id_as_a_row_key() -> None:
    tree = _tree()
    allowed: set[int] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.keyword)
            and node.arg in _USER_ID_KEYWORDS
            and _is_principal_user_id(node.value)
        ):
            allowed.add(id(node.value))
    offenders = [
        node.lineno
        for node in ast.walk(tree)
        if _is_principal_user_id(node) and id(node) not in allowed
    ]
    assert offenders == [], f"principal.user_id used outside the allowlist at lines {offenders}"

    # ``account_user_id=`` only inside the authorizer's lookup.
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name != "_authorize_speaker_self":
            for child in ast.walk(node):
                if isinstance(child, ast.keyword) and child.arg == "account_user_id":
                    raise AssertionError(f"{node.name} looks a profile up by login")


def test_repository_calls_key_rows_by_the_bound_profile() -> None:
    for handler in _handlers():
        for node in ast.walk(handler):
            if isinstance(node, ast.keyword) and node.arg == "professional_id":
                assert ast.unparse(node.value) == "bound.professional_id", (
                    handler.name,
                    ast.unparse(node.value),
                )


def test_the_token_helper_is_not_used() -> None:
    assert "answer_by_token" not in _names(_tree())
