"""`smartmatch_providers.fixture_ingest` is reachable from one place. Proof.

`tests/unit/test_fixture_ingest.py` covers what the module *does*. What that
file cannot see is the property this one exists for: exactly which code can
reach it. Same shape as `tests/unit/test_paid_extraction_wiring.py`, and for
the same reason — a capability that must stay bounded is guarded by asserting
where it is absent, not by trusting that nobody wired it.

Why absence was the whole deliverable, and what changed. The signed threat
model (`docs/security/crawler-threat-model-draft.md` revision 4) is explicit
that it "does **not** authorize HTTP crawl code, worker routes, UI, or live
provider calls", and its non-goals name `POST /api/crawler/start` and the
legacy `CrawlerFeed` specifically. When the reader first landed, nothing
imported it at all, and this file said so of both services.

Card P-EVENTS-API wired the half that is authorized. G3 §9 puts every network
action worker-side and leaves API handlers "commands and review decisions
only", so the reader is now imported by exactly one worker module —
`smartmatch_worker.event_ingest`, which carries committed fixtures into the
`event` tables migration `0017` created. Nothing else may import it, and in
particular **the API still may not**: `TestTheApiCannotReachIt` keeps that half
of the original assertion exactly as strict as it was, and
`TestOnlyTheEventIngestSeamImportsIt` pins the worker's single importer by name
rather than loosening the check to "the worker may".

Everything the threat model actually gates is unchanged and still asserted
below: no crawl/discovery/scrape command type on the shipped registry, no such
path in the committed contract or on the live app, and no migration citing this
module. The reader itself still reaches no persistence layer — the write
happens in `smartmatch_persistence.events`, on the far side of the seam — which
is what `TestNoPersistence` continues to hold it to.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

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

#: The one module card P-EVENTS-API authorizes to import the reader: the seam
#: that carries a committed fixture into `smartmatch_persistence.events`. Named
#: as a literal so widening the permission is an edit to this line rather than
#: a side effect of adding an import somewhere in the worker tree.
EVENT_INGEST_MODULE = "smartmatch_worker.event_ingest"
EVENT_INGEST_PATH = WORKER_ROOT / "event_ingest.py"

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


class TestTheApiCannotReachIt:
    """The API half of the original assertion, unchanged and still absolute.

    G3 §9: "All network activity is worker-side; API handlers record commands
    and review decisions only." The reader is the thing that opens documents,
    so no file the API process can load may import it — not a router, not a
    helper a router imports, nothing.
    """

    def test_no_api_module_imports_it(self):
        """Every file in the tree, not only `main.py`.

        Checking only the composition root would miss a helper importing it and
        `main` importing the helper, which is the same wiring by a longer path.
        """
        offenders = [
            path.relative_to(REPO_ROOT).as_posix()
            for path in _python_files(API_ROOT)
            if any(name.startswith(QUALIFIED_NAME) for name in _imported_modules(path))
        ]

        assert offenders == [], f"{QUALIFIED_NAME} is imported by the API: {offenders}"


class TestOnlyTheEventIngestSeamImportsIt:
    """The worker half: one importer, named, and nothing else."""

    def test_exactly_one_worker_module_imports_it(self):
        """A list of one, compared by equality rather than by membership.

        `assert EVENT_INGEST_PATH in offenders` would pass while three other
        worker modules had quietly acquired the import too. The point of this
        file is knowing the exact reachable set, so the assertion is an
        equality against it.
        """
        offenders = [
            path.relative_to(REPO_ROOT).as_posix()
            for path in _python_files(WORKER_ROOT)
            if any(name.startswith(QUALIFIED_NAME) for name in _imported_modules(path))
        ]

        assert offenders == [EVENT_INGEST_PATH.relative_to(REPO_ROOT).as_posix()], (
            f"{QUALIFIED_NAME} must be imported by {EVENT_INGEST_MODULE} and nothing "
            f"else in the worker; found {offenders}"
        )

    def test_the_seam_reaches_the_writer_rather_than_writing_anything_itself(self):
        """The seam imports the repository; it does not open its own connection.

        `smartmatch_persistence.events` is the only module permitted to write
        `event`, `event_tag` and `discovery_review_item`. A seam that reached
        for an engine, or built its own INSERT, would be a second writer —
        which is how a table acquires two definitions of what a valid row is.
        """
        imported = _imported_modules(EVENT_INGEST_PATH)

        assert "smartmatch_persistence.events" in imported
        assert not any(name.startswith("alembic") for name in imported)
        assert not any(name == "sqlalchemy" for name in imported), (
            "the seam imports sqlalchemy directly; the repository owns the "
            f"statements. Reached: {sorted(imported)}"
        )

    def test_the_seam_imports_no_http_client(self):
        """The reader has no transport, and neither does its caller.

        Structural rather than behavioural, for the reason
        `tests/unit/test_fixture_ingest.py` gives about the same check on the
        reader: asserting "this call made no request" only covers the paths a
        test happens to exercise.
        """
        transports = {"httpx", "requests", "urllib", "urllib3", "http", "socket", "aiohttp"}
        reached = {name.split(".")[0] for name in _imported_modules(EVENT_INGEST_PATH)}

        assert not (reached & transports), f"the seam can reach: {sorted(reached & transports)}"


class TestNoCompositionRootImportsIt:
    """What neither service may do, regardless of which one is asking."""

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
