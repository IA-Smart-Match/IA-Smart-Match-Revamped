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
import re
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from fastapi import FastAPI

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


#: How many levels :func:`_nested_route_paths` will descend before giving up.
#: Router nesting in a real application is a handful of levels deep; this is
#: far enough that no honest composition reaches it, and small enough that a
#: self-mount is cut short well before the interpreter's own recursion limit.
_MAX_DESCENT_DEPTH = 50


def _nested_route_paths(routes: Iterable[object]) -> set[str]:
    """Best-effort descent into nested routers, for the paths OpenAPI omits.

    Returns paths **as served** — every enclosing prefix composed in. That is
    the whole difficulty, and getting it wrong is worse than not walking at
    all. ``app.include_router(router, prefix="/api/crawler")`` puts the
    capability's name in the prefix and leaves the leaf reading ``/start``;
    combine that with ``include_in_schema=False``, which keeps the route out of
    the OpenAPI document, and a descent that yielded the bare leaf would match
    no token and report a live crawl route as clean. So each level's
    ``include_context.prefix`` is accumulated on the way down, and a leaf is
    recorded as ``prefix + path``.

    The de-duplication key is ``(id(route), prefix)``, not ``id(route)``. The
    same router object included twice under two prefixes is two surfaces, and
    keying on identity alone would report the first and silently drop the
    second — which is precisely where a crawl route would be hidden from this
    walk. Keying on identity-at-a-prefix keeps the cycle guard while letting a
    genuine second mounting through.

    That key is why there is also a depth bound. ``app.mount("/sub", app)``
    revisits the same object at a prefix one lap longer every time, so the key
    is never a repeat and the identity guard never fires; unbounded, it ends in
    ``RecursionError``. :data:`_MAX_DESCENT_DEPTH` stops the descent instead,
    keeping whatever was found above it. Quiet truncation is the right failure
    here for the same reason the whole function is additive: this is a
    supplement to the OpenAPI document, and a supplement that raises would take
    the guard down with it over a pathological app shape that is not what the
    guard is about.

    **What this covers**: routes reached through ``include_router``, at any
    depth, under any composition of prefixes; and sub-applications reached
    through ``app.mount()``, whose mount path is itself treated as a prefix.
    Both branches are pinned by a decoy in :class:`TestTheGuardCanFire` — the
    live app happens to use neither a prefix nor a mount, so a test is the only
    thing holding either of them up.
    **What it does not cover**: anything whose path is not a static string —
    a route added by a custom ``APIRoute`` subclass that computes its path at
    request time, or an ASGI app mounted as a bare callable with no ``routes``
    attribute, is opaque to any static walk, including this one.

    Purely additive, and deliberately so. Reaching inside an ``_IncludedRouter``
    means touching ``original_router`` and ``include_context``, which are
    FastAPI's private business and may be renamed without notice. So every step
    is a ``getattr`` with a default: on a FastAPI that spells them differently
    this returns fewer paths — in the limit, none — and :func:`_app_paths` still
    has the whole OpenAPI document underneath it. A version bump can therefore
    cost this walk reach, but it cannot make it wrong, and it cannot make the
    guard vacuous the way reading ``app.routes`` did.
    """
    found: set[str] = set()
    seen: set[tuple[int, str]] = set()

    def visit(route: object, prefix: str, depth: int) -> None:
        if depth >= _MAX_DESCENT_DEPTH:  # a self-mount; keep what we have
            return
        key = (id(route), prefix)
        if key in seen:  # a cycle; a second mounting has a different prefix
            return
        seen.add(key)

        inner = getattr(route, "original_router", None) or getattr(route, "router", None)
        if inner is not None:
            context = getattr(route, "include_context", None)
            nested_prefix = prefix + (getattr(context, "prefix", "") or "")
            for nested in getattr(inner, "routes", ()) or ():
                visit(nested, nested_prefix, depth + 1)
            return

        path = getattr(route, "path", None)
        if isinstance(path, str) and path:
            found.add(prefix + path)
            # A `Mount` carries both a path and the sub-app's routes, and those
            # routes are relative to it — so its own path is the prefix for them.
            prefix += path
        for nested in getattr(route, "routes", ()) or ():
            visit(nested, prefix, depth + 1)

    for route in routes:
        visit(route, "", 0)
    return found


