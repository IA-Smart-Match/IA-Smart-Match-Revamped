"""The calendar-invite facade is wired to exactly one .ics route, and nothing else.

`tests/golden/test_calendar_invite_golden.py` covers what
`smartmatch_domain.calendar_invite` *does*. What is covered here is the shape of
its reach into a running deployment, which no test of the facade itself can see.

## What changed, and what did not

This file used to assert an **absence**: no route, no command, no import, on the
argument that the synthetic pilot development authorization (2026-09-03, §3)
permits "ICS artifacts" only while gate **G5 (Calendar API)** stays deferred,
and that a builder nothing can call is exactly that permission and nothing more.

The absence was the right control while there was nothing to serve. It was never
the *whole* control, and reading it as one would have made the authorization say
something it does not: §3 permits ICS artifacts, and an artifact nobody can
obtain is not an artifact. So the assertions below now pin the two halves that
actually matter, and the ones that were only ever proxies for them are gone:

* **The API serves one .ics route, and it is the one this file names.** Not "no
  calendar route" — a route set the contract and the live app both agree on,
  with exactly one calendar path in it. A second one appearing is as much a
  failure as the first one was.
* **The worker still routes no calendar command.** Unchanged, and load-bearing:
  the .ics is produced synchronously from a row the request already read. A
  command that generated calendar artifacts in the background would be a
  scheduling surface nobody asked for and G5 has not granted.
* **Nothing reaches for the Google Calendar API.** Unchanged, and the reason
  this file still names the gate. G5 is about writing into somebody's calendar
  on their behalf; handing a person a file is not that, and the difference is
  the dependency that is absent here. These are the assertions that would fail
  if "wire the facade" were ever read as "acquire the capability".

`docs/plans/open-questions/calendar-deferred.md` OQ-001 is the decision this
file is the enforcement of.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from smartmatch_worker.handlers import default_registry

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The module the API is now expected to reach, and the worker is not.
FACADE_MODULE = "smartmatch_domain.calendar_invite"

#: The one calendar route the API is allowed to serve. Written out in full
#: rather than matched by pattern: the point of this file is that *this* path
#: exists and no other calendar path does, and a pattern would accept a second
#: route that happened to look similar.
INVITE_PATH = "/v1/units/{unit_id}/events/{event_id}/invite.ics"

#: Mirrors `[tool.pytest.ini_options] pythonpath` so a subprocess sees the same
#: workspace packages this session imported.
_WORKSPACE_PATHS = (
    ".",
    "python/smartmatch_domain",
    "python/smartmatch_authz",
    "python/smartmatch_providers",
    "python/smartmatch_persistence",
    "services/api",
    "services/worker",
)

#: Substrings that betray a calendar capability appearing in a path or a command
#: type. Deliberately broader than the module name: the point is to catch a
#: route named `/v1/.../invite.ics` as readily as an import. A bare "ics" is not
#: usable as a marker — it is a substring of "metrics", which is a real and
#: unrelated route — so the extension and command-namespace forms are matched
#: instead.
_CALENDAR_MARKERS = ("calendar", "invite", ".ics", "ics.")


def _import_in_a_fresh_interpreter(module: str) -> frozenset[str]:
    """Import `module` alone and report every module it dragged in.

    A subprocess rather than `sys.modules`: this pytest session has already
    imported the facade for the golden tests, so an in-process check would be
    answering a question about the test run instead of about the composition
    root.
    """
    script = (
        "import sys, json\n"
        f"sys.path[:0] = {list(_WORKSPACE_PATHS)!r}\n"
        f"__import__({module!r})\n"
        "print(json.dumps(sorted(sys.modules)))\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, (
        f"importing {module} failed:\n{completed.stdout}\n{completed.stderr}"
    )
    return frozenset(json.loads(completed.stdout.splitlines()[-1]))


class TestExactlyOneHttpSurface:
    """The API serves the .ics route this file names, and no other calendar path."""

    def test_the_served_openapi_paths_still_match_the_committed_contract(self):
        """The route-set claim, stated against the artifact clients are built from.

        Checking the live app against `contracts/openapi/smartmatch.json` catches
        both halves of the failure at once: a route added without regenerating
        the contract, and a contract edited to accommodate one.
        """
        from smartmatch_api.main import app

        committed = json.loads(
            (REPO_ROOT / "contracts" / "openapi" / "smartmatch.json").read_text(encoding="utf-8")
        )

        assert sorted(app.openapi()["paths"]) == sorted(committed["paths"])

    def test_the_invite_route_is_served(self):
        """The wiring itself: §3's "ICS artifacts" is a thing a caller can obtain."""
        from smartmatch_api.main import app

        assert INVITE_PATH in app.openapi()["paths"]

    def test_it_is_a_get_that_offers_the_calendar_media_type(self):
        """A download, not a command.

        The method and the advertised content type are what a client builds a
        link against, and they are what distinguish this from a
        `POST`-a-command-and-poll surface — see the route module's docstring on
        why an .ics is not a job.
        """
        from smartmatch_api.main import app

        operations = app.openapi()["paths"][INVITE_PATH]

        assert set(operations) == {"get"}
        assert "text/calendar" in operations["get"]["responses"]["200"]["content"]

    def test_no_second_calendar_route_appeared(self):
        """One .ics surface. A feed, an upload, or a bulk export is not this one.

        Stated independently of the contract, so regenerating it cannot help.
        A `webcal:` subscription feed in particular is a different
        authorization question — a URL carrying its own long-lived credential —
        and it must not arrive as a quiet sibling of this route
        (`docs/plans/open-questions/calendar-deferred.md`).
        """
        from smartmatch_api.main import app

        offenders = sorted(
            path
            for path in app.openapi()["paths"]
            if path != INVITE_PATH
            and any(marker in str(path).lower() for marker in _CALENDAR_MARKERS)
        )

        assert offenders == [], f"these routes serve a second calendar surface: {offenders}"

    def test_the_api_composition_root_reaches_the_facade(self):
        """Import reachability, the other direction from what this file used to assert.

        The route imports `build_invite_ics` rather than reimplementing RFC 5545
        beside it, and this is what would notice a handler that stopped
        delegating and started assembling the document itself — the divergence
        the golden tests exist to prevent, arriving through the API instead of
        through the domain.
        """
        imported = _import_in_a_fresh_interpreter("smartmatch_api.main")

        assert FACADE_MODULE in imported


