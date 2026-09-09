output "environment" {
  description = "The environment this instance describes."
  value       = var.environment
}

output "claimed_names" {
  description = <<-TEXT
    Every cloud name this environment claims, sorted.

    Exposed so a future root module can diff two environments' outputs and see
    an empty intersection. A convenience, not the control: the control runs in
    CI without Terraform.
  TEXT
  value       = sort(local.scoped_names)
}

output "api_uri" {
  description = "API service URL. Known only after an apply, which has not been run."
  value       = module.api.uri
}

output "worker_uri" {
  description = "Worker service URL. Known only after an apply, which has not been run."
  value       = module.worker.uri
}
