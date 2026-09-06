"""Opaque speaker identity: the rename fork is closed and same names are two people.

OQ-CBA-017, decided 2026-09-05 as *identity becomes opaque*. Migration ``0030``
re-keys the rows; this module owns the behaviour that decision buys, against the
tables rather than against an HTTP response —
``tests/contract/test_cba_contact_duplicate_hint.py`` owns the API surface.

What was wrong, in one paragraph
----------------------------------
``professional_id`` used to be ``uuid5(ns, "tenant:unit:folded_name")``. An edit
that changed a name did **not** move that key, so after ``"Dana Ryes"`` was
corrected to ``"Dana Reyes"`` the stored row's id no longer corresponded to the
name it carried. The duplicate guard of the day — a ``409`` raised when the
derived id was already taken — then silently did not fire for a create of
``"Dana Reyes"``, because that name derived a *different* id. One person, two
records, no warning anywhere.
:func:`test_the_rename_fork_no_longer_hides_a_second_record` is that exact
sequence, and it asserts the guard fires.

Why "one row" is not what these tests assert
----------------------------------------------
The same decision removed the ``409``: two professionals in one department
genuinely can share a name, and refusing the second create made the commoner
honest case impossible in order to prevent the rarer accident. So a same-name
create **succeeds**, and what these tests pin is that it succeeds *visibly* —
two distinct identities, both stored intact, and the create that made the second
one told about the first. A test asserting a single row would be asserting the
behaviour this card deleted.

Requires a live database, and is skipped when none is reachable.
"""

from __future__ import annotations

import uuid

import pytest

pytest.importorskip("sqlalchemy")

from conftest import ensure_owning_unit, unique_subject
from smartmatch_domain.cba_contacts import SpeakerContactDraft
from smartmatch_persistence.cba_contacts import SpeakerContactRepository
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

#: The typo and its correction. Two names that fold differently, so a
#: name-derived key would have produced two different ids for them — which is
#: precisely the fork.
TYPO_NAME = "Dana Ryes"
NAME = "Dana Reyes"
COMPANY = "Reyes Analytics"
TITLE = "Principal Analyst"


@pytest.fixture(autouse=True)
def _clean_contacts(engine: Engine, tenant_id):
    """Clear this file's rows before ``tenant_id`` tears its own down.

    ``speaker_profile`` holds ``ON DELETE RESTRICT`` references to both
    ``user_account`` and ``org_unit``, and every create here writes an account of
    its own, so the two child tables go first — the ordering
    ``test_cba_contact_corrections.py``'s cleanup fixture exists for.
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
def other_unit_id(engine: Engine, tenant_id) -> uuid.UUID:
    """A second department in the same tenant, for the hint's scoping test."""
    unit = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                "VALUES (:id, :tid, :path, 'department', 'Second department')"
            ),
            {"id": unit, "tid": tenant_id, "path": f"unit_{unit.hex[:8]}"},
        )
    return unit


@pytest.fixture
def actor_id(engine: Engine, tenant_id) -> uuid.UUID:
    """The Speaker Connector every write here is performed by.

    A real ``user_account``, because ``fk_speaker_profile_industry_classified_by``
    is a composite key into ``(tenant_id, id)`` — an invented id would fail the
    foreign key and every test would report a broken fixture instead of the
    behaviour it is about.
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
                "sub": unique_subject(f"opaque-connector-{account_id.hex[:8]}"),
                "email": f"opaque-connector-{account_id.hex[:8]}@example.edu",
            },
        )
    return account_id


def _draft(**overrides: object) -> SpeakerContactDraft:
    """An unclassified contact. Overrides replace whole fields.

    Deliberately carries no classification codes: nothing in this file is about
    §§7-8, and an unclassified contact is a real §13 state.
    """
    values: dict[str, object] = {"full_name": NAME, "company": COMPANY, "title": TITLE}
    values.update(overrides)
    return SpeakerContactDraft.create(**values)  # type: ignore[arg-type]


def _create(engine: Engine, repository, tenant_id, unit_id, actor_id, **overrides):
    """Create one contact in its own transaction, returning the create result."""
    with Session(engine) as session, session.begin():
        return repository.create(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            draft=_draft(**overrides),
            actor_id=actor_id,
        )


def _rename(engine: Engine, repository, tenant_id, unit_id, actor_id, professional_id, to: str):
    """Edit one contact's name and nothing else."""
    with Session(engine) as session, session.begin():
        return repository.update(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            professional_id=professional_id,
            draft=_draft(full_name=to),
            actor_id=actor_id,
        )


