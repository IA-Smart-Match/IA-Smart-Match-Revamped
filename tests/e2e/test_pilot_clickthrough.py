"""The synthetic pilot, clicked through end to end against a running appliance.

One ordered walk, in the order a coordinator would actually take it:

    fixture auth -> columns.yaml contract -> live import -> scheduler dispatch
      -> review ACCEPT and review REJECT -> metrics read (and drill-down)
      -> match run (score, explanation, shortlist) -> events + tag quarantine
      -> rewards -> outreach (draft -> send command -> job -> delivery events)

``scripts/compose_smoke.sh`` already proves the middle of that path — import,
dispatch, one accept, the metric moving, the pipeline row, the web proxy — and
this module does not restate it. What it adds is the half the smoke script does
not reach (the **reject** decision, the metric drill-down, the match run and its
explanation, the events and tag-quarantine reads, rewards, and the outreach
draft/send path), plus the honesty properties this job exists to enforce.

## What this job fails on

It is designed to go red on dishonesty, not only on breakage:

1. **A mocked rank or score.** :func:`test_09_match_run_scores_are_computed`
   and :func:`test_10_a_changed_evidence_changes_the_score` submit two pools
   that differ in one candidate's evidence and assert the score moves with it.
   A constant, a fixture, or a shuffled placeholder fails both.
2. **An unknown rendered as 0** (ADR-0011).
   :func:`test_12_an_unknown_factor_is_null_and_a_real_zero_is_zero` asserts
   both halves in one run: the candidate with no expertise record scores
   ``null`` / ``state=unknown``, while the candidate with an empty-but-present
   record scores ``0.0`` / ``zero_classification=measured_zero``. A system that
   collapses the two passes neither.
3. **A caller-chosen role.** :func:`test_02_the_role_is_resolved_from_me` reads
   the role from ``GET /v1/me`` and never sends one;
   :func:`test_03_the_caller_cannot_choose_its_own_role` proves the server is
   the one deciding, because the same principal is refused the student-gated
   rewards catalog.
4. **A percentage on a match score.** The ratified G1 rules forbid it:
   :func:`test_11_no_score_is_presented_as_a_percentage` asserts the label is
   ``"heuristic score"`` on every score, that no score exceeds 1.0, and that
   nothing in the payload is spelled as a percent.
5. **An outreach send that reports success without sending.**
   :func:`test_19_the_send_is_a_command_and_reports_no_status` asserts the
   ``202`` carries no field a client could render as "sent" — B17's replacement
   — and :func:`test_20_the_worker_sends_through_the_fixture_provider` reads
   the outcome back from the job's summary and the send's own delivery events
   rather than inferring it from the acknowledgement. It also asserts
   ``live_mode`` is false, so a green run is a run through the fixture provider
   and never one bought by mailing a stranger.
6. **A consent gate that is not actually enforced.**
   :func:`test_18_a_contact_without_approved_consent_cannot_be_composed_for`
   proves the compose gate refuses a ``discovered`` address, and
   :func:`test_21_a_recipient_who_unsubscribes_after_approval_is_not_written_to`
   proves the *submission* gate re-checks: a recipient who unsubscribes after a
   coordinator approved the draft gets the send refused ``403`` at submission,
   with nothing queued and no send row written. A ``202`` there would be the
   fake success this module exists to catch — an acknowledgement for a message
   that was never going to go out. The worker's delivery-time re-check, which
   covers the window after a ``202`` that no request-path check can see, is
   exercised in ``tests/integration/test_outreach_handler.py``.

## Known gaps, asserted rather than worked around

Every step that cannot run calls :func:`pytest.skip` naming the reason, and the
Makefile target passes ``-ra`` so each one is printed in the summary. Nothing
here asserts a fake success and nothing here widens authorization to make a
test pass.

* **Rewards is gated on the ``student`` role alone.** The compose principal is
  a coordinator, so the catalog and the redemption self-read are ``403``. That
  is deliberate pending the D6 role decision, so this module asserts the 403 is
  a *correct refusal* and skips the catalog walk by name.
* **The review queue has no list route.** The API exposes only
  ``POST /v1/review-items/{id}/decision``; the id a coordinator would click is
  not obtainable from any ``/v1`` path. The item ids below are therefore read
  from the database, exactly as ``compose_smoke.sh`` reads them, and the gap is
  recorded here rather than hidden behind the helper that works around it.
* **There is no ``GET /v1/units/{unit_id}/match-runs`` listing either.** A run's
  id is recovered from the job's own ``events_url``, which is the documented
  path — ``POST`` returns 202 and tells you where to follow the work.
* **Nothing creates a contact channel.** The outreach surface composes, lists,
  sends and reads; a contact arrives from the pipeline, and this appliance's
  seed creates none. :func:`_seed_contact_channel` therefore writes the row
  directly — through the shipped schema, so migration 0021's consent CHECKs
  apply to it exactly as they would to a row the application wrote — and every
  address it writes is under RFC 2606's reserved ``.invalid`` TLD.
* **No route maps a send command's job to its send row.** A *succeeded* job
  reports the send id in its own completion summary and needs none; a *refused*
  one fails before it can report anything, so the refusal record in step 21 is
  reached by the same database read the review items use.
* **The one-click unsubscribe token cannot be read from outside the worker.**
  It is minted at delivery and handed to the provider, which on this appliance
  holds it in a container's memory. Step 21 therefore records the suppression
  directly rather than following a link it cannot see; ``POST /v1/unsubscribe``
  itself is covered by ``tests/contract/test_outreach.py``.
* **The portal pages fetch ``/api/portals/*``**, a backend that does not exist
  in this repository. Not exercised, and not faked.

The steps run in definition order and share :class:`~conftest.ClickThrough`.
A step whose predecessor did not run skips naming that predecessor rather than
failing a second time for the same cause.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

import httpx
import pytest

# Plain `conftest`, not `.conftest`: `tests/` carries no `__init__.py` anywhere,
# and pytest's rootdir insertion is what makes this resolve — the same import
# tests/integration/test_import_rows.py already uses.
from conftest import (
    POLL_ATTEMPTS,
    SCORE_LABEL,
    UNIT_PATH,
    ClickThrough,
    json_body,
    poll_until,
    psql_scalar,
)

pytestmark = pytest.mark.e2e

#: The G1 presentation rule: a shortlist is 2-3 speakers, never one and never
#: ten. Restated from the ratified rules so a drift in the API fails here.
MIN_SPEAKERS = 2
MAX_SPEAKERS = 3

#: A per-session tag, so this module's rows are always distinguishable from the
#: `seed-review` demo queue and from a previous run's leftovers. Every row name
#: below carries it, and every lookup narrows by it.
RUN_TAG = uuid.uuid4().hex[:8]

#: Obviously fictional, synthetic, and spelled against the ratified
#: `professionals` columns in docs/pilot-data/columns.yaml (`name` and
#: `metro_region` both required).
ACCEPT_ROW_NAME = f"E2E Accept {RUN_TAG}"
REJECT_ROW_NAME = f"E2E Reject {RUN_TAG}"

#: RFC 2606 reserves ``.invalid``: it cannot resolve, and no mailbox can exist
#: behind it. Per-session, so this module's contact is never a previous run's.
OUTREACH_ADDRESS = f"e2e-outreach-{RUN_TAG}@synthetic.invalid"

#: One of the three shipped templates. There is no request field that carries
#: message text, which is what keeps unreviewed copy out of the send path.
OUTREACH_TEMPLATE_ID = "pilot.event_invitation.v1"

#: Obviously fictional placeholder values, matching the template's declared set.
OUTREACH_VALUES = {
    "professional_name": f"E2E Professional {RUN_TAG}",
    "unit_name": "Northside Robotics",
    "event_name": "Spring Showcase",
    "event_date": "Friday, 12 June",
    "coordinator_name": "E2E Coordinator",
}


# ---------------------------------------------------------------------------
# Helpers — every wait below is bounded and reports what it saw.
# ---------------------------------------------------------------------------


def _metric(api: httpx.Client, unit_id: str, name: str) -> int | None:
    """Read one metric from its owning route (ADR-0011 rule 4), never recomputed.

    Returns ``None`` for an unknown value. It does not fall back to 0, because
    that substitution is the exact defect this suite exists to catch.
    """
    body = json_body(api.get(f"/v1/units/{unit_id}/metrics"))
    for metric in body["metrics"]:
        if metric["name"] == name:
            value = metric["value"]
            assert value is None or isinstance(value, int), (
                f"metric {name!r} carried a {type(value).__name__}, expected an int or null"
            )
            return value
    raise AssertionError(f"no metric named {name!r} on GET /v1/units/{unit_id}/metrics")


def _await_job(api: httpx.Client, job_id: str) -> dict[str, Any]:
    """Poll one job to a terminal state, then return its completion summary.

    Bounded, and it reports each observed status. A job that never settles is a
    failure here rather than a longer sleep somewhere else.
    """
    seen: dict[str, str] = {}

    def settled() -> bool:
        status = json_body(api.get(f"/v1/jobs/{job_id}"))["status"]
        seen["status"] = status
        return status in {"succeeded", "failed", "abandoned"}

    assert poll_until(f"job {job_id} settles", settled, attempts=POLL_ATTEMPTS, interval=1.0), (
        f"job {job_id} never left status {seen.get('status')!r}"
    )
    assert seen["status"] == "succeeded", (
        f"job {job_id} finished {seen['status']!r}, not 'succeeded'"
    )

    # The job's own event stream, which is where `events_url` points. The
    # terminal `job.completed` payload carries the summary; nothing is inferred
    # from the 202 the submission returned.
    stream = api.get(f"/v1/jobs/{job_id}/events").text
    for line in stream.splitlines():
        if not line.startswith("data: "):
            continue
        payload = json.loads(line.removeprefix("data: "))["payload"]
        if payload.get("type") == "job.completed":
            summary = payload["summary"]
            assert isinstance(summary, dict)
            return summary
    raise AssertionError(
        f"job {job_id} reported 'succeeded' but its event stream carried no summary"
    )


def _submit_import(
    api: httpx.Client,
    unit_id: str,
    *,
    dataset: str,
    dry_run: bool,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Submit one inline import and return the completed job's summary."""
    response = api.post(
        f"/v1/units/{unit_id}/imports",
        json={"dataset": dataset, "dry_run": dry_run, "rows": rows},
        # A fresh de-duplication id per submission. It authenticates nothing.
        headers={"Idempotency-Key": f"e2e-{RUN_TAG}-{uuid.uuid4().hex}"},
    )
    assert response.status_code == 202, (
        f"POST /v1/units/{unit_id}/imports returned {response.status_code}, "
        f"expected 202: {response.text[:400]}"
    )
    return _await_job(api, json_body(response)["job_id"])


def _pending_item_id(unit_id: str, name: str) -> str:
    """The pending review item carrying *name*, read from the database.

    Read from the database and not from the API because **the API has no route
    that lists review items** — see this module's docstring. This is a recorded
    gap, not a shortcut.
    """
    return psql_scalar(
        f"""
        select ri.id
          from review_item ri
          join import_batch ib
            on ib.tenant_id = ri.tenant_id and ib.id = ri.import_batch_id
         where ib.owning_unit_id = '{unit_id}'
           and ri.status = 'pending'
           and ri.row_data->>'name' = '{name}'
         limit 1
        """
    )


#: The released taxonomy versions the CBA factors score against, restated here
#: for the reason ``SCORE_LABEL`` and ``MIN_SPEAKERS`` are: this module writes
#: ``speaker_profile`` rows directly, and a classification stamped with a
#: version the API no longer scores against is *excluded* rather than silently
#: rescored. Drift therefore fails loudly here, naming the version, instead of
#: quietly changing what these steps prove.
INDUSTRY_TAXONOMY_VERSION = "cba-naics-2026-09-04"
ROLE_TAXONOMY_VERSION = "cba-roles-2026-09-04"

#: The Speaker Request's targets. One sector and one role, so each factor is the
#: two-valued comparison customer sections 7-8 describe and a candidate's score
#: is readable by eye.
REQUESTED_SECTOR = "52"
REQUESTED_ROLE = "finance"

#: Populated by :func:`_seed_match_fixtures` on first use: the Speaker Request's
#: event id, and each seeded speaker's ``professional_id`` by nickname. Module
#: state rather than a new ``ClickThrough`` field, so this module's rework does
#: not reach into ``tests/e2e/conftest.py``, which every other step shares.
_MATCH_FIXTURE: dict[str, Any] = {}


def _seed_speaker(
    unit_id: str,
    *,
    nickname: str,
    industry_code: str,
    role_code: str,
    source: str,
    topic_text: str | None,
) -> str:
    """Create one professional and their ``speaker_profile``, returning its id.

    Written through the database for the same reason ``_seed_contact_channel``
    is: **this appliance's seed creates no speaker profiles**, and the customer
    section 13 contact surface is another card's route whose failure would
    surface here as a match-run failure. Nothing is faked — the row goes in
    through the shipped schema, so ``ck_speaker_profile_industry_provenance``
    and the two closed code vocabularies are enforced on it exactly as they
    would be on a row the application wrote.

    The id is whatever the database generated, and it is never derived from
    ``nickname``: OQ-CBA-017 is re-keying ``professional_id`` to an opaque
    generated id, and a test that computed one from a name would be asserting
    the property that decision removes.

    ``industry_classified_by_user_id`` is left NULL even on a ``human`` row —
    migration 0028's third arm permits exactly that, and this appliance has no
    Speaker Connector account this step is entitled to name as the reviewer.
    """
    topic_sql = "null" if topic_text is None else f"'{topic_text}'"
    return psql_scalar(
        f"""
        with acct as (
            insert into user_account (id, tenant_id, external_subject, email)
            select gen_random_uuid(), tenant_id,
                   'e2e-speaker-{RUN_TAG}-{nickname}',
                   'e2e-speaker-{RUN_TAG}-{nickname}@example.invalid'
              from org_unit where id = '{unit_id}'
            returning id, tenant_id
        ), profile as (
            insert into speaker_profile (
                tenant_id, professional_id, owning_unit_id, full_name,
                primary_industry_code, industry_taxonomy_version,
                primary_role_code, role_taxonomy_version, topic_text,
                industry_classification_source, industry_classified_at,
                role_classification_source, role_classified_at
            )
            select tenant_id, id, '{unit_id}', 'E2E Speaker {nickname} {RUN_TAG}',
                   '{industry_code}', '{INDUSTRY_TAXONOMY_VERSION}',
                   '{role_code}', '{ROLE_TAXONOMY_VERSION}', {topic_sql},
                   '{source}', now(), '{source}', now()
              from acct
            returning professional_id
        )
        select professional_id from profile
        """
    )


