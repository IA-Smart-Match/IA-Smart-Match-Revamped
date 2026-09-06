"""What ``SpeakerContactRepository`` writes, against real PostgreSQL.

``tests/contract/test_cba_contacts_api.py`` owns the HTTP surface — who may
call, what status comes back, what the response body says. This module owns the
rows underneath it: that a create really does write all three tables, that a
correction replaces a current value and bumps ``updated_at`` **without** leaving
a history behind, and that a repeat create is refused rather than resolved.

The distinction matters most for the correction. OQ-CBA-008's interim ruling is
current value only, and "no history was written" is not something an HTTP
response can demonstrate — a route that quietly inserted an audit row would
return exactly the same ``200``. So that assertion has to be made here, against
the tables, and it is made by reading the rows back rather than by trusting the
repository's docstring.

Requires a live database, and is skipped when none is reachable.
"""

from __future__ import annotations

import uuid

import pytest

pytest.importorskip("sqlalchemy")

from conftest import ensure_owning_unit, unique_subject
from smartmatch_domain.cba_contacts import (
    CONTACT_BOARD_ROLE,
    ClassificationCorrection,
    SpeakerContactDraft,
    speaker_contact_subject_id,
)
from smartmatch_domain.cba_role_categories import CBA_ROLE_TAXONOMY_VERSION
from smartmatch_domain.naics_sectors import NAICS_TAXONOMY_VERSION
from smartmatch_persistence.cba_contacts import (
    SpeakerContactAlreadyExists,
    SpeakerContactRepository,
)
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

FINANCE_SECTOR = "52"
PROFESSIONAL_SERVICES_SECTOR = "54"
FINANCE_ROLE = "finance"
MARKETING_ROLE = "marketing"

NAME = "Dana Reyes"
COMPANY = "Reyes Analytics"
TITLE = "Principal Analyst"


@pytest.fixture(autouse=True)
def _clean_contacts(engine: Engine, tenant_id):
    """Delete this file's rows before ``tenant_id`` tears its own down.

    ``speaker_profile`` holds ``ON DELETE RESTRICT`` references to both
    ``user_account`` and ``org_unit``, and every create here writes a
    ``user_account`` of its own, so both child tables must be cleared — the
    ordering hazard ``test_cba_classification_schema.py``'s cleanup fixture
    exists for.
    """
    yield
    with engine.begin() as conn:
        for table in ("speaker_profile", "professional_unit_relationship"):
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": tenant_id})


@pytest.fixture
def repository() -> SpeakerContactRepository:
    return SpeakerContactRepository()


@pytest.fixture
def unit_id(engine: Engine, tenant_id) -> uuid.UUID:
    """The unit every contact in this module is filed under."""
    with engine.begin() as conn:
        return ensure_owning_unit(conn, tenant_id)


@pytest.fixture
def actor_id(engine: Engine, tenant_id) -> uuid.UUID:
    """The Speaker Connector every write in this module is performed by.

    A real ``user_account`` rather than a bare UUID, because
    ``fk_speaker_profile_industry_classified_by`` is a composite key into
    ``(tenant_id, id)``: an invented id would fail the foreign key, and every
    test here would then report a broken fixture instead of the behaviour it is
    about.
    """
    account_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO user_account (id, tenant_id, external_subject, email) "
                "VALUES (:id, :tid, :sub, :email)"
            ),
            {
                "id": account_id,
                "tid": tenant_id,
                "sub": unique_subject(f"connector-{account_id.hex[:8]}"),
                "email": f"connector-{account_id.hex[:8]}@example.edu",
            },
        )
    return account_id


def _draft(**overrides: object) -> SpeakerContactDraft:
    """A fully classified contact. Overrides replace whole fields."""
    values: dict[str, object] = {
        "full_name": NAME,
        "company": COMPANY,
        "title": TITLE,
        "topic_text": "Financial modelling for early-career analysts.",
        "location_city": "Pomona",
        "primary_industry_code": FINANCE_SECTOR,
        "primary_role_code": FINANCE_ROLE,
    }
    values.update(overrides)
    return SpeakerContactDraft.create(**values)  # type: ignore[arg-type]


def _create(
    engine: Engine,
    repository: SpeakerContactRepository,
    tenant_id,
    unit_id,
    actor_id,
    **overrides,
):
    """Create one contact in its own transaction and return the stored row."""
    with Session(engine) as session, session.begin():
        return repository.create(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            draft=_draft(**overrides),
            actor_id=actor_id,
        )


# ---------------------------------------------------------------------------
# What a create writes
# ---------------------------------------------------------------------------


