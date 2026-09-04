# Secret Manager PLACEHOLDERS — containers, never contents.
#
# This module creates `google_secret_manager_secret` and nothing else. There is
# deliberately no `google_secret_manager_secret_version` here, and there never
# should be: a version carries the value, a value in Terraform is a value in
# state, and state is a file somebody eventually commits by accident. Versions
# are added out of band by whoever holds the credential.
#
# `tools/env_isolation_check.py` asserts that absence rather than trusting this
# paragraph: a `google_secret_manager_secret_version` anywhere under
# infra/terraform fails the build.
#
# Which entries exist is the caller's decision, and it is not uniform. The
# classroom project declares no provider credential at all (architecture v1.1
# §3.3) — not an empty one, not an unused one — so its set is smaller by one.
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

resource "google_secret_manager_secret" "placeholder" {
  for_each = var.placeholder_ids

  project   = var.project_id
  secret_id = each.value

  labels = {
    environment = var.environment
    managed-by  = "terraform"
  }

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}
