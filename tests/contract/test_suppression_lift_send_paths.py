"""A ``lifted_at`` contract test per send path (B26 T6b-3 plan §8).

Every consumer in the plan's §5.1 table reads send eligibility through one of
three readers (R1 ``ContactChannelRow.suppressed``, R2 ``load_recipient``, R3
``is_suppressed``). Today all three treat *any* ``suppression_record`` row as a
live suppression. T6b-3 makes them read only rows with ``lifted_at IS NULL``.

Each test here drives one consumer over its real HTTP route and is parametrized
over the four suppression states :func:`_seed_suppression_state` produces:

========== ========================================== ===============
State      Rows                                       Send-eligible
========== ========================================== ===============
NONE       no row                                     yes
ACTIVE     active ``unsubscribe_link`` row            no
LIFTED     that row lifted by a user in the tenant    **yes**
REOPENED   lifted, then re-suppressed through W1      no
========== ========================================== ===============

Against today's readers only the ``LIFTED`` cases fail. Any other failure means
the fixture is wrong, not the code.

:data:`SEND_PATHS` maps every §5.1 consumer to the test that pins it, and
:func:`test_every_send_path_has_a_lifted_at_test` proves each named test exists.

Requires a live migrated PostgreSQL, and is skipped when none is reachable.
Every address is on the RFC 2606 reserved ``.invalid`` TLD.
"""

from __future__ import annotations

import ast
import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from smartmatch_api.errors import EXCEPTION_HANDLERS
from smartmatch_api.main import app
from smartmatch_api.routers import speaker_portal as portal_router
from smartmatch_persistence.engine import create_session_factory
from smartmatch_persistence.outreach import OutreachRepository
from smartmatch_providers import FixtureTokenVerifier
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

DATABASE_URL = os.getenv(
    "SMARTMATCH_DATABASE_URL",
    "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch",
)

REPO_ROOT = Path(__file__).resolve().parents[2]

UNIT_PATH = "iawest.liftpaths"

TEMPLATE_ID = "pilot.event_invitation.v1"
VALUES = {
    "professional_name": "Sam Rivera",
    "unit_name": "Northside Robotics",
    "event_name": "Spring Showcase",
    "event_date": "Friday, 12 June",
    "coordinator_name": "Alex Chen",
}
EVIDENCE = "signed consent form, filed 2026-09-05"

#: The §5.1 consumer table, each mapped to the test that pins it against
#: ``lifted_at``. C11 (``GET /v1/me/contact-channels``) is added with its route.
SEND_PATHS: dict[str, str] = {
    "C1": (
        "tests/integration/test_outreach_handler.py"
        "::TestLiftedSuppression::test_delivery_recheck_honours_lifted_at"
    ),
    "C2": "tests/contract/test_suppression_lift_send_paths.py::test_generic_compose",
    "C3": "tests/contract/test_suppression_lift_send_paths.py::test_generic_send",
    "C4": "tests/contract/test_suppression_lift_send_paths.py::test_cba_batch_creation",
    "C5": "tests/contract/test_suppression_lift_send_paths.py::test_cba_dispatch",
    "C6": (
        "tests/contract/test_suppression_lift_send_paths.py"
        "::test_connector_views_report_the_live_suppression"
    ),
    "C7": (
        "tests/contract/test_suppression_lift_send_paths.py"
        "::test_register_refuses_only_an_active_suppression"
    ),
    "C8": (
        "tests/contract/test_suppression_lift_send_paths.py"
        "::test_escalation_is_refused_only_under_an_active_suppression"
    ),
    "C9": (
        "tests/contract/test_suppression_lift_send_paths.py"
        "::test_connector_views_report_the_live_suppression"
    ),
    "C10": "tests/contract/test_suppression_lift_send_paths.py::test_portal_invite_eligibility",
}


# ---------------------------------------------------------------------------
# The four suppression states (copied verbatim into test_outreach_handler.py)
# ---------------------------------------------------------------------------

SUPPRESSION_STATES = ("NONE", "ACTIVE", "LIFTED", "REOPENED")
#: Whether a channel whose address is in each state may be written to.
SEND_ELIGIBLE = {"NONE": True, "ACTIVE": False, "LIFTED": True, "REOPENED": False}

_SUPPRESSED_AT = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
_LIFTED_AT = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
_REOPENED_AT = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