def _seed_match_fixtures(unit_id: str) -> dict[str, Any]:
    """File one virtual Speaker Request and five speakers, once per session.

    Virtual on purpose, and not a limitation of the test: customer section 11
    removes Proximity from the virtual model, so ``cba-virtual-1`` scores on
    these speakers' evidence alone. None of them has a postal code on file, and
    that is deliberate — step 09b runs the *physical* model over this same
    roster to prove that a speaker nobody has located is excluded and reported
    rather than shortlisted at a distance nobody measured.

    Each speaker exists to make one distinction visible through the appliance:

    * ``strong``   — sector and role both match, no topic text. Customer section
      9's observed absence, so its topic factor is a stated policy value rather
      than an unknown, and the candidate is shortlistable.
    * ``mid``      — sector matches, role does not.
    * ``weak``     — neither matches. The knob step 10 turns.
    * ``unknown``  — both match, but topic text is on file and the fixture topic
      provider holds no recorded comparison for it, so the comparison is an
      unknown rather than a guess (OQ-CBA-026). Unscorable.
    * ``proposal`` — both codes present but ``inferred``. Customer section 19
      orders review before availability, so this contact is absent from the pool
      entirely rather than ranked last in it.
    """
    if _MATCH_FIXTURE:
        return _MATCH_FIXTURE

    title = f"E2E virtual finance panel {RUN_TAG}"
    event_id = psql_scalar(
        f"""
        with created as (
            insert into event (
                id, tenant_id, host_org_unit_id, title, normalized_title, description,
                time_precision, on_date, time_zone, resolved_date, origin, is_virtual
            )
            select gen_random_uuid(), tenant_id, '{unit_id}', '{title}', lower('{title}'),
                   'A panel on how finance teams evaluate analytics investments.',
                   'date_only', date '2027-03-04', 'America/Los_Angeles',
                   date '2027-03-04', 'coordinator_entry', true
              from org_unit where id = '{unit_id}'
            returning id
        )
        select id from created
        """
    )
    for kind, code, version in (
        ("industry", REQUESTED_SECTOR, INDUSTRY_TAXONOMY_VERSION),
        ("role", REQUESTED_ROLE, ROLE_TAXONOMY_VERSION),
    ):
        psql_scalar(
            f"""
            insert into speaker_request_classification
                (id, tenant_id, event_id, kind, code, taxonomy_version)
            select gen_random_uuid(), tenant_id, '{event_id}', '{kind}', '{code}', '{version}'
              from org_unit where id = '{unit_id}'
            """
        )

    speakers = {
        nickname: _seed_speaker(
            unit_id,
            nickname=nickname,
            industry_code=industry,
            role_code=role,
            source=source,
            topic_text=topic,
        )
        for nickname, industry, role, source, topic in (
            ("strong", REQUESTED_SECTOR, REQUESTED_ROLE, "human", None),
            ("mid", REQUESTED_SECTOR, "marketing", "human", None),
            ("weak", "11", "marketing", "human", None),
            (
                "unknown",
                REQUESTED_SECTOR,
                REQUESTED_ROLE,
                "human",
                "Twelve years of treasury analytics and forecasting.",
            ),
            ("proposal", REQUESTED_SECTOR, REQUESTED_ROLE, "inferred", None),
        )
    }

    _MATCH_FIXTURE.update({"event_id": event_id, "speakers": speakers})
    return _MATCH_FIXTURE


