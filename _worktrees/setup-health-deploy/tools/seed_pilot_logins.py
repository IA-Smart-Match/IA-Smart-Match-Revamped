#!/usr/bin/env python3
"""Seed the four synthetic pilot logins from owner-supplied environment variables.

An operator tool, like :mod:`seed_pilot`, and for the same reason: a caller
cannot obtain a role through a request. This script creates the identity rows
(tenant, org unit, account, **membership**) and one ``pilot_credential`` row
per role, so that ``POST /v1/auth/login`` has something to verify against.

## Where the credentials come from, and where they emphatically do not

From the environment, filled in by the project owner in a gitignored ``.env``:

    SMARTMATCH_PILOT_COORDINATOR_EMAIL / SMARTMATCH_PILOT_COORDINATOR_PASSWORD
    SMARTMATCH_PILOT_STUDENT_EMAIL     / SMARTMATCH_PILOT_STUDENT_PASSWORD
    SMARTMATCH_PILOT_ADMIN_EMAIL       / SMARTMATCH_PILOT_ADMIN_PASSWORD
    SMARTMATCH_PILOT_VOLUNTEER_EMAIL   / SMARTMATCH_PILOT_VOLUNTEER_PASSWORD

There is **no default password anywhere in this file**, no fallback, and no
generated one. A role whose two variables are not both set is *not created*,
and this script says so by name on stderr. That is deliberate and is the one
behaviour most worth protecting here: a seed that invents a password creates an
account whose credential is in the source tree, and a seed that skips silently
leaves an operator wondering why a login they were promised does not work.

Partial configuration — one of the two variables set — is an **error**, not a
skip. It is far more likely to be a typo in a variable name than a decision,
and treating it as a decision would answer a misconfiguration with a shrug.

## The role is the seed's to assign, never the login's

Each entry below carries a fixed ``role`` written into a ``membership`` row.
That is the whole shape of the system: an administrator (here, this operator
tool) writes the role; sign-in proves *who*; ``smartmatch_authz`` decides
*what*. Nothing about the role travels through ``POST /v1/auth/login`` in
either direction, and ``LoginRequest`` forbids extra fields so a browser cannot
even attempt it.

## Rerunning it

Idempotent for identical data. The identity rows go through
:func:`seed_pilot.seed_pilot`, which refuses to change a tenant, account, or
role that already exists with different values. The credential is *replaced*,
which is how a pilot password is rotated: change the variable, re-run, and
every previously issued session for that account keeps working until it
expires — revoking those is a separate operator action this pilot does not
automate, and the decision record names it.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

import sqlalchemy as sa
from seed_pilot import (
    SeedConfigurationError,
    SeedConflictError,
    acquire_seed_lock,
    require_development_fixture_settings,
    seed_pilot,
)
from smartmatch_api.config import Settings
from smartmatch_domain.pilot_credentials import (
    MINIMUM_PASSWORD_LENGTH,
    derive_password_hash,
    new_salt,
)
from smartmatch_persistence import schema
from smartmatch_persistence.engine import create_db_engine
from smartmatch_persistence.pilot_auth import PilotCredentialRepository
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError


@dataclass(frozen=True, slots=True)
class RoleCredential:
    """One pilot role: the variables that configure it and the row it writes.

    Attributes:
        role: The ``membership.role`` this login is granted. Fixed here, so it
            is a property of the seed rather than of anything a caller sends.
        subject: The stable synthetic ``external_subject`` for the account.
        email_var: Environment variable holding the account's address.
        password_var: Environment variable holding the password to store.
    """

    role: str
    subject: str
    email_var: str
    password_var: str


#: The four roles the pilot needs a working login for.
#:
#: ``student`` is not optional-in-practice even though every role here is
#: optional-in-configuration: the rewards catalog and redemption routes are
#: gated on ``student`` alone (``routers/rewards.py``), so without this entry
#: no login in the system can demonstrate rewards at all.
ROLE_CREDENTIALS: tuple[RoleCredential, ...] = (
    RoleCredential(
        role="coordinator",
        subject="pilot-login-coordinator",
        email_var="SMARTMATCH_PILOT_COORDINATOR_EMAIL",
        password_var="SMARTMATCH_PILOT_COORDINATOR_PASSWORD",
    ),
    RoleCredential(
        role="student",
        subject="pilot-login-student",
        email_var="SMARTMATCH_PILOT_STUDENT_EMAIL",
        password_var="SMARTMATCH_PILOT_STUDENT_PASSWORD",
    ),
    RoleCredential(
        role="admin",
        subject="pilot-login-admin",
        email_var="SMARTMATCH_PILOT_ADMIN_EMAIL",
        password_var="SMARTMATCH_PILOT_ADMIN_PASSWORD",
    ),
    RoleCredential(
        role="volunteer",
        subject="pilot-login-volunteer",
        email_var="SMARTMATCH_PILOT_VOLUNTEER_EMAIL",
        password_var="SMARTMATCH_PILOT_VOLUNTEER_PASSWORD",
    ),
)


class SeedCredentialError(RuntimeError):
    """A role was configured incompletely or unusably."""


@dataclass(frozen=True, slots=True)
class RoleOutcome:
    """What happened to one role, for the report this tool prints.

    The password is deliberately absent from this type. The value is read, used
    once, and never carried into anything that is printed, logged, or returned.
    """

    role: str
    created: bool
    reason: str


def _read_role(entry: RoleCredential, environ: dict[str, str]) -> tuple[str, str] | None:
    """The configured ``(email, password)`` for a role, or ``None`` if unconfigured.

    Raises:
        SeedCredentialError: when exactly one of the two variables is set, or
            when the password is shorter than
            :data:`~smartmatch_domain.pilot_credentials.MINIMUM_PASSWORD_LENGTH`.
            Both are refusals to guess at an intention.
    """
    email = (environ.get(entry.email_var) or "").strip()
    secret = environ.get(entry.password_var) or ""

    if not email and not secret:
        return None

    if not email or not secret:
        missing = entry.email_var if not email else entry.password_var
        present = entry.password_var if not email else entry.email_var
        raise SeedCredentialError(
            f"{entry.role}: {present} is set but {missing} is not. Set both or "
            "neither — a half-configured login is far more likely to be a typo "
            "than a decision, and this tool will not guess which."
        )

    if len(secret) < MINIMUM_PASSWORD_LENGTH:
        raise SeedCredentialError(
            f"{entry.role}: {entry.password_var} is shorter than "
            f"{MINIMUM_PASSWORD_LENGTH} characters. Choose a longer one; this "
            "tool will not store a value that short and will not lengthen it "
            "for you."
        )

    return email, secret


def _account_id(connection: Connection, *, subject: str) -> uuid.UUID:
    """The account id for a subject the identity seed has just written."""
    row = connection.execute(
        sa.select(schema.user_account.c.id).where(schema.user_account.c.external_subject == subject)
    ).one()
    return uuid.UUID(str(row.id))


def seed_role_logins(
    connection: Connection,
    *,
    environ: dict[str, str],
    tenant_slug: str,
    tenant_name: str,
    unit_path: str,
    unit_type: str,
    unit_name: str,
) -> list[RoleOutcome]:
    """Create every configured role login. Returns one outcome per role.

    Identity rows first, through :func:`seed_pilot.seed_pilot` — which is what
    writes the ``membership`` row carrying the role — then the credential.
    The order matters: a credential row references an account by composite
    ``(tenant_id, user_id)``, so the account has to exist, and doing it this
    way means the role is written by the same code path the existing
    single-principal seed already uses rather than by a second one that could
    drift from it.

    Raises:
        SeedCredentialError: on a half-configured or unusably short entry.
        SeedConflictError: when existing rows disagree with the requested
            identity (propagated from :func:`seed_pilot.seed_pilot`).
    """
    outcomes: list[RoleOutcome] = []
    repository = PilotCredentialRepository()

    for entry in ROLE_CREDENTIALS:
        configured = _read_role(entry, environ)
        if configured is None:
            outcomes.append(
                RoleOutcome(
                    role=entry.role,
                    created=False,
                    reason=(
                        f"not created — {entry.email_var} and {entry.password_var} "
                        "are unset. No account, no membership, and no password "
                        "were invented for it."
                    ),
                )
            )
            continue

        email, secret = configured

        seed_pilot(
            connection,
            tenant_slug=tenant_slug,
            tenant_name=tenant_name,
            unit_path=unit_path,
            unit_type=unit_type,
            unit_name=unit_name,
            subject=entry.subject,
            email=email,
            role=entry.role,
        )

        tenant_id = connection.execute(
            sa.select(schema.tenant.c.id).where(schema.tenant.c.slug == tenant_slug)
        ).scalar_one()
        user_id = _account_id(connection, subject=entry.subject)

        # A fresh salt on every run, so re-seeding the same password twice does
        # not produce the same stored bytes twice.
        stored = derive_password_hash(secret, salt=new_salt())
        repository.upsert(
            connection,  # type: ignore[arg-type]
            tenant_id=uuid.UUID(str(tenant_id)),
            user_id=user_id,
            password=stored,
        )

        outcomes.append(
            RoleOutcome(
                role=entry.role,
                created=True,
                reason=f"login ready for {email} (role assigned server-side as {entry.role!r})",
            )
        )

    return outcomes


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-slug", default="pilot", help="Synthetic tenant slug")
    parser.add_argument(
        "--tenant-name", default="Synthetic Pilot", help="Synthetic tenant display name"
    )
    parser.add_argument("--unit-path", default="pilot", help="ltree path receiving the membership")
    parser.add_argument("--unit-type", default="program", help="Org-unit type")
    parser.add_argument("--unit-name", default="Synthetic Pilot Unit", help="Org-unit display name")
    parser.add_argument(
        "--require-all",
        action="store_true",
        help=(
            "Exit non-zero unless every role is configured. For the compose "
            "stack and CI, where a partially seeded appliance is a broken one."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        settings = require_development_fixture_settings(Settings())
    except SeedConfigurationError as exc:
        print(f"seed-pilot-logins: configuration error: {exc}", file=sys.stderr)
        return 2

    engine = create_db_engine(settings.database_url)
    try:
        with engine.begin() as connection:
            acquire_seed_lock(connection)
            outcomes = seed_role_logins(
                connection,
                environ=dict(os.environ),
                tenant_slug=args.tenant_slug,
                tenant_name=args.tenant_name,
                unit_path=args.unit_path,
                unit_type=args.unit_type,
                unit_name=args.unit_name,
            )
    except (SeedConflictError, SeedConfigurationError, SeedCredentialError) as exc:
        print(f"seed-pilot-logins: {exc}", file=sys.stderr)
        return 2
    except SQLAlchemyError as exc:
        print(
            "seed-pilot-logins: database operation failed; run `make migrate` against "
            f"the target database first: {exc}",
            file=sys.stderr,
        )
        return 1
    finally:
        engine.dispose()

    for outcome in outcomes:
        stream = sys.stdout if outcome.created else sys.stderr
        print(f"seed-pilot-logins: {outcome.role}: {outcome.reason}", file=stream)

    created = [outcome.role for outcome in outcomes if outcome.created]
    missing = [outcome.role for outcome in outcomes if not outcome.created]

    if not created:
        print(
            "seed-pilot-logins: no role was configured, so no login exists. Set the "
            "SMARTMATCH_PILOT_*_EMAIL / _PASSWORD pairs in .env — see .env.example.",
            file=sys.stderr,
        )
        return 2

    if missing and args.require_all:
        print(
            "seed-pilot-logins: --require-all was given and these roles are "
            f"unconfigured: {', '.join(missing)}.",
            file=sys.stderr,
        )
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
