"""Authorized, unit-scoped access to the ADR-0011 metric register.

Both the aggregate collection and a metric's drill-down resolve through
``_OWNING_QUERIES``. A storage-backed query returns its constituent rows once;
the aggregate is ``len(rows)`` and the drill-down returns those rows. There is
no separate COUNT query whose filters can drift from the row query.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any, Final

import sqlalchemy as sa
from fastapi import APIRouter, Path, Request, Response, status
from pydantic import BaseModel, Field
from smartmatch_authz import OrgPath, Resource, assert_allowed
from smartmatch_domain.metrics import METRIC_REGISTER, MetricDefinition, get_metric
from smartmatch_persistence import schema
from sqlalchemy.orm import Session

from smartmatch_api.dependencies import CurrentPrincipal, DbSession
from smartmatch_api.errors import ApiError
from smartmatch_api.units import load_unit_or_404
from smartmatch_api.utils import utc_now

router = APIRouter(prefix="/v1/units", tags=["metrics"])


class MetricSummary(BaseModel):
    """One registered metric and its current accountable value."""

    name: str
    display_name: str
    definition: str
    value: int | None = Field(
        description="Measured row count, or null when no evidence source exists."
    )
    unknown_reason: str | None = Field(
        default=None,
        description="Why value is unknown; absent when value is measured.",
    )
    drill_down_url: str


class MetricsResponse(BaseModel):
    """All accountable metrics registered for an organizational unit."""

    unit_id: uuid.UUID
    metrics: list[MetricSummary]


class MetricDrillDownResponse(BaseModel):
    """The exact rows from which one aggregate was calculated."""

    unit_id: uuid.UUID
    name: str
    definition: str
    aggregate_value: int | None
    unknown_reason: str | None = None
    rows: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class _MetricEvidence:
    """A query result before it is rendered into either API response."""

    rows: tuple[dict[str, Any], ...]
    unknown_reason: str | None = None

    @property
    def value(self) -> int | None:
        """Count known rows, preserving unknown as ``None``."""
        if self.unknown_reason is not None:
            return None
        return len(self.rows)


_OwningQuery = Callable[[Session, uuid.UUID, uuid.UUID, MetricDefinition], _MetricEvidence]


def _pipeline_funnel_rows_v1(
    _session: Session,
    _tenant_id: uuid.UUID,
    _unit_id: uuid.UUID,
    metric: MetricDefinition,
) -> _MetricEvidence:
    """Report honest absence until S12 provides Pipeline evidence."""
    assert metric.unknown_reason is not None
    return _MetricEvidence(rows=(), unknown_reason=metric.unknown_reason)


def _opportunities_rows_v1(
    _session: Session,
    _tenant_id: uuid.UUID,
    _unit_id: uuid.UUID,
    metric: MetricDefinition,
) -> _MetricEvidence:
    """Report honest absence until S12 pipeline persistence provides evidence.

    Shared interface contract (P1/V4 + P8/V5 card O1): the ``opportunities``
    metric registers with ``owning_query = "opportunities_rows_v1"``, and this
    is its adapter. Cards O2 (persistence) and O3 (owning-query binding) give
    it a real storage-backed query later; until then it carries the same
    honest-unknown shape :func:`_pipeline_funnel_rows_v1` already uses for an
    absent evidence source.
    """
    assert metric.unknown_reason is not None
    return _MetricEvidence(rows=(), unknown_reason=metric.unknown_reason)


def _pending_review_item_rows_v1(
    session: Session,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    _metric: MetricDefinition,
) -> _MetricEvidence:
    """Return every pending review row owned by ``unit_id``, once."""
    result = session.execute(
        sa.select(
            schema.review_item.c.id,
            schema.review_item.c.import_batch_id,
            schema.review_item.c.row_index,
            schema.review_item.c.status,
            schema.review_item.c.row_data,
        )
        .join(
            schema.import_batch,
            sa.and_(
                schema.import_batch.c.tenant_id == schema.review_item.c.tenant_id,
                schema.import_batch.c.id == schema.review_item.c.import_batch_id,
            ),
        )
        .where(
            schema.review_item.c.tenant_id == tenant_id,
            schema.import_batch.c.owning_unit_id == unit_id,
            schema.review_item.c.status == "pending",
        )
        .order_by(schema.review_item.c.created_at, schema.review_item.c.id)
    )
    rows = tuple(
        {
            "id": row.id,
            "import_batch_id": row.import_batch_id,
            "row_index": row.row_index,
            "status": row.status,
            "row_data": row.row_data,
        }
        for row in result
    )
    return _MetricEvidence(rows=rows)


_OWNING_QUERIES: dict[str, _OwningQuery] = {
    "pipeline_funnel_rows_v1": _pipeline_funnel_rows_v1,
    "pending_review_item_rows_v1": _pending_review_item_rows_v1,
    "opportunities_rows_v1": _opportunities_rows_v1,
}

#: Roles permitted to drill into a metric's constituent rows (the ratified
#: metrics-authorization decision, Option B —
#: ``docs/decisions/metrics-authorization-decision-draft.md`` §4, CLOSED
#: 2026-09-02). Row-level drill-down carries ``row_data`` — the full imported
#: row payload, which may include contact fields (P9 Gate B) — so it is
#: deliberately tighter than the aggregate read below.
_DRILL_DOWN_ROLES: Final[frozenset[str]] = frozenset({"admin", "coordinator"})


def _authorize_aggregate_read(
    session: Session,
    principal: CurrentPrincipal,
    unit_id: uuid.UUID,
) -> None:
    """Load the unit and authorize aggregate metric reads.

    Per the ratified decision's §4: any **active unit membership with a
    role** may read aggregates; a bare ``resource_grant`` is denied. There is
    no finite role set to enumerate — ``membership.role`` is free text
    (``schema.py``) — so this is expressed with no ``required_roles`` at all
    (any active membership's role suffices) plus ``require_membership=True``,
    which withdraws the explicit-grant path as a substitute for holding no
    membership. See ``smartmatch_authz.policy`` module docstring rule 5 and
    ``tests/authz/test_policy_matrix.py`` (:data:`MEMBERSHIP_ONLY_OPERATIONS`).
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
        require_membership=True,
    )


