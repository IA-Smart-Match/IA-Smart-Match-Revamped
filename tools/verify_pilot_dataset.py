#!/usr/bin/env python3
"""Dev-only operator tool: assert the synthetic pilot dataset is actually there.

A read-only counterpart to ``tools/generate_pilot_dataset.py``. It writes
nothing, decides nothing, and answers exactly one question: **for the pilot
tenant, which of the tables a demo reads from are empty?**

Why this exists as a separate tool
----------------------------------
The generator already prints a long report, and that report is a record of what
the *tool* believed it did. It is not a record of what the *database holds*.
The two came apart once already, and expensively: an appliance was found
carrying 250 ``professional_unit_relationship`` rows, 60 ``event`` rows and 180
``pipeline_record`` rows — every one of them written by the generator's Phase B,
which goes through repositories — beside **zero** ``job``, ``import_batch``,
``review_item``, ``speaker_profile``, ``match_run``, ``cba_invitation`` and
``student_speaker_feedback`` rows, every one of which is written by Phase A,
which goes through the HTTP API. Phase A requires the API *and* the worker *and*
something driving dispatch to be running; two of those three had not been, and
nothing in the stack said so. Half a dataset looks, from a screen, exactly like
a whole one whose numbers happen to be unknown.

So this tool exists to make that state loud. It exits non-zero the moment any
counted table holds nothing, and it prints the whole table either way, so a run
that half-succeeded cannot be read as a run that succeeded.

What "zero" means here, and what it does not
--------------------------------------------
A zero in this table is a claim about **a table that this dataset's own
generator is supposed to fill**, not a claim about a measurement. That
distinction is the whole of ADR-0011 rule 1 and it is worth stating plainly,
because this file counts rows and ADR-0011 forbids exactly one thing this file
could be mistaken for doing:

* An empty ``review_item`` table means *the import path did not run*. That is a
  broken pipeline, and reporting it as zero is correct — it is a count of rows,
  and there are none.
* A speaker whose topic relevance is unknown, or a student whose balance is
  unknown, is **not** counted here at all and must never be rendered as ``0``.
  Those are measurements with no evidence behind them, and the generator writes
  a deliberate fraction of them on purpose. See
  ``tools/pilot_dataset_plan.py``'s ``UNKNOWN_*_SHARE`` constants.

This tool therefore never reports a *fraction* as zero and never asks a
repository for a score. It counts rows in tables and nothing else.

Dev-only
--------
:func:`~seed_pilot.require_development_fixture_settings` — imported from
``seed_pilot``, as every other tool under ``tools/`` imports it rather than
restating it — refuses to run unless ``SMARTMATCH_EDITION=dev`` and
``SMARTMATCH_USE_FIXTURE_PROVIDERS=true``. A read-only tool arguably needs no
such guard; it carries one anyway, because the guard is what makes "everything
in ``tools/`` is local-pilot-only" a property of the directory rather than a
habit of most of its files.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

import sqlalchemy as sa
from seed_demo_pipeline import resolve_tenant_id, resolve_unit_id
from seed_pilot import SeedConfigurationError, require_development_fixture_settings
from smartmatch_api.config import Settings
from smartmatch_persistence import schema
from smartmatch_persistence.engine import create_session_factory
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

__all__ = [
    "COUNTED_TABLES",
    "DEMO_PORTAL_SURFACES",
    "CountedTable",
    "PortalSurface",
    "SurfaceCount",
    "TableCount",
    "count_dataset",
    "count_portal_surfaces",
    "main",
    "portal_report_lines",
    "report_lines",
]


@dataclass(frozen=True, slots=True)
class CountedTable:
    """One table this tool counts, and how it is scoped to the pilot.

    Attributes:
        table: The ``smartmatch_persistence.schema`` table object. Taken from
            the shipped metadata rather than named as a string, so a table this
            tool counts cannot outlive a rename: the import fails at load
            instead of the count silently reading a table that no longer exists.
        unit_column: The column carrying the owning unit, or ``None`` when the
            table is scoped by tenant alone. Three spellings are in use across
            the schema — ``owning_unit_id``, ``host_org_unit_id`` and
            ``unit_id`` — so the spelling is recorded per table rather than
            guessed from a convention that does not hold.
        writer: Which phase of the generator fills this table. Printed beside
            the count, because "review_item is empty" is only actionable once a
            reader knows that means the HTTP import path did not run.
    """

    table: sa.Table
    unit_column: str | None
    writer: str


@dataclass(frozen=True, slots=True)
class TableCount:
    """One counted table and what was found in it."""

    name: str
    rows: int
    writer: str

    @property
    def empty(self) -> bool:
        """Whether this table holds nothing for the pilot tenant."""
        return self.rows == 0


#: Every table a pilot demo reads from, in the order a run fills them.
#:
#: The order is the generator's own order — identity, then the HTTP import path,
#: then the repository writers, then the match and invitation surfaces, then
#: feedback — so that the first zero in the printed table is the earliest step
#: that failed rather than an arbitrary alphabetical one. A reader scanning down
#: the column stops at the first ``0`` and that is the thing to go and fix.
#:
#: ``reward_item`` is counted and is deliberately last: it is the one table the
#: generator does **not** fill, by design — every catalog value is owner-supplied
#: through ``make seed-pilot-rewards`` — so a zero there means "the operator has
#: not run that target", which is a different instruction from every other zero
#: in this list. The ``writer`` column says so.
COUNTED_TABLES: Final[tuple[CountedTable, ...]] = (
    CountedTable(schema.professional_unit_relationship, "unit_id", "generator Phase B"),
    CountedTable(schema.event, "host_org_unit_id", "generator Phase B"),
    CountedTable(schema.job, "owning_unit_id", "generator Phase A (HTTP import)"),
    CountedTable(schema.import_batch, "owning_unit_id", "generator Phase A (HTTP import)"),
    CountedTable(schema.review_item, None, "generator Phase A (worker -> review)"),
    CountedTable(schema.speaker_profile, "owning_unit_id", "generator Phase A (review accept)"),
    CountedTable(schema.pipeline_record, "owning_unit_id", "generator Phase B"),
    CountedTable(schema.attendance_record, "owning_unit_id", "generator Phase B"),
    CountedTable(schema.point_ledger_entry, None, "generator Phase B"),
    CountedTable(schema.speaker_request_classification, None, "generator Phase A (request)"),
    CountedTable(schema.match_run, "owning_unit_id", "generator Phase A (match runs)"),
    CountedTable(schema.cba_invitation_batch, "owning_unit_id", "generator Phase A (invitations)"),
    CountedTable(schema.cba_invitation, "owning_unit_id", "generator Phase A (invitations)"),
    CountedTable(schema.student_speaker_feedback, "owning_unit_id", "generator Phase C"),
    # The engagement surfaces. Counted after the generator's own tables because
    # nothing the generator runs fills them: `event_registration` and
    # `cba_meeting` have no writer in it at all, and `redemption` cannot have one
    # until a catalog exists. A zero in this block therefore means "the operator
    # has not run `make seed-pilot-engagement`", which is a different
    # instruction from every zero above it, and the `writer` column says so.
    CountedTable(schema.event_registration, "owning_unit_id", "make seed-pilot-engagement"),
    CountedTable(schema.cba_meeting, "owning_unit_id", "make seed-pilot-engagement"),
    CountedTable(schema.reward_item, None, "make seed-pilot-rewards (owner-supplied)"),
    # Last, and after `reward_item` deliberately: a redemption cannot exist
    # before the catalog it redeems against, so a zero here under a non-zero
    # `reward_item` is a real gap and a zero here under an empty `reward_item`
    # is the same gap read one line higher.
    CountedTable(schema.redemption, None, "make seed-pilot-engagement"),
)


@dataclass(frozen=True, slots=True)
class PortalSurface:
    """One screen a demo principal lands on, and whose rows must be behind it.

    The second class of hollowness, and the one a row count alone cannot see.
    :data:`COUNTED_TABLES` answers "is this table empty for the pilot tenant?".
    That question has a healthy answer for ``point_ledger_entry`` — 187 rows —
    while the student portal is still blank, because every one of those rows
    belongs to a ``synthetic-student:*`` account and the person signing in is
    ``compose-pilot-student``. Three surfaces are scoped by
    ``principal.user_id`` and not by unit, so for those the owner *is* the
    question.

    Attributes:
        token: The ``SMARTMATCH_DEV_PRINCIPALS`` bearer that opens this portal.
            Recorded so ``tests/unit/test_demo_portal_surfaces.py`` can compare
            this table against ``seed_pilot_principals.COMPOSE_DEV_PRINCIPALS``
            and fail on a principal with no declared surface at all.
        subject: The ``user_account.external_subject`` that token resolves to.
        surface: The screen, in the words a reader of the report would use.
            Documentation for the operator; it scopes nothing.
        table: The table behind that screen, from the shipped metadata for
            :class:`CountedTable`'s reason.
        subject_column: The column carrying the owner, for a surface scoped by
            person — ``None`` for one scoped by unit alone, where membership
            rather than authorship decides who sees the rows. When it is not
            ``None``, :attr:`subject` is load-bearing and a count is taken for
            that subject specifically.
        unit_column: The owning-unit column, or ``None`` for tenant-wide.
            Three spellings are in use across the schema, so it is recorded per
            surface rather than guessed.
        writer: What fills it, printed beside the count.
    """

    token: str
    subject: str
    surface: str
    table: sa.Table
    subject_column: str | None
    unit_column: str | None
    writer: str


#: Every demo portal's primary surfaces, with the account whose rows must be there.
#:
#: "Primary" is the screen the portal lands on and the screen it exists for, not
#: every table a route touches. A portal is not demonstrable because its API
#: answers ``200``; it is demonstrable when the person who signs in sees rows.
#:
#: The ``subject_column`` entries are the ones that were invisibly empty. Each
#: names ``compose-pilot-student`` or ``compose-pilot-volunteer`` — the accounts
#: the demo logins actually resolve to — and *not* the ``synthetic-student:*``
#: accounts the generator writes under, which is the whole point of recording an
#: owner here rather than trusting a tenant-wide count.
DEMO_PORTAL_SURFACES: Final[tuple[PortalSurface, ...]] = (
    # Coordinator — the Speaker Request queue, the runs it drives, the meetings
    # page. All unit-scoped: a coordinator sees their unit's rows, not their own.
    PortalSurface(
        token="compose-api",
        subject="compose-pilot-coordinator",
        surface="Speaker Request queue",
        table=schema.event,
        subject_column=None,
        unit_column="host_org_unit_id",
        writer="generator Phase A/B",
    ),
    PortalSurface(
        token="compose-api",
        subject="compose-pilot-coordinator",
        surface="Speaker Request targets (§7/§8)",
        table=schema.speaker_request_classification,
        subject_column=None,
        unit_column=None,
        writer="generator Phase A (request)",
    ),
    PortalSurface(
        token="compose-api",
        subject="compose-pilot-coordinator",
        surface="Match runs",
        table=schema.match_run,
        subject_column=None,
        unit_column="owning_unit_id",
        writer="generator Phase A (match runs)",
    ),
    PortalSurface(
        token="compose-api",
        subject="compose-pilot-coordinator",
        surface="Meetings with the CBA team",
        table=schema.cba_meeting,
        subject_column=None,
        unit_column="owning_unit_id",
        writer="make seed-pilot-engagement",
    ),
    # Student — every one of these is scoped by `principal.user_id`, and every
    # one of them was empty for the demo login while the tenant-wide count was
    # healthy. This block is the ownership trap, written down.
    PortalSurface(
        token="compose-student",
        subject="compose-pilot-student",
        surface="My agenda (attended)",
        table=schema.attendance_record,
        subject_column="subject_id",
        unit_column="owning_unit_id",
        writer="make seed-pilot-engagement",
    ),
    PortalSurface(
        token="compose-student",
        subject="compose-pilot-student",
        surface="My agenda (registered)",
        table=schema.event_registration,
        subject_column="subject_id",
        unit_column="owning_unit_id",
        writer="make seed-pilot-engagement",
    ),
    PortalSurface(
        token="compose-student",
        subject="compose-pilot-student",
        surface="Points balance",
        table=schema.point_ledger_entry,
        subject_column="subject_id",
        unit_column=None,
        writer="make seed-pilot-engagement",
    ),
    PortalSurface(
        token="compose-student",
        subject="compose-pilot-student",
        surface="My redemptions",
        table=schema.redemption,
        subject_column="subject_id",
        unit_column=None,
        writer="make seed-pilot-engagement",
    ),
    # Event Host — one read route and one predicate on it,
    # `filed_by_user_id == principal.user_id` (OQ-CBA-014). The generator files
    # every request with the *coordinator* token, so this surface is empty by
    # construction however many requests exist.
    PortalSurface(
        token="compose-host",
        subject="compose-pilot-volunteer",
        surface="My filed Speaker Requests",
        table=schema.event,
        subject_column="filed_by_user_id",
        unit_column="host_org_unit_id",
        writer="make seed-pilot-engagement",
    ),
    # Administration — the meetings page (#130) and the catalog whose budget
    # this account owns. Both unit- or tenant-scoped; `reward_item` carries a
    # `budget_owner_id`, which is an accountability record and not a read scope,
    # so it is not a `subject_column` here.
    PortalSurface(
        token="compose-admin",
        subject="compose-pilot-admin",
        surface="Meetings with the CBA team",
        table=schema.cba_meeting,
        subject_column=None,
        unit_column="owning_unit_id",
        writer="make seed-pilot-engagement",
    ),
    PortalSurface(
        token="compose-admin",
        subject="compose-pilot-admin",
        surface="Rewards catalog",
        table=schema.reward_item,
        subject_column=None,
        unit_column=None,
        writer="make seed-pilot-rewards (owner-supplied)",
    ),
)


@dataclass(frozen=True, slots=True)
class SurfaceCount:
    """One portal surface and what was found behind it, for the printed report."""

    token: str
    surface: str
    name: str
    owner: str
    rows: int
    writer: str

    @property
    def empty(self) -> bool:
        """Whether this surface holds nothing for the person the portal is for."""
        return self.rows == 0


def count_dataset(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    tables: Sequence[CountedTable] = COUNTED_TABLES,
) -> tuple[TableCount, ...]:
    """Count every table in ``tables`` for one tenant and unit.

    Scoped by tenant always and by unit where the table carries one. A table
    with no unit column is counted tenant-wide, which for a single-unit pilot
    appliance is the same set of rows. That is stated rather than assumed: a
    second unit in this tenant would make those counts wider than the others,
    and the printed table names the scope so nobody has to guess.

    Every count runs inside one session, so the table printed is one snapshot
    rather than fifteen reads of a database somebody may still be writing.
    """
    counted: list[TableCount] = []
    for entry in tables:
        criteria = [entry.table.c.tenant_id == tenant_id]
        if entry.unit_column is not None:
            criteria.append(entry.table.c[entry.unit_column] == unit_id)
        rows = session.execute(
            sa.select(sa.func.count()).select_from(entry.table).where(*criteria)
        ).scalar_one()
        counted.append(TableCount(name=entry.table.name, rows=int(rows), writer=entry.writer))
    return tuple(counted)


def count_portal_surfaces(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    surfaces: Sequence[PortalSurface] = DEMO_PORTAL_SURFACES,
) -> tuple[SurfaceCount, ...]:
    """Count each demo portal's primary surfaces **as the person who signs in**.

    The difference from :func:`count_dataset` is one predicate, and it is the
    whole reason this function exists: where a surface carries a
    ``subject_column``, the count is filtered to the ``user_account`` that
    surface's demo login resolves to. A tenant-wide count of
    ``point_ledger_entry`` says 187 and the student's screen says nothing,
    because all 187 belong to accounts nobody can sign in as.

    A subject that resolves to no ``user_account`` at all is reported as **zero
    rows**, not skipped and not raised on. That is a count of rows and not a
    measurement, so ADR-0011 has nothing to say about it: an unseeded principal
    genuinely has no rows, and the report naming the surface and its writer is
    exactly the instruction the operator needs.
    """
    resolved: dict[str, uuid.UUID | None] = {}
    counted: list[SurfaceCount] = []
    for surface in surfaces:
        criteria = [surface.table.c.tenant_id == tenant_id]
        if surface.unit_column is not None:
            criteria.append(surface.table.c[surface.unit_column] == unit_id)

        if surface.subject_column is not None:
            if surface.subject not in resolved:
                found = session.execute(
                    sa.select(schema.user_account.c.id).where(
                        schema.user_account.c.tenant_id == tenant_id,
                        schema.user_account.c.external_subject == surface.subject,
                    )
                ).scalar_one_or_none()
                resolved[surface.subject] = None if found is None else uuid.UUID(str(found))
            subject_id = resolved[surface.subject]
            if subject_id is None:
                counted.append(
                    SurfaceCount(
                        token=surface.token,
                        surface=surface.surface,
                        name=surface.table.name,
                        owner=f"{surface.subject} (NO ACCOUNT)",
                        rows=0,
                        writer=surface.writer,
                    )
                )
                continue
            criteria.append(surface.table.c[surface.subject_column] == subject_id)

        rows = session.execute(
            sa.select(sa.func.count()).select_from(surface.table).where(*criteria)
        ).scalar_one()
        counted.append(
            SurfaceCount(
                token=surface.token,
                surface=surface.surface,
                name=surface.table.name,
                owner=surface.subject if surface.subject_column is not None else "(unit-scoped)",
                rows=int(rows),
                writer=surface.writer,
            )
        )
    return tuple(counted)


def portal_report_lines(counts: Sequence[SurfaceCount]) -> tuple[str, ...]:
    """The per-portal table, grouped by token so one portal reads as one block.

    Aligned for :func:`report_lines`'s reason, and grouped for a second one: the
    failure here is rarely a single zero. It is one portal's whole block at zero
    while every other portal is full, which is what "the rows are under the
    wrong account" looks like from a report.
    """
    if not counts:
        return ()
    token_width = max(len(count.token) for count in counts)
    surface_width = max(len(count.surface) for count in counts)
    owner_width = max(len(count.owner) for count in counts)
    lines: list[str] = []
    previous: str | None = None
    for count in counts:
        if previous is not None and count.token != previous:
            lines.append("")
        previous = count.token
        lines.append(
            f"  {count.token:<{token_width}}  {count.surface:<{surface_width}}  "
            f"{count.owner:<{owner_width}}  {count.rows:>7}  "
            f"{'EMPTY  ' if count.empty else '       '}{count.writer}"
        )
    return tuple(lines)


def report_lines(counts: Sequence[TableCount]) -> tuple[str, ...]:
    """The printed table, one line per counted table.

    Formatted rather than dumped so the counts line up in a column: the failure
    this tool exists to catch is a *block* of zeros in the middle of an
    otherwise full table, and that shape is only visible when the numbers are
    aligned under one another.
    """
    width = max((len(count.name) for count in counts), default=0)
    return tuple(
        f"  {count.name:<{width}}  {count.rows:>7}  {'EMPTY  ' if count.empty else '       '}"
        f"{count.writer}"
        for count in counts
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-slug", default="pilot", help="Synthetic tenant slug")
    parser.add_argument("--unit-path", default="pilot", help="ltree path owning the dataset")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Print the table and exit non-zero if any counted table is empty.

    Three distinguishable failures, three distinguishable exits: ``2`` for a
    configuration refusal (this is not a dev fixture appliance), ``1`` for a
    missing tenant or unit or a database that could not be read, and ``1`` again
    for the finding this tool exists for — an empty table. The last one prints
    the empty tables by name and says which writer was supposed to fill each,
    because "the dataset is incomplete" without that list is a sentence nobody
    can act on.
    """
    args = parse_args(argv)
    try:
        settings = require_development_fixture_settings(Settings())
    except SeedConfigurationError as exc:
        print(f"verify-pilot-dataset: configuration error: {exc}", file=sys.stderr)
        return 2

    session_factory = create_session_factory(settings.database_url)
    with session_factory() as session:
        try:
            tenant_id = resolve_tenant_id(session, slug=args.tenant_slug)
            if tenant_id is None:
                print(
                    f"verify-pilot-dataset: no tenant with slug {args.tenant_slug!r}; "
                    "run `make seed-pilot` first",
                    file=sys.stderr,
                )
                return 1
            unit_id = resolve_unit_id(session, tenant_id=tenant_id, path=args.unit_path)
            if unit_id is None:
                print(
                    f"verify-pilot-dataset: no org_unit at path {args.unit_path!r} in tenant "
                    f"{args.tenant_slug!r}; run `make seed-pilot` first",
                    file=sys.stderr,
                )
                return 1
            counts = count_dataset(session, tenant_id=tenant_id, unit_id=unit_id)
            surfaces = count_portal_surfaces(session, tenant_id=tenant_id, unit_id=unit_id)
        except SQLAlchemyError as exc:
            print(
                "verify-pilot-dataset: database read failed; the database must be migrated "
                f"first: {exc}",
                file=sys.stderr,
            )
            return 1

    print(f"verify-pilot-dataset: tenant {tenant_id} (slug {args.tenant_slug!r}), unit {unit_id}")
    for line in report_lines(counts):
        print(line)

    print("")
    print("verify-pilot-dataset: per-portal surfaces, counted as the account that signs in")
    for line in portal_report_lines(surfaces):
        print(line)

    empty = [count for count in counts if count.empty]
    empty_surfaces = [surface for surface in surfaces if surface.empty]
    if not empty and not empty_surfaces:
        print("verify-pilot-dataset: every counted table holds rows, for every demo portal.")
        return 0

    if empty:
        print("verify-pilot-dataset: INCOMPLETE. These tables hold nothing:", file=sys.stderr)
        for count in empty:
            print(f"  {count.name} — filled by {count.writer}", file=sys.stderr)

    if empty_surfaces:
        # Reported separately, and separately worded, because it is a different
        # defect with a different fix. A table above is empty. A surface here can
        # be empty over a table that is *full* — the rows are there and they
        # belong to somebody nobody can sign in as.
        print(
            "verify-pilot-dataset: INCOMPLETE. These demo portals land on an empty "
            "surface — note that the table above may be full, in which case the rows "
            "exist under an account no demo login resolves to:",
            file=sys.stderr,
        )
        for surface in empty_surfaces:
            print(
                f"  {surface.token} -> {surface.surface} ({surface.name}, owner "
                f"{surface.owner}) — filled by {surface.writer}",
                file=sys.stderr,
            )

    print(
        "verify-pilot-dataset: a demo run over this database will show empty surfaces, not "
        "unknown values. Rebuild with scripts/reset_pilot_dataset.sh.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
