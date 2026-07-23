# ── Kynetic AI — Terraform Variables ────────────────────────────────────────

variable "environment" {
  description = "Deployment environment: dev | staging | production"
  type        = string
  validation {
    condition     = contains(["dev", "staging", "production"], var.environment)
    error_message = "Environment must be one of: dev, staging, production."
  }
}

variable "aws_region" {
  description = "AWS region (default: ap-south-1 India-first)"
  type        = string
  default     = "ap-south-1"
}

variable "services_node_instance_type" {
  description = "EC2 instance type for EKS service nodes"
  type        = string
  default     = "t3.xlarge"
}

variable "db_instance_class" {
  description = "RDS PostgreSQL instance class"
  type        = string
  default     = "db.t3.medium"
}

variable "db_storage_gb" {
  description = "Allocated RDS storage in GB"
  type        = number
  default     = 50
}

variable "db_password" {
  description = "Initial RDS master password — should be rotated via Vault immediately after creation"
  type        = string
  sensitive   = true
}

variable "redis_node_type" {
  description = "ElastiCache Redis node type"
  type        = string
  default     = "cache.t3.medium"
}

variable "cloudflare_zone_id" {
  description = "Cloudflare zone ID for kynetic.ai"
  type        = string
  sensitive   = true
}

variable "cloudflare_api_token" {
  description = "Cloudflare API token with DNS + WAF permissions"
  type        = string
  sensitive   = true
}
