variable "project_id" {
  description = "Owning GCP project."
  type        = string
}

variable "region" {
  description = "Bucket location."
  type        = string
}

variable "evidence_bucket" {
  description = "Bucket holding review evidence. Environment-scoped; never a default."
  type        = string
}

variable "artifact_bucket" {
  description = "Bucket holding build and export artifacts. Environment-scoped; never a default."
  type        = string
}

variable "environment" {
  description = "Environment label applied to both buckets."
  type        = string
}
