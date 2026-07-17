output "batch_job_queue" {
  description = "AWS Batch queue consumed by the Nextflow awsbatch profile."
  value       = aws_batch_job_queue.main.name
}

output "batch_job_queue_arn" {
  value = aws_batch_job_queue.main.arn
}

output "batch_job_role_arn" {
  description = "Least-privilege role assigned to Nextflow-created Batch jobs."
  value       = aws_iam_role.job.arn
}

output "batch_log_group" {
  value = aws_cloudwatch_log_group.batch.name
}

output "data_bucket" {
  value = aws_s3_bucket.data.id
}

output "nextflow_work_uri" {
  value = "s3://${aws_s3_bucket.data.id}/work"
}

output "nextflow_results_uri" {
  value = "s3://${aws_s3_bucket.data.id}/results"
}

output "reference_cache_uri" {
  description = "S3 prefix for immutable checksum-keyed reference materializations."
  value       = "s3://${aws_s3_bucket.data.id}/references"
}

output "scientific_ecr_repository" {
  value = aws_ecr_repository.scientific.repository_url
}

output "nextflow_submitter_policy_arn" {
  description = "Attach this policy to the role running the Nextflow head process."
  value       = aws_iam_policy.nextflow_submitter.arn
}

output "aws_region" {
  value = var.aws_region
}