def test_a_create_writes_all_three_tables(
    engine: Engine, tenant_id, unit_id, actor_id, repository: SpeakerContactRepository
) -> None:
    """A contact is not one row, and the account is what the profile's key points at.

    Asserted table by table rather than as "the create returned something". A
    repository that wrote only ``speaker_profile`` could not have — the foreign
    key would have refused it — but one that wrote the account and skipped the
    unit link would look identical from the API, and the contact would then be
    invisible to every query that starts from a unit's professionals.
    """
    row = _create(engine, repository, tenant_id, unit_id, actor_id)

    with engine.connect() as conn:
        accounts = conn.execute(
            text("SELECT count(*) FROM user_account WHERE tenant_id = :t AND id = :p"),
            {"t": tenant_id, "p": row.professional_id},
        ).scalar_one()
        board_role = conn.execute(
            text(
                "SELECT board_role FROM professional_unit_relationship "
                "WHERE tenant_id = :t AND professional_id = :p AND unit_id = :u"
            ),
            {"t": tenant_id, "p": row.professional_id, "u": unit_id},
        ).scalar_one()
        profiles = conn.execute(
            text(
                "SELECT count(*) FROM speaker_profile WHERE tenant_id = :t AND professional_id = :p"
            ),
            {"t": tenant_id, "p": row.professional_id},
        ).scalar_one()

    assert accounts == 1
    assert profiles == 1
    # OQ-CBA-016: `board_role` is NOT NULL free text with no vocabulary, so a
    # create is forced to write something. Asserted against the domain constant
    # rather than a literal, so the register row and the code cannot drift.
    assert board_role == CONTACT_BOARD_ROLE


def test_the_identity_is_derived_rather_than_generated(
    engine: Engine, tenant_id, unit_id, actor_id, repository: SpeakerContactRepository
) -> None:
    """The stored key is exactly what the domain derives from the folded name.

    That equality is what makes a repeat create a conflict rather than a second
    row, and pinning it here means the two halves cannot drift apart silently.
    """
    row = _create(engine, repository, tenant_id, unit_id, actor_id)

    assert row.professional_id == speaker_contact_subject_id(
        tenant_id=tenant_id, unit_id=unit_id, full_name=NAME
    )


def test_the_stored_account_carries_no_real_address(
    engine: Engine, tenant_id, unit_id, actor_id, repository: SpeakerContactRepository
) -> None:
    """``user_account.email`` is NOT NULL, so a create must write something.

    What it writes is undeliverable by construction — the RFC 2606 ``.invalid``
    TLD — because OQ-CBA-011 withholds the address a Connector types, and those
    two facts are only compatible if nothing can be sent to what is stored.
    """
    row = _create(engine, repository, tenant_id, unit_id, actor_id)

    with engine.connect() as conn:
        email, subject = conn.execute(
            text(
                "SELECT email, external_subject FROM user_account WHERE tenant_id = :t AND id = :p"
            ),
            {"t": tenant_id, "p": row.professional_id},
        ).one()

    assert email.endswith("@contact.invalid")
    # Not `synthetic-professional:` — a person a Connector met is not fabricated
    # data, and the tooling that filters on that prefix would be wrong here.
    assert subject.startswith("contact-professional:")


def test_a_create_writes_no_contact_channel(
    engine: Engine, tenant_id, unit_id, actor_id, repository: SpeakerContactRepository
) -> None:
    """The structural half of OQ-CBA-011's posture.

    Counted across the whole tenant rather than searched for by address, so a row
    written under any address at all fails this.
    """
    _create(engine, repository, tenant_id, unit_id, actor_id)

    with engine.connect() as conn:
        channels = conn.execute(
            text("SELECT count(*) FROM contact_channel WHERE tenant_id = :t"),
            {"t": tenant_id},
        ).scalar_one()

    assert channels == 0


def test_a_repeat_create_is_refused_and_names_the_stored_contact(
    engine: Engine, tenant_id, unit_id, actor_id, repository: SpeakerContactRepository
) -> None:
    """OQ-CBA-017. The exception carries the row, so a route can say who is there.

    The *folded* name is what collides, so the second create uses different
    casing and spacing — proving the identity turns on the fold rather than on
    the literal, which is what makes a re-typed name resolve to one person.
    """
    first = _create(engine, repository, tenant_id, unit_id, actor_id)

    with (
        Session(engine) as session,
        session.begin(),
        pytest.raises(SpeakerContactAlreadyExists) as caught,
    ):
        repository.create(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            draft=_draft(full_name="  DANA REYES  ", company="A Different Employer"),
            actor_id=actor_id,
        )

    assert caught.value.existing.professional_id == first.professional_id
    assert caught.value.existing.company == COMPANY, (
        "the refused create must not have overwritten the stored contact"
    )


