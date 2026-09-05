"""HTTP contracts for customer §13's speaker-contact surface.

``tests/authz/test_policy_matrix.py`` owns the full authorization rectangle for
all five operations and needs no database to run it. What this file adds is the
part that only exists over HTTP: that authorization is reached before any row is
written, that a Speaker Connector really can add a contact and an Event Host
really cannot — the one cell that distinguishes this card from
``CBA-EVENT-REQUEST`` — that a unit in another tenant is a ``404`` rather than a
``403``, that a second person with the same name is refused rather than merged,
and that the contact email a Connector types is visibly discarded.

``tests/integration/test_cba_contact_corrections.py`` owns what the writer does
to the rows. Nothing here re-asserts that; what it asserts is that the response
describes those rows rather than echoing the request body, which is why the
interesting assertions read a *second* call rather than the first one's echo.

Every request is synthetic and nothing in the path under test opens a socket.
There is no field on any request model that could carry a URL, which is customer
§20's out-of-scope external discovery refused by the shape of the contract
rather than by a runtime check.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from smartmatch_api.main import app
from smartmatch_domain.cba_role_categories import CBA_ROLE_TAXONOMY_VERSION
from smartmatch_domain.naics_sectors import NAICS_TAXONOMY_VERSION
from smartmatch_persistence.engine import create_session_factory
from smartmatch_providers import FixtureTokenVerifier
from sqlalchemy import Engine, create_engine, text

pytestmark = pytest.mark.integration

DATABASE_URL = os.getenv(
    "SMARTMATCH_DATABASE_URL",
    "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch",
)

UNIT_PATH = "iawest.contacts"
#: A second department in the same tenant containing none of :data:`UNIT_PATH`.
#: The authorizer passes no ``tenant_wide_roles``, so ordinary subtree
#: containment applies and a coordinator here must not reach the contacts unit.
SIBLING_UNIT_PATH = "iawest.contactssibling"

FULL_NAME = "Dana Reyes"
COMPANY = "Reyes Analytics"
TITLE = "Principal Analyst"

FINANCE_SECTOR = "52"
PROFESSIONAL_SERVICES_SECTOR = "54"
FINANCE_ROLE = "finance"
MARKETING_ROLE = "marketing"

#: An address a Connector might type into §13's form. On the RFC 2606 reserved
#: ``.invalid`` TLD so that a defect which *did* persist and later send it could
#: not reach a real mailbox — the test asserts the discard, and the domain of the
#: literal makes a failure of that assertion harmless.
TYPED_CONTACT_EMAIL = "dana.reyes@example.invalid"


def _body(**overrides: object) -> dict[str, object]:
    """A complete, valid contact. Overrides replace whole fields."""
    body: dict[str, object] = {
        "full_name": FULL_NAME,
        "company": COMPANY,
        "title": TITLE,
        "topic_text": "Financial modelling for early-career analysts.",
        "location_city": "Pomona",
        "primary_industry_code": FINANCE_SECTOR,
        "primary_role_code": FINANCE_ROLE,
    }
    body.update(overrides)
    return body


@pytest.fixture(scope="module")
def engine() -> Engine:
    """A live migrated PostgreSQL engine, or skip this contract.

    The probe selects ``speaker_profile.full_name`` specifically, so a database
    migrated only to ``0024`` skips rather than failing every test with an
    ``UndefinedColumn`` that names the symptom instead of the cause.
    """
    try:
        eng = create_engine(DATABASE_URL, future=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT full_name FROM speaker_profile LIMIT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"no PostgreSQL migrated to 0025 at {DATABASE_URL}: {exc}")
    return eng


def _insert_principal(
    conn,
    tenant_id: uuid.UUID,
    *,
    role: str | None,
    membership_path: str = UNIT_PATH,
) -> str:
    """One ``user_account`` and, unless ``role`` is ``None``, one membership.

    Returns the external subject, which is what a fixture token is registered
    against. ``role=None`` builds a principal with no membership at all.
    """
    user_id = uuid.uuid4()
    subject = f"sub-contacts-{uuid.uuid4().hex}"
    conn.execute(
        text(
            "INSERT INTO user_account (id, tenant_id, external_subject, email) "
            "VALUES (:id, :tid, :subject, :email)"
        ),
        {
            "id": user_id,
            "tid": tenant_id,
            "subject": subject,
            "email": f"{subject}@example.edu",
        },
    )
    if role is not None:
        conn.execute(
            text(
                "INSERT INTO membership (id, tenant_id, user_id, granted_path, role) "
                "VALUES (:id, :tid, :uid, CAST(:path AS ltree), :role)"
            ),
            {
                "id": uuid.uuid4(),
                "tid": tenant_id,
                "uid": user_id,
                "path": membership_path,
                "role": role,
            },
        )
    return subject


@pytest.fixture
def contact_context(engine: Engine) -> Iterator[tuple[TestClient, uuid.UUID, str, uuid.UUID]]:
    """One tenant, one unit, one sibling unit, and a Speaker Connector in the unit.

    The default principal is a ``coordinator`` — the stored role behind §13's
    **Speaker Connector** persona — because that is the caller this surface
    exists for. ``tests/contract/test_speaker_requests_api.py`` defaults to a
    ``volunteer`` for the mirror-image reason, and the contrast between the two
    fixtures is the contrast between the two cards.
    """
    tenant_id = uuid.uuid4()
    unit_id = uuid.uuid4()
    sibling_unit_id = uuid.uuid4()
    token = f"tok-contacts-{uuid.uuid4().hex}"

    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": tenant_id, "slug": f"test-contacts-{tenant_id.hex[:12]}"},
        )
        for new_unit_id, path, name in (
            (unit_id, UNIT_PATH, "Contacts"),
            (sibling_unit_id, SIBLING_UNIT_PATH, "Sibling"),
        ):
            conn.execute(
                text(
                    "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                    "VALUES (:id, :tid, CAST(:path AS ltree), 'department', :name)"
                ),
                {"id": new_unit_id, "tid": tenant_id, "path": path, "name": name},
            )
        subject = _insert_principal(conn, tenant_id, role="coordinator")

    verifier = FixtureTokenVerifier()
    verifier.register(token, subject)
    client = TestClient(app)
    client.app.state.session_factory = create_session_factory(
        engine.url.render_as_string(hide_password=False)
    )
    client.app.state.token_verifier = verifier

    yield client, unit_id, token, tenant_id

    with engine.begin() as conn:
        # `speaker_profile` holds ON DELETE RESTRICT references to both
        # `user_account` and `org_unit`, so it must go before either — the
        # ordering hazard `test_cba_classification_schema.py`'s cleanup fixture
        # exists for, restated here because this file creates the rows through
        # HTTP and has no repository teardown to lean on.
        for table in (
            "speaker_profile",
            "professional_unit_relationship",
            "membership",
            "resource_grant",
            "user_account",
            "org_unit",
            "rate_limit_counter",
        ):
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": tenant_id})
        conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tenant_id})


def _register(engine: Engine, client: TestClient, tenant_id: uuid.UUID, *, role: str | None) -> str:
    """Add one more principal to ``tenant_id`` and return a bearer token."""
    token = f"tok-contacts-{uuid.uuid4().hex}"
    with engine.begin() as conn:
        subject = _insert_principal(conn, tenant_id, role=role)
    client.app.state.token_verifier.register(token, subject)
    return token


def _auth(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token is not None else {}


def _create(client: TestClient, unit_id: uuid.UUID, token: str | None, **overrides: object):
    return client.post(
        f"/v1/units/{unit_id}/speaker-contacts",
        json=_body(**overrides),
        headers=_auth(token),
    )


def _add_unit(engine: Engine, tenant_id: uuid.UUID, path: str) -> uuid.UUID:
    """One more department under the same tenant, returned by id."""
    unit_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                "VALUES (:id, :tid, CAST(:path AS ltree), 'department', :name)"
            ),
            {"id": unit_id, "tid": tenant_id, "path": path, "name": path},
        )
    return unit_id


# ---------------------------------------------------------------------------
# Creating a contact
# ---------------------------------------------------------------------------


def test_a_connector_adds_a_contact_and_reads_it_back(contact_context) -> None:
    """§13's whole point, asserted through a second call rather than the echo.

    The read is what proves a row exists: a create that returned its own request
    body would pass an assertion on the ``201`` and fail this one.
    """
    client, unit_id, token, _ = contact_context

    created = _create(client, unit_id, token)
    assert created.status_code == 201, created.text
    professional_id = created.json()["professional_id"]

    fetched = client.get(
        f"/v1/units/{unit_id}/speaker-contacts/{professional_id}", headers=_auth(token)
    )
    assert fetched.status_code == 200, fetched.text
    body = fetched.json()

    assert body["full_name"] == FULL_NAME
    assert body["company"] == COMPANY
    assert body["title"] == TITLE
    assert body["owning_unit_id"] == str(unit_id)
    # The code and its version travel together, and the version is derived
    # rather than supplied — a caller cannot store a code under a taxonomy
    # version that did not evaluate it.
    assert body["primary_industry_code"] == FINANCE_SECTOR
    assert body["industry_taxonomy_version"] == NAICS_TAXONOMY_VERSION
    assert body["primary_role_code"] == FINANCE_ROLE
    assert body["role_taxonomy_version"] == CBA_ROLE_TAXONOMY_VERSION


def test_an_unclassified_contact_is_storable(contact_context) -> None:
    """§19 records a contact first and classifies them after.

    Both axes absent, and both version tokens absent with them — the paired
    nullability ``ck_speaker_profile_industry_versioned`` requires.
    """
    client, unit_id, token, _ = contact_context

    created = _create(client, unit_id, token, primary_industry_code=None, primary_role_code=None)
    assert created.status_code == 201, created.text
    body = created.json()

    assert body["primary_industry_code"] is None
    assert body["industry_taxonomy_version"] is None
    assert body["primary_role_code"] is None
    assert body["role_taxonomy_version"] is None


def test_an_absent_company_is_stored_as_absent(contact_context) -> None:
    """A retired professional has no employer, and null is the honest answer."""
    client, unit_id, token, _ = contact_context

    created = _create(client, unit_id, token, company=None, title=None)
    assert created.status_code == 201, created.text

    assert created.json()["company"] is None
    assert created.json()["title"] is None


def test_a_blank_company_is_refused_rather_than_stored(contact_context) -> None:
    """ADR-0011: absent is a value, blank is a writer that forgot.

    Refused at the API rather than at the constraint, so the message names the
    field instead of ``ck_speaker_profile_text_present``.
    """
    client, unit_id, token, _ = contact_context

    refused = _create(client, unit_id, token, company="   ")

    assert refused.status_code in (400, 422), refused.text


@pytest.mark.parametrize("whitespace", ["   ", "\t", "\n", "\t\n"])
def test_a_whitespace_only_name_is_refused(contact_context, whitespace: str) -> None:
    """The API is stricter than the CHECK, and deliberately.

    PostgreSQL's single-argument ``btrim`` strips spaces only, so
    ``ck_speaker_profile_text_present`` accepts a tab-only name —
    ``tests/integration/test_cba_contact_schema.py`` pins that as the
    constraint's real reach. The domain validates with Python's ``str.strip()``,
    which strips tabs and newlines too, so none of these reaches the database
    through this surface.

    Both halves are asserted, in the two files, because "the database allows it"
    and "the API allows it" are different claims and only one of them is a
    defect.
    """
    client, unit_id, token, _ = contact_context

    refused = _create(client, unit_id, token, full_name=whitespace)

    assert refused.status_code in (400, 422), refused.text


@pytest.mark.parametrize(
    ("field", "value"),
    [("primary_industry_code", "99"), ("primary_role_code", "chief_vibes_officer")],
)
def test_a_code_outside_the_closed_taxonomy_is_refused(
    contact_context, field: str, value: str
) -> None:
    """The vocabularies are closed, and §13's Connector picks from a rendered list.

    So an unrecognized code is a client defect and gets a ``400``, not a
    quarantine — quarantine is the import path's job and this is not that path
    (OQ-CBA-010).
    """
    client, unit_id, token, _ = contact_context

    refused = _create(client, unit_id, token, **{field: value})

    assert refused.status_code == 400, refused.text


# ---------------------------------------------------------------------------
# The withheld contact email — OQ-CBA-011, ratified
# ---------------------------------------------------------------------------


def test_a_typed_contact_email_is_accepted_and_reported_as_withheld(contact_context) -> None:
    """Accepted so the form works; reported so the discard is not silent.

    A ``422`` here would tell a client that §13's own form field is invalid. A
    ``201`` with an empty ``withheld_fields`` would tell a Connector the address
    was saved. Neither is what OQ-CBA-011 ratified.
    """
    client, unit_id, token, _ = contact_context

    created = _create(client, unit_id, token, contact_email=TYPED_CONTACT_EMAIL)

    assert created.status_code == 201, created.text
    assert created.json()["withheld_fields"] == ["contact_email"]


def test_a_contact_created_without_an_email_reports_nothing_withheld(contact_context) -> None:
    """Reporting a refusal that did not happen is how a field trains people to ignore it."""
    client, unit_id, token, _ = contact_context

    created = _create(client, unit_id, token)

    assert created.status_code == 201, created.text
    assert created.json()["withheld_fields"] == []


def test_the_typed_address_reaches_no_table_and_no_response_field(
    contact_context, engine: Engine
) -> None:
    """The assertion the whole withhold posture rests on.

    Three separate claims, because a defect could satisfy any two of them:
    nothing in the response body carries the address, no ``contact_channel`` row
    exists for this tenant at all, and the ``user_account.email`` the create did
    write is the derived ``.invalid`` placeholder rather than what was typed.

    The ``contact_channel`` check counts rows for the whole tenant rather than
    looking for this address, so a row written under any other form of it —
    normalized, lowercased — fails the assertion too.
    """
    client, unit_id, token, tenant_id = contact_context

    created = _create(client, unit_id, token, contact_email=TYPED_CONTACT_EMAIL)
    assert created.status_code == 201, created.text
    professional_id = created.json()["professional_id"]

    assert TYPED_CONTACT_EMAIL not in created.text

    with engine.connect() as conn:
        channels = conn.execute(
            text("SELECT count(*) FROM contact_channel WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        ).scalar_one()
        stored_email = conn.execute(
            text("SELECT email FROM user_account WHERE tenant_id = :tid AND id = :pid"),
            {"tid": tenant_id, "pid": professional_id},
        ).scalar_one()

    assert channels == 0, "creating a §13 contact must never write a contact channel"
    assert stored_email != TYPED_CONTACT_EMAIL
    assert stored_email.endswith("@contact.invalid"), stored_email


# ---------------------------------------------------------------------------
# Authorization, over HTTP
# ---------------------------------------------------------------------------


def test_an_event_host_may_not_add_a_contact(contact_context, engine: Engine) -> None:
    """The cell that distinguishes this card from CBA-EVENT-REQUEST.

    The same ``volunteer`` principal is *permitted* to file a Speaker Request
    (``tests/contract/test_speaker_requests_api.py``). §12 lets a host ask for a
    speaker; §13 gives the roster to the Connector. Asserted over HTTP as well as
    in the matrix because the matrix proves the authorizer decides correctly and
    this proves the route calls it.
    """
    client, unit_id, _, tenant_id = contact_context
    host_token = _register(engine, client, tenant_id, role="volunteer")

    refused = _create(client, unit_id, host_token)

    assert refused.status_code == 403, refused.text


def test_a_student_may_not_read_the_roster(contact_context, engine: Engine) -> None:
    """§15 gives a Student browsing, registration, calendar and feedback — not this.

    The roster carries named professionals, their employers and their titles.
    """
    client, unit_id, _, tenant_id = contact_context
    student_token = _register(engine, client, tenant_id, role="student")

    refused = client.get(f"/v1/units/{unit_id}/speaker-contacts", headers=_auth(student_token))

    assert refused.status_code == 403, refused.text


def test_an_anonymous_caller_is_refused(contact_context) -> None:
    """No route on this surface is public."""
    client, unit_id, _, _ = contact_context

    refused = client.get(f"/v1/units/{unit_id}/speaker-contacts", headers=_auth(None))

    assert refused.status_code == 401, refused.text


def test_a_unit_in_another_tenant_is_a_404(contact_context) -> None:
    """A 403 would confirm that a unit id the caller may not reach names something real."""
    client, _, token, _ = contact_context

    refused = _create(client, uuid.uuid4(), token)

    assert refused.status_code == 404, refused.text


def test_a_contact_in_another_unit_is_a_404(contact_context, engine: Engine) -> None:
    """Reads are scoped by ``(tenant_id, owning_unit_id)``, never by contact id alone.

    Built by creating the contact under the real unit and then asking for it
    under a *second* unit the same coordinator also covers, so the only thing
    refusing the read is the scoping rather than the authorization.
    """
    client, unit_id, token, tenant_id = contact_context

    created = _create(client, unit_id, token)
    assert created.status_code == 201, created.text
    professional_id = created.json()["professional_id"]

    other_unit_id = _add_unit(engine, tenant_id, f"{UNIT_PATH}.other")

    refused = client.get(
        f"/v1/units/{other_unit_id}/speaker-contacts/{professional_id}", headers=_auth(token)
    )

    assert refused.status_code == 404, refused.text


# ---------------------------------------------------------------------------
# The duplicate name — OQ-CBA-017
# ---------------------------------------------------------------------------


def test_a_second_contact_with_the_same_name_is_refused(contact_context) -> None:
    """409, and neither a merge nor a duplicate.

    The identity derives from the folded name, so the second create would land on
    the first person's primary key. Upserting would overwrite one person's record
    with another's while returning ``200``; a second row is not available at all.
    Refusing is the only answer that loses nothing silently.
    """
    client, unit_id, token, _ = contact_context

    first = _create(client, unit_id, token)
    assert first.status_code == 201, first.text

    second = _create(client, unit_id, token, company="A Different Employer")

    assert second.status_code == 409, second.text


def test_the_refused_duplicate_did_not_overwrite_the_stored_contact(contact_context) -> None:
    """The point of the 409 is that the first person's record is intact afterwards.

    Asserted separately from the status code, because a route could answer 409
    *after* writing — the refusal has to happen before the write, not instead of
    reporting one.
    """
    client, unit_id, token, _ = contact_context

    first = _create(client, unit_id, token)
    professional_id = first.json()["professional_id"]
    _create(client, unit_id, token, company="A Different Employer")

    fetched = client.get(
        f"/v1/units/{unit_id}/speaker-contacts/{professional_id}", headers=_auth(token)
    )

    assert fetched.json()["company"] == COMPANY


def test_the_same_name_in_a_different_unit_is_a_different_contact(
    contact_context, engine: Engine
) -> None:
    """``unit_id`` is in the hash input, so two departments' rosters do not collide."""
    client, unit_id, token, tenant_id = contact_context

    second_unit_id = _add_unit(engine, tenant_id, f"{UNIT_PATH}.second")

    first = _create(client, unit_id, token)
    second = _create(client, second_unit_id, token)

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["professional_id"] != second.json()["professional_id"]