def _authorize_drill_down_read(
    session: Session,
    principal: CurrentPrincipal,
    unit_id: uuid.UUID,
) -> None:
    """Load the unit and authorize row-level drill-down reads.

    Per the ratified decision's §4: only ``admin`` and ``coordinator`` may
    drill into a metric's constituent rows, which is an ordinary role-gated
    operation (:data:`_DRILL_DOWN_ROLES`). ``require_membership=True`` is
    still passed alongside it: it has no observable effect once
    ``required_roles`` is non-empty (a bare grant is already refused by the
    required-roles check first), but it keeps this authorizer's shape
    consistent with :func:`_authorize_aggregate_read` and with what the
    decision record actually authorizes — membership, not mere resource
    reach, admin/coordinator role notwithstanding.
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
        required_roles=_DRILL_DOWN_ROLES,
        require_membership=True,
    )


def _evidence_for(
    session: Session,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    metric: MetricDefinition,
) -> _MetricEvidence:
    """Dispatch a metric through its one registered owning query."""
    try:
        query = _OWNING_QUERIES[metric.owning_query]
    except KeyError as exc:  # fail closed if register and API adapter drift
        raise RuntimeError(f"No owning query adapter for {metric.owning_query!r}") from exc
    return query(session, tenant_id, unit_id, metric)


def _summary(
    unit_id: uuid.UUID,
    metric: MetricDefinition,
    evidence: _MetricEvidence,
) -> MetricSummary:
    return MetricSummary(
        name=metric.canonical_name,
        display_name=metric.display_name,
        definition=metric.definition,
        value=evidence.value,
        unknown_reason=evidence.unknown_reason,
        drill_down_url=f"/v1/units/{unit_id}/metrics/{metric.canonical_name}/drill-down",
    )


_NOT_MODIFIED_RESPONSE: Final[dict[int | str, dict[str, Any]]] = {
    status.HTTP_304_NOT_MODIFIED: {
        "description": (
            "Not Modified: the payload named by If-None-Match is still current. "
            "The body is empty; Cache-Control and ETag repeat the values a "
            "matching 200 would have carried."
        ),
    },
}


def _etag_matches(if_none_match: str | None, etag: str) -> bool:
    """Weakly compare an ``If-None-Match`` header against ``etag`` (RFC 9110 §8.8.3.2).

    ``If-None-Match`` may carry a comma-separated list of entity tags, any of
    which may be marked weak (``W/"..."``), or the literal ``*`` which matches
    any current representation. Weak comparison only requires the opaque tags
    to be equal, so the ``W/`` prefix is stripped from both sides before
    comparing -- this endpoint only ever issues weak tags (the payload is
    derived from row contents, not verified byte-for-byte across requests).
    """
    if if_none_match is None:
        return False
    if if_none_match.strip() == "*":
        return True
    candidate = etag.removeprefix("W/")
    for raw_tag in if_none_match.split(","):
        tag = raw_tag.strip().removeprefix("W/")
        if tag == candidate:
            return True
    return False


def _conditional_json_response(payload_model: BaseModel, request: Request) -> Response:
    """Serve ``payload_model`` with revalidation headers, honoring If-None-Match.

    The ETag is a weak hash of the exact bytes returned, computed by
    serializing ``payload_model`` deterministically (sorted keys, no
    incidental whitespace) and hashing that serialization -- never a separate
    representation than the one sent, so a client's cached copy can never
    drift from what this handler would compute for the same data.

    ``Cache-Control`` is fixed at ``private, max-age=0, must-revalidate``.
    ``private`` is mandatory, not a default: every metrics payload is scoped to
    one authorized principal's view of one unit (ADR-0011's accountable
    numbers are meaningless outside that authorization context), so this
    response must never be eligible for a shared cache -- a proxy or CDN
    serving it to a second principal would leak one tenant's counts to
    another. ``max-age=0, must-revalidate`` forces a revalidation round trip on
    every use, so a client can skip re-transferring an unchanged body but can
    never present a stale value as live.
    """
    payload = payload_model.model_dump(mode="json")
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    etag = f'W/"{hashlib.sha256(body).hexdigest()}"'
    headers = {
        "Cache-Control": "private, max-age=0, must-revalidate",
        "ETag": etag,
    }
    if _etag_matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)


@router.get(
    "/{unit_id}/metrics",
    response_model=MetricsResponse,
    responses=_NOT_MODIFIED_RESPONSE,
    summary="List accountable metrics for a unit",
)
def list_metrics(
    principal: CurrentPrincipal,
    session: DbSession,
    request: Request,
    unit_id: Annotated[uuid.UUID, Path()],
) -> Response:
    """Return registered metrics, preserving unknown values as null.

    Authorization runs before any conditional-request handling: an
    ``If-None-Match`` header must never let an unauthorized or unknown caller
    learn that a 304-eligible representation exists. Any active unit
    membership with a role may read aggregates (a bare ``resource_grant`` is
    refused) — see :func:`_authorize_aggregate_read`.
    """
    _authorize_aggregate_read(session, principal, unit_id)
    metrics = [
        _summary(
            unit_id,
            metric,
            _evidence_for(session, principal.tenant_id, unit_id, metric),
        )
        for metric in METRIC_REGISTER
    ]
    response_model = MetricsResponse(unit_id=unit_id, metrics=metrics)
    return _conditional_json_response(response_model, request)


@router.get(
    "/{unit_id}/metrics/{metric_name}/drill-down",
    response_model=MetricDrillDownResponse,
    responses=_NOT_MODIFIED_RESPONSE,
    summary="Drill into an accountable metric",
)
def metric_drill_down(
    principal: CurrentPrincipal,
    session: DbSession,
    request: Request,
    unit_id: Annotated[uuid.UUID, Path()],
    metric_name: Annotated[str, Path(min_length=1)],
) -> Response:
    """Return exactly the rows the named metric's aggregate counted.

    Authorization and the metric-not-found check both run before any
    conditional-request handling, for the same reason as ``list_metrics``: a
    404 must never be short-circuited into a 304 by a caller replaying an
    ETag it never legitimately received. Only ``admin`` and ``coordinator``
    may drill into rows — see :func:`_authorize_drill_down_read`.
    """
    _authorize_drill_down_read(session, principal, unit_id)
    metric = get_metric(metric_name)
    if metric is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="metric_not_found",
            message="No such registered metric.",
        )

    evidence = _evidence_for(session, principal.tenant_id, unit_id, metric)
    response_model = MetricDrillDownResponse(
        unit_id=unit_id,
        name=metric.canonical_name,
        definition=metric.definition,
        aggregate_value=evidence.value,
        unknown_reason=evidence.unknown_reason,
        rows=list(evidence.rows),
    )
    return _conditional_json_response(response_model, request)
