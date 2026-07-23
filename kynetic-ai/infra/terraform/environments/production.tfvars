# ── Production Environment ───────────────────────────────────────────────────
# Usage: terraform apply -var-file=environments/production.tfvars

environment = "production"
aws_region  = "ap-south-1"

# Production-grade instances
services_node_instance_type = "t3.xlarge"
db_instance_class           = "db.r6g.large"   # Graviton2 — better price/perf
db_storage_gb               = 100
redis_node_type             = "cache.r6g.large"

# NOTE: db_password, cloudflare_zone_id, cloudflare_api_token must be provided
# via environment variables (TF_VAR_*) or a Vault-backed CI/CD pipeline — NEVER in this file.
# db.r6g.large with Multi-AZ = ~$220/month; cache.r6g.large with 3 replicas = ~$180/month
