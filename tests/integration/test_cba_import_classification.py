"""What migration ``0028``'s provenance constraints accept and refuse.

``test_cba_classification_schema.py`` owns ``0024``'s two code columns — which
codes are storable, and that a code travels with its taxonomy version. This
module owns the three columns per axis ``0028`` added beside them, and the
single question they exist to answer: **can a reader tell whether anybody looked
at this classification?**

The forbidden write that matters most is
:func:`test_an_inferred_classification_cannot_name_an_actor`, and it is the one
no other test in this repository could make. Nothing in the application can
construct that row — ``smartmatch_domain.cba_classification.inferred_classification``
offers no actor parameter at all — so a test driven through the domain would
pass whether or not the constraint existed. Written as raw SQL here, it asserts
that "a classifier's proposal must not be recordable as somebody's judgment" is
a property of the database rather than of one module's shape.

Every case is parametrized over both axes rather than written twice, which is
``0028``'s own reason for iterating ``_AXES``: an arm tightened on ``industry``
and left slack on ``role`` is exactly the divergence a hand-written pair hides.

The vocabulary binding the migration docstring promises is here too, in
:func:`test_every_released_classification_source_is_storable`: it parametrizes
over ``CLASSIFICATION_SOURCES`` *from the domain module*, so a third source
added in Python without a migration fails here rather than in a Connector's
screen.

Requires a live database, and is skipped when none is reachable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

pytest.importorskip("sqlalchemy")

from conftest import ensure_owning_unit, unique_subject
from smartmatch_domain.cba_classification import (
    CLASSIFICATION_SOURCE_HUMAN,
    CLASSIFICATION_SOURCE_INFERRED,
    CLASSIFICATION_SOURCES,
)
from smartmatch_domain.cba_role_categories import CBA_ROLE_TAXONOMY_VERSION
from smartmatch_domain.naics_sectors import NAICS_TAXONOMY_VERSION
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration

#: One value per axis, so a parametrized case names its axis and nothing else.
#: The codes themselves are arbitrary members of the two closed taxonomies —
#: which codes are legal is ``test_cba_classification_schema.py``'s subject, not
#: this module's.
_AXIS_CODES = {
    "industry": ("52", NAICS_TAXONOMY_VERSION),
    "role": ("finance", CBA_ROLE_TAXONOMY_VERSION),
}

_AXES = tuple(_AXIS_CODES)

#: A fixed instant rather than ``now()``: no assertion here depends on the value,
#: and a literal keeps every insert's parameters a plain dict.
_CLASSIFIED_AT = datetime(2026, 9, 6, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _clean_profiles(engine: Engine, tenant_id):
    """Delete this file's rows before ``tenant_id`` tears its own down.

    ``speaker_profile`` holds ``ON DELETE RESTRICT`` references to
    ``user_account`` and ``org_unit`` — and, as of ``0028``, a second one into
    ``user_account`` through the actor columns — so a row left behind here would
    make ``conftest.py``'s teardown fail on those deletes.
    """
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM speaker_profile WHERE tenant_id = :tid"), {"tid": tenant_id})


def _make_account(conn, tenant_id: uuid.UUID) -> uuid.UUID:
    """One ``user_account``, usable as a professional or as an actor.

    Both are the same table today, and a test that names an actor needs two
    rows: ``speaker_profile.professional_id`` and
    ``{axis}_classified_by_user_id`` are separate foreign keys into it.
    Routed through :func:`conftest.unique_subject` because ``external_subject``
    is globally unique as of migration ``0003``.
    """
    account_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO user_account (id, tenant_id, external_subject, email) "
            "VALUES (:id, :tid, :sub, :email)"
        ),
        {
            "id": account_id,
            "tid": tenant_id,
            "sub": unique_subject(f"provenance-{account_id.hex[:8]}"),
            "email": f"{account_id.hex[:8]}@example.edu",
        },
    )
    return account_id


def _insert(
    conn,
    tenant_id: uuid.UUID,
    *,
    axis: str,
    code: str | None,
    taxonomy_version: str | None,
    source: str | None,
    actor_id: uuid.UUID | None,
    classified_at: datetime | None,
) -> uuid.UUID:
    """One ``speaker_profile`` row stating one axis and leaving the other absent.

    One axis at a time on purpose: a row classifying both would engage two
    constraints at once, and a refusal would not say which arm it failed. The
    unnamed axis stays in the unclassified arm, which every case here relies on
    being independently legal — and which
    :func:`test_an_unclassified_contact_is_storable` asserts rather than assumes.
    """
    professional_id = _make_account(conn, tenant_id)
    owning_unit_id = ensure_owning_unit(conn, tenant_id)
    conn.execute(
        text(
            "INSERT INTO speaker_profile (tenant_id, professional_id, owning_unit_id, "
            f"full_name, primary_{axis}_code, {axis}_taxonomy_version, "
            f"{axis}_classification_source, {axis}_classified_by_user_id, "
            f"{axis}_classified_at) "
            "VALUES (:tid, :pid, :unit, :full_name, :code, :version, :source, :actor, :at)"
        ),
        {
            "tid": tenant_id,
            "pid": professional_id,
            "unit": owning_unit_id,
            "full_name": "Speaker Under Test",
            "code": code,
            "version": taxonomy_version,
            "source": source,
            "actor": actor_id,
            "at": classified_at,
        },
    )
    return professional_id


# ---------------------------------------------------------------------------
# The permitted half — one test per arm, so an inverted constraint fails here
# rather than passing on a refusal it made for the wrong reason.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("axis", _AXES)
def test_an_inferred_proposal_is_storable_without_an_actor(
    engine: Engine, tenant_id, axis: str
) -> None:
    """§19's steps three and four: the pipeline proposed, and nobody has looked yet.

    This is the row every import writes, and the reason the actor column is
    nullable rather than ``NOT NULL``.
    """
    code, version = _AXIS_CODES[axis]
    with engine.begin() as conn:
        professional_id = _insert(
            conn,
            tenant_id,
            axis=axis,
            code=code,
            taxonomy_version=version,
            source=CLASSIFICATION_SOURCE_INFERRED,
            actor_id=None,
            classified_at=_CLASSIFIED_AT,
        )
        stored = conn.execute(
            text(
                f"SELECT {axis}_classification_source AS source, "
                f"{axis}_classified_by_user_id AS actor "
                "FROM speaker_profile WHERE tenant_id = :tid AND professional_id = :pid"
            ),
            {"tid": tenant_id, "pid": professional_id},
        ).one()

    assert stored.source == CLASSIFICATION_SOURCE_INFERRED
    assert stored.actor is None


@pytest.mark.parametrize("axis", _AXES)
def test_a_human_classification_is_storable_with_its_actor(
    engine: Engine, tenant_id, axis: str
) -> None:
    """§19's step five: a Connector decided, and the row says which Connector."""
    code, version = _AXIS_CODES[axis]
    with engine.begin() as conn:
        actor_id = _make_account(conn, tenant_id)
        professional_id = _insert(
            conn,
            tenant_id,
            axis=axis,
            code=code,
            taxonomy_version=version,
            source=CLASSIFICATION_SOURCE_HUMAN,
            actor_id=actor_id,
            classified_at=_CLASSIFIED_AT,
        )
        stored = conn.execute(
            text(
                f"SELECT {axis}_classification_source AS source, "
                f"{axis}_classified_by_user_id AS actor, "
                f"{axis}_classified_at AS classified_at "
                "FROM speaker_profile WHERE tenant_id = :tid AND professional_id = :pid"
            ),
            {"tid": tenant_id, "pid": professional_id},
        ).one()

    assert stored.source == CLASSIFICATION_SOURCE_HUMAN
    assert stored.actor == actor_id
    assert stored.classified_at == _CLASSIFIED_AT


