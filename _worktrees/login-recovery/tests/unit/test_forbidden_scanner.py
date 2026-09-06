"""Self-tests for the forbidden-behavior scanner.

A gate nobody has verified is worse than no gate: it produces a green check that
means nothing. These tests feed the scanner known-bad source and assert it
fires, and known-good source and assert it stays quiet.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "scan_forbidden", REPO_ROOT / "tools" / "scan_forbidden.py"
)
assert _spec and _spec.loader
scan_forbidden = importlib.util.module_from_spec(_spec)
sys.modules["scan_forbidden"] = scan_forbidden
_spec.loader.exec_module(scan_forbidden)

RULES = {rule.code: rule for rule in scan_forbidden.RULES}


def _fires(code: str, source: str) -> bool:
    """Whether the named rule matches ``source`` after prose stripping."""
    searchable = scan_forbidden.strip_python_prose(source)
    return bool(RULES[code].regex.search(searchable))


# ---------------------------------------------------------------------------
# Each rule catches the legacy pattern it was written for
# ---------------------------------------------------------------------------


def test_catches_mock_login():
    assert _fires("mock-login", '@router.post("/auth/mock-login")\ndef login(): ...')


def test_catches_local_business_persistence():
    assert _fires("local-business-persistence", "df.to_csv(path)")
    assert _fires("local-business-persistence", "conn = sqlite3.connect('demo.db')")


def test_catches_module_level_mutable_state():
    assert _fires("module-level-mutable-state", "_JOB_QUEUE = []")
    assert _fires("module-level-mutable-state", "RESULT_BUS = {}")


def test_catches_demo_mode_fallback():
    assert _fires("demo-mode-fallback", "from src.demo_mode import load_fixture")


def test_catches_hard_coded_credential():
    assert _fires("hard-coded-credential", 'api_key = "re_abcdefghijklmnop123456"')


def test_catches_legacy_imports():
    assert _fires("legacy-import", "from src.matching.engine import rank")


def test_catches_client_supplied_identity():
    assert _fires("client-supplied-identity", 'tenant_id = payload["tenant_id"]')


def test_catches_unconditional_success():
    assert _fires("unconditional-success", 'return {"success": True}')


def test_catches_fabricated_meeting_url():
    assert _fires("fabricated-meeting", 'url = "https://meet.google.com/abc-defg-hij"')


def test_catches_a_genuinely_mutating_get():
    source = '@router.get("/u/{token}")\ndef unsubscribe(token: str):\n    suppress(token)\n'
    assert _fires("mutating-get", source)


# ---------------------------------------------------------------------------
# The corrected patterns do not fire
# ---------------------------------------------------------------------------


def test_render_only_get_handler_is_not_flagged():
    """The corrected unsubscribe design: GET renders, POST mutates."""
    source = (
        '@app.get("/u/{token}")\n'
        "def unsubscribe_page(token: str):\n"
        "    return HTMLResponse('confirm')\n"
    )
    assert not _fires("mutating-get", source)


@pytest.mark.parametrize("suffix", ["page", "form", "confirmation", "view"])
def test_all_render_suffixes_are_exempt(suffix: str):
    source = f'@app.get("/x")\ndef confirm_{suffix}():\n    return 1\n'
    assert not _fires("mutating-get", source)


def test_prose_naming_a_forbidden_pattern_is_not_a_violation():
    """Documentation explaining why a pattern is absent must not fail the gate."""
    source = '"""We archived POST /auth/mock-login — callers never pick roles."""\n'
    assert not _fires("mock-login", source)


def test_comments_are_stripped_too():
    source = "# legacy wrote results with df.to_csv(path)\nx = 1\n"
    assert not _fires("local-business-persistence", source)


def test_ordinary_string_literals_are_still_scanned():
    """Stripping prose must not blind the scanner to real credentials."""
    source = 'CONFIG = {"api_key": "re_abcdefghijklmnop123456"}\n'
    assert _fires("hard-coded-credential", source)


def test_strip_prose_preserves_line_numbers():
    """Reported line numbers must still point at the right source line."""
    source = '"""Doc\nspanning\nlines."""\nOFFENDING = 1\n'
    stripped = scan_forbidden.strip_python_prose(source)
    assert stripped.splitlines()[3] == "OFFENDING = 1"


def test_strip_prose_returns_unparseable_source_unchanged():
    """A syntax error must not silently disable scanning for that file."""
    broken = "def (:\n"
    assert scan_forbidden.strip_python_prose(broken) == broken


# ---------------------------------------------------------------------------
# Allowlist hygiene
# ---------------------------------------------------------------------------


def test_every_allowlist_entry_has_a_reason():
    """An unexplained allowlist entry defeats the gate."""
    for key, reason in scan_forbidden.ALLOWLIST.items():
        assert reason and len(reason) > 20, f"allowlist entry {key} lacks a real reason"


def test_every_allowlist_entry_names_a_real_rule():
    """A typo in a rule code would silently disable nothing, and mislead."""
    for _path, code in scan_forbidden.ALLOWLIST:
        assert code in RULES, f"allowlist references unknown rule {code!r}"


def test_every_exclusion_has_a_reason():
    for prefix, reason in scan_forbidden.EXCLUDED_PREFIXES:
        assert reason, f"exclusion {prefix!r} lacks a reason"


def test_rule_codes_are_unique():
    codes = [rule.code for rule in scan_forbidden.RULES]
    assert len(codes) == len(set(codes))


# ---------------------------------------------------------------------------
# The repository itself is clean
# ---------------------------------------------------------------------------


def test_repository_scan_is_clean():
    """The gate, run against the target as it stands."""
    result = scan_forbidden.scan()
    assert result.files_scanned > 0, "scanner found no files — check tracked_files()"
    assert result.violations == [], "\n".join(
        f"{v.path}:{v.line_number} [{v.rule_code}] {v.excerpt}" for v in result.violations
    )
