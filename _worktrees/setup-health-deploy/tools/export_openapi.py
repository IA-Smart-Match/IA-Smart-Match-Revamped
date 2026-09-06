#!/usr/bin/env python3
"""Export the OpenAPI document, or verify the committed copy is current.

Architecture v1.1 §1.11 makes OpenAPI the source of truth for the API contract,
with the TypeScript client generated from it and never hand-written. That only
holds if the committed document cannot drift from the application, so
``--check`` runs in CI and fails the build when it has.

Usage::

    python tools/export_openapi.py contracts/openapi/smartmatch.json
    python tools/export_openapi.py contracts/openapi/smartmatch.json --check
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def build_document() -> dict[str, object]:
    """Generate the OpenAPI document from the live application."""
    from smartmatch_api.main import app

    return app.openapi()


def serialize(document: dict[str, object]) -> str:
    """Render deterministically.

    Sorted keys and a fixed indent, so the committed file changes only when the
    contract does — not because a dict happened to iterate differently.
    """
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="path to the OpenAPI document")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed document matches, without writing",
    )
    args = parser.parse_args()

    rendered = serialize(build_document())

    if args.check:
        if not args.output.exists():
            print(f"{args.output} does not exist; run `make openapi`.", file=sys.stderr)
            return 1
        if args.output.read_text(encoding="utf-8") != rendered:
            print(
                f"{args.output} is stale. The API surface changed without the "
                "contract being regenerated. Run `make openapi` and commit the "
                "result.",
                file=sys.stderr,
            )
            return 1
        print(f"{args.output} is current.")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
