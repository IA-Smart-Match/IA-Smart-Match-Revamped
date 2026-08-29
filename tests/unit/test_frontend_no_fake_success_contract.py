"""Source contract: deleted controls that faked success must not come back.

Guards backlog items B12, B13, B20, B21, B32, B33 and B37 from
``docs/plans/frontend-broken-buttons.md``. Each of these controls advertised an
action no backend can perform, and several reported success unconditionally --
defect class N2 in architecture v1.1 section 3.6. They were removed rather than
wired, because the commands behind them do not exist and are gate-blocked.

A control may only claim an action succeeded after a 2xx from a command that
committed. Re-adding any pattern below reintroduces a fabricated success story.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src"

STUDENT_CONNECT = FRONTEND_SRC / "app" / "pages" / "student" / "StudentConnect.tsx"
AGENTIC_OUTREACH_PANEL = FRONTEND_SRC / "components" / "AgenticOutreachPanel.tsx"
OUTREACH_PAGE = FRONTEND_SRC / "app" / "pages" / "Outreach.tsx"

# B12 / B13 -- in-app chat is archived (MM-F04, Fix #11). The sheet rendered
# fabricated message history and "Send" only cleared the input.
STUDENT_CONNECT_FORBIDDEN = (
    "makeMockThreadMessages",
    "draftMessage",
    "Demo-only: messages are not persisted",
    "inboxThreads",
    "activeThreadId",
)

# B20 / B21 -- "Approve & Send" only set local state; the UI then claimed the
# outreach had been sent and the pipeline updated. Nothing was ever dispatched.
AGENTIC_PANEL_FORBIDDEN = (
    "Outreach sent",
    "Pipeline updated",
    "Speaker contacted successfully",
    "Approve & Send",
    'setPhase("approved")',
    'setPhase("rejected")',
)

# B32 / B33 / B37 -- a Save Draft button with no onClick, an "AI Enhance" that
# appended a hard-coded sentence and passed it off as model output, and a
# Create Template dialog whose input was uncontrolled and stored nothing.
OUTREACH_FORBIDDEN = (
    "handleAIEnhance",
    "AI Enhance",
    "Enhanced note",
    "Save Draft",
    "showNewTemplate",
    "Create Template",
)


def test_student_connect_has_no_mock_chat() -> None:
    source = STUDENT_CONNECT.read_text(encoding="utf-8")
    for pattern in STUDENT_CONNECT_FORBIDDEN:
        assert pattern not in source, (
            f"StudentConnect reintroduced archived in-app chat: {pattern!r}"
        )


def test_agentic_outreach_panel_never_claims_outreach_was_sent() -> None:
    source = AGENTIC_OUTREACH_PANEL.read_text(encoding="utf-8")
    for pattern in AGENTIC_PANEL_FORBIDDEN:
        assert pattern not in source, (
            f"AgenticOutreachPanel reintroduced unconditional success: {pattern!r}"
        )


def test_agentic_outreach_panel_states_no_send_path_exists() -> None:
    source = AGENTIC_OUTREACH_PANEL.read_text(encoding="utf-8")
    assert "No send path exists" in source, (
        "AgenticOutreachPanel must truthfully state that outreach cannot be dispatched"
    )


def test_outreach_page_has_no_stub_controls() -> None:
    source = OUTREACH_PAGE.read_text(encoding="utf-8")
    for pattern in OUTREACH_FORBIDDEN:
        assert pattern not in source, (
            f"Outreach page reintroduced a control with no backend: {pattern!r}"
        )
