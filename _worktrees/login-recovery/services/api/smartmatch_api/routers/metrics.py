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
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Annotated, Any, Final

import sqlalchemy as sa
from fastapi import APIRouter, Path, Request, Response, status
from pydantic import BaseModel, Field
from smartmatch_authz import OrgPath, Resource, assert_allowed
from smartmatch_domain.metrics import (
    METRIC_REGISTER,
    MetricDefinition,
    OpportunityCategoryShape,
    get_metric,
    shape_opportunity_category,
)
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


#: Which timestamp column on ``pipeline_record`` each Pipeline metric reads.
#: A canonical-name -> column mapping, spelled out explicitly rather than
#: derived by string-munging ``metric.canonical_name`` (e.g. stripping a
#: ``"pipeline_"`` prefix and appending ``"_at"``). The two would agree for
#: all five metrics that exist today, which is exactly what makes the
#: shortcut dangerous: a sixth Pipeline metric registered with a
#: ``canonical_name`` that does not spell its column exactly right (a rename,
#: a synonym, a metric that intentionally reads a *different* table's stage)
#: would still pattern-match some string and silently measure the wrong
#: stage, or the right-looking wrong column, instead of failing loudly. An
#: explicit table has no such derivation to get subtly wrong, and
#: :func:`_pipeline_funnel_rows_v1` fails closed with a ``RuntimeError`` — the
#: same posture :func:`_evidence_for` already takes on a missing owning-query
#: adapter — when a metric bound to ``pipeline_funnel_rows_v1`` is not a key
#: here.
_PIPELINE_STAGE_COLUMNS: Final[dict[str, sa.ColumnElement[Any]]] = {
    "pipeline_matched": schema.pipeline_record.c.matched_at,
    "pipeline_contacted": schema.pipeline_record.c.contacted_at,
    "pipeline_confirmed": schema.pipeline_record.c.confirmed_at,
    "pipeline_attended": schema.pipeline_record.c.attended_at,
    "pipeline_member_inquiry": schema.pipeline_record.c.member_inquiry_at,
}


def _pipeline_funnel_rows_v1(
    session: Session,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    metric: MetricDefinition,
) -> _MetricEvidence:
    """Measure one funnel stage from ``pipeline_record`` (P8 card O3).

    Migration ``0011`` (card O2) gave the five Pipeline metrics a real
    evidence table; this is the query card O3 binds them to. "Reached stage
    X" is exactly ``<stage>_at IS NOT NULL`` and nothing else — the same
    predicate ``tests/integration/test_pipeline_record_constraints.py``'s
    ``funnel_counts`` and ``funnel_rows`` helpers were written against, so
    this binding has something to be checked against rather than invented.
    Filtered by ``tenant_id`` and ``owning_unit_id`` (A5-shaped, written on
    the row rather than joined through the not-yet-existing ``event`` table —
    see migration ``0011``'s docstring), and ordered by ``matched_at, id`` to
    match those same helpers.

    An empty result here is a **measured zero**, not an unknown: the table
    exists and this query ran against it. That is a materially different
    claim from the honest-unknown stub this adapter used to return, and it is
    the entire point of this card — see the module docstring of
    ``smartmatch_domain.metrics`` for what a measured zero does and does not
    mean today (no application code writes ``pipeline_record`` yet, so a
    zero here means "no pipeline records exist for this unit", not "no
    matching has happened"; nothing in this adapter can distinguish those
    until a write path exists, and building one is out of scope for this
    card).

    The returned rows carry no imported row payload — unlike
    :func:`_pending_review_item_rows_v1`'s ``row_data``, which is exactly the
    submitted import row. A Pipeline journey has no "submission" to echo back;
    its rows are what a coordinator drilling in needs to identify and audit
    one journey: which student, which opportunity, and every stage timestamp
    reached so far. Drill-down authorization (:func:`_authorize_drill_down_read`)
    is unchanged either way — it gates access to the *rows*, not to any one
    column within them.
    """
    try:
        stage_column = _PIPELINE_STAGE_COLUMNS[metric.canonical_name]
    except KeyError as exc:  # fail closed: an unmapped Pipeline metric must not
        # silently measure the wrong stage (or none at all) instead of
        # refusing to answer, the same posture _evidence_for takes on a
        # missing owning-query adapter.
        raise RuntimeError(
            f"No pipeline stage column mapped for metric {metric.canonical_name!r}; "
            "add it to _PIPELINE_STAGE_COLUMNS."
        ) from exc

    result = session.execute(
        sa.select(
            schema.pipeline_record.c.id,
            schema.pipeline_record.c.subject_id,
            schema.pipeline_record.c.opportunity_event_id,
            schema.pipeline_record.c.matched_at,
            schema.pipeline_record.c.contacted_at,
            schema.pipeline_record.c.confirmed_at,
            schema.pipeline_record.c.attended_at,
            schema.pipeline_record.c.member_inquiry_at,
        )
        .where(
            schema.pipeline_record.c.tenant_id == tenant_id,
            schema.pipeline_record.c.owning_unit_id == unit_id,
            stage_column.is_not(None),
        )
        .order_by(schema.pipeline_record.c.matched_at, schema.pipeline_record.c.id)
    )
    rows = tuple(
        {
            "id": row.id,
            "subject_id": row.subject_id,
            "opportunity_event_id": row.opportunity_event_id,
            "matched_at": row.matched_at,
            "contacted_at": row.contacted_at,
            "confirmed_at": row.confirmed_at,
            "attended_at": row.attended_at,
            "member_inquiry_at": row.member_inquiry_at,
        }
        for row in result
    )
    return _MetricEvidence(rows=rows)


