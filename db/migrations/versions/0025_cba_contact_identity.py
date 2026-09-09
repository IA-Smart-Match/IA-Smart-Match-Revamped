"""Give a CBA speaker contact a name, an employer, and a job title.

Revision ID: 0025_cba_contact_identity
Revises: 0024_cba_classification

``CBA-CONTACT-MANAGEMENT`` implements customer §13's Speaker Connector surface:
a Connector adds a professional contact by hand, reads back the ones their unit
owns, edits them, and corrects a classification the pipeline assigned. Every one
of those five operations has to render a person on a screen, and before this
revision the schema had nothing to render.

Why this is a migration and not a repository
----------------------------------------------
The search was exhaustive rather than impressionistic, because "surely a name
column exists somewhere" is the assumption that would have made this card a
one-file change. It does not. No revision from ``0001`` to ``0024`` creates a
person-name column, a company column, or a job-title column anywhere in the
schema. The only ``title`` in the database is ``event.title``, which is the name
of an event and not of a person. ``speaker_profile`` (``0024``) is the closest
thing to a speaker record and it holds *classification* —
``primary_industry_code``, ``primary_role_code``, ``topic_text``,
``prior_talk``, ``location_city``, ``location_postal_code`` — and no identity at
all, deliberately: it was written to classify a professional the import path had
already created.

The two columns that look like they might serve are both refusals:

* ``user_account.email`` is a contact channel, not a display field, and §13's
  contact-email posture (OQ-CBA-011, ratified withhold) is that a manually
  entered address must not become sendable. Writing a name there is not
  available, and writing a name *anywhere adjacent to* an address is what that
  ruling exists to prevent.
* ``user_account.external_subject`` is an **identity** column — the IdP subject,
  or a derived stand-in ending in ``.invalid`` where no IdP has ever seen the
  person. Since ``0007`` its only uniqueness constraint is
  ``uq_user_account_external_subject``, which is **global** rather than
  tenant-scoped, so writing a display name there would make two unrelated
  tenants' identically named contacts collide outright; and overloading an
  identity key as a label means a person's name change silently re-identifies
  them. ``professionals.py`` keeps the ``.invalid`` placeholder and this
  revision does not touch it.

So the three fields §13 needs go on ``speaker_profile``, which is already keyed
``(tenant_id, professional_id)``, already ``owning_unit_id``-scoped for A5, and
is already the row a Speaker Connector edits.

``full_name`` is ``NOT NULL``; the other two are not
------------------------------------------------------
A speaker record with no name is not a contact — it is a row nobody can act on,
and §13's list surface would render a blank. ``company`` and ``title`` are
genuinely optional: a retired professional, an independent consultant, or a
contact a Connector met before learning where they work are all real §13 cases,
and forcing a value would produce ``"Unknown"`` strings that outlive the
uncertainty that created them.

There is **no backfill**, and none is needed: ``speaker_profile`` is one
revision old and, at the time this lands, is written only by the classification
path, which no shipped release exercises. ``NOT NULL`` with no server default is
therefore safe on an empty table. It is *not* safe on a populated one, and a
deployment that has already begun writing profiles must backfill before applying
this — recorded here rather than guarded, because inventing a placeholder name as
a server default would be exactly the ``"Unknown"`` this paragraph refuses.

Why ``ck_speaker_profile_text_present`` grows rather than gaining a sibling
----------------------------------------------------------------------------
ADR-0011: absent is a value, blank is a writer that forgot. ``company`` and
``title`` are nullable, so ``NULL`` says "nobody told us" and ``''`` says "a form
posted an empty input" — two states a reader cannot tell apart, and only one of
them is true. The existing constraint already makes that distinction for
``topic_text``, ``prior_talk``, ``location_city`` and ``location_postal_code``;
the two new nullable text columns join it rather than getting a constraint of
their own, so ``speaker_profile`` keeps one place that answers "which text
columns refuse blanks" instead of two that could disagree.

``full_name`` is in the same constraint for a different reason: ``NOT NULL``
refuses the absence and says nothing about ``'   '``, which is a name-shaped
value that renders as nothing.

PostgreSQL cannot alter a ``CHECK`` in place, so the constraint is dropped and
recreated under the same name. Both halves are in this revision's transaction
(``transaction_per_migration=True``, ADR-0009), so there is no window in which
the table is unconstrained.

Expand-only, and what it is not
---------------------------------
Three columns and one widened constraint. Nothing is dropped, renamed, or
backfilled, so this is safe under a rolling deploy per v1.1 §4.2 subject to the
empty-table caveat above: the old release does not know the columns exist, and
the only writer that could insert a ``speaker_profile`` row without a
``full_name`` is one that has not shipped.

Deliberately **not** here: no history table, no ``corrected_by``, no
``industry_source`` vocabulary. OQ-CBA-008's interim ruling is current-value
only, and ``0024``'s docstring already states why inventing a provenance
vocabulary by writing a column is the thing ``0012``'s refusal to invent a
``board_role`` vocabulary is the local precedent against. A correction under
this revision is an ``UPDATE`` that bumps ``updated_at``.

Also not here: any uniqueness on ``(tenant_id, owning_unit_id, full_name)``. Two
different people in one unit can share a name, and a database constraint would
turn that into a write the second Connector cannot make at all. The card's answer
is a ``409`` from the create route that names the existing contact and asks which
the caller meant — see **OQ-CBA-017**, which asks whether that stays application
logic or becomes a constraint once the pilot has evidence about how often it
fires.

Open questions this revision leaves open
------------------------------------------
* **OQ-CBA-015** — a manually created contact's email address. §13's create form
  collects one and OQ-CBA-011's ratified posture withholds it, so the API
  recognises the field, never persists it, and reports it back as withheld. No
  column is added here for it, which is the whole point.
* **OQ-CBA-016** — what ``board_role`` a manually created contact's
  ``professional_unit_relationship`` carries. That column is ``NOT NULL`` free
  text and ``0012`` refused to give it a vocabulary, so a create is forced to
  write *something*. Not answerable by DDL in this revision.
* **OQ-CBA-008** — unchanged and still open. This revision stores the current
  value only.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0025_cba_contact_identity"
down_revision = "0024_cba_classification"
branch_labels = None
depends_on = None


#: ``0024``'s four nullable text columns, unchanged. Repeated because the
#: constraint is recreated whole and PostgreSQL has no ``ALTER CHECK``.
_ORIGINAL_TEXT_COLUMNS = (
    "topic_text",
    "prior_talk",
    "location_city",
    "location_postal_code",
)

#: The two this revision adds. Nullable, so each gets the same NULL-or-non-blank
#: arm the four above have.
_NEW_NULLABLE_TEXT_COLUMNS = ("company", "title")


def _blank_free(column: str) -> str:
    """``0024``'s per-column clause, factored so all six read identically."""
    return f"({column} IS NULL OR length(btrim({column})) > 0)"


