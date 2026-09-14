"""What migration ``0033`` does to ``event`` rows that already exist: nothing.

``0033`` adds ``event.filed_by_user_id`` (OQ-CBA-014, closed 7 September 2026) and
**deliberately does not backfill it**. That is the part of the revision no assertion
against the development database can reach: there, the migration has already run and
the pre-``0033`` rows it would have rewritten are gone. So this file brings a scratch
database to ``0032``, fills it with events the way the previous release would have,
and then runs Alembic for real.

``NULL`` means *unknown filer*, never *no filer*
=================================================
A Speaker Request filed before this revision has no recorded filer, and the column
says so with ``NULL``. Writing the unit's coordinator, or the only volunteer in the
unit, would be a reconstruction indistinguishable from a recorded fact — ADR-0011
rule 1 applied to an identity rather than to a number. The consequence is stated
plainly and is asserted here: **a host cannot list a request they filed before this
migration**, because nothing in the database says they filed it.

What the constraints are for
=============================
* ``ck_event_filed_by_manual_origin`` — an extracted event has no filer, and a filer
  on a crawled row would attribute a fetch to a person. The mirror of
  ``ck_event_provenance_evidence``, which enforces the other direction.
* The composite foreign key ``(tenant_id, filed_by_user_id)`` — every account
  reference in this schema is composite, so a single-column key cannot accept an
  owner from another tenant. Asserted by trying exactly that.

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

#: The revision immediately before the one under test. Read off the ``revision =``
#: line of ``0032_match_run_scoring_mode.py``, not off a filename: Alembic revision
#: ids are not filenames, and this repository carries the standing proof —
#: ``0024_cba_classification_schema.py`` declares ``revision = "0024_cba_classification"``.
REVISION_BEFORE = "0032_match_run_scoring_mode"

#: The revision under test.
REVISION = "0033_event_filed_by"

#: The current head. ``0034_cba_meeting`` chains to :data:`REVISION` and
#: creates the ``cba_meeting`` table; it writes nothing to ``event`` and so
#: cannot invent a filer for a row that had none. The upgrades below run to
#: ``head`` rather than to :data:`REVISION` on purpose — the claim this file
#: makes is that an unrecorded filer stays unrecorded through *every* later
#: revision, not merely through the one that added the column. Extending the
#: chain is therefore a deliberate edit here.
#: Moved again by the manual-events card: ``0035_manual_event_detail`` chains to
#: ``0034_cba_meeting``. It creates the three manual-event side tables and
#: writes nothing to ``event``, so it cannot invent a filer for a row that had
#: none, and the claim below still holds through it.
#: Moved again by PR #154's host-organization card:
#: ``0036_host_organization`` chains to ``0035_manual_event_detail``. It is the
#: first later revision that touches ``event`` at all -- it ADDs the nullable
#: ``host_organization_id`` -- and it is an ADD COLUMN with no server default
#: and no UPDATE, so it writes no value into any existing row and cannot
#: invent a filer either. The claim below still holds through it, and
#: :func:`test_the_upgrade_writes_no_row_at_all` is what proves that rather
#: than this comment.
HEAD_REVISION = "0036_host_organization"

ON_DATE = "2026-10-14"
ZONE = "America/Los_Angeles"


def _insert_tenant(conn, tenant_id: uuid.UUID) -> None:
    conn.execute(
        text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
        {"id": tenant_id, "slug": f"scratch-{tenant_id.hex[:12]}"},
    )


def _insert_unit(conn, tenant_id: uuid.UUID) -> uuid.UUID:
    unit_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
            "VALUES (:id, :tid, CAST(:path AS ltree), 'department', 'Scratch')"
        ),
        {"id": unit_id, "tid": tenant_id, "path": f"scratch{tenant_id.hex[:8]}"},
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


def _insert_pre_0033_filed_request(conn, tenant_id: uuid.UUID, unit_id: uuid.UUID) -> uuid.UUID:
    """A ``coordinator_entry`` event, written the way ``0032`` would have."""
    event_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO event (id, tenant_id, host_org_unit_id, title, normalized_title, "
            "                   on_date, time_zone, time_precision, resolved_date, origin) "
            "VALUES (:id, :tid, :unit, 'Analytics Careers Panel', "
            "        'analytics careers panel', :on_date, :zone, 'date_only', :on_date, "
            "        'coordinator_entry')"
        ),
        {"id": event_id, "tid": tenant_id, "unit": unit_id, "on_date": ON_DATE, "zone": ZONE},
    )
    return event_id


def _insert_pre_0033_extracted_event(conn, tenant_id: uuid.UUID, unit_id: uuid.UUID) -> uuid.UUID:
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


def _seed(scratch) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """One tenant, one unit, one account, one filed event and one extracted one."""
    tenant_id = uuid.uuid4()
    with scratch.begin() as conn:
        _insert_tenant(conn, tenant_id)
        unit_id = _insert_unit(conn, tenant_id)
        user_id = _insert_user(conn, tenant_id)
        filed = _insert_pre_0033_filed_request(conn, tenant_id, unit_id)
        extracted = _insert_pre_0033_extracted_event(conn, tenant_id, unit_id)
    return tenant_id, user_id, filed, extracted


def test_a_pre_0033_event_keeps_a_null_filer(engine: Engine):
    """Both kinds of row come through the upgrade with no filer, and none is invented.

    The ``coordinator_entry`` row is the one that could have gone either way: it has
    a host unit, and that unit has exactly one account, so a backfill "obvious" enough
    to be tempting was available. It stays NULL, which is the true statement about a
    request filed before anybody recorded who filed it.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)

        with connected(url) as scratch:
            _tenant_id, _user_id, filed, extracted = _seed(scratch)

            alembic(url, "head", expect_success=True)

            with scratch.connect() as conn:
                stored = {
                    row.id: row.filed_by_user_id
                    for row in conn.execute(text("SELECT id, filed_by_user_id FROM event"))
                }

        assert applied_revision(url) == HEAD_REVISION

    assert stored[filed] is None, (
        "a Speaker Request filed before 0033 was given a filer. 0033 declines to "
        "backfill on purpose: an inferred filer is indistinguishable from a recorded "
        "one, and a host must not be able to list a request nothing says they filed "
        "(OQ-CBA-014, ADR-0011 rule 1)."
    )
    assert stored[extracted] is None


