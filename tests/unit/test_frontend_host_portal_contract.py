"""Source contract for the Event Host portal's organization and request pages.

The host half of the migration ``0036`` surface, and the Connector's request
detail it pairs with. Three guarantees, each pinned because each is a decision
somebody made rather than a shape the code happened to take:

**The host routes and the Connector routes are disjoint, and pages honour it.**
``GET``/``PUT .../host/organization`` and ``GET .../host/speaker-requests`` are
``volunteer``-only; ``GET .../speaker-requests`` and ``GET
.../host-organizations`` are ``admin``/``coordinator``-only. A host page that
imported the Connector's helpers would be a page whose every read is a 403 —
and, worse, a standing invitation to "fix" the refusal by widening a role set
the server deliberately narrowed. So the mounted volunteer pages are scanned
for the Connector's helpers by name.

**A 404 on ``host/organization`` is a state, not a failure.** A host who has
described no organization gets ``host_organization_not_found``; the page must
branch on that code and open the create form rather than render an outage.
Both ``409``s — ``host_organization_name_taken`` and
``host_organization_unit_conflict`` — are rendered from the server's message,
because both are things a person resolves rather than retries.

**The Connector's request detail does not invent a filer.**
``SpeakerRequestResponse`` carries no ``filed_by`` and no organization field:
the ``host_organization_id`` stamp the create path writes is published by no
read model. The detail therefore shows the unit's *directory*
(``GET .../host-organizations``) labelled as the directory, and says plainly
that which organization filed this request is not a fact the surface has. If
the contract ever grows a filer field, the assertion below fails loudly rather
than letting the page silently start presenting it.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src"

API_LIB = FRONTEND_SRC / "lib" / "api.ts"
ROUTES = FRONTEND_SRC / "app" / "routes.tsx"
HOST_SHELL = FRONTEND_SRC / "app" / "components" / "VolunteerPortalLayout.tsx"
PAGES = FRONTEND_SRC / "app" / "pages"

HOST_HOME = PAGES / "volunteer" / "VolunteerHome.tsx"
HOST_REQUEST_FORM = PAGES / "volunteer" / "VolunteerSpeakerRequest.tsx"
HOST_REQUESTS = PAGES / "volunteer" / "VolunteerMyRequests.tsx"
HOST_ORGANIZATION = PAGES / "volunteer" / "VolunteerOrganization.tsx"
HOST_PROFILE = PAGES / "volunteer" / "VolunteerProfile.tsx"
CONNECTOR_REQUESTS = PAGES / "coordinator" / "CoordinatorSpeakerRequests.tsx"
CONNECTOR_MATCH_RUNS = PAGES / "coordinator" / "CoordinatorMatchRuns.tsx"

#: The volunteer-portal pages the router mounts. ``VolunteerConfirmedSpeaker``
#: and ``VolunteerAssignments`` stay in the directory unmounted — the former is
#: pinned by ``test_frontend_handoff_contract.py`` to routes only a Connector
#: may call, which is exactly why it is not on this list.
MOUNTED_HOST_PAGES = (HOST_HOME, HOST_REQUEST_FORM, HOST_REQUESTS, HOST_ORGANIZATION, HOST_PROFILE)

#: Helpers whose routes are ``admin``/``coordinator`` only. A mounted Event
#: Host page that named one would guarantee its reader a 403.
CONNECTOR_ONLY_HELPERS = (
    "fetchSpeakerRequests",
    "fetchHostOrganizations",
    "createMatchRun",
    "fetchMatchRun",
    "fetchSpeakerContacts",
    "fetchReviewItems",
    "fetchConfirmedSpeakers",
    "reconcileSpeakerHandoff",
    "createSpeakerContact",
    "fetchUnitEvents",
    "createManualEvent",
    "fetchSpeakerInvitationBatches",
    "createSpeakerInvitationBatch",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _code_only(source: str) -> str:
    """Strip JSDoc blocks and line comments before scanning. See the sibling files."""
    without_blocks = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return "\n".join(
        line for line in without_blocks.splitlines() if not line.lstrip().startswith("//")
    )


def _helper_body(source: str, name: str) -> str:
    """The source of one exported helper, from its signature to its closing brace."""
    marker = f"export async function {name}"
    assert marker in source, f"api.ts is missing {name}"
    return source.split(marker, 1)[1].split("\n}", 1)[0]


# ---------------------------------------------------------------------------
# The client helpers
# ---------------------------------------------------------------------------


def test_api_lib_reads_and_writes_the_hosts_own_organization() -> None:
    """``GET``/``PUT /v1/units/{unit_id}/host/organization``, unit in the path."""
    source = API_LIB.read_text(encoding="utf-8")

    read_helper = _helper_body(source, "fetchOwnHostOrganization")
    assert "/host/organization" in read_helper
    assert 'method: "GET"' in read_helper
    assert "encodeURIComponent(unitId)" in read_helper
    assert "authenticated: true" in read_helper

    write_helper = _helper_body(source, "upsertOwnHostOrganization")
    assert "/host/organization" in write_helper
    assert 'method: "PUT"' in write_helper, (
        "the URL names one resource — the caller's organization — and replaces it"
    )
    assert "encodeURIComponent(unitId)" in write_helper
    assert "authenticated: true" in write_helper


def test_api_lib_reads_the_connector_directory() -> None:
    """``GET /v1/units/{unit_id}/host-organizations`` — a different, disjoint route."""
    source = API_LIB.read_text(encoding="utf-8")
    helper = _helper_body(source, "fetchHostOrganizations")

    assert "/host-organizations" in helper
    assert "/host/organization" not in helper.replace("/host-organizations", ""), (
        "the directory and the host's own route are different paths and different role sets"
    )
    assert "encodeURIComponent(unitId)" in helper
    assert "authenticated: true" in helper
    assert 'method: "POST"' not in helper and 'method: "PUT"' not in helper


def test_the_upsert_payload_carries_no_caller_chosen_identity() -> None:
    """MM-A01: the body names no tenant, unit, user, organization, or member.

    All of those come off the verified principal and the authorized path
    server-side. A field that let the body name one is the caller-selected
    identity pattern — here it would let a host rewrite another host's
    organization.
    """
    source = API_LIB.read_text(encoding="utf-8")
    declared = source.split("export interface HostOrganizationUpsertPayload", 1)
    assert len(declared) == 2, "api.ts must type the upsert body rather than sending unknown"
    body = declared[1].split("\n}", 1)[0]

    for forbidden in (
        "unit_id",
        "tenant",
        "user_id",
        "organization_id",
        "member",
        "granted_by",
    ):
        assert forbidden not in body, (
            f"HostOrganizationUpsertPayload gained {forbidden!r}; the server takes every "
            "one of those from the principal and the path, never the body"
        )


def test_the_organization_types_carry_the_membership_truth() -> None:
    """``member_count`` and ``self_asserted`` are what keeps membership honest.

    A count, never the accounts — and a flag that says the membership was
    asserted rather than granted, so no screen can present it as approved.
    """
    source = API_LIB.read_text(encoding="utf-8")

    view = source.split("export interface HostOrganizationView", 1)
    assert len(view) == 2
    assert "member_count" in view[1].split("\n}", 1)[0]

    own = source.split("export interface HostOwnOrganization", 1)
    assert len(own) == 2
    own_body = own[1].split("\n}", 1)[0]
    assert "self_asserted" in own_body
    assert "member_since" in own_body


# ---------------------------------------------------------------------------
# The host's organization page
# ---------------------------------------------------------------------------


def test_the_organization_page_uses_only_the_host_routes() -> None:
    source = HOST_ORGANIZATION.read_text(encoding="utf-8")

    assert "fetchOwnHostOrganization" in source
    assert "upsertOwnHostOrganization" in source
    assert "fetchHostOrganizations" not in source, (
        "the directory is admin/coordinator-only; a host page that called it would "
        "guarantee its reader a 403"
    )


def test_the_organization_page_treats_the_404_as_a_state() -> None:
    """``host_organization_not_found`` opens the create form, not an error."""
    source = HOST_ORGANIZATION.read_text(encoding="utf-8")
    assert '"host_organization_not_found"' in source, (
        "the page must branch on the 404's code — branching on message text is "
        "parsing prose, and treating every 404 as an error hides the create path"
    )
    assert ".code" in source, "the branch is on the error's stable code, never its message"


def test_the_organization_page_renders_the_servers_refusals() -> None:
    """The two 409s and every other refusal arrive as the server's message."""
    source = HOST_ORGANIZATION.read_text(encoding="utf-8")
    assert "ApiRequestError" in source
    assert "member_count" in source
    assert "self_asserted" in source


