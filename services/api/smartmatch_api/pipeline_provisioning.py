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
to that opportunity's unit, up to
:data:`~smartmatch_domain.synthetic_pilot.MAX_SYNTHETIC_JOURNEYS_PER_ACCEPT`,
was opened a journey as a consequence. That is a real event. It is just not
a fitness judgement, and this module never pretends otherwise.

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

**What "converges" means when a unit is over the cap.**
``professional_ids_for_unit`` returns ids ascending by ``professional_id``,
and this module always retains the smallest
:data:`~smartmatch_domain.synthetic_pilot.MAX_SYNTHETIC_JOURNEYS_PER_ACCEPT`
of whatever it reads. So a re-accept of the same ``events`` row against a
unit that is over the cap re-selects that same smallest subset and re-opens
the same journeys — it does **not** reach further into the roster on a
second call, and it never opens a journey for the professionals the first
call already omitted. Convergence here means "the same accept always
targets the same rows", not "an accept eventually covers everyone the unit
has linked" — the cap is a hard ceiling per accept, not a queue that later
calls drain.

## Silent zero — and silent partial fan-out — are both a defect (plan §1.10)

An accepted in-list ``events`` row that finds no professional already
linked to its unit is not an error — the coordinator's decision to accept
the row is still recorded as a :class:`ProvisionOutcome` naming its derived
``opportunity_event_id`` — but it must never look, from the log, like a
successful accept that opened journeys. :func:`provision_on_accept` emits a
``WARNING`` in exactly that case, naming the review item and the unit, so
that "nothing happened" is a visible, searchable fact rather than a silence
indistinguishable from success.

The same defect class applies one step short of zero: a unit with *more*
professionals linked than
:data:`~smartmatch_domain.synthetic_pilot.MAX_SYNTHETIC_JOURNEYS_PER_ACCEPT`
still opens journeys, but not for everyone, and "opened 50 journeys" reads
identically in the log whether that was every linked professional or a
truncated subset unless the truncation itself is said out loud. This module
requests one more row than the cap allows and, only when that extra row
comes back, emits a second ``WARNING`` naming the review item, the unit, and
the cap, before truncating to the cap and opening journeys for the
retained, smallest-``professional_id`` subset. Exactly at the cap — the
common case once a unit's roster stabilizes — nothing was dropped, and no
warning fires; the naive check "did we hit the limit exactly" would produce
a false positive there; over the cap, the warning fires and the log line
naming how many journeys were opened is now provably a *ceiling*, not a
silent full count.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from smartmatch_domain.cba_classification import (
    ContactClassificationProposal,
    ProposedClassification,
)
from smartmatch_domain.cba_contacts import SpeakerContactDraft
from smartmatch_domain.cba_role_categories import (
    ClassifiedRoleCategory,
    resolve_role_category,
)
from smartmatch_domain.metrics import OpportunityCategoryShape, shape_opportunity_category
from smartmatch_domain.naics_sectors import ClassifiedSector, resolve_sector
from smartmatch_domain.synthetic_pilot import (
    MAX_SYNTHETIC_JOURNEYS_PER_ACCEPT,
    SYNTHETIC_BOARD_ROLE,
    SYNTHETIC_MATCH_PROVENANCE,
    synthetic_opportunity_event_id,
    synthetic_professional_email,
    synthetic_professional_external_subject,
    synthetic_professional_subject_id,
)
from smartmatch_persistence.cba_contacts import SpeakerContactRepository
from smartmatch_persistence.pipeline import PipelineRepository
from smartmatch_persistence.professionals import ProfessionalIdentityRepository
from smartmatch_providers.cba_classification import build_contact_classifier
from sqlalchemy.orm import Session

from smartmatch_api.config import get_settings

__all__ = [
    "EVENTS_DATASET",
    "EVENT_CATEGORY_KEY",
    "IMPORT_COLUMN_CLASSIFIER",
    "PROFESSIONALS_DATASET",
    "PROFESSIONAL_NAME_KEY",
    "ProvisionOutcome",
    "provision_on_accept",
]

logger = logging.getLogger(__name__)

_professionals = ProfessionalIdentityRepository()
_pipeline = PipelineRepository()
_contacts = SpeakerContactRepository()

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

