#!/usr/bin/env python3
"""Dev-only demo seed tool: walk already-open synthetic journeys toward Attended.

A `pipeline_record` row only ever starts at Matched — this tool never opens
one. What it does is walk journeys another writer already opened (the
synthetic review-accept path, `services/api/smartmatch_api/pipeline_provisioning.py`,
outside this card's scope) through the remaining funnel stages, so a
stakeholder demo of the compose appliance shows a funnel with real depth
across Contacted, Confirmed, Attended, and Member Inquiry rather than one bar
at Matched and nothing after it.

**This is an operator tool, not a service.** It is invoked by a human (or a
demo script) against an already-migrated database, the same way
`tools/seed_pilot.py` is. It is not part of either shipped container image,
it declares no route, and no application code imports it — the only door
into it is this file's own `main`.

**It does not call `record_matched` and writes no provenance.** Every row
this tool touches already has a `matched_provenance` written by whichever
call opened it; `PipelineRepository.advance_stage` never rewrites that
column, and neither does this tool. A reader looking for a provenance
argument here will not find one — there is nothing about *how the match
happened* left for this tool to say. Its only job is *what happened next*.

**Attended evidence is real, not invented.** `ck_pipeline_record_attendance_evidence`
requires a genuine `attendance_record` row before `attended_at` can be set,
and this tool satisfies that the same way Card 4's writer exists to: it
inserts one, through `AttendanceRepository.record_attendance`, and cites the
row it gets back. Every row this tool writes carries
`smartmatch_domain.synthetic_pilot.SYNTHETIC_ATTENDANCE_METHOD` — the value
recorded when a coordinator enters attendance by hand, and the only value
this tool ever writes. It never claims the value that names a badge- or
code-scanning device: no scanner integration reaches this file, nobody here
observed a badge or a code, and claiming otherwise would be exactly the
fabricated-evidence defect `ck_pipeline_record_attendance_evidence` exists to
prevent.

**This tool computes no fitness figure of any kind.** It reads a journey's
own `matched_at` and derives later timestamps from it; it opens no opinion
about how well a subject and an opportunity fit, because nothing in this
codebase can compute one yet and inventing one here would be exactly the
fabricated-evidence defect this whole synthetic pilot is built to avoid.

**Dev-only, by the same guard `tools/seed_pilot.py` already applies.**
`require_development_fixture_settings` below refuses to run unless the
resolved `Settings` describe `SMARTMATCH_EDITION=dev` with
`SMARTMATCH_USE_FIXTURE_PROVIDERS=true` — the identical check, so this tool
cannot be pointed at anything but the local fixture appliance.

**A silent zero is never a success.** Advancing zero journeys is always
reported — a one-line count on stdout, whatever the count is, every run —
and by default it is also a failure: `main` returns non-zero unless
`--allow-empty` was passed, in which case the same situation is reported as
a warning on stderr and the exit code becomes ``0``. There is no code path in
this module that can exit ``0`` having silently done nothing.

**Transaction boundary.** Unlike every repository this tool calls
(`PipelineRepository`, `AttendanceRepository` — neither commits, by
package-wide convention), this *is* the caller, so it owns the boundary. It
commits once per journey, immediately after that journey's own walk
finishes, not once at the end for the whole run: a run advancing several
journeys that fails partway through keeps the journeys it already finished
rather than losing them to one all-or-nothing transaction. Each journey's own
walk (one to four `advance_stage` calls, plus one `record_attendance` call
when the walk reaches Attended) is itself part of that same single
per-journey transaction, so a journey can never be left half-advanced by
this tool.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

import sqlalchemy as sa
from smartmatch_api.config import Settings
from smartmatch_domain.pipeline import PIPELINE_STAGE_SEQUENCE, PipelineStage
from smartmatch_domain.synthetic_pilot import SYNTHETIC_ATTENDANCE_METHOD
from smartmatch_persistence import schema
from smartmatch_persistence.attendance import AttendanceRepository
from smartmatch_persistence.engine import create_session_factory
from smartmatch_persistence.pipeline import PipelineRepository
from sqlalchemy.orm import Session

#: Minutes between consecutive funnel stages this tool writes — see the
#: module docstring's "Transaction boundary" note for how each stage's
#: timestamp is derived from a journey's own `matched_at`, never from
#: `utc_now()`, so a re-run is deterministic and idempotent.
_STAGE_STEP_MINUTES: Final[int] = 10


class SeedDemoPipelineConfigurationError(RuntimeError):
    """The seed-demo-pipeline command was invoked outside its dev/fixture scope."""


def require_development_fixture_settings(settings: Settings) -> Settings:
    """Refuse to run unless validated settings describe the local fixture pilot.

    Byte-for-byte the same check `tools/seed_pilot.py::require_development_fixture_settings`
    applies, so the two tools can never quietly diverge on what "dev" means.
    """
    if settings.edition.value != "dev" or not settings.use_fixture_providers:
        raise SeedDemoPipelineConfigurationError(
            "seed-demo-pipeline requires SMARTMATCH_EDITION=dev and "
            "SMARTMATCH_USE_FIXTURE_PROVIDERS=true."
        )
    return settings


@dataclass(frozen=True, slots=True)
class _SelectedJourney:
    """One `pipeline_record` row selected for this run's walk."""

    id: uuid.UUID
    subject_id: uuid.UUID
    opportunity_event_id: uuid.UUID
    matched_at: datetime


