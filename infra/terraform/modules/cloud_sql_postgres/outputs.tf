output "instance_name" {
  description = "The Cloud SQL instance name."
  value       = google_sql_database_instance.this.name
}

output "database_name" {
  description = "The logical database name."
  value       = google_sql_database.this.name
}

output "connection_name" {
  description = "Instance connection name. Known only after an apply, which has not been run."
  value       = google_sql_database_instance.this.connection_name
}
