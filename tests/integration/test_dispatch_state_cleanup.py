"""What ``conftest._clean_dispatch_state`` does with an *abandoned* chain.

The sweep that runs before every integration test deletes ``match_run``
globally, and ``cba_invitation_batch`` holds an ``ON DELETE RESTRICT`` foreign
key to it (migration ``0029``). A run that was killed between writing a batch
and its tenant teardown therefore leaves a row that makes ``DELETE FROM
match_run`` fail -- in *every* test, forever, with a ``ForeignKeyViolation``
naming ``cba_invitation_batch_tenant_id_match_run_id_fkey`` rather than the row
that is actually in the way. On this project being killed mid-run is the
ordinary case, so this is a wedge that arrives on its own.

Two things are proven here, and they are deliberately in tension:

* An abandoned chain **under a tenant this suite created** is cleaned, and the
  sweep completes. That is the wedge, gone.
* An identical chain **under a tenant this suite did not create** -- the
  ``pilot`` tenant a dev database carries, say -- is *not* touched. The sweep
  refuses, loudly, naming the batch and its tenant. Refusing is the point: the
  alternative to a clear failure here is a ``DELETE`` that quietly removes
  somebody's real data to make a test pass.

Requires a live database, and is skipped when none is reachable.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import pytest

pytest.importorskip("sqlalchemy")

from conftest import (
    TEST_TENANT_SLUG_PREFIX,
    ForeignInvitationBatchError,
    clear_dispatch_state,
)
from sqlalchemy import Engine, text

pytestmark = pytest.mark.integration


@dataclass(frozen=True, slots=True)
class _Chain:
    """The rows one killed run leaves behind, in the order they cite each other."""

    tenant_id: uuid.UUID
    slug: str
    unit_id: uuid.UUID
    user_id: uuid.UUID
    job_id: uuid.UUID
    match_run_id: uuid.UUID
    batch_id: uuid.UUID
    invitation_id: uuid.UUID


def _plant_abandoned_chain(engine: Engine, slug: str) -> _Chain:
    """Write a complete invitation chain and leave it there, as a killed run would.

    Nothing here goes through the ``tenant_id`` fixture: the whole point is a
    tenant that no *live* fixture owns, which is what an abandoned chain is.
    """
    chain = _Chain(
        tenant_id=uuid.uuid4(),
        slug=slug,
        unit_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        match_run_id=uuid.uuid4(),
        batch_id=uuid.uuid4(),
        invitation_id=uuid.uuid4(),
    )
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": chain.tenant_id, "slug": chain.slug},
        )
        conn.execute(
            text(
                "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                "VALUES (:id, :tid, CAST(:path AS ltree), 'department', 'Abandoned Unit')"
            ),
            {
                "id": chain.unit_id,
                "tid": chain.tenant_id,
                "path": f"abandoned.{chain.unit_id.hex[:8]}",
            },
        )
        conn.execute(
            text(
                "INSERT INTO user_account (id, tenant_id, external_subject, email) "
                "VALUES (:id, :tid, :sub, :email)"
            ),
            {
                "id": chain.user_id,
                "tid": chain.tenant_id,
                "sub": f"abandoned-{chain.user_id.hex}",
                "email": f"{chain.user_id.hex[:8]}@example.edu",
            },
        )
        conn.execute(
            text(
                "INSERT INTO job (id, tenant_id, owning_unit_id, command_type, status, "
                "actor_id, payload) "
                "VALUES (:id, :tid, :unit, 'matching.run', 'succeeded', :actor, "
                "CAST('{}' AS jsonb))"
            ),
            {
                "id": chain.job_id,
                "tid": chain.tenant_id,
                "unit": chain.unit_id,
                "actor": chain.user_id,
            },
        )
        conn.execute(
            text(
                "INSERT INTO match_run (id, tenant_id, owning_unit_id, job_id, event_need_id, "
                "inputs_hash, portfolio_size, random_seed, registry_version, registry_hash, "
                "weights, optimizer_model_version, solver_name, solver_version, "
                "route_estimate_source, route_estimate_version, portfolio_status) "
                "VALUES (:id, :tid, :unit, :job, 'need-abandoned', 'hash-abandoned', 1, 0, "
                "'v1', 'registry-abandoned', CAST('{\"fit\": 1}' AS jsonb), 'model-v1', "
                "'cbc', '2.10', 'straight_line', 'v1', 'optimal')"
            ),
            {
                "id": chain.match_run_id,
                "tid": chain.tenant_id,
                "unit": chain.unit_id,
                "job": chain.job_id,
            },
        )
        conn.execute(
            text(
                "INSERT INTO cba_invitation_batch (id, tenant_id, owning_unit_id, match_run_id, "
                "idempotency_key, template_id, event_name, event_date, created_by_user_id) "
                "VALUES (:id, :tid, :unit, :run, :key, 'speaker_invite_v1', "
                "'Abandoned Career Panel', '14 September 2026', :actor)"
            ),
            {
                "id": chain.batch_id,
                "tid": chain.tenant_id,
                "unit": chain.unit_id,
                "run": chain.match_run_id,
                "key": f"abandoned-{chain.batch_id.hex}",
                "actor": chain.user_id,
            },
        )
        conn.execute(
            text(
                "INSERT INTO cba_invitation (id, tenant_id, owning_unit_id, batch_id, "
                "professional_id, status, skip_reason, response_status) "
                "VALUES (:id, :tid, :unit, :batch, :pro, 'skipped', 'not_on_roster', "
                "'awaiting_response')"
            ),
            {
                "id": chain.invitation_id,
                "tid": chain.tenant_id,
                "unit": chain.unit_id,
                "batch": chain.batch_id,
                "pro": uuid.uuid4(),
            },
        )
    return chain


def _remove_chain(engine: Engine, chain: _Chain) -> None:
    """Delete whatever of a planted chain is still there, children first."""
    with engine.begin() as conn:
        for statement in (
            "DELETE FROM cba_invitation WHERE tenant_id = :tid",
            "DELETE FROM cba_invitation_batch WHERE tenant_id = :tid",
            "DELETE FROM match_run WHERE tenant_id = :tid",
            "DELETE FROM job WHERE tenant_id = :tid",
            "DELETE FROM user_account WHERE tenant_id = :tid",
            "DELETE FROM org_unit WHERE tenant_id = :tid",
            "DELETE FROM tenant WHERE id = :tid",
        ):
            conn.execute(text(statement), {"tid": chain.tenant_id})


@pytest.fixture
def abandoned_test_chain(engine: Engine) -> Iterator[_Chain]:
    """An abandoned chain under a slug the ``tenant_id`` fixture would have made."""
    chain = _plant_abandoned_chain(engine, f"{TEST_TENANT_SLUG_PREFIX}{uuid.uuid4().hex[:12]}")
    try:
        yield chain
    finally:
        _remove_chain(engine, chain)


@pytest.fixture
def foreign_chain(engine: Engine) -> Iterator[_Chain]:
    """The same chain under a tenant this suite did not create.

    ``pilot-`` rather than ``test-``: ``scripts/seed_pilot`` writes a ``pilot``
    tenant into a dev database, and it is exactly the tenant whose rows a global
    sweep would destroy.
    """
    chain = _plant_abandoned_chain(engine, f"pilot-{uuid.uuid4().hex[:12]}")
    try:
        yield chain
    finally:
        _remove_chain(engine, chain)


def _batch_exists(engine: Engine, chain: _Chain) -> bool:
    with engine.connect() as conn:
        return (
            conn.execute(
                text("SELECT count(*) FROM cba_invitation_batch WHERE id = :bid"),
                {"bid": chain.batch_id},
            ).scalar_one()
            == 1
        )


def _match_run_exists(engine: Engine, chain: _Chain) -> bool:
    with engine.connect() as conn:
        return (
            conn.execute(
                text("SELECT count(*) FROM match_run WHERE id = :rid"),
                {"rid": chain.match_run_id},
            ).scalar_one()
            == 1
        )


def test_abandoned_test_chain_does_not_wedge_the_sweep(
    engine: Engine, abandoned_test_chain: _Chain
) -> None:
    """The wedge: before the fix this raised ``ForeignKeyViolation``, in every test."""
    clear_dispatch_state(engine)

    assert not _batch_exists(engine, abandoned_test_chain)
    assert not _match_run_exists(engine, abandoned_test_chain)


def test_abandoned_test_chain_leaves_its_tenant_and_identity_rows(
    engine: Engine, abandoned_test_chain: _Chain
) -> None:
    """The sweep clears coordination rows, not the identity rows it does not own.

    ``conftest`` is explicit that tenants and their identity rows belong to the
    fixtures that create them; widening the batch cleanup must not quietly widen
    that too.
    """
    clear_dispatch_state(engine)

    with engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM tenant WHERE id = :tid"),
                {"tid": abandoned_test_chain.tenant_id},
            ).scalar_one()
            == 1
        )
        assert (
            conn.execute(
                text("SELECT count(*) FROM user_account WHERE id = :uid"),
                {"uid": abandoned_test_chain.user_id},
            ).scalar_one()
            == 1
        )


def test_foreign_chain_survives_and_is_named(engine: Engine, foreign_chain: _Chain) -> None:
    """A batch under a tenant the suite did not create is reported, never deleted.

    The message has to carry what an operator needs to act: the table, the batch
    id, and the slug of the tenant it belongs to. An opaque ``ForeignKeyViolation``
    naming only the constraint is what this replaces.
    """
    with pytest.raises(ForeignInvitationBatchError) as excinfo:
        clear_dispatch_state(engine)

    message = str(excinfo.value)
    assert "cba_invitation_batch" in message
    assert str(foreign_chain.batch_id) in message
    assert foreign_chain.slug in message

    assert _batch_exists(engine, foreign_chain)
    assert _match_run_exists(engine, foreign_chain)
    with engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM job WHERE id = :jid"),
                {"jid": foreign_chain.job_id},
            ).scalar_one()
            == 1
        )
