"""A Speaker Connector's view of, and control over, one unit's matching weights.

Customer §13: "manage matching weights". Customer §5: one configurable location,
no scattered or duplicated hard-coded values, "a basic settings mechanism is
sufficient". These two routes are that mechanism — a read of what is in force and
a write of what should be.

## The response shows *effective* weights, and stores none of them

``GET`` returns two things that are easy to confuse and must not be. ``overrides``
is what this unit has stored — often empty, and never containing a factor the
Connector has not deliberately changed. ``modes`` is what a run would actually
score with, per scoring mode, computed at request time by
:func:`smartmatch_domain.weight_settings.applied_weights` from the registry plus
those overrides.

Only the first is persisted. The second is derived on every read and is
deliberately *not* stored anywhere, because a stored effective weight is a copy
of a registry default with a timestamp on it — the exact duplication §5 forbids,
and the one that would keep serving yesterday's approved figure after ADR-0016
revised it.

For the same reason there is no default in this module: no ``Field`` default
naming a weight, no placeholder for a form, no example value in a schema. A
factor the Connector has not set is absent from ``overrides`` and present in
``modes`` at whatever the registry says today.

## Refusal, and what each refusal is

* **422 ``invalid_matching_weights``** — the proposal is inadmissible.
  :func:`~smartmatch_domain.weight_settings.validate_weight_overrides` decides
  that, and its message names every offending field at once. Nothing is
  normalized, clamped or dropped on the way through: a Connector who typed a
  negative number is told so, rather than getting a 200 and a weighting they did
  not ask for.
* **409 ``matching_weights_stale``** — ``expected_version`` did not match. Two
  Connectors with the settings page open is the ordinary case, and the
  alternative to refusing the second save is that it silently discards the first
  while the audit log records both as successful.
* **404** — the unit is not in the caller's tenant. ``load_unit_or_404`` scopes
  by tenant, so a real unit elsewhere is a 404 rather than a 403 confirming that
  it exists.

## Authorization is server-side, and a screen cannot widen it

:func:`_authorize_matching_weights` loads the unit and evaluates the policy
against *that row's* ``ltree`` path, never against anything in the request. The
role set is ``{admin, coordinator}`` — the Speaker Connector persona as every
other Connector surface in this package spells it (``routers/cba_contacts.py``,
``routers/match_runs.py``, ``routers/outreach.py``). A ``student`` and a
``volunteer`` are refused both routes, including the read: the weights are the
rulebook the shortlist is produced under, and they are coordinator material for
the reason the shortlist itself is.

Whether a UI renders a weights panel decides nothing. The panel is a label; the
permit is that function, and ``tests/authz/test_policy_matrix.py`` runs both
operations through it cell by cell.

## What changing a weight does not do

It does not touch a stored run. A ``match_run`` row carries the weights it was
scored with (migration ``0018``) and is immutable; nothing in this module writes
that table, and no foreign key runs from a run to a setting. A run recorded
yesterday reports yesterday's weights after a change made today, and
``tests/integration/test_cba_weight_settings_persistence.py`` proves that against the table
rather than against a response.

It also does not re-run anything. A new weighting applies to the next run
submitted, and OQ-CBA-032 records the unanswered question of whether it should
have to pass MM-005's shadow-evaluation gate first.

## There is no frontend for this yet, on purpose

Deferred in writing, in ``docs/plans/open-questions/cba-phase-deferred.md``
("Connector weights UI — deferred by ``CBA-MATCH-WEIGHTS``"). The short version:
the ``GET`` already returns the effective weights a panel would have had to
compute, so a later UI renders this contract rather than designing anything new;
and a weights form is the exact shape that goes wrong as a control with nothing
behind it, which this repository treats as a defect rather than as a smaller
product. Read that entry before building one — it names what the panel owes,
including that it must never print a registry default as a placeholder.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Annotated, Final

from fastapi import APIRouter, Path, status
from pydantic import BaseModel, Field
from smartmatch_authz import OrgPath, Resource, assert_allowed
from smartmatch_domain.factor_registry import (
    REGISTRY_VERSION,
    SCORING_MODELS,
    ScoringModel,
)
from smartmatch_domain.weight_settings import (
    InvalidWeightOverrideError,
    applied_weights,
    configurable_factor_keys,
    validate_weight_overrides,
)
from smartmatch_persistence.match_weight_settings import (
    MatchWeightSettingRecord,
    MatchWeightSettingRepository,
    StaleWeightSettingsError,
)
from smartmatch_persistence.rate_limit import RateLimit
from sqlalchemy.orm import Session

from smartmatch_api.dependencies import CurrentPrincipal, DbSession, charge_quota
from smartmatch_api.errors import ApiError
from smartmatch_api.units import load_unit_or_404
from smartmatch_api.utils import utc_now

router = APIRouter(prefix="/v1/units", tags=["matching-weights"])

#: Roles permitted to read and to change a unit's matching weights. The Speaker
#: Connector persona, spelled as every other Connector surface in this package
#: spells it. A literal ``frozenset`` rather than an import of
#: ``match_runs._MATCH_RUN_ROLES``, for the reason ``tests/authz/test_route_roles.py``
#: gives: several role sets agreeing today is not a reason a widening of one
#: should silently widen the others.
_MATCHING_WEIGHTS_ROLES: Final[frozenset[str]] = frozenset({"admin", "coordinator"})

#: v1.1 §3.4 pilot defaults, the shape ``routers/cba_contacts.py`` uses: a read is
#: bounded loosely, a write more tightly. A weight change is rare by nature — it
#: is a policy decision, not a workflow step — so the write bucket is sized for a
#: person adjusting a form, not for a client polling one.
MATCHING_WEIGHTS_READ_RATE_LIMIT: Final[RateLimit] = RateLimit(
    operation="matching_weights.read", max_requests=120, window=timedelta(minutes=1)
)
MATCHING_WEIGHTS_WRITE_RATE_LIMIT: Final[RateLimit] = RateLimit(
    operation="matching_weights.update", max_requests=30, window=timedelta(minutes=1)
)


_settings = MatchWeightSettingRepository()


# ---------------------------------------------------------------------------
# Wire models
# ---------------------------------------------------------------------------


class ScoringModeWeightsView(BaseModel):
    """What one scoring mode would actually score with, right now.

    Derived on every read from the registry and this unit's overrides. Not
    stored, and deliberately so — see the module docstring.
    """

    scoring_mode: str = Field(description="The scoring mode these weights apply to.")
    registry_version: str = Field(
        description="The registry release the weights are normalized under."
    )
    weights: dict[str, float] = Field(
        description=(
            "Normalized weights over this mode's factors, summing to 1.0. A factor the "
            "unit has not overridden carries the registry's own weight."
        )
    )


class MatchingWeightsResponse(BaseModel):
    """One unit's weight configuration, and what it currently amounts to."""

    unit_id: uuid.UUID
    registry_version: str = Field(
        description="The factor registry release in force for this response."
    )
    configurable_factors: list[str] = Field(
        description=(
            "Every factor key a weight may be set for. Derived from the registry's "
            "approved scoring set, so it moves when the registry does."
        )
    )
    overrides: dict[str, float] = Field(
        description=(
            "The weights this unit has deliberately set. A factor absent here has no "
            "stored weight anywhere and reads the registry's."
        )
    )
    modes: list[ScoringModeWeightsView] = Field(
        description="The effective weights per scoring mode, computed for this response."
    )
    version: int | None = Field(
        default=None,
        description=(
            "The stored settings version, or null for a unit that has never configured "
            "anything. Echo it back as expected_version to avoid a lost update."
        ),
    )
    updated_by_user_id: uuid.UUID | None = Field(
        default=None,
        description="Who last changed these settings, or null if nobody has.",
    )
    updated_at: datetime | None = Field(
        default=None, description="When they were last changed, or null if never."
    )
    ignored_factor_keys: list[str] = Field(
        default_factory=list,
        description=(
            "Stored keys no current registry model admits — reported rather than "
            "silently dropped. Normally empty; non-empty means a factor was retired "
            "after this unit configured it."
        ),
    )


