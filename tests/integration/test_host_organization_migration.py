"""What migration ``0036`` does to a **populated** ``0035`` database.

``0036_host_organization`` adds ``host_organization``,
``host_organization_member`` and the nullable ``event.host_organization_id``
(PR #154, PLAN v2 finding 10, owner decision 4). Every claim it makes is about
rows that already exist when it runs, and a scratch database migrated from
empty can prove none of them: there, the tables it adds have never been
without their column and the rows it must not rewrite were never written. So
this file brings a scratch database to ``0035``, fills it the way the previous
release would have, and then runs Alembic for real — the shape
``tests/integration/test_event_filed_by_migration.py`` established for
``0033``.

What is asserted, and why each one is a thing that could go wrong
=================================================================
* **No row is rewritten.** ``host_organization_id`` is ADDed with no server
  default and no ``UPDATE``, so every pre-``0036`` event keeps ``NULL``.
  ``NULL`` there means *no organization was recorded* — never "the host has
  none" and never "look it up from the filer". A backfill from the filer's
  organization would report today's affiliation as the one a request was filed
  under, which is a reconstruction indistinguishable from a recorded fact
  (ADR-0011 rule 1).
* **The downgrade returns the exact pre-``0036`` state**, with the pre-existing
  rows still there. A downgrade that took the events with it would be data
  loss disguised as a rollback, and the revision's own docstring promises only
  that the *new* facts go.
* **An extracted event cannot be given an organization**
  (``ck_event_host_organization_manual_origin``) — the mirror of
  ``ck_event_filed_by_manual_origin``, and for the same reason: a crawl is
  nobody's affiliation.
* **Tenant isolation is structural**, not a predicate a reader has to
  remember: the composite foreign keys refuse an organization and a member
  from another tenant.
* **One organization per host** (``uq_host_organization_member_user``) and
  **one organization per case-folded name per unit**
  (``uq_host_organization_unit_name``) — the two constraints that make "the
  caller's organization" and "this unit's organizations" well-defined phrases
  on the routes built over them.
* **A member row cannot disagree with its organization about the unit**, which
  is what the three-column foreign key to
  ``uq_host_organization_tenant_id_unit`` exists for.

What is deliberately **not** asserted here: that an organization grants
anybody anything. It does not. Authorization still runs per user through
``event.filed_by_user_id``, and
:func:`test_the_upgrade_grants_no_membership_and_no_grant` pins that by
counting the two tables the policy actually reads.

Requires a live database and the privilege to create one; skipped otherwise.
"""

from __future__ import annotations

import uuid

import pytest

pytest.importorskip("sqlalchemy")

from migration_harness import alembic, applied_revision, connected, scratch_database
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.integration

#: The revision immediately before the one under test. Read off the
#: ``revision =`` line of ``0035_manual_event_detail.py``, not off a filename:
#: Alembic revision ids are not filenames, and this repository carries the
#: standing proof — ``0024_cba_classification_schema.py`` declares
#: ``revision = "0024_cba_classification"``.
REVISION_BEFORE = "0035_manual_event_detail"

#: The revision under test, and the head at the time of writing. The upgrades
#: below run to ``head`` rather than to this id on purpose, for the reason
#: ``test_event_filed_by_migration.py`` gives about its own pin: the claim is
#: that a pre-existing row survives *every* later revision untouched, not
#: merely the one that added the column. Extending the chain is a deliberate
#: edit here.
REVISION = "0036_host_organization"
HEAD_REVISION = "0036_host_organization"

ON_DATE = "2026-10-14"
ZONE = "America/Los_Angeles"


def _insert_tenant(conn, tenant_id: uuid.UUID) -> None:
    conn.execute(
        text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
        {"id": tenant_id, "slug": f"scratch-{tenant_id.hex[:12]}"},
    )


def _insert_unit(conn, tenant_id: uuid.UUID, suffix: str = "") -> uuid.UUID:
    unit_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
            "VALUES (:id, :tid, CAST(:path AS ltree), 'department', 'Scratch')"
        ),
        {"id": unit_id, "tid": tenant_id, "path": f"scratch{unit_id.hex[:8]}{suffix}"},
    )
    return unit_id


