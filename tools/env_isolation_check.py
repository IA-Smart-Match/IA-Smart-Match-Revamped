#!/usr/bin/env python3
"""Assert that Terraform environments share no identifiers.

Architecture v1.1 §3.2 puts every environment in a separate project and forbids
them sharing a project, database, queue, bucket, service-account, or secret
identifier. §3.3 adds the classroom boundary on top of that. Both are stated in
``infra/terraform/README.md``, and a statement in a README is not a control:
nothing about the sentence "environments cannot share identifiers" fails a build
when two of them do. This script is the control.

What it asserts, over ``infra/terraform/envs/*/main.tf``:

* **Nothing here can be applied.** Only ``terraform`` and ``locals`` blocks are
  permitted. A ``provider``, ``backend``, ``resource``, ``module``, or ``data``
  block fails the check — an environment file is a registry of names, not a
  deployment, and this repository has no credentials and no deployment path.
* **Every environment declares exactly the same keys.** Without this, the
  disjointness assertion below could be satisfied by *deleting* an identifier,
  which is the one way to make a uniqueness check pass by making the
  configuration worse.
* **No identifier value appears in two environments.** The load-bearing rule.
* **No identifier value carries another environment's name**, and each carries
  its own. Disjointness alone accepts ``classroom``'s bucket being named
  ``...-prod-evidence``; this catches the copy-paste at the line it happened on
  rather than after it drifts into something that also collides.
* **Every identifier is visibly a placeholder** — the reserved ``example``
  namespace, and RFC 2606 reserved domains for anything that looks like a host
  or an address. A real project id or service-account address cannot be pasted
  in without this failing.
* **The classroom boundary.** ``provider_mode`` is fixtures, there is no
  provider secret at all, and no environment promotes into or out of classroom.
* **Live data implies gated providers**, and only ``prod`` may hold anything
  other than synthetic data.

And, since F5 added them, over ``infra/terraform/modules/**/*.tf``:

* **No module mints an identifier of its own.** Every variable that names a
  cloud object is declared without a default, and no module writes a literal
  name into a resource attribute. A default is one value shared by every
  caller, so it is the one way two environments can still collide after the
  registry above has been proven disjoint.
* **The registry and the composition module name exactly the same things.**
  Every identifier the environments declare is consumed by ``modules/platform``
  and every input ``modules/platform`` declares is classified. An input nobody
  classified could be filled from somewhere nobody checks.
* **No module carries a provider, a backend, a secret version, a database
  user, or a service-account credential.** The first two would name a project
  and a credential; the rest would put a value into Terraform state.
* **Nothing has been initialized, planned, or applied.** There is no state, no
  plan file, no ``.tfvars``, and no lock file anywhere in the tree, and the four
  ``modules/platform`` deploy inputs stay defaultless — no image has been pushed
  and nothing has ever been deployed. ``ALLOW_CLOUD_DEPLOY`` remains false.

And, over ``infra/terraform/envs/<env>/root.tf``, where one exists:

* **Only a listed environment may carry a root module at all.** Classroom does,
  because it holds no provider credential; ``ROOT_MODULE_ENVIRONMENTS`` is the
  decision, and an unlisted environment growing one fails.
* **A root module is plan-only.** No ``provider`` block — so nothing to
  authenticate as — no ``backend``, no ``resource``, no ``data``, and no
  ``locals`` that could mint a name the registry never saw. It is exactly one
  call into ``modules/platform`` by local path, passing every input the module
  declares, each from ``local.*`` or ``var.*`` and never a literal.
* **Its deploy inputs cannot hold a real value.** The four names that do not
  exist yet are supplied here as reserved-namespace placeholders, and each
  carries a ``validation`` requiring the ``example`` token — so a ``-var`` on
  the command line cannot slip a real image reference past review either. A
  plan produced from this root plans a deployment of nothing, to nowhere.

This parses a deliberately small subset of HCL rather than shelling out to
``terraform``: the check must run in CI and on a laptop with no Terraform
installed, no plugins downloaded, and no network. Anything the subset does not
recognize — an interpolation, a variable reference, a list, a nested block
inside ``locals`` — is a parse error, not a shrug. Fail closed: a value this
script cannot read is a value it cannot prove is unique.

Usage::

    python tools/env_isolation_check.py           # check the tree
    python tools/env_isolation_check.py --json    # machine-readable output

Exit codes: ``0`` clean, ``1`` findings.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENVS_ROOT = REPO_ROOT / "infra" / "terraform" / "envs"

#: The environments that must exist, from v1.1 §3.2 and the README table. A new
#: directory that is not listed here fails the check: an environment nobody
#: classified is an environment nobody checked the isolation of.
EXPECTED_ENVIRONMENTS: tuple[str, ...] = ("classroom", "dev", "prod", "staging")

#: Blocks permitted at the top level of an environment file. Everything else —
#: `provider`, `resource`, `module`, `data`, `import` — describes something that
#: gets created, and nothing here gets created.
ALLOWED_BLOCKS: frozenset[str] = frozenset({"terraform", "locals"})

Scalar = str | int | bool | None


@dataclass(frozen=True)
class IdentifierKey:
    """One key whose value must be unique across environments.

    Attributes:
        name: The key as it appears in the ``locals`` block.
        placeholder: Whether the value must carry the reserved ``example``
            token. Cloud resource names must; a release tag prefix is not a
            cloud resource and would read as noise with ``example`` in it.
        null_in: Environments where the value must be ``null``, and where a
            non-null value is itself a finding. Everywhere else it must be set.
    """

    name: str
    placeholder: bool = True
    null_in: tuple[str, ...] = ()


IDENTIFIER_KEYS: tuple[IdentifierKey, ...] = (
    IdentifierKey("project_id"),
    IdentifierKey("database_instance"),
    IdentifierKey("database_name"),
    IdentifierKey("evidence_bucket"),
    IdentifierKey("artifact_bucket"),
    IdentifierKey("task_queue"),
    IdentifierKey("api_service_account"),
    IdentifierKey("worker_service_account"),
    # Cloud Run service names. Two environments naming one service is the
    # collision the F5 direction names first, because it is the one a reviewer
    # is least likely to notice: the services are supposed to look alike.
    IdentifierKey("api_service"),
    IdentifierKey("worker_service"),
    IdentifierKey("scheduler_job"),
    # A Secret Manager placeholder holding the database URL. A name only — the
    # modules create no secret version anywhere, which is asserted below.
    IdentifierKey("database_secret_id"),
    # Classroom holds no provider credential at all (v1.1 §3.3): not an empty
    # one, not an unused one — none, so there is nothing to reach for.
    IdentifierKey("provider_secret_id", null_in=("classroom",)),
    # Not a cloud resource, but it decides which releases an environment may
    # deploy. Two environments sharing a prefix means one of them can deploy
    # the other's releases, which is the promotion path §3.3 forbids.
    IdentifierKey("release_tag_prefix", placeholder=False),
)

#: Keys that may legitimately hold the same value in two environments. Listing
#: them explicitly is what makes an unlisted key a failure rather than a silent
#: pass — a new identifier has to be classified before the check will accept it.
SETTING_KEYS: frozenset[str] = frozenset(
    {
        "environment",
        "region",
        "provider_mode",
        "data_class",
        "min_instances",
        "max_instances",
        "database_version",
        "database_tier",
        "dispatch_cron",
        "promotion_source",
    }
)

# ---------------------------------------------------------------------------
# The module tree
#
# The environment files are a registry of names. The modules under
# `infra/terraform/modules` are what would turn those names into resources. A
# registry whose names are disjoint is worth nothing if a module can mint a name
# of its own, so the rules below are the same isolation rule pushed one level
# down: every name a module gives a cloud object must arrive from the caller.
# ---------------------------------------------------------------------------

MODULES_ROOT = REPO_ROOT / "infra" / "terraform" / "modules"

#: The composition module — one instance describes one environment's topology.
PLATFORM_MODULE = "platform"

#: Blocks a module file may contain. `provider` is absent on purpose: a provider
#: block is where credentials and a project would be named, and no module here
#: may carry either.
MODULE_ALLOWED_BLOCKS: frozenset[str] = frozenset(
    {
        "terraform",
        "variable",
        "output",
        "locals",
        "resource",
        "module",
        "data",
    }
)

#: Resource types no module may declare, and why.
FORBIDDEN_RESOURCE_TYPES: dict[str, str] = {
    "google_secret_manager_secret_version": (
        "a secret version carries the value. A value in Terraform is a value in "
        "state, and state is a file somebody eventually commits by accident. "
        "This tree creates secret containers and never contents."
    ),
    "google_sql_user": (
        "a database user resource carries a password, with the same consequence. "
        "The application credential is supplied out of band."
    ),
    "google_service_account_key": (
        "a long-lived credential this repository must never hold or create."
    ),
}

#: Attributes that name a cloud object. Checked only where they are a block's
#: own attribute, never inside a nested block — `name` on a resource is an
#: identifier, `name` inside a Cloud Run `env` block is an environment variable.
NAME_ATTRIBUTES: frozenset[str] = frozenset(
    {
        "name",
        "name_prefix",
        "project",
        "project_id",
        "secret_id",
        "queue_name",
        "job_name",
        "service_name",
        "instance",
        "instance_name",
        "database_name",
        "evidence_bucket",
        "artifact_bucket",
        "bucket",
        "service_account",
        "service_account_email",
        "runtime_identity",
        "caller_identity",
    }
)

#: Module inputs that name something. None may declare a `default`: a default is
#: one value shared by every caller, and two environments accepting the same
#: default share an identifier — which is the collision this whole file exists
#: to prevent, arriving through the one door the registry cannot see.
NAME_INPUT_VARIABLES: frozenset[str] = frozenset(
    {
        "project_id",
        "service_name",
        "instance_name",
        "database_name",
        "queue_name",
        "job_name",
        "evidence_bucket",
        "artifact_bucket",
        "placeholder_ids",
        "runtime_identity",
        "caller_identity",
        "database_url_ref",
        "container_image",
        "target_url",
        "token_audience",
    }
    | {entry.name for entry in IDENTIFIER_KEYS}
)

#: Platform inputs that name something which does not exist yet: no image has
#: been pushed to any registry, and nothing has ever been deployed, so no URL
#: exists and no audience exists to bind a token to. None may declare a default,
#: which is the apply gate — a plan cannot be produced without a human supplying
#: values nobody can supply today.
DEPLOY_INPUT_KEYS: frozenset[str] = frozenset(
    {
        "api_container_image",
        "worker_container_image",
        "worker_base_url",
        "scheduler_token_audience",
    }
)

#: Registry identifiers that are deliberately not module inputs. A release tag
#: prefix decides which releases an environment may deploy; it names no cloud
#: object and no module consumes it.
NON_MODULE_IDENTIFIERS: frozenset[str] = frozenset({"release_tag_prefix"})

# ---------------------------------------------------------------------------
# The root module
#
# One environment — classroom, and only classroom — carries a caller for
# `modules/platform` beside its registry, so that `terraform validate` can be
# run over a composed environment rather than one leaf module at a time. A
# caller is the thing that makes an apply *conceivable*, so the rules below are
# what keep it plan-only: no provider to authenticate as, no backend to keep
# state in, nothing declared that is not a call into the composition module,
# and every deploy input pinned to a value that is visibly not real.
#
# The registry itself is untouched by any of this. `envs/*/main.tf` still holds
# only `terraform` and `locals`, and `ALLOWED_BLOCKS` above still says so.
# ---------------------------------------------------------------------------

#: The one file name an environment directory may hold beside `main.tf`.
ROOT_MODULE_FILE = "root.tf"

#: Environments permitted to carry one. Classroom is the F5 deploy target
#: (`docs/decisions/f5-deploy-target-note-2026-09-03.md`) and holds no provider
#: credential at all, which makes it the only environment where a root module
#: cannot be one credential away from an apply.
ROOT_MODULE_ENVIRONMENTS: frozenset[str] = frozenset({"classroom"})

#: Blocks a root file may contain. `provider` and `locals` are both absent on
#: purpose: the first names a project and a credential, and the second would let
#: the root mint a name the registry never saw. `resource` and `data` are absent
#: because a root module composes and declares nothing of its own.
ROOT_ALLOWED_BLOCKS: frozenset[str] = frozenset({"terraform", "variable", "module", "output"})

#: The only module source a root file may name, and it is a local path. A
#: registry source would fetch code nobody in this repository reviewed.
PLATFORM_MODULE_SOURCE = "../../modules/platform"

#: File names that must never appear under `infra/terraform`. Each is produced
#: by running something — a plan, an apply, an init — and this tree has had none
#: of them run against it.
_ARTIFACT_SUFFIXES: tuple[str, ...] = (".tfstate", ".tfplan", ".tfvars")
_ARTIFACT_NAMES: frozenset[str] = frozenset({".terraform.lock.hcl"})

#: The token that marks a value as a placeholder rather than a real name.
PLACEHOLDER_TOKEN = "example"

#: Domains reserved by RFC 2606 / RFC 6761 for documentation and testing. A
#: value that looks like a host or an address must sit under one of these.
RESERVED_DOMAINS: tuple[str, ...] = (
    "example.com",
    "example.net",
    "example.org",
    "example.invalid",
    "example.test",
    ".invalid",
    ".test",
    ".example",
    ".localhost",
)

_VALUE_CHARSET = re.compile(r"^[a-z0-9][a-z0-9._@-]*$")
_TOKEN_SPLIT = re.compile(r"[-._@]+")
_BLOCK_OPEN = re.compile(r'^([A-Za-z_][A-Za-z0-9_-]*)\s*((?:"[^"]*"\s*)*)\{\s*$')
_ASSIGNMENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*=\s*(.+?)\s*$")


class ParseError(ValueError):
    """An environment file this script cannot read, which is a failure."""


@dataclass(frozen=True)
class Block:
    """One top-level block of a Terraform file.

    Attributes:
        type: The block keyword — ``resource``, ``variable``, ``locals``, …
        labels: The quoted labels on the header line.
        body: Every line inside the block, nesting flattened.
        direct: The subset of ``body`` that are the block's own attributes,
            excluding anything nested inside a child block. The distinction
            matters: ``name`` on a resource is a cloud identifier, while
            ``name`` inside a Cloud Run ``env`` block is an environment
            variable, and a rule that cannot tell the two apart is a rule
            somebody eventually switches off.
    """

    type: str
    labels: tuple[str, ...]
    body: tuple[str, ...]
    direct: tuple[str, ...] = ()


@dataclass(frozen=True)
class Environment:
    """One parsed environment configuration."""

    name: str
    path: str
    blocks: tuple[Block, ...]
    values: dict[str, Scalar]


@dataclass(frozen=True)
class ModuleFile:
    """One parsed ``.tf`` file belonging to a module."""

    module: str
    path: str
    blocks: tuple[Block, ...]


@dataclass(frozen=True)
class RootFile:
    """One parsed ``root.tf`` — an environment's caller for the platform module."""

    environment: str
    path: str
    blocks: tuple[Block, ...]


