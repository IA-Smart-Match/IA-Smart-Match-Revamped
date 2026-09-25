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

## Two logins, one connector persona

``coordinator`` and ``admin`` are one persona (``role_presentation``) landing
in one shell (``routers/portals.py``), so both connector logins carry **both**
memberships and are the same thing to the product: one account each, two
``membership`` rows each, one identical Connector Dashboard with the
Administration section visible. They remain two accounts with two credentials
because login is keyed on ``user_account.email`` and an account holds one
``pilot_credential`` — so the alternative would be retiring one of the two
addresses the owner already has, which is the owner's call and not this
file's. Until then, either address signs in to the same surface.

Reconciliation is upwards only (``seed_pilot.verify_membership_set``, then
``login_accounts.find_or_add_role``): an account seeded before this change
gains the row it is missing on the next run, without anything existing being
rewritten, and a changed email is still a hard refusal.

## The role is the seed's to assign, never the login's

Each entry below carries a fixed ``role`` — and, for the connector logins, an
``additional_roles`` set — written into ``membership`` rows.
That is the whole shape of the system: an administrator (here, this operator
tool) writes the role; sign-in proves *who*; ``smartmatch_authz`` decides
*what*. Nothing about the role travels through ``POST /v1/auth/login`` in
either direction, and ``LoginRequest`` forbids extra fields so a browser cannot
even attempt it.

## Rerunning it

Idempotent for identical data. The tenant, unit and account go through
``seed_pilot``'s helpers, which refuse to change a tenant, account, or role
that already exists with different values. Every credential write goes
through ``smartmatch_persistence.login_accounts``, the one ``pilot_credential``
writer (B26 T6b-5), under the address lock and the credential row locks:

* A free address: the seed's account gets its roles and its first credential.
* The seed's own login: its roles are checked and added, and its credential is
  *replaced*, which is how a pilot password is rotated: change the variable,
  re-run, and every previously issued session for that account keeps working
  until it expires — revoking those is a separate operator action this pilot
  does not automate, and the decision record names it.
* A login the seed did not create (a Speaker who activated at that address):
  merged **only** as the volunteer entry, and only while that login's active
  roles are a subset of ``{speaker, volunteer}`` (owner ruling R-B). Then the
  volunteer role is added, its password is **never** changed, and stderr says
  the password variable was not applied. Any other entry, or a login holding
  any other active role, is a conflict: the seed never grants staff access to
  a login it did not create, nor adds ``volunteer`` to one that holds it.
* An address held in another organization, or by two logins: a conflict.

``speaker`` rows (``INVITATION_ONLY_ROLES``) are activation's, active or
expired by an unbind; the membership check ignores them, so a Host who became
a Speaker does not fail the next deploy's ``seed-logins`` run.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from seed_pilot import (
    SeedConfigurationError,
    SeedConflictError,
    _existing_or_insert_account,
    _existing_or_insert_tenant,
    _existing_or_insert_unit,
    acquire_seed_lock,
    require_development_fixture_settings,
    verify_membership_set,
)
from smartmatch_api.config import Settings
from smartmatch_domain.pilot_credentials import (
    MINIMUM_PASSWORD_LENGTH,
    derive_password_hash,
    new_salt,
)
from smartmatch_persistence import login_accounts
from smartmatch_persistence.engine import create_db_engine
from smartmatch_persistence.login_accounts import AddressState, NewLogin
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError


@dataclass(frozen=True, slots=True)
class RoleCredential:
    """One pilot role: the variables that configure it and the row it writes.

    Attributes:
        role: The ``membership.role`` this login is granted. Fixed here, so it
            is a property of the seed rather than of anything a caller sends.
        additional_roles: Further roles the same account holds over the same
            path. One account may legitimately hold several — see the module
            docstring on the two connector logins.
        subject: The stable synthetic ``external_subject`` for the account.
        email_var: Environment variable holding the account's address.
        password_var: Environment variable holding the password to store.
    """

    role: str
    subject: str
    email_var: str
    password_var: str
    additional_roles: tuple[str, ...] = ()

    @property
    def roles(self) -> tuple[str, ...]:
        """Every role this login holds, primary first."""
        return (self.role, *self.additional_roles)