class MatchingWeightsUpdateRequest(BaseModel):
    """A proposed weighting for one unit.

    ``overrides`` is the **complete** override set after the change, not a patch
    of a patch: sending ``{}`` resets the unit to the registry's weights, and
    omitting a factor that was previously overridden clears that override.
    Merge-with-existing semantics would have made "clear this one" unexpressible
    without a second field, and would leave a Connector unable to tell what they
    were about to save from what they had typed.
    """

    overrides: dict[str, float] = Field(
        description=(
            "The complete set of factor weights this unit overrides. Send {} to return "
            "the unit to the registry's approved weights. No default: a factor omitted "
            "here has no stored weight at all."
        )
    )
    expected_version: int | None = Field(
        default=None,
        description=(
            "The version this change is based on, from a prior read. When it no longer "
            "matches, the change is refused with 409 rather than overwriting whatever "
            "arrived in between. Null writes without an opinion."
        ),
    )


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


def _authorize_matching_weights(
    session: Session,
    principal: CurrentPrincipal,
    unit_id: uuid.UUID,
) -> uuid.UUID:
    """Load the unit and authorize the caller against *that row's* path.

    Shared by both operations because both ask the identical question against the
    identical resource — may this caller work with this unit's matching weights —
    in the same spirit as ``routers/match_runs.py::_authorize_match_run``: a
    widening applies to both surfaces or to neither, and cannot reach one by
    accident.

    No ``require_membership`` and no ``tenant_wide_roles``:
    :data:`_MATCHING_WEIGHTS_ROLES` is non-empty, so ``evaluate`` already refuses
    a bare ``resource_grant`` on the required-roles check (S-007), and the only
    committed artifact that makes anything tenant-wide is the metrics decision's
    §4, which says it of aggregate reads specifically.

    Returns:
        The loaded unit's own id — the value the settings row is filed under, so
        the configuration is scoped to the subtree the request was permitted for.
    """
    unit = load_unit_or_404(session, tenant_id=principal.tenant_id, unit_id=unit_id)
    assert_allowed(
        principal.principal,
        Resource(
            resource_type="org_unit",
            resource_id=str(unit_id),
            tenant_id=str(principal.tenant_id),
            owning_unit_path=OrgPath.parse(unit.path),
        ),
        at=utc_now(),
        required_roles=_MATCHING_WEIGHTS_ROLES,
    )
    return unit.id


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _mode_view(
    mode: str,
    model: ScoringModel,
    overrides: dict[str, float],
) -> ScoringModeWeightsView:
    return ScoringModeWeightsView(
        scoring_mode=mode,
        registry_version=model.registry_version,
        weights=dict(applied_weights(overrides, model=model)),
    )