# ---------------------------------------------------------------------------
# The identity itself
# ---------------------------------------------------------------------------


def test_two_creates_of_one_name_derive_two_different_identities(
    engine: Engine, tenant_id, unit_id, actor_id, repository: SpeakerContactRepository
) -> None:
    """The negative statement that defines opaque identity.

    Under the derived scheme these two calls produced the *same* id — that was
    the whole mechanism, and it is what made a second create impossible. If this
    assertion ever fails, some caller has reintroduced a derivation and every
    other test in this file is about a system that no longer exists.
    """
    first = _create(engine, repository, tenant_id, unit_id, actor_id)
    second = _create(engine, repository, tenant_id, unit_id, actor_id)

    assert first.contact.professional_id != second.contact.professional_id


def test_the_identity_does_not_change_when_the_name_does(
    engine: Engine, tenant_id, unit_id, actor_id, repository: SpeakerContactRepository
) -> None:
    """A rename edits a label, and the key is no longer a function of the label.

    This assertion was true before the decision too, but for the opposite
    reason: the key *was* derived from the name and simply was not re-derived,
    which is what made it wrong. Now it is true because there is nothing to
    re-derive. Pinned here so a later card cannot make renaming move an id that
    other rows reference.
    """
    created = _create(engine, repository, tenant_id, unit_id, actor_id, full_name=TYPO_NAME)

    edited = _rename(
        engine, repository, tenant_id, unit_id, actor_id, created.contact.professional_id, to=NAME
    )

    assert edited is not None
    assert edited.full_name == NAME
    assert edited.professional_id == created.contact.professional_id


def test_the_account_behind_a_contact_is_keyed_by_the_same_opaque_id(
    engine: Engine, tenant_id, unit_id, actor_id, repository: SpeakerContactRepository
) -> None:
    """``0024``'s composite foreign key still holds, with a generated id in it.

    The subject and the address are re-derived *from* the id — the discipline
    ``ensure_account``'s ``ON CONFLICT`` depends on — so an opaque id must show
    up in all three places or the account states two identities. Migration
    ``0030``'s re-key writes exactly this shape for rows that predate it, and
    this is the create path producing it natively.
    """
    created = _create(engine, repository, tenant_id, unit_id, actor_id)
    professional_id = created.contact.professional_id

    with engine.connect() as conn:
        subject, email = conn.execute(
            text(
                "SELECT external_subject, email FROM user_account WHERE tenant_id = :t AND id = :p"
            ),
            {"t": tenant_id, "p": professional_id},
        ).one()

    assert subject == f"contact-professional:{professional_id}"
    assert email == f"contact-{professional_id}@contact.invalid"


# ---------------------------------------------------------------------------
# Same name, two people
# ---------------------------------------------------------------------------


def test_a_second_person_with_the_same_name_is_stored_rather_than_refused(
    engine: Engine, tenant_id, unit_id, actor_id, repository: SpeakerContactRepository
) -> None:
    """The ``409`` is gone, and what replaces it is two rows that are both real.

    Two professionals in one department can share a name. Under the derived
    scheme the second create was refused outright, which made the honest case
    impossible in order to prevent the rarer accident; the decision reversed
    that. Both halves are asserted — the second create returns a contact, *and*
    the roster holds two.
    """
    first = _create(engine, repository, tenant_id, unit_id, actor_id)
    second = _create(engine, repository, tenant_id, unit_id, actor_id, company="Okonkwo Partners")

    with Session(engine) as session:
        roster = repository.list_for_unit(
            session, tenant_id=tenant_id, owning_unit_id=unit_id, limit=10
        )

    assert first.contact.professional_id != second.contact.professional_id
    assert {row.professional_id for row in roster} == {
        first.contact.professional_id,
        second.contact.professional_id,
    }
    assert [row.full_name for row in roster] == [NAME, NAME]


