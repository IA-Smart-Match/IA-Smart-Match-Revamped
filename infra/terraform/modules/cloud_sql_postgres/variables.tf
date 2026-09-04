variable "project_id" {
  description = "Owning GCP project."
  type        = string
}

variable "region" {
  description = "Cloud SQL region."
  type        = string
}

variable "instance_name" {
  description = "Cloud SQL instance name. Environment-scoped; never a default."
  type        = string
}

variable "database_name" {
  description = "Logical database created on the instance."
  type        = string
}

variable "database_version" {
  description = "PostgreSQL major version. Pinned to 16 by the schema this repository ships."
  type        = string

  validation {
    condition     = startswith(var.database_version, "POSTGRES_16")
    error_message = "Migrations and tests target PostgreSQL 16; another major version is a schema decision, not a variable."
  }
}

variable "tier" {
  description = "Cloud SQL machine tier."
  type        = string
}

variable "environment" {
  description = "Environment label applied to the instance."
  type        = string
}