# ---------------------------------------------------------------------------
# What a correction does, and what it does not
# ---------------------------------------------------------------------------


def test_a_correction_replaces_the_named_axis_and_its_version(
    engine: Engine, tenant_id, unit_id, actor_id, repository: SpeakerContactRepository
) -> None:
    """§§7-8's correction. The code and its version travel together."""
    created = _create(engine, repository, tenant_id, unit_id, actor_id)

    with Session(engine) as session, session.begin():
        corrected = repository.correct_classification(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            professional_id=created.professional_id,
            correction=ClassificationCorrection.create(
                primary_industry_code=PROFESSIONAL_SERVICES_SECTOR
            ),
            actor_id=actor_id,
        )

    assert corrected is not None
    assert corrected.primary_industry_code == PROFESSIONAL_SERVICES_SECTOR
    assert corrected.industry_taxonomy_version == NAICS_TAXONOMY_VERSION


def test_an_unnamed_axis_is_left_alone_rather_than_cleared(
    engine: Engine, tenant_id, unit_id, actor_id, repository: SpeakerContactRepository
) -> None:
    """The rule that makes "fix the industry, leave the role" safe.

    If ``None`` meant "clear", the commonest correction would silently
    un-classify half of the speaker's record.
    """
    created = _create(engine, repository, tenant_id, unit_id, actor_id)

    with Session(engine) as session, session.begin():
        corrected = repository.correct_classification(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            professional_id=created.professional_id,
            correction=ClassificationCorrection.create(
                primary_industry_code=PROFESSIONAL_SERVICES_SECTOR
            ),
            actor_id=actor_id,
        )

    assert corrected is not None
    assert corrected.primary_role_code == FINANCE_ROLE
    assert corrected.role_taxonomy_version == CBA_ROLE_TAXONOMY_VERSION


def test_a_create_records_the_connector_as_the_classifier(
    engine: Engine, tenant_id, unit_id, actor_id, repository: SpeakerContactRepository
) -> None:
    """A code typed into §13's form is a person's judgment, and the row says whose.

    Read back from ``speaker_profile`` rather than from the returned row,
    because the returned row is this module's own read model: a writer that
    populated the dataclass and not the table would satisfy an assertion made
    against the return value, and ``get_session`` rolls back unconditionally, so
    a write path missing its columns can still hand back something that looks
    right.

    This is also the test that would have caught the whole defect this fixed:
    before it, ``create`` wrote a code and no provenance, and every write of a
    classified contact was refused by ``ck_speaker_profile_industry_provenance``.
    """
    created = _create(engine, repository, tenant_id, unit_id, actor_id)

    with engine.connect() as conn:
        stored = conn.execute(
            text(
                "SELECT industry_classification_source, industry_classified_by_user_id, "
                "industry_classified_at, role_classification_source, "
                "role_classified_by_user_id, role_classified_at "
                "FROM speaker_profile WHERE tenant_id = :t AND professional_id = :p"
            ),
            {"t": tenant_id, "p": created.professional_id},
        ).one()

    # Both axes, because the draft classifies both and a helper that stamped
    # only the first would leave the second unattributed.
    assert stored.industry_classification_source == "human"
    assert stored.role_classification_source == "human"
    assert stored.industry_classified_by_user_id == actor_id
    assert stored.role_classified_by_user_id == actor_id
    # Not asserted against a particular instant — `now()` is the database's
    # clock. That it is present at all is the claim: `human` with no timestamp
    # is a review nobody can date, and the CHECK refuses it.
    assert stored.industry_classified_at is not None
    assert stored.role_classified_at is not None


def test_an_unclassified_create_attributes_nothing_to_anybody(
    engine: Engine, tenant_id, unit_id, actor_id, repository: SpeakerContactRepository
) -> None:
    """§19 imports a contact first and classifies it after.

    A Connector who adds somebody without saying which sector they belong to has
    made no classification judgment, so no actor is recorded — stamping them
    anyway would put a name against a decision nobody took, which is the same
    fabrication ``0028`` refuses for an inferred value.
    """
    created = _create(
        engine,
        repository,
        tenant_id,
        unit_id,
        actor_id,
        primary_industry_code=None,
        primary_role_code=None,
    )

    with engine.connect() as conn:
        stored = conn.execute(
            text(
                "SELECT industry_classification_source, industry_classified_by_user_id, "
                "role_classification_source, role_classified_by_user_id "
                "FROM speaker_profile WHERE tenant_id = :t AND professional_id = :p"
            ),
            {"t": tenant_id, "p": created.professional_id},
        ).one()

    assert stored.industry_classification_source is None
    assert stored.industry_classified_by_user_id is None
    assert stored.role_classification_source is None
    assert stored.role_classified_by_user_id is None


