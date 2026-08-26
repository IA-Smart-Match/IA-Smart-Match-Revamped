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
  block fails the check — an environment skeleton that can be applied is not a
  skeleton, and this repository has no credentials and no deployment path.
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
        "promotion_source",
    }
)

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
    """One top-level block of an environment file."""

    type: str
    labels: tuple[str, ...]
    body: tuple[str, ...]


@dataclass(frozen=True)
class Environment:
    """One parsed environment configuration."""

    name: str
    path: str
    blocks: tuple[Block, ...]
    values: dict[str, Scalar]


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


def parse_environment_file(name: str, text: str, path: str) -> Environment:
    """Parse one ``main.tf`` into blocks and ``locals`` values."""
    blocks: list[Block] = []
    depth = 0
    block_type = ""
    labels: tuple[str, ...] = ()
    body: list[str] = []

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
            depth = 1
            continue

        depth += line.count("{") - line.count("}")
        if depth == 0:
            blocks.append(Block(block_type, labels, tuple(body)))
        else:
            if line:
                body.append(line)

    if depth != 0:
        raise ParseError(f"{path}: unbalanced braces")

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


def check(environments: dict[str, Environment]) -> IsolationReport:
    """Run every rule over a set of parsed environments."""
    report = IsolationReport(environments=sorted(environments))
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
            f"{report.identifiers_checked} identifiers, none shared."
        )

    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
