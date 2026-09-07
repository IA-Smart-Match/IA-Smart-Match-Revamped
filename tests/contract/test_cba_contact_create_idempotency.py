"""An ``Idempotency-Key`` collapses a repeated §13 create into one contact.

OQ-CBA-047, decided 6 September 2026. Migration ``0030`` made a speaker
contact's identity opaque, and the name-derived key that went with it had been
doing duplicate prevention as a side effect. Removing it was right — it refused
two genuinely different people who share a name, and it stopped preventing
anything the moment somebody corrected a name — but it left the create with no
way to tell *this request happened twice* from *these are two people*. A
double-clicked form added the same person twice, and with **no merge surface
anywhere in this product** (OQ-CBA-049 records that building one is a separate
decision nobody has taken) the result was two rows for one person that nobody
could combine.

The header answers that and nothing else. What this file pins:

* **No key behaves exactly as it did before.** The header is optional, every
  existing caller omits it, and none of them may notice a difference.
* **Same key, same body** — one row, the original ``201``, the identical body.
* **Same key, different body** — ``409 idempotency_key_reused``, and no row.
* **Two different keys, identical bodies** — *two* contacts. This is the case
  that proves the key is taken off the **request** and never off the name: two
  real professionals can share a name, and a scheme that deduplicated by name
  would collapse them into one. See
  :func:`test_two_different_keys_with_identical_bodies_create_two_contacts`.

The duplicate hint (OQ-CBA-021) is a different mechanism answering a different
question and is unchanged; ``tests/contract/test_cba_contact_duplicate_hint.py``
owns it. ``tests/contract/test_cba_contacts_api.py`` owns the rest of the HTTP
surface, and ``tests/integration/test_cba_opaque_speaker_identity.py`` owns the
rows underneath.

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
from smartmatch_api.routers.cba_contacts import (
    MAX_IDEMPOTENCY_KEY_LENGTH,
    SPEAKER_CONTACT_CREATE_COMMAND_TYPE,
)
from smartmatch_persistence.engine import create_session_factory
from smartmatch_providers import FixtureTokenVerifier
from sqlalchemy import Engine, create_engine, text

pytestmark = pytest.mark.integration

DATABASE_URL = os.getenv(
    "SMARTMATCH_DATABASE_URL",
    "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch",
)

UNIT_PATH = "iawest.idemcreate"
#: A second department under the same tenant. A key is scoped by tenant and
#: command type but *not* by unit, so this is where the fingerprint has to hold
#: the line — see :func:`test_the_same_key_against_another_unit_is_a_conflict`.
OTHER_UNIT_PATH = "iawest.idemcreateother"

FULL_NAME = "Dana Reyes"
COMPANY = "Reyes Analytics"
TITLE = "Principal Analyst"


def _body(**overrides: object) -> dict[str, object]:
    """A valid, unclassified contact. Overrides replace whole fields.

    Unclassified deliberately: nothing here is about §§7-8, and carrying
    taxonomy codes would make every assertion below depend on a vocabulary this
    file has no opinion about.
    """
    body: dict[str, object] = {"full_name": FULL_NAME, "company": COMPANY, "title": TITLE}
    body.update(overrides)
    return body


@pytest.fixture(scope="module")
def engine() -> Engine:
    """A live migrated PostgreSQL engine, or skip this contract.

    Probes for ``ix_speaker_profile_unit_folded_name`` — migration ``0030``'s
    index — rather than selecting a column, so a database migrated only to
    ``0029`` skips with a message naming the cause instead of failing every test
    here on a response field that does not exist yet. ``idempotency_record`` is
    much older, so ``0030`` is the binding floor for this file even though the
    header is the subject.
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
def idem_context(engine: Engine) -> Iterator[tuple[TestClient, uuid.UUID, uuid.UUID, str]]:
    """One tenant, two departments, and a Speaker Connector covering both.

    The connector's membership is granted at ``iawest`` rather than at either
    department, exactly as the duplicate-hint fixture does it and for the same
    reason: a caller authorized for only one unit would make the cross-unit test
    pass on a ``403`` instead of on the thing being asserted.

    Every test gets a fresh tenant, so a key like ``"double-click"`` is
    unambiguous within a test and cannot leak into the next one — the
    reservation is scoped by ``tenant_id`` and the tenant is torn down here.
    """
    tenant_id = uuid.uuid4()
    unit_id = uuid.uuid4()
    other_unit_id = uuid.uuid4()
    token = f"tok-idemcreate-{uuid.uuid4().hex}"
    user_id = uuid.uuid4()
    subject = f"sub-idem-create-{uuid.uuid4().hex}"

    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": tenant_id, "slug": f"test-idemcreate-{tenant_id.hex[:12]}"},
        )
        for new_unit_id, path, name in (
            (unit_id, UNIT_PATH, "Idempotent create"),
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
        # `idempotency_record` references only `tenant`, so its position is
        # free; it goes with the rest for one readable list.
        for table in (
            "speaker_profile",
            "professional_unit_relationship",
            "membership",
            "resource_grant",
            "idempotency_record",
            "user_account",
            "org_unit",
            "rate_limit_counter",
        ):
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": tenant_id})
        conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tenant_id})


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create(
    client: TestClient,
    unit_id: uuid.UUID,
    token: str,
    *,
    key: str | None = None,
    **overrides: object,
):
    """POST one contact, with an ``Idempotency-Key`` only when one is given.

    ``key=None`` sends **no header at all** rather than an empty one, because
    "the caller omitted it" is the case the optional-header tests are about and
    an empty header is a different thing.
    """
    headers = _auth(token)
    if key is not None:
        headers["Idempotency-Key"] = key
    return client.post(
        f"/v1/units/{unit_id}/speaker-contacts",
        json=_body(**overrides),
        headers=headers,
    )