def _insert_user(conn, tenant_id: uuid.UUID) -> uuid.UUID:
    user_id = uuid.uuid4()
    subject = f"scratch-{user_id.hex}"
    conn.execute(
        text(
            "INSERT INTO user_account (id, tenant_id, external_subject, email) "
            "VALUES (:id, :tid, :subject, :email)"
        ),
        {"id": user_id, "tid": tenant_id, "subject": subject, "email": f"{subject}@example.edu"},
    )
    return user_id


def _insert_pre_0036_filed_request(
    conn, tenant_id: uuid.UUID, unit_id: uuid.UUID, user_id: uuid.UUID, title: str
) -> uuid.UUID:
    """A ``coordinator_entry`` event with a recorded filer, as ``0035`` would have."""
    event_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO event (id, tenant_id, host_org_unit_id, title, normalized_title, "
            "                   on_date, time_zone, time_precision, resolved_date, origin, "
            "                   filed_by_user_id) "
            "VALUES (:id, :tid, :unit, :title, :norm, :on_date, :zone, 'date_only', "
            "        :on_date, 'coordinator_entry', :uid)"
        ),
        {
            "id": event_id,
            "tid": tenant_id,
            "unit": unit_id,
            "title": title,
            "norm": title.lower(),
            "on_date": ON_DATE,
            "zone": ZONE,
            "uid": user_id,
        },
    )
    return event_id


def _insert_pre_0036_extracted_event(conn, tenant_id: uuid.UUID, unit_id: uuid.UUID) -> uuid.UUID:
    """An ``extraction`` event. RFC 2606 reserves ``.invalid``; nothing opens a socket."""
    event_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO event (id, tenant_id, host_org_unit_id, title, normalized_title, "
            "                   on_date, time_zone, time_precision, resolved_date, origin, "
            "                   source_url, fetched_at, extractor_version) "
            "VALUES (:id, :tid, :unit, 'Crawled Career Fair', 'crawled career fair', "
            "        :on_date, :zone, 'date_only', :on_date, 'extraction', "
            "        'https://example.invalid/events/career-fair', now(), 'test-1')"
        ),
        {"id": event_id, "tid": tenant_id, "unit": unit_id, "on_date": ON_DATE, "zone": ZONE},
    )
    return event_id


def _seed(scratch) -> dict[str, uuid.UUID]:
    """One tenant, two units, two accounts, two filed requests and one extracted."""
    tenant_id = uuid.uuid4()
    with scratch.begin() as conn:
        _insert_tenant(conn, tenant_id)
        unit_id = _insert_unit(conn, tenant_id)
        other_unit_id = _insert_unit(conn, tenant_id, suffix="b")
        host_id = _insert_user(conn, tenant_id)
        other_host_id = _insert_user(conn, tenant_id)
        filed = _insert_pre_0036_filed_request(
            conn, tenant_id, unit_id, host_id, "Analytics Careers Panel"
        )
        second = _insert_pre_0036_filed_request(
            conn, tenant_id, unit_id, other_host_id, "Audit Careers Night"
        )
        extracted = _insert_pre_0036_extracted_event(conn, tenant_id, unit_id)
    return {
        "tenant_id": tenant_id,
        "unit_id": unit_id,
        "other_unit_id": other_unit_id,
        "host_id": host_id,
        "other_host_id": other_host_id,
        "filed": filed,
        "second": second,
        "extracted": extracted,
    }


def _organization(
    conn, tenant_id: uuid.UUID, unit_id: uuid.UUID, name: str = "Accounting Society"
) -> uuid.UUID:
    organization_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO host_organization (id, tenant_id, unit_id, name) "
            "VALUES (:id, :tid, :unit, :name)"
        ),
        {"id": organization_id, "tid": tenant_id, "unit": unit_id, "name": name},
    )
    return organization_id


