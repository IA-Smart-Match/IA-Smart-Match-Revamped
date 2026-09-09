# One variable per identifier in the environment registry, named identically.
#
# The 1:1 naming is load-bearing, not cosmetic. `tools/env_isolation_check.py`
# asserts that the set of name inputs declared here is exactly the set of
# IDENTIFIER_KEYS the environments declare — no more and no fewer. A module
# input that is not in the registry could be filled from somewhere nobody checks
# for uniqueness; a registry identifier that no module consumes is an identifier
# nobody actually isolates.
#
# None of them has a default. A default is one value shared by every caller,
# which is precisely the collision the architecture forbids.

# --- Identifiers -----------------------------------------------------------

variable "project_id" {
  description = "The environment's own GCP project."
  type        = string
}

variable "database_instance" {
  description = "Cloud SQL instance name."
  type        = string
}

variable "database_name" {
  description = "Logical database name."
  type        = string
}

variable "evidence_bucket" {
  description = "Review-evidence bucket name."
  type        = string
}

variable "artifact_bucket" {
  description = "Build and export artifact bucket name."
  type        = string
}

variable "task_queue" {
  description = "Cloud Tasks queue name."
  type        = string
}

variable "api_service" {
  description = "Cloud Run service name for the API."
  type        = string
}

variable "worker_service" {
  description = "Cloud Run service name for the worker."
  type        = string
}

variable "scheduler_job" {
  description = "Cloud Scheduler job name for the dispatcher pass."
  type        = string
}

variable "api_service_account" {
  description = "Runtime identity the API service runs as."
  type        = string
}

variable "worker_service_account" {
  description = "Runtime identity the worker runs as, and the scheduler calls with."
  type        = string
}

variable "database_secret_id" {
  description = "Secret Manager placeholder name for the database URL. A name, never a value."
  type        = string
}

variable "provider_secret_id" {
  description = <<-TEXT
    Secret Manager placeholder name for provider credentials, or null.

    Null in classroom, and only in classroom: that project holds no provider
    credential at all (architecture v1.1 §3.3), so no entry is created for one.
    Nullable rather than defaulted — an unset value here has to be written down,
    not inherited.
  TEXT
  type        = string
  nullable    = true
}

# --- Settings --------------------------------------------------------------
# These may legitimately match across environments, which is exactly why they
# are not identifiers. Defaults are permitted here.

variable "environment" {
  description = "Environment name; every identifier above must carry it."
  type        = string
}

variable "region" {
  description = "Region for every regional resource in this environment."
  type        = string
}

variable "min_instances" {
  description = "Minimum Cloud Run instances per service."
  type        = number
}

variable "max_instances" {
  description = "Maximum Cloud Run instances per service."
  type        = number
}

variable "database_version" {
  description = "PostgreSQL major version."
  type        = string
  default     = "POSTGRES_16"
}

variable "database_tier" {
  description = "Cloud SQL machine tier."
  type        = string
}

variable "dispatch_cron" {
  description = "Cron expression for the scheduled dispatcher pass."
  type        = string
}

# --- Deploy inputs that do not exist yet -----------------------------------
# The apply gate, written as configuration rather than as a request. Every
# variable below names something that has never been created: no image has been
# pushed to any registry, and no service has ever been deployed, so no URL
# exists and no audience exists to bind a token to. None has a default, so a
# plan cannot be produced without a human supplying four values that nobody can
# supply today. `tools/env_isolation_check.py` asserts they stay defaultless.

variable "api_container_image" {
  description = "Image reference for the API revision. No registry is owned; no value exists."
  type        = string
}

variable "worker_container_image" {
  description = "Image reference for the worker revision. No registry is owned; no value exists."
  type        = string
}

variable "worker_base_url" {
  description = "Deployed worker URL the scheduler posts to. Assigned at apply; nothing is applied."
  type        = string
}

variable "scheduler_token_audience" {
  description = <<-TEXT
    OIDC audience the scheduler's token is bound to.

    Left unset on purpose. Finding S-001 keeps the scheduler audience and the
    service-account allowlist open, and the A1b worksheet is unfilled; a
    plausible-looking value written here would be an invented one.
  TEXT
  type        = string
}
