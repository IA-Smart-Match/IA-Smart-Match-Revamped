"""The Event Host's own organization, modelled but not yet enforced against.

PR #154 close-out, PLAN v2 finding 10, owner decision 4 (posted on the PR):
"organization modelled now, enforcement per-user". Two new tables and one new
nullable column, and the second half of that sentence is the part this
docstring exists to make unmissable.

What an organization is here
============================
``host_org_unit_id`` on ``event`` (migration ``0017``, ADR-0012) is the
*institution's* org unit — the department inside Smart Match that a request is
filed under and authorized against. It is not the host's own organization: an
accounting student society and a dean's office both file into the same unit,
and nothing in the schema could tell them apart.

``host_organization`` is that missing thing: the club, department or office an
Event Host says they are asking on behalf of. It is a **self-asserted** record
by default — a host types it, nobody approves it — and
``host_organization_member.granted_by_user_id`` is where that distinction is
stored: ``NULL`` means the member asserted their own place in the organization,
and a non-NULL value names the coordinator who granted it. Nothing in this
revision writes a non-NULL value; the column exists so that the day a
coordinator grants membership, a granted row is distinguishable from an
asserted one rather than being indistinguishable after the fact (ADR-0011
rule 1, the same reason ``0033`` declined to backfill a filer).

**No authorization reads any of this.** Every route that decides whose rows a
caller may see still decides it per user, through ``event.filed_by_user_id``
(``0033``). Adding a table that *looks* like a tenancy boundary without making
it one is a real risk, so it is stated here and asserted in
``tests/integration/test_host_organization_migration.py``: an organization does
not widen anybody's reach, and the day it should, that is a deliberate change
to a route's predicate and not a consequence of this revision.

One organization per host
=========================
``host_organization_member`` carries ``unit_id`` alongside ``organization_id``,
which looks redundant — the organization already has one. It is not redundant,
and it is not denormalisation for speed. It is what lets

    UNIQUE (user_id)

mean what it says. A host belongs to **one** organization at a time -- not one
per unit -- and that is what makes "the caller's organization" a well-defined
phrase on ``GET/PUT /v1/units/{unit_id}/host/organization``. ``unit_id`` on the
member row is then the unit that organization files into, carried here so the
unit-scoped routes can answer without a join and, more importantly, so it
cannot drift: the composite foreign key ``(tenant_id, organization_id,
unit_id) -> host_organization (tenant_id, id, unit_id)`` makes a member row
that disagreed with its organization about the unit unrepresentable, rather
than something a repository has to remember to check.

The consequence is deliberate and is what the routes implement: a host whose
one organization sits in another department gets ``404`` from this unit's
``GET`` (they have no organization *here*) and ``409`` from its ``PUT``, which
names the conflict instead of silently re-homing them.

``host_organization`` additionally carries a **case-folded unique name per
unit** (``uq_host_organization_unit_name`` on ``(tenant_id, unit_id,
lower(name))``): two hosts typing "Accounting Society" into the same
department are describing one club, and two rows for it would split its
requests with nothing to say they belong together.

``event.host_organization_id``
==============================
Nullable, never backfilled, and constrained to typed rows exactly as
``filed_by_user_id`` is (``ck_event_host_organization_manual_origin`` mirrors
``ck_event_filed_by_manual_origin``): an extracted event has no host
organization for the same reason it has no filer. ``NULL`` means **no
organization was recorded**, never "the host has none" and never "look it up
from the filer" — a reader that fell back to the filer's *current*
organization would report today's affiliation as the one a request was filed
under, which is a reconstruction indistinguishable from a recorded fact.

Expand-only
===========
Two CREATE TABLEs, one ADD COLUMN (nullable, no default, no backfill), one
CHECK that every existing row satisfies through its ``IS NULL`` arm without
being read, one composite foreign key and two indexes. Nothing existing is
altered in place, dropped, renamed or rewritten — safe under a rolling deploy
per v1.1 §4.2.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0036_host_organization"
down_revision = "0035_manual_event_detail"
branch_labels = None
depends_on = None

#: The mirror of ``0033``'s ``_FILER_ONLY_ON_A_TYPED_ROW``, spelled out here
#: rather than imported for the reason every revision before it gave for its
#: own predicate: a CHECK cannot import Python, and a migration describes the
#: database as of the moment it ran.
_ORGANIZATION_ONLY_ON_A_TYPED_ROW = "host_organization_id IS NULL OR origin = 'coordinator_entry'"


def upgrade() -> None:
    """Create the two organization tables and add ``event.host_organization_id``."""
    op.create_table(
        "host_organization",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        # The institution's org unit this organization files into. An
        # organization is scoped to one unit rather than to the tenant: the
        # routes that read and write it are unit-scoped, and a tenant-wide
        # record would be reachable from a unit nobody authorized the caller
        # against.
        sa.Column("unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        # Every descriptive field below is nullable and none is defaulted. A
        # host who has not said which department they sit in has not said it;
        # an empty string would be a statement they did not make.
        sa.Column("department", sa.Text, nullable=True),
        sa.Column("default_location", sa.Text, nullable=True),
        # Free text a host types about who to reach for logistics. Deliberately
        # NOT a `contact_channel`: nothing in this schema treats it as an
        # address, no outreach path reads it, and it grants no consent.
        sa.Column("logistics_contact", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="host_organization_pkey"),
        # What `host_organization_member` and `event.host_organization_id`
        # reference. Same convention as `uq_event_tenant_id`.
        sa.UniqueConstraint("tenant_id", "id", name="uq_host_organization_tenant_id"),
        # What the member table's composite key references, so a member row
        # cannot disagree with its organization about which unit it is in.
        sa.UniqueConstraint(
            "tenant_id", "id", "unit_id", name="uq_host_organization_tenant_id_unit"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "unit_id"],
            ["org_unit.tenant_id", "org_unit.id"],
            ondelete="RESTRICT",
            name="fk_host_organization_unit",
        ),
        sa.CheckConstraint(
            "length(btrim(name)) > 0 AND length(name) <= 200",
            name="ck_host_organization_name_shape",
        ),
        sa.CheckConstraint(
            "department IS NULL OR length(btrim(department)) > 0",
            name="ck_host_organization_department_shape",
        ),
        sa.CheckConstraint(
            "default_location IS NULL OR length(btrim(default_location)) > 0",
            name="ck_host_organization_default_location_shape",
        ),
        sa.CheckConstraint(
            "logistics_contact IS NULL OR length(btrim(logistics_contact)) > 0",
            name="ck_host_organization_logistics_contact_shape",
        ),
    )
    op.create_index(
        "ix_host_organization_unit",
        "host_organization",
        ["tenant_id", "unit_id", "name"],
    )
    # One organization per name per unit, case-folded. Two hosts who each type
    # "Accounting Society" into the same department are describing the same
    # club, and letting the second create a duplicate would split one
    # organization's requests across two rows with no way to tell they belong
    # together. Functional (``lower(name)``) rather than a plain UNIQUE, so
    # "Accounting Society" and "accounting society" collide, which is the
    # whole point; ``btrim`` is not folded in because
    # ``ck_host_organization_name_shape`` already refuses a blank and the
    # writer stores the trimmed string.
    op.create_index(
        "uq_host_organization_unit_name",
        "host_organization",
        ["tenant_id", "unit_id", sa.text("lower(name)")],
        unique=True,
    )

    op.create_table(
        "host_organization_member",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        # See the module docstring: present so that UNIQUE (tenant_id, unit_id,
        # user_id) below can exist, and kept honest by the composite key to
        # `uq_host_organization_tenant_id_unit`.
        sa.Column("unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        # NULL means self-asserted — the member said so themselves. A non-NULL
        # value names the coordinator who granted the membership. Nothing in
        # this release writes one; the column exists so that when something
        # does, a granted row is distinguishable from an asserted one.
        sa.Column("granted_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("organization_id", "user_id", name="host_organization_member_pkey"),
        # One current organization per account, full stop -- not one per unit.
        # A host belongs to the club they belong to; the row that says so is
        # the same row whichever department they file into, and two
        # simultaneous affiliations would make "the caller's organization" two
        # answers to one question on every route below.
        sa.UniqueConstraint("user_id", name="uq_host_organization_member_user"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "organization_id", "unit_id"],
            [
                "host_organization.tenant_id",
                "host_organization.id",
                "host_organization.unit_id",
            ],
            ondelete="CASCADE",
            name="fk_host_organization_member_organization",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["user_account.tenant_id", "user_account.id"],
            ondelete="RESTRICT",
            name="fk_host_organization_member_user",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "granted_by_user_id"],
            ["user_account.tenant_id", "user_account.id"],
            ondelete="RESTRICT",
            name="fk_host_organization_member_granted_by",
        ),
    )
    op.create_index(
        "ix_host_organization_member_organization",
        "host_organization_member",
        ["tenant_id", "organization_id"],
    )

    # Nullable, no server default, no backfill — `0033`'s reasoning about
    # `filed_by_user_id`, applied to an affiliation instead of an identity.
    op.add_column(
        "event",
        sa.Column("host_organization_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_event_host_organization_manual_origin",
        "event",
        _ORGANIZATION_ONLY_ON_A_TYPED_ROW,
    )
    # Composite, against `uq_host_organization_tenant_id`. A single-column key
    # would accept an organization from another tenant — the row exists, it is
    # simply somebody else's — and tenant isolation in this schema is
    # structural rather than a predicate every reader has to remember.
    op.create_foreign_key(
        "fk_event_host_organization",
        "event",
        "host_organization",
        ["tenant_id", "host_organization_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    """Drop the column, its key and constraint, then the two tables.

    A development tool, not a production rollback path (v1.1 §4.2): running it
    discards every recorded organization and every stamp tying a request to
    one, and there is no second copy of either anywhere. The state it returns
    to is the one before this revision — hosts with no organization and
    requests that name none.
    """
    op.drop_constraint("fk_event_host_organization", "event", type_="foreignkey")
    op.drop_constraint("ck_event_host_organization_manual_origin", "event", type_="check")
    op.drop_column("event", "host_organization_id")
    op.drop_index("ix_host_organization_member_organization", table_name="host_organization_member")
    op.drop_table("host_organization_member")
    op.drop_index("uq_host_organization_unit_name", table_name="host_organization")
    op.drop_index("ix_host_organization_unit", table_name="host_organization")
    op.drop_table("host_organization")
