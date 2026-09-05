"""Self-tests for the environment-isolation gate.

A gate nobody has verified is worse than no gate. The assertion this file exists
to verify is the one in the F5 backlog row and in ``infra/terraform/README.md``:
**environments share no identifiers.** So the central test here is the negative
one — two environments given the same project id, and the check must fail. A
uniqueness assertion that has never been shown to fail is indistinguishable from
``return 0``.

The rest cover the ways such a check goes quietly wrong: an identifier deleted
rather than made unique, a new identifier nobody classified, a value the parser
cannot read being skipped instead of refused, and the classroom boundary being
described in prose while the configuration says otherwise.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "env_isolation_check", REPO_ROOT / "tools" / "env_isolation_check.py"
)
assert _spec and _spec.loader
env_isolation_check = importlib.util.module_from_spec(_spec)
sys.modules["env_isolation_check"] = env_isolation_check
_spec.loader.exec_module(env_isolation_check)

Environment = env_isolation_check.Environment
ParseError = env_isolation_check.ParseError

TERRAFORM_BLOCK = env_isolation_check.Block("terraform", (), ('required_version = ">= 1.6.0"',))

_SETTINGS: dict[str, dict[str, object]] = {
    "dev": {"provider_mode": "fixtures", "data_class": "synthetic", "promotion_source": None},
    "staging": {"provider_mode": "fixtures", "data_class": "synthetic", "promotion_source": "dev"},
    "classroom": {
        "provider_mode": "fixtures",
        "data_class": "synthetic",
        "promotion_source": None,
    },
    "prod": {
        "provider_mode": "gated",
        "data_class": "live-pilot",
        "promotion_source": "staging",
    },
}


def _env(name: str, **overrides: object) -> Environment:
    """A valid environment configuration, with any value replaced."""
    values: dict[str, object] = {
        "project_id": f"example-smartmatch-{name}",
        "database_instance": f"example-smartmatch-{name}-sql",
        "database_name": f"example-smartmatch-{name}-core",
        "evidence_bucket": f"example-smartmatch-{name}-evidence",
        "artifact_bucket": f"example-smartmatch-{name}-artifacts",
        "task_queue": f"example-smartmatch-{name}-jobs",
        "api_service_account": f"example-smartmatch-{name}-api@example.invalid",
        "worker_service_account": f"example-smartmatch-{name}-worker@example.invalid",
        "api_service": f"example-smartmatch-{name}-api-service",
        "worker_service": f"example-smartmatch-{name}-worker-service",
        "scheduler_job": f"example-smartmatch-{name}-dispatch-job",
        "database_secret_id": f"example-smartmatch-{name}-database-url",
        "provider_secret_id": (
            None if name == "classroom" else f"example-smartmatch-{name}-provider-credentials"
        ),
        "release_tag_prefix": f"{name}-v",
        "environment": name,
        "region": "us-west1",
        "min_instances": 0,
        "max_instances": 2,
        "database_version": "POSTGRES_16",
        "database_tier": "db-custom-1-3840",
        "dispatch_cron": "*/5 * * * *",
        **_SETTINGS[name],
    }
    values.update(overrides)
    for key in [k for k, v in values.items() if v is ...]:
        del values[key]
    return Environment(
        name=name,
        path=f"infra/terraform/envs/{name}/main.tf",
        blocks=(TERRAFORM_BLOCK,),
        values=values,
    )


def _tree(**overrides: dict[str, object]) -> dict[str, Environment]:
    """The four environments, with per-environment overrides applied."""
    return {
        name: _env(name, **overrides.get(name, {}))
        for name in env_isolation_check.EXPECTED_ENVIRONMENTS
    }


def _codes(environments: dict[str, Environment]) -> set[str]:
    return {finding.code for finding in env_isolation_check.check(environments).findings}


# ---------------------------------------------------------------------------
# The rule the backlog row names: environments share no identifiers
# ---------------------------------------------------------------------------


def test_a_valid_tree_is_clean():
    """Otherwise every negative test below proves nothing."""
    report = env_isolation_check.check(_tree())
    assert report.ok, [f.message for f in report.findings]
    assert report.identifiers_checked == 4 * len(env_isolation_check.IDENTIFIER_KEYS)


def test_two_environments_sharing_a_project_id_fails():
    """The assertion. A shared project is how classroom reaches production data."""
    report = env_isolation_check.check(_tree(classroom={"project_id": "example-smartmatch-prod"}))
    shared = [f for f in report.findings if f.code == "shared-identifier"]
    assert shared, "a shared project id did not fail the check"
    assert "example-smartmatch-prod" in shared[0].message
    assert "classroom.project_id" in shared[0].message
    assert "prod.project_id" in shared[0].message


@pytest.mark.parametrize("key", [k.name for k in env_isolation_check.IDENTIFIER_KEYS])
def test_every_identifier_key_is_actually_checked_for_sharing(key: str):
    """Not just project_id: each identifier must fail on its own."""
    value = _env("prod").values[key]
    if value is None:  # provider_secret_id is null in classroom by policy
        pytest.skip(f"{key} is null in the environment used for this comparison")
    assert "shared-identifier" in _codes(_tree(staging={key: value}))


def test_sharing_is_detected_case_insensitively():
    assert "shared-identifier" in _codes(_tree(staging={"project_id": "EXAMPLE-SMARTMATCH-PROD"}))


def test_an_identifier_naming_another_environment_fails_before_it_collides():
    """Catches the copied block, not only the finished collision."""
    codes = _codes(_tree(classroom={"evidence_bucket": "example-smartmatch-prod-evidence-2"}))
    assert "foreign-environment" in codes
    assert "untagged-identifier" in codes
    assert "shared-identifier" not in codes  # it has not collided yet — that is the point


def test_an_identifier_missing_its_own_environment_name_fails():
    assert "untagged-identifier" in _codes(_tree(dev={"task_queue": "example-smartmatch-jobs"}))


# ---------------------------------------------------------------------------
# The ways a uniqueness check gets defeated
# ---------------------------------------------------------------------------


def test_deleting_an_identifier_does_not_make_the_check_pass():
    """The cheapest way to win a uniqueness check is to remove the duplicate."""
    assert "missing-key" in _codes(_tree(classroom={"project_id": ...}))


def test_an_unclassified_key_fails():
    """A new identifier nobody classified is a new identifier nobody checked."""
    assert "unclassified-key" in _codes(_tree(dev={"kms_key_ring": "example-dev-keys"}))


def test_an_environment_whose_declared_name_disagrees_with_its_directory_fails():
    assert "environment-name" in _codes(_tree(dev={"environment": "development"}))


def test_an_unlisted_environment_directory_fails():
    tree = _tree()
    tree["sandbox"] = _env("dev")
    assert "unlisted-environment" in _codes(tree)


def test_a_missing_environment_fails():
    tree = _tree()
    del tree["classroom"]
    assert "missing-environment" in _codes(tree)


# ---------------------------------------------------------------------------
# Nothing here may be applied
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("block_type", ["resource", "provider", "module", "data", "import"])
def test_a_deployable_block_fails(block_type: str):
    tree = _tree()
    env = tree["dev"]
    tree["dev"] = Environment(
        env.name,
        env.path,
        (*env.blocks, env_isolation_check.Block(block_type, ("google_storage_bucket",), ())),
        env.values,
    )
    assert "deployable-block" in _codes(tree)


def test_a_state_backend_fails():
    tree = _tree()
    env = tree["prod"]
    tree["prod"] = Environment(
        env.name,
        env.path,
        (env_isolation_check.Block("terraform", (), ('backend "gcs" {', "}")),),
        env.values,
    )
    assert "state-backend" in _codes(tree)


# ---------------------------------------------------------------------------
# Placeholders must be visibly placeholders
# ---------------------------------------------------------------------------


def test_a_real_looking_project_id_fails():
    assert "not-a-placeholder" in _codes(_tree(prod={"project_id": "ia-smartmatch-prod-482915"}))


def test_a_real_service_account_domain_fails():
    codes = _codes(
        _tree(prod={"api_service_account": "example-prod-api@smartmatch.iam.gserviceaccount.com"})
    )
    assert "unreserved-domain" in codes


def test_reserved_documentation_domains_are_accepted():
    for domain in ("example.invalid", "example.com", "example.test"):
        tree = _tree(dev={"api_service_account": f"example-smartmatch-dev-api@{domain}"})
        assert "unreserved-domain" not in _codes(tree)


def test_an_uppercase_or_spaced_identifier_fails():
    assert "identifier-charset" in _codes(_tree(dev={"database_name": "Dev Core DB"}))


def test_a_release_tag_prefix_is_exempt_from_the_example_token():
    """It is not a cloud resource; requiring 'example' in it would be noise."""
    assert "not-a-placeholder" not in _codes(_tree())


# ---------------------------------------------------------------------------
# Classroom isolation (v1.1 §3.3) and data class
# ---------------------------------------------------------------------------


def test_classroom_declaring_a_provider_secret_fails():
    """No provider credential exists in that project — not even an unused one."""
    assert "unexpected-identifier" in _codes(
        _tree(classroom={"provider_secret_id": "example-smartmatch-classroom-provider-credentials"})
    )


def test_classroom_with_live_providers_fails():
    assert "classroom-providers" in _codes(_tree(classroom={"provider_mode": "gated"}))


def test_promoting_out_of_classroom_fails():
    assert "classroom-promotion" in _codes(_tree(prod={"promotion_source": "classroom"}))


def test_classroom_promoting_from_anywhere_fails():
    assert "classroom-promotion" in _codes(_tree(classroom={"promotion_source": "staging"}))


def test_a_promotion_source_that_is_not_an_environment_fails():
    assert "unknown-promotion-source" in _codes(_tree(prod={"promotion_source": "qa"}))


def test_self_promotion_fails():
    assert "self-promotion" in _codes(_tree(staging={"promotion_source": "staging"}))


def test_live_data_outside_prod_fails():
    assert "data-class" in _codes(_tree(staging={"data_class": "live-pilot"}))


def test_live_data_with_ungated_providers_fails():
    assert "ungated-live-data" in _codes(_tree(prod={"provider_mode": "fixtures"}))


def test_a_non_classroom_environment_may_not_omit_its_provider_secret():
    assert "missing-identifier" in _codes(_tree(dev={"provider_secret_id": None}))


# ---------------------------------------------------------------------------
# The HCL subset — anything it cannot read is refused, not skipped
# ---------------------------------------------------------------------------


def test_parses_a_minimal_environment_file():
    text = (
        "# a comment\n"
        'terraform {\n  required_version = ">= 1.6.0"\n}\n\n'
        'locals {\n  project_id = "example-smartmatch-dev"  # trailing comment\n'
        "  min_instances = 0\n  provider_secret_id = null\n  enabled = true\n}\n"
    )
    env = env_isolation_check.parse_environment_file("dev", text, "dev/main.tf")
    assert env.values == {
        "project_id": "example-smartmatch-dev",
        "min_instances": 0,
        "provider_secret_id": None,
        "enabled": True,
    }
    assert [b.type for b in env.blocks] == ["terraform", "locals"]


def test_a_hash_inside_a_string_is_not_a_comment():
    text = 'locals {\n  release_tag_prefix = "dev-v#1"\n}\n'
    env = env_isolation_check.parse_environment_file("dev", text, "dev/main.tf")
    assert env.values["release_tag_prefix"] == "dev-v#1"


@pytest.mark.parametrize(
    "value",
    ["var.project_id", "local.project_id", '"${var.project_id}"', "[]", "{}"],
)
def test_a_value_the_parser_cannot_resolve_is_refused(value: str):
    """Skipping it would let an identifier escape the uniqueness check."""
    with pytest.raises(ParseError):
        env_isolation_check.parse_environment_file(
            "dev", f"locals {{\n  project_id = {value}\n}}\n", "dev/main.tf"
        )


def test_an_unsupported_top_level_construct_is_refused():
    with pytest.raises(ParseError):
        env_isolation_check.parse_environment_file("dev", 'project_id = "x"\n', "dev/main.tf")


def test_a_duplicate_key_is_refused():
    text = 'locals {\n  project_id = "a"\n  project_id = "b"\n}\n'
    with pytest.raises(ParseError, match="assigned twice"):
        env_isolation_check.parse_environment_file("dev", text, "dev/main.tf")


def test_unbalanced_braces_are_refused():
    with pytest.raises(ParseError, match="unbalanced"):
        env_isolation_check.parse_environment_file("dev", "locals {\n", "dev/main.tf")


def test_a_resource_block_parses_and_is_then_rejected_rather_than_crashing():
    text = 'resource "google_storage_bucket" "evidence" {\n  name = "x"\n}\n'
    env = env_isolation_check.parse_environment_file("dev", text, "dev/main.tf")
    assert env.blocks[0].type == "resource"


# ---------------------------------------------------------------------------
# The gate, run against this repository as it stands
# ---------------------------------------------------------------------------


def test_the_committed_environments_are_clean():
    report = env_isolation_check.check(env_isolation_check.load_environments())
    assert sorted(report.environments) == sorted(env_isolation_check.EXPECTED_ENVIRONMENTS)
    assert report.ok, "\n".join(f"[{f.code}] {f.message}" for f in report.findings)


# ---------------------------------------------------------------------------
# The module layer (F5)
#
# The environment registry above proves four sets of names are disjoint. That
# proof is worth nothing if a module can mint a name of its own, so the tests
# below are the same rule one level down: a module default is one value every
# caller shares, and a literal name in a module is a name every environment
# that calls it gets.
# ---------------------------------------------------------------------------

ModuleFile = env_isolation_check.ModuleFile

_PLATFORM_INPUTS = sorted(
    (
        {entry.name for entry in env_isolation_check.IDENTIFIER_KEYS}
        - env_isolation_check.NON_MODULE_IDENTIFIERS
    )
    | set(env_isolation_check.DEPLOY_INPUT_KEYS)
)


def _module(name: str, text: str, filename: str = "main.tf") -> ModuleFile:
    """Parse module source the same way the gate parses the committed tree."""
    path = f"infra/terraform/modules/{name}/{filename}"
    return ModuleFile(module=name, path=path, blocks=env_isolation_check.parse_blocks(text, path))


def _platform(
    inputs: list[str] | None = None, defaults: dict[str, str] | None = None
) -> ModuleFile:
    """A composition module declaring the given inputs, with optional defaults."""
    names = _PLATFORM_INPUTS if inputs is None else inputs
    supplied = defaults or {}
    text = ""
    for name in names:
        text += f'variable "{name}" {{\n  type = string\n'
        if name in supplied:
            text += f'  default = "{supplied[name]}"\n'
        text += "}\n\n"
    return _module("platform", text, "variables.tf")


def _module_codes(*extra: ModuleFile, platform: ModuleFile | None = None) -> set[str]:
    modules = ((platform or _platform()), *extra)
    # No roots: these are the module rules. The root-module rules are exercised
    # against a synthetic root further down, and against the committed one.
    report = env_isolation_check.check(_tree(), modules=modules, roots=())
    return {finding.code for finding in report.findings}


def test_a_valid_module_set_is_clean():
    """Otherwise every negative test below proves nothing."""
    assert _module_codes() == set()


def test_a_default_on_a_module_name_input_fails():
    """The one way two environments still collide after the registry is disjoint."""
    source = 'variable "service_name" {\n  type = string\n  default = "smartmatch-api"\n}\n'
    assert "module-name-default" in _module_codes(
        _module("cloud_run_service", source, "variables.tf")
    )


@pytest.mark.parametrize("name", sorted(env_isolation_check.DEPLOY_INPUT_KEYS))
def test_a_default_on_a_deploy_input_fails(name: str):
    """These name things that do not exist; their absence is what gates apply."""
    platform = _platform(defaults={name: "a-value-somebody-invented"})
    assert "deploy-input-default" in _module_codes(platform=platform)


def test_a_literal_name_in_a_module_fails():
    source = (
        'resource "google_cloud_run_v2_service" "this" {\n'
        "  project = var.project_id\n"
        '  name    = "smartmatch-api"\n'
        "}\n"
    )
    assert "hardcoded-name" in _module_codes(_module("cloud_run_service", source))


def test_a_nested_name_attribute_is_not_mistaken_for_an_identifier():
    """`name` inside a Cloud Run env block is a variable name, not a cloud name."""
    source = (
        'resource "google_cloud_run_v2_service" "this" {\n'
        "  name = var.service_name\n"
        "  template {\n"
        "    containers {\n"
        "      env {\n"
        '        name  = "SMARTMATCH_EDITION"\n'
        "        value = var.environment\n"
        "      }\n"
        "    }\n"
        "  }\n"
        "}\n"
    )
    assert "hardcoded-name" not in _module_codes(_module("cloud_run_service", source))


def test_a_provider_block_in_a_module_fails():
    source = 'provider "google" {\n  project = var.project_id\n}\n'
    assert "module-block" in _module_codes(_module("cloud_run_service", source))


def test_a_state_backend_in_a_module_fails():
    source = 'terraform {\n  backend "gcs" {\n    bucket = "somewhere"\n  }\n}\n'
    assert "state-backend" in _module_codes(_module("platform", source))


@pytest.mark.parametrize("resource_type", sorted(env_isolation_check.FORBIDDEN_RESOURCE_TYPES))
def test_a_resource_that_would_hold_a_credential_fails(resource_type: str):
    """A version, a database user, and a long-lived credential all carry a value."""
    source = f'resource "{resource_type}" "this" {{\n  project = var.project_id\n}}\n'
    assert "forbidden-resource" in _module_codes(_module("secret_placeholders", source))


def test_an_identifier_no_module_consumes_fails():
    """Disjointness protects nothing if nothing actually consumes the name."""
    trimmed = [name for name in _PLATFORM_INPUTS if name != "task_queue"]
    assert "orphan-identifier" in _module_codes(platform=_platform(inputs=trimmed))


def test_an_unclassified_module_input_fails():
    """An input nobody classified is filled from somewhere nobody checks."""
    extended = [*_PLATFORM_INPUTS, "shared_landing_bucket"]
    assert "unclassified-module-input" in _module_codes(platform=_platform(inputs=extended))


def test_a_missing_deploy_input_fails():
    trimmed = [name for name in _PLATFORM_INPUTS if name != "worker_base_url"]
    assert "missing-deploy-input" in _module_codes(platform=_platform(inputs=trimmed))


def test_an_absent_composition_module_fails():
    assert "missing-platform-module" in {
        finding.code for finding in env_isolation_check.check(_tree(), modules=()).findings
    }


def test_parse_blocks_separates_a_blocks_own_attributes_from_nested_ones():
    source = 'resource "x" "y" {\n  name = var.a\n  env {\n    name = "B"\n  }\n}\n'
    block = env_isolation_check.parse_blocks(source, "x.tf")[0]
    assert "name = var.a" in block.direct
    assert 'name = "B"' not in block.direct
    assert 'name = "B"' in block.body


# ---------------------------------------------------------------------------
# Nothing has been initialized, planned, or applied
# ---------------------------------------------------------------------------


def _layout_codes(root: Path) -> set[str]:
    findings: list = []
    env_isolation_check._check_layout(root, findings)
    return {finding.code for finding in findings}


@pytest.mark.parametrize(
    "filename",
    ["terraform.tfstate", "terraform.tfstate.backup", "plan.tfplan", "prod.tfvars"],
)
def test_a_file_produced_by_running_terraform_fails(tmp_path: Path, filename: str):
    """Each of these records resolved values, and nothing here has been run."""
    (tmp_path / filename).write_text("", encoding="utf-8")
    assert "apply-artifact" in _layout_codes(tmp_path)


def test_an_example_tfvars_is_allowed(tmp_path: Path):
    (tmp_path / "classroom.tfvars.example").write_text("", encoding="utf-8")
    assert "apply-artifact" not in _layout_codes(tmp_path)


def test_a_root_module_fails(tmp_path: Path):
    """A root module is the thing that makes an apply possible."""
    (tmp_path / "main.tf").write_text("", encoding="utf-8")
    assert "root-module" in _layout_codes(tmp_path)


def test_a_second_file_in_an_environment_directory_fails(tmp_path: Path):
    """Only main.tf is read, so a deploy.tf beside it would be unasserted."""
    (tmp_path / "envs" / "dev").mkdir(parents=True)
    (tmp_path / "envs" / "dev" / "main.tf").write_text("", encoding="utf-8")
    (tmp_path / "envs" / "dev" / "deploy.tf").write_text("", encoding="utf-8")
    assert "stray-environment-file" in _layout_codes(tmp_path)


# ---------------------------------------------------------------------------
# The gate, run against the committed module tree
# ---------------------------------------------------------------------------


def test_the_committed_modules_are_clean():
    modules = env_isolation_check.load_modules()
    assert {entry.module for entry in modules} == {
        "cloud_run_service",
        "cloud_scheduler_job",
        "cloud_sql_postgres",
        "cloud_tasks_queue",
        "platform",
        "secret_placeholders",
        "storage_buckets",
    }
    report = env_isolation_check.check(env_isolation_check.load_environments(), modules=modules)
    assert report.ok, "\n".join(f"[{f.code}] {f.message}" for f in report.findings)


# ---------------------------------------------------------------------------
# The classroom root module
#
# A root module is the thing that makes an apply conceivable, so a check that
# merely tolerated one would give up the property the rest of this file exists
# to hold. The tests below are the negative ones that matter: a provider block,
# a backend, a literal name at the call site, and a real image reference passed
# to a deploy input. Each must fail. A gate on the one file that could deploy
# something, never shown to fail, is `return 0` with extra steps.
# ---------------------------------------------------------------------------

RootFile = env_isolation_check.RootFile

_DEPLOY_INPUTS = sorted(env_isolation_check.DEPLOY_INPUT_KEYS)
_IDENTIFIER_INPUTS = sorted(set(_PLATFORM_INPUTS) - set(_DEPLOY_INPUTS))

_PLACEHOLDER_DEFAULTS: dict[str, str] = {
    "api_container_image": "example.invalid/smartmatch/example-classroom-api:example",
    "worker_container_image": "example.invalid/smartmatch/example-classroom-worker:example",
    "worker_base_url": "https://example-smartmatch-classroom-worker.example.invalid",
    "scheduler_token_audience": (
        "https://example-smartmatch-classroom-worker.example.invalid/operations/dispatch"
    ),
}


def _variable_block(
    name: str,
    default: str | None = None,
    validation: bool = True,
    condition: str | None = None,
) -> str:
    """One root `variable`, with whichever part a test wants to break left out."""
    value = _PLACEHOLDER_DEFAULTS.get(name, "example-placeholder") if default is None else default
    text = f'variable "{name}" {{\n  type = string\n'
    if value != "":
        text += f'  default = "{value}"\n'
    if validation:
        guard = condition or f'can(regex("example", var.{name}))'
        text += (
            "  validation {\n"
            f"    condition     = {guard}\n"
            '    error_message = "placeholders only."\n'
            "  }\n"
        )
    return text + "}\n\n"


def _variables_text(**replacements: str) -> str:
    """Every deploy input, with named ones replaced by a prepared block."""
    return "".join(replacements.get(name) or _variable_block(name) for name in _DEPLOY_INPUTS)


def _call_text(
    source: str = env_isolation_check.PLATFORM_MODULE_SOURCE,
    label: str = "platform",
    omit: str = "",
    overrides: dict[str, str] | None = None,
    extra: dict[str, str] | None = None,
) -> str:
    """The `module "platform"` block, with any one input altered."""
    supplied = overrides or {}
    lines = [f'module "{label}" {{\n', f'  source = "{source}"\n']
    for name in (*_IDENTIFIER_INPUTS, *_DEPLOY_INPUTS):
        if name == omit:
            continue
        reference = "var" if name in _DEPLOY_INPUTS else "local"
        lines.append(f"  {name} = {supplied.get(name, f'{reference}.{name}')}\n")
    for name, value in (extra or {}).items():
        lines.append(f"  {name} = {value}\n")
    return "".join(lines) + "}\n"


def _root_text(
    variables: str | None = None,
    call: str | None = None,
    terraform: str | None = None,
    extra: str = "",
) -> str:
    """A root file that passes every rule, with any one part replaced."""
    header = terraform or 'terraform {\n  required_version = ">= 1.6.0"\n}\n\n'
    body = _variables_text() if variables is None else variables
    return header + body + (call or _call_text()) + extra


def _root(text: str, environment: str = "classroom") -> RootFile:
    """Parse root source the same way the gate parses the committed tree."""
    path = f"infra/terraform/envs/{environment}/root.tf"
    return RootFile(
        environment=environment,
        path=path,
        blocks=env_isolation_check.parse_blocks(text, path),
    )


def _root_codes(*roots: RootFile) -> set[str]:
    report = env_isolation_check.check(_tree(), modules=(_platform(),), roots=roots)
    return {finding.code for finding in report.findings}


def test_a_valid_root_module_is_clean():
    """Otherwise every negative test below proves nothing."""
    assert _root_codes(_root(_root_text())) == set()


def test_no_root_module_at_all_is_still_clean():
    """The root is permitted, not required — three environments carry none."""
    assert _root_codes() == set()


@pytest.mark.parametrize("block_type", ["provider", "resource", "data", "locals"])
def test_a_block_that_would_make_an_apply_possible_fails(block_type: str):
    """A provider names the credential; a local would mint an unchecked name."""
    extra = f'{block_type} "google" {{\n  project = "example-smartmatch-classroom"\n}}\n'
    assert "root-deployable-block" in _root_codes(_root(_root_text(extra=extra)))


def test_a_state_backend_in_a_root_module_fails():
    terraform = 'terraform {\n  backend "gcs" {\n    bucket = "example-state"\n  }\n}\n\n'
    assert "state-backend" in _root_codes(_root(_root_text(terraform=terraform)))


def test_a_root_module_in_an_unlisted_environment_fails():
    """Classroom is the F5 target and holds no credential; prod is neither."""
    assert "unlisted-root-module" in _root_codes(_root(_root_text(), environment="prod"))


def test_root_tf_is_exempt_from_the_stray_file_rule_in_classroom_alone(tmp_path: Path):
    """The exemption is by file name *and* environment, or it is a loophole."""
    for name in env_isolation_check.EXPECTED_ENVIRONMENTS:
        directory = tmp_path / "envs" / name
        directory.mkdir(parents=True)
        (directory / "main.tf").write_text("", encoding="utf-8")
        (directory / "root.tf").write_text("", encoding="utf-8")

    findings: list = []
    env_isolation_check._check_layout(tmp_path, findings)
    flagged = {f.environment for f in findings if f.code == "stray-environment-file"}
    assert flagged == set(env_isolation_check.EXPECTED_ENVIRONMENTS) - {"classroom"}


def test_a_deploy_tf_beside_a_root_tf_still_fails(tmp_path: Path):
    directory = tmp_path / "envs" / "classroom"
    directory.mkdir(parents=True)
    for name in ("main.tf", "root.tf", "deploy.tf"):
        (directory / name).write_text("", encoding="utf-8")
    assert "stray-environment-file" in _layout_codes(tmp_path)


def test_a_second_module_call_in_a_root_fails():
    extra = 'module "second" {\n  source = "../../modules/platform"\n}\n'
    assert "root-call-count" in _root_codes(_root(_root_text(extra=extra)))


def test_a_root_calling_something_other_than_the_platform_module_fails():
    call = 'module "buckets" {\n  source = "../../modules/storage_buckets"\n}\n'
    assert "root-foreign-module" in _root_codes(_root(_root_text(call=call)))


def test_a_remote_module_source_fails():
    """A registry source fetches code nobody in this repository reviewed."""
    call = _call_text(source="example-org/platform/google")
    assert "root-module-source" in _root_codes(_root(_root_text(call=call)))


def test_a_literal_name_at_the_call_site_fails():
    """The name the registry never saw is the one disjointness cannot check."""
    call = _call_text(overrides={"project_id": '"example-smartmatch-classroom"'})
    assert "root-literal-input" in _root_codes(_root(_root_text(call=call)))


def test_an_omitted_platform_input_fails():
    """Terraform would prompt for it, or take a default nobody checked."""
    call = _call_text(omit="task_queue")
    assert "root-missing-input" in _root_codes(_root(_root_text(call=call)))


def test_an_input_the_platform_module_does_not_declare_fails():
    call = _call_text(extra={"invented": "local.project_id"})
    assert "root-unknown-input" in _root_codes(_root(_root_text(call=call)))


def test_a_root_variable_that_is_not_a_deploy_input_fails():
    """Identifiers come from the registry, where uniqueness is asserted."""
    variables = _variables_text() + _variable_block(
        "project_id", default="example-smartmatch-classroom"
    )
    assert "root-unclassified-input" in _root_codes(_root(_root_text(variables=variables)))


@pytest.mark.parametrize("name", sorted(env_isolation_check.DEPLOY_INPUT_KEYS))
def test_a_real_looking_deploy_input_default_fails(name: str):
    """The one that matters: a real image reference pasted into the root."""
    broken = _variable_block(name, default="us-west1-docker.pkg.dev/smartmatch/api:v1")
    variables = _variables_text(**{name: broken})
    assert "root-input-not-a-placeholder" in _root_codes(_root(_root_text(variables=variables)))


def test_a_placeholder_on_an_unreserved_domain_fails():
    """`example` in the path is not enough; the host has to be unresolvable."""
    broken = _variable_block("worker_base_url", default="https://example.smartmatch.io")
    variables = _variables_text(worker_base_url=broken)
    assert "root-input-unreserved-domain" in _root_codes(_root(_root_text(variables=variables)))


def test_a_deploy_input_with_no_default_fails():
    """Without one, running a validate means somebody supplying a real value."""
    variables = _variables_text(worker_base_url=_variable_block("worker_base_url", default=""))
    assert "root-input-unset" in _root_codes(_root(_root_text(variables=variables)))


def test_a_deploy_input_without_a_validation_fails():
    """A default alone is a suggestion: a `-var` overrides it silently."""
    broken = _variable_block("api_container_image", validation=False)
    variables = _variables_text(api_container_image=broken)
    assert "root-input-unguarded" in _root_codes(_root(_root_text(variables=variables)))


def test_a_validation_that_would_accept_a_real_value_fails():
    broken = _variable_block("api_container_image", condition="length(var.api_container_image) > 0")
    variables = _variables_text(api_container_image=broken)
    assert "root-input-unguarded" in _root_codes(_root(_root_text(variables=variables)))


def test_the_committed_root_module_is_clean():
    """The gate, run against the classroom root as it is actually committed."""
    roots = env_isolation_check.load_roots()
    assert [entry.environment for entry in roots] == ["classroom"]
    report = env_isolation_check.check(
        env_isolation_check.load_environments(),
        modules=env_isolation_check.load_modules(),
        roots=roots,
    )
    assert report.ok, "\n".join(f"[{f.code}] {f.message}" for f in report.findings)
