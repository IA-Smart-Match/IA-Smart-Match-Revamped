"""The §13 create tells a Connector about a same-name contact, and creates anyway.

OQ-CBA-017 removed ``409 speaker_contact_name_already_used``. That refusal was
doing two jobs at once and only one of them was legitimate: it was enforcing a
*derived key* that could not hold two same-named people, and — as a side effect
— it was the only duplicate prevention this surface had. Removing it settles the
first and leaves the second unowned, which is what this file is about.

The replacement is a **hint, never a block**. A create that names somebody the
unit already holds still returns ``201`` and still writes a distinct person; the
response additionally names who else carries that name, so the Connector can
recognize them and stop. ``tests/contract/test_cba_contacts_api.py`` owns the
rest of the HTTP surface;
``tests/integration/test_cba_opaque_speaker_identity.py`` owns the rows
underneath.

Requires a live database, and is skipped when none is reachable.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest

pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient
from smartmatch_api.main import app
from smartmatch_persistence.engine import create_session_factory
from smartmatch_providers import FixtureTokenVerifier
from sqlalchemy import Engine, create_engine, text

pytestmark = pytest.mark.integration

DATABASE_URL = os.getenv(
    "SMARTMATCH_DATABASE_URL",
    "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch",
)

UNIT_PATH = "iawest.duphint"
#: A second department under the same tenant. The hint must not reach it.
OTHER_UNIT_PATH = "iawest.duphintother"

FULL_NAME = "Dana Reyes"
TYPO_NAME = "Dana Ryes"
COMPANY = "Reyes Analytics"
TITLE = "Principal Analyst"


def _body(**overrides: object) -> dict[str, object]:
    """A valid, unclassified contact. Overrides replace whole fields.

    Unclassified deliberately: nothing here is about §§7-8, and carrying codes
    would make every assertion below depend on a taxonomy this file has no
    opinion about.
    """
    body: dict[str, object] = {"full_name": FULL_NAME, "company": COMPANY, "title": TITLE}
    body.update(overrides)
    return body


@pytest.fixture(scope="module")
def engine() -> Engine:
    """A live migrated PostgreSQL engine, or skip this contract.

    The probe reads ``ix_speaker_profile_unit_folded_name`` out of ``pg_indexes``
    rather than selecting a column, because that index is what migration ``0030``
    adds — so a database migrated only to ``0029`` skips with a message naming
    the cause instead of failing every test on a response field that does not
    exist yet.
    """
    try:
        eng = create_engine(DATABASE_URL, future=True)
        with eng.connect() as conn:
            found = conn.execute(
                text(
                    "SELECT count(*) FROM pg_indexes "
                    "WHERE indexname = 'ix_speaker_profile_unit_folded_name'"
                )
            ).scalar_one()
        if not found:  # pragma: no cover - environment dependent
            pytest.skip(f"database at {DATABASE_URL} is not migrated to 0030")
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"no PostgreSQL migrated to 0030 at {DATABASE_URL}: {exc}")
    return eng


@pytest.fixture
def hint_context(engine: Engine) -> Iterator[tuple[TestClient, uuid.UUID, uuid.UUID, str]]:
    """One tenant, two departments, and a Speaker Connector covering both.

    The connector's membership is granted at ``iawest`` rather than at either
    department, so the *only* thing keeping the hint inside one unit is the
    query's own scoping rather than an authorization failure. A fixture granting
    per-department would make
    :func:`test_the_hint_does_not_reach_another_unit` pass for the wrong reason.
    """
    tenant_id = uuid.uuid4()
    unit_id = uuid.uuid4()
    other_unit_id = uuid.uuid4()
    token = f"tok-duphint-{uuid.uuid4().hex}"
    user_id = uuid.uuid4()
    subject = f"sub-dup-hint-{uuid.uuid4().hex}"

    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": tenant_id, "slug": f"test-duphint-{tenant_id.hex[:12]}"},
        )
        for new_unit_id, path, name in (
            (unit_id, UNIT_PATH, "Duplicate hint"),
            (other_unit_id, OTHER_UNIT_PATH, "Other department"),
        ):
            conn.execute(
                text(
                    "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                    "VALUES (:id, :tid, CAST(:path AS ltree), 'department', :name)"
                ),
                {"id": new_unit_id, "tid": tenant_id, "path": path, "name": name},
            )
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
        conn.execute(
            text(
                "INSERT INTO membership (id, tenant_id, user_id, granted_path, role) "
                "VALUES (:id, :tid, :uid, CAST(:path AS ltree), 'coordinator')"
            ),
            {"id": uuid.uuid4(), "tid": tenant_id, "uid": user_id, "path": "iawest"},
        )

    verifier = FixtureTokenVerifier()
    verifier.register(token, subject)
    client = TestClient(app)
    client.app.state.session_factory = create_session_factory(
        engine.url.render_as_string(hide_password=False)
    )
    client.app.state.token_verifier = verifier

    yield client, unit_id, other_unit_id, token

    with engine.begin() as conn:
        # `speaker_profile` holds ON DELETE RESTRICT references to both
        # `user_account` and `org_unit`, so it goes before either.
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


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create(client: TestClient, unit_id: uuid.UUID, token: str, **overrides: object):
    return client.post(
        f"/v1/units/{unit_id}/speaker-contacts",
        json=_body(**overrides),
        headers=_auth(token),
    )


# ---------------------------------------------------------------------------
# The create succeeds — the 409 is gone
# ---------------------------------------------------------------------------


def test_a_second_contact_with_the_same_name_is_created_rather_than_refused(
    hint_context,
) -> None:
    """``201`` and a second identity, where this surface used to answer ``409``.

    Two professionals in one department can share a name. The removed refusal
    made that case impossible in order to prevent a rarer accident, and
    OQ-CBA-017 reversed the trade. Both halves matter: the status *and* the fact
    that the second create names a different person rather than returning the
    first.
    """
    client, unit_id, _, token = hint_context

    first = _create(client, unit_id, token)
    assert first.status_code == 201, first.text

    second = _create(client, unit_id, token, company="Okonkwo Partners")

    assert second.status_code == 201, second.text
    assert second.json()["professional_id"] != first.json()["professional_id"]


def test_the_second_create_does_not_overwrite_the_first_persons_record(hint_context) -> None:
    """Silently merging is the failure the removed ``409`` was right to fear.

    Removing the refusal must not have replaced it with an upsert. Read back
    through a second request rather than off the create's echo, because a route
    that overwrote and returned its own body would pass an assertion on the
    response and fail this one.
    """
    client, unit_id, _, token = hint_context

    first = _create(client, unit_id, token)
    professional_id = first.json()["professional_id"]
    _create(client, unit_id, token, company="Okonkwo Partners")

    fetched = client.get(
        f"/v1/units/{unit_id}/speaker-contacts/{professional_id}", headers=_auth(token)
    )

    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["company"] == COMPANY


def test_both_same_named_contacts_appear_on_the_roster(hint_context) -> None:
    """Two people, two rows, both visible.

    The listing is where a Connector resolves what the hint told them, so a
    same-name pair that could be created but not seen would leave them with a
    warning and no way to act on it.
    """
    client, unit_id, _, token = hint_context

    first = _create(client, unit_id, token)
    second = _create(client, unit_id, token, company="Okonkwo Partners")

    listed = client.get(f"/v1/units/{unit_id}/speaker-contacts", headers=_auth(token))

    assert listed.status_code == 200, listed.text
    ids = {row["professional_id"] for row in listed.json()["contacts"]}
    assert ids == {first.json()["professional_id"], second.json()["professional_id"]}


# ---------------------------------------------------------------------------
# The hint itself
# ---------------------------------------------------------------------------


def test_a_first_create_reports_no_same_name_contacts(hint_context) -> None:
    """Quiet when there is nothing to say.

    Asserted before the positive case: a field that is always populated tells a
    Connector nothing and teaches them to skip it, which is the same reason
    ``withheld_fields`` reports only a discard that actually happened.
    """
    client, unit_id, _, token = hint_context

    created = _create(client, unit_id, token)

    assert created.status_code == 201, created.text
    assert created.json()["same_name_contacts"] == []
    assert created.json()["same_name_truncated"] is False


def test_the_hint_identifies_the_contact_already_holding_the_name(hint_context) -> None:
    """A bare "somebody has this name" is not actionable; naming them is.

    That was the one thing the ``409`` did well — it named who was already there
    so a Connector could recognize or dispute them — and it is the part kept.
    The employer is asserted alongside the id for exactly that reason: "Dana
    Reyes at Reyes Analytics" is recognizable and a bare UUID is not.
    """
    client, unit_id, _, token = hint_context

    first = _create(client, unit_id, token)
    second = _create(client, unit_id, token, company="Okonkwo Partners")

    hint = second.json()["same_name_contacts"]

    assert [row["professional_id"] for row in hint] == [first.json()["professional_id"]]
    assert hint[0]["full_name"] == FULL_NAME
    assert hint[0]["company"] == COMPANY


def test_the_hint_never_names_the_contact_just_created(hint_context) -> None:
    """A row is not a duplicate of itself.

    A hint computed after the insert and filtered afterwards would be one
    forgotten predicate away from telling every Connector that the person they
    just added already exists — a warning that means nothing, and therefore
    trains them past every warning.
    """
    client, unit_id, _, token = hint_context

    created = _create(client, unit_id, token)
    body = created.json()

    assert body["professional_id"] not in {
        row["professional_id"] for row in body["same_name_contacts"]
    }


def test_the_hint_folds_case_and_surrounding_space(hint_context) -> None:
    """The commonest way one person gets entered twice is a re-typed name.

    ``"  DANA REYES  "`` is that. The removed derivation folded with
    ``.strip().casefold()`` and the hint keeps precisely that folding, matched in
    SQL as ``lower(btrim(...))`` against ``ix_speaker_profile_unit_folded_name``.
    """
    client, unit_id, _, token = hint_context

    first = _create(client, unit_id, token)
    second = _create(client, unit_id, token, full_name="  DANA REYES  ")

    assert second.status_code == 201, second.text
    assert [row["professional_id"] for row in second.json()["same_name_contacts"]] == [
        first.json()["professional_id"]
    ]


def test_a_near_miss_name_is_not_hinted(hint_context) -> None:
    """A fold is not a fuzzy match, and this surface does not guess.

    ``"Dana Ryes"`` and ``"Dana Reyes"`` differ by one letter and are two
    different names. A hint that fired on near-misses would fire constantly on a
    real roster and be ignored within a week; similarity matching is recorded as
    OQ-CBA-050 rather than invented here.
    """
    client, unit_id, _, token = hint_context

    _create(client, unit_id, token)
    other = _create(client, unit_id, token, full_name=TYPO_NAME)

    assert other.status_code == 201, other.text
    assert other.json()["same_name_contacts"] == []


def test_the_hint_does_not_reach_another_unit(hint_context) -> None:
    """A5 scoping, and here it is a disclosure boundary rather than a filter.

    The fixture's Connector covers both departments, so nothing but the query's
    own ``owning_unit_id`` predicate keeps this hint inside one roster. A hint
    that reached across units would tell a Connector who another department
    knows, on a surface that exists to add somebody to their own.
    """
    client, unit_id, other_unit_id, token = hint_context

    _create(client, unit_id, token)
    elsewhere = _create(client, other_unit_id, token)

    assert elsewhere.status_code == 201, elsewhere.text
    assert elsewhere.json()["same_name_contacts"] == []


def test_a_read_reports_no_hint(hint_context) -> None:
    """The hint answers a question only a create asks.

    A ``GET`` supplied no name to collide with, so an empty list there is not a
    claim that nobody shares the name — it is the absence of a question. Pinned
    so the field cannot quietly become a per-row duplicate flag that every
    roster screen would start rendering.
    """
    client, unit_id, _, token = hint_context

    first = _create(client, unit_id, token)
    _create(client, unit_id, token, company="Okonkwo Partners")

    fetched = client.get(
        f"/v1/units/{unit_id}/speaker-contacts/{first.json()['professional_id']}",
        headers=_auth(token),
    )

    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["same_name_contacts"] == []


# ---------------------------------------------------------------------------
# The rename fork, over HTTP
# ---------------------------------------------------------------------------


def test_a_create_after_a_rename_is_told_about_the_renamed_contact(hint_context) -> None:
    """The three-step sequence OQ-CBA-017 was decided to close, end to end.

    Type ``"Dana Ryes"``, correct it to ``"Dana Reyes"``, then create
    ``"Dana Reyes"``. Under the derived scheme the third step succeeded in
    silence: the guard compared derived ids, the renamed row still carried
    ``uuid5(…"dana ryes")``, and the create derived something else — so the one
    mechanism that could have caught it was looking at the wrong thing.

    The create still succeeds, because same-name creates are legitimate now.
    What changed is that it is no longer silent: the hint compares names, which
    is what a rename actually changes.
    """
    client, unit_id, _, token = hint_context

    typo = _create(client, unit_id, token, full_name=TYPO_NAME)
    assert typo.status_code == 201, typo.text
    professional_id = typo.json()["professional_id"]

    renamed = client.patch(
        f"/v1/units/{unit_id}/speaker-contacts/{professional_id}",
        json=_body(full_name=FULL_NAME),
        headers=_auth(token),
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["professional_id"] == professional_id

    again = _create(client, unit_id, token)

    assert again.status_code == 201, again.text
    assert [row["professional_id"] for row in again.json()["same_name_contacts"]] == [
        professional_id
    ], "a create after a rename must name the renamed contact"
