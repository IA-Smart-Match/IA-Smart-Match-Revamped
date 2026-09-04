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

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src"

STUDENT_CONNECT = FRONTEND_SRC / "app" / "pages" / "student" / "StudentConnect.tsx"
AGENTIC_OUTREACH_PANEL = FRONTEND_SRC / "components" / "AgenticOutreachPanel.tsx"
OUTREACH_PAGE = FRONTEND_SRC / "app" / "pages" / "Outreach.tsx"
COORDINATOR_OUTREACH = FRONTEND_SRC / "app" / "pages" / "coordinator" / "CoordinatorOutreach.tsx"
OUTREACH_HOOK = FRONTEND_SRC / "app" / "hooks" / "useOutreach.ts"

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


# B17 -- the coordinator Send button. The legacy version called
# `console.log("Message sent:")`, rendered "Message sent!" for two seconds, and
# closed the dialog, having issued no request at all.
#
# R4 gave it a real command to submit, which is why these two guards exist now
# and did not before: a button with a working `fetch` behind it is *more*
# tempting to decorate with a success toast, not less, because the request
# really did succeed. What it succeeded at is recording a command. The message
# has not been sent, and the page must not say it has.
COORDINATOR_OUTREACH_FORBIDDEN = (
    "Message sent",
    "console.log",
    "setTimeout",
    # Every past tense that would be a claim about a message rather than about
    # the command. "Queued" is the strongest thing this page may say on its own.
    "Sent!",
    "Delivered",
    "successfully",
)


def _code_only(source: str) -> str:
    """Strip JSDoc blocks and line comments before scanning.

    The other guards in this file scan raw source, and that works because the
    files they guard do not discuss the patterns they forbid. This one does:
    `CoordinatorOutreach.tsx` quotes the legacy `console.log("Message sent:")`
    at the top, in order to say what it no longer does. A raw scan would fail on
    a file's own explanation of why it passes, which trains the next person to
    delete the comment rather than keep the guard.

    So prose is removed and code is checked. That is the same call
    `test_outreach_wiring.py` makes for the domain modules, which parse their
    source with `ast` for the identical reason.
    """
    without_blocks = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return "\n".join(
        line for line in without_blocks.splitlines() if not line.lstrip().startswith("//")
    )


def test_coordinator_outreach_never_claims_a_message_was_sent() -> None:
    """B17. The Send button submits a command; it does not report a delivery."""
    source = _code_only(COORDINATOR_OUTREACH.read_text(encoding="utf-8"))
    for pattern in COORDINATOR_OUTREACH_FORBIDDEN:
        assert pattern not in source, (
            f"CoordinatorOutreach reintroduced a fabricated success: {pattern!r}"
        )


def test_coordinator_outreach_reports_the_queued_state_it_actually_has() -> None:
    """The positive half of the guard above.

    Forbidding the word "sent" is only half a contract -- a page that said
    nothing at all would pass it and leave a coordinator with no idea whether
    their click did anything. What the page owes them is the true fact: the
    command was accepted, and here is the job it became.
    """
    source = COORDINATOR_OUTREACH.read_text(encoding="utf-8")

    assert "Queued" in source
    assert "queued.jobId" in source


def test_the_outreach_hook_has_no_state_that_means_delivered() -> None:
    """The state machine is where a fake success would have to be born.

    `SendState` stops at "queued" on purpose. If a "sent" or "delivered" member
    ever appears here, every consumer gains a state it can render, and the page
    guard above becomes a rule about one file rather than about the feature.
    """
    source = _code_only(OUTREACH_HOOK.read_text(encoding="utf-8"))

    assert '"idle" | "submitting" | "queued" | "failed"' in source
    for forbidden in ('| "sent"', '| "delivered"', '| "success"'):
        assert forbidden not in source, (
            f"useOutreach gained a state that claims delivery: {forbidden!r}"
        )