def test_the_second_create_leaves_the_first_persons_record_untouched(
    engine: Engine, tenant_id, unit_id, actor_id, repository: SpeakerContactRepository
) -> None:
    """The failure mode an upsert would have had, asserted rather than assumed.

    Silently overwriting the first person's company with the second's is the
    outcome the removed ``409`` existed to prevent, and removing the refusal
    must not have quietly enabled it. Read back from the table rather than from
    the create's return value, because a repository that overwrote and then
    returned its argument would look correct from the outside.
    """
    first = _create(engine, repository, tenant_id, unit_id, actor_id)
    _create(engine, repository, tenant_id, unit_id, actor_id, company="Okonkwo Partners")

    with engine.connect() as conn:
        company = conn.execute(
            text(
                "SELECT company FROM speaker_profile WHERE tenant_id = :t AND professional_id = :p"
            ),
            {"t": tenant_id, "p": first.contact.professional_id},
        ).scalar_one()

    assert company == COMPANY


# ---------------------------------------------------------------------------
# The duplicate hint — what replaced the 409
# ---------------------------------------------------------------------------


def test_a_first_create_of_a_name_hints_at_nobody(
    engine: Engine, tenant_id, unit_id, actor_id, repository: SpeakerContactRepository
) -> None:
    """The hint fires on a collision and stays quiet otherwise.

    Asserted before the positive case, because a hint that is always populated
    is indistinguishable from one that works, and it trains a Connector to
    ignore it — the argument ``_withheld_fields`` already makes about reporting
    a discard that did not happen.
    """
    created = _create(engine, repository, tenant_id, unit_id, actor_id)

    assert created.same_name == ()


def test_the_hint_names_the_contact_already_holding_the_name(
    engine: Engine, tenant_id, unit_id, actor_id, repository: SpeakerContactRepository
) -> None:
    """A bare "somebody else has this name" is not actionable; a name and an employer are.

    That was the one virtue of the removed ``409`` — it named who was already
    there, so a Connector could recognize or dispute them — and it is kept.
    """
    first = _create(engine, repository, tenant_id, unit_id, actor_id)

    second = _create(engine, repository, tenant_id, unit_id, actor_id, company="Okonkwo Partners")

    assert [row.professional_id for row in second.same_name] == [first.contact.professional_id]
    assert second.same_name[0].company == COMPANY


def test_the_hint_does_not_include_the_contact_just_created(
    engine: Engine, tenant_id, unit_id, actor_id, repository: SpeakerContactRepository
) -> None:
    """A row cannot be a duplicate of itself.

    The guard is structural — the hint is read *before* the insert — and this
    pins it, because reading afterwards and filtering the new id out would be
    one forgotten predicate away from telling every Connector that the person
    they just added already exists.
    """
    created = _create(engine, repository, tenant_id, unit_id, actor_id)

    assert created.contact.professional_id not in {row.professional_id for row in created.same_name}


def test_the_hint_folds_case_and_surrounding_space(
    engine: Engine, tenant_id, unit_id, actor_id, repository: SpeakerContactRepository
) -> None:
    """``"  DANA REYES  "`` is how the same person gets typed a second time.

    The removed derivation folded with ``.strip().casefold()`` and that is the
    one part of it worth keeping: a hint matching only byte-identical names
    would miss the commonest way a duplicate is actually created. The SQL side
    folds with ``lower(btrim(...))``, which is what
    ``ix_speaker_profile_unit_folded_name`` indexes.
    """
    first = _create(engine, repository, tenant_id, unit_id, actor_id)

    second = _create(engine, repository, tenant_id, unit_id, actor_id, full_name="  DANA REYES  ")

    assert [row.professional_id for row in second.same_name] == [first.contact.professional_id]


