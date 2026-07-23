"""
Phase 12 — Terraform IaC Root Module
AWS: VPC, EKS Cluster, RDS PostgreSQL, ElastiCache Redis, S3, ECR
"""

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.25"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.12"
    }
  }

  # Remote state — S3 backend (bucket + DynamoDB lock table must be bootstrapped manually)
  backend "s3" {
    bucket         = "kynetic-terraform-state"
    key            = "infra/terraform.tfstate"
    region         = "ap-south-1"     # Mumbai — India-first
    dynamodb_table = "kynetic-tf-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "kynetic-ai"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# ── Data sources ────────────────────────────────────────────────────────────
data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_caller_identity" "current" {}

# ── Locals ──────────────────────────────────────────────────────────────────
locals {
  cluster_name = "kynetic-${var.environment}"
  vpc_cidr     = "10.0.0.0/16"

  private_subnets = [
    "10.0.1.0/24",
    "10.0.2.0/24",
    "10.0.3.0/24",
  ]
  public_subnets = [
    "10.0.101.0/24",
    "10.0.102.0/24",
    "10.0.103.0/24",
  ]
}

# ── VPC ─────────────────────────────────────────────────────────────────────
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "kynetic-vpc-${var.environment}"
  cidr = local.vpc_cidr

  azs             = slice(data.aws_availability_zones.available.names, 0, 3)
  private_subnets = local.private_subnets
  public_subnets  = local.public_subnets

  enable_nat_gateway     = true
  single_nat_gateway     = var.environment != "production"
  enable_dns_hostnames   = true
  enable_dns_support     = true

  # Required for EKS load balancer controller
  public_subnet_tags = {
    "kubernetes.io/cluster/${local.cluster_name}" = "shared"
    "kubernetes.io/role/elb"                      = 1
  }
  private_subnet_tags = {
    "kubernetes.io/cluster/${local.cluster_name}" = "shared"
    "kubernetes.io/role/internal-elb"             = 1
  }
}

# ── EKS Cluster ─────────────────────────────────────────────────────────────
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = local.cluster_name
  cluster_version = "1.29"

  vpc_id                         = module.vpc.vpc_id
  subnet_ids                     = module.vpc.private_subnet_ids
  cluster_endpoint_public_access = true

  # Enable IRSA (IAM Roles for Service Accounts) — used by External Secrets Operator
  enable_irsa = true

  eks_managed_node_groups = {
    # General-purpose nodes for API services
    services = {
      name           = "kynetic-services"
      instance_types = [var.services_node_instance_type]
      min_size       = 2
      max_size       = 20
      desired_size   = var.environment == "production" ? 4 : 2

      block_device_mappings = {
        xvda = {
          device_name = "/dev/xvda"
          ebs = {
            volume_size           = 50
            volume_type           = "gp3"
            delete_on_termination = true
          }
        }
      }
    }

    # Spot instances for Celery workers (cost optimization)
    workers = {
      name           = "kynetic-workers"
      instance_types = ["m5.xlarge", "m5a.xlarge", "m5n.xlarge"]
      capacity_type  = "SPOT"
      min_size       = 2
      max_size       = 30
      desired_size   = var.environment == "production" ? 4 : 2

      labels = {
        role = "worker"
      }

      taints = [{
        key    = "dedicated"
        value  = "worker"
        effect = "NO_SCHEDULE"
      }]
    }
  }
}

# ── RDS PostgreSQL ──────────────────────────────────────────────────────────
resource "aws_db_subnet_group" "main" {
  name       = "kynetic-db-${var.environment}"
  subnet_ids = module.vpc.private_subnet_ids
}

resource "aws_security_group" "rds" {
  name_prefix = "kynetic-rds-${var.environment}-"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [module.eks.node_security_group_id]
    description     = "Allow PostgreSQL from EKS nodes"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_instance" "main" {
  identifier     = "kynetic-${var.environment}"
  engine         = "postgres"
  engine_version = "16.2"
  instance_class = var.db_instance_class

  db_name  = "kynetic"
  username = "kynetic"
  password = var.db_password   # Rotated via Vault after initial provision

  allocated_storage     = var.db_storage_gb
  max_allocated_storage = var.db_storage_gb * 4
  storage_type          = "gp3"
  storage_encrypted     = true

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  # Prod: Multi-AZ standby; staging: single-AZ
  multi_az                = var.environment == "production"
  backup_retention_period = var.environment == "production" ? 14 : 3
  backup_window           = "03:00-04:00"
  maintenance_window      = "sun:05:00-sun:06:00"

  deletion_protection      = var.environment == "production"
  skip_final_snapshot      = var.environment != "production"
  final_snapshot_identifier = var.environment == "production" ? "kynetic-prod-final" : null

  # Enable Performance Insights for prod
  performance_insights_enabled = var.environment == "production"

  lifecycle {
    prevent_destroy = false  # Set true for prod after initial setup
  }
}

# ── ElastiCache Redis ───────────────────────────────────────────────────────
resource "aws_elasticache_subnet_group" "main" {
  name       = "kynetic-redis-${var.environment}"
  subnet_ids = module.vpc.private_subnet_ids
}

resource "aws_security_group" "redis" {
  name_prefix = "kynetic-redis-${var.environment}-"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [module.eks.node_security_group_id]
    description     = "Allow Redis from EKS nodes"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_elasticache_replication_group" "main" {
  replication_group_id = "kynetic-${var.environment}"
  description          = "Kynetic AI Redis — ${var.environment}"

  node_type          = var.redis_node_type
  num_cache_clusters = var.environment == "production" ? 3 : 1
  engine_version     = "7.2"
  port               = 6379

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true

  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.redis.id]

  automatic_failover_enabled = var.environment == "production"

  snapshot_retention_limit = var.environment == "production" ? 7 : 1
  snapshot_window          = "04:00-05:00"
}

# ── S3 Storage — Invoices, Logs, Agent Binaries ─────────────────────────────
resource "aws_s3_bucket" "storage" {
  bucket = "kynetic-storage-${var.environment}-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_versioning" "storage" {
  bucket = aws_s3_bucket.storage.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "storage" {
  bucket = aws_s3_bucket.storage.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "storage" {
  bucket                  = aws_s3_bucket.storage.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "storage" {
  bucket = aws_s3_bucket.storage.id

  rule {
    id     = "transition-old-invoices"
    status = "Enabled"

    filter {
      prefix = "invoices/"
    }

    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = 365
      storage_class = "GLACIER"
    }
  }
}

# ── ECR Repositories — one per service ─────────────────────────────────────
locals {
  services = [
    "api-gateway",
    "auth-service",
    "marketplace-service",
    "wallet-billing-service",
    "provisioning-service",
    "ai-router-copilot-service",
    "reputation-pricing-service",
    "security-service",
    "host-service",
    "notifications-service",
    "monitoring-service",
  ]
}

resource "aws_ecr_repository" "services" {
  for_each = toset(local.services)

  name                 = "kynetic/${each.value}"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true  # Built-in AWS ECR image vulnerability scanning
  }
}

resource "aws_ecr_lifecycle_policy" "services" {
  for_each   = aws_ecr_repository.services
  repository = each.value.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 20 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 20
      }
      action = { type = "expire" }
    }]
  })
}
