# The job queue the outbox dispatcher hands work to.
#
# The retry settings below match what the worker already assumes rather than
# being invented here: `POST /tasks/execute` is idempotent per job, so a
# redelivery is safe, and the dispatcher reclaims stranded rows on its next
# pass. Retries therefore back off rather than give up quickly.
#
# The queue holds no identity of its own. Who may enqueue, and what identity a
# delivery carries, is the Cloud Tasks OIDC binding in Finding S-001 — still
# open, and deliberately not decided here.
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

resource "google_cloud_tasks_queue" "this" {
  project  = var.project_id
  location = var.region
  name     = var.queue_name

  rate_limits {
    max_dispatches_per_second = 10
    max_concurrent_dispatches = 20
  }

  retry_config {
    max_attempts       = 10
    min_backoff        = "5s"
    max_backoff        = "300s"
    max_doublings      = 4
    max_retry_duration = "3600s"
  }
}
