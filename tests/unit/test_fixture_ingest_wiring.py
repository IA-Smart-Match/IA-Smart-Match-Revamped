"""`smartmatch_providers.fixture_ingest` is not wired to anything. Proof.

`tests/unit/test_fixture_ingest.py` covers what the module *does*. What that
file cannot see is the property this PR actually ships: that the module is
reachable only by a test. Same shape as
`tests/unit/test_paid_extraction_wiring.py`, and for the same reason — a
capability that must not be live is guarded by asserting its absence from the
composition roots, not by trusting that nobody wired it.

Why absence is the deliverable here. The signed threat model
(`docs/security/crawler-threat-model-draft.md` revision 4) is explicit that it
"does **not** authorize HTTP crawl code, worker routes, UI, or live provider
calls", and its non-goals name `POST /api/crawler/start` and the legacy
`CrawlerFeed` specifically. The S6 plan card puts the crawl adapter behind
S4/S5 and makes its HTTP surface conditional on a signed artifact that does not
call for one. So this scaffold ships readable, tested, and unreferenced: no
route, no command type, no migration, no OpenAPI change. The day someone wires
it, this file fails, which is the point.

Persistence is likewise out of scope — the `event` tables are a later card
(P-EVENTS-SCHEMA) — so the migration tree must not mention this module either.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

API_ROOT = REPO_ROOT / "services" / "api" / "smartmatch_api"
WORKER_ROOT = REPO_ROOT / "services" / "worker" / "smartmatch_worker"
PROVIDERS_INIT = (
    REPO_ROOT / "python" / "smartmatch_providers" / "smartmatch_providers" / "__init__.py"
)
OPENAPI_PATH = REPO_ROOT / "contracts" / "openapi" / "smartmatch.json"
FIXTURE_INGEST_PATH = (
    REPO_ROOT / "python" / "smartmatch_providers" / "smartmatch_providers" / "fixture_ingest.py"
)
MIGRATIONS_ROOT = REPO_ROOT / "db" / "migrations" / "versions"

MODULE_NAME = "fixture_ingest"
QUALIFIED_NAME = f"smartmatch_providers.{MODULE_NAME}"

#: Path/command-type substrings that would mean a discovery surface exists.
#: The first two are named as non-goals by the threat model itself.
_CRAWL_TOKENS = ("crawler", "crawl", "discovery", "scrape")

#: Top-level packages a module would have to reach to own persistent state, and
#: therefore to need a migration. The ORM and the migration tool are listed
#: alongside this project's persistence package because a module could reach a
#: table through either without going through it.
_PERSISTENCE_ROOTS = ("smartmatch_persistence", "sqlalchemy", "alembic")


def _imported_modules(path: Path) -> set[str]:
    """Every module name `path` imports, dotted and whole.

    AST rather than a substring grep: a grep for "fixture_ingest" also matches
    this file's own prose, a comment, and a string literal, so it cannot tell
    "imported" from "mentioned". An import statement is the thing that makes a
    module reachable at runtime, and that is what is asserted against.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


class TestNoCompositionRootImportsIt:
    """Neither service can reach the module, at any depth."""

    @pytest.mark.parametrize("root", [API_ROOT, WORKER_ROOT], ids=["api", "worker"])
    def test_no_service_module_imports_it(self, root: Path):
        """Every file in the tree, not only `main.py`.

        Checking only the composition root would miss a helper importing it and
        `main` importing the helper, which is the same wiring by a longer path.
        """
        offenders = [
            path.relative_to(REPO_ROOT).as_posix()
            for path in _python_files(root)
            if any(name.startswith(QUALIFIED_NAME) for name in _imported_modules(path))
        ]

        assert offenders == [], f"{QUALIFIED_NAME} is imported by: {offenders}"

    def test_the_providers_package_does_not_re_export_it(self):
        """A re-export would import it into both services for free.

        `services/api/smartmatch_api/main.py` does `from smartmatch_providers
        import build_token_verifier`, which executes `__init__.py`. Naming this
        module there would quietly undo everything above without a single line
        changing in either service.
        """
        assert not any(
            name.startswith(QUALIFIED_NAME) for name in _imported_modules(PROVIDERS_INIT)
        )

    def test_importing_the_package_does_not_import_the_module(self):
        """The runtime check behind the source check.

        Belt and braces: the assertions above read source, this one boots the
        package in a clean interpreter and looks at what actually landed in
        `sys.modules`.
        """
        probe = f"import sys; import smartmatch_providers; print('{QUALIFIED_NAME}' in sys.modules)"
        # Fixed argv, no shell, no external input.
        result = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True,
            text=True,
            check=True,
            cwd=REPO_ROOT,
        )

        assert result.stdout.strip() == "False"