def _app_paths(app: FastAPI) -> set[str]:
    """Every path an app actually serves. Not ``app.routes``.

    ``app.routes`` is the obvious place to look and it is the wrong one. On
    FastAPI 0.141 ``include_router`` leaves an ``_IncludedRouter`` wrapper in
    ``app.routes`` — 35 of the live API's 40 entries — and a wrapper carries no
    ``.path``. So the set comprehension this function replaced,
    ``{str(getattr(route, "path", "")) for route in app.routes}``, collapsed
    every included route to ``""`` and returned six items: ``""``, the one
    route declared with ``@app.get``, and the four documentation routes. The
    app serves 66. A crawl route mounted through any router — which is how
    every route in this app but one is mounted — never appeared in that set,
    and the guard that reads it would have passed with
    ``POST /api/crawler/start`` live. ``tests/contract/test_api_health.py``
    reaches for the OpenAPI document for this same reason, in these same words.

    The document is what a client sees, so it is also the more meaningful
    thing to assert on. Its one gap is ``include_in_schema=False``: such a
    route is served and undocumented, which is the most useful shape a hidden
    crawl surface could take. :func:`_nested_route_paths` closes that gap for
    routes reached through ``include_router`` and ``app.mount()``, composing
    every enclosing prefix, and leaves it open only for routes whose path is
    not a static string — see that function for the exact boundary.

    On this app the gap is exactly four routes — ``/docs``,
    ``/docs/oauth2-redirect``, ``/openapi.json`` and ``/redoc`` — none of them
    crawl-shaped, and the descent reaches all four. The union is 70 paths
    against the document's 66, and every documented path also appears in the
    descent, which is the cross-check that the prefix composition is right.
    """
    return set(app.openapi()["paths"]) | _nested_route_paths(app.routes)


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
        past the assertion above; this one reads what the app itself serves.
        See :func:`_app_paths` for why that is not ``app.routes``.
        """
        from smartmatch_api.main import app

        documented = set(app.openapi()["paths"])
        paths = _app_paths(app)

        # Two floors, not one. The union's floor alone could be satisfied
        # entirely by the descent while the document half returned nothing, and
        # vice versa — so each half is held to a size of its own. Both are
        # loose on purpose: they catch a walk that went blind, not route churn.
        assert len(documented) > 10, (
            f"the OpenAPI document reported only {len(documented)} path(s): "
            f"{sorted(documented)}. The app serves dozens; a set this small "
            "means the document half of the walk went blind."
        )
        assert len(paths) > 10, (
            f"the walk found only {len(paths)} path(s): {sorted(paths)}. A set "
            "this small does not mean the app is small — it serves dozens — it "
            "means the walk went blind, and a blind walk reports no crawl route "
            "no matter what is mounted."
        )
        assert not any(token in path.lower() for path in paths for token in _CRAWL_TOKENS), (
            f"routes: {sorted(paths)}"
        )


class TestTheGuardCanFire:
    """The guard above, proved able to fail. The opposite shape of the rest.

    Every other class here asserts an absence against the real tree. These
    assert a *presence* against throwaway apps built in-test, because a guard
    that cannot fail is worth nothing and absence-checking cannot show the
    difference. The defect this file carried was not a wrong answer but a
    vacuous one: the old walk read ``app.routes``, returned six strings for a
    66-path app, and passed every time over a set that could not have contained
    what it was looking for. Vacuity is invisible from a green run, so the
    repair owes a demonstration for each shape of mounting a crawl route could
    hide behind.

    Every decoy below is a path string and a stub that raises if called. None
    imports a crawler module, reaches a provider, or is reachable from outside
    its own function body. G3 keeps the crawl surface absent; these exist to
    keep proving that, and a decoy with no implementation behind it is the only
    way to show a guard fires without building the thing it guards against.
    """

    def test_it_sees_a_crawl_route_mounted_through_include_router(self):
        """The plain case: a router included with no prefix."""
        from fastapi import APIRouter, FastAPI

        router = APIRouter()

        @router.post("/api/crawler/start")
        def _decoy() -> dict[str, str]:  # pragma: no cover - mounted, never called
            raise AssertionError("decoy route: this test asserts on the path table only")

        probe = FastAPI()
        probe.include_router(router)

        paths = _app_paths(probe)

        assert "/api/crawler/start" in paths, (
            "the walk cannot see a route added by include_router, so the guard "
            f"is vacuous: {sorted(paths)}"
        )
        assert sorted(
            path for path in paths if any(token in path.lower() for token in _CRAWL_TOKENS)
        ) == ["/api/crawler/start"]

    def test_it_sees_a_crawl_token_that_lives_only_in_the_include_prefix(self):
        """The leaf is innocent; the prefix is the whole offence.

        ``include_in_schema=False`` keeps this out of the OpenAPI document, so
        the descent is the only thing that can see it — and a descent that
        reported the leaf ``/start`` rather than ``/api/crawler/start`` would
        match no token and report the app clean with a live crawl route on it.
        That is not hypothetical: it is what this helper did before review
        round 1. The prefix is where the capability is named, which makes it
        the half that must not be dropped.
        """
        from fastapi import APIRouter, FastAPI

        router = APIRouter()

        @router.post("/start", include_in_schema=False)
        def _decoy() -> dict[str, str]:  # pragma: no cover - mounted, never called
            raise AssertionError("decoy route: this test asserts on the path table only")

        probe = FastAPI()
        probe.include_router(router, prefix="/api/crawler")

        assert set(probe.openapi()["paths"]) == set(), (
            "precondition: include_in_schema=False must keep this out of the "
            "document, or the test is not exercising the descent"
        )

        paths = _app_paths(probe)

        assert "/api/crawler/start" in paths, (
            "the descent dropped the include_router prefix, so a crawl route "
            f"named only by its prefix is invisible: {sorted(paths)}"
        )
        assert any(token in path.lower() for path in paths for token in _CRAWL_TOKENS)

    def test_it_composes_prefixes_through_two_levels_of_nesting(self):
        """Routers include routers. Each level contributes its own prefix."""
        from fastapi import APIRouter, FastAPI

        leaf = APIRouter()

        @leaf.get("/start", include_in_schema=False)
        def _decoy() -> dict[str, str]:  # pragma: no cover - mounted, never called
            raise AssertionError("decoy route: this test asserts on the path table only")

        middle = APIRouter()
        middle.include_router(leaf, prefix="/crawler")

        probe = FastAPI()
        probe.include_router(middle, prefix="/api")

        paths = _app_paths(probe)

        assert "/api/crawler/start" in paths, (
            f"nested include prefixes were not composed: {sorted(paths)}"
        )

    def test_it_reports_one_router_included_under_two_prefixes_twice(self):
        """The cycle guard must not swallow a legitimate second mounting.

        The same router object under two prefixes is two surfaces, and the
        second is exactly where a crawl route would hide from a walk that
        de-duplicates on object identity alone. So identity is not the key —
        identity *at an accumulated prefix* is.
        """
        from fastapi import APIRouter, FastAPI

        router = APIRouter()

        @router.get("/start", include_in_schema=False)
        def _decoy() -> dict[str, str]:  # pragma: no cover - mounted, never called
            raise AssertionError("decoy route: this test asserts on the path table only")

        probe = FastAPI()
        probe.include_router(router, prefix="/api/harmless")
        probe.include_router(router, prefix="/api/crawler")

        paths = _app_paths(probe)

        assert {"/api/harmless/start", "/api/crawler/start"} <= paths, (
            f"a router included twice yielded only one of its mountings: {sorted(paths)}"
        )

    def test_it_sees_a_crawl_token_that_lives_only_in_a_mount_path(self):
        """``app.mount()`` is the other way a sub-tree acquires a prefix.

        A mounted sub-application does not appear in the parent's OpenAPI
        document at all, so the descent is the only thing that can see inside
        it, and the sub-app's own route reads ``/start``.

        Worth being exact about what this buys, because it is less than the
        ``include_router`` case. A ``Mount``'s own path is recorded too, so a
        mount named ``/api/crawler`` trips the token check whether or not the
        prefix is composed. What composition buys here is the *reported path*:
        without it the walk claims the app serves ``/start``, which is not a
        path the app serves, and the failure message would send the next reader
        looking for a route that does not exist. A guard is also a report, and
        a report that names the wrong path is how a real finding gets dismissed
        as noise.
        """
        from fastapi import FastAPI

        sub = FastAPI()

        @sub.get("/start", include_in_schema=False)
        def _decoy() -> dict[str, str]:  # pragma: no cover - mounted, never called
            raise AssertionError("decoy route: this test asserts on the path table only")

        probe = FastAPI()
        probe.mount("/api/crawler", sub)

        assert set(probe.openapi()["paths"]) == set(), (
            "precondition: a mounted sub-app must not reach the parent's "
            "document, or the test is not exercising the descent"
        )

        paths = _app_paths(probe)

        assert "/api/crawler/start" in paths, f"the descent dropped the mount: {sorted(paths)}"
        assert any(token in path.lower() for path in paths for token in _CRAWL_TOKENS)

    def test_it_terminates_on_an_app_mounted_inside_itself(self):
        """A self-mount must truncate, not raise.

        ``app.mount("/sub", app)`` revisits the same object at a longer prefix
        every lap, so the ``(id, prefix)`` key is never a repeat and the cycle
        guard never fires. Unbounded, this walk ends in ``RecursionError`` —
        which would take down a guard about crawl routes over an app shape that
        has nothing to do with crawl routes. :data:`_MAX_DESCENT_DEPTH` stops it
        quietly instead, keeping the paths found on the way down.

        Nobody writes a self-mount on purpose. The point is the failure mode:
        this function is a supplement to the OpenAPI document, and a supplement
        must never be the reason the suite falls over.
        """
        from fastapi import FastAPI

        probe = FastAPI()
        probe.mount("/sub", probe)

        # Terminating at all is the assertion; reaching this line is it being
        # met, because the unbounded version raises RecursionError here.
        paths = _nested_route_paths(probe.routes)

        deepest = max(path.count("/sub") for path in paths)
        assert deepest <= _MAX_DESCENT_DEPTH, (
            f"the descent recursed {deepest} levels, past {_MAX_DESCENT_DEPTH}"
        )
        assert "/sub" in paths, f"truncation lost the paths found above it: {sorted(paths)}"


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


#: The legacy frontend, which is the other place a crawl surface could appear
#: without any backend module importing the reader at all.
FRONTEND_SRC = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src"

#: The `/api/crawler/*` client helpers that survive in `src/lib/api.ts`. They
#: are kept, not deleted -- the same disposition `cba-phase-deferred.md` gives
#: every gated capability -- and they call routes the API does not serve, which
#: `TestTheContractAndTheAppAgree` already proves. What must stay true is that
#: no component calls them, so the dead helper cannot quietly become a control.
CRAWL_API_HELPERS = (
    "startCrawl",
    "fetchCrawlerResults",
    "clearCrawlerResults",
    "fetchCrawlerStatus",
)


def _frontend_sources() -> list[Path]:
    return sorted(
        path
        for suffix in ("*.ts", "*.tsx")
        for path in FRONTEND_SRC.rglob(suffix)
        if "node_modules" not in path.parts
    )


def _tsx_code_only(source: str) -> str:
    """Strip `/* */` and `//` prose so a file may explain why it passes."""
    without_blocks = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", without_blocks, flags=re.MULTILINE)


class TestNoCbaFrontendSurfaceOffersIt:
    """The frontend half of "fixture ingest is a test/operator seam".

    Everything above asks where the *reader* can be reached from. That is the
    right question for the backend, where reachability is an import graph. It is
    the wrong question for the browser: a page needs no import of a Python
    module to offer a crawl button — it only needs a `fetch` and a label, and
    the promise is made to the user whether or not any route answers.

    So this asks the browser's version of the same question. Customer §20 puts
    external discovery out of scope for this phase and
    `docs/plans/open-questions/cba-phase-deferred.md` requires crawl controls
    hidden while fixture ingest stays usable for tests; CBA-SCOPE-COMPOSITION is
    where that became composition rather than intention.
    """

    def test_no_component_calls_a_crawl_client_helper(self):
        """The dead `/api/crawler/*` helpers keep having no caller.

        Deleting them is not the deliverable and never was — the gated code
        stays. Being *called* is the deliverable, and it is the part a later
        edit could change in one line.
        """
        offenders: dict[str, list[str]] = {}
        for path in _frontend_sources():
            if path.name == "api.ts":
                continue
            code = _tsx_code_only(path.read_text(encoding="utf-8"))
            called = sorted(helper for helper in CRAWL_API_HELPERS if f"{helper}(" in code)
            if called:
                offenders[path.relative_to(FRONTEND_SRC).as_posix()] = called

        assert offenders == {}, f"a component reached for a crawl client helper: {offenders}"

    def test_the_crawl_client_helpers_are_still_present(self):
        """No deletion cleanup. The counterpart to the test above.

        If these vanished, the previous test would pass for the wrong reason and
        the repository would have lost the history the threat model's re-entry
        conditions are written against.
        """
        source = (FRONTEND_SRC / "lib" / "api.ts").read_text(encoding="utf-8")
        missing = [helper for helper in CRAWL_API_HELPERS if f"function {helper}" not in source]
        assert missing == [], (
            f"gated crawl helpers were deleted rather than left unreachable: {missing}"
        )

    def test_no_crawl_token_reaches_the_unauthenticated_landing_page(self):
        """The public page is the one surface with no gate in front of it.

        A signed-in page behind a capability-gated route can hold a retired
        placeholder; the landing page is read by anyone, cannot be gated by a
        session, and is therefore held to the stricter rule.
        """
        code = _tsx_code_only(
            (FRONTEND_SRC / "app" / "pages" / "LandingPage.tsx").read_text(encoding="utf-8")
        ).lower()
        found = sorted(token for token in _CRAWL_TOKENS if token in code)
        assert found == [], f"the public landing page advertises external discovery: {found}"
