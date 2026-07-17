data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

data "aws_iam_policy_document" "kms" {
  statement {
    sid    = "EnableAccountIAMPolicies"
    effect = "Allow"
    principals {
      type        = "AWS"
      identifiers = ["arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
    actions   = ["kms:*"]
    resources = ["*"]
  }

  statement {
    sid    = "AllowCloudWatchLogsEncryption"
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["logs.${var.aws_region}.amazonaws.com"]
    }
    actions = [
      "kms:Decrypt",
      "kms:DescribeKey",
      "kms:Encrypt",
      "kms:GenerateDataKey*",
      "kms:ReEncrypt*",
    ]
    resources = ["*"]
    condition {
      test     = "ArnLike"
      variable = "kms:EncryptionContext:aws:logs:arn"
      values   = ["arn:${data.aws_partition.current.partition}:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/batch/${var.project_name}-${var.environment}*"]
    }
  }

  statement {
    sid    = "AllowAutoScalingEncryptedVolumes"
    effect = "Allow"
    principals {
      type = "AWS"
      identifiers = [
        "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:root"
      ]
    }
    actions = [
      "kms:Decrypt",
      "kms:DescribeKey",
      "kms:Encrypt",
      "kms:GenerateDataKey*",
      "kms:ReEncrypt*",
    ]
    resources = ["*"]
    condition {
      test     = "ArnLike"
      variable = "aws:PrincipalArn"
      values = [
        "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:role/aws-service-role/autoscaling.amazonaws.com/AWSServiceRoleForAutoScaling"
      ]
    }
  }

  statement {
    sid    = "AllowAutoScalingGrant"
    effect = "Allow"
    principals {
      type = "AWS"
      identifiers = [
        "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:root"
      ]
    }
    actions   = ["kms:CreateGrant"]
    resources = ["*"]
    condition {
      test     = "Bool"
      variable = "kms:GrantIsForAWSResource"
      values   = ["true"]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:PrincipalArn"
      values = [
        "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:role/aws-service-role/autoscaling.amazonaws.com/AWSServiceRoleForAutoScaling"
      ]
    }
  }
}

locals {
  name        = "${var.project_name}-${var.environment}"
  bucket_name = coalesce(var.bucket_name, "${local.name}-${data.aws_caller_identity.current.account_id}-${var.aws_region}")
  work_prefix = "work/*"
  data_prefixes = [
    "arn:${data.aws_partition.current.partition}:s3:::${local.bucket_name}/inputs/*",
    "arn:${data.aws_partition.current.partition}:s3:::${local.bucket_name}/references/*",
    "arn:${data.aws_partition.current.partition}:s3:::${local.bucket_name}/results/*",
    "arn:${data.aws_partition.current.partition}:s3:::${local.bucket_name}/${local.work_prefix}",
  ]
}

resource "aws_kms_key" "data" {
  description             = "TranscriptForge ${var.environment} S3, ECR, Logs, and EBS encryption"
  deletion_window_in_days = var.kms_deletion_window_days
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.kms.json
}

resource "aws_kms_alias" "data" {
  name          = "alias/${local.name}-data"
  target_key_id = aws_kms_key.data.key_id
}

resource "aws_s3_bucket" "data" {
  bucket        = local.bucket_name
  force_destroy = var.force_destroy
}

resource "aws_s3_bucket_ownership_controls" "data" {
  bucket = aws_s3_bucket.data.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket                  = aws_s3_bucket.data.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "data" {
  bucket = aws_s3_bucket.data.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  bucket = aws_s3_bucket.data.id
  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.data.arn
      sse_algorithm     = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "data" {
  bucket = aws_s3_bucket.data.id

  rule {
    id     = "abort-incomplete-multipart-uploads"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  depends_on = [aws_s3_bucket_versioning.data]
}

data "aws_iam_policy_document" "bucket" {
  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.data.arn,
      "${aws_s3_bucket.data.arn}/*",
    ]
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "data" {
  bucket = aws_s3_bucket.data.id
  policy = data.aws_iam_policy_document.bucket.json
}

resource "aws_ecr_repository" "scientific" {
  name                 = "${local.name}-scientific"
  image_tag_mutability = "IMMUTABLE"

  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = aws_kms_key.data.arn
  }

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "scientific" {
  repository = aws_ecr_repository.scientific.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Expire untagged build layers after 14 days"
      selection = {
        tagStatus   = "untagged"
        countType   = "sinceImagePushed"
        countUnit   = "days"
        countNumber = 14
      }
      action = { type = "expire" }
    }]
  })
}

resource "aws_cloudwatch_log_group" "batch" {
  name              = "/aws/batch/${local.name}"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.data.arn
}

resource "aws_security_group" "batch" {
  name_prefix = "${local.name}-batch-"
  description = "No inbound access; egress for Batch task dependencies"
  vpc_id      = var.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  lifecycle { create_before_destroy = true }
}

data "aws_iam_policy_document" "batch_service_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["batch.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "batch_service" {
  name               = "${local.name}-batch-service"
  assume_role_policy = data.aws_iam_policy_document.batch_service_assume.json
}

resource "aws_iam_role_policy_attachment" "batch_service" {
  role       = aws_iam_role.batch_service.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AWSBatchServiceRole"
}

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "batch_instance" {
  name               = "${local.name}-batch-instance"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

resource "aws_iam_role_policy_attachment" "batch_instance_ecs" {
  role       = aws_iam_role.batch_instance.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role"
}

data "aws_iam_policy_document" "batch_instance_logs" {
  statement {
    sid       = "WriteBatchLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.batch.arn}:*"]
  }
}