def _roster_ids(client: TestClient, unit_id: uuid.UUID, token: str) -> set[str]:
    listed = client.get(f"/v1/units/{unit_id}/speaker-contacts", headers=_auth(token))
    assert listed.status_code == 200, listed.text
    return {row["professional_id"] for row in listed.json()["contacts"]}


# ---------------------------------------------------------------------------
# No key: nothing changed
# ---------------------------------------------------------------------------


def test_a_create_without_a_key_still_succeeds(idem_context) -> None:
    """The header is **optional**, and this is the assertion that says so.

    Asserted first and deliberately: every caller that exists today posts §13's
    form without an ``Idempotency-Key``, and a required header would have turned
    all of them into ``400``s. ``submit_command`` and ``redrive.py`` require
    theirs because they start durable background work; this route creates its
    rows synchronously and does not.
    """
    client, unit_id, _, token = idem_context

    created = _create(client, unit_id, token)

    assert created.status_code == 201, created.text
    assert created.json()["full_name"] == FULL_NAME


def test_two_creates_without_keys_still_make_two_contacts(idem_context) -> None:
    """The un-keyed path keeps the behaviour OQ-CBA-017 decided, cost and all.

    A caller who sends no key is asking for no idempotency, and gets none: two
    identical un-keyed submissions are two rows, exactly as before this header
    existed. Pinning it matters because the tempting "fix" for OQ-CBA-047 is to
    make the route deduplicate on its own, which would silently change what
    every existing caller gets.
    """
    client, unit_id, _, token = idem_context

    first = _create(client, unit_id, token)
    second = _create(client, unit_id, token)

    assert second.status_code == 201, second.text
    assert second.json()["professional_id"] != first.json()["professional_id"]
    assert len(_roster_ids(client, unit_id, token)) == 2


def test_a_create_without_a_key_still_reports_the_same_name_hint(idem_context) -> None:
    """Behaves exactly as today, **hint and all**.

    The duplicate hint is the interim answer OQ-CBA-021 shipped and it is not
    replaced by the key — it answers *is this name already here*, which is a
    different question from *did this request already happen*. A refactor that
    routed the un-keyed path through some shared helper and dropped the hint
    would pass every other test in this file.
    """
    client, unit_id, _, token = idem_context

    first = _create(client, unit_id, token)
    second = _create(client, unit_id, token, company="Okonkwo Partners")

    hint = second.json()["same_name_contacts"]

    assert [row["professional_id"] for row in hint] == [first.json()["professional_id"]]
    assert second.json()["same_name_truncated"] is False


