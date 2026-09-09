variable "project_id" {
  description = "Owning GCP project."
  type        = string
}

variable "region" {
  description = "Region the replica is pinned to."
  type        = string
}

variable "placeholder_ids" {
  description = <<-TEXT
    Names of the Secret Manager entries this environment owns.

    Names only. This module creates the container and never a version, so there
    is no place in this repository for a value to live.
  TEXT
  type        = set(string)
}

variable "environment" {
  description = "Environment label applied to each entry."
  type        = string
}
