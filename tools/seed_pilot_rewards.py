#!/usr/bin/env python3
"""Seed one funded ``reward_item`` from values the operator types on the line.

An operator tool, like :mod:`seed_pilot`, :mod:`seed_pilot_logins`, and
:mod:`seed_pilot_principals`, whose settings gate and advisory lock it reuses.
It exists because `RewardsRepository` gained a catalog writer
(:meth:`smartmatch_persistence.rewards.RewardsRepository.create_item`) on 7
September 2026, authorized beside the D6 record rather than by editing it —
see ``docs/plans/open-questions/cba-phase-deferred.md``, "Decision taken 2026-
09-07".

## Why every value is a required argument, with no default anywhere

``docs/pilot-data/rewards-catalog-worksheet.md`` says the empty cells in its
catalog table "are intentional — engineering must not invent owners, funding,
or point costs." This tool honours that rule by construction rather than by
convention: ``--name``, ``--points-cost``, ``--fulfilment-cost``,
``--budget-owner-subject``, and ``--funded``/``--unfunded`` are all required,
and ``argparse`` exits non-zero if any is omitted. There is no default reward,
no default cost, and no default owner anywhere in this file. The worksheet is
where the owner writes a row; this tool is what turns that row into a database
row, and cannot run without one.

``--budget-owner-subject`` takes a ``user_account.external_subject`` — not a
name and not an id. D6 names Danny Tran as the pilot's budget owner
(``docs/decisions/d6-rewards-budget-decision-record.md``), and this tool still
does not hard-code that subject: a name in a decision record is not a
``user_account`` row, and the seeded pilot's synthetic subjects are not fixed
in advance the way the four login roles are.

## What this tool is not

It is not a route, and it does not open one. Nothing here decides who may
*read* or *redeem* a catalog item — D6 §5 leaves "read/redemption roles"
undecided, and a seed tool needs no role set because seeding is an operator's
act, not a request a caller made. See
:mod:`smartmatch_persistence.rewards`'s module docstring for the same point
made from the persistence side.

It does not promote D7. D7's calibration property
(``points_cost <= CALIBRATION_N_TENTATIVE * POINTS_PER_VERIFIED_ATTENDANCE``)
is printed as a **report line**, on both success and idempotent-repeat, never
as a refusal — D7 is tentative, and an operator may deliberately seed a
stretch reward priced above it.

## Rerunning it

Idempotent on ``(tenant, name)``, like every seed tool in this file's family:
an existing item with identical ``points_cost``, ``fulfilment_cost``,
``budget_owner_id``, and ``funded`` is a no-op report; one with any different
value is a :class:`SeedConflictError`, exactly the rule
:func:`seed_pilot.seed_pilot` already applies to identity rows.
"""

from __future__ import annotations

import argparse
import decimal
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
)
from smartmatch_api.config import Settings
from smartmatch_domain.rewards import CALIBRATION_N_TENTATIVE, POINTS_PER_VERIFIED_ATTENDANCE
from smartmatch_persistence import schema
from smartmatch_persistence.engine import create_db_engine
from smartmatch_persistence.rewards import RewardsRepository, UnknownBudgetOwnerError
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError


class UnknownTenantError(RuntimeError):
    """The requested tenant slug has no ``tenant`` row.

    Refused rather than creating one: this tool seeds a reward item into an
    already-seeded pilot appliance, the way ``seed_pilot_logins`` and
    ``seed_pilot_principals`` do — it does not stand up a tenant, unit, or
    account of its own.
    """


class UnknownBudgetOwnerSubjectError(RuntimeError):
    """``--budget-owner-subject`` names no ``user_account`` row anywhere.

    Distinct from :class:`~smartmatch_persistence.rewards.UnknownBudgetOwnerError`,
    which the repository raises when a *resolved* id is not in the tenant. This
    error is raised earlier, when the subject itself does not resolve to any
    account at all — a more specific message for the more common typo.
    """


@dataclass(frozen=True, slots=True)
class SeedRewardOutcome:
    """What happened, for the report this tool prints.

    Attributes:
        created: ``True`` for a new row, ``False`` for a verified identical
            repeat.
        item_id: The ``reward_item.id``, new or existing.
        satisfies_calibration: Whether ``points_cost`` clears D7's tentative
            property. A report fact, never a refusal.
    """

    created: bool
    item_id: uuid.UUID
    satisfies_calibration: bool


def _tenant_id(connection: Connection, *, tenant_slug: str) -> uuid.UUID:
    row = connection.execute(
        sa.select(schema.tenant.c.id).where(schema.tenant.c.slug == tenant_slug)
    ).one_or_none()
    if row is None:
        raise UnknownTenantError(
            f"no tenant with slug {tenant_slug!r}; run `make seed-pilot` (or "
            "`make seed-pilot-principals`) first"
        )
    return uuid.UUID(str(row.id))


def _budget_owner_id(
    connection: Connection, *, tenant_id: uuid.UUID, subject: str
) -> uuid.UUID:
    row = connection.execute(
        sa.select(schema.user_account.c.id, schema.user_account.c.tenant_id).where(
            schema.user_account.c.external_subject == subject
        )
    ).one_or_none()
    if row is None:
        raise UnknownBudgetOwnerSubjectError(
            f"no user_account with external_subject {subject!r}; the budget owner must "
            "already have a seeded login (make seed-pilot-logins / seed-pilot-principals)"
        )
    if uuid.UUID(str(row.tenant_id)) != tenant_id:
        raise UnknownBudgetOwnerSubjectError(
            f"external subject {subject!r} exists but not in tenant {tenant_id}"
        )
    return uuid.UUID(str(row.id))