def resolve_tenant_id(session: Session, *, slug: str) -> uuid.UUID | None:
    """Return `tenant.id` for `slug`, or `None` if no such tenant exists."""
    row = session.execute(
        sa.select(schema.tenant.c.id).where(schema.tenant.c.slug == slug)
    ).one_or_none()
    return uuid.UUID(str(row.id)) if row is not None else None


def resolve_unit_id(session: Session, *, tenant_id: uuid.UUID, path: str) -> uuid.UUID | None:
    """Return `org_unit.id` for `(tenant_id, path)`, or `None` if no such unit exists."""
    row = session.execute(
        sa.select(schema.org_unit.c.id).where(
            schema.org_unit.c.tenant_id == tenant_id,
            schema.org_unit.c.path == path,
        )
    ).one_or_none()
    return uuid.UUID(str(row.id)) if row is not None else None


def select_journeys(
    session: Session, *, tenant_id: uuid.UUID, owning_unit_id: uuid.UUID, limit: int
) -> tuple[_SelectedJourney, ...]:
    """Return up to `limit` journeys for `(tenant_id, owning_unit_id)`, oldest first.

    Ordered by `(matched_at, id)` — the tie-break on `id` makes the selection
    deterministic even when two journeys share a `matched_at`, which matters
    for `--limit` to pick a reproducible subset rather than whatever order
    PostgreSQL happens to return.
    """
    rows = session.execute(
        sa.select(
            schema.pipeline_record.c.id,
            schema.pipeline_record.c.subject_id,
            schema.pipeline_record.c.opportunity_event_id,
            schema.pipeline_record.c.matched_at,
        )
        .where(
            schema.pipeline_record.c.tenant_id == tenant_id,
            schema.pipeline_record.c.owning_unit_id == owning_unit_id,
        )
        .order_by(schema.pipeline_record.c.matched_at, schema.pipeline_record.c.id)
        .limit(limit)
    ).all()
    return tuple(
        _SelectedJourney(
            id=uuid.UUID(str(row.id)),
            subject_id=uuid.UUID(str(row.subject_id)),
            opportunity_event_id=uuid.UUID(str(row.opportunity_event_id)),
            matched_at=row.matched_at,
        )
        for row in rows
    )


def advance_journey(
    session: Session,
    *,
    pipeline_repo: PipelineRepository,
    attendance_repo: AttendanceRepository,
    tenant_id: uuid.UUID,
    owning_unit_id: uuid.UUID,
    journey: _SelectedJourney,
    through: PipelineStage,
) -> int:
    """Walk one journey from its current stage up to and including `through`.

    Every stage's `reached_at` is `journey.matched_at + timedelta(minutes=10 *
    i)`, where `i` is that stage's own index in
    `smartmatch_domain.pipeline.PIPELINE_STAGE_SEQUENCE` — strictly
    increasing by construction, which is what satisfies
    `ck_pipeline_record_stage_order` without this function needing to reason
    about ordering itself.

    A stage `advance_stage` reports as already reached is not an error and
    is not counted: this function calls every stage in the walk regardless of
    the journey's starting point, and lets `advance_stage`'s own
    idempotency — a no-op when a stage is already reached — decide what
    happened. That is also what makes a re-run of this tool over the same
    journey idempotent: nothing here tracks "did I already do this",
    `advance_stage` and `AttendanceRepository.record_attendance` both already
    do.

    Returns:
        How many stages *this call's own walk* newly transitioned — never
        inferred from the journey's resulting state, only from each
        `advance_stage` outcome's own `transitioned` flag.

    Raises:
        RuntimeError: `journey.id` no longer exists in this tenant partway
            through the walk. Unreachable in ordinary operation — nothing
            deletes a `pipeline_record` row — and raised explicitly rather
            than silently stopping the walk, for the same reason
            `PipelineRepository`'s own unreachable branches are raised
            rather than asserted.
    """
    through_index = PIPELINE_STAGE_SEQUENCE.index(through)
    stages_transitioned = 0

    for index, stage in enumerate(PIPELINE_STAGE_SEQUENCE):
        if index == 0 or index > through_index:
            # index 0 is Matched, the entry stage every selected row already
            # has; advance_stage refuses to be called with it.
            continue

        reached_at = journey.matched_at + timedelta(minutes=_STAGE_STEP_MINUTES * index)
        attended_attendance_id: uuid.UUID | None = None
        if stage is PipelineStage.ATTENDED:
            attended_attendance_id = attendance_repo.record_attendance(
                session,
                tenant_id=tenant_id,
                owning_unit_id=owning_unit_id,
                subject_id=journey.subject_id,
                event_id=journey.opportunity_event_id,
                method=SYNTHETIC_ATTENDANCE_METHOD,
            )

        outcome = pipeline_repo.advance_stage(
            session,
            tenant_id=tenant_id,
            record_id=journey.id,
            stage=stage,
            reached_at=reached_at,
            attended_attendance_id=attended_attendance_id,
        )
        if not outcome.exists:
            raise RuntimeError(
                f"pipeline_record {journey.id} no longer exists in tenant {tenant_id} — "
                "this should be unreachable"
            )
        if outcome.transitioned:
            stages_transitioned += 1

    return stages_transitioned