def _opportunities_rows_v1(
    session: Session,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    _metric: MetricDefinition,
) -> _MetricEvidence:
    """Measure accepted, in-list ``review_item`` rows (P8 card O3, P8 §3).

    P8 §3 permits counting import-origin opportunities before crawler
    persistence (P6) exists, so this binds to ``review_item`` — the same
    table :func:`_pending_review_item_rows_v1` already reads — filtered to
    rows a coordinator has moved to ``status = 'accepted'`` (a legal value
    under migration ``0008``'s ``ck_review_item_status`` independent of the
    parallel work adding the API route that sets it).

    The join to ``import_batch`` for unit scoping mirrors
    :func:`_pending_review_item_rows_v1` exactly, substituting ``'accepted'``
    for ``'pending'``: both metrics are "review_item rows in a given review
    status, owned by this unit", differing only in which status.

    The category filter runs in Python, deliberately, against
    ``row_data["category"]`` (JSONB) rather than as a SQL predicate:

    * ``"category"`` is the correct key because the worker normalizes every
      submitted header through ``smartmatch_domain.ingest.normalize_header``
      before writing ``row_data`` (``smartmatch_worker.handlers._normalize_row``
      calls it on every key). That function lower-cases, strips punctuation to
      spaces, and joins on ``"_"`` — so the events dataset's ratified column
      ``"Category"`` (``docs/pilot-data/columns.yaml``, required for the
      ``events`` dataset) is stored as ``"category"``, not ``"Category"``.
    * ``smartmatch_domain.metrics.shape_opportunity_category`` is the single
      ratified implementation of the counting rule (in-list vs. out-of-list
      vs. absent, case-insensitive, blank-folds-to-absent — see its
      docstring). Recreating that logic as a SQL ``casefold``/``IN (...)``
      clause would be a *second* owning query answering the same question the
      domain function already answers, which is precisely the defect
      ADR-0011 rule 4 exists to name: one number, one calculation. Filtering
      in Python after one ``SELECT`` keeps the calculation singular even
      though the predicate does not live in the ``WHERE`` clause.
    * This still satisfies ADR-0011 rule 3: exactly one query executes and
      returns its rows once, the Python filter is applied to that one result
      set, and the aggregate is ``len(rows)`` over the *filtered* tuple — so
      the aggregate and the drill-down are reading the same filtered
      collection and cannot drift apart.

    ``import_batch.dataset`` is deliberately **not** filtered on. It is free
    text supplied in the original import request body (``schema.py``:
    ``import_batch.dataset``), never validated against a fixed vocabulary, so
    it is caller-supplied metadata, not a contract this query can rely on.
    The category predicate — sourced from the ratified events-dataset column
    and the ratified counting rule — is the whole rule; a dataset-name filter
    would let mislabeled or free-text batches silently exclude in-list rows
    (or admit rows never meant to count) for a reason the register's
    definition says nothing about.
    """
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
            schema.review_item.c.status == "accepted",
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
        if shape_opportunity_category(_category_of(row.row_data))
        is OpportunityCategoryShape.IN_LIST
    )
    return _MetricEvidence(rows=rows)