def seed_reward_item(
    connection: Connection,
    *,
    tenant_slug: str,
    name: str,
    points_cost: int,
    fulfilment_cost: decimal.Decimal,
    budget_owner_subject: str,
    funded: bool,
) -> SeedRewardOutcome:
    """Write the requested item, or verify an identical existing one.

    Raises:
        UnknownTenantError: ``tenant_slug`` has no row.
        UnknownBudgetOwnerSubjectError: the subject resolves to no account, or
            to one in a different tenant.
        UnknownBudgetOwnerError: propagated from
            :meth:`RewardsRepository.create_item` for the (unreachable in
            practice, given the check above) case of a resolved id that the
            repository's own tenant check still refuses.
        SeedConflictError: an item with this ``(tenant, name)`` exists with a
            different ``points_cost``, ``fulfilment_cost``, ``budget_owner_id``,
            or ``funded``.
    """
    tenant_id = _tenant_id(connection, tenant_slug=tenant_slug)
    budget_owner_id = _budget_owner_id(connection, tenant_id=tenant_id, subject=budget_owner_subject)

    existing = connection.execute(
        sa.select(
            schema.reward_item.c.id,
            schema.reward_item.c.points_cost,
            schema.reward_item.c.fulfilment_cost,
            schema.reward_item.c.budget_owner_id,
            schema.reward_item.c.funded,
        ).where(
            schema.reward_item.c.tenant_id == tenant_id,
            schema.reward_item.c.name == name,
        )
    ).one_or_none()

    if existing is not None:
        if (
            int(existing.points_cost) != points_cost
            or decimal.Decimal(existing.fulfilment_cost) != fulfilment_cost
            or uuid.UUID(str(existing.budget_owner_id)) != budget_owner_id
            or bool(existing.funded) != funded
        ):
            raise SeedConflictError(
                f"reward_item {name!r} already exists in tenant {tenant_slug!r} with "
                "different values; this tool will not silently change a catalog row. "
                "Edit the worksheet row and the existing database row consistently, "
                "by hand, if the values were genuinely meant to change."
            )
        item_id = uuid.UUID(str(existing.id))
        created = False
    else:
        item_id = RewardsRepository().create_item(
            connection,  # type: ignore[arg-type]
            tenant_id=tenant_id,
            name=name,
            points_cost=points_cost,
            fulfilment_cost=fulfilment_cost,
            budget_owner_id=budget_owner_id,
            funded=funded,
        )
        created = True

    return SeedRewardOutcome(
        created=created,
        item_id=item_id,
        satisfies_calibration=points_cost <= CALIBRATION_N_TENTATIVE * POINTS_PER_VERIFIED_ATTENDANCE,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--name", required=True, help="Reward item display name (from the worksheet row)"
    )
    parser.add_argument(
        "--points-cost", required=True, type=int, help="Points cost (from the worksheet row)"
    )
    parser.add_argument(
        "--fulfilment-cost",
        required=True,
        type=decimal.Decimal,
        help="Fulfilment cost in USD, stored and never read by any API (from the worksheet row)",
    )
    parser.add_argument(
        "--budget-owner-subject",
        required=True,
        help="user_account.external_subject of the item's budget owner (from the worksheet row)",
    )
    funded_group = parser.add_mutually_exclusive_group(required=True)
    funded_group.add_argument(
        "--funded", dest="funded", action="store_true", help="Mark the item listable"
    )
    funded_group.add_argument(
        "--unfunded", dest="funded", action="store_false", help="Mark the item not listable"
    )
    parser.add_argument("--tenant-slug", default="pilot", help="Synthetic tenant slug")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        settings = require_development_fixture_settings(Settings())
    except SeedConfigurationError as exc:
        print(f"seed-pilot-rewards: configuration error: {exc}", file=sys.stderr)
        return 2

    engine = create_db_engine(settings.database_url)
    try:
        with engine.begin() as connection:
            acquire_seed_lock(connection)
            outcome = seed_reward_item(
                connection,
                tenant_slug=args.tenant_slug,
                name=args.name,
                points_cost=args.points_cost,
                fulfilment_cost=args.fulfilment_cost,
                budget_owner_subject=args.budget_owner_subject,
                funded=args.funded,
            )
    except (
        SeedConflictError,
        SeedConfigurationError,
        UnknownTenantError,
        UnknownBudgetOwnerSubjectError,
        UnknownBudgetOwnerError,
    ) as exc:
        print(f"seed-pilot-rewards: {exc}", file=sys.stderr)
        return 2
    except SQLAlchemyError as exc:
        print(
            "seed-pilot-rewards: database operation failed; run `make migrate` against "
            f"the target database first: {exc}",
            file=sys.stderr,
        )
        return 1
    finally:
        engine.dispose()

    verb = "created" if outcome.created else "verified (identical repeat)"
    print(f"seed-pilot-rewards: {verb} reward_item {outcome.item_id} {args.name!r}")
    calibration_note = (
        "clears"
        if outcome.satisfies_calibration
        else "does NOT clear (a deliberate stretch reward, if intended)"
    )
    print(
        "seed-pilot-rewards: D7 calibration check (tentative, not enforced): "
        f"points_cost={args.points_cost} {calibration_note} "
        f"<= {CALIBRATION_N_TENTATIVE} x {POINTS_PER_VERIFIED_ATTENDANCE} "
        f"({CALIBRATION_N_TENTATIVE * POINTS_PER_VERIFIED_ATTENDANCE})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
