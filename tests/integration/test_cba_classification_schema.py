"""What migration ``0024``'s CBA classification storage refuses, against real PostgreSQL.

Customer §7 says "each speaker should have **one primary industry sector**" and
§8 says "each speaker should normally have **one primary role category**", while
§7's event-side paragraph says "a Speaker Request may target **multiple
industries**" and §12 says a host may "select one or more industries" and "one
or more roles". Those are two different cardinalities over the same two closed
vocabularies, and this module is where the database is required to hold them
apart.

Every test attempts the write and requires the database to answer. None of them
goes through a repository: application code guards the same rules, and a test
routed through it would prove the guard rather than the constraint — the
discipline ``test_event_schema_constraints.py`` already states for ADR-0010.

The taxonomy membership tests are deliberately **driven from the domain
modules** rather than from a literal list repeated here.
``docs/product/cba-taxonomies.md`` requires the domain module to be the only
copy of each vocabulary, and migration ``0024`` still has to transcribe the
codes into a ``CHECK`` — a constraint cannot import Python. That transcription
is a second copy whether or not anyone likes it, so these tests bind the two
ends together behaviourally: every code
:mod:`smartmatch_domain.naics_sectors` and
:mod:`smartmatch_domain.cba_role_categories` release must be storable, and a
value neither releases must not be. A twenty-first sector added to the domain
without a migration fails here, which is the only place the divergence can be
caught before it reaches a speaker's record.

Requires a live database, and is skipped when none is reachable.
"""

from __future__ import annotations

import uuid

import pytest

pytest.importorskip("sqlalchemy")

from conftest import ensure_owning_unit, unique_subject
from smartmatch_domain.cba_role_categories import (
    CBA_ROLE_TAXONOMY_VERSION,
    ROLE_CATEGORY_CODES,
)
from smartmatch_domain.event_vocabulary import TERM_CONCEPTS, VOCABULARY_VERSION
from smartmatch_domain.naics_sectors import NAICS_TAXONOMY_VERSION, SECTOR_CODES
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _clean_classification_tables(engine: Engine, tenant_id):
    """Delete this file's rows before ``tenant_id`` tears its own down.

    ``speaker_profile`` holds ``ON DELETE RESTRICT`` references to both
    ``user_account`` and ``org_unit``, so a row left behind here would make
    ``conftest.py``'s teardown fail on those two deletes — the same hazard
    ``test_event_schema_constraints.py``'s own cleanup fixture exists for.
    Child before parent; ``speaker_request_classification`` would cascade with
    its event anyway and is deleted explicitly so a failure names the table it
    happened in.
    """
    yield
    with engine.begin() as conn:
        for table in ("speaker_request_classification", "speaker_profile", "event"):
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": tenant_id})


# ---------------------------------------------------------------------------
# Row builders. Each defaults to a row every constraint accepts, so a test body
# holds only the value under test.
# ---------------------------------------------------------------------------