def _modes_view(overrides: dict[str, float]) -> list[ScoringModeWeightsView]:
    """The effective weights for every current scoring mode.

    Sorted by mode so two responses are comparable, and computed rather than
    stored so a registry revision reaches this response the day it lands.
    """
    return [_mode_view(mode, model, overrides) for mode, model in sorted(SCORING_MODELS.items())]


def _response(
    unit_id: uuid.UUID,
    record: MatchWeightSettingRecord | None,
) -> MatchingWeightsResponse:
    """Render a unit's configuration, present or absent.

    ``record is None`` is a unit that has never configured anything, and it is
    rendered as empty overrides with a null version, author and timestamp — *not*
    as version 0 or as a synthetic author. Inventing either would make a unit
    that has never been touched indistinguishable from one that was reset, which
    the persistence layer goes out of its way to keep apart.
    """
    overrides = {} if record is None else dict(record.settings.overrides)
    return MatchingWeightsResponse(
        unit_id=unit_id,
        registry_version=REGISTRY_VERSION,
        configurable_factors=list(configurable_factor_keys()),
        overrides=overrides,
        modes=_modes_view(overrides),
        version=None if record is None else record.settings.version,
        updated_by_user_id=(
            None if record is None else uuid.UUID(record.settings.updated_by_user_id)
        ),
        updated_at=None if record is None else record.settings.updated_at,
        ignored_factor_keys=[] if record is None else list(record.ignored_factor_keys),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/{unit_id}/matching-weights",
    response_model=MatchingWeightsResponse,
    summary="Read a unit's matching weights and what they currently amount to",
)
def read_matching_weights(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
) -> MatchingWeightsResponse:
    """Return this unit's overrides and the effective weights per scoring mode.

    A unit that has never configured anything is a 200 with empty overrides and a
    null version — not a 404. There is nothing missing: the unit scores on the
    registry's approved weights, which is what ``modes`` reports.

    Quota is charged first (ADR-0015), ahead of the load and the authorization,
    so a caller producing 404s against invented unit ids spends what a caller
    reading real ones spends.
    """
    charge_quota(session, principal, MATCHING_WEIGHTS_READ_RATE_LIMIT)
    owning_unit_id = _authorize_matching_weights(session, principal, unit_id)
    record = _settings.get(session, tenant_id=principal.tenant_id, owning_unit_id=owning_unit_id)
    return _response(owning_unit_id, record)


@router.patch(
    "/{unit_id}/matching-weights",
    response_model=MatchingWeightsResponse,
    summary="Change a unit's matching weights",
)
def update_matching_weights(
    principal: CurrentPrincipal,
    session: DbSession,
    body: MatchingWeightsUpdateRequest,
    unit_id: Annotated[uuid.UUID, Path()],
) -> MatchingWeightsResponse:
    """Validate the proposal, record it, and log the change.

    The write commits explicitly. ``get_session`` rolls back unconditionally on
    exit, so a handler that returned without committing would answer 200 and
    store nothing — which is why the integration test asserts against the tables
    and not against this response.

    Raises:
        ApiError: 422 when the proposal is inadmissible, naming every offending
            field; 409 when ``expected_version`` is no longer current.
    """
    charge_quota(session, principal, MATCHING_WEIGHTS_WRITE_RATE_LIMIT)
    owning_unit_id = _authorize_matching_weights(session, principal, unit_id)

    try:
        overrides = validate_weight_overrides(body.overrides)
    except InvalidWeightOverrideError as exc:
        # 422 rather than 400: the body parsed and its shape is right, and what
        # is wrong is what the values mean. Nothing is repaired on the way
        # through — see the module docstring.
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="invalid_matching_weights",
            message=f"These weights cannot be applied: {exc}",
        ) from exc

    try:
        record = _settings.put(
            session,
            tenant_id=principal.tenant_id,
            owning_unit_id=owning_unit_id,
            overrides=overrides,
            actor_user_id=principal.user_id,
            expected_version=body.expected_version,
            now=utc_now(),
        )
    except StaleWeightSettingsError as exc:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="matching_weights_stale",
            message=(
                "These weights were changed by someone else since you read them. "
                f"Re-read them and reapply your change. {exc}"
            ),
        ) from exc

    session.commit()
    return _response(owning_unit_id, record)