def test_a_different_name_hints_at_nobody(
    engine: Engine, tenant_id, unit_id, actor_id, repository: SpeakerContactRepository
) -> None:
    """The fold is a fold, not a fuzzy match.

    ``"Dana Ryes"`` and ``"Dana Reyes"`` are one letter apart and are two
    different strings, so the hint says nothing about them. Deliberate: a hint
    that guessed at near-misses would fire constantly on a real roster, and
    OQ-CBA-050 is where similarity matching is recorded rather than invented
    here.
    """
    _create(engine, repository, tenant_id, unit_id, actor_id)

    other = _create(engine, repository, tenant_id, unit_id, actor_id, full_name=TYPO_NAME)

    assert other.same_name == ()


def test_the_hint_is_scoped_to_the_owning_unit(
    engine: Engine, tenant_id, unit_id, other_unit_id, actor_id, repository
) -> None:
    """Another department's roster is not this Connector's business.

    ``owning_unit_id`` scoping is the same A5 rectangle every other read in this
    module applies, and it matters more for the hint than for a listing: a hint
    that reached across units would disclose who another department knows, to
    somebody who cannot read that roster.
    """
    _create(engine, repository, tenant_id, unit_id, actor_id)

    elsewhere = _create(engine, repository, tenant_id, other_unit_id, actor_id)

    assert elsewhere.same_name == ()


def test_the_hint_reader_honours_its_callers_cap(
    engine: Engine, tenant_id, unit_id, actor_id, repository: SpeakerContactRepository
) -> None:
    """``list_same_name`` returns at most ``limit`` and invents no flag beside it.

    ``list_for_unit``'s stated arrangement: the caller passes the cap and decides
    what a full page means, because a repository inventing a "truncated" flag
    would be a second opinion beside the route's own. The route therefore asks
    for one more than it shows — which is what lets it answer truthfully rather
    than presenting a capped list as the whole answer.
    """
    for company in ("First Employer", "Second Employer", "Third Employer"):
        _create(engine, repository, tenant_id, unit_id, actor_id, company=company)

    with Session(engine) as session:
        capped = repository.list_same_name(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            full_name=NAME,
            limit=2,
        )

    assert len(capped) == 2


# ---------------------------------------------------------------------------
# The rename fork — the defect the decision was taken to close
# ---------------------------------------------------------------------------


def test_the_rename_fork_no_longer_hides_a_second_record(
    engine: Engine, tenant_id, unit_id, actor_id, repository: SpeakerContactRepository
) -> None:
    """The exact three-step sequence that used to corrupt data in silence.

    1. A Connector types ``"Dana Ryes"``.
    2. They correct it to ``"Dana Reyes"``.
    3. Somebody creates ``"Dana Reyes"``.

    Under the derived scheme step 3 succeeded and **nothing said so**: the
    duplicate guard compared derived ids, the renamed row's id was still
    ``uuid5(…"dana ryes")``, and a create of ``"Dana Reyes"`` derived a
    different id, so the guard could not see the collision it existed to catch.
    One person, two records, no warning.

    The assertion is not "one row" — the decision made a same-name create a
    legitimate act, so step 3 still succeeds and *must*. What it asserts is that
    the guard now fires: the hint compares **names**, which is the thing a
    rename actually changes, so whoever creates the second record is told about
    the first and can stop. Silent is what this closes, not possible.
    """
    typo = _create(engine, repository, tenant_id, unit_id, actor_id, full_name=TYPO_NAME)
    _rename(engine, repository, tenant_id, unit_id, actor_id, typo.contact.professional_id, to=NAME)

    again = _create(engine, repository, tenant_id, unit_id, actor_id)

    assert [row.professional_id for row in again.same_name] == [typo.contact.professional_id], (
        "the create after a rename must be told about the renamed contact; under "
        "the derived scheme this was exactly the case the guard could not see"
    )
    assert again.same_name[0].full_name == NAME
