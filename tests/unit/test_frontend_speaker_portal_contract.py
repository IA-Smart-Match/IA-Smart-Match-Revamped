"""Source contract for the Speaker Portal pages (B26 T6b-4 §9.3).

The Speaker Portal is the one shell whose every request names no subject: the
server resolves the Speaker from the bearer token (``/v1/me/*``). These scans
hold that, and the boundaries around it, at the level a source scan can reach:

- the file set exists, so a renamed file fails by name instead of letting the
  scans below pass over nothing;
- no Speaker page calls a Connector route (``/v1/units/…``) or a Connector
  adapter, so no page can come to name a unit or a professional;
- the three contact-channel adapters take no subject;
- the portal switcher slot a later track fills (T6b-5) is marked where that
  track will look, and nothing is built early; the load band slot (T8d) is
  filled, by ``LoadBandSummary``, and its marker is gone.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src"

API_LIB = FRONTEND_SRC / "lib" / "api.ts"
LAYOUT = FRONTEND_SRC / "app" / "components" / "SpeakerPortalLayout.tsx"
HOOKS = FRONTEND_SRC / "app" / "hooks" / "useSpeakerSelf.ts"
SPEAKER_PAGES = FRONTEND_SRC / "app" / "pages" / "speaker"
OWN_AVAILABILITY = SPEAKER_PAGES / "SpeakerOwnAvailability.tsx"

#: Exactly the files under ``app/pages/speaker/`` (tests aside).
SPEAKER_PAGE_FILES = frozenset(
    {
        "SpeakerHome.tsx",
        "SpeakerInvitations.tsx",
        "SpeakerEngagements.tsx",
        "SpeakerOwnAvailability.tsx",
        "SpeakerContactPreferences.tsx",
        "InvitationRow.tsx",
        "EngagementRow.tsx",
        "ContactChannelRow.tsx",
        "SpeakerSelfNotice.tsx",
        "speakerPortalErrors.ts",
        "speakerPortalFormat.ts",
        "useSpeakerPageTitle.ts",
    }
)

#: The Connector adapters a Speaker page must never reach for.
CONNECTOR_ADAPTERS = (
    "fetchSpeakerAvailability(",
    "updateSpeakerAvailability(",
    "fetchSpeakerContactChannels(",
    "fetchSpeakerInvitationBatches(",
)

#: The three adapters T6b-4 writes, and the path each one calls.
CONTACT_CHANNEL_ADAPTERS = {
    "fetchMyContactChannels": "`/v1/me/contact-channels`",
    "optInMyContactChannel": "/opt-in`",
    "optOutMyContactChannel": "/opt-out`",
}

SUBJECT_PARAMETERS = ("professionalId", "unitId", "userId")


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


def _speaker_sources() -> list[Path]:
    pages = sorted(
        path
        for path in SPEAKER_PAGES.iterdir()
        if path.is_file() and path.suffix in {".ts", ".tsx"} and ".test." not in path.name
    )
    return [*pages, HOOKS]


def _signature(source: str, name: str) -> str:
    match = re.search(rf"export async function {name}\((.*?)\)", source, flags=re.DOTALL)
    assert match is not None, f"lib/api.ts has no `export async function {name}(`"
    return match.group(1)


def _function_body(source: str, name: str) -> str:
    start = source.index(f"export async function {name}(")
    end = source.find("\nexport ", start + 1)
    return source[start : end if end != -1 else len(source)]


def test_the_speaker_portal_file_set_exists() -> None:
    """Asserted first, so a missing or renamed file fails here by name."""
    assert LAYOUT.is_file(), "app/components/SpeakerPortalLayout.tsx is missing"
    assert HOOKS.is_file(), "app/hooks/useSpeakerSelf.ts is missing"
    present = frozenset(
        path.name
        for path in SPEAKER_PAGES.iterdir()
        if path.is_file() and ".test." not in path.name
    )
    assert present == SPEAKER_PAGE_FILES, (
        f"app/pages/speaker/ holds {sorted(present)}; expected exactly {sorted(SPEAKER_PAGE_FILES)}"
    )


def test_speaker_pages_call_only_me_routes() -> None:
    for path in _speaker_sources():
        code = _code_only(path.read_text(encoding="utf-8"))
        assert "/v1/units/" not in code, f"{path.name} names a Connector route"
        for adapter in CONNECTOR_ADAPTERS:
            assert adapter not in code, f"{path.name} calls the Connector adapter {adapter}"


def test_contact_channel_adapters_take_no_subject() -> None:
    source = _code_only(API_LIB.read_text(encoding="utf-8"))
    for name, path in CONTACT_CHANNEL_ADAPTERS.items():
        signature = _signature(source, name)
        for parameter in SUBJECT_PARAMETERS:
            assert parameter not in signature, f"{name} takes a subject ({parameter})"
        body = _function_body(source, name)
        assert path in body, f"{name} does not call {path}"
        assert "/v1/units/" not in body, f"{name} calls a Connector route"
    assert _signature(source, "fetchMyContactChannels").strip() == ""


def test_the_t6b5_slots_are_marked_and_t8d_filled_its_slot() -> None:
    """Raw source: the slots are comments, which ``_code_only`` would strip."""
    layout = LAYOUT.read_text(encoding="utf-8")
    assert layout.count("SLOT(T6b-5)") == 2, "the layout marks the switcher slot twice"
    identity = layout.index("principalDisplayName(")
    sign_out = layout.index("Sign out", identity)
    sidebar_slot = layout.index("SLOT(T6b-5)")
    assert sidebar_slot < identity, "the sidebar switcher slot sits above the identity block"
    assert "SLOT(T6b-5)" not in layout[identity:sign_out], (
        "nothing may sit between the profile and Sign out (DESIGN.md: sign-out directly "
        "beneath the profile area)"
    )
    assert "SLOT(T6b-5): portal switcher (mobile)" in layout

    availability = OWN_AVAILABILITY.read_text(encoding="utf-8")
    assert "SLOT(T8d)" not in availability, "T8d filled the load band slot; the marker goes"
    assert re.search(
        r'import \{[^}]*\bLoadBandSummary\b[^}]*\} from "[^"]*components/load/LoadBandSummary"',
        availability,
    ), "the availability page imports LoadBandSummary for the Speaker's load band"
    assert "<LoadBandSummary" in _code_only(availability), "LoadBandSummary is rendered"


def test_speaker_portal_reuses_the_t5_form() -> None:
    """One availability form, T5's: the Speaker page wires it, never rebuilds it."""
    source = OWN_AVAILABILITY.read_text(encoding="utf-8")
    assert "components/speakerAvailability/SpeakerAvailabilityForm" in source
    assert "<SpeakerAvailabilityForm" in _code_only(source)
    for path in _speaker_sources():
        assert 'type="date"' not in _code_only(path.read_text(encoding="utf-8")), (
            f"{path.name} renders its own date input; the Speaker's dates are T5's form"
        )