# ---------------------------------------------------------------------------
# Listing, editing, correcting
# ---------------------------------------------------------------------------


def test_the_roster_lists_this_units_contacts(contact_context) -> None:
    """And says whether it is complete, rather than leaving a full page ambiguous."""
    client, unit_id, token, _ = contact_context

    _create(client, unit_id, token)
    _create(client, unit_id, token, full_name="Aria Okonkwo")

    listed = client.get(f"/v1/units/{unit_id}/speaker-contacts", headers=_auth(token))

    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["truncated"] is False
    # Ordered by name, so a Connector scanning finds somebody where a person
    # would look.
    assert [row["full_name"] for row in body["contacts"]] == ["Aria Okonkwo", FULL_NAME]


def test_an_edit_can_remove_a_stored_company(contact_context) -> None:
    """The body states the record in full, so an omitted optional field clears it.

    Merging instead would make removing a value the one edit a Connector could
    never perform.
    """
    client, unit_id, token, _ = contact_context

    created = _create(client, unit_id, token)
    professional_id = created.json()["professional_id"]

    edited = client.patch(
        f"/v1/units/{unit_id}/speaker-contacts/{professional_id}",
        json=_body(company=None),
        headers=_auth(token),
    )

    assert edited.status_code == 200, edited.text
    assert edited.json()["company"] is None