#: The four roles the pilot needs a working login for.
#:
#: ``student`` is not optional-in-practice even though every role here is
#: optional-in-configuration: the rewards catalog and redemption routes are
#: gated on ``student`` alone (``routers/rewards.py``), so without this entry
#: no login in the system can demonstrate rewards at all.
ROLE_CREDENTIALS: tuple[RoleCredential, ...] = (
    # The two connector logins are the *same persona* and hold the *same two
    # roles*. See the module docstring: one shell, two QA credentials.
    RoleCredential(
        role="coordinator",
        additional_roles=("admin",),
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
        additional_roles=("coordinator",),
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
    #: The address already signed in as a login this seed did not create; the
    #: volunteer role was added to it and the configured password was not
    #: applied. Reported on stderr (B26 T6b-5 Q4, narrowed by R-B).
    foreign_login: bool = False


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


def _conflict(entry: RoleCredential) -> SeedConflictError:
    """Names the role and the variable, never the other tenant or any account id."""
    return SeedConflictError(
        f"{entry.role}: the address in {entry.email_var} matches a login in another "
        "organization, or more than one login. Fix that before seeding this role."
    )


#: The only entry role R-B lets the seed add to a login it did not create.
_MERGEABLE_ENTRY_ROLE = "volunteer"

#: The only active roles such a login may hold for that merge (R-B). ``speaker``
#: and ``volunteer`` never widen each other: the merge adds ``volunteer`` only.
_MERGEABLE_HOLDER_ROLES: frozenset[str] = frozenset({"speaker", "volunteer"})


def _foreign_conflict(entry: RoleCredential) -> SeedConflictError:
    """Names the role and the variable; never the other login, its roles, or any id."""
    return SeedConflictError(
        f"{entry.role}: the address in {entry.email_var} already signs in as a login "
        "this seed did not create, and this seed will not add this role to it. Use "
        "another address, or change that login's access first."
    )


def _may_merge(entry: RoleCredential, holder_active: frozenset[str]) -> bool:
    """R-B: the volunteer entry only, onto a login holding nothing but speaker/volunteer."""
    return set(entry.roles) == {_MERGEABLE_ENTRY_ROLE} and holder_active <= _MERGEABLE_HOLDER_ROLES


def _roles_text(entry: RoleCredential) -> str:
    return ", ".join(repr(role) for role in entry.roles)


def _seed_one(
    connection: Connection,
    *,
    entry: RoleCredential,
    email: str,
    secret: str,
    tenant_id: uuid.UUID,
    unit_path: str,
    now: datetime,
) -> RoleOutcome:
    """One configured login, inside the caller's seed-locked transaction (plan §3.4).

    Lock order: the seed's advisory lock (held by the caller) → the address
    lock → the address's ``pilot_credential`` rows, then writes — the order
    activation and unbind use (plan §4.5). A foreign holder's active roles are
    read after the row locks and before any write (R-B).
    """
    login_accounts.lock_address(connection, address=email)
    holders = login_accounts.holders_for_address(
        connection, tenant_id=tenant_id, address=email, lock=True
    )
    if holders.state in (AddressState.OTHER_TENANT, AddressState.AMBIGUOUS):
        raise _conflict(entry)

    def grant(role: str, create: NewLogin | None = None) -> None:
        login_accounts.find_or_add_role(
            connection,
            tenant_id=tenant_id,
            email=email,
            role=role,
            path=unit_path,
            now=now,
            create=create,
        )

    holder = holders.holder
    if holder is not None and holder.external_subject != entry.subject:
        # Q4, narrowed by owner ruling R-B: the address already signs in as a
        # login this seed did not create (an activated Speaker, say). Only the
        # volunteer entry merges, and only while that login's active roles are
        # a subset of {speaker, volunteer} — read here, under the address lock
        # and the credential row locks, before any write. Its password is never
        # changed, and no second account is created for the subject.
        holder_active = login_accounts.active_roles(
            connection, tenant_id=tenant_id, user_id=holder.user_id, now=now
        )
        if not _may_merge(entry, holder_active):
            raise _foreign_conflict(entry)
        for role in entry.roles:
            grant(role)
        return RoleOutcome(
            role=entry.role,
            created=True,
            foreign_login=True,
            reason=(
                f"{email} already signs in as another login; roles {_roles_text(entry)} "
                f"added to it; {entry.password_var} was not applied"
            ),
        )

    # The seed's own subject: create it if absent (refusing a changed email or a
    # suspended account, as before), check its membership set, then grant.
    account_id = _existing_or_insert_account(
        connection, tenant_id=tenant_id, subject=entry.subject, email=email
    )
    verify_membership_set(
        connection,
        tenant_id=tenant_id,
        account_id=account_id,
        path=unit_path,
        roles=entry.roles,
    )
    # A fresh salt on every run, so re-seeding the same password twice does
    # not produce the same stored bytes twice.
    stored = derive_password_hash(secret, salt=new_salt())
    if holder is None:
        grant(entry.roles[0], NewLogin(user_id=account_id, password=stored))
        for role in entry.roles[1:]:
            grant(role)
        rotated = ""
    else:
        for role in entry.roles:
            grant(role)
        # Rotation stays the seed's right over its *own* subject only.
        login_accounts.rotate_own_password(
            connection, tenant_id=tenant_id, user_id=account_id, password=stored, now=now
        )
        rotated = "; password rotated"
    return RoleOutcome(
        role=entry.role,
        created=True,
        reason=(
            f"login ready for {email} (roles assigned server-side as {_roles_text(entry)}){rotated}"
        ),
    )


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

    Tenant and unit first (``seed_pilot``'s helpers), then, per address, the
    one credential writer: ``login_accounts`` (B26 T6b-5 R-G). A free address
    gets the seed's account and its first credential; the seed's own login
    gets its roles and a rotated password; a login the seed did not create
    gets the volunteer role and keeps its password, but only from the volunteer
    entry and only while it holds no active role beyond speaker and volunteer
    (Q4, R-B); anything else there, or an address held in another tenant or by
    two logins, is a :class:`SeedConflictError`.

    Raises:
        SeedCredentialError: on a half-configured or unusably short entry.
        SeedConflictError: when existing rows disagree with the requested
            identity.
    """
    outcomes: list[RoleOutcome] = []
    now = datetime.now(UTC)

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
        tenant_id = _existing_or_insert_tenant(
            connection, slug=tenant_slug, display_name=tenant_name
        )
        _existing_or_insert_unit(
            connection,
            tenant_id=tenant_id,
            path=unit_path,
            unit_type=unit_type,
            display_name=unit_name,
        )
        outcomes.append(
            _seed_one(
                connection,
                entry=entry,
                email=email,
                secret=secret,
                tenant_id=tenant_id,
                unit_path=unit_path,
                now=now,
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
        stream = sys.stdout if outcome.created and not outcome.foreign_login else sys.stderr
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
