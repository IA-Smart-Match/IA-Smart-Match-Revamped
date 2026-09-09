"""The rename hint's read: same fold as the create's, minus the row being renamed.

**OQ-CBA-049, decided 2026-09-06.** The create has warned about a same-name
contact since OQ-CBA-017 replaced ``409 speaker_contact_name_already_used`` with
a hint. An *edit* that renamed somebody into a name the unit already held said
nothing at all — the same hazard from the other direction, with no signal — and
this module owns the persistence half of closing that gap:
:meth:`SpeakerContactRepository.list_same_name` with ``exclude_professional_id``.

``tests/integration/test_cba_opaque_speaker_identity.py`` owns the create's read
and the identity decision underneath both; ``tests/contract/`` owns what a
Connector actually sees over HTTP. What is here is the one thing the edit path
needs that the create path does not.

Why an exclusion argument exists at all
-----------------------------------------
A create reads *before* it inserts, so the row it is about does not exist yet
and cannot appear in its own hint — the arrangement is the guarantee. A rename
has no equivalent: the contact being renamed has been stored since some earlier
request, and it carries the new name as soon as the ``UPDATE`` lands. An
unfiltered read would return it and report that a contact shares a name with
itself, which is not a warning about anything. A warning that fires on every
single rename is one a Connector learns to click past within a week, and the
cost of that is paid by the renames that *did* collide with somebody.

Excluded in SQL rather than dropped afterwards, and the cap is why: a caller
that filtered in Python would still have spent one of its ``limit`` rows on the
excluded contact, so a hint capped at ten could show nine while reporting itself
full.

Nothing here refuses anything. There is no uniqueness constraint on
``(tenant_id, owning_unit_id, full_name)`` and there is not going to be one
(OQ-CBA-021); every assertion below is about what a caller is *told*.

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

#: The name two contacts end up sharing, and the typo one of them starts from.
NAME = "Dana Reyes"
TYPO_NAME = "Dana Ryes"
COMPANY = "Reyes Analytics"
TITLE = "Principal Analyst"


@pytest.fixture(autouse=True)
def _clean_contacts(engine: Engine, tenant_id):
    """Clear this file's rows before ``tenant_id`` tears its own down.

    ``speaker_profile`` holds ``ON DELETE RESTRICT`` references to both
    ``user_account`` and ``org_unit``, and every create here writes an account
    of its own, so the two child tables go first — the ordering
    ``test_cba_opaque_speaker_identity.py``'s cleanup fixture exists for.
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
    """The Speaker Connector every write here is performed by.

    A real ``user_account``: ``fk_speaker_profile_industry_classified_by`` is a
    composite key into ``(tenant_id, id)``, so an invented id would fail the
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
                "sub": unique_subject(f"rename-connector-{account_id.hex[:8]}"),
                "email": f"rename-connector-{account_id.hex[:8]}@example.edu",
            },
        )
    return account_id


def _draft(**overrides: object) -> SpeakerContactDraft:
    """An unclassified contact. Overrides replace whole fields."""
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


def _same_name(
    engine: Engine, repository, tenant_id, unit_id, *, name=NAME, limit=10, exclude=None
):
    """The lookup under test, in its own read-only session."""
    with Session(engine) as session:
        return repository.list_same_name(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            full_name=name,
            limit=limit,
            exclude_professional_id=exclude,
        )


# ---------------------------------------------------------------------------
# The exclusion
# ---------------------------------------------------------------------------


def test_the_renamed_contact_is_left_out_of_its_own_answer(
    engine: Engine, tenant_id, unit_id, actor_id, repository: SpeakerContactRepository
) -> None:
    """The single reason this argument exists.

    After the ``UPDATE`` lands, the renamed row carries the new name like any
    other. Asked without the exclusion the read would return it — the assertion
    below therefore reads the same name twice, once each way, so a regression
    that quietly ignored the argument could not pass by finding nothing.
    """
    created = _create(engine, repository, tenant_id, unit_id, actor_id, full_name=TYPO_NAME)
    professional_id = created.contact.professional_id
    _rename(engine, repository, tenant_id, unit_id, actor_id, professional_id, to=NAME)

    unfiltered = _same_name(engine, repository, tenant_id, unit_id)
    excluded = _same_name(engine, repository, tenant_id, unit_id, exclude=professional_id)

    assert [row.professional_id for row in unfiltered] == [professional_id]
    assert excluded == ()


def test_the_exclusion_keeps_everybody_else(
    engine: Engine, tenant_id, unit_id, actor_id, repository: SpeakerContactRepository
) -> None:
    """Excluding one row must not excuse the read from answering.

    A renamed contact that collides with somebody is the case the hint exists
    for, and an over-broad exclusion — folding on the name, say, rather than
    matching the id — would silence exactly it while leaving the previous test
    green.
    """
    resident = _create(engine, repository, tenant_id, unit_id, actor_id)
    renamed = _create(engine, repository, tenant_id, unit_id, actor_id, full_name=TYPO_NAME)
    professional_id = renamed.contact.professional_id
    _rename(engine, repository, tenant_id, unit_id, actor_id, professional_id, to=NAME)

    matches = _same_name(engine, repository, tenant_id, unit_id, exclude=professional_id)

    assert [row.professional_id for row in matches] == [resident.contact.professional_id]
    assert matches[0].full_name == NAME
    assert matches[0].company == COMPANY


def test_the_exclusion_is_optional_and_the_create_path_is_unchanged(
    engine: Engine, tenant_id, unit_id, actor_id, repository: SpeakerContactRepository
) -> None:
    """The create passes no exclusion and must keep getting the whole answer.

    ``exclude_professional_id`` defaults to ``None`` so that adding the edit
    path's argument could not narrow the create's hint by accident. Asserted
    through :meth:`create` itself rather than through a bare lookup, because
    that is the caller whose behaviour must not have moved.
    """
    first = _create(engine, repository, tenant_id, unit_id, actor_id)

    second = _create(engine, repository, tenant_id, unit_id, actor_id, company="Okonkwo Partners")

    assert [row.professional_id for row in second.same_name] == [first.contact.professional_id]


def test_the_exclusion_folds_the_name_the_way_the_create_does(
    engine: Engine, tenant_id, unit_id, actor_id, repository: SpeakerContactRepository
) -> None:
    """One fold, both directions. ``lower(btrim(...))``, and no more than that.

    A rename to ``"  DANA REYES  "`` is the commonest way one person gets a
    second record, so the edit's read has to fold exactly as the create's does.
    It is the *same* method, so this pins that the exclusion did not arrive
    beside a second, subtly different comparison.
    """
    resident = _create(engine, repository, tenant_id, unit_id, actor_id)
    renamed = _create(engine, repository, tenant_id, unit_id, actor_id, full_name=TYPO_NAME)
    professional_id = renamed.contact.professional_id
    _rename(engine, repository, tenant_id, unit_id, actor_id, professional_id, to="  DANA REYES  ")

    matches = _same_name(
        engine,
        repository,
        tenant_id,
        unit_id,
        name="  DANA REYES  ",
        exclude=professional_id,
    )

    assert [row.professional_id for row in matches] == [resident.contact.professional_id]


def test_a_near_miss_is_still_not_a_match(
    engine: Engine, tenant_id, unit_id, actor_id, repository: SpeakerContactRepository
) -> None:
    """**OQ-CBA-050, decided 2026-09-06: exact folded match only.**

    ``"Dana Ryes"`` and ``"Dana Reyes"`` are one letter apart and are two
    different names. No similarity algorithm, no cutoff, nothing to tune — a
    hint that guessed at near-misses would fire constantly on a real roster and
    be ignored, and the decision is revisitable once somebody has a roster large
    enough to measure a false-positive rate on.
    """
    _create(engine, repository, tenant_id, unit_id, actor_id)
    renamed = _create(engine, repository, tenant_id, unit_id, actor_id, company="Okonkwo Partners")
    professional_id = renamed.contact.professional_id
    _rename(engine, repository, tenant_id, unit_id, actor_id, professional_id, to=TYPO_NAME)

    matches = _same_name(
        engine, repository, tenant_id, unit_id, name=TYPO_NAME, exclude=professional_id
    )

    assert matches == ()


def test_the_exclusion_does_not_reach_across_units(
    engine: Engine, tenant_id, unit_id, actor_id, repository: SpeakerContactRepository
) -> None:
    """``owning_unit_id`` is a disclosure boundary and the exclusion is inside it.

    A hint that reached another department would tell a Connector who that
    department knows. The scoping predicate is the create's and is untouched;
    this pins that the new predicate sits beside it rather than replacing it.
    """
    other_unit = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                "VALUES (:id, :tid, :path, 'department', 'Second department')"
            ),
            {"id": other_unit, "tid": tenant_id, "path": f"unit_{other_unit.hex[:8]}"},
        )
    _create(engine, repository, tenant_id, unit_id, actor_id)
    elsewhere = _create(engine, repository, tenant_id, other_unit, actor_id, full_name=TYPO_NAME)
    professional_id = elsewhere.contact.professional_id
    _rename(engine, repository, tenant_id, other_unit, actor_id, professional_id, to=NAME)

    matches = _same_name(engine, repository, tenant_id, other_unit, exclude=professional_id)

    assert matches == ()


def test_the_cap_is_spent_on_other_people_only(
    engine: Engine, tenant_id, unit_id, actor_id, repository: SpeakerContactRepository
) -> None:
    """The reason the exclusion is a SQL predicate rather than a later filter.

    With three contacts under one name and the renamed one excluded, a read
    capped at two must return two *other* people. A caller that filtered
    afterwards would have spent one row of the cap on the excluded contact and
    returned one — which is how a truncation flag ends up lying about a list
    that was never full.
    """
    _create(engine, repository, tenant_id, unit_id, actor_id, company="First Employer")
    _create(engine, repository, tenant_id, unit_id, actor_id, company="Second Employer")
    renamed = _create(engine, repository, tenant_id, unit_id, actor_id, full_name=TYPO_NAME)
    professional_id = renamed.contact.professional_id
    _rename(engine, repository, tenant_id, unit_id, actor_id, professional_id, to=NAME)

    matches = _same_name(engine, repository, tenant_id, unit_id, limit=2, exclude=professional_id)

    assert len(matches) == 2
    assert professional_id not in {row.professional_id for row in matches}
