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

What it asserts beyond counts
-----------------------------
A count of rows is the weakest thing that can be said about a dataset, and it
was not enough. Sixty-four events, three match runs and nine invitations is a
healthy-looking table that says nothing about whether those nine invitations
belong to those three runs, whether those runs belong to those events, or
whether any speaker named on them is on this unit's roster. A demo does not
fail because a table is empty; it fails because a page shows a row whose
neighbours are missing.

So this tool runs three passes and every one of them can fail the run:

1. :data:`COUNTED_TABLES` — is the table empty for this tenant?
2. :data:`DEMO_PORTAL_SURFACES` — does the person who *signs in* own enough
   rows on the screens their portal lands on? Each surface carries a floor
   (:attr:`PortalSurface.minimum_rows`), because one row is a screen with one
   row on it and a reviewer clicking through can tell.
3. :data:`CROSS_TABLE_CHECKS` — does every row point at a row that exists?
   Each check reports a *population* (the rows the question is about) and a
   *violation* count, and a population of zero fails as loudly as a violation
   does. "Every invitation names a roster speaker" is trivially true of no
   invitations, and a check that can only pass is not a check.

Whose rows: the logins, not the fixtures
----------------------------------------
Two families of account exist in a pilot tenant and only one of them can be
signed in as from a browser. ``pilot-login-*`` are the accounts
``tools/seed_pilot_logins.py`` creates for the four ``@``-addressed credentials
a reviewer types into the login form. ``compose-pilot-*`` are the accounts the
``SMARTMATCH_DEV_PRINCIPALS`` bearer tokens resolve to — a local-only fixture
that no deployed surface may carry.

The person-scoped surfaces here therefore default to **the logins**
(:data:`LOGIN_SUBJECT_SET`), and ``--subjects fixture`` selects the bearer-token
accounts for a stack being driven by tokens alone. It was the other way round,
and the consequence was a tool that reported a healthy student portal for an
account nobody could sign in as while ``student@`` saw a blank page.

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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Protocol

import sqlalchemy as sa
from seed_demo_pipeline import resolve_tenant_id, resolve_unit_id
from seed_pilot import SeedConfigurationError, require_development_fixture_settings
from seed_pilot_logins import ROLE_CREDENTIALS
from seed_pilot_principals import COMPOSE_DEV_PRINCIPALS
from smartmatch_api.config import Settings
from smartmatch_persistence import schema
from smartmatch_persistence.engine import create_session_factory
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

