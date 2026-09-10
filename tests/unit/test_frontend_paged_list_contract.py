"""Source contract for the shared list pager (TRACK T1 §B).

Pagination is where a client quietly acquires a second, wrong idea of how big
something is. The honest version of the feature is small: take an array that has
already arrived, show a window onto it, and say which window. The dishonest
version looks identical from a screenshot — it grows an offset, a limit, a
`total`, and within a release the page is reporting a population figure that it
computed from whatever the last response happened to contain.

This file holds the small version in place, at the level a source scan can
reach.

**ADR-0011 rule 1 — an unmeasured quantity is unknown, never a number.** A list
pager has exactly one number it is entitled to: the length of the array it was
handed. That is a fact about this browser's memory and it is labelled as one
("of N loaded"). How many rows *exist* is a server-owned figure that no route
behind these pages returns, so the pager must never name one, and must never
reach for a `total`, a `total_count` or a `count` field to fill the gap.

**The server's `truncated` notice is a different statement and must survive.**
`CoordinatorMatchRuns` reads two capped list routes and tells the Connector when
the server stopped sending. "The server stopped sending" and "this page is not
drawing everything it holds" are two different facts about two different
quantities; folding the second over the first hides a real truncation, so the
notices stay, worded so that a reader can tell which is which.

**Selection is the caller's state, so paging cannot destroy it.** The pager
never receives, stores or clears a selection. That is not a convention to be
remembered — it is the absence of any code path that could, and the check below
is what keeps that absence honest as the component grows.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src"

PAGED_LIST = FRONTEND_SRC / "app" / "components" / "PagedList.tsx"
MATCH_RUNS_PAGE = FRONTEND_SRC / "app" / "pages" / "coordinator" / "CoordinatorMatchRuns.tsx"

#: Every list this track was asked to page, as (path relative to `pages/`, the
#: arrays each `PagedList` there is handed). A page missing from this map is a
#: page a reader still has to scroll to the bottom of.
PAGED_SURFACES: dict[str, tuple[str, ...]] = {
    "student/StudentEvents.tsx": ("published", "agenda"),
    "student/StudentSpeakerFeedback.tsx": ("ordered",),
    "student/StudentRewards.tsx": ("catalog.items", "redemptions"),
    "coordinator/CoordinatorMatchRuns.tsx": ("requests", "contacts"),
    "coordinator/CoordinatorSpeakerContacts.tsx": ("contacts",),
    "coordinator/CoordinatorSpeakerFeedback.tsx": ("rows",),
    "coordinator/CoordinatorInvitations.tsx": ("recipients",),
    # The three coordinator pages authored in parallel worktrees before this
    # component existed. Each left a `TODO(integrator)` asking to be wired up
    # once it landed, and each rendered a plain unpaged list until it was — so
    # they are pinned here, where a page that stops paging fails a test rather
    # than going unnoticed for a release.
    "coordinator/CoordinatorEvents.tsx": ("listing.events",),
    "coordinator/CoordinatorMeetings.tsx": ("meetings",),
    "coordinator/CoordinatorReviewQueue.tsx": ("items",),
    "volunteer/VolunteerMyRequests.tsx": ("requests",),
    "volunteer/VolunteerConfirmedSpeaker.tsx": ("speakers",),
}


def _code_only(source: str) -> str:
    """Strip JSDoc blocks and line comments before scanning.

    Prose *about* a server-owned total is not a server-owned total, and a check
    that could not tell the two apart would forbid this component from
    explaining why it does not compute one.
    """
    without_blocks = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return "\n".join(
        line for line in without_blocks.splitlines() if not line.lstrip().startswith("//")
    )


def _paged_list_code() -> str:
    """The pager's source with its explanatory prose removed."""
    return _code_only(PAGED_LIST.read_text(encoding="utf-8"))


