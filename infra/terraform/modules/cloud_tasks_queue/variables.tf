variable "project_id" {
  description = "Owning GCP project."
  type        = string
}

variable "region" {
  description = "Cloud Tasks location."
  type        = string
}

variable "queue_name" {
  description = "Cloud Tasks queue name. Environment-scoped; never a default."
  type        = string
}
