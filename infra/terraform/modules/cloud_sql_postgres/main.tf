# The single system of record: one Cloud SQL PostgreSQL 16 instance and one
# logical database on it, per environment.
#
# What this module deliberately does NOT declare:
#
#   * No `google_sql_user`. A user resource carries a password, and a password
#     in Terraform is a password in state. The application's credential lives in
#     a Secret Manager placeholder (see ../secret_placeholders) whose value is
#     supplied out of band and never by this repository.
#   * No authorized network and no public address. Access is over the Cloud SQL
#     connector from Cloud Run; opening an address range is a decision nobody
#     has made, for an environment that does not exist.
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

resource "google_sql_database_instance" "this" {
  project          = var.project_id
  region           = var.region
  name             = var.instance_name
  database_version = var.database_version

  # Left on. A synthetic classroom database is still a database somebody is
  # demonstrating against, and an accidental destroy mid-demo is the failure
  # this flag exists for. Turning it off is a deliberate act, not a default.
  deletion_protection = true

  settings {
    tier              = var.tier
    availability_type = "ZONAL"
    disk_autoresize   = true

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
    }

    ip_configuration {
      ipv4_enabled = false
    }

    user_labels = {
      environment = var.environment
      managed-by  = "terraform"
    }
  }
}

resource "google_sql_database" "this" {
  project  = var.project_id
  instance = google_sql_database_instance.this.name
  name     = var.database_name
}