#: The remaining ``professionals`` columns a §13 speaker record is built from,
#: mapped to the ``speaker_profile`` field each one lands in. Every one is
#: optional in ``docs/pilot-data/columns.yaml`` — customer §18 opens by saying
#: the data "is scattered across multiple people and systems" with "no single
#: authoritative export", so a record missing any of them is ordinary rather
#: than defective.
#:
#: ``expertise_tags`` maps to ``topic_text`` because the contract ratified that
#: spelling for §18's "Topic/interests/expertise text" on 28 August 2026 and
#: declines to declare the field twice; ``docs/pilot-data/cba-field-mapping.md``
#: is the table this line implements.
#:
#: ``contact_email`` is deliberately absent, and its absence is the point: it is
#: withheld at the import gate (CBA Gate C, OQ-CBA-011) and never reaches
#: ``review_item.row_data``, so there is nothing here to read even if this
#: mapping wanted it. Nothing in this module writes ``contact_channel``, records
#: consent, or makes anybody sendable.
_PROFESSIONAL_PROFILE_KEYS: Final[Mapping[str, str]] = {
    "company": "company",
    "title": "title",
    "expertise_tags": "topic_text",
    "prior_talk": "prior_talk",
    "location_city": "location_city",
    "location_postal_code": "location_postal_code",
}

#: ``row_data`` keys carrying a classification code the coordinator's own export
#: stated, per axis. ``docs/pilot-data/columns.yaml`` declares both and says in
#: as many words that it "does NOT validate them against those taxonomies,
#: resolve a display name to a code, or infer either one from company or title.
#: That is CBA-IMPORT-CLASSIFY's work" — this module is that work.
_PROFESSIONAL_CODE_KEYS: Final[Mapping[str, str]] = {
    "industry": "primary_industry_code",
    "role": "primary_role_code",
}