__all__ = [
    "COUNTED_TABLES",
    "CROSS_TABLE_CHECKS",
    "DEFAULT_SUBJECT_SET",
    "DEMO_PORTAL_SURFACES",
    "FIXTURE_SUBJECT_SET",
    "LOGIN_SUBJECT_SET",
    "SUBJECT_SETS",
    "CheckResult",
    "CountedTable",
    "JoinCheck",
    "OwnedByColumn",
    "OwnedByLedgerCause",
    "OwnerScope",
    "PortalSurface",
    "ReferenceCheck",
    "SurfaceCount",
    "TableCount",
    "check_report_lines",
    "count_dataset",
    "count_portal_surfaces",
    "main",
    "portal_report_lines",
    "report_lines",
    "run_checks",
    "subjects_for",
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
    CountedTable(schema.contact_channel, "owning_unit_id", "generator Phase A (review accept)"),
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


# ---------------------------------------------------------------------------
# Whose rows: the two families of pilot account
# ---------------------------------------------------------------------------
#
# Neither list is restated here. ``ROLE_CREDENTIALS`` and
# ``COMPOSE_DEV_PRINCIPALS`` are the seeds that write these accounts, so they
# are the only places a subject string is allowed to be decided; a third copy
# in this file would be a fourth thing to keep in step and the first to drift.

#: ``membership.role`` -> ``user_account.external_subject`` for the four
#: accounts a reviewer can actually sign in as (``pilot@``, ``student@``,
#: ``admin@``, ``volunteer@``). Derived from ``tools/seed_pilot_logins.py``.
LOGIN_SUBJECT_SET: Final[Mapping[str, str]] = {
    entry.role: entry.subject for entry in ROLE_CREDENTIALS
}

#: ``membership.role`` -> ``external_subject`` for the local-only accounts the
#: compose ``SMARTMATCH_DEV_PRINCIPALS`` bearer tokens resolve to. A fixture,
#: never a deployed identity. Derived from ``tools/seed_pilot_principals.py``.
FIXTURE_SUBJECT_SET: Final[Mapping[str, str]] = {
    principal.role: principal.subject for principal in COMPOSE_DEV_PRINCIPALS
}

#: The selectable families, by the value ``--subjects`` takes.
SUBJECT_SETS: Final[Mapping[str, Mapping[str, str]]] = {
    "login": LOGIN_SUBJECT_SET,
    "fixture": FIXTURE_SUBJECT_SET,
}

#: The default, and the correction this module carries: a person-scoped surface
#: is about the person who signs in, and that is a login.
DEFAULT_SUBJECT_SET: Final[str] = "login"


def subjects_for(name: str = DEFAULT_SUBJECT_SET) -> Mapping[str, str]:
    """The ``role -> external_subject`` map named by ``name``.

    Raises:
        KeyError: ``name`` is not a declared family. Raised rather than
            defaulted, because silently falling back to the fixture accounts is
            the exact failure this parameter exists to end.
    """
    return SUBJECT_SETS[name]


# ---------------------------------------------------------------------------
# Ownership: how a row is attached to the person who reads it
# ---------------------------------------------------------------------------


class OwnerScope(Protocol):
    """How to ask a table "which of these rows belong to this account?".

    A column on the row is the ordinary answer and is not the only one. A
    ``point_ledger_entry`` carries no subject at all — it names its *cause*, and
    the cause names the student. Modelling that as a column was the second half
    of the defect in this file: the first spelling tried was ``subject_id``,
    which does not exist on that table, and the second candidate ``actor_id``
    exists but is NULL for every attendance credit, because a derived credit has
    no author. Either spelling would have reported an empty student surface as
    an error in the tool rather than as a fact about the data.
    """

    def predicate(self, table: sa.Table, subject_id: uuid.UUID) -> sa.ColumnElement[bool]:
        """The WHERE clause selecting ``subject_id``'s rows of ``table``."""
        ...  # pragma: no cover - structural


@dataclass(frozen=True, slots=True)
class OwnedByColumn:
    """The row carries the owner directly, in ``column``."""

    column: str

    def predicate(self, table: sa.Table, subject_id: uuid.UUID) -> sa.ColumnElement[bool]:
        """``table.column == subject_id``."""
        return table.c[self.column] == subject_id


@dataclass(frozen=True, slots=True)
class OwnedByLedgerCause:
    """The row names a cause, and the cause names the owner.

    ``point_ledger_entry`` only. The predicate is the same disjunction
    :meth:`RewardsRepository.ledger_entries_for_subject` folds a balance over —
    ``coalesce(attendance.subject_id, redemption.subject_id)`` — written as two
    ``IN`` clauses rather than two outer joins so it composes with the other
    criteria as a plain WHERE term. ``ck_point_ledger_entry_kind`` guarantees
    exactly one of the two source columns is set on any row, so the disjunction
    selects and never double-counts.
    """

    def predicate(self, table: sa.Table, subject_id: uuid.UUID) -> sa.ColumnElement[bool]:
        """Rows whose attendance or whose redemption belongs to ``subject_id``."""
        attended = sa.select(schema.attendance_record.c.id).where(
            schema.attendance_record.c.subject_id == subject_id
        )
        redeemed = sa.select(schema.redemption.c.id).where(
            schema.redemption.c.subject_id == subject_id
        )
        return sa.or_(
            table.c.source_attendance_id.in_(attended),
            table.c.source_redemption_id.in_(redeemed),
        )


@dataclass(frozen=True, slots=True)
class PortalSurface:
    """One screen a demo principal lands on, and whose rows must be behind it.

    The second class of hollowness, and the one a row count alone cannot see.
    :data:`COUNTED_TABLES` answers "is this table empty for the pilot tenant?".
    That question has a healthy answer for ``point_ledger_entry`` — 182 rows —
    while the student portal is still blank, because every one of those rows
    belongs to a ``synthetic-student:*`` account and the person signing in is
    ``student@``. Several surfaces are scoped by ``principal.user_id`` and not
    by unit, so for those the owner *is* the question.

    Attributes:
        token: The ``SMARTMATCH_DEV_PRINCIPALS`` bearer that opens this portal
            on a token-driven stack. Recorded so
            ``tests/unit/test_demo_portal_surfaces.py`` can compare this table
            against ``seed_pilot_principals.COMPOSE_DEV_PRINCIPALS`` and fail on
            a principal with no declared surface at all.
        role: The ``membership.role`` whose account owns this surface. A role
            and not a subject string, because which *account* holds that role
            depends on whether the stack is being driven by logins or by bearer
            tokens — see :data:`SUBJECT_SETS`. Resolving late is what makes
            ``--subjects`` a real switch rather than a documented warning.
        surface: The screen, in the words a reader of the report would use.
            Documentation for the operator; it scopes nothing.
        table: The table behind that screen, from the shipped metadata for
            :class:`CountedTable`'s reason.
        owner: How this table attaches a row to a person, or ``None`` for a
            surface scoped by unit alone, where membership rather than
            authorship decides who sees the rows.
        unit_column: The owning-unit column, or ``None`` for tenant-wide.
            Three spellings are in use across the schema, so it is recorded per
            surface rather than guessed.
        minimum_rows: The floor below which this surface is reported as thin.
            A floor and never a target: it is the number under which a reviewer
            clicking this page would see something they would call broken. One
            row is a list with one row in it.
        writer: What fills it, printed beside the count.
    """

    token: str
    role: str
    surface: str
    table: sa.Table
    owner: OwnerScope | None
    unit_column: str | None
    minimum_rows: int
    writer: str


#: Every demo portal's primary surfaces, with the role whose rows must be there.
#:
#: "Primary" is the screen the portal lands on and the screen it exists for, not
#: every table a route touches. A portal is not demonstrable because its API
#: answers ``200``; it is demonstrable when the person who signs in sees rows.
#:
#: The ``owner`` entries are the ones that were invisibly empty. Each names a
#: *role*, resolved against :data:`SUBJECT_SETS` at count time and defaulting to
#: the ``pilot-login-*`` accounts the browser logins resolve to — *not* the
#: ``synthetic-student:*`` accounts the generator writes under, and no longer
#: the ``compose-pilot-*`` fixtures either, which is the whole point of
#: recording an owner here rather than trusting a tenant-wide count.
DEMO_PORTAL_SURFACES: Final[tuple[PortalSurface, ...]] = (
    # Coordinator — the Speaker Request queue, the runs it drives, the meetings
    # page. All unit-scoped: a coordinator sees their unit's rows, not their own.
    PortalSurface(
        token="compose-api",
        role="coordinator",
        surface="Speaker Request queue",
        table=schema.event,
        owner=None,
        unit_column="host_org_unit_id",
        minimum_rows=10,
        writer="generator Phase A/B",
    ),
    PortalSurface(
        token="compose-api",
        role="coordinator",
        surface="Speaker Request targets (§7/§8)",
        table=schema.speaker_request_classification,
        owner=None,
        unit_column=None,
        minimum_rows=10,
        writer="generator Phase A (request)",
    ),
    PortalSurface(
        token="compose-api",
        role="coordinator",
        surface="Match runs",
        table=schema.match_run,
        owner=None,
        unit_column="owning_unit_id",
        minimum_rows=1,
        writer="generator Phase A (match runs)",
    ),
    PortalSurface(
        token="compose-api",
        role="coordinator",
        surface="Speaker contacts",
        table=schema.contact_channel,
        owner=None,
        unit_column="owning_unit_id",
        minimum_rows=10,
        writer="generator Phase A (review accept)",
    ),
    PortalSurface(
        token="compose-api",
        role="coordinator",
        surface="Meetings with the CBA team",
        table=schema.cba_meeting,
        owner=None,
        unit_column="owning_unit_id",
        minimum_rows=1,
        writer="make top-up-pilot-dataset (seed-pilot-engagement)",
    ),
    # Student — every one of these is scoped by `principal.user_id`, and every
    # one of them was empty for the demo login while the tenant-wide count was
    # healthy. This block is the ownership trap, written down.
    PortalSurface(
        token="compose-student",
        role="student",
        surface="My agenda (attended)",
        table=schema.attendance_record,
        owner=OwnedByColumn("subject_id"),
        unit_column="owning_unit_id",
        minimum_rows=3,
        writer="make top-up-pilot-dataset (seed-pilot-engagement)",
    ),
    PortalSurface(
        token="compose-student",
        role="student",
        surface="My agenda (registered)",
        table=schema.event_registration,
        owner=OwnedByColumn("subject_id"),
        unit_column="owning_unit_id",
        minimum_rows=2,
        writer="make top-up-pilot-dataset (seed-pilot-engagement)",
    ),
    PortalSurface(
        token="compose-student",
        role="student",
        surface="Points balance",
        table=schema.point_ledger_entry,
        # Not a column. See OwnedByLedgerCause: this table names its cause and
        # the cause names the student, and the two column spellings that look
        # like an owner (`subject_id`, `actor_id`) are respectively absent and
        # NULL for every derived credit.
        owner=OwnedByLedgerCause(),
        unit_column=None,
        minimum_rows=3,
        writer="make top-up-pilot-dataset (seed-pilot-engagement)",
    ),
    PortalSurface(
        token="compose-student",
        role="student",
        surface="My redemptions",
        table=schema.redemption,
        owner=OwnedByColumn("subject_id"),
        unit_column=None,
        minimum_rows=2,
        writer="make top-up-pilot-dataset (seed-pilot-engagement)",
    ),
    PortalSurface(
        token="compose-student",
        role="student",
        surface="Speakers I rated",
        table=schema.student_speaker_feedback,
        owner=OwnedByColumn("student_id"),
        unit_column="owning_unit_id",
        minimum_rows=1,
        writer="make top-up-pilot-dataset (student feedback, through the API)",
    ),
    # Event Host — one read route and one predicate on it,
    # `filed_by_user_id == principal.user_id` (OQ-CBA-014). The generator files
    # every request with the *coordinator* token, so this surface is empty by
    # construction however many requests exist.
    PortalSurface(
        token="compose-host",
        role="volunteer",
        surface="My filed Speaker Requests",
        table=schema.event,
        owner=OwnedByColumn("filed_by_user_id"),
        unit_column="host_org_unit_id",
        minimum_rows=1,
        writer="make top-up-pilot-dataset (seed-pilot-engagement)",
    ),
    # Administration — the meetings page (#130) and the catalog whose budget
    # this account owns. Both unit- or tenant-scoped; `reward_item` carries a
    # `budget_owner_id`, which is an accountability record and not a read scope,
    # so it is not an `owner` here.
    PortalSurface(
        token="compose-admin",
        role="admin",
        surface="Meetings with the CBA team",
        table=schema.cba_meeting,
        owner=None,
        unit_column="owning_unit_id",
        minimum_rows=1,
        writer="make top-up-pilot-dataset (seed-pilot-engagement)",
    ),
    PortalSurface(
        token="compose-admin",
        role="admin",
        surface="Rewards catalog",
        table=schema.reward_item,
        owner=None,
        unit_column=None,
        minimum_rows=3,
        writer="make top-up-pilot-dataset (seed-pilot-rewards worksheet rows)",
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
    minimum_rows: int
    writer: str

    @property
    def empty(self) -> bool:
        """Whether this surface holds nothing for the person the portal is for."""
        return self.rows == 0

    @property
    def short(self) -> bool:
        """Whether this surface is below its floor — empty included."""
        return self.rows < self.minimum_rows


# ---------------------------------------------------------------------------
# The third pass: does every row point at a row that exists?
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CheckResult:
    """One cross-table question and the two numbers that answer it.

    Attributes:
        name: A stable identifier, so a failure can be grepped for.
        question: The property in a sentence, as the report prints it.
        population: How many rows the question is *about*. Zero is a failure in
            its own right and is reported as ``VACUOUS``: a rule about rows that
            do not exist is satisfied by nothing having happened, which is
            precisely the state this tool exists to refuse to call healthy.
        violations: How many of them break it.
        remedy: What an operator does about it.
    """

    name: str
    question: str
    population: int
    violations: int
    remedy: str

    @property
    def vacuous(self) -> bool:
        """Whether the question was asked of no rows at all."""
        return self.population == 0

    @property
    def failed(self) -> bool:
        """Whether this check is a finding: a violation, or nothing to check."""
        return self.vacuous or self.violations > 0

    @property
    def verdict(self) -> str:
        """``OK``, ``VACUOUS`` or ``BROKEN``, for the printed column."""
        if self.vacuous:
            return "VACUOUS"
        return "BROKEN" if self.violations else "OK"


def _scope(
    table: sa.Table, *, tenant_id: uuid.UUID, unit_id: uuid.UUID, unit_column: str | None
) -> list[sa.ColumnElement[bool]]:
    """Tenant always, unit where the table carries one. Never guessed."""
    criteria: list[sa.ColumnElement[bool]] = [table.c.tenant_id == tenant_id]
    if unit_column is not None:
        criteria.append(table.c[unit_column] == unit_id)
    return criteria


@dataclass(frozen=True, slots=True)
class ReferenceCheck:
    """ "Every row of ``table`` names a row of ``target``" — the common shape.

    Most of what makes a dataset *connected* rather than merely *present* is
    this one property repeated: a foreign key the schema does not enforce, or
    enforces only within a tenant, and which a seeding tool can therefore leave
    dangling. Written once as a factory rather than a dozen times as SQL,
    because a dozen hand-written ``NOT EXISTS`` clauses is a dozen chances to
    scope one of them to the wrong tenant.

    Attributes:
        column: The referencing column on :attr:`table`.
        target_column: The referenced column on :attr:`target`.
        target_unit_column: When set, the referenced row must also belong to the
            same unit — "a speaker on *this* unit's roster", not any speaker.
        cast_target_to_text: ``match_run.event_need_id`` is ``sa.Text`` and
            deliberately not a foreign key (it is a need identifier, not an
            event id, in the domain's own terms). The pilot generator puts an
            event id in it, so the correlation is real and is checked — as a
            text comparison, which is what the column is.
        nullable: Skip rows whose :attr:`column` is NULL. A NULL is "nobody has
            said", which is a state, not a dangling reference.
    """

    name: str
    question: str
    remedy: str
    table: sa.Table
    unit_column: str | None
    column: str
    target: sa.Table
    target_column: str
    target_unit_column: str | None = None
    cast_target_to_text: bool = False
    nullable: bool = False

    def counts(self, session: Session, *, tenant_id: uuid.UUID, unit_id: uuid.UUID) -> CheckResult:
        """Population and violations, in two counts over the same scope."""
        scope = _scope(
            self.table, tenant_id=tenant_id, unit_id=unit_id, unit_column=self.unit_column
        )
        source = self.table.c[self.column]
        if self.nullable:
            scope.append(source.is_not(None))

        target_key: sa.ColumnElement[object] = self.target.c[self.target_column]
        if self.cast_target_to_text:
            target_key = sa.cast(target_key, sa.Text)
        resolves = sa.select(sa.literal(1)).where(
            self.target.c.tenant_id == tenant_id,
            target_key == source,
            *(
                [self.target.c[self.target_unit_column] == unit_id]
                if self.target_unit_column is not None
                else []
            ),
        )

        population = session.execute(
            sa.select(sa.func.count()).select_from(self.table).where(*scope)
        ).scalar_one()
        violations = session.execute(
            sa.select(sa.func.count()).select_from(self.table).where(*scope, ~resolves.exists())
        ).scalar_one()
        return CheckResult(
            name=self.name,
            question=self.question,
            population=int(population),
            violations=int(violations),
            remedy=self.remedy,
        )


@dataclass(frozen=True, slots=True)
class JoinCheck:
    """A cross-table property whose SQL is its own: two counts, supplied.

    For the questions :class:`ReferenceCheck` cannot phrase — the ones with a
    correlated subquery two tables deep, or a predicate over a *pair* of
    columns. ``population`` and ``violations`` are each a ``SELECT count(*)``
    built from ``(tenant_id, unit_id)``, so the scope stays the caller's and not
    the closure's.
    """

    name: str
    question: str
    remedy: str
    population_query: object
    violations_query: object

    def counts(self, session: Session, *, tenant_id: uuid.UUID, unit_id: uuid.UUID) -> CheckResult:
        """Run both supplied counts over this tenant and unit."""
        population = session.execute(
            self.population_query(tenant_id, unit_id)  # type: ignore[operator]
        ).scalar_one()
        violations = session.execute(
            self.violations_query(tenant_id, unit_id)  # type: ignore[operator]
        ).scalar_one()
        return CheckResult(
            name=self.name,
            question=self.question,
            population=int(population),
            violations=int(violations),
            remedy=self.remedy,
        )


def _events_with_a_match_run(tenant_id: uuid.UUID, unit_id: uuid.UUID) -> sa.Select:
    """Count the unit's events that a match run was driven from."""
    run = sa.select(sa.literal(1)).where(
        schema.match_run.c.tenant_id == tenant_id,
        schema.match_run.c.owning_unit_id == unit_id,
        schema.match_run.c.event_need_id == sa.cast(schema.event.c.id, sa.Text),
    )
    return (
        sa.select(sa.func.count())
        .select_from(schema.event)
        .where(
            schema.event.c.tenant_id == tenant_id,
            schema.event.c.host_org_unit_id == unit_id,
            run.exists(),
        )
    )


def _events_with_a_run_but_no_invitation(tenant_id: uuid.UUID, unit_id: uuid.UUID) -> sa.Select:
    """Of those, count the ones no invitation was ever composed for."""
    run = sa.select(sa.literal(1)).where(
        schema.match_run.c.tenant_id == tenant_id,
        schema.match_run.c.owning_unit_id == unit_id,
        schema.match_run.c.event_need_id == sa.cast(schema.event.c.id, sa.Text),
    )
    invited = (
        sa.select(sa.literal(1))
        .select_from(
            schema.cba_invitation.join(
                schema.cba_invitation_batch,
                schema.cba_invitation_batch.c.id == schema.cba_invitation.c.batch_id,
            ).join(
                schema.match_run,
                schema.match_run.c.id == schema.cba_invitation_batch.c.match_run_id,
            )
        )
        .where(
            schema.cba_invitation.c.tenant_id == tenant_id,
            schema.match_run.c.owning_unit_id == unit_id,
            schema.match_run.c.event_need_id == sa.cast(schema.event.c.id, sa.Text),
        )
    )
    return (
        sa.select(sa.func.count())
        .select_from(schema.event)
        .where(
            schema.event.c.tenant_id == tenant_id,
            schema.event.c.host_org_unit_id == unit_id,
            run.exists(),
            ~invited.exists(),
        )
    )


def _feedback_rows(tenant_id: uuid.UUID, unit_id: uuid.UUID) -> sa.Select:
    """Count this unit's student ratings."""
    return (
        sa.select(sa.func.count())
        .select_from(schema.student_speaker_feedback)
        .where(
            schema.student_speaker_feedback.c.tenant_id == tenant_id,
            schema.student_speaker_feedback.c.owning_unit_id == unit_id,
        )
    )


def _feedback_without_attendance(tenant_id: uuid.UUID, unit_id: uuid.UUID) -> sa.Select:
    """Ratings with no attendance record behind them, by student *and* event.

    The pair is the point. A rating whose student attended *some* event and
    whose event *somebody* attended is still a rating nobody was entitled to
    write; ``StudentSpeakerFeedbackRepository.eligibility`` checks the pair, and
    so does this.
    """
    attended = sa.select(sa.literal(1)).where(
        schema.attendance_record.c.tenant_id == tenant_id,
        schema.attendance_record.c.subject_id == schema.student_speaker_feedback.c.student_id,
        schema.attendance_record.c.event_id == schema.student_speaker_feedback.c.event_id,
    )
    return (
        sa.select(sa.func.count())
        .select_from(schema.student_speaker_feedback)
        .where(
            schema.student_speaker_feedback.c.tenant_id == tenant_id,
            schema.student_speaker_feedback.c.owning_unit_id == unit_id,
            ~attended.exists(),
        )
    )


def _ledger_rows(tenant_id: uuid.UUID, unit_id: uuid.UUID) -> sa.Select:
    """Count the tenant's ledger entries. Tenant-wide: the table carries no unit."""
    del unit_id
    return (
        sa.select(sa.func.count())
        .select_from(schema.point_ledger_entry)
        .where(schema.point_ledger_entry.c.tenant_id == tenant_id)
    )


def _ledger_without_a_cause(tenant_id: uuid.UUID, unit_id: uuid.UUID) -> sa.Select:
    """Ledger entries whose named cause is not there.

    ADR-0013: points derive from recorded attendance and nothing else, and a
    debit derives from a redemption. ``ck_point_ledger_entry_kind`` makes
    exactly one of the two source columns non-NULL per row, so an entry whose
    non-NULL source resolves to nothing is a balance with no history behind it —
    the legacy defect ADR-0013 exists to have removed.
    """
    del unit_id
    attendance = sa.select(sa.literal(1)).where(
        schema.attendance_record.c.tenant_id == tenant_id,
        schema.attendance_record.c.id == schema.point_ledger_entry.c.source_attendance_id,
    )
    redemption = sa.select(sa.literal(1)).where(
        schema.redemption.c.tenant_id == tenant_id,
        schema.redemption.c.id == schema.point_ledger_entry.c.source_redemption_id,
    )
    return (
        sa.select(sa.func.count())
        .select_from(schema.point_ledger_entry)
        .where(
            schema.point_ledger_entry.c.tenant_id == tenant_id,
            sa.or_(
                sa.and_(
                    schema.point_ledger_entry.c.source_attendance_id.is_not(None),
                    ~attendance.exists(),
                ),
                sa.and_(
                    schema.point_ledger_entry.c.source_redemption_id.is_not(None),
                    ~redemption.exists(),
                ),
                sa.and_(
                    schema.point_ledger_entry.c.source_attendance_id.is_(None),
                    schema.point_ledger_entry.c.source_redemption_id.is_(None),
                ),
            ),
        )
    )


#: Every cross-table property this tool asserts, in the order a reader would ask
#: them: the match funnel first, then the people surfaces, then the ledger.
#:
#: Each is a question with a population. A check whose population is zero is a
#: failure, and that is the difference between this pass and the two above it: a
#: dataset can satisfy every count and every ownership floor and still be a set
#: of unrelated islands, and the only way to tell is to ask a question that
#: needs two tables to answer.
CROSS_TABLE_CHECKS: Final[tuple[ReferenceCheck | JoinCheck, ...]] = (
    JoinCheck(
        name="event_with_a_match_run_has_invitations",
        question="every event a match run was driven from has invitations composed for it",
        remedy="the generator's invitation phase did not run for this event; see its report",
        population_query=_events_with_a_match_run,
        violations_query=_events_with_a_run_but_no_invitation,
    ),
    ReferenceCheck(
        name="match_run_names_a_real_event",
        question="every match run's event_need_id names an event in this tenant",
        remedy="a run was written against an event that does not exist; regenerate",
        table=schema.match_run,
        unit_column="owning_unit_id",
        column="event_need_id",
        target=schema.event,
        target_column="id",
        cast_target_to_text=True,
    ),
    ReferenceCheck(
        name="invitation_belongs_to_a_batch",
        question="every invitation belongs to an invitation batch",
        remedy="an invitation was written without its batch; regenerate",
        table=schema.cba_invitation,
        unit_column="owning_unit_id",
        column="batch_id",
        target=schema.cba_invitation_batch,
        target_column="id",
    ),
    ReferenceCheck(
        name="invitation_batch_names_a_match_run",
        question="every invitation batch names the match run it was composed from",
        remedy="a batch was written without its run; regenerate",
        table=schema.cba_invitation_batch,
        unit_column="owning_unit_id",
        column="match_run_id",
        target=schema.match_run,
        target_column="id",
    ),
    ReferenceCheck(
        name="invitation_names_a_roster_speaker",
        question="every invitation names a speaker on this unit's §13 roster",
        remedy="an invitation names a professional with no speaker_profile here; regenerate",
        table=schema.cba_invitation,
        unit_column="owning_unit_id",
        column="professional_id",
        target=schema.speaker_profile,
        target_column="professional_id",
        target_unit_column="owning_unit_id",
    ),
    ReferenceCheck(
        name="contact_channel_names_a_roster_speaker",
        question="every contact channel belongs to a speaker on this unit's roster",
        remedy="a channel outlived its speaker profile; regenerate",
        table=schema.contact_channel,
        unit_column="owning_unit_id",
        column="professional_id",
        target=schema.speaker_profile,
        target_column="professional_id",
        target_unit_column="owning_unit_id",
    ),
    ReferenceCheck(
        name="pipeline_record_names_an_event",
        question="every pipeline record names the event it is a journey towards",
        remedy="a journey outlived its event; regenerate",
        table=schema.pipeline_record,
        unit_column="owning_unit_id",
        column="opportunity_event_id",
        target=schema.event,
        target_column="id",
    ),
    ReferenceCheck(
        name="attendance_names_an_event",
        question="every attendance record names an event in this tenant",
        remedy="attendance was recorded against a missing event; regenerate",
        table=schema.attendance_record,
        unit_column="owning_unit_id",
        column="event_id",
        target=schema.event,
        target_column="id",
    ),
    ReferenceCheck(
        name="attendance_names_an_account",
        question="every attendance record names a user_account in this tenant",
        remedy="attendance was recorded for a subject with no account; regenerate",
        table=schema.attendance_record,
        unit_column="owning_unit_id",
        column="subject_id",
        target=schema.user_account,
        target_column="id",
    ),
    ReferenceCheck(
        name="registration_names_an_event",
        question="every event registration names an event in this tenant",
        remedy="run `make top-up-pilot-dataset`; a registration outlived its event",
        table=schema.event_registration,
        unit_column="owning_unit_id",
        column="event_id",
        target=schema.event,
        target_column="id",
    ),
    ReferenceCheck(
        name="registration_names_an_account",
        question="every event registration names a user_account in this tenant",
        remedy="run `make top-up-pilot-dataset`",
        table=schema.event_registration,
        unit_column="owning_unit_id",
        column="subject_id",
        target=schema.user_account,
        target_column="id",
    ),
    ReferenceCheck(
        name="feedback_names_an_event",
        question="every student rating names the event it was given at",
        remedy="run `make top-up-pilot-dataset`; a rating outlived its event",
        table=schema.student_speaker_feedback,
        unit_column="owning_unit_id",
        column="event_id",
        target=schema.event,
        target_column="id",
    ),
    ReferenceCheck(
        name="feedback_names_a_roster_speaker",
        question="every student rating names a speaker on this unit's §13 roster",
        remedy="run `make top-up-pilot-dataset`; a rating names a speaker who is not here",
        table=schema.student_speaker_feedback,
        unit_column="owning_unit_id",
        column="speaker_professional_id",
        target=schema.speaker_profile,
        target_column="professional_id",
        target_unit_column="owning_unit_id",
    ),
    ReferenceCheck(
        name="feedback_names_a_student_account",
        question="every student rating names a user_account in this tenant",
        remedy="run `make top-up-pilot-dataset`",
        table=schema.student_speaker_feedback,
        unit_column="owning_unit_id",
        column="student_id",
        target=schema.user_account,
        target_column="id",
    ),
    JoinCheck(
        name="feedback_is_backed_by_attendance",
        question="every student rating is backed by that student's attendance at that event",
        remedy=(
            "run `make top-up-pilot-dataset`; a rating written around the route's "
            "eligibility check is the defect POST .../student/.../feedback prevents"
        ),
        population_query=_feedback_rows,
        violations_query=_feedback_without_attendance,
    ),
    JoinCheck(
        name="ledger_entry_has_a_cause",
        question="every point ledger entry names an attendance or a redemption that exists",
        remedy="run `make top-up-pilot-dataset`; a balance with no history is ADR-0013's defect",
        population_query=_ledger_rows,
        violations_query=_ledger_without_a_cause,
    ),
    ReferenceCheck(
        name="redemption_names_a_catalog_item",
        question="every redemption names a reward_item in this tenant",
        remedy="run `make top-up-pilot-dataset`; the catalog is seeded from the worksheet",
        table=schema.redemption,
        unit_column=None,
        column="item_id",
        target=schema.reward_item,
        target_column="id",
        nullable=True,
    ),
    ReferenceCheck(
        name="redemption_names_an_account",
        question="every redemption names a user_account in this tenant",
        remedy="run `make top-up-pilot-dataset`",
        table=schema.redemption,
        unit_column=None,
        column="subject_id",
        target=schema.user_account,
        target_column="id",
    ),
    ReferenceCheck(
        name="meeting_names_its_author",
        question="every meeting names the account that recorded it",
        remedy="run `make top-up-pilot-dataset`",
        table=schema.cba_meeting,
        unit_column="owning_unit_id",
        column="created_by_user_id",
        target=schema.user_account,
        target_column="id",
        nullable=True,
    ),
    ReferenceCheck(
        name="reward_item_names_a_budget_owner",
        question="every reward item names the account accountable for its budget",
        remedy="run `make top-up-pilot-dataset`; D6 forbids an ownerless catalog row",
        table=schema.reward_item,
        unit_column=None,
        column="budget_owner_id",
        target=schema.user_account,
        target_column="id",
        nullable=True,
    ),
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
        criteria = _scope(
            entry.table, tenant_id=tenant_id, unit_id=unit_id, unit_column=entry.unit_column
        )
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
    subjects: Mapping[str, str] = LOGIN_SUBJECT_SET,
    surfaces: Sequence[PortalSurface] = DEMO_PORTAL_SURFACES,
) -> tuple[SurfaceCount, ...]:
    """Count each demo portal's primary surfaces **as the person who signs in**.

    The difference from :func:`count_dataset` is one predicate, and it is the
    whole reason this function exists: where a surface carries an ``owner``, the
    count is filtered to the ``user_account`` that surface's role resolves to
    under ``subjects``. A tenant-wide count of ``point_ledger_entry`` says 182
    and the student's screen says nothing, because all 182 belong to accounts
    nobody can sign in as.

    ``subjects`` defaults to :data:`LOGIN_SUBJECT_SET` — the four ``@``-addressed
    browser logins — and that default is the correction this module carries. A
    role with no entry in ``subjects``, and a subject that resolves to no
    ``user_account`` at all, are both reported as **zero rows** rather than
    skipped or raised on. That is a count of rows and not a measurement, so
    ADR-0011 has nothing to say about it: an unseeded principal genuinely has no
    rows, and the report naming the surface and its writer is exactly the
    instruction the operator needs.
    """
    resolved: dict[str, uuid.UUID | None] = {}
    counted: list[SurfaceCount] = []
    for surface in surfaces:
        criteria = _scope(
            surface.table, tenant_id=tenant_id, unit_id=unit_id, unit_column=surface.unit_column
        )

        if surface.owner is not None:
            subject = subjects.get(surface.role)
            if subject is None:
                counted.append(
                    SurfaceCount(
                        token=surface.token,
                        surface=surface.surface,
                        name=surface.table.name,
                        owner=f"(no {surface.role} subject declared)",
                        rows=0,
                        minimum_rows=surface.minimum_rows,
                        writer=surface.writer,
                    )
                )
                continue
            if subject not in resolved:
                found = session.execute(
                    sa.select(schema.user_account.c.id).where(
                        schema.user_account.c.tenant_id == tenant_id,
                        schema.user_account.c.external_subject == subject,
                    )
                ).scalar_one_or_none()
                resolved[subject] = None if found is None else uuid.UUID(str(found))
            subject_id = resolved[subject]
            if subject_id is None:
                counted.append(
                    SurfaceCount(
                        token=surface.token,
                        surface=surface.surface,
                        name=surface.table.name,
                        owner=f"{subject} (NO ACCOUNT)",
                        rows=0,
                        minimum_rows=surface.minimum_rows,
                        writer=surface.writer,
                    )
                )
                continue
            criteria.append(surface.owner.predicate(surface.table, subject_id))

        rows = session.execute(
            sa.select(sa.func.count()).select_from(surface.table).where(*criteria)
        ).scalar_one()
        counted.append(
            SurfaceCount(
                token=surface.token,
                surface=surface.surface,
                name=surface.table.name,
                owner=(
                    subjects.get(surface.role, surface.role)
                    if surface.owner is not None
                    else "(unit-scoped)"
                ),
                rows=int(rows),
                minimum_rows=surface.minimum_rows,
                writer=surface.writer,
            )
        )
    return tuple(counted)


def run_checks(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    checks: Sequence[ReferenceCheck | JoinCheck] = CROSS_TABLE_CHECKS,
) -> tuple[CheckResult, ...]:
    """Answer every cross-table question, in declaration order."""
    return tuple(check.counts(session, tenant_id=tenant_id, unit_id=unit_id) for check in checks)


def check_report_lines(results: Sequence[CheckResult]) -> tuple[str, ...]:
    """The join table: verdict, the two numbers, and the question in words.

    The numbers are printed even when the verdict is ``OK``, for the reason the
    counts above are: "every invitation names a roster speaker" over nine
    invitations and over nine hundred are the same verdict about very different
    datasets, and a reviewer deciding whether a demo is worth giving needs the
    population as much as the pass.
    """
    if not results:
        return ()
    name_width = max(len(result.name) for result in results)
    return tuple(
        f"  {result.verdict:<7}  {result.name:<{name_width}}  "
        f"{result.violations:>6} bad / {result.population:>6} rows  {result.question}"
        for result in results
    )


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
        if count.empty:
            flag = "EMPTY  "
        elif count.short:
            flag = "THIN   "
        else:
            flag = "       "
        lines.append(
            f"  {count.token:<{token_width}}  {count.surface:<{surface_width}}  "
            f"{count.owner:<{owner_width}}  {count.rows:>7}/{count.minimum_rows:<3}  "
            f"{flag}{count.writer}"
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
    parser.add_argument(
        "--subjects",
        choices=sorted(SUBJECT_SETS),
        default=DEFAULT_SUBJECT_SET,
        help=(
            "Which family of account owns the person-scoped surfaces. 'login' (the "
            "default) is the four pilot-login-* accounts a reviewer signs in as; "
            "'fixture' is the compose-pilot-* accounts the local SMARTMATCH_DEV_PRINCIPALS "
            "bearer tokens resolve to, for a stack driven by tokens and no browser."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Print the three tables and exit non-zero on any finding.

    Three distinguishable failures, three distinguishable exits: ``2`` for a
    configuration refusal (this is not a dev fixture appliance), ``1`` for a
    missing tenant or unit or a database that could not be read, and ``1`` again
    for the findings this tool exists for — an empty table, a portal surface
    below its floor, or a cross-table property that is broken or that no row
    exists to satisfy. Each is printed by name with the writer or the remedy
    beside it, because "the dataset is incomplete" without that list is a
    sentence nobody can act on.
    """
    args = parse_args(argv)
    try:
        settings = require_development_fixture_settings(Settings())
    except SeedConfigurationError as exc:
        print(f"verify-pilot-dataset: configuration error: {exc}", file=sys.stderr)
        return 2

    subjects = subjects_for(args.subjects)
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
            surfaces = count_portal_surfaces(
                session, tenant_id=tenant_id, unit_id=unit_id, subjects=subjects
            )
            checks = run_checks(session, tenant_id=tenant_id, unit_id=unit_id)
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
    print(
        "verify-pilot-dataset: per-portal surfaces, counted as the account that signs in "
        f"(--subjects {args.subjects}: {', '.join(sorted(subjects.values()))})"
    )
    for line in portal_report_lines(surfaces):
        print(line)

    print("")
    print("verify-pilot-dataset: cross-table checks (rows that point at rows)")
    for line in check_report_lines(checks):
        print(line)

    empty = [count for count in counts if count.empty]
    thin_surfaces = [surface for surface in surfaces if surface.short]
    failed_checks = [check for check in checks if check.failed]
    if not empty and not thin_surfaces and not failed_checks:
        print(
            "verify-pilot-dataset: every counted table holds rows, every demo portal's "
            "surfaces clear their floor, and every cross-table check passes."
        )
        return 0

    if empty:
        print("verify-pilot-dataset: INCOMPLETE. These tables hold nothing:", file=sys.stderr)
        for count in empty:
            print(f"  {count.name} — filled by {count.writer}", file=sys.stderr)

    if thin_surfaces:
        # Reported separately, and separately worded, because it is a different
        # defect with a different fix. A table above is empty. A surface here can
        # be empty over a table that is *full* — the rows are there and they
        # belong to somebody nobody can sign in as.
        print(
            "verify-pilot-dataset: INCOMPLETE. These demo portals land on an empty or thin "
            "surface — note that the table above may be full, in which case the rows "
            "exist under an account no demo login resolves to:",
            file=sys.stderr,
        )
        for surface in thin_surfaces:
            print(
                f"  {surface.token} -> {surface.surface} ({surface.name}, owner "
                f"{surface.owner}) has {surface.rows} of {surface.minimum_rows} — "
                f"filled by {surface.writer}",
                file=sys.stderr,
            )

    if failed_checks:
        # The third and newest wording. A count says a table is empty; a surface
        # says a person owns nothing; this says the rows are there, belong to the
        # right people, and do not refer to each other.
        print(
            "verify-pilot-dataset: DISCONNECTED. These cross-table properties do not hold "
            "(VACUOUS means no row exists for the question to be about, which a dataset "
            "meant to demonstrate the property does not get to call a pass):",
            file=sys.stderr,
        )
        for check in failed_checks:
            print(
                f"  {check.verdict} {check.name}: {check.question} — "
                f"{check.violations} violating of {check.population} rows. {check.remedy}",
                file=sys.stderr,
            )

    print(
        "verify-pilot-dataset: a demo run over this database will show empty or disconnected "
        "surfaces, not unknown values. Top up an existing tenant with "
        "`make top-up-pilot-dataset`; rebuild a fresh one with "
        "scripts/reset_pilot_dataset.sh.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
