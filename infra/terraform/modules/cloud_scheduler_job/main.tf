# The scheduled dispatcher pass (J8/J9).
#
# The deploy runbook's handoff section describes exactly this job: an HTTP job
# that POSTs to the worker's /operations/dispatch at a fixed interval carrying a
# scheduler-scoped OIDC identity, separate from the Cloud Tasks identity. This
# module is that description turned into configuration — and no further. It does
# not create the service account, does not grant it anything, and does not
# invent an audience.
#
# Two of its inputs, `target_url` and `token_audience`, have no default and no
# discoverable value, because the worker has never been deployed. That is the
# apply gate stated as a plan that cannot be produced, rather than as a comment
# asking people not to produce one.
#
# Nothing here is applied.

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

resource "google_cloud_scheduler_job" "this" {
  project   = var.project_id
  region    = var.region
  name      = var.job_name
  schedule  = var.schedule
  time_zone = var.time_zone

  description = "Scheduled outbox dispatcher pass; see docs/operations/deploy-runbook.md."

  # A pass that overruns its interval must not have a second pass stacked on top
  # of it: the dispatcher takes row leases, and a retry storm turns a slow pass
  # into contention. One attempt, and the absence alert catches a miss.
  attempt_deadline = "320s"

  retry_config {
    retry_count = 0
  }

  http_target {
    http_method = "POST"
    uri         = var.target_url

    oidc_token {
      service_account_email = var.caller_identity
      audience              = var.token_audience
    }
  }
}