def _member(
    conn,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    granted_by_user_id: uuid.UUID | None = None,
) -> None:
    conn.execute(
        text(
            "INSERT INTO host_organization_member "
            "(organization_id, user_id, tenant_id, unit_id, granted_by_user_id) "
            "VALUES (:oid, :uid, :tid, :unit, :granter)"
        ),
        {
            "oid": organization_id,
            "uid": user_id,
            "tid": tenant_id,
            "unit": unit_id,
            "granter": granted_by_user_id,
        },
    )


# ---------------------------------------------------------------------------
# What the upgrade does to rows that were already there
# ---------------------------------------------------------------------------


def test_a_pre_0036_event_keeps_a_null_organization(engine: Engine):
    """Both filed requests come through with no organization, and none is invented.

    The filed rows are the ones that could have gone either way: each has a
    recorded filer, and a backfill "obvious" enough to be tempting — write the
    filer's organization — was available the moment the tables existed. They
    stay ``NULL``, which is the true statement about a request filed before
    anybody recorded an organization for it.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)

        with connected(url) as scratch:
            seeded = _seed(scratch)

            alembic(url, "head", expect_success=True)

            with scratch.connect() as conn:
                stored = {
                    row.id: row.host_organization_id
                    for row in conn.execute(text("SELECT id, host_organization_id FROM event"))
                }

        assert applied_revision(url) == HEAD_REVISION

    assert stored[seeded["filed"]] is None, (
        "a Speaker Request filed before 0036 was given a host organization. The "
        "revision declines to backfill on purpose: the filer's organization today "
        "is not the organization the request was filed under, and an inferred "
        "affiliation is indistinguishable from a recorded one (ADR-0011 rule 1)."
    )
    assert stored[seeded["second"]] is None
    assert stored[seeded["extracted"]] is None


def test_the_upgrade_writes_no_row_at_all(engine: Engine):
    """Whole-table, so a backfill reaching rows this file did not name still fails.

    Also counts the two new tables: the revision creates them empty, and an
    upgrade that seeded a "default organization" for each unit would be
    inventing an affiliation nobody stated.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)

        with connected(url) as scratch:
            _seed(scratch)

            alembic(url, "head", expect_success=True)

            with scratch.connect() as conn:
                stamped = conn.execute(
                    text("SELECT count(*) FROM event WHERE host_organization_id IS NOT NULL")
                ).scalar_one()
                organizations = conn.execute(
                    text("SELECT count(*) FROM host_organization")
                ).scalar_one()
                members = conn.execute(
                    text("SELECT count(*) FROM host_organization_member")
                ).scalar_one()

    assert (stamped, organizations, members) == (0, 0, 0)


def test_the_upgrade_grants_no_membership_and_no_grant(engine: Engine):
    """An organization is a description, not a permit, and the counts say so.

    ``membership`` and ``resource_grant`` are the two tables
    :mod:`smartmatch_authz` reads. This revision adds a table that *looks* like
    a tenancy boundary — hosts, grouped — and the one failure mode worth a test
    of its own is a future reader treating it as one. It cannot start being one
    by accident: nothing here writes either table, and the day an organization
    should convey reach, that is a deliberate change to a route's predicate.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)

        with connected(url) as scratch:
            _seed(scratch)

            alembic(url, "head", expect_success=True)

            with scratch.connect() as conn:
                memberships = conn.execute(text("SELECT count(*) FROM membership")).scalar_one()
                grants = conn.execute(text("SELECT count(*) FROM resource_grant")).scalar_one()

    assert (memberships, grants) == (0, 0)


# ---------------------------------------------------------------------------
# The downgrade, against a populated database
# ---------------------------------------------------------------------------


def test_the_downgrade_returns_the_pre_0036_state_and_keeps_the_events(engine: Engine):
    """Rolling back drops the new facts and nothing else.

    The stamped request is the interesting row: its ``host_organization_id``
    points at a table the downgrade drops, so a downgrade that removed the
    *event* to satisfy the foreign key would be data loss wearing a rollback's
    clothes. The column goes first, which is why it is not.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)

        with connected(url) as scratch:
            seeded = _seed(scratch)

            alembic(url, "head", expect_success=True)

            with scratch.begin() as conn:
                organization_id = _organization(conn, seeded["tenant_id"], seeded["unit_id"])
                _member(
                    conn,
                    seeded["tenant_id"],
                    seeded["unit_id"],
                    organization_id,
                    seeded["host_id"],
                )
                conn.execute(
                    text(
                        "UPDATE event SET host_organization_id = :oid "
                        "WHERE tenant_id = :tid AND id = :eid"
                    ),
                    {"oid": organization_id, "tid": seeded["tenant_id"], "eid": seeded["filed"]},
                )

            alembic(url, REVISION_BEFORE, expect_success=True, command="downgrade")

            with scratch.connect() as conn:
                surviving = {row.id for row in conn.execute(text("SELECT id FROM event"))}
                columns = {
                    row.column_name
                    for row in conn.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_name = 'event'"
                        )
                    )
                }
                tables = {
                    row.table_name
                    for row in conn.execute(
                        text(
                            "SELECT table_name FROM information_schema.tables "
                            "WHERE table_schema = 'public'"
                        )
                    )
                }
                filer = conn.execute(
                    text("SELECT filed_by_user_id FROM event WHERE id = :eid"),
                    {"eid": seeded["filed"]},
                ).scalar_one()

        assert applied_revision(url) == REVISION_BEFORE

    assert {seeded["filed"], seeded["second"], seeded["extracted"]} <= surviving
    assert "host_organization_id" not in columns
    assert "host_organization" not in tables
    assert "host_organization_member" not in tables
    assert filer == seeded["host_id"], "the downgrade took 0033's recorded filer with it"