class TestNoRuntimeSurface:
    """No worker command, no HTTP route, no contract change."""

    def test_the_worker_registry_routes_no_ingest_command(self):
        """`default_registry` is exactly what it was before this scaffold landed."""
        from smartmatch_worker.handlers import default_registry

        routed = set(default_registry().command_types)

        assert not any(
            token in command_type for command_type in routed for token in _CRAWL_TOKENS
        ), f"routed: {sorted(routed)}"
        assert not any(MODULE_NAME in command_type for command_type in routed)
        # The shipped registry is otherwise untouched by this PR.
        assert {"test.noop", "import.create"} <= routed

    def test_the_committed_openapi_contract_exposes_no_crawl_surface(self):
        """Including the legacy route the threat model names as a non-goal.

        This PR must not have regenerated or edited the contract; the absence
        of a crawl path is what proves no route was added along with it.
        """
        contract = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
        paths = set(contract.get("paths", {}))

        assert "/api/crawler/start" not in paths
        offenders = sorted(
            path for path in paths if any(token in path.lower() for token in _CRAWL_TOKENS)
        )
        assert offenders == []

    def test_the_live_api_app_exposes_no_crawl_route(self):
        """The app object, not only the committed file.

        A route added to `main.py` without regenerating the contract would slip
        past the assertion above; this one reads the router table itself.
        """
        from smartmatch_api.main import app

        routes = {str(getattr(route, "path", "")) for route in app.routes}

        assert not any(token in path.lower() for path in routes for token in _CRAWL_TOKENS), (
            f"routes: {sorted(routes)}"
        )


class TestNoPersistence:
    """Event persistence is P-EVENTS-SCHEMA, not this PR."""

    def test_no_migration_references_the_module(self):
        offenders = [
            path.name
            for path in sorted(MIGRATIONS_ROOT.glob("*.py"))
            if MODULE_NAME in path.read_text(encoding="utf-8")
        ]

        assert offenders == []

    def test_this_scaffold_adds_no_revision(self):
        """The scaffold contributed no migration, stated without naming a head.

        This assertion used to pin the newest migration filename as a literal.
        That was a fair reading of "this PR added no revision" on the day it was
        written, but the head is not this file's property: the next revision by
        anyone — ``0017_event_persistence.py`` was the one that actually did it —
        fails a test about the crawl scaffold, for a reason that has nothing to
        do with the crawl scaffold. A guard that cries wolf on every unrelated
        migration is a guard people learn to edit rather than read.

        So the property is asserted directly instead. A module contributes a
        revision when it has schema to migrate, and this one cannot: it reaches
        no persistence layer, no ORM, and no migration machinery. Together with
        :meth:`test_no_migration_references_the_module` — nothing in the tree
        cites it — that is the whole of "adds no revision", and neither half
        moves when somebody else lands one.

        ``import-linter`` enforces the layering in general; this asserts it for
        the one module whose isolation the threat model made a deliverable.
        """
        revisions = sorted(path.name for path in MIGRATIONS_ROOT.glob("[0-9]*.py"))
        assert revisions, "no migrations found; the path is probably wrong"

        reached = _imported_modules(FIXTURE_INGEST_PATH)
        offenders = sorted(
            name
            for name in reached
            if any(name == root or name.startswith(f"{root}.") for root in _PERSISTENCE_ROOTS)
        )

        assert offenders == [], f"{QUALIFIED_NAME} reaches persistence via: {offenders}"
