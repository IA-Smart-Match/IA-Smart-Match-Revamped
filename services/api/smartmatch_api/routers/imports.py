"""Import command resource.

Architecture v1.1 §1.11 lists ``/imports`` among the explicit command resources
that replace the v1.0 generic job endpoint. It ships first among them because it
is the only one whose downstream work is already gated correctly: imports feed
the quarantine-and-review path (v1.1 §1.5), producing review items rather than
verified records, so accepting one commits no policy the open decisions have not
settled.

Match-run, discovery, and send commands follow the *same* shape via
:func:`~smartmatch_api.commands.submit_command`, but each waits on its gate —
match-runs on G1 (factor registry), discovery on G3 (agent controls), sends on
G4 (consent-origin policy).

## Rows travel in ``job.payload``, and that is a considered choice

``rows`` can be up to :data:`MAX_INLINE_ROWS_BYTES` (2 MB) of already-parsed
data, and ``submit_command`` writes the whole request payload — rows included —
into ``job.payload``, a ``jsonb`` column, as part of the job's own INSERT
(migration ``0005``). Putting up to 2 MB there is deliberate, not an oversight:

* ``job.payload`` is never read back to a caller. ``GET /v1/jobs/{id}``
  (``routers/jobs.py``) returns ``JobStatusResponse``, which has no ``payload``
  field; only ``job_event.payload`` — the small, explicit summaries this
  handler's terminal event carries — is ever rendered in a response. So the 2
  MB is write-only from the API's perspective: it is never re-serialized into
  an HTTP response, only read once by the worker.
* PostgreSQL's ``jsonb`` TOASTs values past about 2 KB automatically, and its
  practical ceiling is far above 2 MB — this is an ordinary size for the
  column, not a stress case.
* The alternative — a staging table the router writes rows into and the worker
  reads back by id — needs a migration and a schema change, both out of this
  track's remit (see the module notice this track was given: `schema.py`,
  `db/migrations/**` are not to be touched). Given the two points above, that
  alternative is not needed to make this safe; it would be worth reconsidering
  only if a future bound raised `rows` well past what a single durable command
  payload should reasonably carry.
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from typing import Annotated, Any, Final

from fastapi import APIRouter, Header, Path, status
from pydantic import BaseModel, Field
from smartmatch_authz import OrgPath, Resource, assert_allowed
from smartmatch_persistence.rate_limit import RateLimit

from smartmatch_api.commands import submit_command
from smartmatch_api.dependencies import CurrentPrincipal, DbSession, charge_quota
from smartmatch_api.errors import ApiError
from smartmatch_api.units import load_unit_or_404
from smartmatch_api.utils import utc_now

router = APIRouter(prefix="/v1/units", tags=["imports"])

#: v1.1 §3.4 gives pilot defaults as hypotheses to tune with recorded evidence.
#: Imports are deliberately tighter than reads: each one queues durable work.
IMPORT_RATE_LIMIT = RateLimit(
    operation="import.create",
    max_requests=10,
    window=timedelta(minutes=1),
)

#: Roles permitted to submit an import. An explicit set rather than "any
#: membership": importing records into a unit is a consequential act.
_IMPORT_ROLES = frozenset({"admin", "coordinator"})

#: Most rows one ``rows`` submission may carry. This is a route that queues
#: durable work — every accepted row becomes a job payload, and eventually a
#: review item — so an unbounded body is a denial-of-service surface, not
#: merely a large request. Chosen as a round number comfortably above any
#: pilot cohort's real roster size (v1.1 §3.4's pilot defaults are hypotheses
#: to tune with recorded evidence, and this is one of them).
MAX_INLINE_ROWS: Final[int] = 5_000

#: Most bytes ``rows``, re-serialized, may occupy. Row count alone does not
#: bound this — a handful of rows each carrying a very large value would sail
#: under :data:`MAX_INLINE_ROWS` — so both bounds are enforced, and neither
#: substitutes for the other. See ``create_import`` for where and why each is
#: checked.
MAX_INLINE_ROWS_BYTES: Final[int] = 2 * 1024 * 1024


class ImportRequest(BaseModel):
    """An import submission.

    Deliberately carries no tenant, actor, or timestamp. All three are derived
    server-side; accepting them from the body is the caller-supplied-identity
    pattern archived as MM-A01.

    Exactly one of ``source_reference`` and ``rows`` must be present —
    ``create_import`` rejects both and neither with an ``ApiError``. They name
    the import's content two different ways and are not equally capable:
    ``source_reference`` points at content in object storage this release still
    cannot read (a live import against it is refused, as before);
    ``rows`` carries the content already parsed, in the request body itself,
    which is what lets a live import actually succeed. See
    ``smartmatch_worker.handlers.handle_import_create`` for what each does.
    """

    source_reference: str | None = Field(
        default=None,
        min_length=1,
        max_length=500,
        description=(
            "Opaque reference to previously uploaded content in Cloud Storage. "
            "Mutually exclusive with rows; a live import against a "
            "source_reference is still refused — this release has no adapter "
            "that reads object storage."
        ),
    )
    rows: list[dict[str, Any]] | None = Field(
        default=None,
        description=(
            "Already-parsed rows to import, mutually exclusive with "
            "source_reference. An empty list is a legal, distinct submission — "
            "it is not the same as omitting rows — and is reported as an "
            "unusable (empty) dataset rather than accepted silently. Bounded "
            "at "
            f"{MAX_INLINE_ROWS} rows and {MAX_INLINE_ROWS_BYTES} serialized "
            "bytes; see create_import for where each bound is enforced."
        ),
    )
    dataset: str = Field(
        min_length=1,
        max_length=100,
        description="Logical dataset name, e.g. 'professionals'",
    )
    dry_run: bool = Field(
        default=True,
        description=(
            "When true the import validates and reports without creating review "
            "items. Defaults to true: the safe outcome should be the one you get "
            "by not thinking about it."
        ),
    )


class CommandAcceptedResponse(BaseModel):
    """Standard acknowledgement for every command resource."""

    job_id: uuid.UUID
    status: str = Field(default="accepted")
    #: Where to follow the work.
    events_url: str
    #: True when an identical request under the same key was already accepted.
    replayed: bool = False


@router.post(
    "/{unit_id}/imports",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CommandAcceptedResponse,
    summary="Submit an import command",
)
def create_import(
    principal: CurrentPrincipal,
    session: DbSession,
    body: ImportRequest,
    unit_id: Annotated[uuid.UUID, Path()],
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            description="Required. Makes retries safe.",
        ),
    ] = None,
) -> CommandAcceptedResponse:
    """Accept an import command.

    Returns ``202``, not ``200``: nothing has been imported when this returns.
    The command is recorded and will be dispatched; the job is where the outcome
    lives. Saying ``200`` here would be reporting success for work that has not
    started (v1.1 §3.6 N2).

    Authorization runs against the *owning unit*, after loading it — which is
    why it happens here rather than in a dependency. A dependency cannot
    authorize a resource it has not fetched.

    Quota is charged before any of that (ADR-0015), so a caller producing 404s
    against unit ids they invented, or 403s against a unit they may not import
    into, is spending exactly what a caller submitting real imports spends. It
    used to be charged inside ``submit_command``, which is past all three
    refusals — those requests were free, and they are the cheapest of all the
    refusals to produce in bulk.
    """
    charge = charge_quota(session, principal, IMPORT_RATE_LIMIT)

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
        required_roles=_IMPORT_ROLES,
    )

    has_source = body.source_reference is not None
    has_rows = body.rows is not None

    if has_source == has_rows:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="import_source_ambiguous",
            message=(
                "source_reference and rows are mutually exclusive ways of naming "
                "an import's content; this request named both."
                if has_source
                else (
                    "One of source_reference or rows must be supplied to name "
                    "an import's content; this request named neither."
                )
            ),
        )

    if has_source:
        assert body.source_reference is not None  # narrowed by has_source above
        if not body.source_reference.strip():
            raise ApiError(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="invalid_source_reference",
                message="source_reference must not be blank.",
            )
    else:
        assert body.rows is not None  # narrowed by has_rows above
        _validate_inline_rows(body.rows)

    # This dictionary is the command's durable contract, not a scratch value for
    # the idempotency hash: `submit_command` writes it to `job.payload` in the
    # same INSERT as the job row, and `smartmatch_worker.handlers` reads these
    # keys back and refuses the job if any is missing or unusable. Renaming a
    # key here changes what the worker is given, so the two ends move together.
    # `unit_id` comes from the authorized path parameter rather than the body —
    # the caller may not name the unit their import lands in (MM-A01).
    #
    # Only the field that was actually supplied is written — `source_reference`
    # for that shape, `rows` for the other — rather than writing both keys with
    # the unset one set to `None`. `smartmatch_worker.handlers` reads either key
    # with `.get()`, which returns `None` for an absent key exactly as it would
    # for a key present with a `None` value, so this changes nothing about what
    # the worker can tell; it does keep the persisted payload as lean as the
    # request that produced it, rather than padding every row with a key that
    # was never part of it.
    content_field = (
        {"source_reference": body.source_reference} if has_source else {"rows": body.rows}
    )
    accepted = submit_command(
        session,
        principal,
        command_type="import.create",
        # `unit.id`, not `unit_id` from the path and not anything from the body.
        # All three are the same value here — `load_unit_or_404` looked the row
        # up by that id, scoped to the caller's tenant — and taking it off the
        # loaded row is what keeps them the same value: this is the unit
        # `assert_allowed` was just given, so the job is filed under the subtree
        # the request was actually permitted for. Persisting a caller-named unit
        # would let a submitter choose who may later read, re-drive or abandon
        # their own job (A5, migration 0006).
        owning_unit_id=unit.id,
        payload={
            "unit_id": str(unit_id),
            "dataset": body.dataset,
            "dry_run": body.dry_run,
            **content_field,
        },
        idempotency_key=idempotency_key,
        charge=charge,
    )

    return CommandAcceptedResponse(
        job_id=accepted.job_id,
        events_url=f"/v1/jobs/{accepted.job_id}/events",
        replayed=accepted.is_replay,
    )


def _validate_inline_rows(rows: list[dict[str, Any]]) -> None:
    """Enforce :data:`MAX_INLINE_ROWS` and :data:`MAX_INLINE_ROWS_BYTES`.

    Row count is checked first because it is free: Pydantic has already built
    the list to construct ``body``, so ``len()`` costs nothing more, and a
    request already over the row-count bound is rejected before this function
    does anything that scales with row *content* rather than row *count*.
    Measuring serialized bytes is a real ``O(rows)`` pass over content this
    route does not otherwise need to touch, so it only runs once the count is
    already within bounds — at most :data:`MAX_INLINE_ROWS` rows to serialize,
    never more.

    What this does **not** bound: FastAPI/Pydantic has already parsed the
    entire request body into ``rows`` by the time this function runs, so a
    request whose *raw bytes* are enormous has already paid that parsing cost
    before either check below ever sees it. Refusing an oversized ``rows`` here
    still keeps it out of ``job.payload``, out of durable storage, and out of
    queued work — which is what this route controls — but a hard cap on
    request-body size ahead of parsing is an ASGI-level concern that belongs in
    the service's own app wiring (``smartmatch_api.main``), not in this router.

    Raises:
        ApiError: 400, ``import_rows_too_many`` or ``import_rows_too_large``.
    """
    if len(rows) > MAX_INLINE_ROWS:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="import_rows_too_many",
            message=f"rows must contain at most {MAX_INLINE_ROWS} entries; got {len(rows)}.",
        )

    serialized_size = len(json.dumps(rows, separators=(",", ":")).encode("utf-8"))
    if serialized_size > MAX_INLINE_ROWS_BYTES:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="import_rows_too_large",
            message=(
                f"rows must serialize to at most {MAX_INLINE_ROWS_BYTES} bytes; "
                f"got {serialized_size}."
            ),
        )
