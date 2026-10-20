output "bucket_name" {
  value = aws_s3_bucket.audience.bucket
}

output "bucket_arn" {
  value = aws_s3_bucket.audience.arn
}

output "s3_prefix" {
  value = var.s3_prefix
}

output "runtime_access_policy_json" {
  description = "Least-privilege policy document to attach to the service's AWS identity."
  value       = data.aws_iam_policy_document.runtime_access.json
}