def test_a_blank_key_is_treated_as_no_key_rather_than_as_a_key(idem_context) -> None:
    """Whitespace is absence, not an identity.

    A header that is one space is a client that failed to fill a template in.
    Binding a contact to ``" "`` would make the *next* such client a replay of
    this one — one Connector's contact handed to another because both their
    forms were broken the same way.
    """
    client, unit_id, _, token = idem_context

    first = _create(client, unit_id, token, key="   ")
    second = _create(client, unit_id, token, key="   ")

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert second.json()["professional_id"] != first.json()["professional_id"]


# ---------------------------------------------------------------------------
# Same key, same body: one row, the original answer
# ---------------------------------------------------------------------------


def test_the_same_key_twice_creates_only_one_contact(idem_context) -> None:
    """The double-clicked form. One click's worth of rows.

    The roster is read rather than the two response bodies compared, because a
    route that wrote a second row and *returned* the first would satisfy an
    id-equality assertion and still leave the unrepairable pair this decision
    exists to prevent.
    """
    client, unit_id, _, token = idem_context

    first = _create(client, unit_id, token, key="double-click")
    second = _create(client, unit_id, token, key="double-click")

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert _roster_ids(client, unit_id, token) == {first.json()["professional_id"]}


def test_a_replay_returns_the_original_status_and_the_identical_body(idem_context) -> None:
    """**What a replay returns: the original ``201`` and the original body.**

    Not a ``200``, not a ``409``, not an empty body with a ``Location`` header.
    From the caller's side one request happened, so they get the answer that
    request got — the substrate's existing replay contract (``submit_command``
    answers a replay with the original job) applied to a route that answers
    ``201`` rather than ``202``.

    Whole-body equality rather than a field-by-field spot check, because the
    parts are re-derived rather than read back from a stored response: the
    contact is re-read by id, ``withheld_fields`` follows from a request body
    the fingerprint has already proved identical, and ``same_name_contacts`` is
    re-asked with the replayed row excluded from its own answer. Equality here
    is what says those three re-derivations actually reproduce the original.
    """
    client, unit_id, _, token = idem_context

    first = _create(client, unit_id, token, key="retry-me")
    second = _create(client, unit_id, token, key="retry-me")

    assert second.status_code == first.status_code == 201
    assert second.json() == first.json()


def test_a_replay_does_not_report_the_contact_as_its_own_duplicate(idem_context) -> None:
    """The replayed row must not appear in its own ``same_name_contacts``.

    The original hint was read *before* the insert and so could not see the row
    it was about. A replay's hint is read after, and without the exclusion
    OQ-CBA-049 gave the edit path it would hand the Connector "somebody by this
    name is already here" pointing at the very contact they are looking at — a
    warning that means nothing, and therefore trains them past every warning.
    """
    client, unit_id, _, token = idem_context

    first = _create(client, unit_id, token, key="no-self-hint")
    second = _create(client, unit_id, token, key="no-self-hint")

    assert first.json()["same_name_contacts"] == []
    assert second.json()["same_name_contacts"] == []
    assert second.json()["same_name_truncated"] is False


def test_a_replay_repeats_the_withheld_contact_email_report(idem_context) -> None:
    """``withheld_fields`` survives the replay, because the discard did.

    OQ-CBA-015 has this route accept ``contact_email`` in order to refuse it and
    say so. A replay that dropped the report would tell the retrying caller that
    their address was stored — the opposite of what happened to it.
    """
    client, unit_id, _, token = idem_context

    first = _create(client, unit_id, token, key="withheld", contact_email="dana@example.com")
    second = _create(client, unit_id, token, key="withheld", contact_email="dana@example.com")

    assert first.json()["withheld_fields"] == ["contact_email"]
    assert second.json()["withheld_fields"] == ["contact_email"]


def test_the_reservation_and_the_contact_are_committed_together(idem_context) -> None:
    """One transaction, checked from outside the request that opened it.

    ``get_session`` rolls back unconditionally, so a route that forgot its
    ``session.commit()`` would return a clean ``201`` having stored nothing —
    and a route that committed the reservation separately from the insert would
    leave a key bound to a contact that does not exist, answering every later
    replay with a ``404``. Both rows are read back through a *second* request,
    which is the only way to tell a committed row from an uncommitted one.
    """
    client, unit_id, _, token = idem_context

    created = _create(client, unit_id, token, key="committed-together")
    professional_id = created.json()["professional_id"]

    fetched = client.get(
        f"/v1/units/{unit_id}/speaker-contacts/{professional_id}", headers=_auth(token)
    )
    replayed = _create(client, unit_id, token, key="committed-together")

    assert fetched.status_code == 200, fetched.text
    assert replayed.status_code == 201, replayed.text
    assert replayed.json()["professional_id"] == professional_id