def _submit_match_run(api: httpx.Client, unit_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Submit one match run and return (acknowledgement, the persisted run).

    The body carries **no evidence** — a Speaker Request id, a shortlist size, a
    seed and five subject ids. Everything scored is read server-side off the
    rows seeded above, which is OQ-CBA-031's whole point: a client naming a
    speaker cannot also state what that speaker is like.
    """
    fixture = _seed_match_fixtures(unit_id)
    body = {
        "speaker_request_id": fixture["event_id"],
        "portfolio_size": MIN_SPEAKERS,
        "random_seed": 7,
        "candidate_subject_ids": list(fixture["speakers"].values()),
    }
    response = api.post(
        f"/v1/units/{unit_id}/match-runs",
        json=body,
        headers={"Idempotency-Key": f"e2e-match-{RUN_TAG}-{uuid.uuid4().hex}"},
    )
    if response.status_code == 503 and "registry_not_ready" in response.text:
        pytest.skip(
            "match scoring is unavailable: the API answered 503 registry_not_ready, "
            "so the factor registry is not approved or not fully implemented on this "
            f"appliance — {response.text[:200]}"
        )
    assert response.status_code == 202, (
        f"POST /v1/units/{unit_id}/match-runs returned {response.status_code}, "
        f"expected 202: {response.text[:400]}"
    )
    accepted = json_body(response)

    summary = _await_job(api, accepted["job_id"])
    match_run_id = summary["match_run_id"]
    run = json_body(api.get(f"/v1/units/{unit_id}/match-runs/{match_run_id}"))
    return accepted, run


def _by_nickname(unit_id: str, run: dict[str, Any]) -> dict[str, float | None]:
    """Every seeded speaker's score, keyed by the nickname this file uses.

    The wire carries opaque ``professional_id`` values, which is correct and
    unreadable; this translates them back so an assertion can say "strong
    outscored weak" rather than comparing two UUIDs.
    """
    scores = _scores(run)
    speakers = _seed_match_fixtures(unit_id)["speakers"]
    return {nickname: scores.get(pid) for nickname, pid in speakers.items()}


def _scores(run: dict[str, Any]) -> dict[str, float | None]:
    """Every candidate's score in one mapping, shortlisted or not."""
    return {
        candidate["subject_id"]: candidate["heuristic_score"]
        for group in ("shortlist", "considered", "unscorable")
        for candidate in run[group]
    }


# ---------------------------------------------------------------------------
# Step 1-3 — fixture auth, and the role the server assigns
# ---------------------------------------------------------------------------


def test_01_an_unauthenticated_call_is_refused(api: httpx.Client) -> None:
    """The fixture bearer is doing real work, not decorating an open API.

    There is no real sign-in in this repository, so the compose dev token is
    the only path to a principal. That makes it worth proving the token is what
    admits the caller: without it, ``/v1/me`` refuses.
    """
    anonymous = api.get("/v1/me", headers={"Authorization": ""})
    assert anonymous.status_code in {401, 403}, (
        f"GET /v1/me answered {anonymous.status_code} with no bearer; the API is "
        f"not authenticating at all: {anonymous.text[:300]}"
    )


def test_02_the_role_is_resolved_from_me(api: httpx.Client, flow: ClickThrough) -> None:
    """The caller learns who it is by asking. It never asserts who it is.

    Everything downstream reads ``flow.role`` and ``flow.unit_id`` from this
    response. No test in this module sends a role, a tenant, an actor or a unit
    in a request body — the caller-supplied-identity pattern archived as
    MM-A01.
    """
    me = json_body(api.get("/v1/me"))

    assert me["email"], "GET /v1/me carried no email"
    assert me["suspended"] is False, "the compose principal is suspended"

    memberships = me["memberships"]
    assert memberships, f"the principal {me['email']} holds no memberships at all"

    for membership in memberships:
        if membership["org_unit_path"] == UNIT_PATH and membership["is_active"]:
            flow.role = membership["role"]
            break
    assert flow.role is not None, (
        f"no active membership on '{UNIT_PATH}' in {memberships!r}; the seeded "
        "principal cannot act on the pilot unit"
    )

    flow.email = me["email"]
    # Read from the database for the same reason the review item ids are: no
    # `/v1` route maps a unit path to a unit id, so /v1/me names the path and
    # nothing resolves it. Recorded, not worked around silently.
    flow.unit_id = psql_scalar(f"select id from org_unit where path = '{UNIT_PATH}'")
    assert flow.unit_id, f"no org unit at path '{UNIT_PATH}'"

    print(f"  server-assigned role on '{UNIT_PATH}': {flow.role} (as {flow.email})")


def test_03_the_caller_cannot_choose_its_own_role(api: httpx.Client, flow: ClickThrough) -> None:
    """Proof the role came from the server, not from the request.

    If a role were caller-selectable, this principal could simply ask to be a
    student and read the rewards catalog. It cannot: the catalog is gated on
    ``student`` alone and this principal is a coordinator, so the honest
    outcome is a 403 with ``no_grant``. A 200 here would mean either the gate
    is gone or the role is negotiable, and both are failures.
    """
    if flow.unit_id is None:
        pytest.skip("step 02 did not resolve a unit id from GET /v1/me")

    response = api.get(f"/v1/units/{flow.unit_id}/rewards")
    assert response.status_code == 403, (
        f"the student-gated rewards catalog answered {response.status_code} to a "
        f"'{flow.role}' principal. Deny-by-default authorization means this must be "
        f"a refusal until the D6 role decision widens it: {response.text[:300]}"
    )
    assert json_body(response)["error"]["code"] == "forbidden"


#: The four pre-loaded principals, keyed by the fixture that carries each one's
#: bearer, and what ``GET /v1/me/portals`` must say about it. Written out here
#: rather than derived from the response, because a table built from the answer
#: would agree with any answer: what is being asserted is that the appliance
#: seeds *these four* and that each opens *exactly one* portal.
#:
#: The stored role and the portal id are the server's own strings
#: (``routers/portals.py::_PORTAL_FOR_ROLE``). The display names are deliberately
#: not restated — ``smartmatch_domain.role_presentation`` owns that map, and a
#: second copy here would be a second place for a label to drift.
_PORTAL_PRINCIPALS: dict[str, tuple[str, str, str]] = {
    # fixture name -> (stored role, portal id, frontend home path)
    "api": ("coordinator", "coordinator", "/coordinator-portal"),
    "student_api": ("student", "student", "/student-portal"),
    "host_api": ("volunteer", "volunteer", "/volunteer-portal"),
    "admin_api": ("admin", "admin", "/dashboard"),
}


@pytest.mark.parametrize("fixture_name", sorted(_PORTAL_PRINCIPALS))
def test_03b_every_portal_type_has_a_principal_that_opens_it_and_no_other(
    fixture_name: str, request: pytest.FixtureRequest
) -> None:
    """A stakeholder can enter every portal, and each principal enters one.

    This is the step the pre-loaded principal set exists for. Before it the
    appliance mapped one bearer to one coordinator, so three of the four portals
    could not be opened at all and several steps below skipped saying so.

    Both halves are asserted on purpose. That each portal *has* a principal is
    the deliverable; that each principal has *only its own* portal is what keeps
    the deliverable from having been bought by widening something. Four
    single-membership accounts are four identities, not one identity with four
    roles, and ``GET /v1/me/portals`` reports what the server read from
    ``membership`` rows rather than anything a client sent.

    ``home_path`` is asserted because it is the server's answer to "where does
    this shell live": the frontend navigates to a portal it was granted rather
    than deriving a path from a role it read for itself.
    """
    expected_role, expected_portal, expected_home = _PORTAL_PRINCIPALS[fixture_name]
    client: httpx.Client = request.getfixturevalue(fixture_name)

    body = json_body(client.get("/v1/me/portals"))
    portals = body["portals"]

    assert len(portals) == 1, (
        f"the {expected_role!r} principal was handed {len(portals)} portals "
        f"({[entry['portal'] for entry in portals]}). Each pilot principal holds "
        "one membership carrying one role; more than one portal here would mean "
        "a role set or a membership had been widened to make a click work"
    )
    descriptor = portals[0]
    assert descriptor["role"] == expected_role, (
        f"the portal was opened by the stored role {descriptor['role']!r}, not "
        f"{expected_role!r}; the seeded membership is not the one this token is "
        "documented to resolve to"
    )
    assert descriptor["portal"] == expected_portal
    assert descriptor["home_path"] == expected_home
    assert body["default_portal"] == expected_portal, (
        f"default_portal is {body['default_portal']!r}; it must name a portal "
        "already in the list, never a suggestion of one that is not"
    )
    assert descriptor["org_unit_path"] == UNIT_PATH
    assert descriptor["units"], (
        "the granting membership resolved to no org unit rows, so the portal "
        "carries no unit_id that any unit-scoped route could be called with"
    )
    assert descriptor["default_unit_id"] == descriptor["units"][0]["unit_id"]

    print(
        f"  {expected_role}: {descriptor['display_name']!r} at "
        f"{descriptor['home_path']} over '{descriptor['org_unit_path']}'"
    )


# ---------------------------------------------------------------------------
# Step 4 — the columns.yaml import contract
# ---------------------------------------------------------------------------


def test_04_the_columns_yaml_contract_is_enforced_on_import(
    api: httpx.Client, flow: ClickThrough
) -> None:
    """A row that breaks the ratified column contract is reported, not accepted.

    ``docs/pilot-data/columns.yaml`` declares ``name`` and ``metro_region`` as
    required for ``professionals``. This submits a row missing one of them and
    carrying a column the contract does not know, as a ``dry_run``, and asserts
    both findings come back named — an ``error`` for the absence and a
    ``warning`` for the ignored column — with ``usable`` false and no review
    item created.

    A silent acceptance here is the legacy defect the contract exists to close:
    a coordinator would be told their import worked and find nothing in the
    queue.
    """
    if flow.unit_id is None:
        pytest.skip("step 02 did not resolve a unit id from GET /v1/me")

    summary = _submit_import(
        api,
        flow.unit_id,
        dataset="professionals",
        dry_run=True,
        rows=[{"name": f"E2E Contract {RUN_TAG}", "favourite_colour": "green"}],
    )

    assert summary["usable"] is False, (
        f"a row missing the required 'metro_region' column was reported usable: {summary}"
    )
    assert summary["review_items_created"] == 0, (
        f"a dry run created review items: {summary['review_items_created']}"
    )

    findings = {finding["code"]: finding for finding in summary["findings"]}
    assert "missing_required_columns" in findings, (
        f"no 'missing_required_columns' finding for an absent required column: {summary}"
    )
    assert findings["missing_required_columns"]["severity"] == "error"
    assert "metro_region" in findings["missing_required_columns"]["columns"]

    assert "unexpected_columns" in findings, (
        f"a column outside the contract was accepted without a finding: {summary}"
    )
    assert findings["unexpected_columns"]["severity"] == "warning"
    assert "favourite_colour" in findings["unexpected_columns"]["columns"]

    print(f"  contract findings: {sorted(findings)}")


# ---------------------------------------------------------------------------
# Step 5-7 — a live import, then the accept and the reject
# ---------------------------------------------------------------------------


def test_05_a_live_import_reaches_the_review_queue(api: httpx.Client, flow: ClickThrough) -> None:
    """Two contract-clean rows, dispatched to review by the scheduler.

    There is no manual dispatch call anywhere in this module. The count is
    asserted as a measured change from a baseline captured immediately before
    the submission, so a stack already carrying items from an earlier run is
    still a valid starting point — and so the assertion cannot be satisfied by
    a queue that was already there.
    """
    if flow.unit_id is None:
        pytest.skip("step 02 did not resolve a unit id from GET /v1/me")

    baseline = _metric(api, flow.unit_id, "pending_review_items")
    assert baseline is not None, (
        "pending_review_items is unknown on this appliance, so no change in it can be measured"
    )
    flow.baseline_pending = baseline
    print(f"  baseline pending_review_items={baseline}")

    summary = _submit_import(
        api,
        flow.unit_id,
        dataset="professionals",
        dry_run=False,
        rows=[
            {"name": ACCEPT_ROW_NAME, "metro_region": "Portland"},
            {"name": REJECT_ROW_NAME, "metro_region": "Portland"},
        ],
    )
    assert summary["usable"] is True, f"the contract-clean rows were reported unusable: {summary}"

    target = baseline + 2
    assert poll_until(
        f"pending_review_items reaches {target}",
        lambda: _metric(api, flow.unit_id or "", "pending_review_items") == target,
        attempts=POLL_ATTEMPTS,
        interval=1.0,
    ), (
        f"expected pending_review_items == {target} after a two-row import, got "
        f"{_metric(api, flow.unit_id, 'pending_review_items')}; the scheduler "
        "sidecar is not driving the queued import to completion"
    )

    flow.accepted_item_id = _pending_item_id(flow.unit_id, ACCEPT_ROW_NAME)
    flow.rejected_item_id = _pending_item_id(flow.unit_id, REJECT_ROW_NAME)
    assert flow.accepted_item_id, f"no pending review item named {ACCEPT_ROW_NAME!r}"
    assert flow.rejected_item_id, f"no pending review item named {REJECT_ROW_NAME!r}"


def test_06_a_coordinator_accepts_a_review_item(api: httpx.Client, flow: ClickThrough) -> None:
    """The accept half of the decision. 200, and the status it reports back."""
    if flow.accepted_item_id is None:
        pytest.skip("step 05 did not produce a pending review item to accept")

    response = api.post(
        f"/v1/review-items/{flow.accepted_item_id}/decision",
        json={"decision": "accepted"},
    )
    assert response.status_code == 200, (
        f"the accept decision returned {response.status_code}: {response.text[:400]}"
    )
    body = json_body(response)
    assert body["status"] == "accepted", f"the accept reported status {body['status']!r}"
    assert body["decided_at"], "the accept carried no decided_at"


def test_07_a_coordinator_rejects_a_review_item(api: httpx.Client, flow: ClickThrough) -> None:
    """The reject half — the one ``compose_smoke.sh`` never exercises.

    An accept that works says nothing about a reject: they are different
    branches, and the reject branch is the one that must *not* provision
    anything downstream. The metric read in step 08 is what shows it removed
    the item from the queue all the same.
    """
    if flow.rejected_item_id is None:
        pytest.skip("step 05 did not produce a pending review item to reject")

    response = api.post(
        f"/v1/review-items/{flow.rejected_item_id}/decision",
        json={"decision": "rejected"},
    )
    assert response.status_code == 200, (
        f"the reject decision returned {response.status_code}: {response.text[:400]}"
    )
    body = json_body(response)
    assert body["status"] == "rejected", f"the reject reported status {body['status']!r}"

    # A decided item is decided. A second decision on it must not silently
    # succeed and re-run whatever the first one did.
    repeat = api.post(
        f"/v1/review-items/{flow.rejected_item_id}/decision",
        json={"decision": "accepted"},
    )
    assert repeat.status_code == 409, (
        f"re-deciding an already-decided review item returned {repeat.status_code}, "
        f"expected 409: {repeat.text[:300]}"
    )


# ---------------------------------------------------------------------------
# Step 8 — the metrics read, and the drill-down behind it
# ---------------------------------------------------------------------------


def test_08_metrics_reflect_both_decisions(api: httpx.Client, flow: ClickThrough) -> None:
    """Both decisions clear the queue, and the count comes from its owning route.

    Two items in, two decided — one accepted, one rejected — so the queue is
    back to the baseline. Read from ``GET /v1/units/{id}/metrics``, never
    recomputed here (ADR-0011 rule 4).
    """
    if flow.baseline_pending is None or flow.unit_id is None:
        pytest.skip("step 05 did not establish a pending_review_items baseline")

    baseline = flow.baseline_pending
    assert poll_until(
        f"pending_review_items returns to {baseline}",
        lambda: _metric(api, flow.unit_id or "", "pending_review_items") == baseline,
        attempts=POLL_ATTEMPTS,
        interval=1.0,
    ), (
        f"expected pending_review_items back to {baseline} after one accept and "
        f"one reject, got {_metric(api, flow.unit_id, 'pending_review_items')}"
    )


def test_08b_an_unknown_metric_is_null_and_carries_its_reason(
    api: httpx.Client, flow: ClickThrough
) -> None:
    """No metric may present an unknown as a zero (ADR-0011).

    The contract is asserted over every registered metric: a null value must be
    accompanied by a reason, and a measured value must be an integer. The two
    cannot be told apart by a reader who is handed a bare 0, which is why the
    API is required to keep them distinct rather than merged.
    """
    if flow.unit_id is None:
        pytest.skip("step 02 did not resolve a unit id from GET /v1/me")

    metrics = json_body(api.get(f"/v1/units/{flow.unit_id}/metrics"))["metrics"]
    assert metrics, "the metrics route returned no registered metrics at all"

    unknown = [metric for metric in metrics if metric["value"] is None]
    for metric in metrics:
        if metric["value"] is None:
            assert metric["unknown_reason"], (
                f"metric {metric['name']!r} is unknown but says nothing about why; "
                "an unaccountable null is as opaque as a fabricated zero"
            )
        else:
            assert isinstance(metric["value"], int), (
                f"metric {metric['name']!r} carried a non-integer value {metric['value']!r}"
            )
            assert metric["unknown_reason"] is None, (
                f"metric {metric['name']!r} reported both a value and an unknown_reason"
            )

    if not unknown:
        # Stated out loud rather than passed over: the null branch of the
        # contract was not exercised because this appliance happens to have an
        # evidence source for every registered metric.
        print(
            "  every registered metric is measured on this appliance; the "
            "unknown-value branch was checked for shape only, not observed"
        )


def test_08c_a_metric_drill_down_shows_the_rows_behind_the_number(
    api: httpx.Client, flow: ClickThrough
) -> None:
    """The aggregate is backed by rows a coordinator can actually see.

    A count nobody can drill into is a count nobody can check. This asserts the
    drill-down's own aggregate agrees with the listing route's, and that the
    rows it returns actually number that many — which is what makes the figure
    evidence rather than an assertion.
    """
    if flow.unit_id is None:
        pytest.skip("step 02 did not resolve a unit id from GET /v1/me")

    listed = _metric(api, flow.unit_id, "pending_review_items")
    drill = json_body(api.get(f"/v1/units/{flow.unit_id}/metrics/pending_review_items/drill-down"))

    assert drill["aggregate_value"] == listed, (
        f"the drill-down reports {drill['aggregate_value']} but the metrics listing "
        f"reports {listed} for the same metric"
    )
    if drill["aggregate_value"] is None:
        assert drill["unknown_reason"], "an unknown aggregate carried no reason"
        assert drill["rows"] == [], "an unknown aggregate returned rows anyway"
    else:
        assert len(drill["rows"]) == drill["aggregate_value"], (
            f"the drill-down claims {drill['aggregate_value']} but returned "
            f"{len(drill['rows'])} rows"
        )


# ---------------------------------------------------------------------------
# Step 9-12 — the match run, and the honesty properties on it
# ---------------------------------------------------------------------------


def test_09_match_run_scores_are_computed(api: httpx.Client, flow: ClickThrough) -> None:
    """A submitted pool is scored, shortlisted, and explained factor by factor.

    Six things a mock would not do, asserted together:

    * the scores are not all the same value;
    * they order by evidence — the speaker whose stored sector and role both
      match the request outscores the one whose record matches neither;
    * the run is produced under the CBA registry in the virtual model, which is
      the surface OQ-CBA-031 built and the thing no client could reach before;
    * a contact whose classifications are still a machine's proposal is absent
      from the pool with a reason, not ranked last in it;
    * every score carries the registry version it was produced under; and
    * every factor names its own basis, so the number can be argued with.
    """
    if flow.unit_id is None:
        pytest.skip("step 02 did not resolve a unit id from GET /v1/me")

    accepted, run = _submit_match_run(api, flow.unit_id)
    flow.match_run_id = run["id"]

    assert accepted["registry_version"], "the acknowledgement named no registry version"
    assert accepted["scoring_mode"] == "cba-virtual-1", (
        "the run was not scored under the virtual CBA model; the appliance "
        f"reported scoring_mode={accepted.get('scoring_mode')!r}"
    )
    assert accepted["scoring_mode_version"], (
        "a run naming a scoring mode must name the vocabulary version too; the "
        "two are set together or not at all"
    )
    assert accepted["scored_candidates"] == 3, (
        f"expected 3 scorable candidates, got {accepted['scored_candidates']}"
    )
    assert accepted["unscorable_candidates"] == 1, (
        "the speaker whose topic evidence could not be compared should be "
        f"reported unscorable, not scored: {accepted}"
    )

    proposal_id = _seed_match_fixtures(flow.unit_id)["speakers"]["proposal"]
    excluded = {entry["subject_id"]: entry["reason"] for entry in accepted["excluded_candidates"]}
    assert excluded.get(proposal_id) == "industry_classification_awaiting_review", (
        "a contact whose classifications are still a proposal must be absent "
        f"from the pool with its reason; the API reported {excluded!r}"
    )
    assert proposal_id not in _scores(run), (
        "an unreviewed contact was scored rather than held out of the pool; "
        "review comes before availability (customer section 19)"
    )

    assert run["portfolio_status"] in {"optimal", "feasible"}, (
        f"the solver reported portfolio_status={run['portfolio_status']!r}"
    )
    assert MIN_SPEAKERS <= len(run["shortlist"]) <= MAX_SPEAKERS, (
        f"the shortlist holds {len(run['shortlist'])} speakers; the ratified G1 "
        f"presentation rule is {MIN_SPEAKERS}-{MAX_SPEAKERS}"
    )
    assert run["shortlist_available"] is True, (
        f"the shortlist could not be reconstructed: {run['shortlist_unavailable_reason']}"
    )

    scores = _by_nickname(flow.unit_id, run)
    measured = {name: value for name, value in scores.items() if value is not None}
    assert len(set(measured.values())) > 1, (
        f"every scored candidate got the identical score {measured}; that is a "
        "constant, not a computation"
    )
    assert measured["strong"] > measured["mid"] > measured["weak"], (
        "the ranking does not follow the stored evidence — sector-and-role "
        f"{measured['strong']}, sector-only {measured['mid']}, neither "
        f"{measured['weak']}"
    )

    for group in ("shortlist", "considered", "unscorable"):
        for candidate in run[group]:
            assert candidate["registry_version"] == run["registry_version"], (
                f"{candidate['subject_id']} was scored under registry "
                f"{candidate['registry_version']} but the run reports "
                f"{run['registry_version']}"
            )
            assert candidate["factors"], f"{candidate['subject_id']} carried no factors"
            for factor in candidate["factors"]:
                assert factor["basis"], (
                    f"factor {factor['factor_key']} on {candidate['subject_id']} gives "
                    "no basis for its value; an unarguable number is not an explanation"
                )

    print(f"  scores: {scores}")


def test_09b_a_physical_run_excludes_the_speakers_nobody_has_located(
    api: httpx.Client, flow: ClickThrough
) -> None:
    """The physical model runs now, and it still refuses to invent a distance.

    Customer section 10 measures Proximity in miles from the CPP campus.
    OQ-CBA-024 shipped the static offline ZIP-centroid table that resolves a
    stored postal code, so this appliance no longer answers a physical Speaker
    Request with ``match_run_physical_scoring_unavailable``.

    What it still will not do is guess. **None of these seeded speakers has a
    postal code on file**, so every distance is unknown; under
    ``cba-physical-1`` an unknown factor makes the composite unknown, and a
    candidate with no composite is excluded from the pool and reported rather
    than entered at ``0.0`` and sorted last. With nobody left to shortlist, the
    run is refused — and the refusal now names a gap in *this tenant's records*,
    which a Speaker Connector can close by recording an address, rather than a
    capability the deployment lacks.

    The distinction is the whole point. Both answers are an error to a client,
    and only one of them tells the truth about why.
    """
    if flow.unit_id is None:
        pytest.skip("step 02 did not resolve a unit id from GET /v1/me")

    title = f"E2E on-campus finance panel {RUN_TAG}"
    physical_request_id = psql_scalar(
        f"""
        with created as (
            insert into event (
                id, tenant_id, host_org_unit_id, title, normalized_title, description,
                time_precision, on_date, time_zone, resolved_date, origin,
                is_virtual, location_city
            )
            select gen_random_uuid(), tenant_id, '{flow.unit_id}', '{title}', lower('{title}'),
                   'A panel on how finance teams evaluate analytics investments.',
                   'date_only', date '2027-03-05', 'America/Los_Angeles',
                   date '2027-03-05', 'coordinator_entry', false, 'Pomona'
              from org_unit where id = '{flow.unit_id}'
            returning id
        )
        select id from created
        """
    )
    fixture = _seed_match_fixtures(flow.unit_id)

    response = api.post(
        f"/v1/units/{flow.unit_id}/match-runs",
        json={
            "speaker_request_id": physical_request_id,
            "portfolio_size": MIN_SPEAKERS,
            "random_seed": 7,
            "candidate_subject_ids": list(fixture["speakers"].values()),
        },
        headers={"Idempotency-Key": f"e2e-physical-{RUN_TAG}-{uuid.uuid4().hex}"},
    )

    assert response.status_code != 503, (
        "the appliance still refuses a physical Speaker Request as an "
        "unavailable capability; OQ-CBA-024's ZIP-centroid table has shipped "
        f"and the run should be scored. Body: {response.text[:400]}"
    )
    assert response.status_code == 422, (
        "a physical run over speakers with no postal code on file should be "
        "refused for want of scorable candidates; the appliance answered "
        f"{response.status_code}: {response.text[:400]}"
    )
    error = json_body(response)["error"]
    assert error["code"] == "match_run_insufficient_scorable_candidates", (
        f"the refusal is coded {error['code']!r}, which does not point at the "
        "records a Speaker Connector has to fill in"
    )
    # Nobody was scored at 0.0 to pad the shortlist out to its requested size:
    # every named speaker is accounted for as unscorable or excluded, and none
    # as a low-ranked measurement.
    accounted = int(error["details"]["unscorable_candidates"]) + int(
        error["details"]["excluded_candidates"]
    )
    assert int(error["details"]["scorable_candidates"]) == 0
    assert accounted == len(fixture["speakers"])


def test_10_a_changed_evidence_changes_the_score(api: httpx.Client, flow: ClickThrough) -> None:
    """The strongest anti-mock check: turn one knob, watch that one score move.

    The knob is now the **stored record**, not a request field, which is what
    OQ-CBA-031 changed: ``weak``'s ``primary_industry_code`` is corrected to the
    sector the request targets, exactly as a Speaker Connector correcting a
    classification would. The second run submits the identical body.

    ``weak``'s score must rise, and — because nothing else about the roster
    changed — ``strong``'s must not. A fixture, a canned response, or a score
    derived from anything but the stored evidence fails one half or the other.
    Stronger than the old version of this check, because a caller can no longer
    state the evidence at all: the only way to move a score is to move a row.
    """
    if flow.match_run_id is None:
        pytest.skip("step 09 did not produce a match run to compare against")
    assert flow.unit_id is not None

    first = json_body(api.get(f"/v1/units/{flow.unit_id}/match-runs/{flow.match_run_id}"))

    weak_id = _seed_match_fixtures(flow.unit_id)["speakers"]["weak"]
    psql_scalar(
        f"""
        update speaker_profile
           set primary_industry_code = '{REQUESTED_SECTOR}'
         where professional_id = '{weak_id}'
        """
    )
    _, second = _submit_match_run(api, flow.unit_id)

    before = _by_nickname(flow.unit_id, first)
    after = _by_nickname(flow.unit_id, second)
    assert after["weak"] is not None and before["weak"] is not None
    assert after["weak"] > before["weak"], (
        "correcting a speaker's stored sector to the one the request targets did "
        f"not change their score ({before['weak']} -> {after['weak']}); the score "
        "is not a function of the stored evidence"
    )
    assert after["strong"] == before["strong"], (
        "a speaker whose record did not change scored differently "
        f"({before['strong']} -> {after['strong']}); the score depends on "
        "something other than that speaker's own evidence"
    )
    assert second["id"] != first["id"], "the second run reused the first run's id"


def test_11_no_score_is_presented_as_a_percentage(api: httpx.Client, flow: ClickThrough) -> None:
    """The ratified G1 rule: the label is "heuristic score", never a percentage.

    Three ways a percentage could leak, closed together: the label itself, a
    value above 1.0 that could only be read as a percent, and the word or the
    sign appearing anywhere in the payload.
    """
    if flow.match_run_id is None:
        pytest.skip("step 09 did not produce a match run to inspect")
    assert flow.unit_id is not None

    response = api.get(f"/v1/units/{flow.unit_id}/match-runs/{flow.match_run_id}")
    run = json_body(response)

    assert run["score_label"] == SCORE_LABEL, (
        f"the run is labelled {run['score_label']!r}, not {SCORE_LABEL!r}"
    )
    for group in ("shortlist", "considered", "unscorable"):
        for candidate in run[group]:
            assert candidate["score_label"] == SCORE_LABEL, (
                f"{candidate['subject_id']} is labelled "
                f"{candidate['score_label']!r}, not {SCORE_LABEL!r}"
            )
            score = candidate["heuristic_score"]
            assert score is None or 0.0 <= score <= 1.0, (
                f"{candidate['subject_id']} scored {score}, outside [0.0, 1.0] — "
                "a value in that range can only be read as a percentage"
            )

    offenders = re.findall(r"[^\"]*(?:percent|pct|%)[^\"]*", response.text, flags=re.IGNORECASE)
    assert not offenders, f"the match-run payload spells a score as a percentage: {offenders[:5]}"


def test_12_an_unknown_factor_is_null_and_a_real_zero_is_zero(
    api: httpx.Client, flow: ClickThrough
) -> None:
    """ADR-0011, both halves, in one response.

    ``unknown`` has topic text on file that the fixture provider holds no
    recorded comparison for, so the comparison could not be made: it must come
    back unscorable with a null score and a factor whose state is ``unknown``.
    ``weak``'s sector genuinely is not one the request named: it must come back
    with a real, classified ``measured_zero``.

    A system that renders the first as 0 passes neither assertion, and a system
    that renders the second as unknown fails just as loudly. The whole point is
    that the two are different facts.

    Read against the run step 09 produced, before step 10's correction. That is
    deliberate rather than incidental: the snapshot is immutable and its stored
    explanations are what was actually scored, so correcting a record afterwards
    must not change what an earlier run says about it.
    """
    if flow.match_run_id is None:
        pytest.skip("step 09 did not produce a match run to inspect")
    assert flow.unit_id is not None

    run = json_body(api.get(f"/v1/units/{flow.unit_id}/match-runs/{flow.match_run_id}"))
    speakers = _seed_match_fixtures(flow.unit_id)["speakers"]

    unscorable = {candidate["subject_id"]: candidate for candidate in run["unscorable"]}
    assert speakers["unknown"] in unscorable, (
        "the speaker whose topic evidence could not be compared was scored "
        f"rather than reported unscorable; unscorable holds {sorted(unscorable)}"
    )
    absent = unscorable[speakers["unknown"]]
    assert absent["heuristic_score"] is None, (
        f"a candidate with an unevaluable factor scored {absent['heuristic_score']!r}; "
        "an absence of evidence is never a zero"
    )
    assert absent["state"] == "unknown"
    assert "cba_semantic_topic" in absent["unknown_factor_keys"]

    absent_factor = next(
        factor for factor in absent["factors"] if factor["factor_key"] == "cba_semantic_topic"
    )
    assert absent_factor["state"] == "unknown"
    assert absent_factor["value"] is None, (
        f"the unknown factor carried the value {absent_factor['value']!r} rather than null"
    )
    assert absent_factor["zero_classification"] == "unknown"

    scored = {
        candidate["subject_id"]: candidate
        for group in ("shortlist", "considered")
        for candidate in run[group]
    }
    assert speakers["weak"] in scored, (
        "the speaker whose stored sector simply does not match was not scored; a "
        "mismatch is a measurement, not an absence"
    )
    measured_zero = next(
        factor
        for factor in scored[speakers["weak"]]["factors"]
        if factor["factor_key"] == "industry_match"
    )
    assert measured_zero["state"] == "measured"
    assert measured_zero["value"] == 0.0
    assert measured_zero["zero_classification"] == "measured_zero", (
        "a sector that is classified and simply does not match must be a measured "
        f"zero, not {measured_zero['zero_classification']!r} — otherwise it is "
        "indistinguishable from the unknown above"
    )

    # Proximity is not in the factor list at all: customer section 11 removes it
    # from the virtual model, so there is no number to report and no absence to
    # explain. Absent is a third thing, and this is where it has to be visible.
    for candidate in run["shortlist"] + run["considered"] + run["unscorable"]:
        keys = {factor["factor_key"] for factor in candidate["factors"]}
        assert "cba_proximity" not in keys, (
            f"{candidate['subject_id']} carries a proximity factor under the "
            "virtual model, which scores three factors and not four"
        )


# ---------------------------------------------------------------------------
# Step 13 — events and the tag quarantine
# ---------------------------------------------------------------------------


def test_13_events_and_the_tag_quarantine_are_readable(
    api: httpx.Client, flow: ClickThrough
) -> None:
    """Both coordinator reads answer, and both account for what they withhold.

    On a freshly seeded appliance these listings are empty — the seed imports
    professionals, not events — so this asserts the shape and the accounting
    rather than a populated catalog. That the withheld counters exist at all is
    the point: ADR-0010 and ADR-0012 make an event without a resolved date or
    carrying a quarantined tag unlistable, and a listing that dropped those
    silently would look identical to one with nothing to drop.
    """
    if flow.unit_id is None:
        pytest.skip("step 02 did not resolve a unit id from GET /v1/me")

    events = json_body(api.get(f"/v1/units/{flow.unit_id}/events"))
    assert isinstance(events["events"], list)
    for key in ("withheld_unresolved_date", "withheld_quarantined_tags"):
        assert isinstance(events[key], int), (
            f"the events listing reports {key}={events[key]!r}; a withholding that "
            "is not counted is a silent drop"
        )

    quarantine = json_body(api.get(f"/v1/units/{flow.unit_id}/tag-quarantine"))
    assert isinstance(quarantine["items"], list)
    assert quarantine["current_vocabulary_version"], (
        "the tag quarantine named no vocabulary version, so nothing says which "
        "closed vocabulary these values failed against"
    )

    if not events["events"]:
        print(
            "  the events listing is empty on this appliance: the compose seed "
            "imports professionals, not events, so nothing has reached the "
            "catalog. Shape and withholding accounting checked; a populated "
            "listing was not observed."
        )


# ---------------------------------------------------------------------------
# Step 14-15 — rewards. Gated, and asserted as gated.
# ---------------------------------------------------------------------------


def test_14_the_rewards_catalog_is_a_students_to_read_and_nobody_elses(
    api: httpx.Client, student_api: httpx.Client, flow: ClickThrough
) -> None:
    """The student walks the catalog; the coordinator is still refused it.

    Rewards operations are gated on the ``student`` role alone. This appliance
    now pre-loads a student principal, so the walk that used to skip runs — and
    it runs *without* the gate having moved, which is the half worth asserting.
    The coordinator's ``403`` is checked first for exactly that reason: a step
    that only proved the student could read would pass equally well if the route
    had been opened to everyone.

    What the catalog reports is asserted as a *shape*, not as a number. On a
    freshly seeded appliance nothing has funded a reward and nothing has earned
    a point, so an honest answer is an empty list beside a balance that says
    which kind of nothing it is. ``state`` is carried next to ``points`` for
    ADR-0011's reason — a consumer that had to reconstruct "unknown" from an
    absent number is one ``?? 0`` away from rendering a fabricated zero — and
    this step pins that both are present and agree.

    ``earn_policy_ratified`` is read back rather than expected to be true: D6
    has not ratified an earn policy, and a run that asserted it had would be
    this test claiming a decision the project has not made.
    """
    if flow.unit_id is None:
        pytest.skip("step 02 did not resolve a unit id from GET /v1/me")

    catalog_refused = api.get(f"/v1/units/{flow.unit_id}/rewards")
    assert catalog_refused.status_code == 403, (
        f"the rewards catalog answered {catalog_refused.status_code} to a "
        f"'{flow.role}' principal, not the expected 403. Rewards is gated on "
        f"'student' alone and a wider answer here is a widening: "
        f"{catalog_refused.text[:300]}"
    )
    redemptions_refused = api.get(f"/v1/units/{flow.unit_id}/redemptions")
    assert redemptions_refused.status_code == 403, (
        f"the redemption self-read answered {redemptions_refused.status_code} to "
        f"a '{flow.role}' principal, not the expected 403: "
        f"{redemptions_refused.text[:300]}"
    )

    catalog = student_api.get(f"/v1/units/{flow.unit_id}/rewards")
    assert catalog.status_code == 200, (
        f"the rewards catalog answered {catalog.status_code} to the pre-loaded "
        f"student principal: {catalog.text[:400]}"
    )
    body = json_body(catalog)
    assert body["unit_id"] == flow.unit_id

    balance = body["balance"]
    assert balance["state"] in {"measured", "unknown"}, (
        f"the balance reports state={balance['state']!r}; ADR-0011 allows two "
        "values and no third — there is no 'stale', 'partial' or 'estimated'"
    )
    if balance["state"] == "measured":
        assert isinstance(balance["points"], int) and balance["points"] >= 0
        assert balance["unknown_reason"] is None
    else:
        assert balance["points"] is None, (
            f"an unknown balance published points={balance['points']!r}; an "
            "unknown must be null and never 0"
        )
        assert balance["unknown_reason"], (
            "the balance is unknown and says nothing about why; a consumer "
            "cannot tell 'we are not telling you' from 'the answer is nothing'"
        )

    assert isinstance(body["items"], list)
    assert isinstance(body["earn_policy_ratified"], bool)
    for item in body["items"]:
        assert item["points_cost"] > 0

    own = student_api.get(f"/v1/units/{flow.unit_id}/redemptions")
    assert own.status_code == 200, (
        f"the student's own redemption listing answered {own.status_code}: {own.text[:300]}"
    )
    assert json_body(own)["redemptions"] == [], (
        "a freshly seeded appliance handed the student redemptions nobody "
        "requested; this listing is the caller's own tickets and there are none"
    )

    print(
        f"  the student reads {len(body['items'])} funded reward(s) against a "
        f"{balance['state']} balance; the '{flow.role}' principal reads neither"
    )


def test_15_a_redemption_decision_has_nothing_to_decide(
    api: httpx.Client, student_api: httpx.Client, flow: ClickThrough
) -> None:
    """The gate moved; the catalog did not fill. Asserted, then skipped by name.

    ``POST /v1/units/{id}/redemptions/{id}/decision`` is gated on
    ``coordinator``, and a student principal now exists to create the redemption
    it would act on — so the role gate that blocked this step is gone. What
    blocks it now is data, not authorization: **no funded reward item exists on
    this appliance**, because nothing seeds one and no ``/v1`` route creates
    one. A student with a balance and no catalog has nothing to ask for.

    That is asserted rather than assumed. The request is issued against an item
    id that does not exist and the answer is required to be a ``404`` — which
    proves the route is reachable by this principal (it is not a ``403``) and
    that the appliance holds no such item. Inserting a reward row and a ledger
    entry to force a ticket into existence would manufacture the evidence the
    decision route exists to check, so the step stops here and says which half
    is missing.
    """
    if flow.unit_id is None:
        pytest.skip("step 02 did not resolve a unit id from GET /v1/me")

    catalog = json_body(student_api.get(f"/v1/units/{flow.unit_id}/rewards"))
    assert catalog["items"] == [], (
        "a funded reward item now exists on this appliance, so this step can "
        f"stop skipping and walk the request/decide path: {catalog['items']}"
    )

    invented = student_api.post(
        f"/v1/units/{flow.unit_id}/redemptions",
        json={"item_id": str(uuid.uuid4())},
    )
    assert invented.status_code == 404, (
        f"a redemption request for an item id nobody issued answered "
        f"{invented.status_code}. 403 would mean the student gate had closed "
        f"again; 201 would mean an item had been conjured: {invented.text[:300]}"
    )
    assert json_body(invented)["error"]["code"] == "reward_item_not_found"

    pytest.skip(
        "no redemption exists to decide on, and the reason is no longer the "
        "role: a student principal is pre-loaded and reaches the request route "
        "(the 404 above proves it, where a 403 would have meant the gate). What "
        "is missing is a funded reward item — nothing seeds a rewards catalog "
        "and no /v1 route creates one, so there is nothing to request and "
        "therefore nothing for the coordinator-gated decision route to act on. "
        "Seeding a reward and a points ledger directly would manufacture the "
        "ticket this step exists to watch move"
    )


# ---------------------------------------------------------------------------
# Step 16 — the portal pages
# ---------------------------------------------------------------------------


def test_16_the_portal_pages_have_no_backend_in_this_repository() -> None:
    """Not exercised, and not faked.

    The portal pages fetch ``/api/portals/*``. No service in this repository
    serves that prefix, so the pages render a load-failure state by design.
    ``compose_smoke.sh`` stage 16 already proves what *is* true of the web
    service — that it serves the SPA route and proxies ``/v1/me`` as the seeded
    coordinator — and this step declines to assert anything beyond it.
    """
    pytest.skip(
        "the portal pages fetch /api/portals/*, a backend that does not exist in "
        "this repository, so they render a load-failure state; nothing here "
        "stands in for it. The web service's real behaviour is covered by "
        "scripts/compose_smoke.sh stage 16"
    )


# ---------------------------------------------------------------------------
# Step 17-21 — consent-gated outreach: draft -> send -> job -> delivery events
# ---------------------------------------------------------------------------


def _seed_contact_channel(
    unit_id: str,
    *,
    address: str,
    contact_state: str,
    consent_source: str | None,
) -> str:
    """Create one synthetic contact in *unit_id* and return its id.

    Written through the database for the same reason the review item ids are
    read from it: **there is no route that creates a contact channel.** The
    ``/v1`` outreach surface composes, lists, sends and reads; a contact arrives
    from the pipeline, and this appliance's seed creates none. The gap is
    recorded here rather than papered over, and nothing about it is faked — the
    row goes in through the shipped schema, so every CHECK migration 0021
    declares (the state vocabulary, the approved-source pairing, the
    consent/date pairing) is enforced on it exactly as it would be on a row the
    application wrote. A row this constraint set rejects fails this step.

    ``professional_id`` is a fresh UUID carrying no foreign key: migration 0021
    records at length that no professional table exists in this schema yet.

    The address is always under RFC 2606's reserved ``.invalid`` TLD, which
    cannot resolve. Even if this appliance were somehow pointed at a live
    provider — it is not, and step 20 asserts that — there is no mailbox at the
    other end of anything composed here.
    """
    source_sql = "null" if consent_source is None else f"'{consent_source}'"
    recorded_sql = "null" if consent_source is None else "now()"
    # The insert is wrapped in a CTE so the statement psql runs is a SELECT.
    # `psql -tAc` prints a command tag ("INSERT 0 1") after the rows of a
    # non-SELECT, and `psql_scalar` returns stdout — a bare `returning id`
    # therefore hands back an id with a command tag stuck to it, which the API
    # rejects as a malformed UUID rather than as anything meaningful.
    return psql_scalar(
        f"""
        with created as (
            insert into contact_channel (
                id, tenant_id, owning_unit_id, professional_id, channel_kind,
                address, contact_state, consent_source, consent_recorded_at,
                consent_evidence
            ) values (
                gen_random_uuid(),
                (select tenant_id from org_unit where id = '{unit_id}'),
                '{unit_id}', gen_random_uuid(), 'email',
                '{address}', '{contact_state}', {source_sql}, {recorded_sql},
                'synthetic row created by tests/e2e/test_pilot_clickthrough.py'
            )
            returning id
        )
        select id from created
        """
    )


def _compose_draft(api: httpx.Client, unit_id: str, contact_id: str) -> httpx.Response:
    """Compose one draft from a shipped pilot template.

    No request field carries message text — the contract suite pins that
    against the published schema — so the wording is the template's and the
    values are obviously synthetic.
    """
    return api.post(
        f"/v1/units/{unit_id}/outreach/drafts",
        json={
            "contact_channel_id": contact_id,
            "template_id": OUTREACH_TEMPLATE_ID,
            "values": OUTREACH_VALUES,
            "approve": True,
        },
    )


def test_17_a_coordinator_composes_a_draft_for_a_consented_contact(
    api: httpx.Client, flow: ClickThrough
) -> None:
    """The draft is composed text, stored, and marked unreviewed.

    Nothing is sent by this call, and the ``201`` says so: a row exists and can
    be read back, which is exactly what has happened. ``202`` is reserved for
    the operation that genuinely defers work, and step 19 is that one.
    """
    if flow.unit_id is None:
        pytest.skip("step 02 did not resolve a unit id from GET /v1/me")

    flow.contact_channel_id = _seed_contact_channel(
        flow.unit_id,
        address=OUTREACH_ADDRESS,
        contact_state="active_candidate",
        consent_source="self_service",
    )
    assert flow.contact_channel_id, "the synthetic contact channel was not created"

    response = _compose_draft(api, flow.unit_id, flow.contact_channel_id)
    assert response.status_code == 201, (
        f"composing an outreach draft returned {response.status_code}, expected "
        f"201: {response.text[:400]}"
    )
    body = json_body(response)

    assert body["recipient_address"] == OUTREACH_ADDRESS, (
        f"the draft names {body['recipient_address']!r}, not the synthetic "
        f"contact {OUTREACH_ADDRESS!r} it was composed for"
    )
    assert body["status"] == "approved", (
        f"the draft came back {body['status']!r}; step 19 needs an approved one"
    )
    # OQ-003 on the wire: a coordinator can see that the wording has not been
    # through institutional review, which is the fact deciding whether this
    # message could ever go to a real person.
    assert body["content_status"] == "synthetic", (
        f"the draft reports content_status {body['content_status']!r}; a pilot "
        "appliance composing from the shipped templates must say 'synthetic'"
    )
    assert OUTREACH_VALUES["professional_name"] in body["body"], (
        "the rendered body does not contain the value it was given, so the "
        "template was not actually rendered"
    )

    flow.outreach_draft_id = body["draft_id"]
    print(f"  composed draft {flow.outreach_draft_id} for {OUTREACH_ADDRESS}")


def test_18_a_contact_without_approved_consent_cannot_be_composed_for(
    api: httpx.Client, flow: ClickThrough
) -> None:
    """The consent gate runs before any message text exists.

    A ``discovered`` address is evidence that someone exists, not permission to
    write to them, and this appliance must refuse it. The refusal is a ``403``
    rather than a ``422`` because it is a permission fact: no inputs make it
    allowed, and reporting it as a validation error would invite the caller to
    try different ones.

    This is the step that makes step 17 mean something. A route that composed
    for anybody would pass every other assertion in this section.
    """
    if flow.unit_id is None:
        pytest.skip("step 02 did not resolve a unit id from GET /v1/me")

    ineligible_id = _seed_contact_channel(
        flow.unit_id,
        address=f"e2e-discovered-{RUN_TAG}@synthetic.invalid",
        contact_state="discovered",
        consent_source=None,
    )

    response = _compose_draft(api, flow.unit_id, ineligible_id)

    assert response.status_code == 403, (
        f"composing for a 'discovered' contact returned {response.status_code}, "
        f"expected a 403 refusal: {response.text[:400]}"
    )
    code = json_body(response)["error"]["code"]
    assert code == "outreach_recipient_not_eligible", (
        f"the refusal carried code {code!r}, not 'outreach_recipient_not_eligible'"
    )


def test_19_the_send_is_a_command_and_reports_no_status(
    api: httpx.Client, flow: ClickThrough
) -> None:
    """B17's replacement, asserted as the absence of a field.

    The legacy button logged to the console and said "Message sent!". What
    replaces it is a ``202`` and a job id: there is nothing in this body a
    client could render as a success, which is what makes an optimistic toast
    impossible rather than merely discouraged.
    """
    if flow.unit_id is None or flow.outreach_draft_id is None:
        pytest.skip("step 17 did not compose an approved outreach draft to send")

    response = api.post(
        f"/v1/units/{flow.unit_id}/outreach/drafts/{flow.outreach_draft_id}/send",
        headers={"Idempotency-Key": f"e2e-outreach-{RUN_TAG}-{uuid.uuid4().hex}"},
    )
    assert response.status_code == 202, (
        f"submitting the send returned {response.status_code}, expected 202: {response.text[:400]}"
    )
    body = json_body(response)
    assert set(body) == {"job_id", "events_url", "replayed"}, (
        f"the send acknowledgement carried {sorted(body)}; any field beyond "
        "job_id/events_url/replayed is one a client could render as 'sent'"
    )
    assert body["events_url"] == f"/v1/jobs/{body['job_id']}/events", (
        f"events_url is {body['events_url']!r} and does not point at the job"
    )

    flow.outreach_job_id = body["job_id"]
    print(f"  send accepted as job {flow.outreach_job_id}")


def test_20_the_worker_sends_through_the_fixture_provider(
    api: httpx.Client, flow: ClickThrough
) -> None:
    """The job settles, and the send says what actually happened.

    Everything asserted here is read back from the appliance after the fact:
    the job's own completion summary, then the send row and the delivery events
    recorded against it. Nothing is inferred from the ``202``.

    ``disposition`` is ``accepted`` — the provider took custody — and never
    "sent" or "delivered", which are claims about a mailbox nobody here can
    observe. ``live_mode`` is asserted false, so this step also proves the
    appliance is on the fixture provider rather than reporting a success it
    bought by mailing a stranger.
    """
    if flow.unit_id is None or flow.outreach_job_id is None:
        pytest.skip("step 19 did not submit an outreach send command")

    summary = _await_job(api, flow.outreach_job_id)

    assert summary["disposition"] == "accepted", (
        f"the send job reported disposition {summary['disposition']!r}, expected 'accepted'"
    )
    assert summary["live_mode"] is False, (
        "the appliance reports live_mode=true: this suite composes only "
        f"{OUTREACH_ADDRESS!r}, but a click-through must never run against a "
        "provider that can reach a real mailbox"
    )
    assert summary["provider"] == "fixture-email", (
        f"the send went through provider {summary['provider']!r}, not the fixture"
    )

    send = json_body(api.get(f"/v1/units/{flow.unit_id}/outreach/sends/{summary['send_id']}"))
    assert send["disposition"] == "accepted", (
        f"the send reads back {send['disposition']!r} after a job that reported "
        "'accepted'; the summary and the row disagree"
    )
    assert send["provider_message_id"], (
        "an accepted send carries no provider_message_id, so nothing identifies "
        "what the provider took custody of"
    )
    # The delivery stream, not a folded status: the queue happened, then the
    # provider accepted, and both are true at once.
    event_types = [event["event_type"] for event in send["delivery_events"]]
    assert event_types == ["queued", "accepted"], (
        f"the delivery events are {event_types}, expected exactly ['queued', 'accepted']"
    )

    print(f"  send {summary['send_id']} accepted by {summary['provider']}")


def test_21_a_recipient_who_unsubscribes_after_approval_is_not_written_to(
    api: httpx.Client, flow: ClickThrough
) -> None:
    """The whole feature, against the running appliance.

    The draft is composed while the recipient is eligible, and approved by a
    coordinator who could see that. *Then* the person unsubscribes. *Then* the
    command is submitted — and the submission itself is refused.

    Three gates close three different windows, and this is the middle one:
    composition proves what was true while the coordinator was looking at the
    screen; **submission** re-reads the recipient and catches a withdrawal in
    the hours between composing and sending; the worker's re-check catches the
    window after a ``202``, which no request-path check can see. The third is
    the one that actually protects the recipient and it is unchanged — it is
    exercised in ``tests/integration/test_outreach_handler.py``'s
    ``TestDeliveryTimeRefusal``, because once submission refuses first there is
    no way to queue a command for a suppressed recipient through the HTTP
    boundary at all.

    The refusal reaches the person acting, at the moment they act, rather than
    arriving as a job failure nobody is watching. Nothing is queued and no send
    row is written, which is what the assertions below check: a ``202`` here
    would hand a coordinator an acknowledgement for a message that was never
    going to go out, which is exactly the fake success this suite exists to
    catch.
    """
    if flow.unit_id is None or flow.contact_channel_id is None:
        pytest.skip("step 17 did not create a synthetic contact to compose for")

    composed = _compose_draft(api, flow.unit_id, flow.contact_channel_id)
    assert composed.status_code == 201, (
        f"composing the second draft returned {composed.status_code}: {composed.text[:400]}"
    )
    draft_id = json_body(composed)["draft_id"]

    # As if the recipient clicked unsubscribe between the approval and the
    # submission. Written directly because the one-click token is minted inside
    # the worker and handed to the provider; on this appliance the fixture
    # provider holds it in a container's memory, so nothing on this side of the
    # HTTP boundary can read it. The row is the same row POST /v1/unsubscribe
    # writes, `source` included, and the contract suite covers that route.
    suppression_id = psql_scalar(
        f"""
        with suppressed as (
            insert into suppression_record (id, tenant_id, address, suppressed_at, source)
            values (
                gen_random_uuid(),
                (select tenant_id from org_unit where id = '{flow.unit_id}'),
                '{OUTREACH_ADDRESS}', now(), 'unsubscribe_link'
            )
            returning id
        )
        select id from suppressed
        """
    )
    assert suppression_id, "the suppression record was not written"

    response = api.post(
        f"/v1/units/{flow.unit_id}/outreach/drafts/{draft_id}/send",
        headers={"Idempotency-Key": f"e2e-blocked-{RUN_TAG}-{uuid.uuid4().hex}"},
    )
    assert response.status_code == 403, (
        f"submitting the second send returned {response.status_code}, expected "
        "403 — the route re-reads the recipient and refuses a consent that was "
        f"withdrawn after the approval: {response.text[:400]}"
    )
    error = json_body(response)["error"]
    assert error["code"] == "outreach_recipient_not_eligible", (
        f"the refusal is coded {error['code']!r}; without that code a client "
        "cannot tell a withdrawn consent from an unapproved draft"
    )
    assert "suppress" in error["message"], (
        f"the refusal message is {error['message']!r} and does not name the "
        "suppression; a consent system must be able to answer why a person was "
        "not written to"
    )

    # Nothing queued means nothing recorded. The sends listing is the unit's own
    # record of what it has attempted, so a send row for this draft would mean
    # the refusal landed after something had already been committed.
    listed = json_body(api.get(f"/v1/units/{flow.unit_id}/outreach/sends"))
    assert not [send for send in listed["sends"] if send["draft_id"] == draft_id], (
        "a send row exists for the refused draft, so the submission was not "
        "refused before anything was written"
    )

    print("  send to a suppressed recipient was refused at submission / 403")


# ---------------------------------------------------------------------------
# Step 22-25 — the CBA extension: invite the shortlist, take the Speaker's own
# answer, hand the Event Host the one who accepted, and read the aggregate a
# Connector is allowed to see.
# ---------------------------------------------------------------------------

#: The invitation template the batch route composes from. Restated here for the
#: reason ``SCORE_LABEL`` is: a caller cannot choose it, so a drift in what the
#: server picked fails loudly here rather than passing unnoticed.
INVITATION_TEMPLATE_ID = "cba.speaker_invitation.v1"

#: The response link the invitation carries. The API composes it as
#: ``{public_base_url}/i/{token}`` from a token minted per invitation, and this
#: is how step 23 recovers the token a Speaker would click — out of the message
#: the appliance actually composed, read back over HTTP.
_RESPONSE_LINK = re.compile(r"/i/([A-Za-z0-9_\-]{16,})")

#: Carried between steps 22-25 for the reason ``_MATCH_FIXTURE`` is: module
#: state rather than new ``ClickThrough`` fields, so this extension does not
#: reach into ``tests/e2e/conftest.py``, which every other step shares.
_INVITATION_STATE: dict[str, Any] = {}


def _invitation_address(nickname: str) -> str:
    """The per-session ``.invalid`` address one seeded speaker is invited at.

    RFC 2606's reserved TLD, exactly as ``OUTREACH_ADDRESS`` is: it cannot
    resolve, so nothing composed here has a mailbox at the other end of it.
    """
    return f"e2e-speaker-{nickname}-{RUN_TAG}@synthetic.invalid"


def _register_invitable_channel(
    api: httpx.Client, unit_id: str, *, professional_id: str, address: str
) -> str:
    """Give one roster contact an address a batch may write to, through the API.

    Two calls and no database write, which is the point: ``POST
    /v1/units/{unit_id}/speaker-contacts/{professional_id}/channels`` records the
    address with its consent source and evidence, and ``POST .../transitions``
    activates it. Creating an ``active_candidate`` outright is refused by the
    route — "activation is an act with an actor, not an initial value" — so the
    two calls here are the shipped lifecycle rather than a convenience, and
    ``send_eligible`` below is the appliance's own answer about the row rather
    than this file's claim about it.

    Contrast ``_seed_contact_channel`` above, which writes directly because
    *nothing* creates a channel on the pre-CBA outreach surface. This one has a
    route, so this one uses it.
    """
    created = api.post(
        f"/v1/units/{unit_id}/speaker-contacts/{professional_id}/channels",
        json={
            "address": address,
            "contact_state": "consented",
            "consent_source": "self_service",
            "consent_evidence": (
                "synthetic consent recorded by tests/e2e/test_pilot_clickthrough.py"
            ),
            "reason": "e2e click-through: the speaker agreed to hear about opportunities",
        },
    )
    assert created.status_code == 201, (
        f"registering a channel for {professional_id} returned "
        f"{created.status_code}, expected 201: {created.text[:400]}"
    )
    channel_id = json_body(created)["channel"]["contact_channel_id"]

    activated = api.post(
        f"/v1/units/{unit_id}/speaker-contacts/{professional_id}/channels/{channel_id}/transitions",
        json={
            "to_state": "active_candidate",
            "reason": "e2e click-through: the Connector opened outreach on this contact",
        },
    )
    # ``201``, not ``200``: a transition is a new trail entry, and the route
    # says so by creating one rather than by reporting an edit.
    assert activated.status_code == 201, (
        f"activating channel {channel_id} returned {activated.status_code}, "
        f"expected 201: {activated.text[:400]}"
    )
    channel = json_body(activated)["channel"]
    assert channel["send_eligible"] is True, (
        f"the appliance reports channel {channel_id} is not send-eligible after "
        f"activation: {channel}"
    )
    return str(channel_id)


def test_22_the_shortlist_is_composed_into_an_invitation_batch(
    api: httpx.Client, flow: ClickThrough
) -> None:
    """The shortlist the match run produced becomes invitations, and nothing is sent.

    The batch is composed from ``professional_ids`` — the §13 roster ids the run
    itself shortlisted, read back off the recorded run rather than retyped — and
    it carries ``match_run_id``, so the invitations stay traceable to the ranking
    that proposed these people. There is no ``event_id`` argument on this route
    at all: ``cba_invitation_batch`` holds the event as free text a Connector
    typed, and the Host's own event id enters through the *path* in step 24.

    ``201`` and not ``202``: the batch, its drafts and every outcome in it are
    rows that can be read back when this returns. What has **not** happened is a
    send — step 23 is the operation that genuinely defers work, and the
    assertions below include the absence of anything a client could render as
    one.

    Three things a batch reporting only its good news would not do, asserted
    together: every named recipient produces an outcome, the template is the
    server's closed-registry choice rather than a caller's, and each invitation
    starts at ``awaiting_response`` — the ordinary state of every invitation
    until somebody reads their mail, and not a failure.
    """
    if flow.unit_id is None or flow.match_run_id is None:
        pytest.skip("step 09 did not produce a match run to invite the shortlist of")

    run = json_body(api.get(f"/v1/units/{flow.unit_id}/match-runs/{flow.match_run_id}"))
    shortlist = [candidate["subject_id"] for candidate in run["shortlist"]]
    assert MIN_SPEAKERS <= len(shortlist) <= MAX_SPEAKERS, (
        f"the recorded run shortlisted {len(shortlist)} speakers; steps 22-24 "
        f"need the ratified {MIN_SPEAKERS}-{MAX_SPEAKERS}"
    )

    # The nickname is for this file's own error messages only; the wire carries
    # opaque ids and every request below sends one of those.
    nicknames = {
        professional_id: nickname
        for nickname, professional_id in _seed_match_fixtures(flow.unit_id)["speakers"].items()
    }
    addresses = {
        professional_id: _invitation_address(nicknames[professional_id])
        for professional_id in shortlist
    }
    for professional_id, address in addresses.items():
        _register_invitable_channel(
            api, flow.unit_id, professional_id=professional_id, address=address
        )

    response = api.post(
        f"/v1/units/{flow.unit_id}/speaker-invitations/batches",
        json={
            "professional_ids": shortlist,
            "match_run_id": flow.match_run_id,
            "event_name": f"E2E virtual finance panel {RUN_TAG}",
            "event_date": "Thursday, 4 March 2027",
            "coordinator_name": "E2E Connector",
        },
        headers={"Idempotency-Key": f"e2e-batch-{RUN_TAG}-{uuid.uuid4().hex}"},
    )
    assert response.status_code == 201, (
        f"composing the invitation batch returned {response.status_code}, "
        f"expected 201: {response.text[:400]}"
    )
    batch = json_body(response)

    assert batch["match_run_id"] == flow.match_run_id, (
        f"the batch reports match_run_id {batch['match_run_id']!r} and not the "
        f"run its shortlist came from ({flow.match_run_id})"
    )
    assert batch["template_id"] == INVITATION_TEMPLATE_ID, (
        f"the batch composed from template {batch['template_id']!r}; the "
        "invitation copy is a closed-registry decision, not a caller's"
    )
    assert batch["replayed"] is False, "a fresh idempotency key replayed a stored batch"
    assert batch["skipped_count"] == 0, (
        "a shortlisted speaker with an activated, consented channel was skipped: "
        f"{[outcome for outcome in batch['invitations'] if outcome['skip_reason']]}"
    )
    assert batch["invited_count"] == len(shortlist)

    outcomes = {outcome["professional_id"]: outcome for outcome in batch["invitations"]}
    assert set(outcomes) == set(shortlist), (
        f"the batch reported on {sorted(outcomes)} but was asked to invite "
        f"{sorted(shortlist)}; a shorter list is a batch burying its decisions"
    )
    for professional_id, outcome in outcomes.items():
        assert outcome["status"] == "pending", (
            f"invitation {outcome['invitation_id']} came back {outcome['status']!r}; "
            "composing a batch sends nothing, so nothing may be 'dispatched' yet"
        )
        assert outcome["recipient_address"] == addresses[professional_id], (
            f"invitation {outcome['invitation_id']} names "
            f"{outcome['recipient_address']!r}, not the channel just activated "
            f"for this speaker ({addresses[professional_id]!r})"
        )
        assert outcome["delivery"] is None, (
            f"an invitation nobody has dispatched carries a delivery record: {outcome['delivery']}"
        )
        assert outcome["speaker_response"]["response"] == "awaiting_response", (
            "a freshly composed invitation already records an answer: "
            f"{outcome['speaker_response']}"
        )

    _INVITATION_STATE.update(
        {
            "batch_id": batch["batch_id"],
            "addresses": addresses,
            "outcomes": outcomes,
            "shortlist": shortlist,
            "nicknames": nicknames,
        }
    )
    print(f"  composed batch {batch['batch_id']} inviting {sorted(addresses.values())}")


def _response_tokens(api: httpx.Client, unit_id: str, addresses: dict[str, str]) -> dict[str, str]:
    """Each invited speaker's response token, read out of the message composed for them.

    The token is minted per invitation and stored only as a SHA-256 hash, so the
    plaintext exists in exactly one readable place: the body of the draft the
    batch composed, which ``GET /v1/units/{unit_id}/outreach/drafts`` returns.
    That is a real surface a Connector reads, not a back door — and it is why
    step 23 can follow the Speaker's own link where step 21 could not follow the
    unsubscribe link (that token is minted inside the worker at delivery and
    never lands in a row).

    Paged rather than fetched in one shot, and bounded: a unit accumulates drafts
    across sessions, and a single read that silently missed an older one would
    fail this step with a confusing ``KeyError`` instead of a clear message.
    """
    wanted = {address: professional_id for professional_id, address in addresses.items()}
    tokens: dict[str, str] = {}

    limit = 200
    for page in range(10):
        listing = json_body(
            api.get(
                f"/v1/units/{unit_id}/outreach/drafts",
                params={"limit": limit, "offset": page * limit},
            )
        )
        drafts = listing["drafts"]
        for draft in drafts:
            professional_id = wanted.get(draft["recipient_address"])
            if professional_id is None or professional_id in tokens:
                continue
            assert draft["template_id"] == INVITATION_TEMPLATE_ID, (
                f"the draft for {draft['recipient_address']} was composed from "
                f"{draft['template_id']!r}, not the invitation template"
            )
            found = _RESPONSE_LINK.search(draft["body"])
            assert found is not None, (
                f"the invitation composed for {draft['recipient_address']} carries "
                f"no response link, so a Speaker has no way to answer it: "
                f"{draft['body'][:400]}"
            )
            tokens[professional_id] = found.group(1)
        if len(tokens) == len(addresses) or len(drafts) < limit:
            break

    missing = sorted(address for pid, address in addresses.items() if pid not in tokens)
    assert not missing, f"no composed invitation was found for {missing}"
    return tokens


def test_23_the_speaker_answers_through_the_link_in_their_own_invitation(
    api: httpx.Client, flow: ClickThrough
) -> None:
    """The batch goes out through the fixture provider, and the Speakers answer it.

    Two facts are kept apart the whole way down, and this is the step where they
    could most easily be confused. ``delivery.disposition`` is ``accepted`` — the
    *provider* took custody. ``speaker_response.response`` is
    ``accepted_invitation`` or ``declined_invitation`` — the *Speaker* answered.
    The two vocabularies share no value, so no client can render one as the
    other, and this step asserts both on the same invitation at once.

    The dispatch runs through ``fixture-email`` and ``live_mode`` is asserted
    false, exactly as step 20 does: a green run here is a run through the
    deterministic fixture and never one bought by mailing a stranger. Every
    address in the batch is under RFC 2606's reserved ``.invalid`` TLD, so there
    is no mailbox at the other end of any of it.

    The answers are given the way a Speaker gives them — ``POST
    /v1/speaker-invitations/respond``, **unauthenticated**, carrying only the
    token from the link in their own message. That is asserted rather than
    assumed: the requests below strip the bearer, because a route that needed the
    Connector's credentials to accept a Speaker's answer would not be a route a
    Speaker could use. The stored answer therefore reads ``channel='speaker_link'``
    with no ``recorded_by_user_id`` — a stronger evidentiary claim than a
    coordinator retyping what they were told, and one that must not be spelled
    the same way.

    One accepts and the rest decline. The decline is not decoration: step 24
    asserts the Event Host's surface does not expose it, and that assertion is
    vacuous unless a decline exists to be leaked.
    """
    if flow.unit_id is None or not _INVITATION_STATE:
        pytest.skip("step 22 did not compose an invitation batch to dispatch")

    batch_id = _INVITATION_STATE["batch_id"]
    addresses: dict[str, str] = _INVITATION_STATE["addresses"]
    nicknames: dict[str, str] = _INVITATION_STATE["nicknames"]

    response = api.post(f"/v1/units/{flow.unit_id}/speaker-invitations/batches/{batch_id}/dispatch")
    assert response.status_code == 202, (
        f"dispatching batch {batch_id} returned {response.status_code}, "
        f"expected 202: {response.text[:400]}"
    )
    dispatch = json_body(response)
    assert set(dispatch) == {"batch_id", "dispatched", "not_dispatched"}, (
        f"the dispatch acknowledgement carried {sorted(dispatch)}; any field "
        "beyond these three is one a client could render as 'sent'"
    )
    assert dispatch["not_dispatched"] == [], (
        "an invitation composed for an activated, consented channel was refused "
        f"at dispatch: {dispatch['not_dispatched']}"
    )
    assert len(dispatch["dispatched"]) == len(addresses), (
        f"{len(dispatch['dispatched'])} of {len(addresses)} invitations were "
        "submitted; a batch must not silently lose a recipient"
    )

    for entry in dispatch["dispatched"]:
        assert entry["events_url"] == f"/v1/jobs/{entry['job_id']}/events", (
            f"events_url is {entry['events_url']!r} and does not point at the job"
        )
        summary = _await_job(api, entry["job_id"])
        assert summary["live_mode"] is False, (
            "the appliance reports live_mode=true: this suite invites only "
            "'.invalid' addresses, but a click-through must never run against a "
            "provider that can reach a real mailbox"
        )
        assert summary["provider"] == "fixture-email", (
            f"an invitation went through provider {summary['provider']!r}, not the fixture"
        )
        assert summary["disposition"] == "accepted", (
            f"the invitation send reported disposition {summary['disposition']!r}"
        )

    tokens = _response_tokens(api, flow.unit_id, addresses)

    # Deterministic, so a re-read of this file says which speaker did what: the
    # lowest id accepts and every other invited speaker declines.
    ordered = sorted(addresses)
    answers = {ordered[0]: "accept"} | {pid: "decline" for pid in ordered[1:]}

    for professional_id, answer in answers.items():
        # No bearer. The Speaker holds a token from an email and no account —
        # the respond route is unauthenticated by design, and sending the
        # Connector's credentials here would prove nothing about the route a
        # Speaker actually reaches.
        answered = api.post(
            "/v1/speaker-invitations/respond",
            json={"token": tokens[professional_id], "response": answer},
            headers={"Authorization": ""},
        )
        assert answered.status_code == 200, (
            f"a Speaker answering '{answer}' with their own token got "
            f"{answered.status_code}: {answered.text[:400]}"
        )
        assert json_body(answered) == {"recorded": True}, (
            "the answer to a Speaker's response carries more than 'recorded'; a "
            "body that distinguished a real token from an invented one would let "
            "anyone holding a guess confirm who was invited to speak"
        )

    read_back = json_body(
        api.get(f"/v1/units/{flow.unit_id}/speaker-invitations/batches/{batch_id}")
    )
    outcomes = {outcome["professional_id"]: outcome for outcome in read_back["invitations"]}

    for professional_id, answer in answers.items():
        want = "accepted_invitation" if answer == "accept" else "declined_invitation"
        outcome = outcomes[professional_id]
        speaker_response = outcome["speaker_response"]

        assert speaker_response["response"] == want, (
            f"{nicknames[professional_id]} answered {answer!r} through their own "
            f"link, but the batch reads back {speaker_response['response']!r}"
        )
        assert speaker_response["channel"] == "speaker_link", (
            f"the answer is recorded on channel {speaker_response['channel']!r}; "
            "a Speaker's own click and a coordinator retyping what they were told "
            "are different evidentiary claims and must not be stored alike"
        )
        assert speaker_response["recorded_by_user_id"] is None, (
            "a Speaker's own answer names a coordinator as its recorder: "
            f"{speaker_response['recorded_by_user_id']}"
        )
        assert speaker_response["recorded_at"], (
            "an answered invitation carries no recorded_at, so nothing dates the answer"
        )

        assert outcome["status"] == "dispatched", (
            f"invitation {outcome['invitation_id']} reads back {outcome['status']!r} "
            "after a dispatch that reported it submitted"
        )
        # The provider's fact, on the same row as the Speaker's, and different.
        assert outcome["delivery"]["disposition"] == "accepted", (
            f"the delivery reads {outcome['delivery']['disposition']!r}"
        )
        assert outcome["delivery"]["provider"] == "fixture-email"
        assert outcome["delivery"]["disposition"] != speaker_response["response"], (
            "the delivery disposition and the Speaker's answer are spelled the "
            "same way; one is what a mail provider did and the other is what a "
            "person said, and a shared vocabulary is how the two get confused"
        )

    accepted_id = ordered[0]
    declined_ids = ordered[1:]
    _INVITATION_STATE.update(
        {
            "accepted_professional_id": accepted_id,
            "accepted_invitation_id": outcomes[accepted_id]["invitation_id"],
            "declined_professional_ids": declined_ids,
            "declined_invitation_ids": [outcomes[pid]["invitation_id"] for pid in declined_ids],
            "declined_addresses": [addresses[pid] for pid in declined_ids],
        }
    )
    print(
        f"  {nicknames[accepted_id]} accepted through their own link; "
        f"{[nicknames[pid] for pid in declined_ids]} declined"
    )


#: Substrings that must not appear anywhere in the Event Host's hand-off — not
#: as a key, not as a value. OQ-CBA-042 takes the narrow reading: an Event Host
#: learns who accepted and is told nothing whatever about who did not.
#:
#: ``member_inquiry`` rides along because ``Capability.MEMBER_INQUIRY_NARRATIVE``
#: is false under the CBA scope and ``ConfirmedSpeakerView`` carries no field for
#: it — a structural absence worth pinning on the wire, since a filter applied
#: only at the edge would pass every other assertion here.
_FORBIDDEN_ON_THE_HANDOFF: tuple[str, ...] = (
    "declin",
    "member_inquiry",
    "skipped",
    "invited_count",
    "batch",
    "total",
    "_count",
)


def _handoff_leaks(payload: Any, path: str = "") -> list[str]:
    """Every place a hand-off payload names something an Event Host may not see.

    Walks keys *and* string values, because the two failure modes differ: a
    ``declined_count`` field is a schema that leaked, while a ``current_stage``
    of ``declined_invitation`` is a value that leaked through an honest field.
    Both are the same disclosure to the person reading the screen.
    """
    leaks: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            here = f"{path}.{key}" if path else key
            for forbidden in _FORBIDDEN_ON_THE_HANDOFF:
                if forbidden in key.lower():
                    leaks.append(f"key {here!r}")
            leaks.extend(_handoff_leaks(value, here))
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            leaks.extend(_handoff_leaks(item, f"{path}[{index}]"))
    elif isinstance(payload, str):
        for forbidden in _FORBIDDEN_ON_THE_HANDOFF:
            if forbidden in payload.lower():
                leaks.append(f"value at {path!r}: {payload!r}")
    return leaks


def test_24_the_event_host_is_handed_the_confirmed_speaker_and_no_declines(
    api: httpx.Client, flow: ClickThrough
) -> None:
    """The accepted speaker reaches the Event Host. The ones who said no do not.

    The reconciliation writes no stage a request asserted: the body names an
    invitation and nothing else, and ``matched``, ``contacted`` and ``confirmed``
    are read out of that invitation's own ``created_at``, ``dispatched_at`` and
    ``response_recorded_at``. There is no ``stage`` field to toggle and no
    ``reached_at`` to backdate, so this step proves the funnel is derived from
    stored evidence rather than typed beside it.

    That the evidence is what matters is asserted from the other side too: a
    hand-off naming a **declined** invitation is refused ``409
    cba_invitation_not_accepted``. Confirmed is supplied by the Speaker's own
    answer, so an invitation carrying the wrong answer has nothing to hand
    anybody — and a route that accepted it would be manufacturing a confirmation
    out of a refusal.

    **The OQ-CBA-042 property, pinned here and not only in the unit tests.**
    The narrow reading was taken deliberately: an Event Host learning that named
    professionals declined them is a fact about those people's availability and
    willingness that nobody agreed to share. So ``/cba/confirmed-speakers`` is
    checked for three separate disclosures, each of which a plausible convenience
    would introduce:

    * the declining speakers themselves, by id — asserted absent;
    * any **word** for a decline, anywhere in the payload, as a key or a value —
      which is what would appear if a status field were widened to carry the
      whole invitation vocabulary;
    * any **count or total**, which is the subtler leak. "One confirmed of
      three invited" discloses that two people said no without naming either,
      and a batch size is not the Host's fact to have. The surface reports which
      speakers, and no arithmetic about the ones it is not reporting.

    A repeat is a ``200`` with an empty ``applied`` and an unchanged speaker:
    "they are confirmed" and "this request confirmed them" stay separable.
    """
    if flow.unit_id is None or not _INVITATION_STATE.get("accepted_invitation_id"):
        pytest.skip("step 23 did not record an accepted invitation to hand off")

    event_id = _seed_match_fixtures(flow.unit_id)["event_id"]
    accepted_professional_id = _INVITATION_STATE["accepted_professional_id"]
    nicknames: dict[str, str] = _INVITATION_STATE["nicknames"]

    response = api.post(
        f"/v1/units/{flow.unit_id}/cba/events/{event_id}/speaker-handoff",
        json={"invitation_id": _INVITATION_STATE["accepted_invitation_id"]},
    )
    assert response.status_code == 200, (
        f"reconciling the accepted invitation returned {response.status_code}, "
        f"expected 200: {response.text[:400]}"
    )
    handoff = json_body(response)

    assert handoff["applied"] == ["matched", "contacted", "confirmed"], (
        f"the reconciliation applied {handoff['applied']}, not the three stages "
        "the invitation evidences: created (matched), dispatched (contacted), "
        "answered (confirmed)"
    )
    speaker = handoff["speaker"]
    assert speaker["professional_id"] == accepted_professional_id, (
        f"the hand-off returned {speaker['professional_id']}, not the speaker "
        f"who accepted ({accepted_professional_id})"
    )
    assert speaker["current_stage"] == "confirmed", (
        f"the speaker reads back at stage {speaker['current_stage']!r}"
    )
    assert speaker["confirmed_at"], "a confirmed speaker carries no confirmed_at"
    assert speaker["attended_at"] is None and speaker["attendance_id"] is None, (
        "the hand-off cited no attendance record, so Attended must stay unwritten: "
        f"attended_at={speaker['attended_at']!r} attendance_id={speaker['attendance_id']!r}"
    )

    # A repeat writes nothing and says so, rather than replaying the stages.
    repeated = api.post(
        f"/v1/units/{flow.unit_id}/cba/events/{event_id}/speaker-handoff",
        json={"invitation_id": _INVITATION_STATE["accepted_invitation_id"]},
    )
    assert repeated.status_code == 200, (
        f"re-running the hand-off returned {repeated.status_code}: {repeated.text[:400]}"
    )
    assert json_body(repeated)["applied"] == [], (
        "a repeated reconciliation reports stages it did not write: "
        f"{json_body(repeated)['applied']}"
    )

    # The other side of the same rule: a decline evidences no confirmation.
    declined_invitation_id = _INVITATION_STATE["declined_invitation_ids"][0]
    refused = api.post(
        f"/v1/units/{flow.unit_id}/cba/events/{event_id}/speaker-handoff",
        json={"invitation_id": declined_invitation_id},
    )
    assert refused.status_code == 409, (
        f"handing off a declined invitation returned {refused.status_code}, "
        f"expected a 409 refusal: {refused.text[:400]}"
    )
    assert json_body(refused)["error"]["code"] == "cba_invitation_not_accepted", (
        f"the refusal is coded {json_body(refused)['error']['code']!r}; without "
        "that code a client cannot tell a decline from a missing invitation"
    )

    listed = json_body(
        api.get(
            f"/v1/units/{flow.unit_id}/cba/confirmed-speakers",
            params={"event_id": event_id},
        )
    )
    confirmed = {entry["professional_id"]: entry for entry in listed["speakers"]}

    assert accepted_professional_id in confirmed, (
        f"{nicknames[accepted_professional_id]} accepted and was reconciled, but "
        f"the Event Host's confirmed-speakers list holds {sorted(confirmed)}"
    )
    assert confirmed[accepted_professional_id]["current_stage"] == "confirmed"
    assert confirmed[accepted_professional_id]["event_id"] == event_id, (
        "the confirmed speaker is filed against a different event than the one "
        "the list was filtered to"
    )

    for declined_professional_id in _INVITATION_STATE["declined_professional_ids"]:
        assert declined_professional_id not in confirmed, (
            f"{nicknames[declined_professional_id]} declined this invitation and "
            "still appears on the Event Host's confirmed-speaker surface "
            "(OQ-CBA-042: the Host is handed the confirmed speaker and is told "
            "nothing about the people who said no)"
        )

    for payload, surface in ((listed, "GET /cba/confirmed-speakers"), (handoff, "the hand-off")):
        leaks = _handoff_leaks(payload)
        assert not leaks, (
            f"{surface} exposes a decline, a count of declines, or a batch total "
            f"to the Event Host: {leaks}. OQ-CBA-042 takes the narrow reading — "
            "even an unnamed arithmetic ('one of three') discloses that somebody "
            "refused, and the batch tracking surface is the Speaker Connector's "
            "by name and nobody else's"
        )

    print(
        f"  the Event Host is handed {nicknames[accepted_professional_id]}; "
        f"{len(_INVITATION_STATE['declined_professional_ids'])} decline(s) "
        "disclosed nowhere on that surface"
    )


def test_25_student_feedback_reaches_a_connector_only_as_an_aggregate(
    api: httpx.Client, student_api: httpx.Client, flow: ClickThrough
) -> None:
    """A Connector gets a thresholded average and no way to reach one student.

    **The submission itself still cannot be driven on this appliance, and is
    skipped by name rather than faked.** One of the two gates that used to stop
    it is gone; the other is not, and it is the one that matters here:

    1. *Closed.* The route is gated on the ``student`` role alone, and this
       appliance used to map its single dev bearer to one ``coordinator``
       principal. It now pre-loads a student, so the student's own surfaces are
       reachable and are read below — while the coordinator stays refused them,
       which is asserted first so the reachability cannot be mistaken for a
       widening.
    2. *Still standing.* Even as a student, the route requires an
       ``attendance_record`` for the caller at that event, and **nothing in the
       ``/v1`` surface creates one** — ``smartmatch_persistence/attendance.py``
       says in its own docstring that no route imports it and none may. Step 24
       left ``attended_at`` null for exactly this reason: the hand-off cites an
       attendance row and never writes one.

    Writing either row directly would be manufacturing the evidence the feature
    exists to check, so this step asserts everything that *can* be reached over
    HTTP and stops. What it proves is the half that matters for OQ-CBA-003:
    **no individual rating is retrievable by a Connector.**

    * The student's own read is refused to this principal too, so the surface
      that returns per-student rows is not reachable by the role that reads the
      aggregate. There is no parameter to aim it at another student in any case
      — it is scoped by ``principal.user_id``.
    * The Connector's summary answers, and answers *aggregate-only*: it carries
      no field that can name a student, and the response model has none to
      filter. Comments are absent entirely (OQ-CBA-054).
    * Below the threshold it publishes **nothing** — ``mean_rating`` and
      ``response_count`` are both null and never ``0.0`` (ADR-0011 rule 1: a
      speaker nobody rated must not read as a speaker rated zero), with a
      sentence in ``display_text`` so a reader can tell "we are not telling you"
      from "the answer is nothing". The count is withheld *alongside* the mean
      rather than published beside it, because in a class of thirty "two
      students rated this speaker" narrows the field considerably.
    * The threshold is read from ``minimum_responses`` in the response. This
      file asserts the server publishes one and that its own suppression obeys
      it; it does not hard-code the number, because a client that carried its
      own copy would be a second place for the policy to live.

    **OQ-CBA-053** is pinned at the end: no rating is a scoring input. The
    recorded match run is re-read and asserted to carry no factor whose key
    mentions a rating or feedback — a matching model that had quietly grown one
    would fail here rather than in a review.
    """
    if flow.unit_id is None:
        pytest.skip("step 02 did not resolve a unit id from GET /v1/me")
    if not _INVITATION_STATE.get("accepted_professional_id"):
        pytest.skip("step 23 did not confirm a speaker to read a feedback summary for")

    event_id = _seed_match_fixtures(flow.unit_id)["event_id"]
    speaker_id = _INVITATION_STATE["accepted_professional_id"]

    # The Connector's refusal, asserted first. A 200 here would mean the student
    # surface had been widened to a coordinator, which is the thing OQ-CBA-003
    # part 1 forbids — and it is asserted *before* the student's reads below so
    # that a reachable student surface can never be mistaken for an open one.
    submitted = api.post(
        f"/v1/units/{flow.unit_id}/student/events/{event_id}/speakers/{speaker_id}/feedback",
        json={"rating": 4},
    )
    assert submitted.status_code == 403, (
        "the student-gated feedback submission answered "
        f"{submitted.status_code} to a '{flow.role}' principal; rating a speaker "
        f"is a student's act and deny-by-default makes this a refusal: {submitted.text[:300]}"
    )
    assert json_body(submitted)["error"]["code"] == "forbidden"

    # And the student's own read of their ratings is refused to this principal
    # as well: the per-student rows are not reachable from the role that reads
    # the aggregate below.
    mine = api.get(f"/v1/units/{flow.unit_id}/student/events/{event_id}/speaker-feedback")
    assert mine.status_code == 403, (
        "a coordinator could read the student-scoped feedback listing "
        f"({mine.status_code}); individual ratings must not be reachable from "
        f"the Connector's role: {mine.text[:300]}"
    )

    # The student's side of the same two routes, now that a student principal
    # exists. The read answers; the write does not, and the reason it does not
    # is gate 2 rather than the role — which is the distinction this step used
    # to be unable to draw at all.
    student_read = student_api.get(
        f"/v1/units/{flow.unit_id}/student/events/{event_id}/speaker-feedback"
    )
    assert student_read.status_code == 200, (
        "the pre-loaded student could not read their own speaker feedback "
        f"({student_read.status_code}): {student_read.text[:300]}"
    )
    assert json_body(student_read)["feedback"] == [], (
        "the student's own listing carries ratings nobody submitted; on this "
        "appliance no rating can be submitted at all, so anything here would "
        "have been written around the route rather than through it"
    )

    student_submit = student_api.post(
        f"/v1/units/{flow.unit_id}/student/events/{event_id}/speakers/{speaker_id}/feedback",
        json={"rating": 4},
    )
    assert student_submit.status_code == 403, (
        "the student's own submission answered "
        f"{student_submit.status_code}, expected 403. A 201 would mean a rating "
        "had been accepted from someone with no attendance record at this event, "
        f"which is the check OQ-CBA-003 puts in front of it: {student_submit.text[:300]}"
    )
    # The *reason* is what makes this the second gate rather than the first, and
    # the API distinguishes them for exactly this purpose: `forbidden` is "you
    # are not a student here", `student_feedback_not_eligible` is "you are, and
    # you were not at this event". This step would be worthless if it could not
    # tell them apart — a role gate that had quietly closed again would answer
    # 403 too.
    assert json_body(student_submit)["error"]["code"] == "student_feedback_not_eligible", (
        "the student's submission was refused with "
        f"{json_body(student_submit)['error']['code']!r}, not "
        "'student_feedback_not_eligible'. This step exists to show the remaining "
        "block is the missing attendance_record and not the student role gate"
    )

    summary = api.get(f"/v1/units/{flow.unit_id}/speakers/{speaker_id}/feedback-summary")
    assert summary.status_code == 200, (
        f"the Connector's feedback summary answered {summary.status_code}, "
        f"expected 200: {summary.text[:400]}"
    )
    aggregate = json_body(summary)

    # Aggregate-only, held as a shape rather than as a discipline: there is no
    # field here that could name a student, carry a comment, or list a row.
    assert set(aggregate) == {
        "speaker_professional_id",
        "suppressed",
        "response_count",
        "mean_rating",
        "display_text",
        "minimum_responses",
    }, (
        f"the Connector's summary carries {sorted(aggregate)}; any field beyond "
        "these six is one that could identify a student or republish their words "
        "(OQ-CBA-003 part 1, OQ-CBA-054)"
    )
    assert aggregate["speaker_professional_id"] == speaker_id

    threshold = aggregate["minimum_responses"]
    assert isinstance(threshold, int) and threshold > 0, (
        f"the summary publishes minimum_responses={threshold!r}; a surface has to "
        "be able to explain a suppression without hard-coding the number"
    )

    if aggregate["suppressed"]:
        # ADR-0011 rule 1, on both numbers at once. A zero here would say this
        # speaker was rated badly; null says nobody has told us.
        assert aggregate["mean_rating"] is None, (
            f"a suppressed aggregate published mean_rating={aggregate['mean_rating']!r}; "
            "an unknown must be null and never 0.0"
        )
        assert aggregate["response_count"] is None, (
            "a suppressed aggregate published its response_count "
            f"({aggregate['response_count']!r}); the count is withheld alongside "
            "the mean, because a small one narrows the field of who was asked"
        )
        assert aggregate["display_text"] and not any(
            character.isdigit() for character in aggregate["display_text"]
        ), (
            f"the suppressed display_text is {aggregate['display_text']!r}; a "
            "sentence rather than a dash or a zero, and carrying no number that "
            "would leak what is being withheld"
        )
    else:
        assert aggregate["response_count"] >= threshold, (
            f"an aggregate was published from {aggregate['response_count']} "
            f"responses, below the server's own threshold of {threshold}"
        )
        assert 1.0 <= aggregate["mean_rating"] <= 5.0, (
            f"the published mean {aggregate['mean_rating']!r} is off the 1-5 scale"
        )

    # OQ-CBA-053: an event outcome, and never a scoring input. No factor in the
    # recorded run reads this table, and none may grow to.
    if flow.match_run_id is not None:
        run = json_body(api.get(f"/v1/units/{flow.unit_id}/match-runs/{flow.match_run_id}"))
        factor_keys = {
            factor["factor_key"]
            for group in ("shortlist", "considered", "unscorable")
            for candidate in run[group]
            for factor in candidate["factors"]
        }
        rating_derived = sorted(
            key for key in factor_keys if "rating" in key.lower() or "feedback" in key.lower()
        )
        assert not rating_derived, (
            f"the match run scores on {rating_derived}; OQ-CBA-053 says student "
            "speaker feedback is an event outcome and no rating is a scoring "
            "input, so a factor reading it would need that decision reopened first"
        )

    print(
        f"  the Connector reads {aggregate['display_text']!r} "
        f"(suppressed={aggregate['suppressed']}, minimum_responses={threshold}) "
        "and has no route to an individual rating"
    )
    pytest.skip(
        "no student speaker feedback could be submitted on this appliance, so the "
        "aggregate above is asserted over zero stored ratings rather than over a "
        "rating this step wrote. ONE gate now, not two. The role gate is closed: "
        "a student principal is pre-loaded, reads its own feedback listing (200, "
        "empty) and reaches the submit route, while the coordinator is still "
        "refused both — all asserted above. What still stands is the second gate: "
        "the route requires an attendance_record for the caller at the event, and "
        "no /v1 route creates one — smartmatch_persistence/attendance.py says no "
        "route imports it and none may, and step 24's hand-off cites attendance "
        "without writing it. Seeding that row directly would manufacture the "
        "evidence the feature exists to check. The refusals, the student's own "
        "reads, and the aggregate-only shape above did run and are asserted"
    )


# ---------------------------------------------------------------------------
# Step 26 — the Event Host: one write, and nothing to read back
# ---------------------------------------------------------------------------


def test_26_the_event_host_files_a_request_and_can_read_nothing_back(
    api: httpx.Client, host_api: httpx.Client, flow: ClickThrough
) -> None:
    """The Event Host portal's whole reachable surface, and its whole gap.

    Run last, deliberately: filing a Speaker Request creates an ``event`` row,
    and an extra unpublished event ahead of the match-run and metrics steps
    would move numbers those steps assert against.

    What the Event Host can do is one thing — ``POST`` a request — and this step
    proves it works from the pre-loaded ``volunteer`` principal rather than only
    from a contract test's in-process client. What the Event Host **cannot** do
    is read anything at all, including the request they just filed: the queue
    listing is gated on ``{admin, coordinator}`` and no per-host listing exists.
    That is **OQ-CBA-014**, and it is asserted here as a refusal rather than
    closed by adding ``volunteer`` to a read set — a host-scoped read is a
    different query, not a wider permit, and inventing the permit would hand one
    host every other host's request text for the unit.

    The Connector's read is exercised too, on the same request, because that is
    what makes the host's ``403`` a *routing* gap rather than a lost write: the
    filing landed in a queue somebody can work, and only the host cannot see it.
    """
    if flow.unit_id is None:
        pytest.skip("step 02 did not resolve a unit id from GET /v1/me")

    filed = host_api.post(
        f"/v1/units/{flow.unit_id}/speaker-requests",
        json={
            "title": "Analytics Careers Panel",
            "time_zone": "America/Los_Angeles",
            "on_date": "2026-10-14",
            "is_virtual": False,
            "location_city": "Pomona",
            "industry_codes": ["52"],
            "role_codes": ["finance"],
            "description": (
                "Synthetic Speaker Request filed by tests/e2e/test_pilot_clickthrough.py"
            ),
        },
        headers={"Idempotency-Key": f"e2e-speaker-request-{uuid.uuid4()}"},
    )
    # 201 the first time this appliance sees the request, 200 when it has seen
    # it before. The route treats a resubmission of the same filing as the same
    # filing and returns it again rather than opening a second one, so a rerun
    # against a standing stack is a 200 and not a duplicate — accepted here for
    # that reason, and not because either code would do.
    assert filed.status_code in {200, 201}, (
        "the Event Host could not file a Speaker Request "
        f"({filed.status_code}); this is the one write the volunteer role "
        f"carries, and without it the portal has no reachable surface at all: "
        f"{filed.text[:400]}"
    )
    request_body = json_body(filed)
    request_id = request_body["request_id"]
    # The host chose a title, a date and a taxonomy — never a unit, a tenant, an
    # actor, or a publication status. The last of those is the server's and comes
    # back unpublished, which is what keeps a filed request out of the student
    # browse surface until somebody decides otherwise.
    assert request_body["publication_status"] == "unpublished", (
        "a freshly filed Speaker Request came back "
        f"{request_body['publication_status']!r}; a host does not publish their "
        "own event by asking for it"
    )

    listing_refused = host_api.get(f"/v1/units/{flow.unit_id}/speaker-requests")
    assert listing_refused.status_code == 403, (
        "the Speaker Request queue answered "
        f"{listing_refused.status_code} to the Event Host. Customer §13 gives "
        "the queue to the Speaker Connector and names nobody else; the queue "
        "holds every host's request text for the unit, so a 200 here would hand "
        f"one host the others' filings: {listing_refused.text[:300]}"
    )
    assert json_body(listing_refused)["error"]["code"] == "forbidden"

    queue = api.get(f"/v1/units/{flow.unit_id}/speaker-requests")
    assert queue.status_code == 200, (
        f"the Connector's own queue read answered {queue.status_code}: {queue.text[:300]}"
    )
    filed_ids = {entry["request_id"] for entry in json_body(queue)["requests"]}
    assert request_id in filed_ids, (
        f"the request the Event Host just filed ({request_id}) is not in the "
        "Connector's queue; the write reported 201 and reached nobody"
    )

    print(
        f"  the Event Host filed {request_id} and is refused every read of it; "
        "the Connector sees it in the queue (OQ-CBA-014)"
    )
