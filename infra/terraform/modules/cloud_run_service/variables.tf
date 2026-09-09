# Every name this module gives a cloud object arrives as a variable with no
# default. That is the module half of the isolation rule in architecture v1.1
# §3.2: a default is one value shared by every caller, and two environments
# that accept the same default share an identifier. The absence of these
# defaults is asserted by `tools/env_isolation_check.py`, not left to review.

variable "project_id" {
  description = "Owning GCP project. No default: each environment is its own project."
  type        = string
}

variable "region" {
  description = "Cloud Run region."
  type        = string
}

variable "service_name" {
  description = "Cloud Run service name. Environment-scoped; never a default."
  type        = string
}

variable "runtime_identity" {
  description = "Email of the runtime service account this revision runs as."
  type        = string
}

variable "container_image" {
  description = <<-TEXT
    Fully qualified image reference for this revision.

    Deliberately has no default and no committed value. No registry is owned and
    no image has been pushed (docs/operations/deploy-runbook.md, "Not yet
    applicable"), so no plan can be produced without a human supplying one. That
    is one of the gates keeping `apply` out of reach.
  TEXT
  type        = string
}

variable "database_url_ref" {
  description = "Secret Manager placeholder name holding this service's database URL."
  type        = string
}

variable "min_instances" {
  description = "Minimum served revision instances."
  type        = number
}

variable "max_instances" {
  description = "Maximum served revision instances."
  type        = number
}

variable "environment" {
  description = "Environment label applied to the service."
  type        = string
}
