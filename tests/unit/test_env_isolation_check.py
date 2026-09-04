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
    report = env_isolation_check.check(_tree(), modules=modules)
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
