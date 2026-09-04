"""Turns a coordinator's review-accept into ``pipeline_record`` rows — Card 5.

This is the application-service module Decision 1 in
`docs/plans/2026-09-03-pipeline-synthetic-caller-plan.md` §2 names: the caller
`python/smartmatch_persistence/smartmatch_persistence/pipeline.py::PipelineRepository`
has had none of since it was written. Cards 1-4 built the pieces —
``record_matched``'s provenance column and CHECK (Card 1), the deterministic
synthetic derivers (Card 2), the Choice A identity writer (Card 3), and the
minimal attendance writer (Card 4, not called from here — see below); this
module is where they assemble into the one thing a coordinator's accept
actually invokes. Card 6 wires it into
``services/api/smartmatch_api/routers/review.py::decide_review_item``, after
``ReviewRepository.decide`` has returned ``transitioned=True`` and before the
router's own ``session.commit()``. This module opens no route, adds no
authorizer, and changes no role set — it is called, not exposed.

## What this module is authorized to do, quoted verbatim

`docs/decisions/synthetic-pilot-development-authorization-2026-09-03.md`
§4 "Pipeline production caller (item 6)", in full:

    **Authorized:** Wire **synthetic** import and review-decision paths to
    call `PipelineRepository` for stakeholder demo, subject to:

    1. G1 registry approval (D1 sign-off) before `matched_at` semantics
       represent real matching.
    2. Professional identity: import creates or links `user_account` per
       professional (Choice A).
    3. `attendance_record` write path: minimal synthetic writer for
       Attended-stage CHECK constraints in demo seed flow.

    Production live-data callers remain blocked until G2 closes.

Item 1 is why this module never claims a real match: G1 has not closed, so
nothing here may let ``matched_at`` mean "the matching engine placed this
professional against this opportunity". Item 2 is honoured by calling
``ProfessionalIdentityRepository.ensure_account`` / ``.link_to_unit`` at
accept, per Decision 2 in the plan (identity is created at review-accept, not
import — a deliberate reading of "import creates or links", not an
oversight; see ``smartmatch_persistence.professionals``'s own module
docstring for the full argument). Item 3's attendance writer is deliberately
**not** called from this module: the plan's Decision 6 provisions only the
Matched stage from a review-accept — ``AttendanceRepository`` exists for the
demo seed flow (Card 7), a separate caller with a separate authorization
clause, and wiring it in here would be this module reaching for authority
item 3 grants to a different caller.

## ``matched_at`` is a coordinator's acceptance, never a computed fit

Every ``pipeline_record`` this module opens carries ``matched_at =
accepted_at`` — the moment `routers/review.py::decide_review_item` recorded
the coordinator's decision, passed straight through. It is **not** the
output of a matching computation: no matching engine runs in this codebase
today (G1 open, per item 1 above), and this module could not call one if it
wanted to — nothing here imports, depends on, or references
``pilot/match-engine-m2-m7`` (PR #12), and no function or class in this file
is named as if it were a matcher. A ``pipeline_record`` row asserts "a match
occurred" the instant it exists (``matched_at`` is ``NOT NULL``); what this
module writes into that row is the true, complete story of how that
assertion came to be true here — a coordinator, in the pilot appliance,
accepted an in-list opportunity row, and every professional already linked
to that opportunity's unit was opened a journey as a consequence. That is a
real event. It is just not a fitness judgement, and this module never
pretends otherwise.

## The provenance is stored, not merely logged

Every row this module writes carries ``matched_provenance =
"synthetic / coordinator-accepted"``
(``smartmatch_domain.synthetic_pilot.SYNTHETIC_MATCH_PROVENANCE``) **in the
``pipeline_record`` table itself**, not only on a log line. A log
rotates away; ``ck_pipeline_record_matched_provenance`` (migration ``0016``)
does not, and the column is ``NOT NULL`` with no server default, so
``PipelineRepository.record_matched`` refuses to write a row that omits it.
That is what makes the claim "this row came from a coordinator's synthetic
accept, not the matching engine" auditable a year from now — D5's retention
window — by reading the stored column, rather than resting on operational
log retention, which this program does not control and cannot promise for a
year. The structured ``logger.info`` line this module also emits (see
:func:`provision_on_accept`) exists because a log line is useful for
day-to-day operations, exactly as Decision 4 in the plan says — but it is a
convenience, not the record.

## This module cannot write a fabricated score, structurally

``PipelineRepository.record_matched``'s full signature, after Card 1, has no
score, confidence, or rank parameter — ``tenant_id``, ``owning_unit_id``,
``subject_id``, ``opportunity_event_id``, ``matched_at``, and
``matched_provenance``, and nothing else. This module introduces none
either: it computes no figure describing how well a professional and an
opportunity fit, stores no such figure anywhere, and passes nothing of the
kind to any repository. It is not merely that this module happens not to
compute a score today — it has no parameter, local variable, or return
field through which one could flow even if a future edit wanted to smuggle
one in, because the one repository call capable of writing a
``pipeline_record`` row does not accept one. `tests/integration/test_pipeline_provisioning.py`
proves this with an AST check over this module's assignment targets,
parameter names, and function names (not a substring grep over prose — this
docstring is free to explain the refusal in full sentences), and separately
asserts ``record_matched``'s own parameter set has exactly the keys this
module calls it with, so a widened signature elsewhere in the codebase
cannot silently open a door this module never meant to walk through.

## The real matching engine is a different branch; this module must not grow toward it

The real matching engine (G1, plan P5, M1-M10) is landing on
``pilot/match-engine-m2-m7`` (PR #12), an entirely separate branch from this
one. This module does not import from it, depend on it, or reference it,
and it must never be extended to. ``"match-engine"``
(``smartmatch_persistence.pipeline.MATCH_PROVENANCE_MATCH_ENGINE``) is a
reserved provenance value that branch's own writer will use; this module
never passes it to ``record_matched`` and never will — the only provenance
this file's single call site to ``record_matched`` ever supplies is
:data:`~smartmatch_domain.synthetic_pilot.SYNTHETIC_MATCH_PROVENANCE`. No
function, class, or module here is named in a way that suggests a matcher,
and none should be added.

## Every id is a ``uuid5``: re-running this module converges, it does not multiply

``synthetic_professional_subject_id`` and ``synthetic_opportunity_event_id``
(``smartmatch_domain.synthetic_pilot``) are both deterministic hashes over
their inputs, not random ids. The same tenant, unit, and professional name
always derive the same ``subject_id``; the same tenant and review item
always derive the same ``opportunity_event_id``. Combined with
``ensure_account``'s and ``link_to_unit``'s own ``ON CONFLICT DO NOTHING``
writers and ``record_matched``'s own idempotency on
``uq_pipeline_record_subject_opportunity``, calling
:func:`provision_on_accept` twice for the same accepted review item — a
retried request, a replayed import that produced a second review item for
the same person, a re-seeded demo — targets the same rows rather than
creating parallel ones. In practice a literal duplicate call cannot even
reach this module: ``ReviewRepository.decide`` is a conditional
``UPDATE ... WHERE status = 'pending'``, so a second decision on an
already-decided item never gets past the router. The idempotency here is a
second, independent line of defense for the cases that condition does not
cover — a replayed import producing a *new* review item for a person or
opportunity this module has already provisioned once.

## Silent zero is a defect (plan §1.10)

An accepted in-list ``events`` row that finds no professional already
linked to its unit is not an error — the coordinator's decision to accept
the row is still recorded as a :class:`ProvisionOutcome` naming its derived
``opportunity_event_id`` — but it must never look, from the log, like a
successful accept that opened journeys. :func:`provision_on_accept` emits a
``WARNING`` in exactly that case, naming the review item and the unit, so
that "nothing happened" is a visible, searchable fact rather than a silence
indistinguishable from success.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from smartmatch_domain.metrics import OpportunityCategoryShape, shape_opportunity_category
from smartmatch_domain.synthetic_pilot import (
    MAX_SYNTHETIC_JOURNEYS_PER_ACCEPT,
    SYNTHETIC_BOARD_ROLE,
    SYNTHETIC_MATCH_PROVENANCE,
    synthetic_opportunity_event_id,
    synthetic_professional_email,
    synthetic_professional_external_subject,
    synthetic_professional_subject_id,
)
from smartmatch_persistence.pipeline import PipelineRepository
from smartmatch_persistence.professionals import ProfessionalIdentityRepository
from sqlalchemy.orm import Session

__all__ = [
    "EVENTS_DATASET",
    "EVENT_CATEGORY_KEY",
    "PROFESSIONALS_DATASET",
    "PROFESSIONAL_NAME_KEY",
    "ProvisionOutcome",
    "provision_on_accept",
]

logger = logging.getLogger(__name__)

_professionals = ProfessionalIdentityRepository()
_pipeline = PipelineRepository()

#: ``import_batch.dataset`` values this module knows how to provision. Any
#: other value is not an error here — see :func:`provision_on_accept`'s
#: docstring for why.
PROFESSIONALS_DATASET: Final[str] = "professionals"
EVENTS_DATASET: Final[str] = "events"

#: ``review_item.row_data`` keys this module reads. Both are already
#: lower-cased and underscore-joined by the time a row reaches
#: ``review_item`` — ``smartmatch_worker.handlers._normalize_row`` runs every
#: submitted header through ``smartmatch_domain.ingest.normalize_header``
#: before storage, so the ratified contract columns ``"name"`` and
#: ``"Category"`` land here as ``"name"`` and ``"category"`` respectively.
PROFESSIONAL_NAME_KEY: Final[str] = "name"
EVENT_CATEGORY_KEY: Final[str] = "category"


@dataclass(frozen=True, slots=True)
class ProvisionOutcome:
    """What one call to :func:`provision_on_accept` did, and nothing it did not.

    All three fields default to their empty value so a dataset this module
    provisions nothing for — an unrecognised ``dataset``, an out-of-list or
    absent ``events`` category, a nameless ``professionals`` row — can return
    a bare ``ProvisionOutcome()`` rather than a caller having to build one by
    hand at every such branch.
    """

    professional_subject_id: uuid.UUID | None = None
    opportunity_event_id: uuid.UUID | None = None
    journeys_opened: tuple[uuid.UUID, ...] = ()


def provision_on_accept(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    owning_unit_id: uuid.UUID,
    review_item_id: uuid.UUID,
    dataset: str,
    row_data: Mapping[str, Any],
    accepted_at: datetime,
) -> ProvisionOutcome:
    """Provision whatever a coordinator's accept of one review item opens.

    Called once per accepted review item, from inside the router's existing
    transaction — this function never calls ``session.commit()``; the
    caller's transaction boundary is the one that governs. See the module
    docstring for the full authorization and design argument; this
    docstring covers only this function's own contract.

    Behaviour depends on ``dataset``:

    - ``"professionals"``: ensures a synthetic ``user_account`` exists for
      the row's ``name`` and links it to ``owning_unit_id``. Opens no
      journey — a professional alone is not a match, it is one half of one.
    - ``"events"`` whose ``row_data["category"]`` is in-list per
      ``smartmatch_domain.metrics.shape_opportunity_category``: opens one
      ``pipeline_record`` journey for every professional already linked to
      ``owning_unit_id``, capped at
      ``smartmatch_domain.synthetic_pilot.MAX_SYNTHETIC_JOURNEYS_PER_ACCEPT``.
      An ``events`` row whose category is out-of-list or absent provisions
      nothing and is not an error — the ratified rule is that such a row is
      *pending coordinator review*, not invalid, and this function does not
      re-implement or second-guess that rule.
    - Anything else: provisions nothing and logs nothing. An unrecognised
      ``dataset`` is not this function's error to raise — the import
      contract (``smartmatch_worker.handlers._dataset_contract``) already
      refused an unknown dataset before any review item naming it could
      exist.

    **Why ``ConflictingOwningUnitError`` is left to propagate.** It signals
    that a synthetic derivation collided across units in a way that must
    never silently happen — a bug in the derivers, or two different units
    both accepting rows that hashed to the same ``(subject_id,
    opportunity_event_id)`` pair. Catching and swallowing it here would
    record the coordinator's accept as if it succeeded while quietly
    discarding a real data-integrity problem the caller needs to see. Left
    to propagate, it aborts the router's transaction — the decision itself
    rolls back with it, exactly the outcome the plan's Decision 7 states:
    "a failure anywhere rolls the decision back with it".

    Args:
        accepted_at: The moment the coordinator's decision was recorded —
            the router's own ``utc_now()``, passed straight through as
            ``matched_at`` for every journey this call opens. Must be
            timezone-aware.

    Returns:
        A :class:`ProvisionOutcome` describing what this call did. Calling
        this function twice for the same review item — see the module
        docstring's idempotency section — returns an outcome naming the same
        derived ids and the same journeys, not a second set.

    Raises:
        ValueError: ``accepted_at`` is a naive ``datetime``.
        smartmatch_persistence.pipeline.ConflictingOwningUnitError: an
            ``events`` accept would open a journey for a ``(subject_id,
            opportunity_event_id)`` pair that already exists under a
            *different* owning unit. Deliberately left to propagate — see
            above.
    """
    if accepted_at.tzinfo is None:
        raise ValueError("accepted_at must be timezone-aware")

    if dataset == PROFESSIONALS_DATASET:
        return _provision_professional(
            session,
            tenant_id=tenant_id,
            owning_unit_id=owning_unit_id,
            review_item_id=review_item_id,
            row_data=row_data,
        )

    if dataset == EVENTS_DATASET:
        return _provision_event(
            session,
            tenant_id=tenant_id,
            owning_unit_id=owning_unit_id,
            review_item_id=review_item_id,
            row_data=row_data,
            accepted_at=accepted_at,
        )

    return ProvisionOutcome()


def _provision_professional(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    owning_unit_id: uuid.UUID,
    review_item_id: uuid.UUID,
    row_data: Mapping[str, Any],
) -> ProvisionOutcome:
    """Ensure a synthetic identity exists for an accepted ``professionals`` row.

    Opens no journey — see :func:`provision_on_accept`'s docstring.
    """
    name = row_data.get(PROFESSIONAL_NAME_KEY)
    if not isinstance(name, str) or not name.strip():
        logger.warning(
            "accepted professionals review_item %s in unit %s has no usable name "
            "(%r); no synthetic identity can be derived for it",
            review_item_id,
            owning_unit_id,
            name,
        )
        return ProvisionOutcome()

    subject_id = synthetic_professional_subject_id(
        tenant_id=tenant_id, unit_id=owning_unit_id, name=name
    )
    _professionals.ensure_account(
        session,
        tenant_id=tenant_id,
        subject_id=subject_id,
        external_subject=synthetic_professional_external_subject(subject_id),
        email=synthetic_professional_email(subject_id),
    )
    _professionals.link_to_unit(
        session,
        tenant_id=tenant_id,
        professional_id=subject_id,
        unit_id=owning_unit_id,
        board_role=SYNTHETIC_BOARD_ROLE,
    )
    return ProvisionOutcome(professional_subject_id=subject_id)


def _provision_event(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    owning_unit_id: uuid.UUID,
    review_item_id: uuid.UUID,
    row_data: Mapping[str, Any],
    accepted_at: datetime,
) -> ProvisionOutcome:
    """Open journeys for an accepted, in-list ``events`` row.

    See :func:`provision_on_accept`'s docstring for the out-of-list/absent
    and empty-unit behaviour.
    """
    category = row_data.get(EVENT_CATEGORY_KEY)
    if not isinstance(category, str):
        category = None

    if shape_opportunity_category(category) is not OpportunityCategoryShape.IN_LIST:
        return ProvisionOutcome()

    opportunity_event_id = synthetic_opportunity_event_id(
        tenant_id=tenant_id, review_item_id=review_item_id
    )

    subject_ids = _professionals.professional_ids_for_unit(
        session,
        tenant_id=tenant_id,
        unit_id=owning_unit_id,
        limit=MAX_SYNTHETIC_JOURNEYS_PER_ACCEPT,
    )

    if not subject_ids:
        # Plan §1.10 — silent zero is a defect. The coordinator's accept is
        # still real and still recorded (opportunity_event_id below); what
        # must not happen is a zero-journey outcome passing unremarked.
        logger.warning(
            "accepted in-list events review_item %s in unit %s opened NO pipeline "
            "journeys: no professionals are linked to this unit yet. Accept the "
            "professionals rows for this unit first.",
            review_item_id,
            owning_unit_id,
        )
        return ProvisionOutcome(opportunity_event_id=opportunity_event_id)

    journeys: list[uuid.UUID] = []
    for subject_id in subject_ids:
        record = _pipeline.record_matched(
            session,
            tenant_id=tenant_id,
            owning_unit_id=owning_unit_id,
            subject_id=subject_id,
            opportunity_event_id=opportunity_event_id,
            matched_at=accepted_at,
            matched_provenance=SYNTHETIC_MATCH_PROVENANCE,
        )
        journeys.append(record.id)

    logger.info(
        "opened %d synthetic pipeline journey(s) for review_item %s in unit %s; provenance=%s",
        len(journeys),
        review_item_id,
        owning_unit_id,
        SYNTHETIC_MATCH_PROVENANCE,
    )

    return ProvisionOutcome(
        opportunity_event_id=opportunity_event_id, journeys_opened=tuple(journeys)
    )