def test_the_reservation_is_recorded_under_this_routes_own_command_type(
    idem_context, engine: Engine
) -> None:
    """The key is honored under ``speaker_contact.create`` and nothing else.

    ``uq_idempotency_scope`` is ``(tenant_id, command_type, idempotency_key)``,
    so the command type is what stops a key a Connector reused from an import
    submission from resolving to a contact — and the other way round. Read out
    of the table rather than inferred, because this is the one part of the
    reservation no response body shows.
    """
    client, unit_id, _, token = idem_context

    created = _create(client, unit_id, token, key="scoped-key")

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT command_type, job_id FROM idempotency_record "
                "WHERE idempotency_key = 'scoped-key'"
            )
        ).all()

    assert [row.command_type for row in rows] == [SPEAKER_CONTACT_CREATE_COMMAND_TYPE]
    # The reservation remembers the contact it made. That binding is the whole
    # of how a replay is answerable, since `idempotency_record` has nowhere to
    # store a response body.
    assert str(rows[0].job_id) == created.json()["professional_id"]


# ---------------------------------------------------------------------------
# Same key, different body: 409, and nothing written
# ---------------------------------------------------------------------------


def test_the_same_key_with_a_different_body_is_a_conflict(idem_context) -> None:
    """``409 idempotency_key_reused`` — the substrate's own rule, unchanged.

    Returning the earlier contact would silently discard the request the caller
    actually made, which is worse than failing. This is a conflict about a
    **key**, and it is the only ``409`` on this surface: there is still no
    ``409`` on a name.
    """
    client, unit_id, _, token = idem_context

    first = _create(client, unit_id, token, key="reused")
    conflicting = _create(client, unit_id, token, key="reused", title="Director of Analytics")

    assert first.status_code == 201, first.text
    assert conflicting.status_code == 409, conflicting.text
    assert conflicting.json()["error"]["code"] == "idempotency_key_reused"


def test_a_conflicting_reuse_writes_no_contact(idem_context) -> None:
    """A refused reuse leaves the roster exactly as the first create left it.

    The ``409`` propagates before any contact insert runs and nothing on that
    path commits, so the second request must be invisible in the data. A route
    that wrote first and checked afterwards would pass the status-code test
    above and fail this one.
    """
    client, unit_id, _, token = idem_context

    first = _create(client, unit_id, token, key="reused-no-write")
    _create(client, unit_id, token, key="reused-no-write", title="Director of Analytics")

    assert _roster_ids(client, unit_id, token) == {first.json()["professional_id"]}


def test_dropping_a_withheld_field_makes_a_different_request(idem_context) -> None:
    """``contact_email`` is part of the fingerprint even though it is discarded.

    A retry that drops the field is not the same request: the first response
    said ``withheld_fields: ["contact_email"]`` and a replay of it would repeat
    that claim to a caller who did not send one. Hashing what was *sent* keeps
    the answer honest about what happened to the caller's data.
    """
    client, unit_id, _, token = idem_context

    first = _create(client, unit_id, token, key="email-dropped", contact_email="dana@example.com")
    without = _create(client, unit_id, token, key="email-dropped")

    assert first.status_code == 201, first.text
    assert without.status_code == 409, without.text


def test_the_same_key_against_another_unit_is_a_conflict(idem_context) -> None:
    """The unit is in the fingerprint, and that is a safety property.

    ``uq_idempotency_scope`` does **not** include the owning unit, so without
    the unit in the fingerprint a key replayed against a second department with
    an otherwise identical body would be resolved as a replay and answered with
    the *first* department's contact — a row in a unit the caller did not ask
    about. A ``409`` is the honest answer: the caller reused a key for a
    different request.
    """
    client, unit_id, other_unit_id, token = idem_context

    first = _create(client, unit_id, token, key="crosses-units")
    crossed = _create(client, other_unit_id, token, key="crosses-units")

    assert first.status_code == 201, first.text
    assert crossed.status_code == 409, crossed.text
    assert _roster_ids(client, other_unit_id, token) == set()


