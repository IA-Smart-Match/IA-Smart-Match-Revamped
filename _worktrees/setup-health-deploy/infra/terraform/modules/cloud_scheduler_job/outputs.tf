output "job_name" {
  description = "The Cloud Scheduler job name."
  value       = google_cloud_scheduler_job.this.name
}
