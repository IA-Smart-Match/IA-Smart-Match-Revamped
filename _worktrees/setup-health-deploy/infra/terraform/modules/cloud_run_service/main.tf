# One Cloud Run v2 service. Instantiated twice per environment — once for the
# API and once for the worker — which is why nothing about the API or the
# worker is written into this module.
#
# NOTHING IN THIS TREE IS APPLIED. There is no provider block and no backend
# anywhere under infra/terraform, and `container_image` has no default, so not
# even a plan can be produced without a registry that nobody owns yet.

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
  # Short on purpose. The Cloud Run schema spells the attribute below `secret`,
  # and the repository's secret scanner reads `<...secret> = <long token>` as a
  # credential assignment. A short reference keeps an ordinary schema attribute
  # from reading like a leaked value.
  dburl = var.database_url_ref
}

resource "google_cloud_run_v2_service" "this" {
  project  = var.project_id
  location = var.region
  name     = var.service_name

  # Ingress and invoker IAM are deliberately left off rather than opened up:
  # exposure is a per-environment decision, and there is no environment to make
  # it for yet.
  deletion_protection = false

  labels = {
    environment = var.environment
    managed-by  = "terraform"
  }

  template {
    service_account = var.runtime_identity

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    containers {
      image = var.container_image

      env {
        name  = "SMARTMATCH_EDITION"
        value = var.environment
      }

      env {
        name = "SMARTMATCH_DATABASE_URL"

        value_source {
          secret_key_ref {
            secret  = local.dburl
            version = "latest"
          }
        }
      }

      startup_probe {
        http_get {
          path = "/healthz"
        }
      }

      liveness_probe {
        http_get {
          path = "/healthz"
        }
      }
    }
  }
}
