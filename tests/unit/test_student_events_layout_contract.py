"""Source contract: the student Events page, and the one thing §15 says about it.

Customer §15's "Events page requirement" is a single sentence — *keep the month
calendar at the bottom of the Events page* — and it is the kind of requirement
that survives review and dies in a refactor. Nothing about a month grid moving
above two lists breaks a build, fails a type check, or reads wrong in a diff. So
the placement is asserted here, mechanically, against the source.

## Three properties, and why each is separate

1. **Order.** Browse, then the agenda, then the month calendar — the calendar
   strictly last. Asserted as positions in the file rather than as "the calendar
   exists", because a page that rendered the grid first would pass every other
   test in this repository.
2. **The grid is not a replacement.** ``docs/architecture/engagement-model.md``
   §5 (D-11) argues against a month grid as the primary surface; the customer
   asked for one on the page. The resolution is *both, in an order*, which only
   holds while the two lists are actually there — so their presence is asserted
   beside the ordering rather than assumed by it.
3. **Nothing is fabricated.** ``docs/plans/frontend-broken-buttons.md`` records
   what this page used to be: B07's "Calendar event added" toast that set a flag
   and called nothing, B09's ``MockStudentCalendar`` of inert invented cells, and
   B06's **Register** button that created no registration. The forbidden list
   below is those three defects by name, so re-adding any of them fails here
   rather than in a demo.

## Why a Python test of a TypeScript file

The same reason ``test_frontend_no_fake_success_contract.py`` and
``test_cba_surface_composition.py`` are Python: these are assertions about what
the repository *contains*, they run in the same suite as the API contracts they
correspond to, and they need no browser, no build and no node toolchain to
answer. A reader tracing "who guarantees the calendar stays at the bottom" finds
one file, in the suite that runs on every change.

``tests/unit/test_frontend_auth_contract.py`` also names this page, in its
``PORTAL_PAGES`` list, and asserts something different about it: that its
identity comes from ``/v1/me`` rather than from the browser. That property is
about every portal page; this file is about this one.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src"

STUDENT_EVENTS = FRONTEND_SRC / "app" / "pages" / "student" / "StudentEvents.tsx"
API_CLIENT = FRONTEND_SRC / "lib" / "api.ts"

#: The three sections, by the ``aria-label`` each one carries. Keyed on the
#: accessibility label rather than on heading text: the label is what a
#: screen-reader user navigates by, so it is the identifier least likely to be
#: "improved" in a copy edit and most costly to get wrong.
SECTION_LABELS = (
    'aria-label="Browse events"',
    'aria-label="Your agenda"',
    'aria-label="Month calendar"',
)

#: The three *render sites*, in the order §15 requires, matched inside the page
#: component's own body.
#:
#: The third entry is the ``<MonthCalendar>`` invocation rather than that
#: section's ``aria-label``, and the difference matters: the label lives in the
#: component's definition, which sits **above** the page component in the file
#: the way every helper here does. Ordering the definitions would assert the
#: layout of the source; ordering the invocations asserts the layout of the
#: page, which is what the customer asked about.
RENDER_SITES_IN_ORDER = (
    'aria-label="Browse events"',
    'aria-label="Your agenda"',
    "<MonthCalendar",
)

#: Where the page body starts. Everything before it is helpers and one long
#: explanation of what this page used to be, and that explanation *names* the
#: defects — see :data:`FORBIDDEN_IN_STUDENT_EVENTS`, which is checked against
#: the code rather than the prose for exactly that reason.
PAGE_COMPONENT = "export function StudentEvents()"

#: Patterns whose presence would mean a defect this page was rewritten to remove
#: has come back. Each names the backlog row it belongs to.
FORBIDDEN_IN_STUDENT_EVENTS = (
    # B07 — the toast that reported a calendar entry nobody made. The page now
    # renders a link the *server* said is valid, or the server's reason there is
    # none.
    "Calendar event added",
    "handleAddToCalendar",
    # B09 — the fabricated month grid. The grid on the page now draws only
    # events the two reads above it returned.
    "MockStudentCalendar",
    "mockEvents",
    # B06 — a Register control with no command behind it. There is no
    # registration table (OQ-CBA-018), so there is nothing for such a button to
    # call, and a client-side set of "registered" ids would be a claim the server
    # cannot confirm on the next page load.
    "registeredEventIds",
    "setRegistered",
    "handleRegister",
)


#: A block comment (`/* … */`, including the JSX `{/* … */}` form), or a line
#: whose first non-blank character starts one (`//`) or continues one (`*`).
_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_COMMENT_LINE = re.compile(r"^\s*(?://|\*).*$", re.MULTILINE)


def _code_only(source: str) -> str:
    """The file with its comments removed.

    Load-bearing rather than tidy. This page's docstring explains at length what
    it used to be, and it names ``MockStudentCalendar``, ``handleAddToCalendar``
    and the "Calendar event added" toast in order to say they are gone. Scanning
    the raw text for those strings would fail on the sentence saying they were
    removed, which would push the next author toward deleting the explanation to
    make a test pass — the opposite of what the explanation is for.

    So the forbidden-pattern checks run against code, and the prose stays free to
    name what it is warning about.
    """
    return _COMMENT_LINE.sub("", _COMMENT.sub("", source))


@pytest.fixture(scope="module")
def source() -> str:
    return STUDENT_EVENTS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def code(source: str) -> str:
    return _code_only(source)


@pytest.fixture(scope="module")
def page_body(code: str) -> str:
    """The page component's own JSX, which is what the reader actually sees."""
    return code[code.index(PAGE_COMPONENT) :]


