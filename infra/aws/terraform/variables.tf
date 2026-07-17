variable "aws_region" {
  description = "AWS Region for all TranscriptForge resources."
  type        = string
}

variable "project_name" {
  description = "Lowercase prefix used in resource names."
  type        = string
  default     = "transcriptforge"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,30}$", var.project_name))
    error_message = "project_name must be 3-31 lowercase letters, digits, or hyphens."
  }
}

variable "environment" {
  description = "Deployment environment label."
  type        = string
  default     = "portfolio"
}

variable "vpc_id" {
  description = "Existing VPC containing the Batch compute subnets."
  type        = string
}

variable "subnet_ids" {
  description = "Existing private subnet IDs with NAT or VPC endpoints for ECR, S3, Logs, and Batch. Use one subnet per Availability Zone."
  type        = set(string)

  validation {
    condition     = length(var.subnet_ids) > 0
    error_message = "At least one Batch subnet is required."
  }
}

variable "bucket_name" {
  description = "Globally unique S3 bucket name. Null derives an account/region-scoped name."
  type        = string
  default     = null
  nullable    = true
}

variable "force_destroy" {
  description = "Permit Terraform to delete a non-empty data bucket. Keep false outside disposable sandboxes."
  type        = bool
  default     = false
}

variable "compute_resource_type" {
  description = "EC2 for predictable execution or SPOT for lower cost with interruption retries."
  type        = string
  default     = "SPOT"

  validation {
    condition     = contains(["EC2", "SPOT"], var.compute_resource_type)
    error_message = "compute_resource_type must be EC2 or SPOT."
  }
}

variable "instance_types" {
  description = "AWS Batch-compatible instance types or the special value optimal."
  type        = list(string)
  default     = ["optimal"]
}

variable "max_vcpus" {
  description = "Hard Batch compute-environment vCPU ceiling; minimum and desired capacity remain zero."
  type        = number
  default     = 32

  validation {
    condition     = var.max_vcpus >= 1 && var.max_vcpus <= 256
    error_message = "max_vcpus must be between 1 and 256."
  }
}

variable "spot_bid_percentage" {
  description = "Maximum Spot price as a percentage of On-Demand."
  type        = number
  default     = 100
}

variable "root_volume_size_gib" {
  description = "Encrypted gp3 root volume size for Batch compute instances."
  type        = number
  default     = 100
}

variable "log_retention_days" {
  description = "CloudWatch Batch log retention."
  type        = number
  default     = 30
}

variable "kms_deletion_window_days" {
  description = "Delay before a destroyed KMS key is deleted."
  type        = number
  default     = 30
}

variable "monthly_budget_usd" {
  description = "Informational monthly AWS cost budget; this sends no notification unless budget_alert_email is set."
  type        = number
  default     = 50
}

variable "budget_alert_email" {
  description = "Optional address notified at 80 percent forecast and 100 percent actual spend."
  type        = string
  default     = null
  nullable    = true
}

variable "tags" {
  description = "Additional resource tags."
  type        = map(string)
  default     = {}
}
