output "bucket_names" {
  description = "The bucket names created, keyed by purpose."
  value       = { for purpose, bucket in google_storage_bucket.this : purpose => bucket.name }
}