#: ``full_name`` is NOT NULL, so it has no NULL arm — a whitespace-only name is
#: the only blank it can carry and the constraint refuses exactly that.
_TEXT_PRESENT_CONDITION = " AND ".join(
    ["length(btrim(full_name)) > 0"]
    + [_blank_free(column) for column in (*_ORIGINAL_TEXT_COLUMNS, *_NEW_NULLABLE_TEXT_COLUMNS)]
)

#: ``0024``'s condition verbatim, restored on downgrade. Written out rather than
#: rebuilt from the helper so that a later edit to the helper cannot silently
#: change what rolling this revision back means.
_ORIGINAL_TEXT_PRESENT_CONDITION = (
    "(topic_text IS NULL OR length(btrim(topic_text)) > 0) "
    "AND (prior_talk IS NULL OR length(btrim(prior_talk)) > 0) "
    "AND (location_city IS NULL OR length(btrim(location_city)) > 0) "
    "AND (location_postal_code IS NULL OR length(btrim(location_postal_code)) > 0)"
)


def upgrade() -> None:
    """Add the three §13 identity columns and widen the blank-text constraint."""
    # §13: "Name" — the one field without which the record is not a contact.
    op.add_column("speaker_profile", sa.Column("full_name", sa.Text, nullable=False))
    # §13: "Company" and "Job title". Optional for the reasons in the module
    # docstring; NULL is a real answer and not a gap to be filled in later.
    op.add_column("speaker_profile", sa.Column("company", sa.Text, nullable=True))
    op.add_column("speaker_profile", sa.Column("title", sa.Text, nullable=True))

    # Drop-and-recreate under the same name: PostgreSQL has no ALTER CHECK, and
    # both statements are inside this revision's transaction so the table is
    # never briefly unconstrained.
    op.drop_constraint("ck_speaker_profile_text_present", "speaker_profile", type_="check")
    op.create_check_constraint(
        "ck_speaker_profile_text_present",
        "speaker_profile",
        _TEXT_PRESENT_CONDITION,
    )


def downgrade() -> None:
    """Restore ``0024``'s constraint, then drop the three columns.

    A development tool, not a production rollback path (v1.1 §4.2). Constraint
    before columns, ``0024``'s own ordering argument: dropping a column first
    takes the constraint with it and leaves a name a later revision could not
    reuse without noticing why.
    """
    op.drop_constraint("ck_speaker_profile_text_present", "speaker_profile", type_="check")
    op.create_check_constraint(
        "ck_speaker_profile_text_present",
        "speaker_profile",
        _ORIGINAL_TEXT_PRESENT_CONDITION,
    )
    op.drop_column("speaker_profile", "title")
    op.drop_column("speaker_profile", "company")
    op.drop_column("speaker_profile", "full_name")
