# One environment's whole topology, composed from the six leaf modules.
#
# Nothing calls this module. That is the state of the work, not an oversight: a
# caller would be a root module, a root module needs a provider block and a
# state backend, and this repository has neither and no credentials to put in
# them. When a deploy target exists, the root module is what gets written — and
# `apply` is still gated behind the program owner's ALLOW_CLOUD_DEPLOY decision,
# which remains false.
#
# The `terraform_data` block at the bottom is a second, plan-time restatement of
# the isolation rule. It is not the assertion of record: it runs only if someone
# runs a plan, and nobody has. The assertion of record is
# `tools/env_isolation_check.py`, which runs in CI on every commit with no
# Terraform installed and no network.

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

locals {
  # Secret Manager entries this environment owns. `compact` drops the provider
  # entry in classroom, where it is null by policy rather than by omission.
  managed = compact([
    var.database_secret_id,
    var.provider_secret_id,
  ])

  # Every name this environment claims in a cloud namespace. Both preconditions
  # below are stated over this one list, so an identifier added to the module
  # but not added here is a review question with an obvious answer.
  scoped_names = concat([
    var.project_id,
    var.database_instance,
    var.database_name,
    var.evidence_bucket,
    var.artifact_bucket,
    var.task_queue,
    var.api_service,
    var.worker_service,
    var.scheduler_job,
    var.api_service_account,
    var.worker_service_account,
  ], local.managed)
}

module "database" {
  source = "../cloud_sql_postgres"

  project_id       = var.project_id
  region           = var.region
  instance_name    = var.database_instance
  database_name    = var.database_name
  database_version = var.database_version
  tier             = var.database_tier
  environment      = var.environment
}

module "buckets" {
  source = "../storage_buckets"

  project_id      = var.project_id
  region          = var.region
  evidence_bucket = var.evidence_bucket
  artifact_bucket = var.artifact_bucket
  environment     = var.environment
}

module "secrets" {
  source = "../secret_placeholders"

  project_id      = var.project_id
  region          = var.region
  placeholder_ids = toset(local.managed)
  environment     = var.environment
}

module "queue" {
  source = "../cloud_tasks_queue"

  project_id = var.project_id
  region     = var.region
  queue_name = var.task_queue
}

module "api" {
  source = "../cloud_run_service"

  project_id       = var.project_id
  region           = var.region
  service_name     = var.api_service
  runtime_identity = var.api_service_account
  container_image  = var.api_container_image
  database_url_ref = var.database_secret_id
  min_instances    = var.min_instances
  max_instances    = var.max_instances
  environment      = var.environment
}

module "worker" {
  source = "../cloud_run_service"

  project_id       = var.project_id
  region           = var.region
  service_name     = var.worker_service
  runtime_identity = var.worker_service_account
  container_image  = var.worker_container_image
  database_url_ref = var.database_secret_id
  min_instances    = var.min_instances
  max_instances    = var.max_instances
  environment      = var.environment
}

module "dispatcher_schedule" {
  source = "../cloud_scheduler_job"

  project_id      = var.project_id
  region          = var.region
  job_name        = var.scheduler_job
  schedule        = var.dispatch_cron
  target_url      = "${var.worker_base_url}/operations/dispatch"
  caller_identity = var.worker_service_account
  token_audience  = var.scheduler_token_audience
}

# The isolation rule, restated where a plan would see it. Neither condition can
# catch a collision with a *different* environment — a plan sees one environment
# at a time, which is exactly why the cross-environment assertion has to live
# outside Terraform, in tools/env_isolation_check.py.
resource "terraform_data" "isolation" {
  input = var.environment

  lifecycle {
    precondition {
      condition = alltrue([
        for candidate in local.scoped_names :
        length(regexall(var.environment, candidate)) > 0
      ])
      error_message = "Every identifier must carry its own environment name; one here does not, which is what a copied configuration block looks like."
    }

    precondition {
      condition     = length(local.scoped_names) == length(distinct(local.scoped_names))
      error_message = "Two resources in this environment were given the same name."
    }
  }
}