def _make_professional(conn, tenant_id: uuid.UUID) -> uuid.UUID:
    """One ``user_account``, which is what a professional's identity is today.

    ``smartmatch_persistence.professionals`` (Choice A of the synthetic pilot
    authorization) creates a real ``user_account`` per professional, and
    ``speaker_profile.professional_id`` references it. Routed through
    :func:`conftest.unique_subject` because ``external_subject`` is globally
    unique as of migration ``0003``.
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
            "sub": unique_subject(f"speaker-{professional_id.hex[:8]}"),
            "email": f"{professional_id.hex[:8]}@example.edu",
        },
    )
    return professional_id


def _insert_profile(
    conn,
    tenant_id: uuid.UUID,
    *,
    professional_id: uuid.UUID | None = None,
    owning_unit_id: uuid.UUID | None = None,
    primary_industry_code: str | None = None,
    industry_taxonomy_version: str | None = None,
    primary_role_code: str | None = None,
    role_taxonomy_version: str | None = None,
    topic_text: str | None = None,
    prior_talk: str | None = None,
    location_city: str | None = None,
    location_postal_code: str | None = None,
) -> uuid.UUID:
    if professional_id is None:
        professional_id = _make_professional(conn, tenant_id)
    if owning_unit_id is None:
        owning_unit_id = ensure_owning_unit(conn, tenant_id)
    conn.execute(
        text(
            "INSERT INTO speaker_profile (tenant_id, professional_id, owning_unit_id, "
            "primary_industry_code, industry_taxonomy_version, primary_role_code, "
            "role_taxonomy_version, topic_text, prior_talk, location_city, "
            "location_postal_code) "
            "VALUES (:tid, :pid, :unit, :industry, :industry_version, :role, "
            ":role_version, :topic, :prior_talk, :city, :postal)"
        ),
        {
            "tid": tenant_id,
            "pid": professional_id,
            "unit": owning_unit_id,
            "industry": primary_industry_code,
            "industry_version": industry_taxonomy_version,
            "role": primary_role_code,
            "role_version": role_taxonomy_version,
            "topic": topic_text,
            "prior_talk": prior_talk,
            "city": location_city,
            "postal": location_postal_code,
        },
    )
    return professional_id


def _insert_speaker_request(
    conn,
    tenant_id: uuid.UUID,
    *,
    title: str = "Synthetic Speaker Request",
    is_virtual: bool = False,
    location_city: str | None = "Pomona",
    location_postal_code: str | None = "91768",
) -> uuid.UUID:
    """One ``event`` row — a Speaker Request is persisted as an event (§4, §12).

    ``date_only`` and ``coordinator_entry``: the honest shape for a row a host
    typed in, and the same choice ``conftest.ensure_event`` makes.
    """
    event_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO event (id, tenant_id, host_org_unit_id, title, normalized_title, "
            "on_date, time_zone, time_precision, resolved_date, origin, is_virtual, "
            "location_city, location_postal_code) "
            "VALUES (:id, :tid, :unit, :title, :normalized, DATE '2026-09-14', "
            "'America/Los_Angeles', 'date_only', DATE '2026-09-14', 'coordinator_entry', "
            ":virtual, :city, :postal)"
        ),
        {
            "id": event_id,
            "tid": tenant_id,
            "unit": ensure_owning_unit(conn, tenant_id),
            "title": f"{title} {event_id.hex[:8]}",
            "normalized": f"{title} {event_id.hex[:8]}".casefold(),
            "virtual": is_virtual,
            "city": location_city,
            "postal": location_postal_code,
        },
    )
    return event_id


#: Sentinel for "whichever taxonomy version matches ``kind``". A distinct
#: object rather than ``None``, because ``None`` is a value one test needs to
#: pass through unchanged: the version column is ``NOT NULL`` and refusing a
#: missing one is the thing that test asserts.
_MATCHING_VERSION = "…match the kind…"


def _insert_request_classification(
    conn,
    tenant_id: uuid.UUID,
    event_id: uuid.UUID,
    *,
    kind: str,
    code: str,
    taxonomy_version: str | None = _MATCHING_VERSION,
) -> uuid.UUID:
    if taxonomy_version is _MATCHING_VERSION:
        taxonomy_version = (
            NAICS_TAXONOMY_VERSION if kind == "industry" else CBA_ROLE_TAXONOMY_VERSION
        )
    row_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO speaker_request_classification "
            "(id, tenant_id, event_id, kind, code, taxonomy_version) "
            "VALUES (:id, :tid, :event, :kind, :code, :version)"
        ),
        {
            "id": row_id,
            "tid": tenant_id,
            "event": event_id,
            "kind": kind,
            "code": code,
            "version": taxonomy_version,
        },
    )
    return row_id


# ---------------------------------------------------------------------------
# Speaker side — customer §§7-8: zero or one primary industry, zero or one
# primary role. The cardinality is structural: one column each on a table keyed
# by (tenant_id, professional_id), so a second primary value has nowhere to go.
# ---------------------------------------------------------------------------


def test_a_speaker_holds_one_primary_industry_and_one_primary_role(
    engine: Engine, tenant_id
) -> None:
    """The permitted write, which is what catches a constraint refusing everything."""
    with engine.begin() as conn:
        professional_id = _insert_profile(
            conn,
            tenant_id,
            primary_industry_code="52",
            industry_taxonomy_version=NAICS_TAXONOMY_VERSION,
            primary_role_code="finance",
            role_taxonomy_version=CBA_ROLE_TAXONOMY_VERSION,
        )
        row = conn.execute(
            text(
                "SELECT primary_industry_code, primary_role_code FROM speaker_profile "
                "WHERE tenant_id = :tid AND professional_id = :pid"
            ),
            {"tid": tenant_id, "pid": professional_id},
        ).one()

    assert row.primary_industry_code == "52"
    assert row.primary_role_code == "finance"


def test_a_speaker_cannot_hold_a_second_primary_classification(engine: Engine, tenant_id) -> None:
    """§7's "one primary industry sector", enforced by the key rather than by a rule.

    A second primary value is not refused by a CHECK that someone could write
    an exception into; it has no row to live in. This is the same argument
    ``professional_unit_relationship``'s composite natural key makes about
    multiplicity, applied in the opposite direction — there the key *permits*
    many rows per professional, here it *forbids* them.
    """
    with engine.begin() as conn:
        professional_id = _insert_profile(
            conn,
            tenant_id,
            primary_industry_code="52",
            industry_taxonomy_version=NAICS_TAXONOMY_VERSION,
        )

    with pytest.raises(IntegrityError, match="speaker_profile_pkey"), engine.begin() as conn:
        _insert_profile(
            conn,
            tenant_id,
            professional_id=professional_id,
            primary_industry_code="51",
            industry_taxonomy_version=NAICS_TAXONOMY_VERSION,
        )


def test_a_speaker_may_carry_neither_classification_yet(engine: Engine, tenant_id) -> None:
    """Zero-or-one, not exactly-one.

    §19's flow imports a contact first and classifies it afterwards, and §7
    requires a Speaker Connector to be able to *correct* an assignment — both
    of which need an unclassified speaker to be a storable state rather than an
    unstorable one. The same reasoning ``test_event_schema_constraints.py``
    applies to an unresolved event.
    """
    with engine.begin() as conn:
        professional_id = _insert_profile(conn, tenant_id)
        row = conn.execute(
            text(
                "SELECT primary_industry_code, primary_role_code, "
                "industry_taxonomy_version, role_taxonomy_version FROM speaker_profile "
                "WHERE tenant_id = :tid AND professional_id = :pid"
            ),
            {"tid": tenant_id, "pid": professional_id},
        ).one()

    assert row.primary_industry_code is None
    assert row.primary_role_code is None
    assert row.industry_taxonomy_version is None
    assert row.role_taxonomy_version is None


def test_a_connector_correction_replaces_the_primary_industry_in_place(
    engine: Engine, tenant_id
) -> None:
    """§7: "a Speaker Connector must be able to manually correct the assigned industry".

    Correction is an ``UPDATE`` of the one primary value, not a second row
    superseding the first — the same current-state-only treatment P9 Gate A §2
    gives ``board_role``, and the reason ``speaker_profile`` carries
    ``updated_at``. Whether the *previous* value is retained anywhere is
    OQ-CBA-008, open at the time this migration landed.
    """
    with engine.begin() as conn:
        professional_id = _insert_profile(
            conn,
            tenant_id,
            primary_industry_code="52",
            industry_taxonomy_version=NAICS_TAXONOMY_VERSION,
        )
        conn.execute(
            text(
                "UPDATE speaker_profile SET primary_industry_code = '51' "
                "WHERE tenant_id = :tid AND professional_id = :pid"
            ),
            {"tid": tenant_id, "pid": professional_id},
        )
        code = conn.execute(
            text(
                "SELECT primary_industry_code FROM speaker_profile "
                "WHERE tenant_id = :tid AND professional_id = :pid"
            ),
            {"tid": tenant_id, "pid": professional_id},
        ).scalar_one()

    assert code == "51"


@pytest.mark.parametrize("code", SECTOR_CODES)
def test_every_released_sector_code_is_storable(engine: Engine, tenant_id, code: str) -> None:
    """Driven from the domain module, so a taxonomy revision fails here first.

    Including the three hyphenated ranges ``31-33``, ``44-45`` and ``48-49``,
    which is why the column is ``TEXT`` and not an integer.
    """
    with engine.begin() as conn:
        _insert_profile(
            conn,
            tenant_id,
            primary_industry_code=code,
            industry_taxonomy_version=NAICS_TAXONOMY_VERSION,
        )


@pytest.mark.parametrize("code", ROLE_CATEGORY_CODES)
def test_every_released_role_category_code_is_storable(
    engine: Engine, tenant_id, code: str
) -> None:
    with engine.begin() as conn:
        _insert_profile(
            conn,
            tenant_id,
            primary_role_code=code,
            role_taxonomy_version=CBA_ROLE_TAXONOMY_VERSION,
        )


@pytest.mark.parametrize(
    "code",
    ["Finance", "finance", "52 ", "3133", "31", "tech", ""],
    ids=["display-name", "role-code", "padded", "unhyphenated", "range-half", "alias", "blank"],
)
def test_an_industry_value_outside_the_taxonomy_is_refused(
    engine: Engine, tenant_id, code: str
) -> None:
    """The closed list is closed in the database too, not only in Python.

    ``sector_for_code`` refuses each of these; so must the column, because the
    column is what a hand-written ``INSERT`` in a psql session reaches. The
    aliases are listed for the reason the taxonomy module states: ``Tech`` does
    not silently become ``Information``, and this is where "silently" is
    prevented at the storage layer.
    """
    with (
        pytest.raises(IntegrityError, match="ck_speaker_profile_industry_code"),
        engine.begin() as conn,
    ):
        _insert_profile(
            conn,
            tenant_id,
            primary_industry_code=code,
            industry_taxonomy_version=NAICS_TAXONOMY_VERSION,
        )


@pytest.mark.parametrize(
    "code",
    ["Finance", "52", "Management & Strategy", "hr", ""],
    ids=["display-name", "sector-code", "display-punctuation", "alias", "blank"],
)
def test_a_role_value_outside_the_taxonomy_is_refused(engine: Engine, tenant_id, code: str) -> None:
    with (
        pytest.raises(IntegrityError, match="ck_speaker_profile_role_code"),
        engine.begin() as conn,
    ):
        _insert_profile(
            conn,
            tenant_id,
            primary_role_code=code,
            role_taxonomy_version=CBA_ROLE_TAXONOMY_VERSION,
        )


@pytest.mark.parametrize("term", sorted(TERM_CONCEPTS))
def test_an_adr_0012_event_tag_cannot_be_stored_as_a_cba_role(
    engine: Engine, tenant_id, term: str
) -> None:
    """CBA roles are not event tags, proved at the column rather than by convention.

    ``docs/product/cba-taxonomies.md`` is explicit that the word "role" means
    unrelated things in the two vocabularies — an ADR-0012 ``role`` term is an
    event function (``panelist``, ``judge``), a CBA role category is a career
    discipline. The domain keeps them apart by type; this keeps them apart in
    the database, where a bulk update has no types to obey.
    """
    with (
        pytest.raises(IntegrityError, match="ck_speaker_profile_role_code"),
        engine.begin() as conn,
    ):
        _insert_profile(
            conn,
            tenant_id,
            primary_role_code=term,
            role_taxonomy_version=VOCABULARY_VERSION,
        )


def test_a_stored_classification_must_name_the_taxonomy_it_was_resolved_against(
    engine: Engine, tenant_id
) -> None:
    """The version token is what keeps a stored code interpretable after a revision.

    Both taxonomy modules stamp one onto every ``Classified…`` value for that
    reason, and ``event_tag.vocabulary_version`` is ``NOT NULL`` for it. Here
    the pairing is conditional rather than unconditional, because the code
    itself is optional: a code without a version, and a version without a code,
    are both refused.
    """
    with (
        pytest.raises(IntegrityError, match="ck_speaker_profile_industry_versioned"),
        engine.begin() as conn,
    ):
        _insert_profile(conn, tenant_id, primary_industry_code="52")

    with (
        pytest.raises(IntegrityError, match="ck_speaker_profile_industry_versioned"),
        engine.begin() as conn,
    ):
        _insert_profile(conn, tenant_id, industry_taxonomy_version=NAICS_TAXONOMY_VERSION)

    with (
        pytest.raises(IntegrityError, match="ck_speaker_profile_role_versioned"),
        engine.begin() as conn,
    ):
        _insert_profile(conn, tenant_id, primary_role_code="finance")

    with (
        pytest.raises(IntegrityError, match="ck_speaker_profile_role_versioned"),
        engine.begin() as conn,
    ):
        _insert_profile(conn, tenant_id, role_taxonomy_version=CBA_ROLE_TAXONOMY_VERSION)


def test_a_speaker_stores_topic_prior_talk_and_location(engine: Engine, tenant_id) -> None:
    """§18's "additional fields required by matching", round-tripped.

    §10 says city or ZIP is sufficient for this phase, so both are nullable and
    neither implies the other; §9 needs topic text, and §18 names prior talk
    information as optional.
    """
    with engine.begin() as conn:
        professional_id = _insert_profile(
            conn,
            tenant_id,
            topic_text="Supply chain resilience after the 2020s",
            prior_talk="Keynote, CPP Logistics Summit 2025",
            location_city="Pomona",
            location_postal_code="91768",
        )
        row = conn.execute(
            text(
                "SELECT topic_text, prior_talk, location_city, location_postal_code "
                "FROM speaker_profile WHERE tenant_id = :tid AND professional_id = :pid"
            ),
            {"tid": tenant_id, "pid": professional_id},
        ).one()

    assert row.topic_text == "Supply chain resilience after the 2020s"
    assert row.prior_talk == "Keynote, CPP Logistics Summit 2025"
    assert row.location_city == "Pomona"
    assert row.location_postal_code == "91768"


@pytest.mark.parametrize(
    "field",
    ["topic_text", "prior_talk", "location_city", "location_postal_code"],
)
def test_a_blank_speaker_field_is_refused_rather_than_stored(
    engine: Engine, tenant_id, field: str
) -> None:
    """ADR-0011's distinction: absent is a value, blank is a writer that forgot.

    §9 assigns a *neutral* topic score to a speaker with no topic information,
    which is a decision about NULL. An empty string would reach that decision
    as text and be scored as if it said something.
    """
    with (
        pytest.raises(IntegrityError, match="ck_speaker_profile_text_present"),
        engine.begin() as conn,
    ):
        _insert_profile(conn, tenant_id, **{field: "   "})


def test_a_speaker_profile_cannot_name_a_unit_in_another_tenant(engine: Engine, tenant_id) -> None:
    """v1.1 §2.2, the reason every reference in this schema carries ``tenant_id``."""
    other_tenant = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": other_tenant, "slug": f"other-{other_tenant.hex[:12]}"},
        )
        foreign_unit = ensure_owning_unit(conn, other_tenant)

    try:
        with pytest.raises(IntegrityError), engine.begin() as conn:
            _insert_profile(conn, tenant_id, owning_unit_id=foreign_unit)
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM org_unit WHERE tenant_id = :tid"), {"tid": other_tenant})
            conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": other_tenant})


def test_a_speaker_profile_cannot_name_a_professional_in_another_tenant(
    engine: Engine, tenant_id
) -> None:
    """The half a single-column key to ``user_account.id`` would have accepted."""
    other_tenant = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": other_tenant, "slug": f"other-{other_tenant.hex[:12]}"},
        )
        foreign_professional = _make_professional(conn, other_tenant)

    try:
        with pytest.raises(IntegrityError), engine.begin() as conn:
            _insert_profile(conn, tenant_id, professional_id=foreign_professional)
    finally:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM user_account WHERE tenant_id = :tid"), {"tid": other_tenant}
            )
            conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": other_tenant})


def test_a_professional_with_a_speaker_profile_cannot_be_deleted(engine: Engine, tenant_id) -> None:
    """RESTRICT: a classification must not outlive, or silently vanish with, its subject."""
    with engine.begin() as conn:
        professional_id = _insert_profile(conn, tenant_id)

    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text("DELETE FROM user_account WHERE id = :id"), {"id": professional_id})


# ---------------------------------------------------------------------------
# Speaker Request side — customer §7 "a Speaker Request may target multiple
# industries", §8 "may target multiple role categories", §12 "select one or
# more industries ... one or more roles". A child table, not an array column
# and not `event_tag`.
# ---------------------------------------------------------------------------


def test_a_speaker_request_targets_many_industries_and_many_roles(
    engine: Engine, tenant_id
) -> None:
    """§7 and §8's event side: "do not restrict an event request to one"."""
    with engine.begin() as conn:
        event_id = _insert_speaker_request(conn, tenant_id)
        for code in ("51", "52", "54"):
            _insert_request_classification(conn, tenant_id, event_id, kind="industry", code=code)
        for code in ("finance", "accounting", "marketing"):
            _insert_request_classification(conn, tenant_id, event_id, kind="role", code=code)

        rows = conn.execute(
            text(
                "SELECT kind, code FROM speaker_request_classification "
                "WHERE tenant_id = :tid AND event_id = :event ORDER BY kind, code"
            ),
            {"tid": tenant_id, "event": event_id},
        ).all()

    assert [(row.kind, row.code) for row in rows] == [
        ("industry", "51"),
        ("industry", "52"),
        ("industry", "54"),
        ("role", "accounting"),
        ("role", "finance"),
        ("role", "marketing"),
    ]


