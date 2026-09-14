#!/usr/bin/env python3
"""Seed one synthetic local-pilot principal into an already-migrated database.

This is deliberately an operator tool, not an API endpoint. A caller cannot
choose a tenant or role through a request: token verification yields only the
stable subject, then the database supplies account and membership facts.

One account may hold more than one role. Since the CBA pivot the Speaker
Connector persona is ``coordinator`` **and** ``admin``, and a connector who
administers is one person with two ``membership`` rows rather than two logins
— so ``seed_pilot`` takes ``additional_roles`` and reconciles the set *upwards
only*: missing rows are added, existing ones are verified, and nothing is ever
deleted. See :func:`_ensure_membership_set`.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from smartmatch_api.config import Settings
from smartmatch_persistence import schema
from smartmatch_persistence.engine import create_db_engine
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

# A dev-only one-shot tool may serialize globally. PostgreSQL releases this
# advisory lock at transaction end, including rollback, so a failed seed cannot
# leave later seed attempts blocked.
SEED_PILOT_ADVISORY_LOCK_KEY = 0x534D50494C4F54


class SeedConflictError(RuntimeError):
    """Existing data disagrees with the requested pilot identity."""


class SeedConfigurationError(RuntimeError):
    """The seed command was invoked outside its explicitly local-pilot scope."""


def require_development_fixture_settings(settings: Settings) -> Settings:
    """Refuse to seed unless validated settings describe the local fixture pilot."""
    if settings.edition.value != "dev" or not settings.use_fixture_providers:
        raise SeedConfigurationError(
            "seed-pilot requires SMARTMATCH_EDITION=dev and SMARTMATCH_USE_FIXTURE_PROVIDERS=true."
        )
    return settings


def acquire_seed_lock(connection: Connection) -> None:
    """Serialize the complete select/insert sequence inside this transaction."""
    connection.execute(
        sa.text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": SEED_PILOT_ADVISORY_LOCK_KEY},
    )


def _existing_or_insert_tenant(
    connection: Connection, *, slug: str, display_name: str
) -> uuid.UUID:
    row = connection.execute(
        sa.select(schema.tenant.c.id, schema.tenant.c.display_name).where(
            schema.tenant.c.slug == slug
        )
    ).one_or_none()
    if row is None:
        tenant_id = uuid.uuid4()
        connection.execute(
            sa.insert(schema.tenant).values(id=tenant_id, slug=slug, display_name=display_name)
        )
        return tenant_id
    if row.display_name != display_name:
        raise SeedConflictError(f"tenant slug {slug!r} exists with a different display name")
    return uuid.UUID(str(row.id))


def _existing_or_insert_unit(
    connection: Connection,
    *,
    tenant_id: uuid.UUID,
    path: str,
    unit_type: str,
    display_name: str,
) -> None:
    row = connection.execute(
        sa.select(schema.org_unit.c.unit_type, schema.org_unit.c.display_name).where(
            schema.org_unit.c.tenant_id == tenant_id,
            schema.org_unit.c.path == path,
        )
    ).one_or_none()
    if row is None:
        connection.execute(
            sa.insert(schema.org_unit).values(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                path=path,
                unit_type=unit_type,
                display_name=display_name,
            )
        )
        return
    if row.unit_type != unit_type or row.display_name != display_name:
        raise SeedConflictError(f"org unit path {path!r} exists with different pilot attributes")


def _existing_or_insert_account(
    connection: Connection, *, tenant_id: uuid.UUID, subject: str, email: str
) -> uuid.UUID:
    row = connection.execute(
        sa.select(
            schema.user_account.c.id,
            schema.user_account.c.tenant_id,
            schema.user_account.c.email,
            schema.user_account.c.suspended,
        ).where(schema.user_account.c.external_subject == subject)
    ).one_or_none()
    if row is None:
        account_id = uuid.uuid4()
        connection.execute(
            sa.insert(schema.user_account).values(
                id=account_id,
                tenant_id=tenant_id,
                external_subject=subject,
                email=email,
            )
        )
        return account_id
    if uuid.UUID(str(row.tenant_id)) != tenant_id:
        raise SeedConflictError(
            f"external subject {subject!r} already belongs to a different tenant; "
            "subjects are global"
        )
    if row.email != email or row.suspended:
        raise SeedConflictError(
            f"external subject {subject!r} exists with different account attributes"
        )
    return uuid.UUID(str(row.id))


def _ensure_membership_set(
    connection: Connection,
    *,
    tenant_id: uuid.UUID,
    account_id: uuid.UUID,
    path: str,
    roles: Sequence[str],
) -> None:
    """Give this account exactly ``roles`` over ``path``, adding only what is missing.

    One account may legitimately hold more than one role: since the CBA pivot
    the Speaker Connector persona is ``coordinator`` **and** ``admin``, and a
    connector who administers is one person with two ``membership`` rows, not
    two logins. The single-role check this replaces refused that outright — it
    treated any second row as a tampered grant — so the seed could create the
    pair on a fresh database and then fail on every re-run against the
    database it had just written.

    Idempotent, and deliberately conservative about which direction it is
    idempotent in:

    * A role in ``roles`` with no row gets one inserted.
    * A role in ``roles`` whose row already matches is left exactly as it is.
    * A row carrying a role **not** in ``roles``, or the right role over a
      different path, or any validity window this seed did not write, is a
      :class:`SeedConflictError`. Those are grants somebody else decided, and
      an operator tool that quietly rewrote them would be the one thing a
      server-assigned role must never be: editable from outside.
    * Nothing is ever deleted. Reconciling *downwards* would mean this tool
      could remove access, and no seed needs that power to do its job.

    Raises:
        SeedConflictError: on any existing row this seed did not ask for.
    """
    requested = sorted(set(roles))
    if not requested:  # pragma: no cover - no caller asks for an empty set
        raise SeedConflictError("a membership set must name at least one role")

    rows = connection.execute(
        sa.select(
            schema.membership.c.granted_path,
            schema.membership.c.role,
            schema.membership.c.valid_from,
            schema.membership.c.valid_until,
        ).where(
            schema.membership.c.tenant_id == tenant_id,
            schema.membership.c.user_id == account_id,
        )
    ).all()

    unexpected = [
        row
        for row in rows
        if row.role not in requested
        or str(row.granted_path) != path
        or row.valid_from is not None
        or row.valid_until is not None
    ]
    if unexpected:
        raise SeedConflictError(
            "external subject already has a different membership "
            f"({sorted((str(row.granted_path), row.role) for row in unexpected)}); "
            f"this seed asks for {requested} over {path!r} and refuses to change "
            "server-assigned roles"
        )

    held = {row.role for row in rows}
    for role in requested:
        if role in held:
            continue
        connection.execute(
            sa.insert(schema.membership).values(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                user_id=account_id,
                granted_path=path,
                role=role,
            )
        )


def _existing_or_insert_membership(
    connection: Connection,
    *,
    tenant_id: uuid.UUID,
    account_id: uuid.UUID,
    path: str,
    role: str,
) -> None:
    """The single-role case of :func:`_ensure_membership_set`."""
    _ensure_membership_set(
        connection, tenant_id=tenant_id, account_id=account_id, path=path, roles=(role,)
    )


def seed_pilot(
    connection: Connection,
    *,
    tenant_slug: str,
    tenant_name: str,
    unit_path: str,
    unit_type: str,
    unit_name: str,
    subject: str,
    email: str,
    role: str,
    additional_roles: Sequence[str] = (),
) -> None:
    """Create the requested identity rows, or verify the exact existing rows.

    The operation is idempotent only for identical requested data. It refuses
    mismatches rather than silently changing a tenant, account, or role.

    Args:
        role: The membership role this identity must hold.
        additional_roles: Further roles the *same* account holds over the same
            path. Empty for every caller but the pilot-login seed, where the
            Speaker Connector persona is ``coordinator`` and ``admin`` at once
            — one person, one account, two ``membership`` rows. Adding a role
            here never removes one; see :func:`_ensure_membership_set`.
    """
    tenant_id = _existing_or_insert_tenant(connection, slug=tenant_slug, display_name=tenant_name)
    _existing_or_insert_unit(
        connection,
        tenant_id=tenant_id,
        path=unit_path,
        unit_type=unit_type,
        display_name=unit_name,
    )
    account_id = _existing_or_insert_account(
        connection, tenant_id=tenant_id, subject=subject, email=email
    )
    _ensure_membership_set(
        connection,
        tenant_id=tenant_id,
        account_id=account_id,
        path=unit_path,
        roles=(role, *additional_roles),
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subject", required=True, help="Stable synthetic external subject")
    parser.add_argument("--email", required=True, help="Synthetic email stored on the account")
    parser.add_argument("--role", required=True, help="Server-assigned membership role")
    parser.add_argument("--tenant-slug", default="pilot", help="Synthetic tenant slug")
    parser.add_argument(
        "--tenant-name", default="Synthetic Pilot", help="Synthetic tenant display name"
    )
    parser.add_argument("--unit-path", default="pilot", help="ltree path receiving the membership")
    parser.add_argument("--unit-type", default="program", help="Org-unit type")
    parser.add_argument("--unit-name", default="Synthetic Pilot Unit", help="Org-unit display name")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        settings = require_development_fixture_settings(Settings())
    except SeedConfigurationError as exc:
        print(f"seed-pilot: configuration error: {exc}", file=sys.stderr)
        return 2

    engine = create_db_engine(settings.database_url)
    try:
        with engine.begin() as connection:
            acquire_seed_lock(connection)
            seed_pilot(
                connection,
                tenant_slug=args.tenant_slug,
                tenant_name=args.tenant_name,
                unit_path=args.unit_path,
                unit_type=args.unit_type,
                unit_name=args.unit_name,
                subject=args.subject,
                email=args.email,
                role=args.role,
            )
    except (SeedConflictError, SeedConfigurationError) as exc:
        print(f"seed-pilot: conflict: {exc}", file=sys.stderr)
        return 2
    except SQLAlchemyError as exc:
        print(
            "seed-pilot: database operation failed; run `make migrate` against the target database "
            "first: "
            f"{exc}",
            file=sys.stderr,
        )
        return 1
    finally:
        engine.dispose()
    print(f"seed-pilot: verified synthetic principal {args.subject!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
