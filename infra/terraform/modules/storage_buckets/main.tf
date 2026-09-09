# The two buckets each environment owns. Bucket names are global across all of
# GCP, so two environments naming the same bucket is not merely a policy breach
# — it is a resource one project cannot create because another already did.
# That makes these the sharpest case for the disjointness assertion in
# tools/env_isolation_check.py.
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

locals {
  buckets = {
    evidence = var.evidence_bucket
    artifact = var.artifact_bucket
  }
}

resource "google_storage_bucket" "this" {
  for_each = local.buckets

  project                     = var.project_id
  location                    = var.region
  name                        = each.value
  uniform_bucket_level_access = true
  force_destroy               = false

  versioning {
    enabled = true
  }

  labels = {
    environment = var.environment
    purpose     = each.key
    managed-by  = "terraform"
  }
}