@pytest.mark.parametrize("axis", _AXES)
def test_an_unclassified_contact_is_storable(engine: Engine, tenant_id, axis: str) -> None:
    """§19 imports a contact first and classifies it after.

    All four columns absent together is a real state and not a placeholder — the
    permitted half of the arm
    :func:`test_an_unclassified_axis_cannot_carry_provenance` approaches from the
    other side.
    """
    with engine.begin() as conn:
        professional_id = _insert(
            conn,
            tenant_id,
            axis=axis,
            code=None,
            taxonomy_version=None,
            source=None,
            actor_id=None,
            classified_at=None,
        )
        stored = conn.execute(
            text(
                f"SELECT primary_{axis}_code AS code, "
                f"{axis}_classification_source AS source "
                "FROM speaker_profile WHERE tenant_id = :tid AND professional_id = :pid"
            ),
            {"tid": tenant_id, "pid": professional_id},
        ).one()

    assert stored.code is None
    assert stored.source is None


@pytest.mark.parametrize("axis", _AXES)
@pytest.mark.parametrize("source", CLASSIFICATION_SOURCES)
def test_every_released_classification_source_is_storable(
    engine: Engine, tenant_id, axis: str, source: str
) -> None:
    """Driven from the domain's own tuple, so a third source fails here first.

    Migration ``0028`` transcribes its two literals rather than importing them —
    a ``CHECK`` cannot import Python, and a migration describes the database as
    of the moment it ran. This is the binding that keeps the transcription
    honest: a source added to ``CLASSIFICATION_SOURCES`` without a migration
    fails here rather than in a Connector's screen.

    The actor is supplied only for ``human``, because that is precisely what
    separates the two arms; a source needing some third combination would fail
    here too, which is the point.
    """
    code, version = _AXIS_CODES[axis]
    with engine.begin() as conn:
        actor_id = _make_account(conn, tenant_id) if source == CLASSIFICATION_SOURCE_HUMAN else None
        _insert(
            conn,
            tenant_id,
            axis=axis,
            code=code,
            taxonomy_version=version,
            source=source,
            actor_id=actor_id,
            classified_at=_CLASSIFIED_AT,
        )