def test_a_speaker_request_cannot_target_the_same_classification_twice(
    engine: Engine, tenant_id
) -> None:
    """Multi-select is a set, not a bag: a duplicate is a double-counted target.

    ``event_tag`` makes the same choice with ``uq_event_tag_term``, and for the
    same reason — a matcher weighting a repeated value twice is a scoring bug
    with no visible cause.
    """
    with engine.begin() as conn:
        event_id = _insert_speaker_request(conn, tenant_id)
        _insert_request_classification(conn, tenant_id, event_id, kind="industry", code="52")

    with (
        pytest.raises(IntegrityError, match="uq_speaker_request_classification"),
        engine.begin() as conn,
    ):
        _insert_request_classification(conn, tenant_id, event_id, kind="industry", code="52")


@pytest.mark.parametrize("code", SECTOR_CODES)
def test_every_released_sector_code_is_targetable(engine: Engine, tenant_id, code: str) -> None:
    with engine.begin() as conn:
        event_id = _insert_speaker_request(conn, tenant_id)
        _insert_request_classification(conn, tenant_id, event_id, kind="industry", code=code)


@pytest.mark.parametrize("code", ROLE_CATEGORY_CODES)
def test_every_released_role_category_code_is_targetable(
    engine: Engine, tenant_id, code: str
) -> None:
    with engine.begin() as conn:
        event_id = _insert_speaker_request(conn, tenant_id)
        _insert_request_classification(conn, tenant_id, event_id, kind="role", code=code)


