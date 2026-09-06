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
from smartmatch_api.config import get_settings
from smartmatch_api.pipeline_provisioning import (
    PROFESSIONAL_NAME_KEY,
    PROFESSIONALS_DATASET,
    provision_on_accept,
)
from smartmatch_domain.cba_classification import (
    CLASSIFICATION_SOURCE_HUMAN,
    CLASSIFICATION_SOURCE_INFERRED,
    CLASSIFICATION_SOURCES,
)
from smartmatch_domain.cba_contacts import ClassificationCorrection
from smartmatch_domain.cba_role_categories import CBA_ROLE_TAXONOMY_VERSION
from smartmatch_domain.naics_sectors import NAICS_TAXONOMY_VERSION
from smartmatch_persistence.cba_contacts import SpeakerContactRepository
from smartmatch_providers.cba_classification import build_contact_classifier
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

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

    ``professional_unit_relationship`` joins it because the accept-path tests
    below provision one per imported contact; child before parent, so the
    profile goes first.
    """
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM speaker_profile WHERE tenant_id = :tid"), {"tid": tenant_id})
        conn.execute(
            text("DELETE FROM professional_unit_relationship WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        )


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


# ---------------------------------------------------------------------------
# The import path: what an accepted `professionals` row becomes.
#
# `provision_on_accept` is called directly rather than over HTTP, for
# `test_pipeline_provisioning.py`'s stated reason — the route's authorization is
# that file's subject, and this one is about what lands in the row. Every call
# commits, so the raw reads below can see it: under READ COMMITTED a second
# connection cannot see another session's uncommitted writes.
# ---------------------------------------------------------------------------


@pytest.fixture
def unit_id(engine: Engine, tenant_id) -> uuid.UUID:
    """The unit every imported contact in this module is filed under."""
    with engine.begin() as conn:
        return ensure_owning_unit(conn, tenant_id)


def _accept(
    session_factory: sessionmaker[Session],
    *,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    **row: object,
) -> uuid.UUID:
    """Accept one ``professionals`` review item and return the professional id.

    ``name`` is defaulted because no test here is about identity derivation —
    that is ``test_pipeline_provisioning.py``'s subject — and every test here
    would otherwise repeat it.
    """
    row_data: dict[str, object] = {PROFESSIONAL_NAME_KEY: "Dana Reyes", **row}
    with session_factory() as session:
        outcome = provision_on_accept(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            review_item_id=uuid.uuid4(),
            dataset=PROFESSIONALS_DATASET,
            row_data=row_data,
            accepted_at=_CLASSIFIED_AT,
        )
        session.commit()
    assert outcome.professional_subject_id is not None
    return outcome.professional_subject_id


def _profile(engine: Engine, tenant_id: uuid.UUID, professional_id: uuid.UUID):
    """The stored profile, read through a separate connection."""
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT full_name, company, title, topic_text, location_city, "
                "primary_industry_code, industry_classification_source, "
                "industry_classified_by_user_id, industry_classified_at, "
                "primary_role_code, role_classification_source, "
                "role_classified_by_user_id "
                "FROM speaker_profile WHERE tenant_id = :t AND professional_id = :p"
            ),
            {"t": tenant_id, "p": professional_id},
        ).one_or_none()


def test_an_accepted_import_row_becomes_a_speaker_record(
    engine: Engine, tenant_id, unit_id, session_factory
) -> None:
    """Customer §19's second step: an accepted row is a speaker, not just an account.

    Before this card the accept path stopped at ``user_account`` and the unit
    link, so a coordinator's import produced a professional nobody could
    classify, match, or read as a §13 contact. The stated fields are asserted
    rather than taken on trust: a classification stored beside the wrong
    person's company is worse than no classification.
    """
    professional_id = _accept(
        session_factory,
        tenant_id=tenant_id,
        unit_id=unit_id,
        company="Reyes Analytics",
        title="Principal Analyst",
        expertise_tags="Financial modelling for early-career analysts.",
        location_city="Pomona",
    )

    stored = _profile(engine, tenant_id, professional_id)

    assert stored is not None
    assert stored.full_name == "Dana Reyes"
    assert stored.company == "Reyes Analytics"
    assert stored.title == "Principal Analyst"
    # §18's "Topic/interests/expertise text" is `expertise_tags` in the import
    # contract and `topic_text` in the schema. This is that mapping, exercised.
    assert stored.topic_text == "Financial modelling for early-career analysts."
    assert stored.location_city == "Pomona"


def test_the_classifier_proposal_is_stored_as_inferred_and_names_nobody(
    engine: Engine, tenant_id, unit_id, session_factory
) -> None:
    """A proposal is inferred provenance, and the actor column is what proves it.

    ``"Finance"`` as a job title resolves through the released role taxonomy's
    own ``resolve_role_category``, so this row exercises the classifier rather
    than the stated-code path. What it must **not** produce is an actor: nobody
    reviewed this, and the person who accepted the import row reviewed the row.
    """
    professional_id = _accept(
        session_factory,
        tenant_id=tenant_id,
        unit_id=unit_id,
        title="Finance",
    )

    stored = _profile(engine, tenant_id, professional_id)

    assert stored is not None
    assert stored.primary_role_code == "finance"
    assert stored.role_classification_source == CLASSIFICATION_SOURCE_INFERRED
    assert stored.role_classified_by_user_id is None


def test_an_unrecognized_company_is_left_unclassified_rather_than_guessed(
    engine: Engine, tenant_id, unit_id, session_factory
) -> None:
    """Ambiguous or unknown is reviewable, never a guess.

    ``"Reyes Analytics"`` is neither a sector name nor a sector code, so the
    industry axis resolves to nothing. The second assertion is the one that
    matters: the company text is still on the row, which is why no quarantine
    column was added (OQ-CBA-010). A reviewer decides from what the sheet said,
    and the stored classification does not pretend to an answer.
    """
    professional_id = _accept(
        session_factory,
        tenant_id=tenant_id,
        unit_id=unit_id,
        company="Reyes Analytics",
    )

    stored = _profile(engine, tenant_id, professional_id)

    assert stored is not None
    assert stored.primary_industry_code is None
    assert stored.industry_classification_source is None
    assert stored.company == "Reyes Analytics"


def test_a_stated_taxonomy_code_is_taken_as_a_proposal_rather_than_as_a_fact(
    engine: Engine, tenant_id, unit_id, session_factory
) -> None:
    """The export's own code is used, and is still only a proposal.

    ``docs/pilot-data/columns.yaml`` declares both code columns and says the
    import contract does not validate them, handing that to this card.
    Honouring a valid one is better evidence than a guess from the company
    name — but it arrived on a spreadsheet, so it is ``inferred`` and still
    awaits §19's review. Storing it as ``human`` would let a coordinator's
    export put a speaker straight into matching with nobody having looked.
    """
    professional_id = _accept(
        session_factory,
        tenant_id=tenant_id,
        unit_id=unit_id,
        primary_industry_code="52",
        primary_role_code="finance",
    )

    stored = _profile(engine, tenant_id, professional_id)

    assert stored is not None
    assert stored.primary_industry_code == "52"
    assert stored.primary_role_code == "finance"
    assert stored.industry_classification_source == CLASSIFICATION_SOURCE_INFERRED
    assert stored.role_classification_source == CLASSIFICATION_SOURCE_INFERRED
    assert stored.industry_classified_by_user_id is None
    assert stored.role_classified_by_user_id is None


@pytest.mark.parametrize("stated", ["banking", "Finance and Insurance!", "521", "  ", "52.0"])
def test_a_stated_code_outside_the_closed_taxonomy_is_not_stored(
    engine: Engine, tenant_id, unit_id, session_factory, stated: str
) -> None:
    """Never invent a code, and never store one merely because somebody typed it.

    An unrecognized value is a review item's problem rather than the batch's —
    the import contract says exactly that — so the accept succeeds, the axis
    stays unclassified, and the raw value is still in ``review_item.row_data``
    for anybody who wants to see what was not taken.
    """
    professional_id = _accept(
        session_factory,
        tenant_id=tenant_id,
        unit_id=unit_id,
        primary_industry_code=stated,
    )

    stored = _profile(engine, tenant_id, professional_id)

    assert stored is not None
    assert stored.primary_industry_code is None
    assert stored.industry_classification_source is None


def test_an_imported_contact_does_not_enter_matching_until_a_connector_reviews_it(
    engine: Engine, tenant_id, unit_id, session_factory
) -> None:
    """§19's last two steps, in order, asserted end to end.

    The contact is fully proposed on both axes — the state most likely to be
    mistaken for done, because every code column is populated — and is still not
    eligible. Then a Connector corrects both axes, and it is.

    Asserted through ``list_match_eligible``, which is the query a matching pool
    must be built from: a test checking only the row's own property would pass
    for a gate that existed in Python and not in SQL.
    """
    professional_id = _accept(
        session_factory,
        tenant_id=tenant_id,
        unit_id=unit_id,
        primary_industry_code="52",
        primary_role_code="finance",
    )
    repository = SpeakerContactRepository()

    with session_factory() as session:
        before = repository.list_match_eligible(
            session, tenant_id=tenant_id, owning_unit_id=unit_id, limit=10
        )
        proposed = repository.get(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            professional_id=professional_id,
        )

    assert before == ()
    assert proposed is not None
    assert proposed.match_eligible is False
    # The reason names the axis and the situation, so a surface can say which of
    # four states a Connector is looking at rather than greying out a row.
    assert proposed.match_ineligibility_reason == "industry_classification_awaiting_review"

    with session_factory() as session:
        actor_id = _make_account(session.connection(), tenant_id)
        repository.correct_classification(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            professional_id=professional_id,
            correction=ClassificationCorrection.create(
                primary_industry_code="52", primary_role_code="finance"
            ),
            actor_id=actor_id,
        )
        session.commit()

    with session_factory() as session:
        after = repository.list_match_eligible(
            session, tenant_id=tenant_id, owning_unit_id=unit_id, limit=10
        )

    assert [row.professional_id for row in after] == [professional_id]
    assert after[0].match_eligible is True
    assert after[0].match_ineligibility_reason is None


def test_a_partly_reviewed_contact_still_does_not_enter_matching(
    engine: Engine, tenant_id, unit_id, session_factory
) -> None:
    """One axis reviewed is not §19's gate satisfied.

    The failure this guards is the plausible one: a Connector fixes the industry
    they noticed was wrong, the role is still a proposal nobody read, and a gate
    written as "has anybody touched this record" would let the contact through.
    """
    professional_id = _accept(
        session_factory,
        tenant_id=tenant_id,
        unit_id=unit_id,
        primary_industry_code="52",
        primary_role_code="finance",
    )
    repository = SpeakerContactRepository()

    with session_factory() as session:
        actor_id = _make_account(session.connection(), tenant_id)
        repository.correct_classification(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            professional_id=professional_id,
            correction=ClassificationCorrection.create(primary_industry_code="54"),
            actor_id=actor_id,
        )
        session.commit()

    with session_factory() as session:
        eligible = repository.list_match_eligible(
            session, tenant_id=tenant_id, owning_unit_id=unit_id, limit=10
        )
        row = repository.get(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            professional_id=professional_id,
        )

    assert eligible == ()
    assert row is not None
    assert row.match_ineligibility_reason == "role_classification_awaiting_review"


def test_an_unclassifiable_contact_is_ineligible_rather_than_eligible_by_default(
    engine: Engine, tenant_id, unit_id, session_factory
) -> None:
    """Fail closed: no proposal is not the same as nothing to object to.

    A contact the classifier could read nothing from has both axes NULL, and
    NULL must not read as consent to match. The reason distinguishes it from the
    awaiting-review case, because the two call for different acts — find out
    where this person works, versus check a proposal somebody made.
    """
    professional_id = _accept(session_factory, tenant_id=tenant_id, unit_id=unit_id)
    repository = SpeakerContactRepository()

    with session_factory() as session:
        eligible = repository.list_match_eligible(
            session, tenant_id=tenant_id, owning_unit_id=unit_id, limit=10
        )
        row = repository.get(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            professional_id=professional_id,
        )

    assert eligible == ()
    assert row is not None
    assert row.match_ineligibility_reason == "industry_classification_missing"


def test_re_accepting_the_same_person_does_not_undo_a_review(
    engine: Engine, tenant_id, unit_id, session_factory
) -> None:
    """A second import must not put a reviewed speaker back behind the gate.

    This is the hazard ``create_from_import``'s read-first guard exists for, and
    it is not hypothetical: re-importing a corrected roster is the ordinary way
    a coordinator updates one. Overwriting would silently discard a Connector's
    judgment *and* make the contact unmatchable again, and both would look like
    a successful import.
    """
    professional_id = _accept(
        session_factory,
        tenant_id=tenant_id,
        unit_id=unit_id,
        primary_industry_code="52",
        primary_role_code="finance",
    )
    repository = SpeakerContactRepository()

    with session_factory() as session:
        actor_id = _make_account(session.connection(), tenant_id)
        repository.correct_classification(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            professional_id=professional_id,
            correction=ClassificationCorrection.create(
                primary_industry_code="54", primary_role_code="marketing"
            ),
            actor_id=actor_id,
        )
        session.commit()

    _accept(
        session_factory,
        tenant_id=tenant_id,
        unit_id=unit_id,
        primary_industry_code="52",
        primary_role_code="finance",
    )

    stored = _profile(engine, tenant_id, professional_id)

    assert stored is not None
    assert stored.primary_industry_code == "54"
    assert stored.primary_role_code == "marketing"
    assert stored.industry_classification_source == CLASSIFICATION_SOURCE_HUMAN
    assert stored.industry_classified_by_user_id == actor_id


def test_the_import_path_writes_no_contact_channel(
    engine: Engine, tenant_id, unit_id, session_factory
) -> None:
    """Contact email does not imply consent, and this path does not touch either.

    ``contact_email`` is withheld at the import gate (CBA Gate C, OQ-CBA-011)
    and never reaches ``review_item.row_data`` — so it is passed here anyway,
    which is the stronger test: even handed the address, this path stores no
    channel and records no consent. Track 19 owns that lifecycle and closed the
    invite-to-consent loophole; nothing here reopens it.
    """
    _accept(
        session_factory,
        tenant_id=tenant_id,
        unit_id=unit_id,
        company="Reyes Analytics",
        contact_email="dana@example.com",
    )

    with engine.connect() as conn:
        channels = conn.execute(
            text("SELECT count(*) FROM contact_channel WHERE tenant_id = :t"),
            {"t": tenant_id},
        ).scalar_one()

    assert channels == 0


def test_the_wired_classifier_is_deterministic_and_consults_no_model(
    engine: Engine, tenant_id, unit_id, session_factory
) -> None:
    """OQ-CBA-039 stays deferred, and the accept path is not what opens it.

    ``is_model`` is asserted rather than assumed, for the discipline the
    protocol states: a misleading name becomes a permanent lie in the data, and
    this is the flag a later reader would trust when asking whether a stored
    ``inferred`` value came from a model.

    Determinism is asserted the only way it can be — the same evidence twice,
    against two different people, producing the same code.
    """
    settings = get_settings()
    classifier = build_contact_classifier(
        settings.edition, use_fixture=settings.use_fixture_providers
    )
    assert classifier.is_model is False

    first = _accept(session_factory, tenant_id=tenant_id, unit_id=unit_id, title="Finance")
    second = _accept(
        session_factory,
        tenant_id=tenant_id,
        unit_id=unit_id,
        name="Aria Okonkwo",
        title="Finance",
    )

    first_stored = _profile(engine, tenant_id, first)
    second_stored = _profile(engine, tenant_id, second)

    assert first_stored is not None
    assert second_stored is not None
    assert first_stored.primary_role_code == "finance"
    assert second_stored.primary_role_code == "finance"