def _seed_suppression_state(
    session: Session,
    state: str,
    *,
    tenant_id: uuid.UUID,
    address: str,
    lifter_user_id: uuid.UUID,
) -> None:
    """Put ``address`` into one of the four suppression states. Caller commits.

    ``NONE`` writes nothing. ``ACTIVE`` writes one ``unsubscribe_link`` row.
    ``LIFTED`` lifts that row by direct SQL, as the Speaker would through
    ``SuppressionRepository.lift``: ``lifted_at`` after ``suppressed_at`` and
    ``lifted_by_user_id`` a real account in the tenant. ``REOPENED`` then
    re-suppresses through the shipped writer, ``OutreachRepository.suppress``
    (W1), with a later ``suppressed_at``.
    """
    if state not in SUPPRESSION_STATES:
        raise ValueError(f"unknown suppression state {state!r}")
    if state == "NONE":
        return
    session.execute(
        text(
            "INSERT INTO suppression_record (id, tenant_id, address, suppressed_at, source) "
            "VALUES (:i, :t, :a, :at, 'unsubscribe_link')"
        ),
        {"i": uuid.uuid4(), "t": tenant_id, "a": address, "at": _SUPPRESSED_AT},
    )
    if state == "ACTIVE":
        return
    session.execute(
        text(
            "UPDATE suppression_record SET lifted_at = :l, lifted_by_user_id = :u "
            "WHERE tenant_id = :t AND address = :a"
        ),
        {"l": _LIFTED_AT, "u": lifter_user_id, "t": tenant_id, "a": address},
    )
    if state == "LIFTED":
        return
    OutreachRepository().suppress(
        session,
        tenant_id=tenant_id,
        address=address,
        source="unsubscribe_link",
        suppressed_at=_REOPENED_AT,
    )


# ---------------------------------------------------------------------------
# One tenant, one Connector, one unit, one sendable roster contact
# ---------------------------------------------------------------------------

_CLEANUP = (
    "pilot_session",
    "pilot_credential",
    "speaker_portal_invitation",
    "cba_invitation",
    "cba_invitation_batch",
    "job_event",
    "outbox_record",
    "redrive_record",
    "delivery_event",
    "outreach_send",
    "outreach_draft",
    "contact_channel_transition",
    "contact_channel",
    "suppression_record",
    "job",
    "idempotency_record",
    "speaker_profile",
    "professional_unit_relationship",
    "membership",
    "resource_grant",
    "user_account",
    "org_unit",
    "rate_limit_counter",
)


def _portal_app(session_factory: Any, verifier: FixtureTokenVerifier) -> FastAPI:
    """T6b-1's capability-on stub, as ``test_speaker_portal_api.py`` builds it."""
    portal_app = FastAPI()
    for exception_type, handler in EXCEPTION_HANDLERS.items():
        portal_app.add_exception_handler(exception_type, handler)
    for router in (portal_router.router, portal_router.public_router):
        portal_app.include_router(router)
    portal_app.state.session_factory = session_factory
    portal_app.state.token_verifier = verifier
    portal_app.state.speaker_portal_token_secret = f"lift-{uuid.uuid4().hex}{uuid.uuid4().hex}"
    return portal_app


