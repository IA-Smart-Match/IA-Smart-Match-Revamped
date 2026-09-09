"""Synthetic professional identity writers — Choice A from the synthetic pilot authorization.

`docs/decisions/synthetic-pilot-development-authorization-2026-09-03.md`
§4 item 6.2 requires "Professional identity: import creates or links
``user_account`` per professional (Choice A)". This module is that writer:
every synthetic professional gets a real ``user_account`` row, so that
``pipeline_record.subject_id``'s foreign key to
``(user_account.tenant_id, user_account.id)`` — ``ON DELETE RESTRICT`` —
has something real to point at, and no orphan ``subject_id`` can ever
exist. The accounts this module creates are synthetic: they carry
``.invalid`` emails (RFC 2606), are never issued a credential, are never
registered with a token verifier, and are not sign-in identities — nothing
here authenticates as one.

## Decision 2 — created at review-accept, not at import (deliberate, not an oversight)

`docs/plans/2026-09-03-pipeline-synthetic-caller-plan.md` §2 Decision 2
records this in one paragraph, restated here because it governs when this
module's methods may be called: Architecture v1.1 §1.5 — restated in
``smartmatch_persistence.review``'s own module docstring — is that "a
validated import produces review items, not verified records". Creating a
``user_account`` for every quarantined row the moment it is imported would
manufacture a real account for rows a coordinator subsequently rejects,
which is precisely the defect the review quarantine exists to prevent. The
invariant that actually matters — "no orphan ``subject_id`` exists" — is
preserved exactly by creating the account at **review-accept** instead,
because the ``pipeline_record`` naming that subject is written in the same
transaction, at the same moment, and the foreign key above makes any other
ordering unstorable regardless. Accept is the terminal step of the same
import-then-review path §4 authorizes; this is a ruled-on choice, not a
shortcut, and no caller should "fix" it back to import-time creation.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from smartmatch_persistence import schema

__all__ = ["ProfessionalIdentityRepository"]


class ProfessionalIdentityRepository:
    """Writes ``user_account`` and ``professional_unit_relationship`` rows — Choice A's writer.

    Takes a session per call, like every other repository in this package
    (``jobs.py``, ``review.py``, ``redrive.py``, ``pipeline.py``):
    transaction boundaries belong to the caller, and no method here commits.
    """

    def ensure_account(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        subject_id: uuid.UUID,
        external_subject: str,
        email: str,
    ) -> bool:
        """Create ``user_account`` for ``subject_id`` if it does not already exist.

        ``ON CONFLICT`` targets ``user_account_pkey`` — the row's own id —
        and deliberately not ``uq_user_account_external_subject``. This
        choice is safe in exactly one direction, and this docstring states
        both, having previously stated only the safe one.

        **Safe direction: a colliding ``external_subject`` under a
        *different* ``subject_id``.** Because every legitimate caller derives
        ``external_subject`` *from* ``subject_id``
        (``smartmatch_domain.synthetic_pilot.synthetic_professional_external_subject``),
        two different subjects can only collide on ``external_subject`` if a
        caller passed one that is not so derived. That case is **not**
        absorbed by this method's ``ON CONFLICT`` — the pkey conflict target
        does not cover ``external_subject`` at all — so
        ``uq_user_account_external_subject`` still fires and raises
        ``IntegrityError``. Correct: two different subjects claiming the same
        external identity is a real conflict, not one this method should
        swallow.

        **Unsafe direction: the same ``subject_id`` called again with a
        *different* ``external_subject``.** This hits the ``user_account_pkey``
        conflict *first* — the row already exists — so the insert is a no-op,
        this method returns ``False``, and the row keeps whichever
        ``external_subject`` its first-ever insert wrote. No exception is
        raised and no signal distinguishes this from an identical repeat
        call; the caller's *new* ``external_subject`` is silently discarded.
        This mirrors ``PipelineRepository.record_matched``'s own documented
        "first call wins, not overwritten" treatment of
        ``matched_provenance`` under idempotency, and is intentional for the
        same reason: an ``ON CONFLICT DO NOTHING`` writer never overwrites,
        by construction. It is *not* safe to rely on unless every caller
        keeps the derivation discipline above — a caller that ever computes
        ``external_subject`` some other way, or recomputes it after a
        derivation rule changes, gets this silent divergence instead of an
        error. See
        ``tests/integration/test_professional_identity_writers.py::test_ensure_account_keeps_first_external_subject_on_repeat``
        for this behaviour proven against a live database.

        Writes only ``id``, ``tenant_id``, ``external_subject``, and
        ``email``. ``suspended``, ``created_at``, and ``version`` all carry
        server defaults and are deliberately left unset here, the same
        discipline ``PipelineRepository.record_matched`` applies to
        ``pipeline_record``'s own server-defaulted columns.

        Returns:
            ``True`` if *this call's own insert* created the row, ``False``
            if the row already existed. Never inferred from a re-read — the
            same discipline ``PipelineStageOutcome.transitioned`` documents
            itself with.
        """
        row = session.execute(
            postgresql.insert(schema.user_account)
            .values(
                id=subject_id,
                tenant_id=tenant_id,
                external_subject=external_subject,
                email=email,
            )
            .on_conflict_do_nothing(constraint="user_account_pkey")
            .returning(schema.user_account.c.id)
        ).one_or_none()
        return row is not None

    def link_to_unit(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        professional_id: uuid.UUID,
        unit_id: uuid.UUID,
        board_role: str,
    ) -> bool:
        """Link ``professional_id`` to ``unit_id`` in ``professional_unit_relationship``, once.

        ``ON CONFLICT`` targets ``professional_unit_relationship_pkey`` —
        the composite ``(tenant_id, professional_id, unit_id)`` natural key
        — so a repeated call for the same professional and unit is a no-op,
        not a ``UniqueViolation``.

        Writes only ``tenant_id``, ``professional_id``, ``unit_id``, and
        ``board_role``. ``created_at`` and ``updated_at`` both carry server
        defaults and are left unset. No ``effective_from`` / ``effective_to``
        notion is added or implied anywhere in this method — P9 Gate A §2
        holds ``board_role`` to current-state only for the pilot, and this
        method's signature has no argument that could express dating.

        Returns:
            ``True`` if *this call's own insert* created the row, ``False``
            if the row already existed.
        """
        row = session.execute(
            postgresql.insert(schema.professional_unit_relationship)
            .values(
                tenant_id=tenant_id,
                professional_id=professional_id,
                unit_id=unit_id,
                board_role=board_role,
            )
            .on_conflict_do_nothing(constraint="professional_unit_relationship_pkey")
            .returning(schema.professional_unit_relationship.c.board_role)
        ).one_or_none()
        return row is not None

    def professional_ids_for_unit(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        limit: int,
    ) -> tuple[uuid.UUID, ...]:
        """Return the professionals linked to ``unit_id`` in this tenant, ascending by id.

        Used by an events-row accept (Decision 6 in the plan) to find which
        professionals already linked to the accepting unit should each get
        a journey opened. Scoped by ``tenant_id`` *and* ``unit_id`` together
        — a unit id from a foreign tenant returns nothing, the same
        composite-scoping discipline every lookup in this codebase applies
        (``ADR-0004``).

        Args:
            limit: The maximum number of ids to return. Must be at least 1
                — the caller in this plan passes
                ``smartmatch_domain.synthetic_pilot.MAX_SYNTHETIC_JOURNEYS_PER_ACCEPT``,
                and a limit of zero or fewer would silently return nothing
                for every unit, which is not a cap this method exists to
                express.

        Raises:
            ValueError: ``limit`` is less than 1.
        """
        if limit < 1:
            raise ValueError("limit must be at least 1")

        rows = session.execute(
            sa.select(schema.professional_unit_relationship.c.professional_id)
            .where(
                schema.professional_unit_relationship.c.tenant_id == tenant_id,
                schema.professional_unit_relationship.c.unit_id == unit_id,
            )
            .order_by(schema.professional_unit_relationship.c.professional_id)
            .limit(limit)
        ).all()
        return tuple(row.professional_id for row in rows)