def test_no_optimistic_update_in_the_speaker_portal() -> None:
    """Writes re-read the owning list; the one cache write is the saved row."""
    writes: list[tuple[str, str]] = []
    for path in _speaker_sources():
        code = _code_only(path.read_text(encoding="utf-8"))
        assert "onMutate" not in code, f"{path.name} updates the cache before the server answers"
        writes.extend((path.name, line) for line in code.splitlines() if "setQueryData" in line)
    assert len(writes) == 1, f"expected one setQueryData, found {writes}"
    name, _ = writes[0]
    assert name == "useSpeakerSelf.ts"
    hooks = _code_only(HOOKS.read_text(encoding="utf-8"))
    call = hooks[hooks.index("setQueryData") :].split(";", 1)[0]
    assert "SPEAKER_SELF_RESOURCE.availability" in call, (
        "the one cache write is the saved availability row"
    )


def test_status_regions_wrap_long_addresses_and_titles() -> None:
    """1.4.10 Reflow: a status sentence echoes an address or title, so it wraps at 360 px."""
    found = 0
    for path in sorted(SPEAKER_PAGES.glob("*.tsx")):
        if path.name.endswith(".test.tsx"):
            continue
        code = _code_only(path.read_text(encoding="utf-8"))
        for tag in re.findall(r"<p\b[^>]*role=\"status\"[^>]*>", code):
            found += 1
            assert "break-words" in tag or "break-all" in tag, (
                f"{path.name}: the role=status paragraph does not wrap long words"
            )
    assert found == 2, f"expected the 2 page status regions, found {found}"