class _Context:
    def __init__(
        self,
        engine: Engine,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        coordinator_id: uuid.UUID,
        bearer: str,
        verifier: FixtureTokenVerifier,
    ) -> None:
        self.engine = engine
        self.tenant_id = tenant_id
        self.unit_id = unit_id
        self.coordinator_id = coordinator_id
        self.bearer = bearer
        session_factory = create_session_factory(engine.url.render_as_string(hide_password=False))
        self.client = TestClient(app)
        self.client.app.state.session_factory = session_factory
        self.client.app.state.token_verifier = verifier
        self.portal_client = TestClient(_portal_app(session_factory, verifier))
        self.professional_id, self.channel_id, self.address = self.roster_contact()

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.bearer}"}

    # -- set-up ------------------------------------------------------------

    def roster_contact(
        self, *, with_channel: bool = True
    ) -> tuple[uuid.UUID, uuid.UUID | None, str]:
        """``(professional_id, channel_id, address)`` for a new §13 roster contact.

        With a channel, it is ``active_candidate`` on ``self_service`` consent:
        the one shape every send path accepts when nothing is suppressed.
        """
        professional_id = uuid.uuid4()
        channel_id = uuid.uuid4() if with_channel else None
        address = f"speaker-{professional_id.hex[:8]}@synthetic.invalid"
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO user_account (id, tenant_id, external_subject, email) "
                    "VALUES (:id, :t, :s, :e)"
                ),
                {
                    "id": professional_id,
                    "t": self.tenant_id,
                    "s": f"sub-lift-{professional_id.hex}",
                    "e": f"{professional_id.hex[:8]}@placeholder.invalid",
                },
            )
            conn.execute(
                text(
                    "INSERT INTO speaker_profile (tenant_id, professional_id, owning_unit_id, "
                    "full_name) VALUES (:t, :p, :u, 'Sam Rivera')"
                ),
                {"t": self.tenant_id, "p": professional_id, "u": self.unit_id},
            )
            if channel_id is not None:
                conn.execute(
                    text(
                        "INSERT INTO contact_channel (id, tenant_id, owning_unit_id, "
                        "professional_id, channel_kind, address, contact_state, "
                        "consent_source, consent_recorded_at) VALUES (:id, :t, :u, :p, "
                        "'email', :a, 'active_candidate', 'self_service', now())"
                    ),
                    {
                        "id": channel_id,
                        "t": self.tenant_id,
                        "u": self.unit_id,
                        "p": professional_id,
                        "a": address,
                    },
                )
        return professional_id, channel_id, address

    def seed(self, state: str, address: str | None = None) -> None:
        with Session(self.engine) as session:
            _seed_suppression_state(
                session,
                state,
                tenant_id=self.tenant_id,
                address=address or self.address,
                lifter_user_id=self.professional_id,
            )
            session.commit()

    # -- generic outreach (C2, C3, C9) --------------------------------------

    def compose(self):
        return self.client.post(
            f"/v1/units/{self.unit_id}/outreach/drafts",
            json={
                "contact_channel_id": str(self.channel_id),
                "template_id": TEMPLATE_ID,
                "values": VALUES,
                "approve": True,
            },
            headers=self.headers,
        )

    def send(self, draft_id: str):
        return self.client.post(
            f"/v1/units/{self.unit_id}/outreach/drafts/{draft_id}/send",
            headers={**self.headers, "Idempotency-Key": f"idem-{uuid.uuid4().hex}"},
        )

    def list_contacts(self):
        return self.client.get(f"/v1/units/{self.unit_id}/outreach/contacts", headers=self.headers)

    def read_contact(self):
        return self.client.get(
            f"/v1/units/{self.unit_id}/outreach/contacts/{self.channel_id}", headers=self.headers
        )

    # -- CBA invitations (C4, C5) -------------------------------------------

    def create_batch(self):
        return self.client.post(
            f"/v1/units/{self.unit_id}/speaker-invitations/batches",
            json={
                "professional_ids": [str(self.professional_id)],
                "event_name": "Spring Showcase",
                "event_date": "Friday, 12 June",
                "coordinator_name": "Dana Okafor",
            },
            headers={**self.headers, "Idempotency-Key": f"batch-{uuid.uuid4().hex}"},
        )

    def dispatch(self, batch_id: str):
        return self.client.post(
            f"/v1/units/{self.unit_id}/speaker-invitations/batches/{batch_id}/dispatch",
            headers=self.headers,
        )

    # -- CBA contact channels (C6, C7, C8) ----------------------------------

    def channels_url(self, professional_id: uuid.UUID) -> str:
        return f"/v1/units/{self.unit_id}/speaker-contacts/{professional_id}/channels"

    def list_channels(self):
        return self.client.get(self.channels_url(self.professional_id), headers=self.headers)

    def register_channel(self, professional_id: uuid.UUID, address: str):
        return self.client.post(
            self.channels_url(professional_id),
            json={"address": address, "contact_state": "discovered"},
            headers=self.headers,
        )

    def transition(self, to_state: str, **extra: Any):
        return self.client.post(
            f"{self.channels_url(self.professional_id)}/{self.channel_id}/transitions",
            json={"to_state": to_state, **extra},
            headers=self.headers,
        )

    # -- Speaker portal (C10) -----------------------------------------------

    def portal_invite(self):
        return self.portal_client.post(
            f"/v1/units/{self.unit_id}/speaker-contacts/{self.professional_id}/portal-invitations",
            json={"contact_channel_id": str(self.channel_id)},
            headers=self.headers,
        )


