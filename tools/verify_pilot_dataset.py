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
    "CountedTable",
    "TableCount",
    "count_dataset",
    "main",
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
    CountedTable(schema.reward_item, None, "make seed-pilot-rewards (owner-supplied)"),
)


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

    empty = [count for count in counts if count.empty]
    if not empty:
        print("verify-pilot-dataset: every counted table holds rows.")
        return 0

    print("verify-pilot-dataset: INCOMPLETE. These tables hold nothing:", file=sys.stderr)
    for count in empty:
        print(f"  {count.name} — filled by {count.writer}", file=sys.stderr)
    print(
        "verify-pilot-dataset: a demo run over this database will show empty surfaces, not "
        "unknown values. Rebuild with scripts/reset_pilot_dataset.sh.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