def test_the_two_vocabularies_cannot_be_stored_under_each_others_kind(
    engine: Engine, tenant_id
) -> None:
    """One table, two vocabularies, and ``kind`` decides which one a row is checked against.

    Without the conditional CHECK, ``kind`` would be a label a row carries
    rather than a statement the database holds it to, and an industry target
    reading ``finance`` would sit next to a role target reading ``52``.
    """
    with engine.begin() as conn:
        event_id = _insert_speaker_request(conn, tenant_id)

    with (
        pytest.raises(IntegrityError, match="ck_speaker_request_classification_code"),
        engine.begin() as conn,
    ):
        _insert_request_classification(conn, tenant_id, event_id, kind="industry", code="finance")

    with (
        pytest.raises(IntegrityError, match="ck_speaker_request_classification_code"),
        engine.begin() as conn,
    ):
        _insert_request_classification(conn, tenant_id, event_id, kind="role", code="52")


@pytest.mark.parametrize("term", sorted(TERM_CONCEPTS))
def test_an_adr_0012_event_tag_is_not_a_speaker_request_classification(
    engine: Engine, tenant_id, term: str
) -> None:
    """The separation the wave plan requires, at the storage layer.

    ADR-0012's twelve terms describe what kind of event this is and what a
    speaker does at it. They are stored in ``event_tag`` and remain stored
    there; this table holds the industries and career disciplines a request
    targets, and refuses every one of them under either kind.
    """
    for kind in ("industry", "role"):
        with (
            pytest.raises(IntegrityError, match="ck_speaker_request_classification_code"),
            engine.begin() as conn,
        ):
            event_id = _insert_speaker_request(conn, tenant_id)
            _insert_request_classification(
                conn, tenant_id, event_id, kind=kind, code=term, taxonomy_version=VOCABULARY_VERSION
            )


