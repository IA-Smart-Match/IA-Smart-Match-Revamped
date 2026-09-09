output "placeholder_names" {
  description = "Names of the entries created. Names only — no version is ever created here."
  value       = sort([for entry in google_secret_manager_secret.placeholder : entry.secret_id])
}