def test_the_organization_page_composes_no_identifier_in_the_browser() -> None:
    """The unit is the server's grant, not an env var and not a query string."""
    source = _code_only(HOST_ORGANIZATION.read_text(encoding="utf-8"))

    assert "usePortalAccess" in source
    assert "grantedPortal" in source
    assert "useAuthenticatedPrincipal" in source

    for forbidden in ("getConfiguredUnitId", "VITE_SMARTMATCH_UNIT_ID", "unit_id=", "?org"):
        assert forbidden not in source, (
            f"VolunteerOrganization sources an identifier from the browser: {forbidden!r}"
        )


# ---------------------------------------------------------------------------
# The host home page and the request detail
# ---------------------------------------------------------------------------


def test_the_home_page_reads_the_hosts_own_routes() -> None:
    source = HOST_HOME.read_text(encoding="utf-8")

    assert "fetchMySpeakerRequests" in source, (
        "the home page's request list is the host-scoped read, never the queue"
    )
    assert "fetchOwnHostOrganization" in source


def test_the_home_page_links_into_the_host_surfaces() -> None:
    source = HOST_HOME.read_text(encoding="utf-8")
    for target in (
        "/volunteer-portal/speaker-request",
        "/volunteer-portal/my-requests",
        "/volunteer-portal/organization",
    ):
        assert f'to="{target}"' in source, f"the home page lost its link to {target}"