def test_the_upgrade_is_repeatable_after_a_downgrade(engine: Engine):
    """Down then up again, with rows present the whole time.

    A migration that only works once against an empty database works in CI and
    nowhere else.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)

        with connected(url) as scratch:
            _seed(scratch)

            alembic(url, "head", expect_success=True)
            alembic(url, REVISION_BEFORE, expect_success=True, command="downgrade")
            alembic(url, "head", expect_success=True)

        assert applied_revision(url) == HEAD_REVISION


# ---------------------------------------------------------------------------
# The constraints, exercised against the populated database
# ---------------------------------------------------------------------------


def test_an_extracted_event_cannot_be_given_an_organization(engine: Engine):
    """``ck_event_host_organization_manual_origin``: a crawl has no affiliation.

    The mirror of ``ck_event_filed_by_manual_origin`` (``0033``). An
    organization on an extracted row would attribute a fetch to a club.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)

        with connected(url) as scratch:
            seeded = _seed(scratch)
            alembic(url, "head", expect_success=True)

            with scratch.begin() as conn:
                organization_id = _organization(conn, seeded["tenant_id"], seeded["unit_id"])

            with pytest.raises(DBAPIError) as raised, scratch.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE event SET host_organization_id = :oid "
                        "WHERE tenant_id = :tid AND id = :eid"
                    ),
                    {
                        "oid": organization_id,
                        "tid": seeded["tenant_id"],
                        "eid": seeded["extracted"],
                    },
                )

    assert "ck_event_host_organization_manual_origin" in str(raised.value)


