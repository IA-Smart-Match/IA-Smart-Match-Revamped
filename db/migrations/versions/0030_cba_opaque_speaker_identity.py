"""Stop deriving a speaker contact's identity from their name; re-key the ones that were.

Revision ID: 0030_cba_opaque_speaker_identity
Revises: 0029_cba_speaker_invitation

**OQ-CBA-017, decided 2026-09-05 by Danny Tran (program owner of record):
identity becomes opaque.** ``speaker_profile`` stops keying a §13 contact by
``uuid5(SPEAKER_CONTACT_NAMESPACE, "tenant:unit:folded_name")``. The id becomes
an opaque generated value and ``full_name`` becomes an ordinary column — a label
a Connector may correct, and nothing more.

The defect this closes is live, not theoretical
-------------------------------------------------
Under the derived scheme an **edit** that changes a name does not move the key —
``smartmatch_persistence.cba_contacts.update`` said so in as many words, and
``0025``'s docstring recorded it as a caveat. Follow the caveat one step
further and it stops being a caveat:

1. A Connector types ``"Dana Ryes"``. The row is keyed
   ``uuid5(ns, "…:dana ryes")``.
2. They notice the typo and edit the name to ``"Dana Reyes"``. The label moves;
   the key does not.
3. Later — a different Connector, a re-typed roster, the same person a month on
   — somebody creates ``"Dana Reyes"``. That derives ``uuid5(ns, "…:dana
   reyes")``, which is a *different* id, so the create succeeds.

One person, two ``speaker_profile`` rows, two ``user_account`` rows, two places
a classification can be corrected and disagree, and nothing anywhere reports it.
That is silent data corruption on the ordinary path — fixing a typo — and it is
why this migration happens now, while the data is still synthetic and the
re-key is cheap, rather than after a pilot cohort is loaded.

An opaque id has no such fork. A name is a column; correcting it is an
``UPDATE``; the identity never moves because it was never a function of anything
that can change.

What the re-key touches, and why the survey had to be exhaustive
-----------------------------------------------------------------
The derived id is not only ``speaker_profile.professional_id``. ``0024`` gave
that column the schema's one real professional foreign key — composite
``(tenant_id, professional_id) -> user_account(tenant_id, id)``,
``ON DELETE RESTRICT`` — so the derived uuid5 **is** the ``user_account.id`` of
the contact's account. Re-keying the profile therefore means re-keying the
account, and re-keying the account means finding everything that points at it.

:data:`_ACCOUNT_ID_REFERENCES` is that survey, written out rather than
discovered at runtime. It carries every column with a foreign key to
``user_account(tenant_id, id)`` — twenty-three of them — plus five columns that
hold an account id and carry **no** foreign key, which are exactly the ones
``RESTRICT`` would *not* have caught:

* ``professional_unit_relationship.professional_id`` — ``0012`` states outright
  that it carries no foreign key.
* ``contact_channel.professional_id`` — the same refusal, restated by ``0021``.
* ``cba_invitation.professional_id`` — ``0029`` refuses the reference
  deliberately, because ``not_on_roster`` is a storable outcome.
* ``job.actor_id`` and ``point_ledger_entry.actor_id`` — nullable, unconstrained
  by design.

Most of those twenty-eight can never hold a contact's id: a §13 roster contact
is not a principal, has no credential, no membership and no grant, and never
acts on anything. Those columns are in the list anyway. "Cannot happen" is a
claim about code that is free to change, and an ``UPDATE`` that matches nothing
costs one statement; a re-key that skipped a column and was *wrong* would leave
a dangling id in a column with no foreign key to complain about it.

Which accounts are re-keyed
------------------------------
Exactly those whose ``external_subject`` begins ``contact-professional:``. That
prefix is written by one function —
``smartmatch_domain.cba_contacts.speaker_contact_external_subject`` — on one
path, the §13 manual create, and it is the set of ids
``speaker_contact_subject_id`` produced. Nothing else in the schema carries it.

**The synthetic pilot's ``uuid5`` scheme is deliberately out of scope.**
``smartmatch_domain.synthetic_pilot.synthetic_professional_subject_id`` derives
``user_account.id`` from ``(tenant, unit, folded name)`` too, under its own
namespace and its own ``synthetic-professional:`` prefix, and the §19 import
path provisions accounts through it. It is left alone for a stated reason
rather than by oversight: the rename fork above needs an **edit** surface to
open, and the synthetic pilot has none — its ids are derived once from an
immutable accepted import row and no path renames them. Its determinism is
also load-bearing in a way §13's never was: replaying an accept must resolve to
the same professional rather than mint a second, and that replay guarantee is
the derivation. Changing it would re-key ``tools/generate_pilot_dataset.py``'s
fixtures and ``services/api/smartmatch_api/pipeline_provisioning.py``, neither
of which this decision names. The residual is recorded honestly as
**OQ-CBA-048**: a contact imported under the synthetic scheme and then renamed
through §13's edit surface can still fork on a re-import, because the *import*
side of its identity is still name-derived.

Insert, repoint, delete — in that order, because RESTRICT is not deferrable
-----------------------------------------------------------------------------
None of the foreign keys involved is ``DEFERRABLE``, so ``SET CONSTRAINTS``
buys nothing and an in-place ``UPDATE user_account SET id = …`` is refused by
the first referrer. The order that works without weakening a constraint is:

1. Materialise the mapping (old id -> a fresh ``gen_random_uuid()``) in a temp
   table that dies with the transaction.
2. **Insert** the replacement ``user_account`` rows. ``external_subject`` and
   ``email`` are re-derived from the *new* id, matching
   ``speaker_contact_external_subject`` and ``speaker_contact_email`` exactly —
   an account whose subject still encoded the old id would be a second copy of
   the identity this migration exists to delete. Every other column is copied,
   ``created_at`` included: the person was added when they were added.
3. **Repoint** all twenty-eight columns.
4. **Delete** the old accounts. ``RESTRICT`` is the check on step 3 here: a
   referrer this migration missed makes step 4 fail loudly rather than leaving
   a dangling id behind.

Referential integrity holds at every step, so nothing is dropped, disabled, or
re-added.

The one piece of DDL, and the constraint that must never join it
------------------------------------------------------------------
``ix_speaker_profile_unit_folded_name`` indexes
``(tenant_id, owning_unit_id, lower(btrim(full_name)))``. It exists because the
create surface now answers a question it never asked before — *does this unit
already hold somebody by this name?* — as a **hint** returned beside a
successful ``201``, replacing the ``409 speaker_contact_name_already_used`` this
decision removes. The hint runs on every create, so it gets an index.

It is **not unique**, and it must never become unique. **OQ-CBA-021.** A unique
index on a unit's folded names is the derived scheme wearing a different hat: it
makes the name identifying again, and it fails *harder* than the ``409`` did,
because a constraint violation cannot name the person it collided with or let
the Connector proceed once they have confirmed these are two different people.
Two professionals in one department genuinely can share a name; the system's job
is to say so, not to refuse. ``0025``'s docstring already declined this
constraint, and the decision that produced this revision declines it again.

One-way, and stated as such
------------------------------
The upgrade cannot be undone by recomputing the old ids, and :func:`downgrade`
does not try. Two reasons, either sufficient. The derived id is a ``uuid5`` over
a *folded name*, so restoring it would collapse two same-named contacts — which
this revision's own create path now permits — onto one primary key, which is
data loss dressed as a rollback. And the name a row carries now may not be the
name its id was derived from; that was the whole defect. So the downgrade
returns the *schema* to ``0029``'s shape by dropping the index, and leaves the
opaque ids where they are. A development tool, not a production rollback path
(v1.1 §4.2).

What is deliberately not here
--------------------------------
* No uniqueness on ``(tenant_id, owning_unit_id, full_name)``, in any form, for
  the reason above. **OQ-CBA-021.**
* No ``CHECK``. There is no expression that can assert "this id is not a hash of
  that name" without an extension and a namespace literal in the database, and a
  constraint that could be satisfied by renaming the person is not a constraint.
  ``tests/integration/test_check_constraints.py`` is therefore unchanged: this
  revision adds and alters none.
* No merge surface, no disambiguator column, no ``duplicate_of`` pointer.
  Recording that two rows are one person is a product decision nobody has taken;
  what ships is a hint that says two rows share a name. **OQ-CBA-049.**
* No history of the re-key. Nothing records what a row's id used to be. That is
  OQ-CBA-008's ruling applied to identity: the previous value is not evidence
  about the current one, and a mapping table retained forever would be a
  standing invitation to resolve an old id — which is precisely the identity
  this revision is deleting.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0030_cba_opaque_speaker_identity"
down_revision = "0029_cba_speaker_invitation"
branch_labels = None
depends_on = None


#: The ``external_subject`` prefix every §13 manually created contact carries,
#: and nothing else does. Written by
#: ``smartmatch_domain.cba_contacts.speaker_contact_external_subject``; spelled
#: as a literal here rather than imported, because a migration must keep
#: describing the database it was written against even after the Python that
#: produced these rows has been edited — which, in this revision's own commit,
#: it has been.
_CONTACT_SUBJECT_PREFIX = "contact-professional:"

#: Every column in the schema that holds a ``user_account.id``, as
#: ``(table, column)``. The survey the module docstring describes.
#:
#: The first block is foreign-keyed to ``user_account(tenant_id, id)``; the
#: second is not, and is therefore the half a missed entry would corrupt
#: silently. Both are re-keyed, including the many that cannot hold a contact's
#: id, for the reason the docstring gives: an ``UPDATE`` matching nothing is
#: cheap, and a wrong assumption about which columns "cannot" hold one is not.
#:
#: Every table listed is ``tenant_id``-scoped, which is what lets the repoint
#: join on ``(tenant_id, old_id)`` rather than on the id alone.
_ACCOUNT_ID_REFERENCES: tuple[tuple[str, str], ...] = (
    # --- foreign-keyed to user_account(tenant_id, id) ---------------------
    ("membership", "user_id"),
    ("resource_grant", "user_id"),
    ("attendance_record", "subject_id"),
    ("reward_item", "budget_owner_id"),
    ("redemption", "subject_id"),
    ("redemption", "approved_by"),
    ("redemption", "closed_by"),
    ("pipeline_record", "subject_id"),
    ("review_item", "decided_by"),
    ("discovery_review_item", "decided_by"),
    ("pilot_credential", "user_id"),
    ("pilot_session", "user_id"),
    ("contact_channel_transition", "actor_user_id"),
    ("outreach_draft", "created_by"),
    ("outreach_draft", "approved_by"),
    ("speaker_profile", "professional_id"),
    ("speaker_profile", "industry_classified_by_user_id"),
    ("speaker_profile", "role_classified_by_user_id"),
    ("event_registration", "subject_id"),
    ("match_weight_setting", "updated_by_user_id"),
    ("match_weight_setting_revision", "changed_by_user_id"),
    ("cba_invitation_batch", "created_by_user_id"),
    ("cba_invitation", "response_recorded_by_user_id"),
    # --- no foreign key, by deliberate decision in an earlier revision ----
    # 0012 records that this one carries none; 0021 restates the refusal for
    # contact_channel; 0029 argues its own at length. RESTRICT cannot help
    # here, which is exactly why they are listed.
    ("professional_unit_relationship", "professional_id"),
    ("contact_channel", "professional_id"),
    ("cba_invitation", "professional_id"),
    ("job", "actor_id"),
    ("point_ledger_entry", "actor_id"),
)

#: The non-unique index the duplicate hint reads. Named here so the create, the
#: drop and the docstring cannot disagree about it.
_FOLDED_NAME_INDEX = "ix_speaker_profile_unit_folded_name"

#: The folding, as SQL. ``lower(btrim(...))`` is the SQL spelling of the
#: ``full_name.strip().casefold()`` the removed derivation used and the duplicate
#: hint still uses, so the index and the query it backs fold identically. Stated
#: once and used by both the index and — through
#: ``smartmatch_persistence.cba_contacts`` — the query, because an index the
#: query cannot use is an index that silently does nothing.
_FOLDED_NAME_EXPRESSION = "lower(btrim(full_name))"


def _rekey_contact_identities() -> None:
    """Give every name-derived §13 contact a fresh opaque id, references included.

    Insert, repoint, delete — the order the module docstring argues, and the only
    one that holds referential integrity throughout without making a constraint
    deferrable or dropping it.

    Does nothing at all on a database with no §13 contacts, which is every fresh
    development database and every test run that has not created one. That is
    stated rather than assumed because it is what makes this revision safe to
    apply to an empty schema.
    """
    bind = op.get_bind()

    # ON COMMIT DROP: `transaction_per_migration=True` (ADR-0009) gives this
    # revision its own transaction, so the mapping cannot outlive the re-key and
    # cannot be left behind by a failure. Nothing persists a record of which
    # opaque id replaced which derived one — see the docstring's last section.
    bind.execute(
        sa.text(
            "CREATE TEMPORARY TABLE _speaker_identity_rekey ON COMMIT DROP AS "
            "SELECT tenant_id, id AS old_id, gen_random_uuid() AS new_id "
            "FROM user_account WHERE external_subject LIKE :prefix || '%'"
        ),
        {"prefix": _CONTACT_SUBJECT_PREFIX},
    )

    # The replacement accounts. `external_subject` and `email` are re-derived
    # from the new id, exactly as speaker_contact_external_subject and
    # speaker_contact_email derive them, so the account states one identity and
    # not two. `suspended`, `created_at` and `version` are carried across
    # unchanged: this is the same person, recorded at the same moment, under a
    # key that no longer says who they are.
    bind.execute(
        sa.text(
            "INSERT INTO user_account "
            "(id, tenant_id, external_subject, email, suspended, created_at, version) "
            "SELECT m.new_id, a.tenant_id, "
            ":prefix || m.new_id::text, "
            "'contact-' || m.new_id::text || '@contact.invalid', "
            "a.suspended, a.created_at, a.version "
            "FROM user_account a "
            "JOIN _speaker_identity_rekey m "
            "ON m.tenant_id = a.tenant_id AND m.old_id = a.id"
        ),
        {"prefix": _CONTACT_SUBJECT_PREFIX},
    )

    # Twenty-eight statements, generated from the surveyed list rather than
    # written out, so a column added to the list cannot be forgotten here and a
    # column removed from it cannot linger. Table and column names come from a
    # module constant and never from data, which is what makes the formatting
    # safe.
    for table, column in _ACCOUNT_ID_REFERENCES:
        bind.execute(
            sa.text(
                f"UPDATE {table} AS t SET {column} = m.new_id "
                "FROM _speaker_identity_rekey m "
                f"WHERE t.tenant_id = m.tenant_id AND t.{column} = m.old_id"
            )
        )

    # RESTRICT does the auditing: if any referrer above was missed, this fails
    # and names the constraint rather than leaving a dangling id behind.
    bind.execute(
        sa.text(
            "DELETE FROM user_account a USING _speaker_identity_rekey m "
            "WHERE a.tenant_id = m.tenant_id AND a.id = m.old_id"
        )
    )


def upgrade() -> None:
    """Re-key the derived identities, then index the name as a label."""
    _rekey_contact_identities()

    # NOT unique, and never to become unique — OQ-CBA-021, argued in the module
    # docstring. It backs the duplicate hint the removed 409 is replaced by:
    # "this unit already has somebody by this name, here they are", answered
    # beside a successful create rather than instead of one.
    op.create_index(
        _FOLDED_NAME_INDEX,
        "speaker_profile",
        ["tenant_id", "owning_unit_id", sa.text(_FOLDED_NAME_EXPRESSION)],
        unique=False,
    )


def downgrade() -> None:
    """Drop the index. The identities stay opaque.

    A development tool, not a production rollback path (v1.1 §4.2). The re-key
    is deliberately **not** reversed: recomputing the derived ids would collapse
    two same-named contacts — which the create path this revision ships now
    permits — onto one primary key, and would in any case derive from whatever
    name a row carries *now* rather than the one its old id was built from. Both
    are data loss, and a rollback that loses data is worse than a schema that
    stayed forward.

    One consequence of leaving the ids alone, stated so it is not discovered:
    a downgrade followed by an upgrade re-keys the already-opaque contacts
    *again*, because :func:`_rekey_contact_identities` selects on the
    ``contact-professional:`` prefix, which the replacement accounts also carry.
    That is churn rather than corruption — every reference moves with the id in
    the same transaction — and Alembic never re-runs a revision in ordinary use.
    """
    op.drop_index(_FOLDED_NAME_INDEX, table_name="speaker_profile")
