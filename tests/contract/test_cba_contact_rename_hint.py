"""The §13 edit tells a Connector it just renamed somebody onto an existing name.

**OQ-CBA-049, decided 2026-09-06.** The create has warned about a same-name
contact since OQ-CBA-017 traded ``409 speaker_contact_name_already_used`` for a
hint. The edit warned about nothing: a Connector could rename one of two people
into the other's name and read a clean ``200``, which is the same hazard from
the other direction with no signal at all.

The edit now answers ``name_now_shared_with``, and **not** the create's
``same_name_contacts``. The separate field is the decision, not an accident of
implementation: a create's hint means *you may be about to duplicate somebody*
and an edit's means *you may have just collided with somebody*. The first is
about a record that did not exist a moment ago, the second about one that has
been on the roster for months and just changed its label — and a client holding
the one under the other's key would be reading the wrong sentence. Half the
assertions below are about keeping the two apart.

Still a hint and still never a refusal. Every rename in this file returns
``200`` and every one of them is stored. There is no uniqueness constraint on
``(tenant_id, owning_unit_id, full_name)`` and there is not going to be one
(OQ-CBA-021); nothing here asserts a status code other than the success the edit
already had.

``tests/contract/test_cba_contact_duplicate_hint.py`` owns the create's side of
this; ``tests/integration/test_cba_rename_same_name_lookup.py`` owns the read
underneath. Requires a live database, and is skipped when none is reachable.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest

pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient
from smartmatch_api.main import app
from smartmatch_api.routers.cba_contacts import MAX_SAME_NAME_HINTS
from smartmatch_persistence.engine import create_session_factory
from smartmatch_providers import FixtureTokenVerifier
from sqlalchemy import Engine, create_engine, text

pytestmark = pytest.mark.integration

DATABASE_URL = os.getenv(
    "SMARTMATCH_DATABASE_URL",
    "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch",
)

UNIT_PATH = "iawest.renamehint"

FULL_NAME = "Dana Reyes"
TYPO_NAME = "Dana Ryes"
FREE_NAME = "Ola Okonkwo"
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

    Probes for ``ix_speaker_profile_unit_folded_name`` — migration ``0030``'s
    index, and the one the same-name read relies on — for the reason
    ``test_cba_contact_duplicate_hint.py`` states: a database migrated only to
    ``0029`` should skip naming its cause rather than fail every test on a
    response field that does not exist yet.
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
def rename_context(engine: Engine) -> Iterator[tuple[TestClient, uuid.UUID, str]]:
    """One tenant, one department, and a Speaker Connector who may edit it."""
    tenant_id = uuid.uuid4()
    unit_id = uuid.uuid4()
    token = f"tok-renamehint-{uuid.uuid4().hex}"
    user_id = uuid.uuid4()
    subject = f"sub-rename-hint-{uuid.uuid4().hex}"

    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": tenant_id, "slug": f"test-renamehint-{tenant_id.hex[:12]}"},
        )
        conn.execute(
            text(
                "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                "VALUES (:id, :tid, CAST(:path AS ltree), 'department', 'Rename hint')"
            ),
            {"id": unit_id, "tid": tenant_id, "path": UNIT_PATH},
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

    yield client, unit_id, token

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


def _edit(client: TestClient, unit_id: uuid.UUID, token: str, professional_id: str, **overrides):
    return client.patch(
        f"/v1/units/{unit_id}/speaker-contacts/{professional_id}",
        json=_body(**overrides),
        headers=_auth(token),
    )


# ---------------------------------------------------------------------------
# The hint fires — a rename onto a name somebody else holds
# ---------------------------------------------------------------------------


def test_a_rename_into_an_existing_name_is_hinted(rename_context) -> None:
    """The case the card exists for, and the one that used to be silent.

    Two people, one of them typed wrong. Correcting the typo lands the second
    contact on the first's name — the identical collision a create would be
    warned about, arriving through the route that said nothing. The employer is
    asserted beside the id for the create hint's reason: "Dana Reyes at Reyes
    Analytics" is recognizable and a bare UUID is not.
    """
    client, unit_id, token = rename_context

    resident = _create(client, unit_id, token)
    typo = _create(client, unit_id, token, full_name=TYPO_NAME, company="Okonkwo Partners")

    renamed = _edit(
        client,
        unit_id,
        token,
        typo.json()["professional_id"],
        full_name=FULL_NAME,
        company="Okonkwo Partners",
    )

    assert renamed.status_code == 200, renamed.text
    hint = renamed.json()["name_now_shared_with"]
    assert [row["professional_id"] for row in hint] == [resident.json()["professional_id"]]
    assert hint[0]["full_name"] == FULL_NAME
    assert hint[0]["company"] == COMPANY


def test_the_rename_is_stored_rather_than_refused(rename_context) -> None:
    """The hint warns and never blocks — no ``409``, and no constraint behind one.

    Read back through a second request rather than off the edit's own echo: a
    route that reported a collision and quietly declined to write would pass an
    assertion on its response body and fail this one. Two people may share a
    name (OQ-CBA-017), and there is no uniqueness constraint on
    ``(tenant_id, owning_unit_id, full_name)`` to make it otherwise
    (OQ-CBA-021).
    """
    client, unit_id, token = rename_context

    _create(client, unit_id, token)
    typo = _create(client, unit_id, token, full_name=TYPO_NAME)
    professional_id = typo.json()["professional_id"]

    _edit(client, unit_id, token, professional_id, full_name=FULL_NAME)

    fetched = client.get(
        f"/v1/units/{unit_id}/speaker-contacts/{professional_id}", headers=_auth(token)
    )
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["full_name"] == FULL_NAME
    assert fetched.json()["professional_id"] == professional_id


def test_the_rename_hint_folds_case_and_surrounding_space(rename_context) -> None:
    """The edit folds exactly as the create does: ``lower(btrim(...))``.

    ``"  DANA REYES  "`` is the commonest way one person acquires a second
    record, and a hint that matched byte-identical strings would miss it on the
    edit route while catching it on the create — two answers to one question.
    """
    client, unit_id, token = rename_context

    resident = _create(client, unit_id, token)
    typo = _create(client, unit_id, token, full_name=TYPO_NAME)

    renamed = _edit(
        client, unit_id, token, typo.json()["professional_id"], full_name="  DANA REYES  "
    )

    assert renamed.status_code == 200, renamed.text
    assert [row["professional_id"] for row in renamed.json()["name_now_shared_with"]] == [
        resident.json()["professional_id"]
    ]


# ---------------------------------------------------------------------------
# The hint stays quiet
# ---------------------------------------------------------------------------


def test_a_rename_into_a_free_name_reports_nothing(rename_context) -> None:
    """Quiet when there is nothing to say.

    Asserted alongside the positive case because a field that is always
    populated tells a Connector nothing and teaches them to skip it — the same
    reason ``withheld_fields`` reports only a discard that actually happened.
    """
    client, unit_id, token = rename_context

    _create(client, unit_id, token)
    other = _create(client, unit_id, token, full_name=TYPO_NAME)

    renamed = _edit(client, unit_id, token, other.json()["professional_id"], full_name=FREE_NAME)

    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name_now_shared_with"] == []
    assert renamed.json()["name_now_shared_with_truncated"] is False


def test_an_edit_that_leaves_the_name_alone_reports_nothing(rename_context) -> None:
    """A no-op on the name is not a rename, even while a collision exists.

    Both contacts already carry the name here, so an unconditional lookup would
    fire. §13's form posts the whole record on every save, so a hint that
    ignored whether the name *moved* would re-announce a collision the Connector
    settled weeks ago, on every edit of every field, forever — which is how a
    warning becomes something people click past.
    """
    client, unit_id, token = rename_context

    _create(client, unit_id, token)
    second = _create(client, unit_id, token, company="Okonkwo Partners")

    edited = _edit(
        client,
        unit_id,
        token,
        second.json()["professional_id"],
        company="Okonkwo Partners",
        title="Managing Partner",
    )

    assert edited.status_code == 200, edited.text
    assert edited.json()["title"] == "Managing Partner"
    assert edited.json()["name_now_shared_with"] == []


def test_a_re_cased_name_is_not_a_rename(rename_context) -> None:
    """Re-spacing or re-casing a name does not move the collision set.

    The comparison is the create's fold on both sides, so ``"dana reyes"`` and
    ``"Dana Reyes"`` are the same name arriving twice. Reporting a collision
    here would be reporting one that existed before the request and was not
    caused by it.
    """
    client, unit_id, token = rename_context

    _create(client, unit_id, token)
    second = _create(client, unit_id, token, company="Okonkwo Partners")

    edited = _edit(
        client,
        unit_id,
        token,
        second.json()["professional_id"],
        full_name="  dana reyes ",
        company="Okonkwo Partners",
    )

    assert edited.status_code == 200, edited.text
    assert edited.json()["name_now_shared_with"] == []


def test_a_near_miss_rename_is_not_hinted(rename_context) -> None:
    """**OQ-CBA-050: exact folded match only.**

    ``"Dana Ryes"`` and ``"Dana Reyes"`` differ by one letter and are two
    different names. No similarity matching, no cutoff, nothing to tune — a hint
    that guessed at near-misses would fire constantly on a real roster and be
    ignored within a week. Revisitable when there is a roster large enough to
    measure a false-positive rate on.
    """
    client, unit_id, token = rename_context

    _create(client, unit_id, token)
    second = _create(client, unit_id, token, company="Okonkwo Partners")

    edited = _edit(
        client,
        unit_id,
        token,
        second.json()["professional_id"],
        full_name=TYPO_NAME,
        company="Okonkwo Partners",
    )

    assert edited.status_code == 200, edited.text
    assert edited.json()["name_now_shared_with"] == []


def test_a_contact_is_never_reported_as_sharing_a_name_with_itself(rename_context) -> None:
    """Self-exclusion, on the route where it is not free.

    The renamed row carries the new name the moment the ``UPDATE`` lands, so an
    unfiltered lookup would return the contact in its own hint and warn every
    Connector about every rename. The create gets this guarantee by reading
    before it inserts; the edit has to ask for it, and this is the assertion
    that it does.
    """
    client, unit_id, token = rename_context

    created = _create(client, unit_id, token, full_name=TYPO_NAME)
    professional_id = created.json()["professional_id"]

    renamed = _edit(client, unit_id, token, professional_id, full_name=FULL_NAME)

    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name_now_shared_with"] == []


# ---------------------------------------------------------------------------
# The two hints are two messages
# ---------------------------------------------------------------------------


def test_the_edit_does_not_populate_the_creates_field(rename_context) -> None:
    """``same_name_contacts`` is the create's word and stays the create's.

    A create says *you may be about to duplicate somebody*; an edit says *you
    may have just collided with somebody*. Sending the second under the first's
    key would make a client's reading of it wrong in a way no status code would
    reveal, so the edit populates its own field and leaves the create's empty —
    which is what the create's own description promises.
    """
    client, unit_id, token = rename_context

    _create(client, unit_id, token)
    typo = _create(client, unit_id, token, full_name=TYPO_NAME)

    renamed = _edit(client, unit_id, token, typo.json()["professional_id"], full_name=FULL_NAME)

    body = renamed.json()
    assert body["same_name_contacts"] == []
    assert body["same_name_truncated"] is False
    assert body["name_now_shared_with"] != []


def test_the_create_does_not_populate_the_edits_field(rename_context) -> None:
    """The mirror assertion, so neither route can quietly acquire the other's.

    A create that also answered ``name_now_shared_with`` would be claiming it
    had just moved a name onto somebody, which is not what it did.
    """
    client, unit_id, token = rename_context

    _create(client, unit_id, token)
    second = _create(client, unit_id, token, company="Okonkwo Partners")

    body = second.json()
    assert body["name_now_shared_with"] == []
    assert body["name_now_shared_with_truncated"] is False
    assert body["same_name_contacts"] != []


def test_a_read_reports_neither_hint(rename_context) -> None:
    """A ``GET`` asked no question, so both fields are empty for the same reason.

    Pinned so neither can quietly become a per-row duplicate flag that every
    roster screen would start rendering — a claim nothing would keep current.
    """
    client, unit_id, token = rename_context

    resident = _create(client, unit_id, token)
    typo = _create(client, unit_id, token, full_name=TYPO_NAME)
    _edit(client, unit_id, token, typo.json()["professional_id"], full_name=FULL_NAME)

    fetched = client.get(
        f"/v1/units/{unit_id}/speaker-contacts/{resident.json()['professional_id']}",
        headers=_auth(token),
    )

    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["name_now_shared_with"] == []
    assert fetched.json()["same_name_contacts"] == []


# ---------------------------------------------------------------------------
# The cap
# ---------------------------------------------------------------------------


def test_the_hint_is_capped_and_says_when_it_truncated(rename_context) -> None:
    """A capped hint must never read as the complete set.

    One more than ``MAX_SAME_NAME_HINTS`` residents already carry the name, and
    the contact renamed onto it makes the collision: the response carries the
    cap and admits there were more, answered by reading one row past it rather
    than by a second count — the create's arrangement and the roster listing's
    before that. A unit holding eleven people under one folded name has a
    problem a longer list would not help with; being told the list is partial is
    what sends the Connector to the roster.
    """
    client, unit_id, token = rename_context

    for index in range(MAX_SAME_NAME_HINTS + 1):
        resident = _create(client, unit_id, token, company=f"Employer {index}")
        assert resident.status_code == 201, resident.text
    typo = _create(client, unit_id, token, full_name=TYPO_NAME)

    renamed = _edit(client, unit_id, token, typo.json()["professional_id"], full_name=FULL_NAME)

    assert renamed.status_code == 200, renamed.text
    body = renamed.json()
    assert len(body["name_now_shared_with"]) == MAX_SAME_NAME_HINTS
    assert body["name_now_shared_with_truncated"] is True


def test_a_hint_exactly_at_the_cap_is_not_truncated(rename_context) -> None:
    """The boundary the ``+ 1`` read exists to get right.

    Exactly ``MAX_SAME_NAME_HINTS`` other contacts share the name, so the list
    is full and complete at once. An off-by-one here would tell a Connector
    there are more people to find when there are not, which is the same kind of
    lie as hiding some.
    """
    client, unit_id, token = rename_context

    for index in range(MAX_SAME_NAME_HINTS):
        _create(client, unit_id, token, company=f"Employer {index}")
    typo = _create(client, unit_id, token, full_name=TYPO_NAME)

    renamed = _edit(client, unit_id, token, typo.json()["professional_id"], full_name=FULL_NAME)

    assert renamed.status_code == 200, renamed.text
    body = renamed.json()
    assert len(body["name_now_shared_with"]) == MAX_SAME_NAME_HINTS
    assert body["name_now_shared_with_truncated"] is False


# ---------------------------------------------------------------------------
# The edit's other answers are unchanged
# ---------------------------------------------------------------------------


def test_an_edit_of_a_contact_in_another_unit_is_still_a_404(rename_context) -> None:
    """The pre-read the hint needs must not have changed what a miss looks like.

    The edit now reads the stored contact before writing it, so a miss could in
    principle report something different from the 404 the write itself used to
    produce. A contact that exists elsewhere and one that does not exist at all
    are still one answer, for ``_not_found``'s stated reason: a 403 would
    confirm that an id the caller may not read names a real person.
    """
    client, unit_id, token = rename_context

    missing = _edit(client, unit_id, token, str(uuid.uuid4()), full_name=FREE_NAME)

    assert missing.status_code == 404, missing.text
    assert missing.json()["error"]["code"] == "speaker_contact_not_found"
