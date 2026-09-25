"""Source contract for the load band on the frontend (B26 T8d plan §9.5, F1-F4).

The load band is a word, never a number (OQ-CBA-005). The run read's wire
carries no hours, capacity or utilization (owner ruling R-A: they stay in the
stored run payload for audit), but a candidate's block still carries the
multiplier and the composite before load, so the rule is held where a screen
could break it:

- F1: the TypeScript types for a load declare no ``number``, so no page can
  render one without editing the type first;
- F2: the shared copy module and the load components read no numeric field;
- F3: "Full (no override available)" is spelled once, in ``loadBandCopy.ts``
  (it contains "available", which the availability surfaces forbid);
- F4: every surface takes its words from the shared copy and spells no band
  word itself.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src"

API_LIB = FRONTEND_SRC / "lib" / "api.ts"
LOAD_COPY = FRONTEND_SRC / "lib" / "loadBandCopy.ts"
LOAD_COMPONENTS = FRONTEND_SRC / "app" / "components" / "load"
PAGES = FRONTEND_SRC / "app" / "pages"

#: The four surfaces that show a band (plan §6.2).
SURFACES = (
    PAGES / "AIMatching.tsx",
    PAGES / "coordinator" / "CoordinatorInvitations.tsx",
    PAGES / "coordinator" / "SpeakerAvailabilityPanel.tsx",
    PAGES / "speaker" / "SpeakerOwnAvailability.tsx",
)

LOAD_TYPES = ("MatchLoad", "SpeakerLoad", "EngagementWithoutEndTime")

NUMERIC_FIELDS = (
    "utilization",
    "completed_hours",
    "confirmed_hours",
    "capacity_hours",
    "multiplier",
    "composite_before_load",
    "toFixed",
    "%",
)

FULL_RUN_LABEL = '"Full (no override available)"'

#: Band words a surface must take from ``loadBandCopy.ts`` rather than spell.
BAND_WORD_LITERALS = (
    re.compile(r"\bLight\b"),
    re.compile(r"\bModerate\b"),
    re.compile(r"\bHeavy\b"),
    re.compile(r"Load not measurable"),
    re.compile(r"[\"'>]Full\b"),
)


def _code_only(source: str) -> str:
    """Strip JSDoc blocks and line comments before scanning.

    The ``test_frontend_invitation_compose_contract.py`` helper, for the same
    reason: these files explain the rules they obey, and a raw scan would fail
    on a file's own account of why it passes.
    """
    without_blocks = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return "\n".join(
        line for line in without_blocks.splitlines() if not line.lstrip().startswith("//")
    )


def _interface_body(source: str, name: str) -> str:
    match = re.search(rf"export interface {name} \{{(.*?)\n?\}}", source, flags=re.DOTALL)
    assert match is not None, f"lib/api.ts declares no `export interface {name}`"
    return match.group(1)


def _load_sources() -> list[Path]:
    assert LOAD_COPY.is_file(), "lib/loadBandCopy.ts is missing"
    components = sorted(path for path in LOAD_COMPONENTS.glob("*.tsx") if ".test." not in path.name)
    names = {path.name for path in components}
    assert {"LoadBandSummary.tsx", "RunLoadLine.tsx"} <= names, (
        f"components/load/ lacks a load component: {sorted(names)}"
    )
    return [LOAD_COPY, *components]


def test_match_load_and_speaker_load_types_declare_no_number() -> None:
    """F1: a load type with no ``number`` in it cannot carry a number to a screen."""
    source = _code_only(API_LIB.read_text(encoding="utf-8"))
    for name in LOAD_TYPES:
        body = _interface_body(source, name)
        assert "number" not in body, f"{name} declares a number: {body!r}"
    match_load = _interface_body(source, "MatchLoad")
    fields = re.findall(r"^\s*(\w+)\??:", match_load, flags=re.MULTILINE)
    inline = re.findall(r"(\w+)\??:", match_load)
    assert set(fields or inline) == {"band", "reason"}, (
        f"MatchLoad declares only band and reason, not {sorted(set(fields or inline))}"
    )


def test_load_files_read_no_numeric_field() -> None:
    """F2: the copy module and the load components never touch a number."""
    for path in _load_sources():
        source = _code_only(path.read_text(encoding="utf-8"))
        for pattern in NUMERIC_FIELDS:
            assert pattern not in source, f"{path.name} reads a numeric field: {pattern!r}"


def test_the_full_run_label_is_defined_once() -> None:
    """F3: the one label with "available" in it lives only in the copy module."""
    holders = sorted(
        str(path.relative_to(FRONTEND_SRC))
        for path in FRONTEND_SRC.rglob("*")
        if path.is_file()
        and path.suffix in {".ts", ".tsx"}
        and ".test." not in path.name
        and FULL_RUN_LABEL in path.read_text(encoding="utf-8")
    )
    assert holders == ["lib/loadBandCopy.ts"], f"the Full run label is spelled in {holders}"
    assert LOAD_COPY.read_text(encoding="utf-8").count(FULL_RUN_LABEL) == 1


def test_every_surface_uses_the_shared_copy() -> None:
    """F4: each surface imports the shared copy or components and spells no band word."""
    for path in SURFACES:
        raw = path.read_text(encoding="utf-8")
        assert re.search(r'from "[^"]*(lib/loadBandCopy|components/load/)', raw), (
            f"{path.name} does not import from loadBandCopy or components/load/"
        )
        source = _code_only(raw)
        for literal in BAND_WORD_LITERALS:
            assert literal.search(source) is None, (
                f"{path.name} spells a band word itself: {literal.pattern!r}"
            )
