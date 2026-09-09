variable "project_id" {
  description = "Owning GCP project."
  type        = string
}

variable "region" {
  description = "Cloud Scheduler location."
  type        = string
}

variable "job_name" {
  description = "Cloud Scheduler job name. Environment-scoped; never a default."
  type        = string
}

variable "schedule" {
  description = "Cron expression for the dispatcher pass."
  type        = string
}

variable "time_zone" {
  description = "Time zone the cron expression is read in."
  type        = string
  default     = "Etc/UTC"
}

variable "target_url" {
  description = <<-TEXT
    Absolute URL of the worker's POST /operations/dispatch endpoint.

    No default, and no value committed anywhere in this repository. The worker's
    URL is assigned by Cloud Run at apply time and nothing has been applied, so
    this cannot be filled in from anything known today.
  TEXT
  type        = string
}

variable "caller_identity" {
  description = "Email of the scheduler-scoped service account whose token the job carries."
  type        = string
}

variable "token_audience" {
  description = <<-TEXT
    OIDC audience the minted token is bound to — the worker's own URL.

    No default, and no invented value. Finding S-001 leaves the scheduler
    audience and the service-account allowlist open on purpose, and the A1b
    identity-provider worksheet is unfilled; writing a plausible-looking value
    here would be inventing one. The verifier refuses every delivery until a
    human fills both in, which is the point.
  TEXT
  type        = string
}