def test_the_classification_kind_vocabulary_is_closed(engine: Engine, tenant_id) -> None:
    """Two kinds, because customer §§7-8 name two axes and no third is approved.

    Either constraint may be the one PostgreSQL names, and that is a property
    worth stating rather than a looseness worth hiding: an unapproved ``kind``
    violates ``ck_..._kind`` *and* ``ck_..._code``, because the code check's two
    branches are exhaustive over the two approved kinds and a third kind
    therefore satisfies neither. A row bearing an unknown axis has no way in
    even if one of the two constraints is later dropped.
    """
    with engine.begin() as conn:
        event_id = _insert_speaker_request(conn, tenant_id)

    with (
        pytest.raises(IntegrityError, match=r"ck_speaker_request_classification_(kind|code)"),
        engine.begin() as conn,
    ):
        _insert_request_classification(conn, tenant_id, event_id, kind="topic", code="52")


def test_a_classification_is_deleted_with_the_request_it_describes(
    engine: Engine, tenant_id
) -> None:
    """CASCADE, as ``event_tag`` is: a target cannot outlive the request stating it."""
    with engine.begin() as conn:
        event_id = _insert_speaker_request(conn, tenant_id)
        _insert_request_classification(conn, tenant_id, event_id, kind="industry", code="52")
        conn.execute(text("DELETE FROM event WHERE id = :id"), {"id": event_id})

        remaining = conn.execute(
            text("SELECT count(*) FROM speaker_request_classification WHERE event_id = :event"),
            {"event": event_id},
        ).scalar_one()

    assert remaining == 0