@dataclass(frozen=True)
class Finding:
    """One violation, with the environment and rule that produced it."""

    code: str
    environment: str
    message: str


@dataclass
class IsolationReport:
    """The outcome of a run."""

    findings: list[Finding] = field(default_factory=list)
    environments: list[str] = field(default_factory=list)
    modules: list[str] = field(default_factory=list)
    roots: list[str] = field(default_factory=list)
    identifiers_checked: int = 0

    @property
    def ok(self) -> bool:
        return not self.findings


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def strip_comments(text: str) -> str:
    """Remove ``#`` and ``//`` comments that are not inside a quoted string."""
    out: list[str] = []
    for line in text.splitlines():
        in_string = False
        cut = len(line)
        index = 0
        while index < len(line):
            char = line[index]
            if char == '"' and (index == 0 or line[index - 1] != "\\"):
                in_string = not in_string
            elif not in_string and (
                char == "#" or (char == "/" and line[index : index + 2] == "//")
            ):
                cut = index
                break
            index += 1
        out.append(line[:cut].rstrip())
    return "\n".join(out)


def parse_value(raw: str) -> Scalar:
    """Parse the right-hand side of an assignment, or refuse to.

    Only string, integer, boolean, and ``null`` literals are accepted. A
    reference or an interpolation is refused rather than skipped: a value this
    script cannot resolve is a value whose uniqueness it cannot assert, and
    quietly ignoring it is exactly how a gate goes green while meaning nothing.
    """
    value = raw.strip()
    if value == "null":
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
        inner = value[1:-1]
        if "${" in inner:
            raise ParseError(f"interpolation is not supported in this subset: {raw!r}")
        return inner
    raise ParseError(f"unsupported value: {raw!r}")