@pytest.fixture(scope="module")
def engine() -> Engine:
    """A live migrated PostgreSQL engine with ``lifted_at``, or skip this contract."""
    try:
        eng = create_engine(DATABASE_URL, future=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT lifted_at FROM suppression_record LIMIT 1"))
            conn.execute(text("SELECT 1 FROM speaker_portal_invitation LIMIT 1"))
            conn.execute(text("SELECT 1 FROM cba_invitation LIMIT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}")
    return eng


@pytest.fixture
def ctx(engine: Engine) -> Iterator[_Context]:
    tenant_id = uuid.uuid4()
    unit_id = uuid.uuid4()
    user_id = uuid.uuid4()
    # Derived at runtime rather than written as literals: a fixture credential
    # spelled out in a source file is a credential in a commit patch.
    subject = f"sub-liftpaths-{uuid.uuid4().hex}"
    bearer = f"tok-liftpaths-{uuid.uuid4().hex}"

    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": tenant_id, "slug": f"test-liftpaths-{tenant_id.hex[:12]}"},
        )
        conn.execute(
            text(
                "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                "VALUES (:id, :tid, CAST(:path AS ltree), 'department', 'Northside Robotics')"
            ),
            {"id": unit_id, "tid": tenant_id, "path": UNIT_PATH},
        )
        conn.execute(
            text(
                "INSERT INTO user_account (id, tenant_id, external_subject, email) "
                "VALUES (:id, :tid, :subject, :email)"
            ),
            {"id": user_id, "tid": tenant_id, "subject": subject, "email": f"{subject}@x.edu"},
        )
        conn.execute(
            text(
                "INSERT INTO membership (id, tenant_id, user_id, granted_path, role) "
                "VALUES (:id, :tid, :uid, CAST(:path AS ltree), 'coordinator')"
            ),
            {"id": uuid.uuid4(), "tid": tenant_id, "uid": user_id, "path": UNIT_PATH},
        )

    verifier = FixtureTokenVerifier()
    verifier.register(bearer, subject)

    yield _Context(engine, tenant_id, unit_id, user_id, bearer, verifier)

    with engine.begin() as conn:
        for table in _CLEANUP:
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": tenant_id})
        conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tenant_id})


_states = pytest.mark.parametrize("state", SUPPRESSION_STATES)


# ---------------------------------------------------------------------------
# C2 / C3: generic outreach (R2)
# ---------------------------------------------------------------------------


@_states
def test_generic_compose(ctx: _Context, state: str) -> None:
    ctx.seed(state)

    response = ctx.compose()

    if SEND_ELIGIBLE[state]:
        assert response.status_code == 201, response.text
    else:
        assert response.status_code == 403, response.text
        assert response.json()["error"]["code"] == "outreach_recipient_not_eligible"


@_states
def test_generic_send(ctx: _Context, state: str) -> None:
    composed = ctx.compose()
    assert composed.status_code == 201, composed.text
    ctx.seed(state)

    response = ctx.send(composed.json()["draft_id"])

    if SEND_ELIGIBLE[state]:
        assert response.status_code == 202, response.text
    else:
        assert response.status_code == 403, response.text
        assert response.json()["error"]["code"] == "outreach_recipient_not_eligible"


# ---------------------------------------------------------------------------
# C4 / C5: CBA invitations (R1 at creation, R2 at dispatch)
# ---------------------------------------------------------------------------


@_states
def test_cba_batch_creation(ctx: _Context, state: str) -> None:
    ctx.seed(state)

    response = ctx.create_batch()

    assert response.status_code == 201, response.text
    body = response.json()
    outcome = body["invitations"][0]
    if SEND_ELIGIBLE[state]:
        assert outcome["skip_reason"] is None, body
        assert body["invited_count"] == 1
    else:
        assert outcome["skip_reason"] == "channel_suppressed", body
        assert body["invited_count"] == 0


