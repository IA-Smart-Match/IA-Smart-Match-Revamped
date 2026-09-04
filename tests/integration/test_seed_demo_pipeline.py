"""``tools/seed_demo_pipeline.py``, against a real PostgreSQL instance (Card 7).

Proves the two things that make this tool safe to hand an operator:

* it refuses to run anywhere but the dev/fixture appliance, mirroring
  ``tools/seed_pilot.py``'s own guard exactly; and
* it can never exit ``0`` having silently advanced nothing — §1.10's
  standing rule, restated on this tool's own card as a hard requirement.

**A note on how the dev-guard tests are written.** The card brief describes
testing the guard by ``monkeypatch.delenv``-ing ``SMARTMATCH_EDITION`` and
``SMARTMATCH_USE_FIXTURE_PROVIDERS`` and asserting refusal. That does not
hold against this codebase's actual ``Settings``: both fields default to the
permissive values (``edition=dev``, ``use_fixture_providers=True``) when
absent from the environment — confirmed directly by constructing
``Settings()`` with every ``SMARTMATCH_*`` variable removed, which returns
``edition=dev`` and ``use_fixture_providers=True``. Deleting either
variable therefore cannot produce a refusal; it produces the same permissive
default the tool is supposed to accept. What *does* prove the guard is
setting a variable to a value that is not the permissive one, which is what
the two guard tests below do instead, against the exact same
``require_development_fixture_settings`` check — this is the substance the
card's assertions 1 and 2 are after (the tool refuses outside dev/fixture
scope), proved with the mechanism that can actually exercise it.

Requires a live database, and is skipped when none is reachable.
"""

from __future__ import annotations

import inspect
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("sqlalchemy")

from conftest import DATABASE_URL
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from test_pipeline_record_constraints import _insert_pipeline_record, _make_unit