def _category_of(row_data: Any) -> str | None:
    """Read a stored row's category, treating anything unexpected as absent.

    ``review_item.row_data`` is ``jsonb NOT NULL`` (migration ``0008``), and
    ``jsonb`` holds *any* JSON value — an object, but equally an array, a
    bare string, a number, or ``null``. The import path only ever writes an
    object of normalized headers
    (``smartmatch_worker.handlers._normalize_row``), so in practice every row
    is a mapping with string values; this function exists because "in
    practice" is not a guarantee the database enforces, and this is a read
    path that must not be able to fail.

    Without it, two shapes crash a metrics read with a ``500``: a non-object
    ``row_data`` has no ``.get``, and a non-string category has no
    ``.strip()`` — the latter reaching
    :func:`~smartmatch_domain.metrics.shape_opportunity_category`, whose
    signature is ``str | None`` and which is right not to defend itself
    against a type its callers are supposed to have established. Converting a
    stored row into that type is this boundary's job, which is where the
    repository's "never trust external data" rule puts it: storage is
    external to the domain.

    Anything that is not a string is reported as ``None``, which
    ``shape_opportunity_category`` reads as ``ABSENT`` — deliberately the
    same answer as a missing key, and deliberately not ``OUT_OF_LIST``. A row
    whose category is a number or a list has *no category recorded* in any
    sense a coordinator could review and map; filing it as an unmapped label
    would put it in the wrong queue, which is the distinction that enum's own
    docstring draws. Neither counts toward the metric, so a malformed row is
    excluded from the aggregate exactly as it is from the drill-down, and
    ADR-0011 rule 3 still holds.
    """
    if not isinstance(row_data, Mapping):
        return None
    category = row_data.get("category")
    return category if isinstance(category, str) else None


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

#: Roles whose **aggregate** reach is the whole tenant rather than their own
#: membership subtree (the ratified metrics-authorization decision §4, CLOSED
#: 2026-09-02: "``admin``: unrestricted within tenant for aggregates").
#:
#: Only ``admin``, and only for aggregates. Nothing in the schema requires an
#: ``admin`` membership to be rooted at the tenant root —
#: ``membership.granted_path`` is an ordinary ``ltree`` — so without this an
#: admin attached below the root is refused a sibling unit's aggregates, which
#: §4 does not say. Deliberately *not* passed by
#: :func:`_authorize_drill_down_read`: §4's scope bullet confines "unrestricted
#: within tenant" to aggregates and sends drill-down back to the row above it
#: in the same table, which is a *role* rule (``admin``/``coordinator``) and
#: says nothing about widening scope. Deny-by-default settles the rest: a
#: reading that widened row-level access to `row_data` across the tenant is a
#: permit §4 does not name, so drill-down keeps ordinary subtree containment.
_TENANT_WIDE_AGGREGATE_ROLES: Final[frozenset[str]] = frozenset({"admin"})


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

    §4's scope rules add one thing on top of that, which ordinary subtree
    containment cannot express: "``admin``: unrestricted within tenant for
    aggregates". :data:`_TENANT_WIDE_AGGREGATE_ROLES` carries it, via the
    policy's ``tenant_wide_roles`` keyword (module docstring rule 7) — so an
    active ``admin`` membership anywhere in the tenant reads any unit's
    aggregates, including a sibling unit its own path does not cover.
    Suspension, tenant mismatch, and an explicit resource deny are all decided
    ahead of it and are unaffected.
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
        tenant_wide_roles=_TENANT_WIDE_AGGREGATE_ROLES,
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

    No ``tenant_wide_roles`` here, unlike :func:`_authorize_aggregate_read`.
    §4's scope bullet reads "``admin``: unrestricted within tenant for
    aggregates; drill-down per row above", and the row above restricts
    ``metrics.drill_down`` by *role* (``admin``, ``coordinator``) without
    saying anything about scope. Drill-down therefore keeps ordinary subtree
    containment: an admin attached to a sibling unit reads that unit's
    aggregates but not another unit's ``row_data``, which §3 rates **High** —
    the full imported row payload, contact fields included (P9 Gate B). Under
    deny-by-default the narrower reading is the only one available, since the
    wider one would be a permit the closed decision does not name. See
    :data:`_TENANT_WIDE_AGGREGATE_ROLES`.
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
