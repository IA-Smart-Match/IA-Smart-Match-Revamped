# classroom environment — configuration only. NOTHING HERE IS APPLIED.
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
# classroom is the isolation boundary v1.1 §3.3 exists to hold. Three
# properties are asserted by the check, not merely written here:
#
#   1. `provider_mode` is "fixtures". Always, not "for now".
#   2. `provider_secret_id` is null — no provider credential exists in this
#      project, so there is nothing for a classroom workload to reach for.
#   3. No environment may name classroom as its `promotion_source`, and
#      classroom names none itself. There is no promotion path in either
#      direction; classroom deploys only from classroom-tagged releases,
#      which is what the distinct `release_tag_prefix` records.

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
  project_id             = "example-smartmatch-classroom"
  database_instance      = "example-smartmatch-classroom-sql"
  database_name          = "example-smartmatch-classroom-core"
  evidence_bucket        = "example-smartmatch-classroom-evidence"
  artifact_bucket        = "example-smartmatch-classroom-artifacts"
  task_queue             = "example-smartmatch-classroom-jobs"
  api_service_account    = "example-smartmatch-classroom-api@example.invalid"
  worker_service_account = "example-smartmatch-classroom-worker@example.invalid"
  provider_secret_id     = null
  release_tag_prefix     = "classroom-v"

  # --- Settings ----------------------------------------------------------
  # These may legitimately match another environment's value, so they are
  # classified as settings rather than identifiers. The classification lives in
  # tools/env_isolation_check.py, and a key in neither list fails the check —
  # a new identifier cannot be added without deciding which it is.
  environment      = "classroom"
  region           = "us-west1"
  provider_mode    = "fixtures"
  data_class       = "synthetic"
  min_instances    = 0
  max_instances    = 2
  promotion_source = null
}
