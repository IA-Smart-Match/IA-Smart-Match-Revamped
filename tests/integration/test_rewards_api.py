"""HTTP contracts for the S8 catalog and the S9 redemption command.

``tests/authz/test_policy_matrix.py`` owns the authorization rectangle for all
four operations and needs no database to run it. ``test_rewards_repository.py``
owns the ledger, the listing query, and the state machine against real rows.
What this file adds is the part that exists only over HTTP:

* that the unfunded row is absent from the JSON a student receives, because the
  server never selected it — not because a client filtered it;
* that the balance in the response is a fold over ledger rows, with the entry
  count beside it, and that "unknown" is a state the response can carry rather
  than a zero;
* that a redemption is opened for the *token's* subject and for nobody else,
  with no request field that could name another student;
* that ``fulfilled`` is unreachable except from ``approved``, over the wire and
  not only in the domain;
* and that the ledger debit lands exactly once, at fulfilment.

Lives under ``tests/integration/`` rather than ``tests/contract/`` for one
reason: the attendance rows behind every balance here need a real ``event`` and
a real owning unit, and ``conftest``'s :func:`ensure_event` /
:func:`ensure_owning_unit` are the one place that knows their honest shape. A
third variant of those helpers in ``tests/contract/`` is exactly what this
project has been bitten by before.

Every row is synthetic and written by this file. Nothing is seeded into a
migration, no point cost here is a ratified figure — the costs are D7's recorded
*tentative* bands, cited rather than invented — and no money moves.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest

pytest.importorskip("sqlalchemy")

from conftest import DATABASE_URL, ensure_event, ensure_owning_unit, unique_subject
from fastapi.testclient import TestClient
from smartmatch_api.main import app
from smartmatch_domain.rewards import (
    D7_TENTATIVE_POINT_BANDS,
    POINTS_PER_VERIFIED_ATTENDANCE,
)
from smartmatch_domain.synthetic_pilot import SYNTHETIC_ATTENDANCE_METHOD
from smartmatch_persistence.engine import create_session_factory
from smartmatch_persistence.rewards import RewardsRepository
from smartmatch_providers import FixtureTokenVerifier
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.integration

#: A second department in the same tenant, containing none of the unit the
#: principals below are granted at.
SIBLING_UNIT_PATH = "iawest.rewards-sibling"

#: D7's recorded tentative bands, used as fixture costs so no number in this file
#: is one this file invented. ``docs/decisions/pilot-decisions.md`` §D7 records
#: all three as tentative and this file promotes none of them.
CHEAP_COST, MID_COST, DEAR_COST = D7_TENTATIVE_POINT_BANDS

#: Verified attendances credited to the funded student. Three at D7's tentative
#: rate is 300 points, which is exactly ``CHEAP_COST`` — the calibration property
#: ``test_rewards_repository.py`` already proves, reused here so the affordable
#: and unaffordable cases are both present without a fourth invented number.
CREDITED_ATTENDANCES = 3


class Fixture:
    """Everything one test needs, assembled once per test by :func:`rewards_api`."""

    def __init__(
        self,
        client: TestClient,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        sibling_unit_id: uuid.UUID,
    ) -> None:
        self.client = client
        self.tenant_id = tenant_id
        self.unit_id = unit_id
        self.sibling_unit_id = sibling_unit_id
        self.tokens: dict[str, str] = {}
        self.users: dict[str, uuid.UUID] = {}
        self.items: dict[str, uuid.UUID] = {}

    # -- request helpers ---------------------------------------------------

    def get(self, suffix: str, who: str):
        return self.client.get(self._url(suffix), headers=self._headers(who))

    def post(self, suffix: str, who: str, body: dict[str, object]):
        return self.client.post(self._url(suffix), headers=self._headers(who), json=body)

    def _url(self, suffix: str) -> str:
        return f"/v1/units/{self.unit_id}{suffix}"

    def _headers(self, who: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.tokens[who]}"}


def _insert_user(conn, tenant_id: uuid.UUID, label: str) -> tuple[uuid.UUID, str]:
    """One ``user_account`` row, and the identity-provider subject naming it."""
    user_id = uuid.uuid4()
    subject = unique_subject(f"rewards-api-{label}-{user_id.hex[:8]}")
    conn.execute(
        text(
            "INSERT INTO user_account (id, tenant_id, external_subject, email) "
            "VALUES (:id, :tid, :sub, :email)"
        ),
        {"id": user_id, "tid": tenant_id, "sub": subject, "email": f"{subject}@example.edu"},
    )
    return user_id, subject


def _grant(conn, tenant_id: uuid.UUID, user_id: uuid.UUID, path: str, role: str) -> None:
    conn.execute(
        text(
            "INSERT INTO membership (id, tenant_id, user_id, granted_path, role) "
            "VALUES (:id, :tid, :uid, CAST(:path AS ltree), :role)"
        ),
        {"id": uuid.uuid4(), "tid": tenant_id, "uid": user_id, "path": path, "role": role},
    )


def _insert_item(
    conn,
    tenant_id: uuid.UUID,
    *,
    name: str,
    cost: int,
    owner_id: uuid.UUID,
    funded: bool,
) -> uuid.UUID:
    """One synthetic ``reward_item``.

    ``fulfilment_cost`` is zero because ``ck_reward_item_fulfilment_cost_non_negative``
    requires a value and nothing on this surface reads, spends, or discloses it.
    Not a claim that a real reward costs nothing.
    """
    item_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO reward_item "
            "(id, tenant_id, name, points_cost, fulfilment_cost, budget_owner_id, funded) "
            "VALUES (:id, :tid, :name, :cost, 0, :owner, :funded)"
        ),
        {
            "id": item_id,
            "tid": tenant_id,
            "name": name,
            "cost": cost,
            "owner": owner_id,
            "funded": funded,
        },
    )
    return item_id


def _record_attendance(session: Session, tenant_id: uuid.UUID, subject_id: uuid.UUID) -> uuid.UUID:
    """One verified attendance at its own synthetic event.

    Same shape as ``test_rewards_repository.py``'s helper and for the same
    reasons: ``coordinator_entry``, a real ``event`` from
    :func:`~conftest.ensure_event`, and a per-record slug so
    ``uq_attendance_record_subject_event`` does not refuse the second one.
    """
    record_id = uuid.uuid4()
    session.execute(
        text(
            "INSERT INTO attendance_record "
            "(id, tenant_id, owning_unit_id, subject_id, event_id, method) "
            "VALUES (:id, :tid, :unit, :subject, :event, :method)"
        ),
        {
            "id": record_id,
            "tid": tenant_id,
            "unit": ensure_owning_unit(session, tenant_id),
            "subject": subject_id,
            "event": ensure_event(session, tenant_id, f"rewards-api-{record_id.hex[:8]}"),
            "method": SYNTHETIC_ATTENDANCE_METHOD,
        },
    )
    return record_id


@pytest.fixture(scope="module")
def engine_or_skip() -> Engine:
    """A live migrated PostgreSQL engine, or skip this contract."""
    try:
        eng = create_engine(DATABASE_URL, future=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1 FROM redemption LIMIT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}")
    return eng


@pytest.fixture
def rewards_api(engine_or_skip: Engine) -> Iterator[Fixture]:
    """One tenant, five principals, three reward items, and a credited ledger.

    Its own tenant rather than ``conftest``'s shared one, so teardown is this
    file's and cannot race another module's — the same choice
    ``tests/contract/test_events_api.py`` makes.
    """
    engine = engine_or_skip
    tenant_id = uuid.uuid4()

    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": tenant_id, "slug": f"test-rewards-{tenant_id.hex[:12]}"},
        )
        unit_id = ensure_owning_unit(conn, tenant_id)
        unit_path = conn.execute(
            text("SELECT CAST(path AS text) FROM org_unit WHERE id = :id"), {"id": unit_id}
        ).scalar_one()

        sibling_unit_id = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                "VALUES (:id, :tid, CAST(:path AS ltree), 'department', 'Rewards Sibling')"
            ),
            {"id": sibling_unit_id, "tid": tenant_id, "path": SIBLING_UNIT_PATH},
        )

        fixture = Fixture(TestClient(app), tenant_id, unit_id, sibling_unit_id)

        for label, role, path in (
            ("student", "student", unit_path),
            ("other_student", "student", unit_path),
            ("uncredited_student", "student", unit_path),
            ("coordinator", "coordinator", unit_path),
            ("sibling_student", "student", SIBLING_UNIT_PATH),
        ):
            user_id, subject = _insert_user(conn, tenant_id, label)
            _grant(conn, tenant_id, user_id, path, role)
            fixture.users[label] = user_id
            fixture.tokens[label] = subject

        owner_id, _ = _insert_user(conn, tenant_id, "budget-owner")
        fixture.items["cheap"] = _insert_item(
            conn,
            tenant_id,
            name="Synthetic cheap reward",
            cost=CHEAP_COST,
            owner_id=owner_id,
            funded=True,
        )
        fixture.items["dear"] = _insert_item(
            conn,
            tenant_id,
            name="Synthetic dear reward",
            cost=DEAR_COST,
            owner_id=owner_id,
            funded=True,
        )
        # Cheaper than everything funded, so if it ever leaked it would sort
        # first and be impossible to miss.
        fixture.items["unfunded"] = _insert_item(
            conn,
            tenant_id,
            name="Synthetic unfunded reward",
            cost=1,
            owner_id=owner_id,
            funded=False,
        )

    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    session = session_factory()
    repository = RewardsRepository()
    try:
        for _ in range(CREDITED_ATTENDANCES):
            attendance_id = _record_attendance(session, tenant_id, fixture.users["student"])
            repository.credit_attendance(session, tenant_id=tenant_id, attendance_id=attendance_id)
        # Attendance on file, deliberately uncredited: the shape that makes a
        # balance unknown rather than zero.
        _record_attendance(session, tenant_id, fixture.users["uncredited_student"])
        session.commit()
    finally:
        session.rollback()
        session.close()

    verifier = FixtureTokenVerifier()
    for label, subject in fixture.tokens.items():
        token = f"tok-rewards-{uuid.uuid4().hex}"
        verifier.register(token, subject)
        fixture.tokens[label] = token

    fixture.client.app.state.session_factory = create_session_factory(
        engine.url.render_as_string(hide_password=False)
    )
    fixture.client.app.state.token_verifier = verifier

    yield fixture

    with engine.begin() as conn:
        for table in (
            "point_ledger_entry",
            "redemption",
            "attendance_record",
            "reward_item",
            "event",
            "membership",
            "resource_grant",
            "user_account",
            "org_unit",
            "rate_limit_counter",
        ):
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": tenant_id})
        conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tenant_id})


def _ledger_rows(engine: Engine, tenant_id: uuid.UUID) -> list:
    """Every ledger row, read with this file's own SQL rather than the repository.

    A test proving the debit landed once must not ask the writer how many rows
    it wrote.
    """
    with engine.connect() as conn:
        return list(
            conn.execute(
                text("SELECT kind, amount FROM point_ledger_entry WHERE tenant_id = :tid"),
                {"tid": tenant_id},
            ).all()
        )


# ---------------------------------------------------------------------------
# S8 — the catalog
# ---------------------------------------------------------------------------


def test_the_unfunded_item_is_absent_from_the_catalog(rewards_api: Fixture) -> None:
    """D6's rule reaches the JSON, and it is the query that enforces it.

    The unfunded fixture costs 1 point, so a catalog that leaked it would list it
    *first* and every student could afford it. Its absence is the whole of D6
    arriving over HTTP.
    """
    response = rewards_api.get("/rewards", "student")
    assert response.status_code == 200, response.text

    listed = {item["item_id"] for item in response.json()["items"]}
    assert str(rewards_api.items["unfunded"]) not in listed
    assert listed == {str(rewards_api.items["cheap"]), str(rewards_api.items["dear"])}


def test_the_catalog_is_ordered_by_cost_and_carries_no_funding_flag(rewards_api: Fixture) -> None:
    """Cheapest first, and no ``funded`` field for a client to have to trust.

    Every item present is listable by construction, so a boolean saying so would
    invite a client to render the case the server never sends.
    """
    items = rewards_api.get("/rewards", "student").json()["items"]
    assert [item["points_cost"] for item in items] == [CHEAP_COST, DEAR_COST]
    assert all("funded" not in item and "budget_owner_id" not in item for item in items)


def test_the_balance_is_a_measured_fold_with_its_entry_count(rewards_api: Fixture) -> None:
    """The number, and the evidence that makes it a number.

    Three credits at D7's tentative rate. ``ledger_entry_count`` is what tells a
    reader this is a fold rather than a stored counter, and it is what would make
    a zero readable as measured.
    """
    balance = rewards_api.get("/rewards", "student").json()["balance"]
    assert balance["state"] == "measured"
    assert balance["points"] == CREDITED_ATTENDANCES * POINTS_PER_VERIFIED_ATTENDANCE
    assert balance["ledger_entry_count"] == CREDITED_ATTENDANCES
    assert balance["unknown_reason"] is None


def test_progress_is_zero_for_an_affordable_item_and_measured_for_a_distant_one(
    rewards_api: Fixture,
) -> None:
    """``0`` here means "affordable now", which is a checkable claim.

    Deliberately not the same thing as the ``null`` the unknown case carries: a
    client renders a request button for the first and no progress bar at all for
    the second.
    """
    items = {
        item["item_id"]: item for item in rewards_api.get("/rewards", "student").json()["items"]
    }

    cheap = items[str(rewards_api.items["cheap"])]
    assert cheap["affordable"] is True
    assert cheap["progress_state"] == "measured"
    assert cheap["points_still_needed"] == 0
    assert cheap["events_still_needed"] == 0

    dear = items[str(rewards_api.items["dear"])]
    balance = CREDITED_ATTENDANCES * POINTS_PER_VERIFIED_ATTENDANCE
    assert dear["affordable"] is False
    assert dear["progress_state"] == "measured"
    assert dear["points_still_needed"] == DEAR_COST - balance
    # Ceiling division, as `events_still_needed` performs it — restated here
    # rather than imported, so the arithmetic is checked and not merely echoed.
    assert dear["events_still_needed"] == -(
        -(DEAR_COST - balance) // POINTS_PER_VERIFIED_ATTENDANCE
    )


def test_a_student_with_uncredited_attendance_has_an_unknown_balance_not_a_zero(
    rewards_api: Fixture,
) -> None:
    """ADR-0011, in the one case a fold cannot see on its own.

    Attendance is on file and no ledger entry derives from it. ``0`` there would
    be a claim this student's own attendance record contradicts, so the response
    says ``unknown`` and carries no number at all — and, consequently, describes
    no item as affordable and offers no distance to one.
    """
    body = rewards_api.get("/rewards", "uncredited_student").json()

    assert body["balance"]["state"] == "unknown"
    assert body["balance"]["points"] is None
    assert body["balance"]["ledger_entry_count"] == 0
    assert body["balance"]["unknown_reason"]

    assert body["items"], "the catalog is still listed; it is the balance that is unknown"
    for item in body["items"]:
        assert item["affordable"] is False
        assert item["progress_state"] == "unknown"
        assert item["points_still_needed"] is None
        assert item["events_still_needed"] is None


def test_a_student_who_has_attended_nothing_has_a_measured_zero(rewards_api: Fixture) -> None:
    """The other half of the same rule, and why it is not "null whenever empty".

    Nothing attended, nothing earned: that is a fact about this student, not the
    absence of one, and ``fold_balance``'s own docstring settles it. The entry
    count beside it is the evidence.
    """
    balance = rewards_api.get("/rewards", "other_student").json()["balance"]
    assert balance["state"] == "measured"
    assert balance["points"] == 0
    assert balance["ledger_entry_count"] == 0


def test_the_response_names_the_earn_rate_it_used_and_calls_it_unratified(
    rewards_api: Fixture,
) -> None:
    """A tentative number reported as tentative.

    D7 is not ratified, so the response says so rather than letting a client
    present the rate as settled policy.
    """
    body = rewards_api.get("/rewards", "student").json()
    assert body["points_per_verified_attendance"] == POINTS_PER_VERIFIED_ATTENDANCE
    assert body["earn_policy_ratified"] is False


# ---------------------------------------------------------------------------
# S9 — redemption
# ---------------------------------------------------------------------------


def test_a_redemption_opens_in_requested_and_never_in_approved(rewards_api: Fixture) -> None:
    """The approval step is ADR-0013's, and no request argument can skip it."""
    response = rewards_api.post(
        "/redemptions", "student", {"item_id": str(rewards_api.items["cheap"])}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["state"] == "requested"
    assert body["item_id"] == str(rewards_api.items["cheap"])
    assert body["points_cost"] == CHEAP_COST


def test_a_second_request_for_the_same_item_resolves_to_the_same_redemption(
    rewards_api: Fixture,
) -> None:
    """Card L4's idempotency, enforced by ``uq_redemption_open_per_item``."""
    first = rewards_api.post(
        "/redemptions", "student", {"item_id": str(rewards_api.items["cheap"])}
    )
    second = rewards_api.post(
        "/redemptions", "student", {"item_id": str(rewards_api.items["cheap"])}
    )
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["redemption_id"] == second.json()["redemption_id"]


def test_the_unfunded_item_cannot_be_redeemed_even_when_its_id_is_known(
    rewards_api: Fixture,
) -> None:
    """Absence from the catalog is not the only thing keeping an unfunded item out.

    The listing hides it; this refuses it. A caller who learned the id some other
    way still cannot redeem against a reward nobody will honour, and the refusal
    is D6's rather than an affordability one — the row costs a single point.
    """
    response = rewards_api.post(
        "/redemptions", "student", {"item_id": str(rewards_api.items["unfunded"])}
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "reward_item_not_listable"


def test_a_balance_that_does_not_cover_the_item_is_refused(rewards_api: Fixture) -> None:
    response = rewards_api.post(
        "/redemptions", "student", {"item_id": str(rewards_api.items["dear"])}
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "insufficient_balance"


def test_an_unknown_balance_is_refused_as_unknown_and_not_as_zero(rewards_api: Fixture) -> None:
    """The refusal a student sees names the right reason.

    ``insufficient_balance`` here would report a balance of 0 the server has just
    said it does not know, which is the ADR-0011 defect wearing an error code.
    """
    response = rewards_api.post(
        "/redemptions", "uncredited_student", {"item_id": str(rewards_api.items["cheap"])}
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "balance_unknown"


def test_an_unknown_item_is_a_404(rewards_api: Fixture) -> None:
    response = rewards_api.post("/redemptions", "student", {"item_id": str(uuid.uuid4())})
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "reward_item_not_found"


def test_the_subject_comes_from_the_token_and_a_body_field_cannot_move_it(
    rewards_api: Fixture, engine_or_skip: Engine
) -> None:
    """MM-A01, checked rather than assumed.

    A body naming another student is not merely ignored — ``RedemptionRequest``
    has no such field, so the request is refused outright by the standard
    validation envelope before the handler runs. Both halves are asserted: the
    refusal, and that the honest request files the redemption under the token's
    own subject.
    """
    smuggled = rewards_api.post(
        "/redemptions",
        "student",
        {
            "item_id": str(rewards_api.items["cheap"]),
            "subject_id": str(rewards_api.users["other_student"]),
        },
    )
    assert smuggled.status_code == 422, smuggled.text

    honest = rewards_api.post(
        "/redemptions", "student", {"item_id": str(rewards_api.items["cheap"])}
    )
    assert honest.status_code == 201, honest.text
    with engine_or_skip.connect() as conn:
        owner = conn.execute(
            text("SELECT subject_id FROM redemption WHERE id = :id"),
            {"id": uuid.UUID(honest.json()["redemption_id"])},
        ).scalar_one()
    assert uuid.UUID(str(owner)) == rewards_api.users["student"]


def test_a_student_sees_their_own_tickets_and_nobody_elses(rewards_api: Fixture) -> None:
    """The self-read is scoped in the query, so there is no filtered-out case."""
    mine = rewards_api.post(
        "/redemptions", "student", {"item_id": str(rewards_api.items["cheap"])}
    ).json()

    own = rewards_api.get("/redemptions", "student").json()["redemptions"]
    assert [ticket["redemption_id"] for ticket in own] == [mine["redemption_id"]]

    others = rewards_api.get("/redemptions", "other_student").json()["redemptions"]
    assert others == []


# ---------------------------------------------------------------------------
# The state machine, over HTTP
# ---------------------------------------------------------------------------


def _open_ticket(rewards_api: Fixture) -> str:
    response = rewards_api.post(
        "/redemptions", "student", {"item_id": str(rewards_api.items["cheap"])}
    )
    assert response.status_code == 201, response.text
    return str(response.json()["redemption_id"])


def test_fulfilment_is_unreachable_from_requested(rewards_api: Fixture) -> None:
    """``fulfilled`` only from ``approved`` — the approval step cannot be jumped.

    Refused by the state machine before any ``UPDATE`` is attempted, and refused
    again by ``ck_redemption_approval_evidence`` if it somehow were.
    """
    redemption_id = _open_ticket(rewards_api)
    response = rewards_api.post(
        f"/redemptions/{redemption_id}/decision", "coordinator", {"decision": "fulfilled"}
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "invalid_redemption_transition"


def test_approval_then_fulfilment_takes_exactly_one_debit(
    rewards_api: Fixture, engine_or_skip: Engine
) -> None:
    """The whole path, and the one ledger row it is allowed to write.

    The debit is taken at *fulfilment*, not at request — migration ``0019`` added
    no refund kind, so a debit taken earlier could not be returned if the ticket
    were later denied. After it, the student's balance is a measured zero folded
    from four entries: three credits and one debit.
    """
    redemption_id = _open_ticket(rewards_api)

    approved = rewards_api.post(
        f"/redemptions/{redemption_id}/decision", "coordinator", {"decision": "approved"}
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["state"] == "approved"

    # Still three rows: approval moves the ticket and touches no ledger.
    assert len(_ledger_rows(engine_or_skip, rewards_api.tenant_id)) == CREDITED_ATTENDANCES

    fulfilled = rewards_api.post(
        f"/redemptions/{redemption_id}/decision", "coordinator", {"decision": "fulfilled"}
    )
    assert fulfilled.status_code == 200, fulfilled.text
    assert fulfilled.json()["state"] == "fulfilled"

    rows = _ledger_rows(engine_or_skip, rewards_api.tenant_id)
    debits = [row for row in rows if row.kind == "redemption_debit"]
    assert len(debits) == 1
    assert debits[0].amount == -CHEAP_COST

    balance = rewards_api.get("/rewards", "student").json()["balance"]
    assert balance["state"] == "measured"
    assert balance["points"] == 0
    assert balance["ledger_entry_count"] == CREDITED_ATTENDANCES + 1


def test_a_fulfilled_redemption_cannot_be_moved_again(rewards_api: Fixture) -> None:
    """A terminal state that could be re-entered is a fulfilment that repeats."""
    redemption_id = _open_ticket(rewards_api)
    rewards_api.post(
        f"/redemptions/{redemption_id}/decision", "coordinator", {"decision": "approved"}
    )
    rewards_api.post(
        f"/redemptions/{redemption_id}/decision", "coordinator", {"decision": "fulfilled"}
    )

    again = rewards_api.post(
        f"/redemptions/{redemption_id}/decision", "coordinator", {"decision": "fulfilled"}
    )
    assert again.status_code == 409, again.text
    assert again.json()["error"]["code"] == "invalid_redemption_transition"


def test_a_denial_is_terminal_and_debits_nothing(
    rewards_api: Fixture, engine_or_skip: Engine
) -> None:
    redemption_id = _open_ticket(rewards_api)
    denied = rewards_api.post(
        f"/redemptions/{redemption_id}/decision", "coordinator", {"decision": "denied"}
    )
    assert denied.status_code == 200, denied.text
    assert denied.json()["state"] == "denied"
    assert len(_ledger_rows(engine_or_skip, rewards_api.tenant_id)) == CREDITED_ATTENDANCES


def test_expiry_is_not_an_http_command(rewards_api: Fixture) -> None:
    """An expiry has no author, and every HTTP command has one.

    Refused by the request model before the handler runs, so the route cannot
    record a person as having done something time does.
    """
    redemption_id = _open_ticket(rewards_api)
    response = rewards_api.post(
        f"/redemptions/{redemption_id}/decision", "coordinator", {"decision": "expired"}
    )
    assert response.status_code == 422, response.text


def test_an_unknown_redemption_is_a_404(rewards_api: Fixture) -> None:
    response = rewards_api.post(
        f"/redemptions/{uuid.uuid4()}/decision", "coordinator", {"decision": "approved"}
    )
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "redemption_not_found"


# ---------------------------------------------------------------------------
# Authorization, reached over HTTP
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("suffix", ["/rewards", "/redemptions"])
def test_an_unauthenticated_caller_is_refused(rewards_api: Fixture, suffix: str) -> None:
    response = rewards_api.client.get(f"/v1/units/{rewards_api.unit_id}{suffix}")
    assert response.status_code == 401


def test_a_coordinator_cannot_read_the_student_rewards_surface(rewards_api: Fixture) -> None:
    """Deny-by-default: no artifact names a coordinator read role, so there is none."""
    assert rewards_api.get("/rewards", "coordinator").status_code == 403
    assert rewards_api.get("/redemptions", "coordinator").status_code == 403


def test_a_student_cannot_decide_their_own_redemption(rewards_api: Fixture) -> None:
    """The cell that matters most on this surface.

    A student approving their own request would delete ADR-0013's approval step;
    fulfilling it would let them hand themselves the reward and take the debit.
    """
    redemption_id = _open_ticket(rewards_api)
    response = rewards_api.post(
        f"/redemptions/{redemption_id}/decision", "student", {"decision": "approved"}
    )
    assert response.status_code == 403, response.text


def test_a_student_in_a_sibling_department_is_refused(rewards_api: Fixture) -> None:
    """Unit scoping applies even though ``reward_item`` is tenant-scoped.

    The unit in the path is the authorization scope, and a membership that does
    not cover it does not reach the route — which is what makes the path's unit
    load-bearing rather than decorative.
    """
    assert rewards_api.get("/rewards", "sibling_student").status_code == 403


def test_an_unknown_unit_is_a_404_and_not_a_403(rewards_api: Fixture) -> None:
    """A unit outside the caller's tenant is indistinguishable from one that is absent."""
    response = rewards_api.client.get(
        f"/v1/units/{uuid.uuid4()}/rewards",
        headers={"Authorization": f"Bearer {rewards_api.tokens['student']}"},
    )
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "unit_not_found"


def test_the_catalog_of_another_tenant_is_never_reachable(
    rewards_api: Fixture, engine_or_skip: Engine
) -> None:
    """Tenant isolation on the listing itself, not only on the unit lookup.

    A second tenant's funded item is cheaper than anything in this one, so a
    listing that ignored the tenant would put it first.
    """
    other_tenant = uuid.uuid4()
    with engine_or_skip.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": other_tenant, "slug": f"test-rewards-other-{other_tenant.hex[:12]}"},
        )
        owner_id, _ = _insert_user(conn, other_tenant, "other-owner")
        foreign_item = _insert_item(
            conn, other_tenant, name="Other tenant reward", cost=1, owner_id=owner_id, funded=True
        )

    try:
        listed = {
            item["item_id"] for item in rewards_api.get("/rewards", "student").json()["items"]
        }
        assert str(foreign_item) not in listed
    finally:
        with engine_or_skip.begin() as conn:
            for table in ("reward_item", "user_account"):
                conn.execute(
                    text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": other_tenant}
                )
            conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": other_tenant})


def test_the_recorded_bands_are_cited_in_order(rewards_api: Fixture) -> None:
    """A guard against this file quietly inventing a fourth number.

    ``MID_COST`` is D7's middle recorded band. It is deliberately not seeded as
    an item — two funded items are enough to prove the affordable and
    unaffordable cases — and this assertion is why unpacking all three bands is a
    citation of the recorded list rather than a leftover.
    """
    assert CHEAP_COST < MID_COST < DEAR_COST
    assert rewards_api.get("/rewards", "student").status_code == 200