class TestTheMonthCalendarIsLast:
    """§15's Events page requirement, asserted as an ordering."""

    def test_all_three_sections_are_present(self, code: str) -> None:
        """The calendar being last is only meaningful while there is something above it.

        A page that dropped the two lists would satisfy "the calendar is last"
        vacuously, and would be exactly the calendar-first page D-11 argues
        against, wearing the requirement as cover.
        """
        for label in SECTION_LABELS:
            assert label in code, f"the Events page no longer renders {label}"

    def test_the_sections_appear_in_the_order_the_customer_asked_for(self, page_body: str) -> None:
        positions = [page_body.index(site) for site in RENDER_SITES_IN_ORDER]

        assert positions == sorted(positions), (
            "the Events page sections are out of order: customer §15 keeps the month "
            "calendar at the bottom. Found at "
            f"{dict(zip(RENDER_SITES_IN_ORDER, positions, strict=True))}"
        )

    def test_nothing_renders_after_the_month_calendar(self, page_body: str) -> None:
        """ "At the bottom" is stronger than "after the lists".

        Checked against the component invocation rather than the section markup,
        because the calendar is rendered by ``<MonthCalendar …>`` at the end of
        the page body and it is *that* call a later edit would move.
        """
        invocation = page_body.rindex("<MonthCalendar")
        remainder = page_body[invocation:]

        # What may follow is the closing of the fragment and the conditional —
        # nothing that renders content of its own.
        for opener in ("<section", "<ul", "<header", "<form"):
            assert opener not in remainder, (
                f"{opener} appears after <MonthCalendar>; the month calendar must be the "
                "last thing on the Events page (customer §15)"
            )


class TestThePageRendersServerData:
    """No fixture events, and no rule about downloads that this page decides itself."""

    def test_both_student_reads_are_called(self, code: str) -> None:
        for reader in ("fetchStudentEvents", "fetchStudentAgenda"):
            assert reader in code, f"the Events page no longer calls {reader}"

    def test_the_client_functions_name_the_routes_the_api_serves(self) -> None:
        """The two paths, spelled in the client exactly as the router registers them.

        ``tests/integration/test_event_registration.py`` asserts the served route
        set contains these two and no registration path; this asserts the browser
        asks for the same two, so a rename on either side is caught from both
        directions.
        """
        client = API_CLIENT.read_text(encoding="utf-8")

        for path in ("/student/events", "/student/agenda"):
            assert path in client, f"lib/api.ts no longer requests {path}"

    def test_the_download_link_is_rendered_from_the_servers_own_verdict(self, code: str) -> None:
        """The page reads ``calendar.download_path``; it does not build one.

        Composing ``/v1/units/.../invite.ics`` in the browser would put a second
        copy of ``routers/calendar.py``'s refusal rules on this page, and the
        first time the two disagreed a student would be handed a link that 404s —
        B07's defect with a real URL attached.
        """
        assert "calendar.download_path" in code
        assert "invite.ics" not in code, (
            "the Events page composes an .ics URL itself; it must render the "
            "`download_path` the server supplied, or the reason there is none"
        )

    def test_a_refusal_is_shown_rather_than_discovered_by_clicking(self, code: str) -> None:
        """All three of the server's reasons have wording a student can read."""
        for reason in (
            "event_time_unresolved",
            "event_end_unknown",
            "event_not_on_your_agenda",
        ):
            assert reason in code, f"the Events page renders no wording for {reason}"


class TestTheRemovedDefectsStayRemoved:
    """B06, B07 and B09, by name."""

    @pytest.mark.parametrize("pattern", FORBIDDEN_IN_STUDENT_EVENTS)
    def test_the_pattern_is_absent(self, pattern: str, code: str) -> None:
        assert pattern not in code, (
            f"{pattern!r} is back on the student Events page. See "
            "`docs/plans/frontend-broken-buttons.md` B06/B07/B09 for what it was."
        )

    def test_the_page_claims_attendance_rather_than_registration(self, code: str) -> None:
        """The wording B06 asked for, held to.

        "Registered" is a state this deployment cannot produce: the only link
        between a student and an event is ``attendance_record``, and writing one
        when somebody signs up would credit them under ADR-0013 for an event they
        had not attended. So the page says what the row actually means.
        """
        assert "recorded at" in code
        assert "on_my_agenda" in code