def test_an_over_long_key_is_refused_rather_than_truncated(idem_context) -> None:
    """``400``, because truncation would collapse two keys sharing a prefix.

    Silently cutting a key at 255 characters would make two distinct requests
    with a long common prefix into a replay of each other, which is the exact
    accident a key exists to prevent.
    """
    client, unit_id, _, token = idem_context

    refused = _create(client, unit_id, token, key="k" * (MAX_IDEMPOTENCY_KEY_LENGTH + 1))

    assert refused.status_code == 400, refused.text
    assert refused.json()["error"]["code"] == "idempotency_key_too_long"
    assert _roster_ids(client, unit_id, token) == set()


def test_an_invalid_body_does_not_consume_the_key(idem_context) -> None:
    """A request that cannot be stored must not burn the key it carried.

    Validation runs before the reservation on purpose. Reserving first would
    bind the key to a request that ended in a ``400``, so the Connector's
    corrected retry — same key, fixed body — would come back ``409`` pointing at
    a contact that was never created, and they would have no way to proceed
    except to invent a new key.
    """
    client, unit_id, _, token = idem_context

    refused = _create(
        client, unit_id, token, key="fix-and-retry", primary_industry_code="not-a-sector"
    )
    corrected = _create(client, unit_id, token, key="fix-and-retry")

    assert refused.status_code == 400, refused.text
    assert corrected.status_code == 201, corrected.text


# ---------------------------------------------------------------------------
# Different keys, identical bodies: two people
# ---------------------------------------------------------------------------


def test_two_different_keys_with_identical_bodies_create_two_contacts(idem_context) -> None:
    """**The test that proves nothing here deduplicates by name.**

    Two byte-identical bodies, two different keys, two contacts. A scheme that
    keyed off ``full_name`` — a uniqueness constraint, an application-level
    refusal, a ``409`` on the name, or a quiet "return the existing row" — would
    collapse these into one, and would be wrong: two genuinely different
    professionals in one department can share a name, which is precisely what
    OQ-CBA-017's opaque identity exists to permit and what the old name-derived
    key made impossible.

    Idempotency is taken off the **request**. Two requests that differ only in
    their key are two requests.
    """
    client, unit_id, _, token = idem_context

    first = _create(client, unit_id, token, key="first-person")
    second = _create(client, unit_id, token, key="second-person")

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert second.json()["professional_id"] != first.json()["professional_id"]
    assert _roster_ids(client, unit_id, token) == {
        first.json()["professional_id"],
        second.json()["professional_id"],
    }


def test_the_second_of_two_keyed_creates_still_gets_the_duplicate_hint(idem_context) -> None:
    """Two people sharing a name still produce the warning that says so.

    The key stopped the second *request* from duplicating; it says nothing about
    the second *person*. A Connector adding a genuine namesake must still be
    told that somebody by that name is already on the roster, because that is
    the case where they most need to look before they save.
    """
    client, unit_id, _, token = idem_context

    first = _create(client, unit_id, token, key="namesake-one")
    second = _create(client, unit_id, token, key="namesake-two", company="Okonkwo Partners")

    hint = second.json()["same_name_contacts"]

    assert [row["professional_id"] for row in hint] == [first.json()["professional_id"]]
    assert hint[0]["full_name"] == FULL_NAME


def test_a_key_and_an_unkeyed_create_do_not_interfere(idem_context) -> None:
    """An un-keyed create is never a replay of a keyed one, or the reverse.

    A caller who sends no key has reserved nothing, so there is nothing for a
    later keyed request to collide with — and a caller holding a key must not
    have their contact handed to a request that never named it.
    """
    client, unit_id, _, token = idem_context

    keyed = _create(client, unit_id, token, key="keyed-only")
    unkeyed = _create(client, unit_id, token)

    assert unkeyed.status_code == 201, unkeyed.text
    assert unkeyed.json()["professional_id"] != keyed.json()["professional_id"]
    assert len(_roster_ids(client, unit_id, token)) == 2
