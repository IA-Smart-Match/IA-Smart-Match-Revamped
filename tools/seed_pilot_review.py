#!/usr/bin/env python3
"""Queue one synthetic import so the seeded pilot unit has a review queue.

`tools/seed_pilot.py` creates the identity a coordinator authenticates as. It
does not create anything for that coordinator to *do*, so a freshly started
appliance shows an empty review queue and a stakeholder's first click lands on
"nothing here". This tool closes that gap, and it closes it the honest way:
it does not write `review_item` rows itself. It submits an ordinary import
through the running API, with the ordinary bearer token, and then waits for
the ordinary worker/scheduler path to turn that import into pending review
items. What the demo shows is therefore what the product does — if the
dispatch path is broken, this exits non-zero and says so rather than
back-filling rows that no pipeline produced.

Like `seed_pilot.py` this is an operator tool, not an API endpoint and not
part of either shipped image. It refuses to run unless `SMARTMATCH_EDITION=dev`
and `SMARTMATCH_USE_FIXTURE_PROVIDERS=true`, and the rows it submits are
synthetic names against `docs/pilot-data/columns.yaml`'s ratified
`professionals` columns (`name` and `metro_region` required).

Idempotent by observation, not by flag: if the target unit already has pending
review items, it changes nothing and exits 0. Re-running `docker compose up`
therefore does not pile up a deeper and deeper queue.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from seed_pilot import SeedConfigurationError, require_development_fixture_settings
from smartmatch_api.config import Settings
from smartmatch_persistence import schema
from smartmatch_persistence.engine import create_db_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

# Synthetic, obviously fictional, and stable: the docs name these rows, and a
# reviewer who sees them should be in no doubt that no real person is involved.
# Both columns are the ones columns.yaml ratifies as required for
# `professionals`, so the rows validate cleanly instead of producing findings
# that would make the queue read as broken rather than as seeded.
DEMO_ROWS: tuple[dict[str, str], ...] = (
    {"name": "Grace Hopper", "metro_region": "Portland"},
    {"name": "Katherine Johnson", "metro_region": "Portland"},
)

# A fixed key, not a timestamp. The API replays the first response for a
# repeated key, which is a second layer of protection against a re-run
# doubling the queue — the pending-item check below is the first.
DEMO_IDEMPOTENCY_KEY = "seed-pilot-review-demo"


class SeedReviewError(RuntimeError):
    """The demo review queue could not be established through the real path."""


def _resolve_unit_id(engine: Engine, *, tenant_slug: str, unit_path: str) -> uuid.UUID:
    with engine.connect() as connection:
        row = connection.execute(
            sa.select(schema.org_unit.c.id)
            .select_from(
                schema.org_unit.join(
                    schema.tenant, schema.tenant.c.id == schema.org_unit.c.tenant_id
                )
            )
            .where(schema.tenant.c.slug == tenant_slug, schema.org_unit.c.path == unit_path)
        ).one_or_none()
    if row is None:
        raise SeedReviewError(
            f"no org unit at path {unit_path!r} in tenant {tenant_slug!r}; "
            "run tools/seed_pilot.py (the compose `seed` service) first"
        )
    return uuid.UUID(str(row.id))


def _pending_review_item_count(engine: Engine, *, unit_id: uuid.UUID) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(
                sa.select(sa.func.count())
                .select_from(
                    schema.review_item.join(
                        schema.import_batch,
                        sa.and_(
                            schema.import_batch.c.tenant_id == schema.review_item.c.tenant_id,
                            schema.import_batch.c.id == schema.review_item.c.import_batch_id,
                        ),
                    )
                )
                .where(
                    schema.import_batch.c.owning_unit_id == unit_id,
                    schema.review_item.c.status == "pending",
                )
            ).scalar_one()
        )


def _post_import(*, api_base: str, bearer_token: str, unit_id: uuid.UUID, timeout: float) -> int:
    """Submit the demo rows through the ordinary import route. Returns the status."""
    payload = json.dumps(
        {"dataset": "professionals", "dry_run": False, "rows": list(DEMO_ROWS)}
    ).encode("utf-8")
    request = urllib.request.Request(
        url=f"{api_base}/v1/units/{unit_id}/imports",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
            "Idempotency-Key": DEMO_IDEMPOTENCY_KEY,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:400]
        raise SeedReviewError(
            f"POST /v1/units/{unit_id}/imports answered {exc.code}: {body}"
        ) from exc
    except urllib.error.URLError as exc:
        raise SeedReviewError(f"could not reach the API at {api_base}: {exc.reason}") from exc


def _wait_for_api(*, api_base: str, attempts: int, delay: float, timeout: float) -> None:
    last = "no attempt made"
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(f"{api_base}/api/health", timeout=timeout) as response:
                if response.status == 200:
                    print(f"seed-pilot-review: api healthy on attempt {attempt}")
                    return
                last = f"HTTP {response.status}"
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            last = str(exc)
        print(f"seed-pilot-review: waiting for api ({last})")
        time.sleep(delay)
    raise SeedReviewError(f"api never became healthy at {api_base}: {last}")


def _wait_for_pending_items(
    engine: Engine, *, unit_id: uuid.UUID, wanted: int, attempts: int, delay: float
) -> int:
    """Poll the database until the dispatch path has produced `wanted` items.

    Deliberately a poll of the real outcome, not a sleep: the queued import is
    processed by the worker only after the `scheduler` sidecar dispatches it,
    and an appliance whose sidecar is refused must fail here loudly rather
    than exit 0 having seeded nothing.
    """
    observed = 0
    for attempt in range(1, attempts + 1):
        observed = _pending_review_item_count(engine, unit_id=unit_id)
        print(f"seed-pilot-review: attempt {attempt}: pending review items = {observed}")
        if observed >= wanted:
            return observed
        time.sleep(delay)
    raise SeedReviewError(
        f"the queued import never reached review: expected at least {wanted} pending "
        f"review items, still {observed}. This is a dispatch failure, not a slow "
        "start — check `docker compose ps -a scheduler` and `docker compose logs scheduler`."
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", required=True, help="Base URL of the running API")
    parser.add_argument(
        "--bearer-token",
        required=True,
        help="Dev-only bearer token the API maps to the seeded coordinator subject",
    )
    parser.add_argument("--tenant-slug", default="pilot", help="Synthetic tenant slug")
    parser.add_argument("--unit-path", default="pilot", help="ltree path owning the import")
    parser.add_argument(
        "--ready-attempts", type=int, default=60, help="API readiness poll attempts (2s apart)"
    )
    parser.add_argument(
        "--dispatch-attempts",
        type=int,
        default=60,
        help="Pending-review-item poll attempts (2s apart)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        settings = require_development_fixture_settings(Settings())
    except SeedConfigurationError as exc:
        print(f"seed-pilot-review: configuration error: {exc}", file=sys.stderr)
        return 2

    api_base = args.api_base.rstrip("/")
    engine = create_db_engine(settings.database_url)
    try:
        unit_id = _resolve_unit_id(engine, tenant_slug=args.tenant_slug, unit_path=args.unit_path)
        already_pending = _pending_review_item_count(engine, unit_id=unit_id)
        if already_pending > 0:
            print(
                f"seed-pilot-review: unit {unit_id} already has {already_pending} pending "
                "review item(s); leaving the queue exactly as it is"
            )
            return 0

        _wait_for_api(api_base=api_base, attempts=args.ready_attempts, delay=2.0, timeout=5.0)
        status = _post_import(
            api_base=api_base,
            bearer_token=args.bearer_token,
            unit_id=unit_id,
            timeout=15.0,
        )
        print(f"seed-pilot-review: POST /v1/units/{unit_id}/imports -> {status}")
        if status != 202:
            raise SeedReviewError(f"import was not accepted (expected 202, got {status})")

        observed = _wait_for_pending_items(
            engine,
            unit_id=unit_id,
            wanted=len(DEMO_ROWS),
            attempts=args.dispatch_attempts,
            delay=2.0,
        )
    except SeedReviewError as exc:
        print(f"seed-pilot-review: {exc}", file=sys.stderr)
        return 1
    except SQLAlchemyError as exc:
        print(
            "seed-pilot-review: database operation failed; the database must be migrated "
            f"and seeded first: {exc}",
            file=sys.stderr,
        )
        return 1
    finally:
        engine.dispose()

    print(
        f"seed-pilot-review: {observed} pending review item(s) on unit {unit_id}, "
        "created through the ordinary import -> dispatch -> review path"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