@_states
def test_cba_dispatch(ctx: _Context, state: str) -> None:
    batch = ctx.create_batch()
    assert batch.status_code == 201, batch.text
    batch_body = batch.json()
    assert batch_body["invited_count"] == 1, batch_body
    invitation_id = batch_body["invitations"][0]["invitation_id"]
    ctx.seed(state)

    response = ctx.dispatch(batch_body["batch_id"])

    assert response.status_code == 202, response.text
    body = response.json()
    if SEND_ELIGIBLE[state]:
        assert [entry["invitation_id"] for entry in body["dispatched"]] == [invitation_id], body
        assert body["not_dispatched"] == []
    else:
        assert body["dispatched"] == [], body
        assert body["not_dispatched"] == [
            {"invitation_id": invitation_id, "reason": "channel_suppressed"}
        ]


# ---------------------------------------------------------------------------
# C6 + C9: the Connector's views (R1)
# ---------------------------------------------------------------------------


@_states
def test_connector_views_report_the_live_suppression(ctx: _Context, state: str) -> None:
    ctx.seed(state)
    expected_suppressed = not SEND_ELIGIBLE[state]

    cba = ctx.list_channels()
    assert cba.status_code == 200, cba.text
    cba_channel = cba.json()["channels"][0]["channel"]

    listed = ctx.list_contacts()
    assert listed.status_code == 200, listed.text
    listed_contact = listed.json()["contacts"][0]

    read = ctx.read_contact()
    assert read.status_code == 200, read.text
    read_contact = read.json()["contact"]

    for surface, view in (
        ("cba channel list", cba_channel),
        ("generic contacts list", listed_contact),
        ("generic contact read", read_contact),
    ):
        assert view["suppressed"] is expected_suppressed, (surface, view)
        assert view["send_eligible"] is SEND_ELIGIBLE[state], (surface, view)


# ---------------------------------------------------------------------------
# C7: register refusal (R3)
# ---------------------------------------------------------------------------


@_states
def test_register_refuses_only_an_active_suppression(ctx: _Context, state: str) -> None:
    """An address with a suppression row and no channel yet."""
    professional_id, _, address = ctx.roster_contact(with_channel=False)
    ctx.seed(state, address)

    response = ctx.register_channel(professional_id, address)

    if SEND_ELIGIBLE[state]:
        assert response.status_code == 201, response.text
    else:
        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "speaker_contact_channel_suppressed"


# ---------------------------------------------------------------------------
# C8: escalating transition (R1)
# ---------------------------------------------------------------------------


@_states
def test_escalation_is_refused_only_under_an_active_suppression(ctx: _Context, state: str) -> None:
    """``active_candidate`` → ``stale`` → ``reviewed`` → ``relationship_recorded``,
    then the move into ``consented`` under each suppression state."""
    for to_state in ("stale", "reviewed", "relationship_recorded"):
        walked = ctx.transition(to_state)
        assert walked.status_code == 201, walked.text
    ctx.seed(state)

    response = ctx.transition("consented", consent_source="in_person", consent_evidence=EVIDENCE)

    if SEND_ELIGIBLE[state]:
        assert response.status_code == 201, response.text
    else:
        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "speaker_contact_channel_transition_refused"


# ---------------------------------------------------------------------------
# C10: T6b-1 portal invite eligibility (R1)
# ---------------------------------------------------------------------------


@_states
def test_portal_invite_eligibility(ctx: _Context, state: str) -> None:
    ctx.seed(state)

    response = ctx.portal_invite()

    if SEND_ELIGIBLE[state]:
        assert response.status_code == 202, response.text
    else:
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "speaker_portal_channel_not_eligible"


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------


def _defines(tree: ast.Module, names: list[str]) -> bool:
    """Whether ``names`` (``[Class, ...,] function``) is defined in ``tree``."""
    body: list[ast.stmt] = tree.body
    for index, name in enumerate(names):
        last = index == len(names) - 1
        wanted = (ast.FunctionDef, ast.AsyncFunctionDef) if last else (ast.ClassDef,)
        found = next(
            (node for node in body if isinstance(node, wanted) and node.name == name), None
        )
        if found is None:
            return False
        body = getattr(found, "body", [])
    return True


def test_every_send_path_has_a_lifted_at_test() -> None:
    assert set(SEND_PATHS) == {f"C{n}" for n in range(1, 11)}

    missing = []
    for path_id, target in sorted(SEND_PATHS.items()):
        file_part, *names = target.split("::")
        source = REPO_ROOT / file_part
        if not source.is_file() or not names:
            missing.append((path_id, target))
            continue
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        if not _defines(tree, names):
            missing.append((path_id, target))

    assert missing == [], f"send paths without a lifted_at test: {missing}"