def parse_blocks(text: str, path: str) -> tuple[Block, ...]:
    """Split a Terraform file into its top-level blocks.

    Shared by the environment registry and the module tree, so both are read by
    the same subset of HCL and neither gets a more forgiving parser than the
    other.
    """
    blocks: list[Block] = []
    depth = 0
    block_type = ""
    labels: tuple[str, ...] = ()
    body: list[str] = []
    direct: list[str] = []

    for raw_line in strip_comments(text).splitlines():
        line = raw_line.strip()
        if depth == 0:
            if not line:
                continue
            match = _BLOCK_OPEN.match(line)
            if not match:
                raise ParseError(f"{path}: unsupported top-level construct: {line!r}")
            block_type = match.group(1)
            labels = tuple(re.findall(r'"([^"]*)"', match.group(2)))
            body = []
            direct = []
            depth = 1
            continue

        if depth == 1 and line and not line.startswith("}"):
            direct.append(line)

        depth += line.count("{") - line.count("}")
        if depth == 0:
            blocks.append(Block(block_type, labels, tuple(body), tuple(direct)))
        else:
            if line:
                body.append(line)

    if depth != 0:
        raise ParseError(f"{path}: unbalanced braces")

    return tuple(blocks)


def parse_environment_file(name: str, text: str, path: str) -> Environment:
    """Parse one ``main.tf`` into blocks and ``locals`` values."""
    blocks = parse_blocks(text, path)

    values: dict[str, Scalar] = {}
    for block in blocks:
        if block.type != "locals":
            continue
        for line in block.body:
            match = _ASSIGNMENT.match(line)
            if not match:
                raise ParseError(f"{path}: unsupported line in locals: {line!r}")
            key = match.group(1)
            if key in values:
                raise ParseError(f"{path}: {key} is assigned twice")
            values[key] = parse_value(match.group(2))

    return Environment(name=name, path=path, blocks=tuple(blocks), values=values)


