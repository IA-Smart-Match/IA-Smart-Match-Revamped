# prod environment — configuration only. NOTHING HERE IS APPLIED.
#
# There is no provider block, no backend block, no resource, module, or data
# block in this file, and `tools/env_isolation_check.py` fails the build if one
# appears. That is deliberate: an environment skeleton that can be applied is
# not a skeleton, and this repository has no credentials, no state backend, and
# no deployment path (architecture v1.1 §3.1, Foundation F5).
#
# Every identifier below is a placeholder in the reserved `example` namespace
# (RFC 2606 for the domains). None of them names a real GCP project, bucket,
# service account, database, queue, or secret — and the check asserts that too,
# so a real value cannot be pasted in without the build noticing.
#
# prod is the only environment permitted a data_class other than "synthetic",
# and the check enforces that a non-synthetic data_class requires
# provider_mode = "gated" — live data and ungated providers must not coexist.
# Releases are gated on manual approval (v1.1 §3.2); nothing here performs one.

terraform {
  required_version = ">= 1.6.0"
}

locals {
  # --- Identifiers -------------------------------------------------------
  # Unique to this environment. No identifier may appear in more than one
  # environment (architecture v1.1 §3.2): a shared project, database, queue,
  # bucket, service account, or secret is how one environment reaches
  # another's data. It is invisible in a diagram and catastrophic in practice,
  # so `make infra-check` asserts disjointness rather than trusting review.
  project_id             = "example-smartmatch-prod"
  database_instance      = "example-smartmatch-prod-sql"
  database_name          = "example-smartmatch-prod-core"
  evidence_bucket        = "example-smartmatch-prod-evidence"
  artifact_bucket        = "example-smartmatch-prod-artifacts"
  task_queue             = "example-smartmatch-prod-jobs"
  api_service_account    = "example-smartmatch-prod-api@example.invalid"
  worker_service_account = "example-smartmatch-prod-worker@example.invalid"
  api_service            = "example-smartmatch-prod-api-service"
  worker_service         = "example-smartmatch-prod-worker-service"
  scheduler_job          = "example-smartmatch-prod-dispatch-job"
  database_secret_id     = "example-smartmatch-prod-database-url"
  provider_secret_id     = "example-smartmatch-prod-provider-credentials"
  release_tag_prefix     = "prod-v"

  # --- Settings ----------------------------------------------------------
  # These may legitimately match another environment's value, so they are
  # classified as settings rather than identifiers. The classification lives in
  # tools/env_isolation_check.py, and a key in neither list fails the check —
  # a new identifier cannot be added without deciding which it is.
  environment      = "prod"
  region           = "us-west1"
  provider_mode    = "gated"
  data_class       = "live-pilot"
  min_instances    = 1
  max_instances    = 8
  database_version = "POSTGRES_16"
  database_tier    = "db-custom-1-3840"
  dispatch_cron    = "*/5 * * * *"
  promotion_source = "staging"
}
