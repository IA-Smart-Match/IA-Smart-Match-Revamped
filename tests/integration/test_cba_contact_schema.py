"""What migration ``0025``'s contact identity columns refuse, against real PostgreSQL.

Customer §13 gives a Speaker Connector a surface for adding a professional
contact by hand and reading their unit's contacts back. Every operation on it
renders a person, and until ``0025`` the schema had nowhere to hold one: no
revision from ``0001`` to ``0024`` created a person-name, company, or job-title
column, and the only ``title`` in the database was ``event.title``.

Two kinds of assertion live here, and the split is deliberate.

The **revision-graph** tests need no database at all. They read the Alembic
script directory the way ``alembic upgrade head`` does and require ``0025`` to
be the single head, chained to ``0024``. That is a cheap check for an expensive
failure: a second head does not fail loudly at migration time, it makes
``upgrade head`` ambiguous, and the branch that produced it is usually merged by
then. This project has several CBA cards writing migrations in parallel, which
is exactly the condition that produces one.

The **constraint** tests attempt the write and require the database to answer,
following ``test_cba_classification_schema.py``'s discipline: none of them goes
through a repository, because a test routed through application code would prove
the guard rather than the constraint.

Requires a live database for the second group, and is skipped when none is
reachable.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")

from conftest import ensure_owning_unit, unique_subject
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration

#: Repository root, from ``tests/integration/`` — the same two-parent hop
#: ``migration_harness.REPO_ROOT`` makes, restated rather than imported so this
#: module does not depend on a harness it otherwise has no use for.
_REPO_ROOT = Path(__file__).resolve().parents[2]

#: The revision this card adds, and the one it must follow. Spelled as the
#: revision **ids** and not the filenames: ``0024``'s file is
#: ``0024_cba_classification_schema.py`` while its id is
#: ``0024_cba_classification``, and a ``down_revision`` naming the filename
#: produces a migration Alembic cannot resolve at all.
_THIS_REVISION = "0025_cba_contact_identity"
_PARENT_REVISION = "0024_cba_classification"


def _script_directory():
    """The Alembic script directory, loaded from ``db/alembic.ini``.

    Imported inside the function rather than at module scope so the two
    revision-graph tests skip cleanly where Alembic is not installed, instead of
    failing collection for the whole module.
    """
    alembic_config = pytest.importorskip("alembic.config")
    alembic_script = pytest.importorskip("alembic.script")

    config = alembic_config.Config(str(_REPO_ROOT / "db" / "alembic.ini"))
    # `script_location` in the ini is relative to `db/`, which is the working
    # directory an operator runs Alembic from. Resolved here rather than
    # chdir-ing, because a test that changes the process's working directory
    # changes it for every test that runs after it in the same session.
    config.set_main_option("script_location", str(_REPO_ROOT / "db" / "migrations"))
    return alembic_script.ScriptDirectory.from_config(config)


# ---------------------------------------------------------------------------
# The revision graph. No database.
# ---------------------------------------------------------------------------


def test_zero_zero_two_five_is_the_only_head():
    """One head, and it is this card's revision.

    Two heads is the failure mode of parallel migration work, and it is quiet:
    Alembic refuses ``upgrade head`` with an ambiguity error only at deploy
    time, on a branch that has already merged. Asserting the *name* as well as
    the count means a later card that legitimately extends the chain has to come
    here and say so, which is the point at which someone notices whether the two
    revisions actually compose.
    """
    heads = _script_directory().get_heads()

    assert heads == [_THIS_REVISION], (
        f"expected {_THIS_REVISION} to be the single Alembic head, got {heads}. "
        "More than one head means `alembic upgrade head` is ambiguous; a "
        "different single head means this revision was superseded without this "
        "assertion being updated."
    )


def test_zero_zero_two_five_follows_the_classification_revision():
    """``down_revision`` names ``0024``'s revision id, not its filename.

    The distinction has teeth: ``0024`` lives in
    ``0024_cba_classification_schema.py`` and declares
    ``revision = "0024_cba_classification"``. A ``down_revision`` pointing at the
    filename resolves to nothing, and Alembic reports it as a missing revision
    rather than as a typo.
    """
    script = _script_directory().get_revision(_THIS_REVISION)

    assert script.down_revision == _PARENT_REVISION


# ---------------------------------------------------------------------------
# The constraints. Real PostgreSQL.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_speaker_profiles(engine: Engine, tenant_id):
    """Delete this file's rows before ``tenant_id`` tears its own down.

    ``speaker_profile`` holds ``ON DELETE RESTRICT`` references to both
    ``user_account`` and ``org_unit``, so a row left behind here would make
    ``conftest.py``'s teardown fail on those deletes — the hazard
    ``test_cba_classification_schema.py``'s own cleanup fixture exists for.
    """
    yield
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM speaker_profile WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        )


def _make_professional(conn, tenant_id: uuid.UUID) -> uuid.UUID:
    """One ``user_account``, which is what a professional's identity is today.

    Routed through :func:`conftest.unique_subject` because ``external_subject``
    is globally unique as of migration ``0003`` — ``0007`` dropped the
    tenant-scoped constraint that used to stand beside it, so the global one is
    the only one left.
    """
    professional_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO user_account (id, tenant_id, external_subject, email) "
            "VALUES (:id, :tid, :sub, :email)"
        ),
        {
            "id": professional_id,
            "tid": tenant_id,
            "sub": unique_subject(f"contact-{professional_id.hex[:8]}"),
            "email": f"{professional_id.hex[:8]}@example.edu",
        },
    )
    return professional_id


def _insert_profile(
    conn,
    tenant_id: uuid.UUID,
    *,
    full_name: str | None = "Dana Reyes",
    company: str | None = "Reyes Analytics",
    title: str | None = "Principal Analyst",
) -> uuid.UUID:
    """A row every constraint accepts, so a test body holds only the value under test."""
    professional_id = _make_professional(conn, tenant_id)
    conn.execute(
        text(
            "INSERT INTO speaker_profile "
            "(tenant_id, professional_id, owning_unit_id, full_name, company, title) "
            "VALUES (:tid, :pid, :unit, :full_name, :company, :title)"
        ),
        {
            "tid": tenant_id,
            "pid": professional_id,
            "unit": ensure_owning_unit(conn, tenant_id),
            "full_name": full_name,
            "company": company,
            "title": title,
        },
    )
    return professional_id


def test_a_contact_stores_name_company_and_title(engine: Engine, tenant_id):
    """The happy path §13 needs, asserted by reading the row back.

    Written as a read rather than as "the insert did not raise", because the
    failure this guards against is a column that exists and silently discards
    what is written to it.
    """
    with engine.begin() as conn:
        professional_id = _insert_profile(conn, tenant_id)
        row = conn.execute(
            text(
                "SELECT full_name, company, title FROM speaker_profile "
                "WHERE tenant_id = :tid AND professional_id = :pid"
            ),
            {"tid": tenant_id, "pid": professional_id},
        ).one()

    assert row.full_name == "Dana Reyes"
    assert row.company == "Reyes Analytics"
    assert row.title == "Principal Analyst"


def test_a_contact_without_a_name_is_refused(engine: Engine, tenant_id):
    """``full_name`` is NOT NULL: a record nobody can act on is not a contact."""
    with pytest.raises(IntegrityError), engine.begin() as conn:
        _insert_profile(conn, tenant_id, full_name=None)


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_a_blank_name_is_refused(engine: Engine, tenant_id, blank: str):
    """NOT NULL rejects the absence and says nothing about ``'   '``.

    A whitespace-only name is a name-shaped value that renders as nothing, which
    is the state ADR-0011 exists to keep out: absent is a value, blank is a
    writer that forgot.
    """
    with pytest.raises(IntegrityError), engine.begin() as conn:
        _insert_profile(conn, tenant_id, full_name=blank)


@pytest.mark.parametrize("column", ["company", "title"])
def test_an_absent_company_or_title_is_a_real_state(engine: Engine, tenant_id, column: str):
    """NULL is accepted for both, and deliberately.

    A retired professional, an independent consultant, and a contact met before
    the Connector learned where they work are all §13 cases. Requiring a value
    produces ``"Unknown"`` strings that outlive the uncertainty that made them.
    """
    with engine.begin() as conn:
        professional_id = _insert_profile(conn, tenant_id, **{column: None})
        stored = conn.execute(
            text(
                # `column` is one of two literals fixed by the parametrize
                # decorator above; nothing caller-supplied reaches this string.
                f"SELECT {column} AS value FROM speaker_profile "
                "WHERE tenant_id = :tid AND professional_id = :pid"
            ),
            {"tid": tenant_id, "pid": professional_id},
        ).scalar_one()

    assert stored is None


@pytest.mark.parametrize("column", ["company", "title"])
@pytest.mark.parametrize("blank", ["", "  "])
def test_a_blank_company_or_title_is_refused(engine: Engine, tenant_id, column: str, blank: str):
    """The two new nullable columns join ``ck_speaker_profile_text_present``.

    They join it rather than getting a constraint of their own, so
    ``speaker_profile`` keeps one answer to "which text columns refuse blanks"
    instead of two that could drift apart.
    """
    with pytest.raises(IntegrityError), engine.begin() as conn:
        _insert_profile(conn, tenant_id, **{column: blank})


def test_the_original_blank_text_columns_are_still_refused(engine: Engine, tenant_id):
    """``0025`` recreates ``0024``'s constraint, so ``0024``'s arms must survive.

    Drop-and-recreate is how a ``CHECK`` is widened in PostgreSQL, and it is
    also how the original arms get dropped by accident. This asserts one of them
    still bites.
    """
    with pytest.raises(IntegrityError), engine.begin() as conn:
        professional_id = _make_professional(conn, tenant_id)
        conn.execute(
            text(
                "INSERT INTO speaker_profile "
                "(tenant_id, professional_id, owning_unit_id, full_name, topic_text) "
                "VALUES (:tid, :pid, :unit, 'Dana Reyes', '   ')"
            ),
            {
                "tid": tenant_id,
                "pid": professional_id,
                "unit": ensure_owning_unit(conn, tenant_id),
            },
        )