def test_an_organization_from_another_tenant_is_refused(engine: Engine):
    """The foreign key is composite, so it cannot accept another tenant's row.

    A single-column ``host_organization_id -> host_organization.id`` would pass
    this update: the organization exists, it is simply somebody else's.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)

        with connected(url) as scratch:
            seeded = _seed(scratch)
            other_tenant_id = uuid.uuid4()
            with scratch.begin() as conn:
                _insert_tenant(conn, other_tenant_id)
                other_unit_id = _insert_unit(conn, other_tenant_id)

            alembic(url, "head", expect_success=True)

            with scratch.begin() as conn:
                intruder = _organization(conn, other_tenant_id, other_unit_id)

            with pytest.raises(DBAPIError) as raised, scratch.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE event SET host_organization_id = :oid "
                        "WHERE tenant_id = :tid AND id = :eid"
                    ),
                    {"oid": intruder, "tid": seeded["tenant_id"], "eid": seeded["filed"]},
                )

    assert "foreign key" in str(raised.value).lower()


def test_a_member_from_another_tenant_is_refused(engine: Engine):
    """Same composite rule, one table along."""
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)

        with connected(url) as scratch:
            seeded = _seed(scratch)
            other_tenant_id = uuid.uuid4()
            with scratch.begin() as conn:
                _insert_tenant(conn, other_tenant_id)
                _insert_unit(conn, other_tenant_id)
                intruder = _insert_user(conn, other_tenant_id)

            alembic(url, "head", expect_success=True)

            with scratch.begin() as conn:
                organization_id = _organization(conn, seeded["tenant_id"], seeded["unit_id"])

            with pytest.raises(DBAPIError) as raised, scratch.begin() as conn:
                _member(conn, seeded["tenant_id"], seeded["unit_id"], organization_id, intruder)

    assert "foreign key" in str(raised.value).lower()


def test_a_member_row_cannot_disagree_with_its_organization_about_the_unit(engine: Engine):
    """The three-column key to ``uq_host_organization_tenant_id_unit``.

    Without it the ``unit_id`` on a member row would be a second, unchecked
    opinion about where the organization lives, and every unit-scoped read
    built over it would be reading that opinion rather than the organization.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)

        with connected(url) as scratch:
            seeded = _seed(scratch)
            alembic(url, "head", expect_success=True)

            with scratch.begin() as conn:
                organization_id = _organization(conn, seeded["tenant_id"], seeded["unit_id"])

            with pytest.raises(DBAPIError) as raised, scratch.begin() as conn:
                _member(
                    conn,
                    seeded["tenant_id"],
                    seeded["other_unit_id"],
                    organization_id,
                    seeded["host_id"],
                )

    assert "foreign key" in str(raised.value).lower()


def test_a_host_may_belong_to_only_one_organization(engine: Engine):
    """``uq_host_organization_member_user``.

    This is what makes "the caller's organization" a single answer rather than
    a list, which every route below it depends on.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)

        with connected(url) as scratch:
            seeded = _seed(scratch)
            alembic(url, "head", expect_success=True)

            with scratch.begin() as conn:
                first = _organization(conn, seeded["tenant_id"], seeded["unit_id"])
                second = _organization(
                    conn, seeded["tenant_id"], seeded["other_unit_id"], name="Finance Club"
                )
                _member(conn, seeded["tenant_id"], seeded["unit_id"], first, seeded["host_id"])

            with pytest.raises(DBAPIError) as raised, scratch.begin() as conn:
                _member(
                    conn,
                    seeded["tenant_id"],
                    seeded["other_unit_id"],
                    second,
                    seeded["host_id"],
                )

    assert "uq_host_organization_member_user" in str(raised.value)


def test_two_hosts_cannot_create_the_same_organization_name_in_one_unit(engine: Engine):
    """``uq_host_organization_unit_name`` is case-folded, which is the point.

    A plain ``UNIQUE (tenant_id, unit_id, name)`` would let "Accounting
    Society" and "accounting society" become two organizations, and every
    request filed under either would be half of one club's history.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)

        with connected(url) as scratch:
            seeded = _seed(scratch)
            alembic(url, "head", expect_success=True)

            with scratch.begin() as conn:
                _organization(conn, seeded["tenant_id"], seeded["unit_id"], "Accounting Society")

            with pytest.raises(DBAPIError) as raised, scratch.begin() as conn:
                _organization(conn, seeded["tenant_id"], seeded["unit_id"], "accounting society")

    assert "uq_host_organization_unit_name" in str(raised.value)


