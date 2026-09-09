# classroom root module — PLAN-ONLY. NOTHING HERE HAS BEEN APPLIED.
#
# This file is the one thing `infra/terraform` previously refused to contain: a
# caller for `modules/platform`. It exists so that `terraform validate` can be
# run against a composed environment — so the module tree is proven to
# type-check as a whole rather than one leaf at a time — and it is written so
# that validating is the only thing it can do.
#
# Four properties make it unappliable, and `tools/env_isolation_check.py`
# asserts every one of them rather than trusting this comment:
#
#   1. No `provider` block. The Google provider is never configured here, so no
#      project and no credential is named. A human adding one is the visible,
#      reviewable act that `ALLOW_CLOUD_DEPLOY=true` would authorise; until
#      then there is nothing for an apply to authenticate as.
#   2. No `backend` block. State would be local and throwaway, which is what a
#      `-backend=false` init is for and nothing else.
#   3. No `resource` and no `data` block. This file composes; it declares
#      nothing of its own and reads nothing from a live project.
#   4. Every deploy input below is a placeholder in the reserved `example`
#      namespace, and each carries a `validation` that rejects a value without
#      the `example` token. A real image reference or a real service URL cannot
#      be passed in without first deleting an assertion, in a diff, under
#      review. The deploy inputs are still defaultless in `modules/platform`
#      itself; the placeholders live here, at the caller, which is where a fake
#      value is obviously fake.
#
# The identifiers all come from `local.*` in main.tf, which is still a registry
# of names and still holds no module block of its own. What each of the four
# deploy values will really be is a question nobody has answered — see
# `docs/plans/open-questions/f5-deploy-deferred.md`, OQ-F5-001 through 004.

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

# --- Deploy inputs that name things which do not exist ---------------------

variable "api_container_image" {
  description = <<-TEXT
    Image reference for the API revision (OQ-F5-001).

    No registry is owned and `.github/workflows/build.yml` pushes nowhere, so
    there is no image to name. The default below is a reserved-domain
    placeholder that cannot be pulled, and the validation refuses anything that
    is not visibly one.
  TEXT
  type        = string
  default     = "example.invalid/smartmatch/example-classroom-api:example"

  validation {
    condition     = can(regex("example", var.api_container_image))
    error_message = "Only example-namespace placeholders may be passed here; a real image reference means a real registry, which requires ALLOW_CLOUD_DEPLOY."
  }
}

variable "worker_container_image" {
  description = <<-TEXT
    Image reference for the worker revision (OQ-F5-001). Same reasoning, same
    registry that nobody owns.
  TEXT
  type        = string
  default     = "example.invalid/smartmatch/example-classroom-worker:example"

  validation {
    condition     = can(regex("example", var.worker_container_image))
    error_message = "Only example-namespace placeholders may be passed here; a real image reference means a real registry, which requires ALLOW_CLOUD_DEPLOY."
  }
}

variable "worker_base_url" {
  description = <<-TEXT
    Deployed worker URL the scheduler posts to (OQ-F5-002).

    A Cloud Run URL is assigned at apply. Nothing has been applied, so this
    value cannot be known; the placeholder is an RFC 2606 host that does not
    resolve.
  TEXT
  type        = string
  default     = "https://example-smartmatch-classroom-worker.example.invalid"

  validation {
    condition     = can(regex("example", var.worker_base_url))
    error_message = "Only example-namespace placeholders may be passed here; a real worker URL only exists after an apply."
  }
}

variable "scheduler_token_audience" {
  description = <<-TEXT
    OIDC audience the scheduler's token is bound to (OQ-F5-003).

    Finding S-001 leaves the audience and the service-account allowlist open,
    and the A1b identity-provider worksheet is unfilled. A plausible-looking
    value here would be an invented one, so the placeholder is deliberately
    unresolvable.
  TEXT
  type        = string
  default     = "https://example-smartmatch-classroom-worker.example.invalid/operations/dispatch"

  validation {
    condition     = can(regex("example", var.scheduler_token_audience))
    error_message = "Only example-namespace placeholders may be passed here; the real audience is blocked on Finding S-001."
  }
}

# --- The composition -------------------------------------------------------
# Every identifier arrives from main.tf's registry. Not one name is written
# here, which is the same rule the modules are held to: a name minted at the
# call site is a name the disjointness check never saw.

module "platform" {
  source = "../../modules/platform"

  project_id             = local.project_id
  database_instance      = local.database_instance
  database_name          = local.database_name
  evidence_bucket        = local.evidence_bucket
  artifact_bucket        = local.artifact_bucket
  task_queue             = local.task_queue
  api_service            = local.api_service
  worker_service         = local.worker_service
  scheduler_job          = local.scheduler_job
  api_service_account    = local.api_service_account
  worker_service_account = local.worker_service_account
  database_secret_id     = local.database_secret_id
  provider_secret_id     = local.provider_secret_id

  environment      = local.environment
  region           = local.region
  min_instances    = local.min_instances
  max_instances    = local.max_instances
  database_version = local.database_version
  database_tier    = local.database_tier
  dispatch_cron    = local.dispatch_cron

  api_container_image      = var.api_container_image
  worker_container_image   = var.worker_container_image
  worker_base_url          = var.worker_base_url
  scheduler_token_audience = var.scheduler_token_audience
}

output "claimed_names" {
  description = "Every cloud name classroom claims. Placeholders, all of them."
  value       = module.platform.claimed_names
}