class TestNoWorkerSurface:
    """The shipped worker routes no command that produces a calendar artifact.

    Unchanged by the wiring. The .ics is rendered synchronously from a row the
    request already holds; a background command that produced calendar
    artifacts would be a scheduling surface nobody asked for, and G5 has granted
    no such thing.
    """

    def test_the_shipped_registry_routes_no_calendar_command(self):
        command_types = default_registry().command_types
        offenders = [
            command
            for command in command_types
            for marker in _CALENDAR_MARKERS
            if marker in command.lower()
        ]

        assert offenders == [], f"G5 is deferred; these commands are routed: {offenders}"
        # The rest of the shipped registry is unaffected by this PR.
        assert {"test.noop", "import.create"} <= set(command_types)

    def test_the_worker_composition_root_never_imports_the_facade(self):
        imported = _import_in_a_fresh_interpreter("smartmatch_worker.main")

        assert FACADE_MODULE not in imported


class TestNoGoogleCalendarDependency:
    """G5 is about the Calendar *API*; neither the facade nor the route reaches for it.

    These are the assertions the deferral actually rests on, and they are why
    this file still names the gate after the route exists. Serving a file a
    person imports themselves needs no authorization from anybody; writing into
    their calendar on their behalf needs an OAuth client, a scope, a consent
    screen and an institutional owner for all three — none of which appear
    below, in either module.
    """

    #: Names that only appear where a Google Calendar client is being set up.
    _FORBIDDEN = (
        "googleapiclient",
        "google_auth_oauthlib",
        "google-api-python-client",
        "auth/calendar",
        "calendar.events",
        "GOOGLE_CALENDAR",
        "CALENDAR_CREDENTIALS",
    )

    #: Both halves of the wiring, checked with the same list. The route is as
    #: capable of acquiring the dependency as the facade is, and it is the newer
    #: and therefore less-examined of the two.
    _SOURCES = (
        Path("python") / "smartmatch_domain" / "smartmatch_domain" / "calendar_invite.py",
        Path("services") / "api" / "smartmatch_api" / "routers" / "calendar.py",
        # The third module that now knows the .ics route exists (card
        # `CBA-STUDENT-EVENTS`). It hands a student the *path* and never the
        # bytes, so it is the likeliest place for somebody to decide the link
        # would be nicer as a real calendar integration — which is precisely the
        # acquisition G5 has not granted.
        Path("services") / "api" / "smartmatch_api" / "routers" / "student_events.py",
    )

    @pytest.mark.parametrize("source", _SOURCES, ids=lambda path: path.name)
    @pytest.mark.parametrize("token", _FORBIDDEN)
    def test_neither_module_names_a_google_calendar_client_scope_or_env_var(
        self, token: str, source: Path
    ):
        assert token not in (REPO_ROOT / source).read_text(encoding="utf-8")

    def test_the_facade_imports_nothing_but_stdlib_and_the_ics_module(self):
        """The domain layer stays pure: no client, no transport, no credentials."""
        imported = _import_in_a_fresh_interpreter(FACADE_MODULE)
        third_party = {
            name
            for name in imported
            if name.split(".")[0] in {"googleapiclient", "google", "httpx", "requests", "urllib3"}
        }

        assert third_party == set()
        assert "smartmatch_domain.ics" in imported

    def test_the_route_pulls_in_no_google_package(self):
        """The API composition root gained an .ics route and no calendar client."""
        imported = _import_in_a_fresh_interpreter("smartmatch_api.main")
        google = {name for name in imported if name.split(".")[0] in {"googleapiclient", "google"}}

        assert google == set()


