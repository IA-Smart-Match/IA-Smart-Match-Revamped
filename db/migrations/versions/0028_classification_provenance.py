"""Classification provenance — how the current value was set, and by whom.

Revision ID: 0028_classification_provenance
Revises: 0027_match_weight_setting
Create Date: 2026-09-06

``0024`` opened **OQ-CBA-008** in its own docstring and declined to answer it:
"Whether the pilot must also record who classified a speaker, whether the value
was inferred or human-assigned, and what the previous value was, is unanswered
— nobody has stated an audit requirement for it." On 6 September 2026 the
program owner of record answered it: **add provenance, no history.**

This revision is that answer, and the shape of the answer is the whole content
of this docstring. Three columns per axis, six in all, on ``speaker_profile``
beside the two ``0024`` already put there.

The question provenance answers is "can I trust this?", not "what changed?"
---------------------------------------------------------------------------
Customer §19 is a two-step flow — the system assigns an initial Industry and
Role classification, and then "Speaker Connector reviews/corrects
classifications" before "Speaker becomes available for matching". §19 also says
why: "Human correction is required because classification may involve judgment
calls."

So the question a Connector's screen actually raises, standing in front of a
speaker with ``primary_industry_code = '52'``, is **has anybody looked at
this?** A stored code alone cannot answer it. A code the pipeline proposed from
the string ``"Finance"`` in a title column and a code a Connector chose after
reading the person's own account of their work are the same four characters in
the same column, and §19's gate between them is invisible.

``classification_source`` is that gate, made visible. ``classified_by_user_id``
and ``classified_at`` are what make a ``human`` value auditable rather than
merely asserted — "a person reviewed this" is not a claim worth storing if
nobody can be asked which person, or when.

**No history table, and that is a decision.** ``0024`` guessed that if the
answer were yes "the shape is ``contact_channel_transition``'s and it is a
later revision". The answer came back narrower than that guess, deliberately:
the previous value of a classification is not evidence about the current one.
A Connector correcting ``'54'`` to ``'52'`` produces a row whose trustworthiness
is entirely described by "a human set this, on this date" — the ``'54'`` it
replaced adds nothing a reviewer can act on, and a revision table would invite
exactly the audit surface nobody asked for. There is therefore no
``speaker_profile_classification_transition``, no revision rows, and no
previous-value columns. A later card that wants one needs its own stated
requirement, not this revision's silence.

**No ``industry_source`` free-text column either**, which is the other thing
``0024`` warned against by name ("Inventing an ``industry_source`` vocabulary
here would be settling that question by writing a column"). The vocabulary is
two values, it is closed, and it is in a ``CHECK`` — the same treatment ``0023``
gave ``smartmatch_domain.consent``'s states and ``0024`` gave the two
taxonomies. ``inferred`` and ``human`` are not a naming of *which* classifier or
*which* screen; they are the only distinction §19's review step turns on, and a
column that could also hold ``"csv-import-v3"`` would be a provenance log
wearing an enum's name.

Why the vocabulary is transcribed rather than imported
--------------------------------------------------------
``smartmatch_domain.cba_classification.CLASSIFICATION_SOURCES`` is the single
copy that application code reads. The two literals below are a second copy, for
``0023``'s and ``0024``'s stated reason: a ``CHECK`` cannot import Python, and "a
migration describes the database as of the moment it ran, and an import would
let a later edit to the domain silently change what this historical revision
meant." The divergence that risks is caught behaviourally, not by discipline —
``tests/integration/test_cba_import_classification.py`` parametrizes over
``CLASSIFICATION_SOURCES`` *from the domain module* and requires every released
source to be storable, so a third source added in Python without a migration
fails there rather than in a Connector's screen.

Three states, enumerated rather than composed
-----------------------------------------------
Each axis's constraint is written as three explicit arms rather than as four
independent couplings, because the couplings are what invite three-valued logic
to decide the outcome. ``(source = 'human') = (actor IS NOT NULL)`` evaluates to
``NULL`` when ``source`` is ``NULL``, a ``CHECK`` treats ``NULL`` as satisfied,
and the constraint then silently admits an unclassified row carrying an actor.
``0024`` had to explain the same trap about its ``IS NULL`` arm, and ``0021``
and ``0023`` before it. Enumerating the arms means every column's value is
stated in every state, and no reading depends on what ``NULL = NULL`` does.

The three arms are the three things that can be true of one axis:

``unclassified``
    No code, no source, no actor, no timestamp. ``0024``'s "NULL is a real state
    and not a placeholder": §19 imports a contact first and classifies it after.

``inferred``
    A code, a timestamp, and **no actor** — enforced, not merely defaulted. This
    is the arm that carries the card's non-negotiable into the database: an
    inferred classification is a *proposal awaiting review*, and attaching a
    person to it would record a human judgment that never happened. Nobody can
    write a row asserting that a Connector approved what a classifier proposed,
    because the constraint refuses it.

``human``
    A code and a timestamp, and the actor is permitted. Permitted rather than
    required, and only because of the backfill below. Every write on every path
    this repository ships supplies one; that is asserted behaviourally in
    ``tests/integration/test_cba_import_classification.py`` rather than by a
    ``NOT NULL`` this backfill could not satisfy.

Note what the second and third arms together establish: an actor may appear
**only** beside ``human``. The actor column is not "who touched this row"; it is
"whose judgment this is", and a classifier has none.

The backfill, and why a legacy actor is NULL rather than invented
-------------------------------------------------------------------
``speaker_profile`` may already hold rows. Every one of them was written by
``services/api/smartmatch_api/routers/cba_contacts.py`` — §13's create, edit, and
correction routes are its only writers, and all three require an authenticated
Speaker Connector. So a pre-existing row with a code was set by a person, and
``human`` is the true statement about it; leaving it ``NULL`` would say "not yet
classified" about a row that is, and would silently make every existing contact
match-ineligible under the gate this revision's application layer adds.

``classified_at`` is backfilled from ``updated_at``, which is the closest true
statement available: the row was last touched then, and the classification
cannot be newer than that. Stamping it with ``now()`` instead would claim every
legacy contact was classified on the day this revision deployed.

``classified_by_user_id`` is backfilled to ``NULL``, and that is the honest
answer rather than a gap. A person set the value; **which** person was not
recorded, because the column did not exist when they did it. Writing any
particular account id there would fabricate an audit record, which is
categorically worse than admitting the record was not kept — the reasoning
``0012`` used when it refused to invent a ``board_role`` vocabulary rather than
guess one. That is why the ``human`` arm permits a NULL actor: not as a loophole
for future writes, but because this revision must be able to describe rows
written before it.

Expand only
-------------
Six nullable columns, one backfill of columns this revision itself added, two
foreign keys, and two ``CHECK`` constraints. Nothing is dropped, renamed, or
rewritten. Safe under a rolling deploy per v1.1 §4.2: the old release does not
know the columns exist and writes ``speaker_profile`` rows leaving them NULL.
The old release *can* still set a code through §13's routes, and such a row
would land outside all three arms — so the constraints are added in the same
transaction as the backfill and the deploy order is the ordinary one (migrate,
then release); a write racing the migration fails loudly on the constraint
rather than storing an unattributed code. Per ADR-0009 this runs in its own
transaction (``transaction_per_migration=True`` in ``db/migrations/env.py``).

Open questions this revision deliberately does not answer
-----------------------------------------------------------
* **OQ-CBA-039 — a live classification model.** The classifier behind the
  ``inferred`` source is a deterministic fixture that resolves company and title
  text against the two released taxonomies and proposes nothing it cannot
  resolve. Which model would replace it, on whose credentials, under whose
  terms, and whether a named person's employer and job title may be sent to a
  third party at all is unanswered — the same question ``topic_semantics``
  records as OQ-CBA-026 about §9's comparison, asked again about §19's
  classification. ``build_contact_classifier`` refuses a live adapter under
  every edition until it is answered. No column here depends on the answer:
  a model-produced proposal is still ``inferred``, and still awaits review.
* **OQ-CBA-045 — whether an inferred proposal expires.** A contact imported and
  never reviewed sits in the ``inferred`` arm indefinitely, permanently
  match-ineligible and permanently invisible unless somebody opens the roster.
  Whether that should age into a work queue, a reminder, or nothing at all is a
  product decision nobody has made, and a ``review_due_at`` column added here
  would be this revision making it.
* **OQ-CBA-010 — where a quarantined classification lives.** ``0024`` handed
  this question to ``CBA-IMPORT-CLASSIFY``, which is this card. It is answered
  by *not* adding a column: an unresolvable company or title produces **no
  proposal**, so the axis stays in the ``unclassified`` arm with the raw text
  still sitting in ``speaker_profile.company`` or ``.title`` where a reviewer
  reads it. There is nowhere for a quarantined value to go because nothing is
  stored that a reviewer could not already see. Whether the import path should
  additionally raise a ``review_item`` per unclassifiable contact — rather than
  relying on the roster showing an empty classification — is the part that
  remains open, and it is a review-surface question rather than a schema one.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0028_classification_provenance"
down_revision = "0027_match_weight_setting"
branch_labels = None
depends_on = None


#: Transcribed from ``smartmatch_domain.cba_classification.CLASSIFICATION_SOURCES``,
#: spelled out here rather than imported for ``0023``'s and ``0024``'s reason —
#: see the module docstring. Bound back to the domain module behaviourally by
#: ``tests/integration/test_cba_import_classification.py``.
_SOURCE_INFERRED = "inferred"
_SOURCE_HUMAN = "human"

#: The two axes ``0024`` gave ``speaker_profile``. Iterated rather than written
#: twice so a constraint tightened on one axis cannot be left slack on the other.
_AXES = ("industry", "role")


def _provenance_condition(axis: str) -> str:
    """The three-arm constraint for one axis, so both read identically.

    ``axis`` is ``"industry"`` or ``"role"``; the code column it guards is
    ``primary_{axis}_code`` in both cases, which is why the two calls differ in
    one word rather than in a hand-written duplicate — ``0025``'s reason for
    factoring ``_blank_free``.
    """
    code = f"primary_{axis}_code"
    source = f"{axis}_classification_source"
    actor = f"{axis}_classified_by_user_id"
    at = f"{axis}_classified_at"
    return (
        # Unclassified: §19 imports first and classifies after, so every column
        # is absent together.
        f"({source} IS NULL AND {code} IS NULL "
        f"AND {at} IS NULL AND {actor} IS NULL)"
        # Inferred: a proposal awaiting review. No actor, enforced — a
        # classifier's proposal must not be recordable as somebody's judgment.
        f" OR ({source} = '{_SOURCE_INFERRED}' AND {code} IS NOT NULL "
        f"AND {at} IS NOT NULL AND {actor} IS NULL)"
        # Human: a person's judgment. The actor is permitted and, on every path
        # this repository ships, supplied; it is not NOT NULL only because rows
        # written before this revision have no actor to name.
        f" OR ({source} = '{_SOURCE_HUMAN}' AND {code} IS NOT NULL "
        f"AND {at} IS NOT NULL)"
    )


def upgrade() -> None:
    """Add the six provenance columns, backfill legacy rows, then constrain."""
    for axis in _AXES:
        # Nullable, all three: the unclassified arm is a real state, and a
        # server default would put every existing row into a state nobody chose.
        op.add_column(
            "speaker_profile",
            sa.Column(f"{axis}_classification_source", sa.Text, nullable=True),
        )
        op.add_column(
            "speaker_profile",
            sa.Column(
                f"{axis}_classified_by_user_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
        )
        op.add_column(
            "speaker_profile",
            sa.Column(f"{axis}_classified_at", sa.DateTime(timezone=True), nullable=True),
        )

    # Backfill before constraining, not after: a pre-existing classified row
    # fails every arm until it names a source, so the constraints below could
    # not be added to a populated table in the other order. See the module
    # docstring on why the actor stays NULL rather than being invented.
    for axis in _AXES:
        op.execute(
            f"""
            UPDATE speaker_profile
               SET {axis}_classification_source = '{_SOURCE_HUMAN}',
                   {axis}_classified_at = updated_at
             WHERE primary_{axis}_code IS NOT NULL
            """
        )

    for axis in _AXES:
        # Composite and tenant-scoped, as every other actor reference in this
        # schema is: an account in one tenant must not be recordable as the
        # reviewer of a classification in another. RESTRICT, for
        # `match_weight_setting.updated_by_user_id`'s stated reason — deleting
        # an account must not silently erase the authorship of a judgment it
        # made. MATCH SIMPLE (the default) is what makes the nullable arm work:
        # a NULL actor satisfies the key without needing a row to point at.
        op.create_foreign_key(
            f"fk_speaker_profile_{axis}_classified_by",
            "speaker_profile",
            "user_account",
            ["tenant_id", f"{axis}_classified_by_user_id"],
            ["tenant_id", "id"],
            ondelete="RESTRICT",
        )
        op.create_check_constraint(
            f"ck_speaker_profile_{axis}_provenance",
            "speaker_profile",
            _provenance_condition(axis),
        )


def downgrade() -> None:
    """Drop the constraints, the keys, then the six columns.

    A development tool, not a production rollback path (v1.1 §4.2). Rolling this
    back discards every record of who reviewed a classification and whether one
    was reviewed at all — the surviving codes then read as equally trustworthy,
    which is precisely the ambiguity this revision exists to remove. Constraints
    before columns, ``0025``'s ordering argument: dropping a column first takes
    its constraint with it and leaves a name a later revision could not reuse
    without noticing why.
    """
    for axis in _AXES:
        op.drop_constraint(
            f"ck_speaker_profile_{axis}_provenance", "speaker_profile", type_="check"
        )
        op.drop_constraint(
            f"fk_speaker_profile_{axis}_classified_by", "speaker_profile", type_="foreignkey"
        )
        op.drop_column("speaker_profile", f"{axis}_classified_at")
        op.drop_column("speaker_profile", f"{axis}_classified_by_user_id")
        op.drop_column("speaker_profile", f"{axis}_classification_source")