def _page_code(relative_path: str) -> str:
    """One page's source with its explanatory prose removed."""
    path = FRONTEND_SRC / "app" / "pages" / Path(relative_path)
    assert path.exists(), f"{relative_path} does not exist"
    return _code_only(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The pager owns no data — it is a window onto an array someone else fetched
# ---------------------------------------------------------------------------


def test_the_pager_fetches_nothing() -> None:
    """No request, no query, no cursor, no route.

    Client-side windowing and server-side paging are two features with two
    contracts, and the difference is invisible from a screenshot. Keeping the
    read out of this component is what lets a reader of any calling page see, in
    that page's own source, which of the two that page has.
    """
    code = _paged_list_code()

    for forbidden in (
        "fetch(",
        "lib/api",
        "useQuery",
        "useEffect",
        "await ",
        "async ",
        "?offset=",
        "?limit=",
        "cursor",
    ):
        assert forbidden not in code, (
            f"PagedList contains {forbidden!r}; it is a view over an array that has already "
            "been fetched and must never acquire a read of its own"
        )


def test_the_pager_slices_only_the_array_it_was_handed() -> None:
    """One `slice`, of `items`, and nothing else is sliced.

    The window is `items.slice(firstIndex, firstIndex + pageSize)`. A second
    source of rows — a copy kept in state, a merge with anything else — would
    mean the drawn list and the array the caller passed could disagree, and the
    caller would have no way to see that from its own code.
    """
    code = _paged_list_code()

    assert "items.slice(" in code, "PagedList must window the caller's array with `items.slice`"
    assert code.count(".slice(") == 1, (
        "PagedList slices more than once; the visible page is one window onto `items`"
    )

    for forbidden in ("useState<TItem", "setItems", "items.sort(", "items.filter(", "concat("):
        assert forbidden not in code, (
            f"PagedList contains {forbidden!r}; ordering, filtering and ownership of the rows "
            "belong to the page above, which has already made those decisions"
        )


def test_the_pager_names_no_total_the_server_owns() -> None:
    """ADR-0011 rule 1: the only count here is the length of the local array.

    `items.length` is a fact about this browser's memory. `total`,
    `total_count`, `count` and `truncated` are the server's vocabulary for facts
    about the collection, and a pager that read any of them would be publishing
    a population figure that no route behind these pages actually returns.
    """
    code = _paged_list_code()

    for forbidden in (
        "total",
        "totalCount",
        "total_count",
        "totalItems",
        "count:",
        "truncated",
        "?? 0",
        "|| 0",
    ):
        assert forbidden not in code, (
            f"PagedList references {forbidden!r}; the only quantity it may state is the length "
            "of the array it was handed, and it labels that as loaded rather than as a total"
        )

    assert "items.length" in code, "the range line must be drawn from the local array's length"
    assert "loaded" in PAGED_LIST.read_text(encoding="utf-8"), (
        "the range line must say `loaded`, so that a count of rows in memory is never read as a "
        "count of rows that exist"
    )


def test_the_pager_never_touches_a_selection() -> None:
    """Selection survives paging because nothing here can clear it.

    A checked candidate is an id in the calling page's state, not a property of
    a drawn row. There is no selection prop, no selection state and no reset
    here, and that absence is the whole mechanism — `CoordinatorMatchRuns` can
    page through a roster and still submit everything a Connector checked.
    """
    code = _paged_list_code()

    for forbidden in ("selected", "onSelect", "onToggle", "checked", "clearSelection"):
        assert forbidden not in code, (
            f"PagedList references {forbidden!r}; a selection is the calling page's state and "
            "paging must have no code path that could reach it"
        )


# ---------------------------------------------------------------------------
# The controls the reader actually gets
# ---------------------------------------------------------------------------


def test_the_pager_offers_the_four_page_sizes_and_starts_at_ten() -> None:
    """Five, ten, twenty-five, fifty — as a real labelled `<select>`."""
    code = _paged_list_code()

    assert "const PAGE_SIZE_OPTIONS = [5, 10, 25, 50] as const;" in code
    assert "const DEFAULT_PAGE_SIZE: PageSizeOption = 10;" in code
    assert "<select" in code, "the page size must be a real select element"
    assert "<label htmlFor={selectId}" in code, (
        "the page-size select must carry a real associated label rather than a placeholder"
    )


def test_the_pager_draws_its_controls_above_and_below_the_list() -> None:
    """The literal complaint: an action button under a long list is unreachable.

    Controls only above a fifty-row list leave a reader who has reached the
    bottom with nowhere to go but back up, which is the scroll the pagination
    was supposed to remove.

    The ordering is read from the paged return only. The earlier
    ``children(items)`` is the un-paged escape hatch for a list too short for
    any page size to split, and it is deliberately bare.
    """
    code = _paged_list_code()

    assert 'controls("top")' in code, "the pager draws no control bar above the list"
    paged_return = code.split('controls("top")', 1)[1]

    assert "{children(" in paged_return, "the rows must be drawn below the upper control bar"
    below_rows = paged_return.split("{children(", 1)[1]
    assert 'controls("bottom")' in below_rows, (
        "the pager draws no control bar below the list, which is the whole complaint"
    )


def test_the_pager_controls_are_reachable_from_a_keyboard() -> None:
    """Buttons, not the primitive's hrefless anchors.

    `ui/pagination.tsx` renders `PaginationLink` as a bare `<a>` with no `href`,
    which no browser puts in the tab order. The nav landmark, the list structure
    and the ellipsis come from that primitive — no new dependency — but anything
    a reader has to operate is a real button.
    """
    code = _paged_list_code()

    assert 'from "./ui/pagination"' in code, (
        "the pager must be built over the existing primitive rather than a new dependency"
    )
    assert "PaginationLink" not in code, (
        "PaginationLink renders an anchor with no href, which is not keyboard reachable"
    )
    assert code.count('type="button"') >= 3, (
        "previous, next and each numbered page must be real buttons"
    )
    assert 'aria-current={page === currentPage ? "page" : undefined}' in code


# ---------------------------------------------------------------------------
# Applied everywhere, and never on top of the server's own truncation notice
# ---------------------------------------------------------------------------


def test_every_named_list_surface_pages_its_rows() -> None:
    """Each list in the §B inventory renders through the one shared component.

    A second, hand-rolled pager on any one page is how the page-size choices
    drift apart and how the "loaded" wording gets dropped from the copy that
    matters.
    """
    for relative_path, arrays in PAGED_SURFACES.items():
        code = _page_code(relative_path)

        assert "PagedList" in code, f"{relative_path} renders a list that still does not page"
        assert "components/PagedList" in code, (
            f"{relative_path} must import the shared pager rather than define its own"
        )
        assert code.count("<PagedList") == len(arrays), (
            f"{relative_path} should page {len(arrays)} list(s); found {code.count('<PagedList')}"
        )
        for array in arrays:
            assert f"items={{{array}}}" in code, (
                f"{relative_path} must hand `{array}` to PagedList rather than mapping it whole"
            )


def test_the_month_calendar_is_not_paged() -> None:
    """A month is a grid of days, not a list of rows.

    `StudentEvents` draws a seven-column calendar whose cells are days. Paging
    it would produce half a month, which is not a shorter view of the same
    thing — it is a different and wrong thing.
    """
    code = _page_code("student/StudentEvents.tsx")

    calendar = code.split("cells.map(", 1)
    assert len(calendar) == 2, "StudentEvents no longer draws its month grid from `cells`"
    assert "<PagedList" not in calendar[1].split("byDay.get", 1)[0], (
        "the month calendar must not be paged; its cells are days, not rows"
    )


#: The three coordinator pages wired to the pager after the fact, as
#: (path relative to `pages/`, the array handed over, the render prop's
#: parameter). Each was authored in its own worktree before `PagedList`
#: existed and rendered its whole array directly.
LATE_WIRED_SURFACES: tuple[tuple[str, str, str], ...] = (
    ("coordinator/CoordinatorEvents.tsx", "listing.events", "visibleEvents"),
    ("coordinator/CoordinatorMeetings.tsx", "meetings", "visibleMeetings"),
    ("coordinator/CoordinatorReviewQueue.tsx", "items", "visibleItems"),
)


def test_the_late_wired_coordinator_pages_draw_the_visible_slice() -> None:
    """Two facts, pinned together, because either alone is satisfiable wrongly.

    Handing the whole array to `PagedList` and then mapping that same whole
    array inside the render prop compiles, typechecks, and renders every row
    with a set of controls sitting uselessly above them — which is the original
    defect wearing the fix's clothes. So this asserts both halves:

    1. the *whole* array the server sent reaches the pager (`items={…}`), so the
       range line counts everything in hand and no filtering happens on the way
       in; and
    2. the render prop draws the *slice* the pager handed back, and the page's
       own array name does not appear in a `.map(` anywhere in its code.

    The three pages here are the ones that spent a release rendering unpaged
    lists behind a satisfied-looking `TODO(integrator)`, so they get the
    stronger check rather than the inventory membership alone.
    """
    for relative_path, array, visible in LATE_WIRED_SURFACES:
        code = _page_code(relative_path)

        assert f"items={{{array}}}" in code, (
            f"{relative_path} must hand the whole `{array}` array to PagedList"
        )
        assert f"{visible}.map(" in code, (
            f"{relative_path} must render the slice PagedList hands back, not its own array"
        )
        assert f"{array}.map(" not in code, (
            f"{relative_path} still maps `{array}` directly; the pager's controls would then sit "
            "above a list that draws every row anyway"
        )


def test_the_late_wired_pages_keep_the_servers_notice_distinct() -> None:
    """The pager's range line may not absorb a server-side truncation.

    All three of these pages read a route that stops sending at a cap, and each
    says so in its own words. That notice is about rows this browser never
    received; the pager's range line is about how much of what *did* arrive is
    currently drawn. A reader shown only the second would conclude the list is
    complete, which is the ADR-0011 rule 1 failure in list form — so the notice
    must still name the server as the thing that stopped.
    """
    for relative_path, _array, _visible in LATE_WIRED_SURFACES:
        text = (FRONTEND_SRC / "app" / "pages" / Path(relative_path)).read_text(encoding="utf-8")
        code = _code_only(text)

        assert "truncated" in code, f"{relative_path} no longer renders the server's cap notice"
        assert "stopped sending" in text.lower(), (
            f"{relative_path}'s truncation notice must say that the *server* stopped sending, so "
            "it cannot be read as the pager describing its own window"
        )


def test_the_servers_truncation_notices_stay_and_stay_distinct() -> None:
    """Two notices, two quantities, and neither may absorb the other.

    `GET /v1/units/{unit_id}/speaker-requests` and `.../speaker-contacts` both
    stop sending at a server-side cap, and `requestsTruncated` /
    `contactsTruncated` are how a Connector learns that the queue and the roster
    are larger than what arrived. The pager's own range line is about a
    different thing entirely — how much of what arrived is currently drawn. A
    reader who saw only one of the two would conclude the wrong thing about the
    other.
    """
    text = MATCH_RUNS_PAGE.read_text(encoding="utf-8")
    code = _code_only(text)

    assert "requestsTruncated" in code
    assert "contactsTruncated" in code
    assert "the server stopped sending" in text.lower(), (
        "the truncation notice must say that the *server* stopped sending, so it cannot be read "
        "as the pager saying this page is showing one window of what it holds"
    )