def load_environments(root: Path | None = None) -> dict[str, Environment]:
    """Parse every environment under ``infra/terraform/envs``."""
    envs_root = ENVS_ROOT if root is None else root
    found: dict[str, Environment] = {}
    for directory in sorted(p for p in envs_root.iterdir() if p.is_dir()):
        main = directory / "main.tf"
        if not main.exists():
            raise ParseError(f"{directory}: no main.tf")
        relative = (
            main.relative_to(REPO_ROOT).as_posix()
            if main.is_absolute() and REPO_ROOT in main.parents
            else str(main)
        )
        found[directory.name] = parse_environment_file(
            directory.name, main.read_text(encoding="utf-8"), relative
        )
    return found


def _relative(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def load_modules(root: Path | None = None) -> tuple[ModuleFile, ...]:
    """Parse every ``.tf`` file under ``infra/terraform/modules``."""
    modules_root = MODULES_ROOT if root is None else root
    if not modules_root.exists():
        return ()

    files: list[ModuleFile] = []
    for path in sorted(modules_root.rglob("*.tf")):
        module = path.relative_to(modules_root).parts[0]
        files.append(
            ModuleFile(
                module=module,
                path=_relative(path),
                blocks=parse_blocks(path.read_text(encoding="utf-8"), _relative(path)),
            )
        )
    return tuple(files)


def load_roots(root: Path | None = None) -> tuple[RootFile, ...]:
    """Parse every ``root.tf`` under ``infra/terraform/envs``."""
    envs_root = ENVS_ROOT if root is None else root
    if not envs_root.exists():
        return ()

    files: list[RootFile] = []
    for directory in sorted(p for p in envs_root.iterdir() if p.is_dir()):
        path = directory / ROOT_MODULE_FILE
        if not path.exists():
            continue
        files.append(
            RootFile(
                environment=directory.name,
                path=_relative(path),
                blocks=parse_blocks(path.read_text(encoding="utf-8"), _relative(path)),
            )
        )
    return tuple(files)


# ---------------------------------------------------------------------------
# The rules
# ---------------------------------------------------------------------------


def _tokens(value: str) -> set[str]:
    return {token for token in _TOKEN_SPLIT.split(value.lower()) if token}


def _check_shape(env: Environment, findings: list[Finding]) -> None:
    """Blocks, key set, and the environment's own name."""
    for block in env.blocks:
        if block.type not in ALLOWED_BLOCKS:
            findings.append(
                Finding(
                    "deployable-block",
                    env.name,
                    f"{env.path}: {block.type!r} block. Environment files are "
                    "configuration only — nothing here may be applied, so only "
                    f"{sorted(ALLOWED_BLOCKS)} blocks are permitted.",
                )
            )
        if block.type == "terraform":
            for line in block.body:
                if re.match(r"^(backend|cloud)\b", line):
                    findings.append(
                        Finding(
                            "state-backend",
                            env.name,
                            f"{env.path}: {line!r}. A state backend points at real "
                            "storage and real credentials; there is none here.",
                        )
                    )

    expected = {key.name for key in IDENTIFIER_KEYS} | set(SETTING_KEYS)
    missing = sorted(expected - set(env.values))
    unknown = sorted(set(env.values) - expected)
    if missing:
        findings.append(
            Finding(
                "missing-key",
                env.name,
                f"{env.path}: missing {', '.join(missing)}. Every environment "
                "declares the same keys, so a uniqueness check cannot be "
                "satisfied by deleting an identifier.",
            )
        )
    if unknown:
        findings.append(
            Finding(
                "unclassified-key",
                env.name,
                f"{env.path}: {', '.join(unknown)} is in neither IDENTIFIER_KEYS "
                "nor SETTING_KEYS in tools/env_isolation_check.py. Classify it: "
                "an unclassified key is not checked for uniqueness.",
            )
        )

    declared = env.values.get("environment")
    if declared != env.name:
        findings.append(
            Finding(
                "environment-name",
                env.name,
                f"{env.path}: environment = {declared!r} in directory {env.name!r}.",
            )
        )


def _check_identifier_value(
    env: Environment, key: IdentifierKey, value: Scalar, findings: list[Finding]
) -> None:
    """Nullability, placeholder form, and environment tagging for one value."""
    if value is None:
        if env.name not in key.null_in:
            findings.append(
                Finding(
                    "missing-identifier",
                    env.name,
                    f"{env.path}: {key.name} is null, but only "
                    f"{list(key.null_in) or 'no environment'} may leave it unset.",
                )
            )
        return

    if env.name in key.null_in:
        findings.append(
            Finding(
                "unexpected-identifier",
                env.name,
                f"{env.path}: {key.name} = {value!r}, but {env.name} must declare "
                "it null. Declaring one is declaring that it exists.",
            )
        )

    if not isinstance(value, str):
        findings.append(
            Finding(
                "identifier-type",
                env.name,
                f"{env.path}: {key.name} = {value!r} is not a string.",
            )
        )
        return

    if not _VALUE_CHARSET.match(value):
        findings.append(
            Finding(
                "identifier-charset",
                env.name,
                f"{env.path}: {key.name} = {value!r} is not lowercase "
                "[a-z0-9._@-], which every cloud identifier here must be.",
            )
        )

    if key.placeholder and PLACEHOLDER_TOKEN not in _tokens(value):
        findings.append(
            Finding(
                "not-a-placeholder",
                env.name,
                f"{env.path}: {key.name} = {value!r} does not carry the "
                f"{PLACEHOLDER_TOKEN!r} token. Nothing here is deployed, so no "
                "identifier may name a real project, bucket, account, or secret.",
            )
        )

    if "@" in value or "." in value.rsplit("@", 1)[-1]:
        host = value.rsplit("@", 1)[-1]
        if "." in host and not any(
            host == domain or host.endswith(domain) for domain in RESERVED_DOMAINS
        ):
            findings.append(
                Finding(
                    "unreserved-domain",
                    env.name,
                    f"{env.path}: {key.name} = {value!r} uses {host!r}, which is "
                    "not a reserved documentation domain (RFC 2606). A real "
                    "address here would be a real account.",
                )
            )

    tokens = _tokens(value)
    if env.name not in tokens:
        findings.append(
            Finding(
                "untagged-identifier",
                env.name,
                f"{env.path}: {key.name} = {value!r} does not contain the "
                f"environment name {env.name!r}. Environment-tagged names are why "
                "identifiers stay disjoint as the configuration grows.",
            )
        )
    foreign = sorted(tokens & (set(EXPECTED_ENVIRONMENTS) - {env.name}))
    if foreign:
        findings.append(
            Finding(
                "foreign-environment",
                env.name,
                f"{env.path}: {key.name} = {value!r} names another environment "
                f"({', '.join(foreign)}). This is what a copied configuration "
                "block looks like before it becomes a shared identifier.",
            )
        )


def _check_disjoint(environments: dict[str, Environment], findings: list[Finding]) -> None:
    """The load-bearing rule: no identifier value in two environments."""
    seen: dict[str, list[tuple[str, str]]] = {}
    for env_name in sorted(environments):
        env = environments[env_name]
        for key in IDENTIFIER_KEYS:
            value = env.values.get(key.name)
            if not isinstance(value, str):
                continue
            seen.setdefault(value.strip().lower(), []).append((env_name, key.name))

    for value, owners in sorted(seen.items()):
        if len(owners) < 2:
            continue
        where = ", ".join(f"{env}.{key}" for env, key in owners)
        findings.append(
            Finding(
                "shared-identifier",
                owners[0][0],
                f"{value!r} is declared by {where}. Environments must share no "
                "project, database, queue, bucket, service-account, or secret "
                "identifier (architecture v1.1 §3.2): a shared identifier is how "
                "a classroom workload reaches production data.",
            )
        )


def _check_policy(environments: dict[str, Environment], findings: list[Finding]) -> None:
    """Classroom isolation, data class, and promotion paths."""
    for env_name in sorted(environments):
        env = environments[env_name]
        provider_mode = env.values.get("provider_mode")
        data_class = env.values.get("data_class")
        promotion_source = env.values.get("promotion_source")

        if env_name == "classroom" and provider_mode != "fixtures":
            findings.append(
                Finding(
                    "classroom-providers",
                    env_name,
                    f"{env.path}: provider_mode = {provider_mode!r}. Classroom is "
                    "fixtures only, always (v1.1 §3.3) — not 'fixtures for now'.",
                )
            )

        if data_class != "synthetic":
            if env_name != "prod":
                findings.append(
                    Finding(
                        "data-class",
                        env_name,
                        f"{env.path}: data_class = {data_class!r}. Only prod may "
                        "hold anything other than synthetic data.",
                    )
                )
            if provider_mode != "gated":
                findings.append(
                    Finding(
                        "ungated-live-data",
                        env_name,
                        f"{env.path}: data_class = {data_class!r} with "
                        f"provider_mode = {provider_mode!r}. Non-synthetic data "
                        "requires gated providers.",
                    )
                )

        if promotion_source is None:
            continue
        if promotion_source == "classroom" or env_name == "classroom":
            findings.append(
                Finding(
                    "classroom-promotion",
                    env_name,
                    f"{env.path}: promotion_source = {promotion_source!r}. There is "
                    "no promotion path into or out of classroom; it deploys only "
                    "from classroom-tagged releases (v1.1 §3.3).",
                )
            )
        elif promotion_source == env_name:
            findings.append(
                Finding(
                    "self-promotion",
                    env_name,
                    f"{env.path}: promotion_source = {promotion_source!r} is itself.",
                )
            )
        elif promotion_source not in environments:
            findings.append(
                Finding(
                    "unknown-promotion-source",
                    env_name,
                    f"{env.path}: promotion_source = {promotion_source!r} is not an "
                    "environment in this tree.",
                )
            )


def _has_default(block: Block) -> bool:
    """Whether a ``variable`` block declares a default."""
    return any(re.match(r"^default\s*=", line) for line in block.direct)


def _check_modules(files: tuple[ModuleFile, ...], findings: list[Finding]) -> None:
    """The isolation rule pushed down into the modules that consume the names."""
    for entry in files:
        for block in entry.blocks:
            if block.type not in MODULE_ALLOWED_BLOCKS:
                findings.append(
                    Finding(
                        "module-block",
                        entry.module,
                        f"{entry.path}: {block.type!r} block. A module may not "
                        "configure a provider or a backend: that is where a "
                        "project and a credential would be named, and this "
                        "repository holds neither.",
                    )
                )

            if block.type == "terraform":
                for line in block.body:
                    if re.match(r"^(backend|cloud)\b", line):
                        findings.append(
                            Finding(
                                "state-backend",
                                entry.module,
                                f"{entry.path}: {line!r}. A state backend points "
                                "at real storage and real credentials.",
                            )
                        )

            if block.type == "resource" and block.labels:
                reason = FORBIDDEN_RESOURCE_TYPES.get(block.labels[0])
                if reason is not None:
                    findings.append(
                        Finding(
                            "forbidden-resource",
                            entry.module,
                            f"{entry.path}: {block.labels[0]!r} — {reason}",
                        )
                    )

            if block.type == "variable" and block.labels and _has_default(block):
                name = block.labels[0]
                if name in NAME_INPUT_VARIABLES:
                    findings.append(
                        Finding(
                            "module-name-default",
                            entry.module,
                            f"{entry.path}: variable {name!r} declares a default. "
                            "A default is one value shared by every caller, so two "
                            "environments accepting it share an identifier — the "
                            "collision architecture v1.1 §3.2 forbids, arriving "
                            "through the one door the environment registry cannot "
                            "see. Names come from the caller, always.",
                        )
                    )
                elif name in DEPLOY_INPUT_KEYS:
                    findings.append(
                        Finding(
                            "deploy-input-default",
                            entry.module,
                            f"{entry.path}: variable {name!r} declares a default. "
                            "It names something that does not exist — no image has "
                            "been pushed and nothing has been deployed — and its "
                            "absence is what stops a plan being produced at all.",
                        )
                    )

            if block.type in {"resource", "module"}:
                for line in block.direct:
                    match = _ASSIGNMENT.match(line)
                    if match is None:
                        continue
                    attribute, raw = match.group(1), match.group(2)
                    if attribute not in NAME_ATTRIBUTES:
                        continue
                    if raw.startswith('"') and "${" not in raw:
                        findings.append(
                            Finding(
                                "hardcoded-name",
                                entry.module,
                                f"{entry.path}: {attribute} = {raw}. A literal name "
                                "in a module is a name every environment that calls "
                                "it would share. It has to come from the caller.",
                            )
                        )


def _check_module_coverage(files: tuple[ModuleFile, ...], findings: list[Finding]) -> None:
    """The registry and the composition module must name exactly the same things."""
    declared = {
        block.labels[0]
        for entry in files
        if entry.module == PLATFORM_MODULE
        for block in entry.blocks
        if block.type == "variable" and block.labels
    }
    if not declared:
        findings.append(
            Finding(
                "missing-platform-module",
                PLATFORM_MODULE,
                f"infra/terraform/modules/{PLATFORM_MODULE} declares no variables. "
                "Without it there is nothing tying the registry's identifiers to "
                "the modules that would consume them.",
            )
        )
        return

    classified = (
        {entry.name for entry in IDENTIFIER_KEYS} | set(SETTING_KEYS) | set(DEPLOY_INPUT_KEYS)
    )
    unclassified = sorted(declared - classified)
    if unclassified:
        findings.append(
            Finding(
                "unclassified-module-input",
                PLATFORM_MODULE,
                f"{', '.join(unclassified)} is in none of IDENTIFIER_KEYS, "
                "SETTING_KEYS, or DEPLOY_INPUT_KEYS. An input nobody classified "
                "can be filled from somewhere nobody checks for uniqueness.",
            )
        )

    required = {entry.name for entry in IDENTIFIER_KEYS} - NON_MODULE_IDENTIFIERS
    orphaned = sorted(required - declared)
    if orphaned:
        findings.append(
            Finding(
                "orphan-identifier",
                PLATFORM_MODULE,
                f"{', '.join(orphaned)} is declared by every environment but "
                "consumed by no module. An identifier nothing consumes is an "
                "identifier whose disjointness protects nothing.",
            )
        )

    absent = sorted(DEPLOY_INPUT_KEYS - declared)
    if absent:
        findings.append(
            Finding(
                "missing-deploy-input",
                PLATFORM_MODULE,
                f"{', '.join(absent)} is missing. Each names something that does "
                "not exist yet, and requiring them is what keeps a plan from "
                "being produced.",
            )
        )


def _platform_inputs(files: tuple[ModuleFile, ...]) -> set[str]:
    """Every variable ``modules/platform`` declares."""
    return {
        block.labels[0]
        for entry in files
        if entry.module == PLATFORM_MODULE
        for block in entry.blocks
        if block.type == "variable" and block.labels
    }


def _check_root_variable(entry: RootFile, block: Block, findings: list[Finding]) -> None:
    """One ``variable`` in a root file: a defaulted, self-evidently fake value."""
    name = block.labels[0]
    if name not in DEPLOY_INPUT_KEYS:
        findings.append(
            Finding(
                "root-unclassified-input",
                entry.environment,
                f"{entry.path}: variable {name!r} is not one of the deploy inputs "
                f"({', '.join(sorted(DEPLOY_INPUT_KEYS))}). A root module supplies "
                "the four values that do not exist yet and nothing else; every "
                "identifier comes from the registry in main.tf, where it is "
                "checked for uniqueness.",
            )
        )
        return

    default: Scalar = None
    found_default = False
    for line in block.direct:
        match = _ASSIGNMENT.match(line)
        if match is None or match.group(1) != "default":
            continue
        found_default = True
        try:
            default = parse_value(match.group(2))
        except ParseError:
            default = match.group(2)

    if not found_default:
        findings.append(
            Finding(
                "root-input-unset",
                entry.environment,
                f"{entry.path}: variable {name!r} declares no default, so the only "
                "way to run a validate here is for somebody to supply a value — "
                "and the value they would reach for is a real one. The placeholder "
                "belongs in the file, where review can see it.",
            )
        )
        return

    if not isinstance(default, str) or PLACEHOLDER_TOKEN not in default.lower():
        findings.append(
            Finding(
                "root-input-not-a-placeholder",
                entry.environment,
                f"{entry.path}: variable {name!r} defaults to {default!r}, which "
                f"does not carry the {PLACEHOLDER_TOKEN!r} token. Nothing here is "
                "deployed, so no image, URL, or audience named here may be one "
                "that could resolve.",
            )
        )
        return

    host = re.sub(r"^[a-z]+://", "", default.lower()).split("/")[0].split(":")[0]
    if "." in host and not any(
        host == domain or host.endswith(domain) for domain in RESERVED_DOMAINS
    ):
        findings.append(
            Finding(
                "root-input-unreserved-domain",
                entry.environment,
                f"{entry.path}: variable {name!r} defaults to {default!r}, whose "
                f"host {host!r} is not a reserved documentation domain (RFC 2606). "
                "A resolvable host here is a registry or a service somebody owns.",
            )
        )

    if not any(re.match(r"^validation\b", line) for line in block.body):
        findings.append(
            Finding(
                "root-input-unguarded",
                entry.environment,
                f"{entry.path}: variable {name!r} declares no validation block. The "
                "default alone is only a suggestion — a `-var` on the command line "
                "overrides it silently. The validation is what makes passing a real "
                "value fail loudly instead.",
            )
        )
        return

    guarded = any(
        re.match(r"^condition\s*=", line) and PLACEHOLDER_TOKEN in line for line in block.body
    )
    if not guarded:
        findings.append(
            Finding(
                "root-input-unguarded",
                entry.environment,
                f"{entry.path}: variable {name!r} has a validation that does not "
                f"require the {PLACEHOLDER_TOKEN!r} token. A validation that accepts "
                "a real image reference is not the gate it looks like.",
            )
        )


def _check_root_call(
    entry: RootFile, block: Block, expected_inputs: set[str], findings: list[Finding]
) -> None:
    """The ``module "platform"`` call itself: local source, no name minted here."""
    if block.labels[:1] != (PLATFORM_MODULE,):
        findings.append(
            Finding(
                "root-foreign-module",
                entry.environment,
                f"{entry.path}: module {block.labels!r}. The only module a root "
                f"file may call is {PLATFORM_MODULE!r}; anything else composes a "
                "topology nobody reviewed as one.",
            )
        )
        return

    supplied: set[str] = set()
    source: Scalar = None
    for line in block.direct:
        match = _ASSIGNMENT.match(line)
        if match is None:
            continue
        attribute, raw = match.group(1), match.group(2)
        if attribute == "source":
            try:
                source = parse_value(raw)
            except ParseError:
                source = raw
            continue
        supplied.add(attribute)
        if raw.startswith('"') or raw.startswith("'"):
            findings.append(
                Finding(
                    "root-literal-input",
                    entry.environment,
                    f"{entry.path}: {attribute} = {raw}. A literal at the call site "
                    "is a name the registry never saw and the disjointness check "
                    "cannot read. Every input comes from local.* or var.*.",
                )
            )

    if source != PLATFORM_MODULE_SOURCE:
        findings.append(
            Finding(
                "root-module-source",
                entry.environment,
                f"{entry.path}: source = {source!r}, not {PLATFORM_MODULE_SOURCE!r}. "
                "A remote or registry source fetches code this repository did not "
                "review, and the composition module is the only thing a root here "
                "may compose.",
            )
        )

    if not expected_inputs:
        return
    missing = sorted(expected_inputs - supplied)
    unknown = sorted(supplied - expected_inputs)
    if missing:
        findings.append(
            Finding(
                "root-missing-input",
                entry.environment,
                f"{entry.path}: the platform call omits {', '.join(missing)}. An "
                "omitted input is one Terraform would prompt for or take from a "
                "default, which is how an unchecked value gets in.",
            )
        )
    if unknown:
        findings.append(
            Finding(
                "root-unknown-input",
                entry.environment,
                f"{entry.path}: the platform call passes {', '.join(unknown)}, which "
                f"modules/{PLATFORM_MODULE} does not declare.",
            )
        )


def _check_roots(
    roots: tuple[RootFile, ...], files: tuple[ModuleFile, ...], findings: list[Finding]
) -> None:
    """A root module is permitted, in one environment, and only plan-only."""
    expected_inputs = _platform_inputs(files)

    for entry in roots:
        if entry.environment not in ROOT_MODULE_ENVIRONMENTS:
            findings.append(
                Finding(
                    "unlisted-root-module",
                    entry.environment,
                    f"{entry.path}: {entry.environment} is not in "
                    "ROOT_MODULE_ENVIRONMENTS in tools/env_isolation_check.py. A "
                    "root module is what makes an apply conceivable; which "
                    "environments may hold one is a decision, not a default.",
                )
            )

        calls = 0
        for block in entry.blocks:
            if block.type not in ROOT_ALLOWED_BLOCKS:
                findings.append(
                    Finding(
                        "root-deployable-block",
                        entry.environment,
                        f"{entry.path}: {block.type!r} block. A root file composes "
                        "the platform module and nothing else — a provider block "
                        "names the credential an apply would use, and a resource or "
                        "data block reaches a live project directly. Only "
                        f"{sorted(ROOT_ALLOWED_BLOCKS)} are permitted, and "
                        "ALLOW_CLOUD_DEPLOY remains false.",
                    )
                )
                continue

            if block.type == "terraform":
                for line in block.body:
                    if re.match(r"^(backend|cloud)\b", line):
                        findings.append(
                            Finding(
                                "state-backend",
                                entry.environment,
                                f"{entry.path}: {line!r}. A state backend points at "
                                "real storage and real credentials; a validate needs "
                                "none, which is what `-backend=false` means.",
                            )
                        )

            if block.type == "variable" and block.labels:
                _check_root_variable(entry, block, findings)

            if block.type == "module":
                calls += 1
                _check_root_call(entry, block, expected_inputs, findings)

        if calls != 1:
            findings.append(
                Finding(
                    "root-call-count",
                    entry.environment,
                    f"{entry.path}: {calls} module calls. A root file is exactly one "
                    f"call into modules/{PLATFORM_MODULE} — the composition is where "
                    "an environment's topology is reviewed as a whole.",
                )
            )


def _check_layout(root: Path, findings: list[Finding]) -> None:
    """Nothing here has been planned, applied, or even initialized."""
    if not root.exists():
        return

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        name = path.name
        if name.endswith(".tfvars.example"):
            continue
        # `.tfstate.backup` is the one that does not end in a listed suffix, and
        # it is the copy of state that survives a failed apply.
        if name in _ARTIFACT_NAMES or name.endswith(_ARTIFACT_SUFFIXES) or ".tfstate." in name:
            findings.append(
                Finding(
                    "apply-artifact",
                    "tree",
                    f"{_relative(path)}: this file is produced by running "
                    "Terraform. Nothing in this tree has been initialized, "
                    "planned, or applied, and each of these files records "
                    "resolved values — which is how a real project id first gets "
                    "written down. .gitignore covers them; a tracked one is a "
                    "failure regardless.",
                )
            )

    for path in sorted(root.glob("*.tf")):
        findings.append(
            Finding(
                "root-module",
                "tree",
                f"{_relative(path)}: a root module at the top of the tree. A root "
                "module is what makes an apply possible; there is deliberately "
                "none, and ALLOW_CLOUD_DEPLOY remains false.",
            )
        )

    envs = root / "envs"
    if not envs.exists():
        return
    for directory in sorted(p for p in envs.iterdir() if p.is_dir()):
        for path in sorted(p for p in directory.iterdir() if p.is_file()):
            if path.name == "main.tf":
                continue
            if path.name == ROOT_MODULE_FILE and directory.name in ROOT_MODULE_ENVIRONMENTS:
                # Read, and asserted over, by `_check_roots`. The exemption is
                # by file name and by environment, so a `deploy.tf` — or a
                # `root.tf` in prod — is still an unasserted file.
                continue
            findings.append(
                Finding(
                    "stray-environment-file",
                    directory.name,
                    f"{_relative(path)}: only main.tf and, where "
                    "ROOT_MODULE_ENVIRONMENTS permits it, root.tf are read here, so "
                    "a third file in an environment directory is configuration this "
                    "check asserts nothing about — which is the whole way around it.",
                )
            )


def check(
    environments: dict[str, Environment],
    modules: tuple[ModuleFile, ...] | None = None,
    layout_root: Path | None = None,
    roots: tuple[RootFile, ...] | None = None,
) -> IsolationReport:
    """Run every rule over a set of parsed environments, modules, and roots."""
    files = load_modules() if modules is None else modules
    root_files = load_roots() if roots is None else roots
    report = IsolationReport(
        environments=sorted(environments),
        modules=sorted({entry.module for entry in files}),
        roots=sorted(entry.environment for entry in root_files),
    )
    findings = report.findings

    missing = sorted(set(EXPECTED_ENVIRONMENTS) - set(environments))
    extra = sorted(set(environments) - set(EXPECTED_ENVIRONMENTS))
    if missing:
        findings.append(
            Finding(
                "missing-environment",
                ",".join(missing),
                f"expected environments are absent: {', '.join(missing)}",
            )
        )
    if extra:
        findings.append(
            Finding(
                "unlisted-environment",
                ",".join(extra),
                f"{', '.join(extra)} is not in EXPECTED_ENVIRONMENTS in "
                "tools/env_isolation_check.py. Add it there — an environment "
                "nobody classified is an environment nobody isolated.",
            )
        )

    for env_name in sorted(environments):
        env = environments[env_name]
        _check_shape(env, findings)
        for key in IDENTIFIER_KEYS:
            if key.name not in env.values:
                continue
            report.identifiers_checked += 1
            _check_identifier_value(env, key, env.values[key.name], findings)

    _check_disjoint(environments, findings)
    _check_policy(environments, findings)
    _check_modules(files, findings)
    _check_module_coverage(files, findings)
    _check_roots(root_files, files, findings)
    _check_layout(
        (REPO_ROOT / "infra" / "terraform") if layout_root is None else layout_root,
        findings,
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    try:
        environments = load_environments()
    except (ParseError, OSError) as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        else:
            print(f"Environment configuration could not be read: {exc}")
        return 1

    report = check(environments)

    if args.json:
        print(
            json.dumps(
                {
                    "ok": report.ok,
                    "environments": report.environments,
                    "modules": report.modules,
                    "roots": report.roots,
                    "identifiers_checked": report.identifiers_checked,
                    "findings": [f.__dict__ for f in report.findings],
                },
                indent=2,
            )
        )
    elif report.findings:
        print(f"Environment isolation findings ({len(report.findings)}):\n")
        for finding in report.findings:
            print(f"  [{finding.code}] {finding.environment}")
            print(f"    {finding.message}\n")
    else:
        print(
            f"Environment isolation clean: {len(report.environments)} environments "
            f"({', '.join(report.environments)}), "
            f"{report.identifiers_checked} identifiers, none shared; "
            f"{len(report.modules)} modules mint no identifier of their own; "
            f"{len(report.roots)} root module(s) "
            f"({', '.join(report.roots) or 'none'}) compose the platform module "
            "with placeholder inputs, hold no provider and no backend, and so "
            "cannot be applied."
        )

    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
