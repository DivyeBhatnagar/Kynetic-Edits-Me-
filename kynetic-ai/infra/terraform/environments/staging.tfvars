# ── Staging Environment ──────────────────────────────────────────────────────
# Usage: terraform apply -var-file=environments/staging.tfvars

environment = "staging"
aws_region  = "ap-south-1"

# Smaller instances for cost savings
services_node_instance_type = "t3.large"
db_instance_class           = "db.t3.small"
db_storage_gb               = 20
redis_node_type             = "cache.t3.micro"

# NOTE: db_password, cloudflare_zone_id, cloudflare_api_token must be provided
# via environment variables (TF_VAR_*) or a Vault-backed CI/CD pipeline — never in this file.