# ---------------------------------------------------------------------------
# The forbidden half.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("axis", _AXES)
def test_an_inferred_classification_cannot_name_an_actor(
    engine: Engine, tenant_id, axis: str
) -> None:
    """The card's central non-negotiable, asserted against the database.

    A row saying "the classifier proposed Finance, and Dana approved it" is a
    record of a review that never happened. The application cannot build one —
    ``inferred_classification`` takes no actor — but this test does not go
    through the application, deliberately: a rule enforced only by a function
    signature is one a hand-written UPDATE, a later route, or a data fix can
    walk around without noticing.
    """
    code, version = _AXIS_CODES[axis]
    with (
        pytest.raises(IntegrityError, match=f"ck_speaker_profile_{axis}_provenance"),
        engine.begin() as conn,
    ):
        actor_id = _make_account(conn, tenant_id)
        _insert(
            conn,
            tenant_id,
            axis=axis,
            code=code,
            taxonomy_version=version,
            source=CLASSIFICATION_SOURCE_INFERRED,
            actor_id=actor_id,
            classified_at=_CLASSIFIED_AT,
        )


@pytest.mark.parametrize("axis", _AXES)
def test_a_classified_axis_must_state_its_provenance(engine: Engine, tenant_id, axis: str) -> None:
    """A stored code with no source is the ambiguity ``0028`` exists to remove.

    It is also exactly the row every writer produced before this card fixed
    them: a code, its version, and nothing saying whether a person chose it.
    """
    code, version = _AXIS_CODES[axis]
    with (
        pytest.raises(IntegrityError, match=f"ck_speaker_profile_{axis}_provenance"),
        engine.begin() as conn,
    ):
        _insert(
            conn,
            tenant_id,
            axis=axis,
            code=code,
            taxonomy_version=version,
            source=None,
            actor_id=None,
            classified_at=None,
        )


@pytest.mark.parametrize("axis", _AXES)
def test_a_classified_axis_must_state_when_it_was_classified(
    engine: Engine, tenant_id, axis: str
) -> None:
    """ "A person reviewed this" is not auditable without a *when*.

    Separated from the source case above rather than folded into it: the two
    conjuncts are independent, and a constraint that lost only the timestamp
    half would still refuse the source-less row and pass a combined test.
    """
    code, version = _AXIS_CODES[axis]
    with (
        pytest.raises(IntegrityError, match=f"ck_speaker_profile_{axis}_provenance"),
        engine.begin() as conn,
    ):
        _insert(
            conn,
            tenant_id,
            axis=axis,
            code=code,
            taxonomy_version=version,
            source=CLASSIFICATION_SOURCE_INFERRED,
            actor_id=None,
            classified_at=None,
        )


@pytest.mark.parametrize("axis", _AXES)
def test_an_unclassified_axis_cannot_carry_provenance(engine: Engine, tenant_id, axis: str) -> None:
    """Provenance about nothing is worse than no provenance.

    This is the row an edit that cleared a code while leaving the three columns
    alone would write, and the reason
    ``smartmatch_persistence.cba_contacts._human_provenance`` clears them
    together rather than omitting them from the statement.
    """
    with (
        pytest.raises(IntegrityError, match=f"ck_speaker_profile_{axis}_provenance"),
        engine.begin() as conn,
    ):
        _insert(
            conn,
            tenant_id,
            axis=axis,
            code=None,
            taxonomy_version=None,
            source=CLASSIFICATION_SOURCE_HUMAN,
            actor_id=None,
            classified_at=_CLASSIFIED_AT,
        )


@pytest.mark.parametrize("axis", _AXES)
@pytest.mark.parametrize("source", ["Inferred", "HUMAN", "corrected", "csv-import-v3", ""])
def test_a_classification_source_outside_the_vocabulary_is_refused(
    engine: Engine, tenant_id, axis: str, source: str
) -> None:
    """The vocabulary is closed, and case-sensitive.

    ``'corrected'`` and ``'csv-import-v3'`` are here by name because they are the
    two the migration argues against in prose: the first tries to encode history
    in an enum, the second turns a review gate into a provenance log. A rule
    stated only in a docstring is not a rule.
    """
    code, version = _AXIS_CODES[axis]
    with (
        pytest.raises(IntegrityError, match=f"ck_speaker_profile_{axis}_provenance"),
        engine.begin() as conn,
    ):
        _insert(
            conn,
            tenant_id,
            axis=axis,
            code=code,
            taxonomy_version=version,
            source=source,
            actor_id=None,
            classified_at=_CLASSIFIED_AT,
        )
