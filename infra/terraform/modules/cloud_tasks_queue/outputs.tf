output "queue_name" {
  description = "The Cloud Tasks queue name."
  value       = google_cloud_tasks_queue.this.name
}