resource "aws_iam_role_policy" "batch_instance_logs" {
  name   = "batch-task-logs"
  role   = aws_iam_role.batch_instance.id
  policy = data.aws_iam_policy_document.batch_instance_logs.json
}

resource "aws_iam_instance_profile" "batch" {
  name = "${local.name}-batch-instance"
  role = aws_iam_role.batch_instance.name
}

data "aws_iam_policy_document" "job_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "job" {
  name               = "${local.name}-job"
  assume_role_policy = data.aws_iam_policy_document.job_assume.json
}

data "aws_iam_policy_document" "pipeline_data" {
  statement {
    sid       = "BucketMetadata"
    actions   = ["s3:GetBucketLocation"]
    resources = [aws_s3_bucket.data.arn]
  }
  statement {
    sid       = "ListPipelinePrefixes"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.data.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["inputs/*", "references/*", "results/*", "work/*"]
    }
  }
  statement {
    sid = "PipelineObjects"
    actions = [
      "s3:AbortMultipartUpload",
      "s3:DeleteObject",
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:ListMultipartUploadParts",
      "s3:PutObject",
    ]
    resources = local.data_prefixes
  }
  statement {
    sid = "PipelineEncryption"
    actions = [
      "kms:Decrypt",
      "kms:DescribeKey",
      "kms:Encrypt",
      "kms:GenerateDataKey",
      "kms:ReEncryptFrom",
      "kms:ReEncryptTo",
    ]
    resources = [aws_kms_key.data.arn]
  }
}

resource "aws_iam_role_policy" "job_data" {
  name   = "pipeline-data"
  role   = aws_iam_role.job.id
  policy = data.aws_iam_policy_document.pipeline_data.json
}

data "aws_iam_policy_document" "spot_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["spotfleet.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "spot_fleet" {
  name               = "${local.name}-spot-fleet"
  assume_role_policy = data.aws_iam_policy_document.spot_assume.json
}

resource "aws_iam_role_policy_attachment" "spot_fleet" {
  role       = aws_iam_role.spot_fleet.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AmazonEC2SpotFleetTaggingRole"
}

resource "aws_launch_template" "batch" {
  name_prefix            = "${local.name}-batch-"
  update_default_version = true

  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      delete_on_termination = true
      encrypted             = true
      kms_key_id            = aws_kms_key.data.arn
      volume_size           = var.root_volume_size_gib
      volume_type           = "gp3"
    }
  }

}

resource "aws_batch_compute_environment" "main" {
  name         = local.name
  service_role = aws_iam_role.batch_service.arn
  type         = "MANAGED"
  state        = "ENABLED"

  compute_resources {
    allocation_strategy = var.compute_resource_type == "SPOT" ? "SPOT_CAPACITY_OPTIMIZED" : "BEST_FIT_PROGRESSIVE"
    bid_percentage      = var.compute_resource_type == "SPOT" ? var.spot_bid_percentage : null
    instance_role       = aws_iam_instance_profile.batch.arn
    instance_type       = var.instance_types
    max_vcpus           = var.max_vcpus
    min_vcpus           = 0
    desired_vcpus       = 0
    security_group_ids  = [aws_security_group.batch.id]
    spot_iam_fleet_role = var.compute_resource_type == "SPOT" ? aws_iam_role.spot_fleet.arn : null
    subnets             = sort(tolist(var.subnet_ids))
    type                = var.compute_resource_type

    launch_template {
      launch_template_id = aws_launch_template.batch.id
      version            = aws_launch_template.batch.latest_version
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.batch_service,
    aws_iam_role_policy_attachment.batch_instance_ecs,
    aws_iam_role_policy.batch_instance_logs,
    aws_iam_role_policy_attachment.spot_fleet,
  ]
}

resource "aws_batch_job_queue" "main" {
  name     = local.name
  state    = "ENABLED"
  priority = 10

  compute_environment_order {
    compute_environment = aws_batch_compute_environment.main.arn
    order               = 1
  }
}

data "aws_iam_policy_document" "nextflow_submitter" {
  source_policy_documents = [data.aws_iam_policy_document.pipeline_data.json]

  statement {
    sid = "SubmitPipelineJobs"
    actions = [
      "batch:CancelJob",
      "batch:DeregisterJobDefinition",
      "batch:DescribeJobDefinitions",
      "batch:DescribeJobs",
      "batch:DescribeJobQueues",
      "batch:ListJobs",
      "batch:RegisterJobDefinition",
      "batch:SubmitJob",
      "batch:TerminateJob",
    ]
    resources = ["*"]
  }
  statement {
    sid       = "PassPipelineJobRole"
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.job.arn]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_policy" "nextflow_submitter" {
  name        = "${local.name}-nextflow-submitter"
  description = "Attach to the API/worker role that launches Nextflow; no long-lived keys required."
  policy      = data.aws_iam_policy_document.nextflow_submitter.json
}

resource "aws_budgets_budget" "monthly" {
  name         = "${local.name}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  dynamic "notification" {
    for_each = var.budget_alert_email == null ? [] : [var.budget_alert_email]
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = 80
      threshold_type             = "PERCENTAGE"
      notification_type          = "FORECASTED"
      subscriber_email_addresses = [notification.value]
    }
  }

  dynamic "notification" {
    for_each = var.budget_alert_email == null ? [] : [var.budget_alert_email]
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = 100
      threshold_type             = "PERCENTAGE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = [notification.value]
    }
  }
}