def _zero_advance_message(*, unit_path: str, rows_found: int, through: str) -> str:
    """The stderr message §1.10 requires whenever this run advanced no journey.

    Names the unit and says what a caller should do next, in both of the two
    circumstances that reach it: no candidate row existed at all, or every
    candidate row had already reached `through` (or beyond) on an earlier
    run.
    """
    if rows_found == 0:
        return (
            f"seed-demo-pipeline advanced 0 journeys in unit {unit_path!r}: no "
            "pipeline_record rows exist there yet. Accept a professionals row and then "
            "an in-list events row first, or pass --allow-empty."
        )
    return (
        f"seed-demo-pipeline advanced 0 journeys in unit {unit_path!r}: {rows_found} "
        f"pipeline_record row(s) were found there, but each had already reached "
        f"{through!r} (or a later stage) on an earlier run. Nothing to advance, or pass "
        "--allow-empty."
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-slug", default="pilot", help="Tenant slug to resolve")
    parser.add_argument(
        "--unit-path", default="pilot", help="org_unit ltree path receiving the walk"
    )
    parser.add_argument(
        "--through",
        choices=["contacted", "confirmed", "attended", "member_inquiry"],
        default="attended",
        help="Furthest funnel stage to advance each selected journey to",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1,
        help="Maximum number of pipeline_record rows to advance",
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Exit 0 even when zero journeys were advanced (still warns on stderr)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        settings = require_development_fixture_settings(Settings())
    except SeedDemoPipelineConfigurationError as exc:
        print(f"seed-demo-pipeline: configuration error: {exc}", file=sys.stderr)
        return 2

    through_stage = PipelineStage(args.through)
    session_factory = create_session_factory(settings.database_url)
    pipeline_repo = PipelineRepository()
    attendance_repo = AttendanceRepository()

    with session_factory() as session:
        tenant_id = resolve_tenant_id(session, slug=args.tenant_slug)
        if tenant_id is None:
            print(
                f"seed-demo-pipeline: no tenant with slug {args.tenant_slug!r}",
                file=sys.stderr,
            )
            return 1

        owning_unit_id = resolve_unit_id(session, tenant_id=tenant_id, path=args.unit_path)
        if owning_unit_id is None:
            print(
                f"seed-demo-pipeline: no org_unit with path {args.unit_path!r} in tenant "
                f"{args.tenant_slug!r}",
                file=sys.stderr,
            )
            return 1

        journeys = select_journeys(
            session, tenant_id=tenant_id, owning_unit_id=owning_unit_id, limit=args.limit
        )

        journeys_advanced = 0
        for journey in journeys:
            stages_transitioned = advance_journey(
                session,
                pipeline_repo=pipeline_repo,
                attendance_repo=attendance_repo,
                tenant_id=tenant_id,
                owning_unit_id=owning_unit_id,
                journey=journey,
                through=through_stage,
            )
            session.commit()
            if stages_transitioned > 0:
                journeys_advanced += 1
            print(
                f"seed-demo-pipeline: journey {journey.id} advanced {stages_transitioned} "
                f"stage(s) toward {through_stage.value!r}"
            )

        # §1.10: the count is printed on every run, including a zero one —
        # never distinguishable from success by its absence.
        print(
            f"seed-demo-pipeline: advanced {journeys_advanced} journey(s) in unit "
            f"{args.unit_path!r}"
        )

        if journeys_advanced == 0:
            print(
                _zero_advance_message(
                    unit_path=args.unit_path, rows_found=len(journeys), through=args.through
                ),
                file=sys.stderr,
            )
            if not args.allow_empty:
                return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