from tools import seed_demo_pipeline

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _clean_demo_pipeline_tables(engine: Engine, tenant_id: uuid.UUID) -> Iterator[None]:
    """Delete this file's rows before ``tenant_id`` tears down its own.

    Ordered child-before-parent, same reasoning as
    ``test_pipeline_record_writers.py``'s own cleanup fixture:
    ``pipeline_record`` cites ``attendance_record``, ``user_account``, and
    ``org_unit``, all ``ON DELETE RESTRICT``, so any row left behind here
    would make ``conftest.py``'s ``tenant_id`` teardown fail.
    ``professional_unit_relationship`` is cleaned too even though this tool
    never writes it — this file shares a tenant with tests that might, and a
    stray row there would fail teardown the same way.
    """
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM pipeline_record WHERE tenant_id = :tid"), {"tid": tenant_id})
        conn.execute(
            text("DELETE FROM attendance_record WHERE tenant_id = :tid"), {"tid": tenant_id}
        )
        conn.execute(
            text("DELETE FROM professional_unit_relationship WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        )
        conn.execute(text("DELETE FROM user_account WHERE tenant_id = :tid"), {"tid": tenant_id})


@pytest.fixture
def tenant_slug(engine: Engine, tenant_id: uuid.UUID) -> str:
    """This test tenant's own ``tenant.slug`` — what ``--tenant-slug`` must name."""
    with engine.begin() as conn:
        return str(
            conn.execute(
                text("SELECT slug FROM tenant WHERE id = :id"), {"id": tenant_id}
            ).scalar_one()
        )


@pytest.fixture
def unit_id(engine: Engine, tenant_id: uuid.UUID) -> uuid.UUID:
    """A unit at the ``"pilot"`` path this file's tests advance journeys in."""
    with engine.begin() as conn:
        return _make_unit(conn, tenant_id, "pilot")


def _dev_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The baseline environment a successful run needs.

    Set explicitly by every test that expects ``main`` to reach the
    database, rather than relied on as an ambient default — see this
    module's own docstring for why relying on the default would make the
    two guard tests below meaningless.
    """
    monkeypatch.setenv("SMARTMATCH_EDITION", "dev")
    monkeypatch.setenv("SMARTMATCH_USE_FIXTURE_PROVIDERS", "true")
    monkeypatch.setenv("SMARTMATCH_DATABASE_URL", DATABASE_URL)


def _args(
    *,
    tenant_slug: str,
    unit_path: str = "pilot",
    through: str = "attended",
    limit: int = 1,
    allow_empty: bool = False,
) -> list[str]:
    argv = [
        "--tenant-slug",
        tenant_slug,
        "--unit-path",
        unit_path,
        "--through",
        through,
        "--limit",
        str(limit),
    ]
    if allow_empty:
        argv.append("--allow-empty")
    return argv


# ---------------------------------------------------------------------------
# Assertions 1 & 2 — dev-only guard.
# ---------------------------------------------------------------------------


def test_refuses_outside_dev_edition(
    monkeypatch: pytest.MonkeyPatch,
    tenant_slug: str,
    unit_id: uuid.UUID,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setenv("SMARTMATCH_EDITION", "staging")
    monkeypatch.setenv("SMARTMATCH_USE_FIXTURE_PROVIDERS", "true")
    monkeypatch.setenv("SMARTMATCH_DATABASE_URL", DATABASE_URL)

    exit_code = seed_demo_pipeline.main(_args(tenant_slug=tenant_slug))

    assert exit_code != 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "dev" in captured.err.lower()


def test_refuses_without_fixture_providers(
    monkeypatch: pytest.MonkeyPatch,
    tenant_slug: str,
    unit_id: uuid.UUID,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setenv("SMARTMATCH_EDITION", "dev")
    monkeypatch.setenv("SMARTMATCH_USE_FIXTURE_PROVIDERS", "false")
    monkeypatch.setenv("SMARTMATCH_DATABASE_URL", DATABASE_URL)

    exit_code = seed_demo_pipeline.main(_args(tenant_slug=tenant_slug))

    assert exit_code != 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "fixture" in captured.err.lower()


# ---------------------------------------------------------------------------
# Assertion 3 — a full walk to Attended, with real attendance evidence.
# ---------------------------------------------------------------------------


def test_through_attended_writes_real_attendance_evidence(
    monkeypatch: pytest.MonkeyPatch,
    engine: Engine,
    tenant_id: uuid.UUID,
    tenant_slug: str,
    unit_id: uuid.UUID,
):
    _dev_env(monkeypatch)
    matched_at = datetime.now(UTC) - timedelta(days=1)
    with engine.begin() as conn:
        record_id = _insert_pipeline_record(
            conn, tenant_id, owning_unit_id=unit_id, times={"matched_at": matched_at}
        )

    exit_code = seed_demo_pipeline.main(_args(tenant_slug=tenant_slug, through="attended"))
    assert exit_code == 0

    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT matched_at, matched_provenance, contacted_at, confirmed_at, "
                "attended_at, member_inquiry_at, attended_attendance_id "
                "FROM pipeline_record WHERE id = :id"
            ),
            {"id": record_id},
        ).one()

    assert row.contacted_at is not None
    assert row.confirmed_at is not None
    assert row.attended_at is not None
    assert row.member_inquiry_at is None
    assert row.matched_at <= row.contacted_at <= row.confirmed_at <= row.attended_at
    # Assertion 11 — the walk never rewrites the provenance an earlier writer set.
    assert row.matched_provenance == "synthetic / coordinator-accepted"

    assert row.attended_attendance_id is not None
    with engine.begin() as conn:
        attendance = conn.execute(
            text("SELECT method, tenant_id, subject_id FROM attendance_record WHERE id = :id"),
            {"id": row.attended_attendance_id},
        ).one()
    assert attendance.method == "coordinator_entry"
    assert attendance.tenant_id == tenant_id


# ---------------------------------------------------------------------------
# Assertion 4 — re-running the same command is idempotent.
# ---------------------------------------------------------------------------


def test_rerun_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    engine: Engine,
    tenant_id: uuid.UUID,
    tenant_slug: str,
    unit_id: uuid.UUID,
):
    _dev_env(monkeypatch)
    matched_at = datetime.now(UTC) - timedelta(days=1)
    with engine.begin() as conn:
        record_id = _insert_pipeline_record(
            conn, tenant_id, owning_unit_id=unit_id, times={"matched_at": matched_at}
        )

    assert seed_demo_pipeline.main(_args(tenant_slug=tenant_slug, through="attended")) == 0

    with engine.begin() as conn:
        first = conn.execute(
            text(
                "SELECT contacted_at, confirmed_at, attended_at, attended_attendance_id "
                "FROM pipeline_record WHERE id = :id"
            ),
            {"id": record_id},
        ).one()

    # Second run: the tool advances zero *new* stages (everything through
    # Attended was already reached), so without --allow-empty it must fail
    # loudly per §1.10 — that is proven separately below. Here it is run
    # with --allow-empty so the idempotency of the stored data can be
    # checked without the exit code getting in the way.
    exit_code = seed_demo_pipeline.main(
        _args(tenant_slug=tenant_slug, through="attended", allow_empty=True)
    )
    assert exit_code == 0

    with engine.begin() as conn:
        second = conn.execute(
            text(
                "SELECT contacted_at, confirmed_at, attended_at, attended_attendance_id "
                "FROM pipeline_record WHERE id = :id"
            ),
            {"id": record_id},
        ).one()
        attendance_count = conn.execute(
            text(
                "SELECT count(*) FROM attendance_record WHERE tenant_id = :tid "
                "AND subject_id = (SELECT subject_id FROM pipeline_record WHERE id = :id)"
            ),
            {"tid": tenant_id, "id": record_id},
        ).scalar_one()

    assert second.contacted_at == first.contacted_at
    assert second.confirmed_at == first.confirmed_at
    assert second.attended_at == first.attended_at
    assert second.attended_attendance_id == first.attended_attendance_id
    assert attendance_count == 1


def test_rerun_without_allow_empty_fails_loudly_once_fully_advanced(
    monkeypatch: pytest.MonkeyPatch,
    engine: Engine,
    tenant_id: uuid.UUID,
    tenant_slug: str,
    unit_id: uuid.UUID,
):
    """§1.10 also covers "found rows, but nothing left to advance" — not only "found none"."""
    _dev_env(monkeypatch)
    matched_at = datetime.now(UTC) - timedelta(days=1)
    with engine.begin() as conn:
        _insert_pipeline_record(
            conn, tenant_id, owning_unit_id=unit_id, times={"matched_at": matched_at}
        )

    assert seed_demo_pipeline.main(_args(tenant_slug=tenant_slug, through="attended")) == 0

    exit_code = seed_demo_pipeline.main(_args(tenant_slug=tenant_slug, through="attended"))
    assert exit_code != 0


# ---------------------------------------------------------------------------
# Assertion 5 — --through contacted sets only contacted_at.
# ---------------------------------------------------------------------------


def test_through_contacted_sets_only_contacted(
    monkeypatch: pytest.MonkeyPatch,
    engine: Engine,
    tenant_id: uuid.UUID,
    tenant_slug: str,
    unit_id: uuid.UUID,
):
    _dev_env(monkeypatch)
    matched_at = datetime.now(UTC) - timedelta(days=1)
    with engine.begin() as conn:
        record_id = _insert_pipeline_record(
            conn, tenant_id, owning_unit_id=unit_id, times={"matched_at": matched_at}
        )

    exit_code = seed_demo_pipeline.main(_args(tenant_slug=tenant_slug, through="contacted"))
    assert exit_code == 0

    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT contacted_at, confirmed_at, attended_at, member_inquiry_at "
                "FROM pipeline_record WHERE id = :id"
            ),
            {"id": record_id},
        ).one()

    assert row.contacted_at is not None
    assert row.confirmed_at is None
    assert row.attended_at is None
    assert row.member_inquiry_at is None


# ---------------------------------------------------------------------------
# Assertion 6 — --limit picks the earliest rows by (matched_at, id).
# ---------------------------------------------------------------------------


def test_limit_selects_earliest_by_matched_at_then_id(
    monkeypatch: pytest.MonkeyPatch,
    engine: Engine,
    tenant_id: uuid.UUID,
    tenant_slug: str,
    unit_id: uuid.UUID,
    capsys: pytest.CaptureFixture[str],
):
    _dev_env(monkeypatch)
    base = datetime.now(UTC) - timedelta(days=3)
    with engine.begin() as conn:
        earliest = _insert_pipeline_record(
            conn, tenant_id, owning_unit_id=unit_id, times={"matched_at": base}
        )
        middle = _insert_pipeline_record(
            conn,
            tenant_id,
            owning_unit_id=unit_id,
            times={"matched_at": base + timedelta(hours=1)},
        )
        latest = _insert_pipeline_record(
            conn,
            tenant_id,
            owning_unit_id=unit_id,
            times={"matched_at": base + timedelta(hours=2)},
        )

    exit_code = seed_demo_pipeline.main(
        _args(tenant_slug=tenant_slug, through="contacted", limit=2)
    )
    assert exit_code == 0

    with engine.begin() as conn:
        rows = {
            row.id: row.contacted_at is not None
            for row in conn.execute(
                text("SELECT id, contacted_at FROM pipeline_record WHERE tenant_id = :tid"),
                {"tid": tenant_id},
            )
        }

    assert rows[earliest] is True
    assert rows[middle] is True
    assert rows[latest] is False

    captured = capsys.readouterr()
    assert "advanced 2 journey(s)" in captured.out


# ---------------------------------------------------------------------------
# Assertions 7 & 8 — zero fails loudly, --allow-empty downgrades it, and the
# count is always on stdout.
# ---------------------------------------------------------------------------


def test_zero_rows_fails_loudly_and_names_the_unit(
    monkeypatch: pytest.MonkeyPatch,
    tenant_slug: str,
    unit_id: uuid.UUID,
    capsys: pytest.CaptureFixture[str],
):
    _dev_env(monkeypatch)

    exit_code = seed_demo_pipeline.main(_args(tenant_slug=tenant_slug))

    assert exit_code != 0
    captured = capsys.readouterr()
    # Assertion 8 — the count is always on stdout, even in the failing case.
    assert "advanced 0 journey(s)" in captured.out
    assert "'pilot'" in captured.err
    assert "--allow-empty" in captured.err


def test_zero_rows_with_allow_empty_exits_zero_but_still_warns(
    monkeypatch: pytest.MonkeyPatch,
    tenant_slug: str,
    unit_id: uuid.UUID,
    capsys: pytest.CaptureFixture[str],
):
    _dev_env(monkeypatch)

    exit_code = seed_demo_pipeline.main(_args(tenant_slug=tenant_slug, allow_empty=True))

    assert exit_code == 0
    captured = capsys.readouterr()
    # Assertion 8 — the count is always on stdout, unchanged by --allow-empty.
    assert "advanced 0 journey(s)" in captured.out
    assert "'pilot'" in captured.err
    assert "--allow-empty" in captured.err


# ---------------------------------------------------------------------------
# Assertion 9 — never the scanning attendance method, and no such literal in
# this tool's own source.
# ---------------------------------------------------------------------------


def test_attendance_method_is_never_the_scanning_value(
    monkeypatch: pytest.MonkeyPatch,
    engine: Engine,
    tenant_id: uuid.UUID,
    tenant_slug: str,
    unit_id: uuid.UUID,
):
    _dev_env(monkeypatch)
    matched_at = datetime.now(UTC) - timedelta(days=1)
    with engine.begin() as conn:
        _insert_pipeline_record(
            conn, tenant_id, owning_unit_id=unit_id, times={"matched_at": matched_at}
        )

    assert seed_demo_pipeline.main(_args(tenant_slug=tenant_slug, through="attended")) == 0

    with engine.begin() as conn:
        methods = [
            row.method
            for row in conn.execute(
                text("SELECT method FROM attendance_record WHERE tenant_id = :tid"),
                {"tid": tenant_id},
            )
        ]
    assert methods, "the walk should have written one attendance_record row"
    scanning_method = "qr" + "_scan"  # built at runtime, not a literal in this test file either
    assert all(method != scanning_method for method in methods)
    assert all(method == "coordinator_entry" for method in methods)


def test_tool_source_never_names_the_scanning_method():
    source = inspect.getsource(seed_demo_pipeline)
    scanning_method = "qr" + "_scan"
    assert scanning_method not in source


# ---------------------------------------------------------------------------
# Assertion 10 — the Attended-stage evidence CHECK is still enforced.
# ---------------------------------------------------------------------------


def test_attendance_evidence_check_constraint_still_enforced(
    engine: Engine, tenant_id: uuid.UUID, unit_id: uuid.UUID
):
    with engine.begin() as conn:
        record_id = _insert_pipeline_record(
            conn, tenant_id, reached="attended_at", owning_unit_id=unit_id
        )

    with (
        pytest.raises(IntegrityError, match="ck_pipeline_record_attendance_evidence"),
        engine.begin() as conn,
    ):
        conn.execute(
            text(
                "UPDATE pipeline_record SET attended_attendance_id = NULL "
                "WHERE id = :id AND attended_at IS NOT NULL"
            ),
            {"id": record_id},
        )


# ---------------------------------------------------------------------------
# Assertion 12 — no fabricated-fitness identifiers anywhere in this tool.
# ---------------------------------------------------------------------------


def test_tool_source_has_no_fabricated_fitness_identifiers():
    source = inspect.getsource(seed_demo_pipeline).lower()
    forbidden = ("sco" + "re", "confidence", "match_" + "score", "ra" + "nk", "wei" + "ght")
    for word in forbidden:
        assert word not in source, word