def test_the_same_name_in_a_different_unit_is_allowed(engine: Engine):
    """The uniqueness is per unit, not per tenant.

    Two departments can each have their own "Student Advisory Board", and they
    are two organizations because they are two groups of people.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)

        with connected(url) as scratch:
            seeded = _seed(scratch)
            alembic(url, "head", expect_success=True)

            with scratch.begin() as conn:
                _organization(conn, seeded["tenant_id"], seeded["unit_id"], "Advisory Board")
                _organization(conn, seeded["tenant_id"], seeded["other_unit_id"], "Advisory Board")

            with scratch.connect() as conn:
                count = conn.execute(text("SELECT count(*) FROM host_organization")).scalar_one()

    assert count == 2


def test_a_granted_membership_records_its_granter(engine: Engine):
    """``granted_by_user_id`` is nullable but not inert.

    ``NULL`` means self-asserted and is what every row this release writes
    carries. A file proving only that the column accepts ``NULL`` would pass
    against a column nothing could ever fill, so the granted shape is written
    here too — it is the state a coordinator's grant will produce, and the
    distinction between the two is the whole reason the column exists.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)

        with connected(url) as scratch:
            seeded = _seed(scratch)
            alembic(url, "head", expect_success=True)

            with scratch.begin() as conn:
                organization_id = _organization(conn, seeded["tenant_id"], seeded["unit_id"])
                _member(
                    conn,
                    seeded["tenant_id"],
                    seeded["unit_id"],
                    organization_id,
                    seeded["host_id"],
                )
                _member(
                    conn,
                    seeded["tenant_id"],
                    seeded["unit_id"],
                    organization_id,
                    seeded["other_host_id"],
                    granted_by_user_id=seeded["host_id"],
                )

            with scratch.connect() as conn:
                granters = {
                    row.user_id: row.granted_by_user_id
                    for row in conn.execute(
                        text("SELECT user_id, granted_by_user_id FROM host_organization_member")
                    )
                }

    assert granters[seeded["host_id"]] is None
    assert granters[seeded["other_host_id"]] == seeded["host_id"]


def test_a_blank_organization_name_is_refused(engine: Engine):
    """``ck_host_organization_name_shape``: a name nobody typed is not a name."""
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)

        with connected(url) as scratch:
            seeded = _seed(scratch)
            alembic(url, "head", expect_success=True)

            with pytest.raises(DBAPIError) as raised, scratch.begin() as conn:
                _organization(conn, seeded["tenant_id"], seeded["unit_id"], "   ")

    assert "ck_host_organization_name_shape" in str(raised.value)


@pytest.mark.parametrize("column", ["department", "default_location", "logistics_contact"])
def test_a_blank_descriptive_field_is_refused(engine: Engine, column: str):
    """``ck_host_organization_<column>_shape``: whitespace is not an answer.

    All three descriptive columns are nullable on purpose — a host who has not
    said which department they sit in has *not said it*, and NULL carries that.
    A blank string is the one value that reads as an answer while saying
    nothing, which is exactly what each column's constraint exists to refuse.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)

        with connected(url) as scratch:
            seeded = _seed(scratch)
            alembic(url, "head", expect_success=True)

            with pytest.raises(DBAPIError) as raised, scratch.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO host_organization "
                        f"(id, tenant_id, unit_id, name, {column}) "
                        "VALUES (:id, :tid, :unit, 'Accounting Society', '   ')"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "tid": seeded["tenant_id"],
                        "unit": seeded["unit_id"],
                    },
                )

    assert f"ck_host_organization_{column}_shape" in str(raised.value)


def test_a_fully_described_organization_is_stored(engine: Engine):
    """The permitted half for the descriptive columns: real values land.

    The NULL half is already made by every ``_organization`` call above — none
    of them sets a descriptive field — so what remains to prove is that a host
    who *does* answer all three is stored, not refused.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)

        with connected(url) as scratch:
            seeded = _seed(scratch)
            alembic(url, "head", expect_success=True)

            organization_id = uuid.uuid4()
            with scratch.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO host_organization "
                        "(id, tenant_id, unit_id, name, department, "
                        " default_location, logistics_contact) "
                        "VALUES (:id, :tid, :unit, 'Accounting Society', "
                        "        'Finance', 'Wyatt Hall 204', 'Sam — sam@example.edu')"
                    ),
                    {
                        "id": organization_id,
                        "tid": seeded["tenant_id"],
                        "unit": seeded["unit_id"],
                    },
                )

            with scratch.connect() as conn:
                stored = conn.execute(
                    text(
                        "SELECT department, default_location, logistics_contact "
                        "FROM host_organization WHERE id = :id"
                    ),
                    {"id": organization_id},
                ).one()

    assert stored == ("Finance", "Wyatt Hall 204", "Sam — sam@example.edu")