def test_the_upgrade_writes_no_row_at_all(engine: Engine):
    """Whole-table, so a backfill reaching rows this file did not name still fails."""
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)

        with connected(url) as scratch:
            _seed(scratch)

            alembic(url, "head", expect_success=True)

            with scratch.connect() as conn:
                attributed = conn.execute(
                    text("SELECT count(*) FROM event WHERE filed_by_user_id IS NOT NULL")
                ).scalar_one()

    assert attributed == 0


def test_an_extracted_event_cannot_be_given_a_filer(engine: Engine):
    """``ck_event_filed_by_manual_origin``: a crawl has no author.

    The mirror of ``ck_event_provenance_evidence``. A filer on an extracted row would
    attribute a fetch to a person, which is the same species of untruth as a source
    URL on a row somebody typed.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)

        with connected(url) as scratch:
            tenant_id, user_id, _filed, extracted = _seed(scratch)

            alembic(url, "head", expect_success=True)

            with pytest.raises(DBAPIError) as raised, scratch.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE event SET filed_by_user_id = :uid "
                        "WHERE tenant_id = :tid AND id = :eid"
                    ),
                    {"uid": user_id, "tid": tenant_id, "eid": extracted},
                )

    assert "ck_event_filed_by_manual_origin" in str(raised.value)


def test_a_filer_from_another_tenant_is_refused(engine: Engine):
    """The foreign key is composite, so it cannot accept another tenant's account.

    A single-column ``filed_by_user_id -> user_account.id`` would pass this update:
    the account exists, it is simply somebody else's. Tenant isolation is structural
    in this schema and the key is what makes it so here.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)

        with connected(url) as scratch:
            tenant_id, _user_id, filed, _extracted = _seed(scratch)
            other_tenant_id = uuid.uuid4()
            with scratch.begin() as conn:
                _insert_tenant(conn, other_tenant_id)
                intruder = _insert_user(conn, other_tenant_id)

            alembic(url, "head", expect_success=True)

            with pytest.raises(DBAPIError) as raised, scratch.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE event SET filed_by_user_id = :uid "
                        "WHERE tenant_id = :tid AND id = :eid"
                    ),
                    {"uid": intruder, "tid": tenant_id, "eid": filed},
                )

    assert "foreign key" in str(raised.value).lower()


def test_a_request_filed_after_the_upgrade_can_record_its_filer(engine: Engine):
    """Declining to backfill does not make the column inert.

    A file proving only that the old rows were untouched would pass against a
    migration that added a column nothing can ever write.
    """
    with scratch_database(engine) as url:
        alembic(url, "head", expect_success=True)

        with connected(url) as scratch:
            tenant_id = uuid.uuid4()
            with scratch.begin() as conn:
                _insert_tenant(conn, tenant_id)
                unit_id = _insert_unit(conn, tenant_id)
                user_id = _insert_user(conn, tenant_id)
                conn.execute(
                    text(
                        "INSERT INTO event (id, tenant_id, host_org_unit_id, title, "
                        "                   normalized_title, on_date, time_zone, "
                        "                   time_precision, resolved_date, origin, "
                        "                   filed_by_user_id) "
                        "VALUES (:id, :tid, :unit, 'Filed After', 'filed after', :on_date, "
                        "        :zone, 'date_only', :on_date, 'coordinator_entry', :uid)"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "tid": tenant_id,
                        "unit": unit_id,
                        "on_date": ON_DATE,
                        "zone": ZONE,
                        "uid": user_id,
                    },
                )

            with scratch.connect() as conn:
                attributed = conn.execute(
                    text("SELECT count(*) FROM event WHERE filed_by_user_id = :uid"),
                    {"uid": user_id},
                ).scalar_one()

    assert attributed == 1