def test_a_correction_replaces_one_axis_and_leaves_the_other(contact_context) -> None:
    """§§7-8's correction, and the reason an omitted axis means "leave it alone".

    Fixing the industry while leaving the role is the common case, and it is only
    safe because null does not mean "clear".
    """
    client, unit_id, token, _ = contact_context

    created = _create(client, unit_id, token)
    professional_id = created.json()["professional_id"]

    corrected = client.post(
        f"/v1/units/{unit_id}/speaker-contacts/{professional_id}/classification",
        json={"primary_industry_code": PROFESSIONAL_SERVICES_SECTOR},
        headers=_auth(token),
    )

    assert corrected.status_code == 200, corrected.text
    body = corrected.json()
    assert body["primary_industry_code"] == PROFESSIONAL_SERVICES_SECTOR
    assert body["primary_role_code"] == FINANCE_ROLE, "an unnamed axis must not be cleared"


def test_a_correction_naming_neither_axis_is_refused(contact_context) -> None:
    """An empty correction changes nothing and would look like a successful edit."""
    client, unit_id, token, _ = contact_context

    created = _create(client, unit_id, token)
    professional_id = created.json()["professional_id"]

    refused = client.post(
        f"/v1/units/{unit_id}/speaker-contacts/{professional_id}/classification",
        json={},
        headers=_auth(token),
    )

    assert refused.status_code == 400, refused.text


def test_an_event_host_may_not_correct_a_classification(contact_context, engine: Engine) -> None:
    """The sharpest reading of the split between the two cards.

    §12's host names the industries their own request targets. Letting them
    restate what a *professional* is would let one side of the match edit the
    other side's record.
    """
    client, unit_id, token, tenant_id = contact_context

    created = _create(client, unit_id, token)
    professional_id = created.json()["professional_id"]
    host_token = _register(engine, client, tenant_id, role="volunteer")

    refused = client.post(
        f"/v1/units/{unit_id}/speaker-contacts/{professional_id}/classification",
        json={"primary_role_code": MARKETING_ROLE},
        headers=_auth(host_token),
    )

    assert refused.status_code == 403, refused.text