def test_the_my_requests_page_has_a_request_detail_state() -> None:
    """``?request={id}`` selects one row the server already returned.

    The parameter is read for selection and never sent back — a detail view
    that re-fetched by a caller-chosen id would be a second, unpermitted read
    path, which is why the host route has no detail endpoint at all.
    """
    source = HOST_REQUESTS.read_text(encoding="utf-8")
    code = _code_only(source)

    assert 'searchParams.get("request")' in code
    assert "setSearchParams" in code
    # And the detail renders the request's own statuses — the only progress
    # signal the host route publishes.
    assert "publication_status" in source
    assert "review_status" in source


def test_no_mounted_host_page_reaches_a_connector_route() -> None:
    """Every helper a host page may not call, checked against every mounted page."""
    for page in MOUNTED_HOST_PAGES:
        source = _code_only(page.read_text(encoding="utf-8"))
        for forbidden in CONNECTOR_ONLY_HELPERS:
            assert forbidden not in source, (
                f"{page.name} reaches {forbidden} — an admin/coordinator-only route that "
                "answers an Event Host with 403"
            )


# ---------------------------------------------------------------------------
# The Connector's request detail and match initiation
# ---------------------------------------------------------------------------


def test_the_connector_page_keeps_its_detail_inside_the_queue() -> None:
    """``?request={id}`` selects from the loaded queue; nothing is re-fetched."""
    source = CONNECTOR_REQUESTS.read_text(encoding="utf-8")
    code = _code_only(source)

    assert "fetchSpeakerRequests" in code
    assert 'searchParams.get("request")' in code
    assert "request_id" in code, "a detail must open by the server's own id"


def test_the_connector_page_reads_the_directory_and_names_no_filer() -> None:
    """The directory is shown; a filer is not invented.

    ``filed_by`` appearing in this file's code would mean the page started
    presenting a field the response does not carry — or that the response grew
    one, in which case this test's failure is the deliberate place to update
    the page's "who is asking" copy.
    """
    source = CONNECTOR_REQUESTS.read_text(encoding="utf-8")
    code = _code_only(source)

    assert "fetchHostOrganizations" in code
    assert "filed_by" not in code, (
        "the request detail must not name a filer — the read model publishes none"
    )
    assert "host_organization_id" not in code, (
        "the event's organization stamp is not on the read model; do not present "
        "a directory row as the request's filer"
    )


def test_the_connector_page_hands_off_to_the_match_form() -> None:
    """The action navigates to ``match-runs?request=`` — a link, not a submission.

    ``POST .../match-runs`` takes a candidate pool that is the Connector's own
    choice, so this page must not call ``createMatchRun`` itself: the hand-off
    is to the form where the pool is picked.
    """
    source = CONNECTOR_REQUESTS.read_text(encoding="utf-8")
    code = _code_only(source)

    assert "/coordinator-portal/match-runs?request=" in code
    assert "createMatchRun" not in code, (
        "a match run is submitted from the Run-a-match form where the pool is "
        "chosen — never fired from the request detail"
    )


def test_the_match_form_honours_the_request_parameter() -> None:
    """``?request={id}`` pre-selects the named request — only if the queue holds it."""
    source = CONNECTOR_MATCH_RUNS.read_text(encoding="utf-8")
    code = _code_only(source)

    assert 'searchParams.get("request")' in code
    assert "setSelectedRequestId" in code


# ---------------------------------------------------------------------------
# Reachability
# ---------------------------------------------------------------------------


def test_the_organization_route_and_nav_entry_exist() -> None:
    """The page is mounted and linked — a route no nav offers is a secret."""
    routes = ROUTES.read_text(encoding="utf-8")
    volunteer = re.search(
        r'path: "volunteer-portal".*?children: \[(.*?)\n {4}\]', routes, flags=re.DOTALL
    )
    assert volunteer is not None, "could not locate the volunteer portal children array"
    assert 'path: "organization"' in volunteer.group(1), (
        "the organization page is not mounted in the Event Host portal"
    )

    shell = HOST_SHELL.read_text(encoding="utf-8")
    assert 'href: "/volunteer-portal/organization"' in shell, (
        "the host shell has no nav entry for the organization page"
    )


def test_every_host_nav_entry_resolves_to_a_mounted_route() -> None:
    """The sidebar's promises, checked against the router rather than restated."""
    routes = ROUTES.read_text(encoding="utf-8")
    volunteer = re.search(
        r'path: "volunteer-portal".*?children: \[(.*?)\n {4}\]', routes, flags=re.DOTALL
    )
    assert volunteer is not None
    mounted = {"/volunteer-portal"}
    for match in re.finditer(r'path: "([^"]+)"', volunteer.group(1)):
        mounted.add(f"/volunteer-portal/{match.group(1)}")

    shell = _code_only(HOST_SHELL.read_text(encoding="utf-8"))
    hrefs = re.findall(r'href: "([^"]+)"', shell)
    assert hrefs, "the host shell declares no navigation"
    for href in hrefs:
        assert href in mounted, f"the host sidebar links {href}, which routes.tsx does not mount"
