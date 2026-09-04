output "service_name" {
  description = "The Cloud Run service name, echoed back for wiring."
  value       = google_cloud_run_v2_service.this.name
}

output "uri" {
  description = "The service URL. Known only after an apply, which has not been run."
  value       = google_cloud_run_v2_service.this.uri
}
