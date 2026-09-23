"""Speaker accounts: the portal invitation, the profile's bound login, and lifted suppressions.

B26 (``docs/plans/2026-09-22-b26-self-service-availability-plan.md`` §4.2,
track plan ``docs/plans/b26-tracks/T6b-1-plan.md`` §2).

``speaker_portal_invitation``
    One row per invitation a Speaker Connector sends. It stores the SHA-256 of
    the activation token (``token_hash``), never the token: the token is an
    HMAC of the invitation id under a server secret and is rendered only by
    the worker at send time. ``issued_at`` has **no default** (R6): every
    timestamp comes from the one ``now`` a request reads, so a writer that
    forgets it fails on NOT NULL instead of quietly using the database clock.
    At most one live invitation per profile (``uq_speaker_portal_invitation_live``).

``speaker_profile.account_user_id`` / ``account_bound_at``
    The login a Speaker activated. One profile per login
    (``uq_speaker_profile_account``); both columns are set together or not at
    all.

``suppression_record.lifted_at`` / ``lifted_by_user_id``
    Schema only. No code in this revision sets them, so every send-eligibility
    read is unchanged; T6b-3 owns the readers. The source vocabulary gains
    ``speaker_portal``. Added for T6b-3: ``ck_suppression_record_lift_source``
    makes "bounce, complaint and coordinator suppressions are never lifted"
    structural.

``contact_channel_speaker_choice`` (added for T6b-3, its plan §4.2)
    An append-only log of a Speaker's opt-in / opt-out on one channel, ordered
    by ``sequence``. ``decided_at`` has no default (R6). No T6b-1 code writes
    it; the trigger refuses every UPDATE, the ``0023`` pattern.

``cba_invitation.response_channel`` (ruling C2 = b, from T6b-2)
    Admits ``speaker_portal``: an answer a signed-in Speaker gave from the
    portal. Like ``connector_recorded`` it requires an actor; ``speaker_link``
    still has none. No T6b-1 route writes it.

No ``membership.role`` CHECK exists, so the ``speaker`` role needs no DDL.

Expand-only: two CREATE TABLEs, nullable columns, three CHECKs widened and
new CHECKs that every existing row already satisfies (the new columns are
NULL). Safe under a rolling deploy per v1.1 §4.2. Transaction handling belongs to
``env.py`` (ADR-0009).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0039_speaker_portal"
down_revision = "0038_speaker_availability"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True)
_TS = sa.DateTime(timezone=True)

_RESPONSE_CHANNEL_BEFORE = (
    "response_channel IS NULL OR response_channel IN ('speaker_link', 'connector_recorded')"
)
_RESPONSE_CHANNEL_AFTER = (
    "response_channel IS NULL OR response_channel IN "
    "('speaker_link', 'connector_recorded', 'speaker_portal')"
)
_RESPONSE_ACTOR_BEFORE = (
    "(response_channel = 'connector_recorded') = (response_recorded_by_user_id IS NOT NULL)"
)
_RESPONSE_ACTOR_AFTER = (
    "(response_channel IN ('connector_recorded', 'speaker_portal')) = "
    "(response_recorded_by_user_id IS NOT NULL)"
)

_SOURCES_BEFORE = "('unsubscribe_link', 'one_click', 'coordinator', 'bounce', 'complaint')"
_SOURCES_AFTER = (
    "('unsubscribe_link', 'one_click', 'coordinator', 'bounce', 'complaint', 'speaker_portal')"
)


def upgrade() -> None:
    """Create the two tables and widen the three existing ones."""
    op.create_table(
        "speaker_portal_invitation",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("professional_id", _UUID, nullable=False),
        sa.Column("contact_channel_id", _UUID, nullable=False),
        sa.Column("issued_by_user_id", _UUID, nullable=False),
        sa.Column("token_hash", sa.LargeBinary, nullable=False),
        sa.Column("issued_at", _TS, nullable=False),
        sa.Column("expires_at", _TS, nullable=False),
        sa.Column("accepted_at", _TS, nullable=True),
        sa.Column("revoked_at", _TS, nullable=True),
        sa.Column("bound_account_user_id", _UUID, nullable=True),
        sa.Column("binding_mode", sa.Text, nullable=True),
        sa.PrimaryKeyConstraint("id", name="speaker_portal_invitation_pkey"),
        sa.UniqueConstraint("token_hash", name="uq_speaker_portal_invitation_token_hash"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "professional_id"],
            ["speaker_profile.tenant_id", "speaker_profile.professional_id"],
            ondelete="RESTRICT",
            name="fk_speaker_portal_invitation_profile",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "contact_channel_id"],
            ["contact_channel.tenant_id", "contact_channel.id"],
            ondelete="RESTRICT",
            name="fk_speaker_portal_invitation_channel",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "issued_by_user_id"],
            ["user_account.tenant_id", "user_account.id"],
            ondelete="RESTRICT",
            name="fk_speaker_portal_invitation_issued_by",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "bound_account_user_id"],
            ["user_account.tenant_id", "user_account.id"],
            ondelete="RESTRICT",
            name="fk_speaker_portal_invitation_bound_account",
        ),
        sa.CheckConstraint(
            "octet_length(token_hash) = 32", name="ck_speaker_portal_invitation_token_hash"
        ),
        sa.CheckConstraint(
            "expires_at > issued_at AND expires_at <= issued_at + interval '7 days'",
            name="ck_speaker_portal_invitation_window",
        ),
        sa.CheckConstraint(
            "accepted_at IS NULL OR revoked_at IS NULL",
            name="ck_speaker_portal_invitation_one_outcome",
        ),
        sa.CheckConstraint(
            "(accepted_at IS NULL OR accepted_at >= issued_at) "
            "AND (revoked_at IS NULL OR revoked_at >= issued_at)",
            name="ck_speaker_portal_invitation_outcome_after_issue",
        ),
        sa.CheckConstraint(
            "(accepted_at IS NULL) = (bound_account_user_id IS NULL) "
            "AND (accepted_at IS NULL) = (binding_mode IS NULL)",
            name="ck_speaker_portal_invitation_binding",
        ),
        sa.CheckConstraint(
            "binding_mode IS NULL OR binding_mode IN ('new_login', 'existing_login')",
            name="ck_speaker_portal_invitation_binding_mode",
        ),
        sa.CheckConstraint(
            "binding_mode IS DISTINCT FROM 'new_login' OR bound_account_user_id = professional_id",
            name="ck_speaker_portal_invitation_new_login_self",
        ),
    )
    op.create_index(
        "uq_speaker_portal_invitation_live",
        "speaker_portal_invitation",
        ["tenant_id", "professional_id"],
        unique=True,
        postgresql_where=sa.text("accepted_at IS NULL AND revoked_at IS NULL"),
    )

    op.add_column("speaker_profile", sa.Column("account_user_id", _UUID, nullable=True))
    op.add_column("speaker_profile", sa.Column("account_bound_at", _TS, nullable=True))
    op.create_foreign_key(
        "fk_speaker_profile_account",
        "speaker_profile",
        "user_account",
        ["tenant_id", "account_user_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_speaker_profile_account_bound",
        "speaker_profile",
        "(account_user_id IS NULL) = (account_bound_at IS NULL)",
    )
    op.create_index(
        "uq_speaker_profile_account",
        "speaker_profile",
        ["tenant_id", "account_user_id"],
        unique=True,
        postgresql_where=sa.text("account_user_id IS NOT NULL"),
    )

    op.add_column("suppression_record", sa.Column("lifted_at", _TS, nullable=True))
    op.add_column("suppression_record", sa.Column("lifted_by_user_id", _UUID, nullable=True))
    op.create_foreign_key(
        "fk_suppression_record_lifted_by",
        "suppression_record",
        "user_account",
        ["tenant_id", "lifted_by_user_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_suppression_record_lifted",
        "suppression_record",
        "(lifted_at IS NULL) = (lifted_by_user_id IS NULL) "
        "AND (lifted_at IS NULL OR lifted_at >= suppressed_at)",
    )
    op.drop_constraint("ck_suppression_record_source", "suppression_record", type_="check")
    op.create_check_constraint(
        "ck_suppression_record_source", "suppression_record", f"source IN {_SOURCES_AFTER}"
    )
    op.create_check_constraint(
        "ck_suppression_record_lift_source",
        "suppression_record",
        "lifted_at IS NULL OR source IN ('speaker_portal', 'unsubscribe_link', 'one_click')",
    )

    _replace_check("cba_invitation", "ck_cba_invitation_response_channel", _RESPONSE_CHANNEL_AFTER)
    _replace_check("cba_invitation", "ck_cba_invitation_response_actor", _RESPONSE_ACTOR_AFTER)

    _create_speaker_choice()


def _replace_check(table: str, name: str, expression: str) -> None:
    op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, expression)


def _create_speaker_choice() -> None:
    """``contact_channel_speaker_choice``, per the T6b-3 plan §4.2, and its append-only trigger."""
    op.create_table(
        "contact_channel_speaker_choice",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("professional_id", _UUID, nullable=False),
        sa.Column("contact_channel_id", _UUID, nullable=False),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("choice", sa.Text, nullable=False),
        sa.Column("decided_at", _TS, nullable=False),
        sa.Column("actor_user_id", _UUID, nullable=False),
        sa.Column("lifted_source", sa.Text, nullable=True),
        sa.Column("lifted_suppressed_at", _TS, nullable=True),
        sa.PrimaryKeyConstraint("id", name="contact_channel_speaker_choice_pkey"),
        sa.UniqueConstraint(
            "tenant_id",
            "contact_channel_id",
            "sequence",
            name="uq_contact_channel_speaker_choice_sequence",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "contact_channel_id"],
            ["contact_channel.tenant_id", "contact_channel.id"],
            ondelete="RESTRICT",
            name="fk_contact_channel_speaker_choice_channel",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "professional_id"],
            ["speaker_profile.tenant_id", "speaker_profile.professional_id"],
            ondelete="RESTRICT",
            name="fk_contact_channel_speaker_choice_profile",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "actor_user_id"],
            ["user_account.tenant_id", "user_account.id"],
            ondelete="RESTRICT",
            name="fk_contact_channel_speaker_choice_actor",
        ),
        sa.CheckConstraint(
            "choice IN ('opt_in', 'opt_out')", name="ck_contact_channel_speaker_choice_choice"
        ),
        sa.CheckConstraint("sequence >= 1", name="ck_contact_channel_speaker_choice_sequence"),
        sa.CheckConstraint(
            "(lifted_source IS NULL) = (lifted_suppressed_at IS NULL) "
            "AND (choice = 'opt_in' OR lifted_source IS NULL)",
            name="ck_contact_channel_speaker_choice_lift",
        ),
        sa.CheckConstraint(
            "lifted_source IS NULL "
            "OR lifted_source IN ('speaker_portal', 'unsubscribe_link', 'one_click')",
            name="ck_contact_channel_speaker_choice_lift_source",
        ),
    )
    op.execute(
        """
        CREATE FUNCTION contact_channel_speaker_choice_reject_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                'contact_channel_speaker_choice rows are append-only: a changed '
                'choice is a new row with the next sequence, never an UPDATE '
                '(migration 0039)'
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER contact_channel_speaker_choice_is_append_only
        BEFORE UPDATE ON contact_channel_speaker_choice
        FOR EACH ROW EXECUTE FUNCTION contact_channel_speaker_choice_reject_mutation();
        """
    )


def downgrade() -> None:
    """Undo the above, in reverse order — but refuse while Speaker-made data exists (R7).

    An accepted invitation means a ``speaker`` membership and a password were
    set through activation. Neither has a foreign key back to this table, so
    dropping it would orphan them silently. A Speaker's channel choice or a
    portal answer on ``cba_invitation`` cannot exist without one, and would be
    destroyed or made unrepresentable. The guards run before any DDL.
    """
    bind = op.get_bind()
    accepted = bind.execute(
        sa.text("SELECT count(*) FROM speaker_portal_invitation WHERE accepted_at IS NOT NULL")
    ).scalar_one()
    if accepted:
        raise RuntimeError(
            f"cannot downgrade 0039: {accepted} accepted speaker portal invitation(s) exist. "
            "A downgrade would orphan the speaker memberships and passwords set through "
            "activation, which have no foreign key back to this table. Decide what should "
            "happen to those accounts first."
        )
    choices = bind.execute(
        sa.text("SELECT count(*) FROM contact_channel_speaker_choice")
    ).scalar_one()
    portal_answers = bind.execute(
        sa.text("SELECT count(*) FROM cba_invitation WHERE response_channel = 'speaker_portal'")
    ).scalar_one()
    if choices or portal_answers:
        raise RuntimeError(
            f"cannot downgrade 0039: {choices} speaker channel choice(s) and "
            f"{portal_answers} portal-recorded invitation answer(s) exist, and the "
            "earlier schema cannot hold them. Decide what should happen to them first."
        )

    op.execute(
        "DROP TRIGGER IF EXISTS contact_channel_speaker_choice_is_append_only "
        "ON contact_channel_speaker_choice"
    )
    op.execute("DROP FUNCTION IF EXISTS contact_channel_speaker_choice_reject_mutation()")
    op.drop_table("contact_channel_speaker_choice")

    _replace_check("cba_invitation", "ck_cba_invitation_response_actor", _RESPONSE_ACTOR_BEFORE)
    _replace_check("cba_invitation", "ck_cba_invitation_response_channel", _RESPONSE_CHANNEL_BEFORE)

    op.drop_constraint("ck_suppression_record_lift_source", "suppression_record", type_="check")

    op.drop_constraint("ck_suppression_record_lifted", "suppression_record", type_="check")
    op.drop_constraint("fk_suppression_record_lifted_by", "suppression_record", type_="foreignkey")
    op.drop_column("suppression_record", "lifted_by_user_id")
    op.drop_column("suppression_record", "lifted_at")
    # Fails loudly if a `speaker_portal` row exists; this revision's code writes none.
    op.drop_constraint("ck_suppression_record_source", "suppression_record", type_="check")
    op.create_check_constraint(
        "ck_suppression_record_source", "suppression_record", f"source IN {_SOURCES_BEFORE}"
    )

    op.drop_index("uq_speaker_profile_account", table_name="speaker_profile")
    op.drop_constraint("ck_speaker_profile_account_bound", "speaker_profile", type_="check")
    op.drop_constraint("fk_speaker_profile_account", "speaker_profile", type_="foreignkey")
    op.drop_column("speaker_profile", "account_bound_at")
    op.drop_column("speaker_profile", "account_user_id")

    op.drop_index("uq_speaker_portal_invitation_live", table_name="speaker_portal_invitation")
    op.drop_table("speaker_portal_invitation")
