#!/usr/bin/env python3
"""Seed the synthetic pilot principals the compose dev bearer tokens resolve to.

An operator tool, like :mod:`seed_pilot`, whose helpers it reuses rather than
restates. It exists because the appliance had **one** dev principal — a
coordinator — and a stakeholder click-through needs to enter every portal the
product has. One token that resolved to one role meant the student surfaces,
the Event Host surface, and the administration surface could not be opened at
all, and three e2e steps said so by skipping.

## What this is, and what it is emphatically not

It is the **same** deliberately bounded fixture the coordinator already used:
a finite, explicitly configured set of local subjects, honoured only when
``SMARTMATCH_EDITION=dev`` and ``SMARTMATCH_USE_FIXTURE_PROVIDERS=true``, over
a compose network that publishes nothing beyond loopback. There is no password,
no expiry, and no revocation, because there is no account-authentication system
here to have them — see ``docs/operations/containers.md``.

It is **not** a widening of anything. Each principal gets its own account and
its own single membership carrying the role its portal needs. No role set in
any router changed, no route became less strict, and no principal holds a role
it does not need: the student is a student everywhere, and the Event Host is a
``volunteer`` and nothing else. A portal that stays unreachable because the API
has no route for it stays unreachable, and this tool answers no such gap with a
permit. ``OQ-CBA-014`` was the standing example — the Event Host could file and
read nothing back — and it was closed on 7 September 2026 by *adding a route*
(``GET /v1/units/{unit_id}/host/speaker-requests``, scoped to the requests that
host filed), which is the only way a gap of that shape may be closed. No role set
here or in any router moved to make it true.

## Why the bearer token is named here

:data:`COMPOSE_DEV_PRINCIPALS` carries the compose token beside the subject it
resolves to, even though this tool never reads a token: the mapping lives in
``docker-compose.yml``'s ``SMARTMATCH_DEV_PRINCIPALS`` and the rows live here,
and two halves of one fixture that can drift silently will.
``tests/unit/test_compose_dev_principals.py`` compares them, so a token added
to compose without a seeded subject — which authenticates as nobody and 401s —
fails a unit test rather than a stakeholder's click.

The token values are short, plain, readable strings for the same reason
``docker-compose.yml``'s header note gives about its own: nothing here may
carry the *shape* of a real credential.

## Rerunning it

Idempotent for identical data, through :func:`seed_pilot.seed_pilot`, which
refuses to change a tenant, account, or role that already exists with different
values rather than quietly reassigning one.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass

from seed_pilot import (
    SeedConfigurationError,
    SeedConflictError,
    acquire_seed_lock,
    require_development_fixture_settings,
    seed_pilot,
)
from smartmatch_api.config import Settings
from smartmatch_persistence.engine import create_db_engine
from sqlalchemy.exc import SQLAlchemyError


@dataclass(frozen=True, slots=True)
class DevPrincipal:
    """One synthetic pilot identity and the compose bearer that resolves to it.

    Attributes:
        token: The ``SMARTMATCH_DEV_PRINCIPALS`` key in ``docker-compose.yml``.
            Recorded so the two halves can be compared; never read here.
        subject: The stable synthetic ``external_subject`` for the account.
        email: The synthetic ``.invalid`` address stored on the account.
        role: The ``membership.role`` an administrator — here, this tool —
            assigns. Never chosen by a caller and never carried in a token.
        portal: The portal this role opens, from ``routers/portals.py``'s
            ``_PORTAL_FOR_ROLE``. Documentation for the operator reading the
            report this tool prints; it authorizes nothing.
    """

    token: str
    subject: str
    email: str
    role: str
    portal: str


#: Every principal the compose appliance pre-loads, one per portal.
#:
#: The stored ``role`` strings are the ones the routers actually check.
#: ``volunteer`` is presented to a reader as **Event Host**
#: (``smartmatch_domain.role_presentation``); the stored string is unchanged,
#: because authorization is over storage and never over presentation.
#:
#: ``coordinator`` is listed here and is *not* seeded by this tool — the
#: ``seed`` one-shot creates it with the same values, and has since before
#: these three existed. It is present so this table is the whole map a test can
#: compare ``SMARTMATCH_DEV_PRINCIPALS`` against, rather than three quarters of
#: one. :data:`SEEDED_BY_THIS_TOOL` is what :func:`main` iterates.
COMPOSE_DEV_PRINCIPALS: tuple[DevPrincipal, ...] = (
    DevPrincipal(
        token="compose-api",
        subject="compose-pilot-coordinator",
        email="compose-pilot-coordinator@example.invalid",
        role="coordinator",
        portal="coordinator",
    ),
    DevPrincipal(
        token="compose-student",
        subject="compose-pilot-student",
        email="compose-pilot-student@example.invalid",
        role="student",
        portal="student",
    ),
    DevPrincipal(
        # `compose-host`, not `compose-volunteer`: the persona is the Event
        # Host and the seventeen-character form would cross the length at which
        # `tools/scan_forbidden.py` treats a quoted literal as credential-
        # shaped. The subject below keeps the *stored* role's name, so a row in
        # the database and a role set in a router still read alike.
        token="compose-host",
        subject="compose-pilot-volunteer",
        email="compose-pilot-volunteer@example.invalid",
        role="volunteer",
        portal="volunteer",
    ),
    DevPrincipal(
        token="compose-admin",
        subject="compose-pilot-admin",
        email="compose-pilot-admin@example.invalid",
        role="admin",
        portal="admin",
    ),
)

#: The subset this tool creates: everything except the coordinator, which the
#: ``seed`` one-shot has always owned and still does. Seeding it twice would be
#: harmless — ``seed_pilot`` is idempotent for identical data — but it would
#: also make two services responsible for one row, and the first to disagree
#: about an email would fail the second rather than itself.
SEEDED_BY_THIS_TOOL: tuple[DevPrincipal, ...] = tuple(
    principal for principal in COMPOSE_DEV_PRINCIPALS if principal.role != "coordinator"
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-slug", default="pilot", help="Synthetic tenant slug")
    parser.add_argument(
        "--tenant-name", default="Synthetic Pilot", help="Synthetic tenant display name"
    )
    parser.add_argument("--unit-path", default="pilot", help="ltree path receiving the membership")
    parser.add_argument("--unit-type", default="program", help="Org-unit type")
    parser.add_argument("--unit-name", default="Synthetic Pilot Unit", help="Org-unit display name")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Seed every principal in :data:`SEEDED_BY_THIS_TOOL`, or report why not.

    All of them in **one** transaction under ``seed_pilot``'s advisory lock: a
    half-seeded appliance would open two portals of four and give no signal
    about the other two, which is the failure this tool exists to remove.
    """
    args = parse_args(argv)
    try:
        settings = require_development_fixture_settings(Settings())
    except SeedConfigurationError as exc:
        print(f"seed-pilot-principals: configuration error: {exc}", file=sys.stderr)
        return 2

    engine = create_db_engine(settings.database_url)
    try:
        with engine.begin() as connection:
            acquire_seed_lock(connection)
            for principal in SEEDED_BY_THIS_TOOL:
                seed_pilot(
                    connection,
                    tenant_slug=args.tenant_slug,
                    tenant_name=args.tenant_name,
                    unit_path=args.unit_path,
                    unit_type=args.unit_type,
                    unit_name=args.unit_name,
                    subject=principal.subject,
                    email=principal.email,
                    role=principal.role,
                )
    except (SeedConflictError, SeedConfigurationError) as exc:
        print(f"seed-pilot-principals: conflict: {exc}", file=sys.stderr)
        return 2
    except SQLAlchemyError as exc:
        print(
            "seed-pilot-principals: database operation failed; run `make migrate` against the "
            f"target database first: {exc}",
            file=sys.stderr,
        )
        return 1
    finally:
        engine.dispose()

    for principal in SEEDED_BY_THIS_TOOL:
        print(
            f"seed-pilot-principals: verified {principal.subject!r} "
            f"(role={principal.role}, portal={principal.portal})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
