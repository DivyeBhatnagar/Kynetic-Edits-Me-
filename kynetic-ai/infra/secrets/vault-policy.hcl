# ── Kynetic AI — HashiCorp Vault Policy ─────────────────────────────────────
#
# Each microservice gets its own Vault policy with read-only access
# to its secrets path. Services cannot read each other's secrets.
#
# Vault paths follow the pattern: secret/kynetic/{environment}/{service}/*
#
# Usage:
#   vault policy write kynetic-auth infra/secrets/vault-policy.hcl
#   (separate policy files per service in production — this is the template)

# ── Shared secrets readable by ALL services ──────────────────────────────────
path "secret/kynetic/+/shared/*" {
  capabilities = ["read", "list"]
}

# ── Auth Service ─────────────────────────────────────────────────────────────
path "secret/kynetic/+/auth/*" {
  capabilities = ["read"]
}

# ── Wallet/Billing Service ───────────────────────────────────────────────────
path "secret/kynetic/+/billing/*" {
  capabilities = ["read"]
}

# ── Provisioning Service ─────────────────────────────────────────────────────
path "secret/kynetic/+/provisioning/*" {
  capabilities = ["read"]
}

# ── AI Router / Copilot Service ──────────────────────────────────────────────
path "secret/kynetic/+/ai-router/*" {
  capabilities = ["read"]
}

# ── Security Service ─────────────────────────────────────────────────────────
path "secret/kynetic/+/security/*" {
  capabilities = ["read"]
}

# ── Notifications Service ────────────────────────────────────────────────────
path "secret/kynetic/+/notifications/*" {
  capabilities = ["read"]
}

# ── Deny everything else ────────────────────────────────────────────────────
path "*" {
  capabilities = ["deny"]
}