def test_a_correction_wins_over_an_inferred_proposal_and_names_its_author(
    engine: Engine, tenant_id, unit_id, actor_id, repository: SpeakerContactRepository
) -> None:
    """§19's step five, and the axis the Connector did not touch stays unreviewed.

    The contact is put into the state an import leaves behind — both axes
    ``inferred``, no actor — by writing it directly, because that is the state
    the classifier produces and no route can create it. The correction then
    names one axis.

    Two things must hold, and the second is the one worth guarding: the
    corrected axis flips to ``human`` with this Connector against it, **and the
    other axis is left inferred**. A writer that stamped both would silently
    mark a classification as reviewed that nobody read, which is precisely the
    approval-by-side-effect the review gate exists to prevent.
    """
    created = _create(engine, repository, tenant_id, unit_id, actor_id)

    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE speaker_profile SET "
                "industry_classification_source = 'inferred', "
                "industry_classified_by_user_id = NULL, "
                "role_classification_source = 'inferred', "
                "role_classified_by_user_id = NULL "
                "WHERE tenant_id = :t AND professional_id = :p"
            ),
            {"t": tenant_id, "p": created.professional_id},
        )

    with Session(engine) as session, session.begin():
        repository.correct_classification(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            professional_id=created.professional_id,
            correction=ClassificationCorrection.create(
                primary_industry_code=PROFESSIONAL_SERVICES_SECTOR
            ),
            actor_id=actor_id,
        )

    with engine.connect() as conn:
        stored = conn.execute(
            text(
                "SELECT primary_industry_code, industry_classification_source, "
                "industry_classified_by_user_id, role_classification_source, "
                "role_classified_by_user_id "
                "FROM speaker_profile WHERE tenant_id = :t AND professional_id = :p"
            ),
            {"t": tenant_id, "p": created.professional_id},
        ).one()

    assert stored.primary_industry_code == PROFESSIONAL_SERVICES_SECTOR
    assert stored.industry_classification_source == "human"
    assert stored.industry_classified_by_user_id == actor_id
    assert stored.role_classification_source == "inferred"
    assert stored.role_classified_by_user_id is None


def test_a_correction_bumps_updated_at_without_redating_the_record(
    engine: Engine, tenant_id, unit_id, actor_id, repository: SpeakerContactRepository
) -> None:
    """The server default fills ``updated_at`` on INSERT only.

    Without the explicit bump, a corrected contact would go on claiming it was
    last touched when it was created — and that column is the one a reviewer
    would sort by to find recent corrections. ``created_at`` must not move with
    it, or the record would look newly added rather than newly edited.
    """
    created = _create(engine, repository, tenant_id, unit_id, actor_id)

    with Session(engine) as session, session.begin():
        corrected = repository.correct_classification(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            professional_id=created.professional_id,
            correction=ClassificationCorrection.create(primary_role_code=MARKETING_ROLE),
            actor_id=actor_id,
        )

    assert corrected is not None
    assert corrected.updated_at > created.updated_at
    assert corrected.created_at == created.created_at


def test_a_correction_leaves_no_history_behind(
    engine: Engine, tenant_id, unit_id, actor_id, repository: SpeakerContactRepository
) -> None:
    """OQ-CBA-008's interim ruling, asserted rather than only documented.

    Two corrections, and afterwards exactly one ``speaker_profile`` row holding
    only the latest value. This is the assertion an HTTP test cannot make: a
    route that quietly inserted an audit row would return the same ``200``, and
    a history table nobody ratified is precisely what ``0012``'s refusal to
    invent a ``board_role`` vocabulary is the local precedent against.

    Deliberately *not* written as "no table named ``*_history`` exists", which
    would pass for a history stored under any other name. Reading the rows back
    is what shows the write replaced rather than appended.
    """
    created = _create(engine, repository, tenant_id, unit_id, actor_id)

    for code in (PROFESSIONAL_SERVICES_SECTOR, FINANCE_SECTOR):
        with Session(engine) as session, session.begin():
            repository.correct_classification(
                session,
                tenant_id=tenant_id,
                owning_unit_id=unit_id,
                professional_id=created.professional_id,
                correction=ClassificationCorrection.create(primary_industry_code=code),
                actor_id=actor_id,
            )

    with engine.connect() as conn:
        stored = (
            conn.execute(
                text(
                    "SELECT primary_industry_code FROM speaker_profile "
                    "WHERE tenant_id = :t AND professional_id = :p"
                ),
                {"t": tenant_id, "p": created.professional_id},
            )
            .scalars()
            .all()
        )

    assert stored == [FINANCE_SECTOR], (
        "two corrections must leave one row holding the latest value, not three rows"
    )


