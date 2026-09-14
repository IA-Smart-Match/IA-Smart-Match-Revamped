"""``SMARTMATCH_CBA_TOPIC_LOCAL_EMBEDDING_ENABLED`` reaches every process that scores topics.

ADR-0017 approved an offline, in-process embedding model for customer §9's
Topic comparison, and ``Settings.cba_topic_local_embedding_enabled`` is the
deployment-level opt-in that reaches it. A flag that selects a *scoring engine*
has a plumbing obligation the flag itself cannot state: it must be set on every
process that scores, and it must not be set on processes that do not, because a
variable a container reads and ignores is indistinguishable — from the outside,
which is where an operator stands — from one it reads and honours.

Which processes those are is **derived here, not asserted from memory.** The
scoring seam is ``build_semantic_topic_provider``; this file finds its call
sites under ``services/`` and works forward from whatever it finds, so a future
card that starts scoring topics in a second service fails this file rather than
shipping a second service that silently scores on the fixture path while the
first scores on the embedding path. Two containers disagreeing about how §9
scores is not a visible failure: it is two shortlists that look alike and were
produced by different engines.

What the derivation currently finds, and why it is not obvious
--------------------------------------------------------------
Only ``services/api`` scores. One other container legitimately carries the
flag without scoring: the ``dataset`` one-shot mounts the ``tools/`` scripts,
and the verifier among them reads the flag from its own settings to judge
whether the deployment it just verified could measure topic evidence — a
reader, derived from the mounts, and required to say so in a comment. A match
run *looks* like worker work — it is
submitted as a command, and ``smartmatch_worker.handlers.handle_match_run_create``
executes it — but the split is that the **API scores and the worker solves**:
``rank_cba_candidates`` runs in ``routers/match_runs.py`` before the command is
ever submitted, and the utilities travel in the command payload, so the worker
calls ``solve_portfolio`` over numbers that are already final. The worker never
constructs a topic provider and its ``Settings`` has no field for this flag, so
setting the variable on the worker container would configure nothing. That
absence is deliberate and is pinned below in both directions — present on the
scorer, absent from the rest — because "add it to the worker too, to be safe"
is the obvious wrong fix and the one this file exists to refuse.

How the variable actually arrives is also pinned
-------------------------------------------------
``docker-compose.yml`` passes the flag through by *interpolation*
(``${VAR:-false}``) rather than hard-setting a literal. Compose resolves an
interpolated reference from the shell environment **and** from a ``.env`` file
in the project directory — both, with the shell winning — which matters on the
appliance far more than it looks: an exported shell variable lives for one
``docker compose up`` invocation, while ``.env`` survives the next deploy. A
deployment enabled by export alone silently reverts to the fixture path the
first time ``scripts/vm/deploy.sh`` runs from anywhere but that shell. So the
prose describing the mechanism is guarded too, and the specific false claim
this file was written to remove — that compose ignores ``.env`` for this
passthrough — is named so it cannot come back by paraphrase.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
SERVICES_DIR = REPO_ROOT / "services"
TOOLS_DIR = REPO_ROOT / "tools"

#: The environment variable under test, spelled once.
FLAG = "SMARTMATCH_CBA_TOPIC_LOCAL_EMBEDDING_ENABLED"

#: The construction seam for the §9 topic comparator. A call to this is what
#: makes a process a topic scorer; a docstring mention of the name is not, so
#: the trailing parenthesis is part of the pattern.
_PROVIDER_CALL = re.compile(r"\bbuild_semantic_topic_provider\s*\(")

#: The scorer itself, checked alongside the provider call so a service that
#: obtained a provider some other way is still caught.
_SCORER_CALL = re.compile(r"\brank_cba_candidates\s*\(")

#: One top-level entry under ``services:``. Service keys carry no inline value;
#: the anchor block above ``services:`` is outside the slice this runs over.
_SERVICE_HEADER = re.compile(r"^  ([a-z][a-z0-9_-]*):\s*$")

#: Claims about this flag that are false. Compose reads ``.env`` from the
#: project directory for every interpolated reference, this one included —
#: verified against ``docker compose config``. Each string is quoted from the
#: text that stated it, so a revert restores the failure rather than the claim.
_FALSE_CLAIMS = (
    "does not read `.env.example`/`.env` for this passthrough",
    "Compose does not read `.env` for it",
    "reads this from `.env`; compose does not",
)

#: Files that describe how to turn the flag on. Every one is scanned for the
#: claims above.
_PROSE_FILES = (
    Path("docker-compose.yml"),
    Path("docs/operations/hosted-synthetic-pilot-guide.md"),
    Path("docs/operations/local-dev-walkthrough.md"),
    Path("docs/operations/pilot-dataset-rebuild.md"),
    Path(".env.example"),
)


def _compose_source() -> str:
    return COMPOSE_FILE.read_text(encoding="utf-8")


def _service_blocks() -> dict[str, str]:
    """Every ``services:`` entry mapped to its own raw text block.

    Read as text rather than through a YAML parser for the reason
    ``test_compose_dev_principals.py`` gives: what has to be true is that the
    literal in the file is the literal the container receives, and this repo
    does not declare a YAML library as a test dependency in the first place.
    """
    source = _compose_source()
    start = source.index("\nservices:\n") + len("\nservices:\n")
    end = source.index("\nvolumes:\n", start)
    body = source[start:end]

    blocks: dict[str, str] = {}
    current: str | None = None
    lines: list[str] = []
    for line in body.splitlines():
        header = _SERVICE_HEADER.match(line)
        if header is not None:
            if current is not None:
                blocks[current] = "\n".join(lines)
            current = header.group(1)
            lines = []
            continue
        if current is not None:
            lines.append(line)
    if current is not None:
        blocks[current] = "\n".join(lines)

    assert "api" in blocks and "worker" in blocks, (
        "docker-compose.yml no longer declares both an `api` and a `worker` "
        "service under `services:`, so this file's block splitter has stopped "
        "seeing what it thinks it sees. Fix the splitter rather than the "
        f"assertion; it found {sorted(blocks)}"
    )
    return blocks


def _assignments(block: str) -> set[str]:
    """The environment keys a compose service block actually assigns.

    Comment lines are dropped first. That distinction is the whole point of
    this helper: naming the flag in a comment that explains why a service does
    *not* set it must not read as setting it.
    """
    keys: set[str] = set()
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.match(r"^([A-Z][A-Z0-9_]*):\s*(.*)$", stripped)
        if match is not None:
            keys.add(match.group(1))
    return keys


def _services_that_score_topics() -> set[str]:
    """Service directories under ``services/`` that construct or run a scorer."""
    scoring: set[str] = set()
    for service_dir in sorted(p for p in SERVICES_DIR.iterdir() if p.is_dir()):
        for module in service_dir.rglob("*.py"):
            text = module.read_text(encoding="utf-8")
            if _PROVIDER_CALL.search(text) or _SCORER_CALL.search(text):
                scoring.add(service_dir.name)
                break
    return scoring


def _services_that_read_the_flag() -> set[str]:
    """Compose services that run a ``tools/`` script which reads the flag.

    The ``dataset`` one-shot mounts ``tools/*.py`` over the api image rather
    than running a directory under ``services/``, so the scorer scan above
    cannot see it. What it runs is still derivable: its volume list names the
    mounted scripts, and a tool that reads
    ``Settings.cba_topic_local_embedding_enabled`` — the verifier, which judges
    the deployment's capability by this process's own settings — makes the
    flag live configuration for the container, not dead configuration. The
    reader set is derived rather than named: if the verifier stops reading
    the flag this goes back to empty, and the compose variable becomes the
    dead configuration the test below exists to refuse.
    """
    readers: set[str] = set()
    mounted = {
        line.split(":")[0].strip().lstrip("-").strip()
        for line in _service_blocks().get("dataset", "").splitlines()
        if "./tools/" in line
    }
    tools_read_flag = {
        path.name
        for path in TOOLS_DIR.glob("*.py")
        if "cba_topic_local_embedding_enabled" in path.read_text(encoding="utf-8")
    }
    for mount in mounted:
        if Path(mount).name in tools_read_flag:
            readers.add("dataset")
            break
    return readers


# ---------------------------------------------------------------------------
# Which processes score
# ---------------------------------------------------------------------------


def test_the_api_is_the_only_service_that_scores_topics() -> None:
    """Derived, so a second scorer appearing is a failure and not a surprise."""
    assert _services_that_score_topics() == {"api"}, (
        "the set of services that construct a §9 topic provider or call "
        "rank_cba_candidates has changed. Every service in that set needs "
        f"{FLAG} in its docker-compose.yml environment block, or two "
        "containers will score the same request with different engines. "
        f"Found: {sorted(_services_that_score_topics())}"
    )


def test_the_worker_solves_a_match_run_but_does_not_score_it() -> None:
    """The reason the worker legitimately has no topic configuration.

    Stated as an assertion rather than a comment because it is the premise the
    rest of this file rests on: if the worker ever starts scoring, the flag's
    absence there stops being correct and becomes the defect.
    """
    handlers = (SERVICES_DIR / "worker" / "smartmatch_worker" / "handlers.py").read_text(
        encoding="utf-8"
    )

    assert "solve_portfolio(" in handlers, (
        "smartmatch_worker.handlers no longer calls solve_portfolio, so the "
        "API-scores/worker-solves split this file documents has moved"
    )
    assert not _PROVIDER_CALL.search(handlers) and not _SCORER_CALL.search(handlers), (
        "the worker has started scoring candidates rather than solving over "
        f"utilities the API already computed. It now needs {FLAG} in its "
        "docker-compose.yml environment block and a corresponding field on "
        "smartmatch_worker.config.Settings, neither of which exists"
    )


# ---------------------------------------------------------------------------
# Where the flag is set, and where it deliberately is not
# ---------------------------------------------------------------------------


def test_every_scoring_service_receives_the_flag() -> None:
    blocks = _service_blocks()
    for service in sorted(_services_that_score_topics()):
        assert service in blocks, (
            f"services/{service} scores topics but has no `{service}` service "
            "in docker-compose.yml, so nothing configures the engine it uses"
        )
        assert FLAG in _assignments(blocks[service]), (
            f"the `{service}` compose service scores §9 topics but does not "
            f"receive {FLAG}. It will always use the recorded-fixture "
            "provider, whatever the deployment intended"
        )


def test_no_service_that_cannot_read_the_flag_is_given_it() -> None:
    """Dead configuration is worse than absent configuration.

    A ``worker`` container carrying this variable would look configured to
    every operator who reads the compose file, while
    ``smartmatch_worker.config.Settings`` has no field to receive it.
    """
    scoring = _services_that_score_topics()
    readers = _services_that_read_the_flag()
    for service, block in sorted(_service_blocks().items()):
        if service in scoring or service in readers:
            continue
        assert FLAG not in _assignments(block), (
            f"the `{service}` compose service sets {FLAG}, but nothing in "
            f"services/{service} scores topics and none of the tools it runs "
            "reads it, so the value is read by nothing. Remove it, or make "
            "the service actually use it"
        )


def test_a_reader_service_says_in_the_file_why_it_has_the_flag() -> None:
    """A reader's presence must be legible, or the next reader will 'fix' it.

    ``dataset`` carries the flag for the verifier's capability check, not for
    scoring — the same kind of non-obvious correctness as the worker's absence
    below. If a compose service that is not a scorer sets the flag without a
    comment naming why, it reads as a mistake the next edit removes, and the
    verifier goes back to reporting a deployment gap that is not one.
    """
    for service in sorted(_services_that_read_the_flag()):
        block = _service_blocks()[service]
        comments = "\n".join(line for line in block.splitlines() if line.strip().startswith("#"))
        assert FLAG in comments, (
            f"docker-compose.yml's `{service}` service sets {FLAG} without a "
            "comment naming what reads it. It is a reader, not a scorer — say "
            "which mounted tool consumes the value, alongside the assignment"
        )


def test_the_worker_says_in_the_file_why_it_has_no_topic_flag() -> None:
    """The absence must be legible, or the next reader will 'fix' it.

    ``docker-compose.yml``'s worker block already documents every other
    deliberate omission by name — the column-contract path, the task audience,
    the two service-account allowlists — precisely so that a missing variable
    reads as a decision rather than an oversight. This one is the omission most
    likely to be undone by a well-meaning edit, because a match run genuinely
    is worker work; it is the omission least able to afford being undocumented.
    """
    worker_block = _service_blocks()["worker"]
    comments = "\n".join(line for line in worker_block.splitlines() if line.strip().startswith("#"))

    assert FLAG in comments, (
        f"docker-compose.yml's `worker` service does not mention {FLAG} in a "
        "comment. Its absence from that block is correct — the worker solves "
        "over utilities the API already scored — but an undocumented absence "
        "is the one a future edit adds back as dead configuration. Say why it "
        "is not there, alongside the other omissions that block already names"
    )


# ---------------------------------------------------------------------------
# How the flag arrives
# ---------------------------------------------------------------------------


def test_the_flag_is_interpolated_so_a_dotenv_file_can_supply_it() -> None:
    """Hard-setting a literal here would make ``.env`` genuinely powerless.

    The interpolated form is what lets the appliance be configured durably.
    ``scripts/vm/deploy.sh`` runs ``docker compose up`` from a service
    invocation, not from an operator's interactive shell, so an ``export`` does
    not survive to the next deploy and a ``.env`` entry does.
    """
    api_block = _service_blocks()["api"]
    assert re.search(rf"^\s*{FLAG}:\s*\$\{{{FLAG}:-false\}}\s*$", api_block, re.MULTILINE), (
        f"the `api` service no longer passes {FLAG} through by interpolation "
        "with a false default. A hard-set literal cannot be overridden by the "
        "VM's .env file, which is the only place an operator can enable this "
        "durably across deploys"
    )


def test_the_env_example_declares_the_flag_off() -> None:
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert f"{FLAG}=false" in text, (
        f".env.example must declare {FLAG}=false. It is the inventory an "
        "operator copies to .env, and an undeclared flag is one nobody knows "
        "they may set"
    )


def test_no_file_claims_compose_ignores_dotenv_for_this_flag() -> None:
    """The claim is false, and it is false in the direction that costs most.

    Verified against ``docker compose config``: with the interpolated form
    above and a project-directory ``.env`` holding ``…=true``, the resolved
    configuration reports ``"true"``. An operator told otherwise reaches for
    ``export`` instead, and loses the setting on the next deploy without any
    signal that it went away.
    """
    offences: list[str] = []
    for relative in _PROSE_FILES:
        path = REPO_ROOT / relative
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for claim in _FALSE_CLAIMS:
            if claim in text:
                offences.append(f"{relative}: {claim!r}")

    assert not offences, (
        "these files state that docker compose does not read a project-"
        f"directory .env when resolving {FLAG}. Compose does read it — for "
        "every interpolated reference, with the shell environment taking "
        "precedence — so the documented way to enable this on the appliance "
        "is wrong, and the way it says will not work is the only one that "
        "survives a redeploy:\n  " + "\n  ".join(offences)
    )