class TestTheStudentSurfaceLinksToTheRouteRatherThanReimplementingIt:
    """One .ics route, and one other module that points at it (card ``CBA-STUDENT-EVENTS``).

    ``routers/student_events.py`` is what finally gave the student portal an
    ``event_id`` to hand the download — the half
    ``docs/plans/frontend-broken-buttons.md`` B07 recorded as remaining. It does
    that by putting the *path* on each listed event, which is a new way for this
    file's subject to go wrong: a module that composes an invite URL is one
    refactor away from composing the invite.

    So the property asserted here is that it stays a **pointer**. It formats the
    same path the route registers, it produces no document, and it does not reach
    the facade at all.
    """

    def test_the_template_it_hands_out_is_the_path_the_api_serves(self):
        """One string, checked against the route set rather than against a copy.

        A drifted template would be worse than a missing one: every item in the
        listing would carry a link that 404s, and nothing would fail until
        somebody clicked. Comparing against :data:`INVITE_PATH` — which
        :class:`TestExactlyOneHttpSurface` has already compared against the live
        app and the committed contract — makes the listing's link and the served
        route the same fact.
        """
        from smartmatch_api.routers import student_events

        assert student_events.INVITE_PATH_TEMPLATE == INVITE_PATH

    def test_it_formats_that_template_rather_than_assembling_a_url(self):
        """The ids go into the one template; no second spelling of the path exists.

        ``.format`` on the module constant is the only construction, so a caller
        cannot get a link the route does not serve, and the test above is
        sufficient to know every link is right.
        """
        import uuid

        from smartmatch_api.routers import student_events

        unit_id = uuid.uuid4()
        event_id = uuid.uuid4()

        formatted = student_events.INVITE_PATH_TEMPLATE.format(unit_id=unit_id, event_id=event_id)

        assert formatted == f"/v1/units/{unit_id}/events/{event_id}/invite.ics"

    def test_the_student_module_never_reaches_the_facade(self):
        """It advertises the artifact; it does not make one.

        The mirror of :func:`test_the_api_composition_root_reaches_the_facade`,
        pointed at the module that must *not*. Two modules producing RFC 5545
        bytes is the divergence the golden tests exist to prevent, and it would
        arrive exactly here — as a "small optimisation" that inlines the document
        into the listing so the client saves a request.
        """
        source = (
            REPO_ROOT / "services" / "api" / "smartmatch_api" / "routers" / "student_events.py"
        ).read_text(encoding="utf-8")

        assert "build_invite_ics" not in source
        assert "smartmatch_domain.calendar_invite" not in source.replace(
            # The module docstring names the facade to say it is *not* imported.
            "``smartmatch_domain.calendar_invite`` is not imported here",
            "",
        )

    def test_the_student_routes_are_not_a_second_calendar_surface(self):
        """Neither student path trips this file's own calendar markers.

        ``/student/events`` and ``/student/agenda`` are event reads that happen to
        mention a calendar link in their bodies, which is a different thing from
        being a calendar surface — and
        :func:`test_no_second_calendar_route_appeared` is what would have caught
        it had they been named otherwise. Stated here too, against the paths
        directly, so the reason they pass that test is recorded rather than
        incidental.

        The registration path joined them in ``CBA-STUDENT-REGISTRATION``, and it
        belongs in this list for the same reason the other two do rather than as
        an exception to it: it writes ``event_registration`` and produces no
        calendar document. What it *does* do is change the answer the ``.ics``
        route gives — a registered student is now attached to the event and may
        download it — which is a change to that route's *input*, not a second
        implementation of it. The one ``.ics`` surface is still the one
        :data:`INVITE_PATH` names.
        """
        from smartmatch_api.main import app

        student_paths = [path for path in app.openapi()["paths"] if "/student/" in str(path)]

        assert sorted(student_paths) == [
            "/v1/units/{unit_id}/student/agenda",
            "/v1/units/{unit_id}/student/events",
            "/v1/units/{unit_id}/student/events/{event_id}/registration",
        ]
        for path in student_paths:
            assert not any(marker in str(path).lower() for marker in _CALENDAR_MARKERS)