#: Stamped on a proposal drawn from a code the export stated rather than from
#: the classifier's reading of company and title text. Not stored on
#: ``speaker_profile`` — migration ``0028`` records *whether* a value was
#: inferred and not by which reader — so this exists to keep the two
#: distinguishable in a log, which is why ``ProposedClassification`` carries the
#: field at all.
IMPORT_COLUMN_CLASSIFIER: Final[str] = "import-column"


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
      ``owning_unit_id``, **up to**
      ``smartmatch_domain.synthetic_pilot.MAX_SYNTHETIC_JOURNEYS_PER_ACCEPT``
      — a unit linking more professionals than the cap gets only the cap's
      worth of journeys (the smallest ``professional_id`` values), and a
      second ``WARNING`` names the omission; see the module docstring's
      "Silent zero — and silent partial fan-out" section. An ``events`` row
      whose category is out-of-list or absent provisions nothing and is not
      an error — the ratified rule is that such a row is *pending
      coordinator review*, not invalid, and this function does not
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
        sqlalchemy.exc.IntegrityError: a ``professionals`` accept names an
            ``owning_unit_id`` that does not exist in ``org_unit`` for this
            tenant. ``ProfessionalIdentityRepository.link_to_unit`` issues
            its insert against the composite foreign key
            ``(tenant_id, unit_id) -> (org_unit.tenant_id, org_unit.id)``
            (``schema.py``) with no pre-check of its own, so a bogus unit id
            surfaces as a raw ``IntegrityError`` rather than a catchable
            application error. Not reachable through Card 6's call site —
            the router derives ``owning_unit_id`` from the review item's own
            ``import_batch`` (a row that only exists with a real unit
            behind it) — so this is documented rather than guarded against
            here; rollback is the correct outcome if it were ever reached.
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
            accepted_at=accepted_at,
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
    accepted_at: datetime,
) -> ProvisionOutcome:
    """Provision the identity and the §19 speaker record for an accepted row.

    Two things, in one transaction. The identity — ``user_account`` and the
    unit link — is what this function has always done. The
    ``speaker_profile`` is customer §19's second step: an accepted import row
    becomes a speaker record carrying the classifier's **proposal**, stored as
    ``inferred`` and awaiting the Connector's review.

    **Accepting the row is not reviewing the classification.** The coordinator
    who accepted this review item looked at a spreadsheet row; §19 asks a
    Speaker Connector to review "Industry/Role classifications" as a separate,
    later step, and says why — "Human correction is required because
    classification may involve judgment calls". So nothing written here is
    ``human`` and nothing names an actor, and the contact stays out of matching
    until somebody corrects or confirms it through
    ``POST /v1/units/{unit_id}/speaker-contacts/{professional_id}/classification``.
    Treating the accept as both would be the review bypass the ordering exists
    to prevent.

    Opens no journey — see :func:`provision_on_accept`'s docstring.

    A row whose ``name`` is unusable provisions nothing, as before: without a
    name there is no identity to derive and therefore no row a profile could
    point at.
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

    _provision_speaker_profile(
        session,
        tenant_id=tenant_id,
        owning_unit_id=owning_unit_id,
        review_item_id=review_item_id,
        professional_id=subject_id,
        name=name,
        row_data=row_data,
        accepted_at=accepted_at,
    )

    return ProvisionOutcome(professional_subject_id=subject_id)


def _provision_speaker_profile(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    owning_unit_id: uuid.UUID,
    review_item_id: uuid.UUID,
    professional_id: uuid.UUID,
    name: str,
    row_data: Mapping[str, Any],
    accepted_at: datetime,
) -> None:
    """Write the §19 speaker record and its unreviewed classification proposal.

    Separated from the identity provisioning above so a failure here is
    attributable: the account and the link are this unit's roster membership,
    and the profile is what that member's record says.

    A row this function cannot turn into a valid draft — a blank field that
    ``SpeakerContactDraft.create`` refuses — is logged and skipped rather than
    raised. The identity has already been provisioned and the accept has already
    been recorded; failing the whole request over an unusable optional field
    would roll back a decision a coordinator legitimately made, and the row is
    still in ``review_item.row_data`` for anybody investigating. The silent-zero
    rule is honoured by the WARNING, not by pretending the profile exists.
    """
    try:
        draft = SpeakerContactDraft.create(
            full_name=name,
            # The classification codes are deliberately not passed. A draft
            # carrying them would store them as `human` attributed to whoever
            # accepted the row — see `_draft_values` — and the whole point of
            # this path is that nobody has reviewed them yet. They reach the row
            # through the proposal below instead.
            **_profile_fields(row_data),
        )
    except ValueError:
        logger.warning(
            "accepted professionals review_item %s in unit %s could not be turned "
            "into a speaker record; the synthetic identity was provisioned and no "
            "speaker_profile was written",
            review_item_id,
            owning_unit_id,
        )
        return

    proposal = _classify(row_data, draft=draft)

    _contacts.create_from_import(
        session,
        tenant_id=tenant_id,
        owning_unit_id=owning_unit_id,
        professional_id=professional_id,
        draft=draft,
        proposal=proposal,
        at=accepted_at,
    )


def _profile_fields(row_data: Mapping[str, Any]) -> dict[str, str | None]:
    """The optional ``speaker_profile`` fields this row states, blanks removed.

    A cell a coordinator left empty arrives as ``""`` or as a whitespace string
    rather than as an absence, and ``ck_speaker_profile_text_present`` refuses a
    blank in every one of these columns. Normalizing to ``None`` here makes the
    absence a stated one — the same distinction §13's create surface draws — so
    an empty Company reads as "this person has none", not as a company whose
    name is nothing.

    Non-string values are dropped rather than coerced. ``str()`` on a number a
    coordinator typed into the wrong column would store it as though it were a
    company name, which is worse than the field being absent.
    """
    fields: dict[str, str | None] = {}
    for row_key, profile_field in _PROFESSIONAL_PROFILE_KEYS.items():
        value = row_data.get(row_key)
        fields[profile_field] = value.strip() if isinstance(value, str) and value.strip() else None
    return fields


def _classify(
    row_data: Mapping[str, Any], *, draft: SpeakerContactDraft
) -> ContactClassificationProposal:
    """Propose both axes: the export's own code first, then the classifier.

    Two readers, tried in that order, and both produce a **proposal**. Neither
    is a fact and neither is stored as one.

    The export's stated code goes first because it is the coordinator's own
    answer about their own person, and discarding it in favour of a guess from
    the company name would throw away better evidence for worse. It is still
    only a proposal: it arrived on a spreadsheet, nobody in this system has
    reviewed it, and ``docs/pilot-data/columns.yaml`` says explicitly that the
    import contract does not validate it, "resolve a display name to a code, or
    infer either one from company or title. That is CBA-IMPORT-CLASSIFY's work".

    All three of those are here. ``resolve_sector`` / ``resolve_role_category``
    accept §7's and §8's **names** as well as their codes, in any casing, so a
    coordinator who exported ``"Finance and Insurance"`` under a column named
    ``primary_industry_code`` is understood rather than silently dropped — the
    display-name resolution that sentence assigns to this card. They accept
    nothing else: a misspelling, or a code from some other vocabulary, resolves
    to nothing rather than being stored because a coordinator typed it.

    The classifier reads company and title when the export stated no usable
    code. It is the deterministic fixture and makes no network call — see
    :func:`smartmatch_providers.cba_classification.build_contact_classifier`,
    which refuses a live adapter under every edition (OQ-CBA-039).

    An axis neither reader resolves is left **undetermined**, which stores as
    NULL. Nothing here falls back to a most-common sector, a nearest match, or a
    token overlap: the raw company and title text is stored on the same row
    where a reviewer reads it, so a guess would add nothing but the appearance
    of an answer (OQ-CBA-010, ADR-0011).
    """
    settings = get_settings()
    classifier = build_contact_classifier(
        settings.edition,
        use_fixture=settings.use_fixture_providers,
    )
    proposed = classifier.propose(company=draft.company, title=draft.title)

    return ContactClassificationProposal(
        industry=_stated_code(row_data, axis="industry") or proposed.industry,
        role=_stated_code(row_data, axis="role") or proposed.role,
    )


def _stated_code(row_data: Mapping[str, Any], *, axis: str) -> ProposedClassification | None:
    """The export's own code for one axis, if it resolves; otherwise ``None``.

    ``None`` rather than an :class:`UndeterminedClassification`, because "this
    export stated nothing usable" is not yet an answer about the axis — the
    classifier has not been consulted. Returning an undetermined outcome here
    would end the search at the first reader and make the classifier
    unreachable for exactly the rows it exists to help.
    """
    value = row_data.get(_PROFESSIONAL_CODE_KEYS[axis])
    if not isinstance(value, str) or not value.strip():
        return None

    stated = value.strip()
    if axis == "industry":
        sector = resolve_sector(stated)
        if not isinstance(sector, ClassifiedSector):
            # Not an import failure and not a finding: the contract already said
            # an unrecognized value here is a review item's problem rather than
            # the batch's. The raw text stays in `review_item.row_data` where it
            # can be read, the axis stays unclassified, and a Connector decides.
            return None
        code, version = sector.sector.code, sector.taxonomy_version
    else:
        role = resolve_role_category(stated)
        if not isinstance(role, ClassifiedRoleCategory):
            return None
        code, version = role.category.code, role.taxonomy_version

    return ProposedClassification(
        code=code,
        taxonomy_version=version,
        # The text as the export wrote it, not the code it resolved to. A
        # reviewer looking at a proposal needs to see what the sheet actually
        # said — `"Finance and Insurance"` and `"52"` are the same proposal and
        # not the same evidence.
        evidence=stated,
        classifier=IMPORT_COLUMN_CLASSIFIER,
    )


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

    # Request one more row than the cap allows. That extra row coming back
    # is exactly the signal that distinguishes "the unit has more linked
    # professionals than the cap" from "the unit has exactly the cap's
    # worth" — a signal `limit=MAX_SYNTHETIC_JOURNEYS_PER_ACCEPT` alone
    # cannot give, because both cases return exactly MAX rows at that limit.
    subject_ids = _professionals.professional_ids_for_unit(
        session,
        tenant_id=tenant_id,
        unit_id=owning_unit_id,
        limit=MAX_SYNTHETIC_JOURNEYS_PER_ACCEPT + 1,
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

    if len(subject_ids) > MAX_SYNTHETIC_JOURNEYS_PER_ACCEPT:
        # Plan §1.10 again, one step short of zero: a truncated fan-out must
        # not read, from the log, the same as a complete one. Exactly at the
        # cap this branch is never taken — the len(subject_ids) == MAX case
        # lost nothing, and warning here would be a false positive.
        omitted = len(subject_ids) - MAX_SYNTHETIC_JOURNEYS_PER_ACCEPT
        logger.warning(
            "accepted in-list events review_item %s in unit %s links more "
            "professionals than the synthetic pilot cap of %d: opening journeys "
            "for only the %d smallest professional_id values; %d professional(s) "
            "were NOT opened a journey by this accept.",
            review_item_id,
            owning_unit_id,
            MAX_SYNTHETIC_JOURNEYS_PER_ACCEPT,
            MAX_SYNTHETIC_JOURNEYS_PER_ACCEPT,
            omitted,
        )
        subject_ids = subject_ids[:MAX_SYNTHETIC_JOURNEYS_PER_ACCEPT]

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