def test_a_correction_for_another_unit_touches_nothing(
    engine: Engine, tenant_id, unit_id, actor_id, repository: SpeakerContactRepository
) -> None:
    """Writes are scoped by ``(tenant_id, owning_unit_id)``, not by contact id alone.

    Returns ``None`` rather than raising, so the route can answer 404 identically
    for "no such contact" and "not yours" — a distinction that would otherwise
    confirm an id names a real person.
    """
    created = _create(engine, repository, tenant_id, unit_id, actor_id)

    with Session(engine) as session, session.begin():
        missed = repository.correct_classification(
            session,
            tenant_id=tenant_id,
            owning_unit_id=uuid.uuid4(),
            professional_id=created.professional_id,
            correction=ClassificationCorrection.create(primary_role_code=MARKETING_ROLE),
            actor_id=actor_id,
        )

    assert missed is None

    with engine.connect() as conn:
        stored = conn.execute(
            text(
                "SELECT primary_role_code FROM speaker_profile "
                "WHERE tenant_id = :t AND professional_id = :p"
            ),
            {"t": tenant_id, "p": created.professional_id},
        ).scalar_one()

    assert stored == FINANCE_ROLE


# ---------------------------------------------------------------------------
# What an edit does
# ---------------------------------------------------------------------------


def test_an_edit_clears_an_omitted_optional_field(
    engine: Engine, tenant_id, unit_id, actor_id, repository: SpeakerContactRepository
) -> None:
    """The draft states the record in full, absences included.

    Merging instead would make removing a value the one edit a Connector could
    never perform.
    """
    created = _create(engine, repository, tenant_id, unit_id, actor_id)

    with Session(engine) as session, session.begin():
        edited = repository.update(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            professional_id=created.professional_id,
            draft=_draft(company=None),
            actor_id=actor_id,
        )

    assert edited is not None
    assert edited.company is None
    assert edited.title == TITLE, "an edit must not clear what it still states"


def test_renaming_a_contact_does_not_move_its_identity(
    engine: Engine, tenant_id, unit_id, actor_id, repository: SpeakerContactRepository
) -> None:
    """The caveat the repository docstring states, pinned so it cannot change silently.

    ``professional_id`` was derived at create time and is now a stored key that
    ``user_account`` and ``professional_unit_relationship`` rows reference. An
    edit changes the label, not the key — re-deriving would rewrite a primary
    key other rows point at, which is a migration rather than a side effect of
    an edit.

    The second assertion is the consequence, stated so a reader meets it here
    rather than in production: the derived id for the corrected name is a
    *different* id, so a later create under that name would succeed and produce
    a second contact for one person. That is the shape of OQ-CBA-017 from the
    other direction.
    """
    created = _create(engine, repository, tenant_id, unit_id, actor_id)
    corrected_name = "Dana Reyes-Okonkwo"

    with Session(engine) as session, session.begin():
        edited = repository.update(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            professional_id=created.professional_id,
            draft=_draft(full_name=corrected_name),
            actor_id=actor_id,
        )

    assert edited is not None
    assert edited.full_name == corrected_name
    assert edited.professional_id == created.professional_id
    assert created.professional_id != speaker_contact_subject_id(
        tenant_id=tenant_id, unit_id=unit_id, full_name=corrected_name
    )


def test_the_roster_lists_only_this_units_contacts(
    engine: Engine, tenant_id, unit_id, actor_id, repository: SpeakerContactRepository
) -> None:
    """Ordered by name, and scoped by the owning unit."""
    _create(engine, repository, tenant_id, unit_id, actor_id)
    _create(engine, repository, tenant_id, unit_id, actor_id, full_name="Aria Okonkwo")

    with Session(engine) as session:
        rows = repository.list_for_unit(
            session, tenant_id=tenant_id, owning_unit_id=unit_id, limit=10
        )
        elsewhere = repository.list_for_unit(
            session, tenant_id=tenant_id, owning_unit_id=uuid.uuid4(), limit=10
        )

    assert [row.full_name for row in rows] == ["Aria Okonkwo", NAME]
    assert elsewhere == ()
