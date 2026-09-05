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
   proves the *worker* re-checks at delivery: a recipient who unsubscribes
   after a coordinator approved the draft ends the job ``failed_policy`` with a
   ``blocked`` delivery event and no provider message id. A job that ended
   ``succeeded`` there would be the fake success this module exists to catch.

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

#: Every terminal job state, transcribed from
#: ``smartmatch_domain.jobs.TERMINAL_STATES`` rather than imported: the
#: appliance under test is a built image, not this checkout, and a drift
#: between the two should fail here rather than be absorbed.
TERMINAL_JOB_STATES = frozenset(
    {
        "succeeded",
        "partial",
        "cancelled",
        "failed_budget",
        "failed_policy",
        "abandoned",
    }
)

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


def _submit_match_run(
    api: httpx.Client, unit_id: str, *, weak_topics: list[str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Submit one match run and return (acknowledgement, the persisted run).

    The pool is four synthetic candidates whose evidence differs deliberately:

    * ``strong``  — every required and preferred topic, next to the venue.
    * ``mid``     — the required topic only, an hour out.
    * ``weak``    — *weak_topics* (``[]`` in the first run: a record that exists
      and is empty, so a measured zero), far away.
    * ``unknown`` — ``expertise_topics: null``: no expertise record at all, so
      unscorable. Not the same thing as ``[]``, and the API must not treat it
      as though it were.

    ``weak_topics`` is the one knob
    :func:`test_10_a_changed_evidence_changes_the_score` turns, so that two
    otherwise identical runs differ in exactly one candidate's evidence.
    """
    body = {
        "event_need_id": f"e2e-need-{RUN_TAG}",
        "required_topics": ["robotics"],
        "preferred_topics": ["mentoring"],
        "event_location": {"latitude": 45.52, "longitude": -122.68},
        "portfolio_size": MIN_SPEAKERS,
        "random_seed": 7,
        "candidates": [
            {
                "subject_id": "strong",
                "expertise_topics": ["robotics", "mentoring"],
                "location": {"latitude": 45.53, "longitude": -122.66},
            },
            {
                "subject_id": "mid",
                "expertise_topics": ["robotics"],
                "location": {"latitude": 45.90, "longitude": -123.40},
            },
            {
                "subject_id": "weak",
                "expertise_topics": weak_topics,
                "location": {"latitude": 47.60, "longitude": -122.30},
            },
            {
                "subject_id": "unknown",
                "expertise_topics": None,
                "location": {"latitude": 45.50, "longitude": -122.60},
            },
        ],
    }
    response = api.post(
        f"/v1/units/{unit_id}/match-runs",
        json=body,
        headers={"Idempotency-Key": f"e2e-match-{RUN_TAG}-{uuid.uuid4().hex}"},
    )
    if response.status_code == 503:
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

    Four things a mock would not do, asserted together:

    * the scores are not all the same value;
    * they order by evidence — the candidate matching every topic next to the
      venue outscores the one matching none from two hundred kilometres away;
    * every score carries the registry version it was produced under; and
    * every factor names its own basis, so the number can be argued with.
    """
    if flow.unit_id is None:
        pytest.skip("step 02 did not resolve a unit id from GET /v1/me")

    accepted, run = _submit_match_run(api, flow.unit_id, weak_topics=[])
    flow.match_run_id = run["id"]

    assert accepted["registry_version"], "the acknowledgement named no registry version"
    assert accepted["scored_candidates"] == 3, (
        f"expected 3 scorable candidates, got {accepted['scored_candidates']}"
    )
    assert accepted["unscorable_candidates"] == 1, (
        "the candidate with no expertise record should be reported unscorable, not "
        f"scored: {accepted}"
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

    scores = _scores(run)
    measured = {name: value for name, value in scores.items() if value is not None}
    assert len(set(measured.values())) > 1, (
        f"every scored candidate got the identical score {measured}; that is a "
        "constant, not a computation"
    )
    assert measured["strong"] > measured["mid"] > measured["weak"], (
        "the ranking does not follow the evidence — every-topic-and-nearby "
        f"{measured['strong']}, one-topic-and-distant {measured['mid']}, "
        f"no-topic-and-far {measured['weak']}"
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


def test_10_a_changed_evidence_changes_the_score(api: httpx.Client, flow: ClickThrough) -> None:
    """The strongest anti-mock check: turn one knob, watch that one score move.

    The second run is identical to the first except that ``weak`` is given the
    required topic. Its score must rise, and — because nothing else about the
    pool changed — ``strong``'s must not. A fixture, a canned response, or a
    score derived from anything but the submitted evidence fails one half or
    the other.
    """
    if flow.match_run_id is None:
        pytest.skip("step 09 did not produce a match run to compare against")
    assert flow.unit_id is not None

    first = json_body(api.get(f"/v1/units/{flow.unit_id}/match-runs/{flow.match_run_id}"))
    _, second = _submit_match_run(api, flow.unit_id, weak_topics=["robotics"])

    before, after = _scores(first), _scores(second)
    assert after["weak"] is not None and before["weak"] is not None
    assert after["weak"] > before["weak"], (
        "giving a candidate the required topic did not change its score "
        f"({before['weak']} -> {after['weak']}); the score is not a function of "
        "the submitted evidence"
    )
    assert after["strong"] == before["strong"], (
        "a candidate whose evidence did not change scored differently "
        f"({before['strong']} -> {after['strong']}); the score depends on "
        "something other than that candidate's own evidence"
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

    ``unknown`` submitted ``expertise_topics: null`` — no expertise record
    exists — and must come back unscorable with a null score and a factor whose
    state is ``unknown``. ``weak`` submitted ``[]`` — the record exists and is
    empty — and must come back with a real, classified ``measured_zero``.

    A system that renders the first as 0 passes neither assertion, and a system
    that renders the second as unknown fails just as loudly. The whole point is
    that the two are different facts.
    """
    if flow.match_run_id is None:
        pytest.skip("step 09 did not produce a match run to inspect")
    assert flow.unit_id is not None

    run = json_body(api.get(f"/v1/units/{flow.unit_id}/match-runs/{flow.match_run_id}"))

    unscorable = {candidate["subject_id"]: candidate for candidate in run["unscorable"]}
    assert "unknown" in unscorable, (
        "the candidate with no expertise record was scored rather than reported "
        f"unscorable; unscorable holds {sorted(unscorable)}"
    )
    absent = unscorable["unknown"]
    assert absent["heuristic_score"] is None, (
        f"a candidate with no evidence scored {absent['heuristic_score']!r}; an "
        "absence of evidence is never a zero"
    )
    assert absent["state"] == "unknown"
    assert "topic_relevance" in absent["unknown_factor_keys"]

    absent_factor = next(
        factor for factor in absent["factors"] if factor["factor_key"] == "topic_relevance"
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
    assert "weak" in scored, "the candidate with an empty-but-present record was not scored"
    measured_zero = next(
        factor for factor in scored["weak"]["factors"] if factor["factor_key"] == "topic_relevance"
    )
    assert measured_zero["state"] == "measured"
    assert measured_zero["value"] == 0.0
    assert measured_zero["zero_classification"] == "measured_zero", (
        "an empty-but-present expertise record must be a measured zero, not "
        f"{measured_zero['zero_classification']!r} — otherwise it is "
        "indistinguishable from the unknown above"
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


def test_14_the_rewards_catalog_is_refused_to_a_coordinator(
    api: httpx.Client, flow: ClickThrough
) -> None:
    """The refusal is asserted; the catalog walk is skipped by name.

    Rewards operations are gated on the ``student`` role alone. The only
    principal this appliance can authenticate is a coordinator, so the catalog,
    the balance, and the redemption request cannot be exercised at all. The
    refusal itself is verified — a widening would be caught here — and then the
    step skips naming the decision it is waiting on. Nothing about
    authorization is changed to make this pass.
    """
    if flow.unit_id is None:
        pytest.skip("step 02 did not resolve a unit id from GET /v1/me")

    catalog = api.get(f"/v1/units/{flow.unit_id}/rewards")
    assert catalog.status_code == 403, (
        f"the rewards catalog answered {catalog.status_code} to a '{flow.role}' "
        f"principal, not the expected 403: {catalog.text[:300]}"
    )
    redemptions = api.get(f"/v1/units/{flow.unit_id}/redemptions")
    assert redemptions.status_code == 403, (
        f"the redemption self-read answered {redemptions.status_code} to a "
        f"'{flow.role}' principal, not the expected 403: {redemptions.text[:300]}"
    )

    pytest.skip(
        "coordinator cannot read the rewards catalog or request a redemption "
        "pending the D6 role decision (rewards is gated on the 'student' role "
        "alone, PR #32); the refusal above is asserted, the catalog walk is not run"
    )


def test_15_a_redemption_decision_has_nothing_to_decide(
    api: httpx.Client, flow: ClickThrough
) -> None:
    """The coordinator half of rewards, unreachable for want of the student half.

    ``POST /v1/units/{id}/redemptions/{id}/decision`` *is* gated on
    ``coordinator``, so this principal could act on a redemption — but only a
    student can create one, and no student principal exists on this appliance.
    The step is therefore blocked by the same D6 decision from the other side.
    """
    if flow.unit_id is None:
        pytest.skip("step 02 did not resolve a unit id from GET /v1/me")

    pytest.skip(
        "no redemption exists to decide on: creating one requires the 'student' "
        "role, which no compose principal holds, pending the D6 role decision. "
        "The coordinator-gated decision route is left unexercised rather than "
        "fed a fabricated redemption id"
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


def _await_terminal_job_state(api: httpx.Client, job_id: str) -> str:
    """Poll one job until it reaches *any* terminal state, and report which.

    Distinct from :func:`_await_job`, which asserts ``succeeded`` and reads the
    completion summary. A refused send is a job that legitimately ends
    ``failed_policy``, and a helper treating every non-success as a bug could
    not describe it. Bounded like every other wait here.
    """
    seen: dict[str, str] = {}

    def settled() -> bool:
        status = json_body(api.get(f"/v1/jobs/{job_id}"))["status"]
        seen["status"] = status
        return status in TERMINAL_JOB_STATES

    assert poll_until(
        f"job {job_id} reaches a terminal state",
        settled,
        attempts=POLL_ATTEMPTS,
        interval=1.0,
    ), f"job {job_id} never left status {seen.get('status')!r}"
    return seen["status"]


def _send_id_for_job(job_id: str) -> str:
    """The send row a command produced, read from the database.

    A recorded gap of the same shape as the review-item lookup: the ``202``
    hands back a job id, ``GET /v1/units/{id}/outreach/sends/{send_id}`` reads
    one send, and no route maps the first to the second. A *succeeded* job
    carries the send id in its completion summary and needs none of this; a
    refused one fails before it can report anything, and this is the only way
    to reach the refusal record it wrote.
    """
    return psql_scalar(f"select id from outreach_send where job_id = '{job_id}'")


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
    command is submitted. The suppression is recorded before the ``202``, so
    there is no race here to lose: whenever the worker gets to it, the refusal
    is already true.

    The job ends ``failed_policy`` — terminal, never retried into succeeding —
    and that is the honest outcome. A send that ended green while the recipient
    was never written to would be exactly the fake success this suite exists to
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
    assert response.status_code == 202, (
        f"submitting the second send returned {response.status_code}, expected "
        "202 — the route checks approval, and the worker is what re-checks "
        f"consent: {response.text[:400]}"
    )
    job_id = json_body(response)["job_id"]

    state = _await_terminal_job_state(api, job_id)
    assert state == "failed_policy", (
        f"the send to a suppressed recipient ended {state!r}. 'succeeded' would "
        "mean the gate did not run, or that the job reported a success it did "
        "not have; 'failed_provider' would mean this is retried into sending"
    )

    send = json_body(api.get(f"/v1/units/{flow.unit_id}/outreach/sends/{_send_id_for_job(job_id)}"))
    assert send["disposition"] == "blocked", (
        f"the refused send reads back {send['disposition']!r}, not 'blocked'"
    )
    assert send["provider_message_id"] is None, (
        "the refused send carries a provider_message_id, so something was handed "
        "to the provider after the recipient unsubscribed"
    )
    assert "suppress" in (send["failure_reason"] or ""), (
        f"the refusal reason is {send['failure_reason']!r} and does not name the "
        "suppression; a consent system must be able to answer why a person was "
        "not written to"
    )
    event_types = [event["event_type"] for event in send["delivery_events"]]
    assert "blocked" in event_types, f"the delivery events are {event_types} and record no refusal"
    assert "accepted" not in event_types, (
        f"the delivery events are {event_types}: a suppressed recipient's send "
        "recorded an acceptance"
    )

    print(f"  send to a suppressed recipient ended {state} / blocked")