def test_a_classification_cannot_cite_an_event_in_another_tenant(engine: Engine, tenant_id) -> None:
    other_tenant = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": other_tenant, "slug": f"other-{other_tenant.hex[:12]}"},
        )
        foreign_event = _insert_speaker_request(conn, other_tenant)

    try:
        with pytest.raises(IntegrityError), engine.begin() as conn:
            _insert_request_classification(
                conn, tenant_id, foreign_event, kind="industry", code="52"
            )
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM event WHERE tenant_id = :tid"), {"tid": other_tenant})
            conn.execute(text("DELETE FROM org_unit WHERE tenant_id = :tid"), {"tid": other_tenant})
            conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": other_tenant})


def test_a_classification_must_name_the_taxonomy_it_was_resolved_against(
    engine: Engine, tenant_id
) -> None:
    """``NOT NULL`` here, unconditionally, because the code is ``NOT NULL`` too.

    A targeted classification always exists — that is what a row means — so
    unlike ``speaker_profile``'s optional primaries there is no absent case for
    the version to mirror.
    """
    with engine.begin() as conn:
        event_id = _insert_speaker_request(conn, tenant_id)

    with pytest.raises(IntegrityError), engine.begin() as conn:
        _insert_request_classification(
            conn, tenant_id, event_id, kind="industry", code="52", taxonomy_version=None
        )
