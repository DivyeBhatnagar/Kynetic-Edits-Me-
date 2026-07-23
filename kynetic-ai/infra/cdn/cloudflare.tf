"""
Cloudflare Infrastructure as Code for Kynetic AI CDN Layer

Provides:
  - DNS A records for api.kynetic.ai and app.kynetic.ai
  - WAF rules (block suspicious user-agents, SQLi patterns)
  - DDoS protection mode configuration
  - Page rules for caching optimization
  - Rate limiting at edge (backing up API Gateway rate limits)
"""

terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
  }
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

# ── Data ──────────────────────────────────────────────────────────────────────
data "cloudflare_zone" "kynetic" {
  zone_id = var.cloudflare_zone_id
}

# ── DNS Records ───────────────────────────────────────────────────────────────

# API Gateway — points to AWS ALB/NLB hostname from EKS Ingress
resource "cloudflare_record" "api" {
  zone_id = data.cloudflare_zone.kynetic.zone_id
  name    = "api"
  value   = var.eks_ingress_hostname  # e.g. xyz.ap-south-1.elb.amazonaws.com
  type    = "CNAME"
  proxied = true  # Traffic routes through Cloudflare — DDoS protection + TLS
  ttl     = 1     # Auto when proxied
}

# Frontend App
resource "cloudflare_record" "app" {
  zone_id = data.cloudflare_zone.kynetic.zone_id
  name    = "app"
  value   = var.frontend_hostname
  type    = "CNAME"
  proxied = true
  ttl     = 1
}

# Root domain — redirect to app.kynetic.ai
resource "cloudflare_record" "root" {
  zone_id = data.cloudflare_zone.kynetic.zone_id
  name    = "@"
  value   = var.frontend_hostname
  type    = "CNAME"
  proxied = true
  ttl     = 1
}

# ── WAF Rules ─────────────────────────────────────────────────────────────────

resource "cloudflare_ruleset" "waf" {
  zone_id     = data.cloudflare_zone.kynetic.zone_id
  name        = "Kynetic AI WAF Rules"
  description = "Custom WAF rules for Kynetic AI"
  kind        = "zone"
  phase       = "http_request_firewall_custom"

  rules {
    action      = "block"
    description = "Block obvious SQL injection in query strings"
    enabled     = true
    expression  = <<EOT
      (http.request.uri.query contains "UNION SELECT" or
       http.request.uri.query contains "OR 1=1" or
       http.request.uri.query contains "DROP TABLE" or
       http.request.uri.query contains "INSERT INTO")
    EOT
  }

  rules {
    action      = "block"
    description = "Block suspicious automated user agents"
    enabled     = true
    expression  = <<EOT
      (http.user_agent contains "sqlmap" or
       http.user_agent contains "nikto" or
       http.user_agent contains "masscan" or
       http.user_agent contains "zgrab")
    EOT
  }

  rules {
    action      = "challenge"
    description = "Challenge India IPs with unusual request patterns"
    enabled     = true
    expression  = <<EOT
      (ip.geoip.country eq "IN" and
       http.request.method eq "POST" and
       not http.request.uri.path matches "^/(auth|wallet|billing|instances|notifications)")
    EOT
  }
}

# ── Rate Limiting (Cloudflare Edge) ───────────────────────────────────────────

resource "cloudflare_ruleset" "rate_limit" {
  zone_id     = data.cloudflare_zone.kynetic.zone_id
  name        = "Kynetic AI Edge Rate Limits"
  description = "Edge rate limiting before traffic reaches EKS"
  kind        = "zone"
  phase       = "http_ratelimit"

  rules {
    action      = "block"
    description = "Rate limit API endpoints: 200 requests per 10 seconds per IP"
    enabled     = true
    expression  = <<EOT
      (http.host eq "api.kynetic.ai")
    EOT
    action_parameters {
      response {
        status_code  = 429
        content_type = "application/json"
        content      = "{\"error\": \"Rate limit exceeded. Please slow down.\"}"
      }
    }
    ratelimit {
      characteristics = ["ip.src"]
      period          = 10
      requests_per_period = 200
      mitigation_timeout  = 60
    }
  }

  rules {
    action      = "block"
    description = "Stricter rate limit on auth endpoints: 10 per 60s"
    enabled     = true
    expression  = <<EOT
      (http.host eq "api.kynetic.ai" and
       http.request.uri.path matches "^/auth/(login|signup|phone)")
    EOT
    ratelimit {
      characteristics = ["ip.src"]
      period          = 60
      requests_per_period = 10
      mitigation_timeout  = 300
    }
  }
}

# ── Caching ───────────────────────────────────────────────────────────────────

resource "cloudflare_ruleset" "cache" {
  zone_id     = data.cloudflare_zone.kynetic.zone_id
  name        = "Kynetic AI Cache Rules"
  description = "Cache public API responses at edge"
  kind        = "zone"
  phase       = "http_response_headers_transform"

  rules {
    action      = "rewrite"
    description = "Cache marketplace listings at edge for 60 seconds"
    enabled     = true
    expression  = <<EOT
      (http.request.method eq "GET" and
       http.request.uri.path matches "^/listings" and
       not http.request.uri.path matches "/listings/[^/]+$")
    EOT
    action_parameters {
      headers {
        name      = "Cache-Control"
        operation = "set"
        value     = "public, max-age=60, s-maxage=60"
      }
    }
  }
}

# ── Variables ─────────────────────────────────────────────────────────────────

variable "eks_ingress_hostname" {
  description = "EKS ALB/NLB hostname from the NGINX Ingress Controller service"
  type        = string
}

variable "frontend_hostname" {
  description = "Frontend hosting hostname (Vercel or CloudFront)"
  type        = string
}
