# Kynetic AI — Compute-First, AI-Native Marketplace

[![Build Status](https://img.shields.io/badge/build-passing-brightgreen.svg)](#)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](#)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109%2B-009688.svg)](#)
[![Next.js](https://img.shields.io/badge/Next.js-14-black.svg)](#)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](#)

**Kynetic AI** is a compute-first, AI-native marketplace connecting two sides:
- **Hosts**: Anyone with idle compute (GPUs, CPUs, RAM, NVMe storage, or full workstations/gaming PCs/enterprise servers) who wants to monetize their hardware.
- **Developers**: Anyone needing compute for AI/ML workloads (fine-tuning, training, inference, 3D rendering, agent hosting) without managing infrastructure.

Unlike legacy GPU-only marketplaces (RunPod, Vast.ai, Lambda), Kynetic AI treats **all compute resources as a single resource-agnostic inventory**, replaces manual hardware selection with an **intent-based AI Resource Router & Copilot**, guarantees **zero-setup 1-click app launches**, and provides **India-first billing (UPI + GST invoicing)** alongside global Stripe support.

> 📖 **New Developer?** Read [DEVELOPMENT.md](file:///Users/divyebhatnagar/Desktop/KyneticSoftware/kynetic-ai/DEVELOPMENT.md) for step-by-step setup, cloning, local microservice execution, database migration, and editing instructions.

---

## Table of Contents

1. [Executive Summary & Core Philosophy](#executive-summary--core-philosophy)
2. [Reference Architecture](#reference-architecture)
3. [Monorepo Directory Structure](#monorepo-directory-structure)
4. [Technology Stack](#technology-stack)
5. [Implementation Plan Exhaustive Deep-Dive (Phases 1 – 10)](#implementation-plan-exhaustive-deep-dive-phases-1--10)
   - [Phase 1: Foundations & Core Platform Skeleton](#phase-1-foundations--core-platform-skeleton)
   - [Phase 2: Host Onboarding, Hardware Verification & Benchmarking](#phase-2-host-onboarding-hardware-verification--benchmarking)
   - [Phase 3: Compute-First Marketplace & Wallet/Billing Core](#phase-3-compute-first-marketplace--walletbilling-core)
   - [Phase 4: Provisioning, Scheduling & Instance Lifecycle](#phase-4-provisioning-scheduling--instance-lifecycle)
   - [Phase 5: Security Hardening & Zero-Trust Safeguards](#phase-5-security-hardening--zero-trust-safeguards)
   - [Phase 6: Zero-Setup App Templates & AI-Native Entry Point](#phase-6-zero-setup-app-templates--ai-native-entry-point)
   - [Phase 7: AI Resource Router & AI Copilot](#phase-7-ai-resource-router--ai-copilot)
   - [Phase 8: Host Experience, Auto-Pricing & Reputation Layer](#phase-8-host-experience-auto-pricing--reputation-layer)
   - [Phase 9: External Marketplace Listings & Transparent Fallbacks](#phase-9-external-marketplace-listings--transparent-fallbacks)
   - [Phase 10: India-First Regional Billing, Unified Monitoring & Dashboard](#phase-10-india-first-regional-billing-unified-monitoring--dashboard)
6. [Launch Readiness: What Remains to be Built for Commercial MVP](#launch-readiness-what-remains-to-be-built-for-commercial-mvp)
7. [Local Development & Operations Summary](#local-development--operations-summary)
8. [Test Suite & Verification](#test-suite--verification)

---

## Executive Summary & Core Philosophy

### Core Differentiators
1. **Resource-Agnostic Inventory**: Compute is listed and bundled as GPU + CPU + RAM + Storage, supporting CPU-bound and balanced workloads alongside GPU-heavy tasks.
2. **Intent-Based Entry Point**: Developers express *"What do you want to run?"* (e.g., Fine-tune Llama 3, Run ComfyUI, Train YOLO) rather than manually picking GPU models.
3. **Zero-Trust Compute Isolation**: MicroVM (Firecracker) + container double-isolation ensures workload sandboxing, zero host filesystem access, ephemeral NVMe volumes, and cryptographic erasure upon termination.
4. **Transparent Marketplace Fallbacks**: When local inventory cannot fulfill a request (e.g., no RTX 4090 available), Kynetic provides transparent fallback recommendations to external providers (RunPod, Vast.ai, Lambda, Crusoe) rather than silent bursting, fostering developer trust.
5. **India-First Regional Layer**: Full native support for UPI payments via Razorpay, sequential GST-compliant invoices (`KYN/2024-25/000001`), dual currency (INR/USD), and regional support routing.

---

## Reference Architecture

```
                    ┌────────────────────────────────────────────────────────┐
                    │       Next.js + TypeScript + Tailwind Frontend         │
                    └───────────────────────────┬────────────────────────────┘
                                                │ HTTPS / REST / WebSockets
                                                ▼
                    ┌────────────────────────────────────────────────────────┐
                    │               FastAPI API Gateway (:8000)              │
                    │        (JWT Validation, Token-Bucket Rate Limiting)    │
                    └───────────────────────────┬────────────────────────────┘
                                                │ Internal REST / gRPC / mTLS
        ┌───────────────────┬───────────────────┼───────────────────┬───────────────────┐
        ▼                   ▼                   ▼                   ▼                   ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ Auth Service │    │ Marketplace  │    │  Provisioning│    │ Wallet &     │    │  AI Router   │
│   (:8001)    │    │   (:8002)    │    │   (:8003)    │    │ Billing      │    │  & Copilot   │
└──────────────┘    └──────────────┘    └───────┬──────┘    │   (:8004)    │    │   (:8005)    │
                                                │           └──────────────┘    └──────────────┘
                                                ▼
                                    ┌──────────────────────┐
                                    │ Host Agent (mTLS)    │
                                    │ - Firecracker MicroVM│
                                    │ - Ephemeral NVMe     │
                                    │ - WireGuard NAT Relay│
                                    └──────────────────────┘
        ┌───────────────────┬───────────────────┼───────────────────┐
        ▼                   ▼                   ▼                   ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ Reputation & │    │  Security    │    │Notifications │    │  Monitoring  │
│ Pricing      │    │  Service     │    │  Service     │    │  Service     │
│   (:8006)    │    │   (:8007)    │    │   (:8010)    │    │   (:8011)    │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘

Data Infrastructure:
- PostgreSQL (SQLAlchemy 2.0 Async + Alembic Migrations)
- Redis (Session Cache + Rate Limiting + Celery Message Broker)
- Prometheus & Grafana (Platform Metrics & Telemetry)
```

---

## Monorepo Directory Structure

```
kynetic-ai/
├── apps/
│   └── frontend/                  # Next.js 14, TypeScript, Tailwind CSS
├── services/
│   ├── api_gateway/               # Reverse proxy, rate-limiting token bucket, JWT check
│   ├── auth_service/              # User auth, passlib hashing, JWT rotation, phone OTP
│   ├── marketplace_service/       # Listing management, hardware search, scheduler
│   ├── provisioning_service/      # Instance orchestration, Firecracker VM/Docker control
│   ├── wallet_billing_service/    # Wallet transactions, Stripe & Razorpay SDKs, GST engine
│   ├── ai_router_copilot_service/ # LangChain intent parser, ranking engine, WS copilot chat
│   ├── reputation_pricing_service/# scikit-learn auto-pricing, 6-factor reputation engine
│   ├── security_service/          # Image malware scanner, cryptomining detector, kill switch
│   ├── host_service/              # Host hardware registration & heartbeat ingest
│   ├── notifications_service/     # Event notification worker & email dispatcher
│   └── monitoring_service/        # Prometheus client metrics scrape & health engine
├── host_agent/                    # Python PyInstaller agent, pynvml/psutil hardware probe
├── libs/
│   ├── db_models/                 # Shared SQLAlchemy models & Alembic migrations
│   ├── schemas/                   # Pydantic schemas for request/response validation
│   └── common/                    # structlog logger, httpx async client wrapper, settings
├── infra/
│   ├── terraform/                 # IaC configs
│   ├── k8s/                       # Kubernetes deployment manifests
│   ├── docker-compose.yml         # Local microservice orchestration
│   ├── docker-compose.monitoring.yml # Prometheus + Grafana stack
│   └── prometheus.yml             # Prometheus scraping targets
├── tests/                         # Pytest test suites (41 passing unit/integration tests)
├── .github/workflows/             # GitHub Actions CI/CD pipelines
├── alembic.ini                    # Alembic migration configuration
└── pyproject.toml                 # Root Python project dependencies
```

---

## Technology Stack

| Layer | Technology Used |
|---|---|
| **Backend Framework** | FastAPI (ASGI, Async Python 3.11+) |
| **Server Engine** | Uvicorn / Gunicorn |
| **ORM & Database** | SQLAlchemy 2.0 (Async Engine) + PostgreSQL + Alembic |
| **Caching & Messaging** | Redis 7+ (Session Store, Rate Limiting, Celery Broker) |
| **Task Queue** | Celery + APScheduler |
| **Host Agent** | Python (PyInstaller binary), `psutil`, `pynvml` / `GPUtil` |
| **Benchmarking** | PyTorch micro-benchmarks (FLOPs, LLM tok/s, SD step latency) |
| **Machine Learning** | `scikit-learn` + `pandas` (Auto-pricing regression & idle prediction) |
| **AI Router & Copilot** | LangChain + OpenAI/Anthropic APIs + WebSockets |
| **Isolation & Virtualization** | Docker + Firecracker MicroVMs + WireGuard NAT Relays |
| **Payments & Billing** | Stripe SDK (Global), Razorpay SDK (India UPI), 18% GST Engine |
| **Telemetry & Logs** | `prometheus-client`, Grafana, `structlog` |
| **Frontend UI** | Next.js 14 (App Router), TypeScript, Tailwind CSS, Lucide Icons |
| **Testing & CI/CD** | `pytest`, `pytest-asyncio`, `httpx`, GitHub Actions |

---

## Implementation Plan Exhaustive Deep-Dive (Phases 1 – 10)

### Phase 1: Foundations & Core Platform Skeleton
- **Objective**: Stand up the core async microservices chassis, database ORM layer, authentication engine, and CI/CD pipelines.
- **Key Modules & Files**:
  - `services/api_gateway/`: FastAPI gateway application with `httpx` async proxying, token-bucket Redis rate limiting, and centralized JWT validation.
  - `services/auth_service/`: Auth microservice handling user management, password hashing via `passlib[bcrypt]`, JWT token issuance/rotation via `python-jose`, and SMS OTP generation stubs.
  - `libs/db_models/`: SQLAlchemy 2.0 async models (`users`, `sessions`, `audit_logs`).
  - `libs/common/`: Global `structlog` configuration for structured JSON logging with correlation IDs.
- **Database Tables**:
  - `users` (`id`, `email`, `hashed_password`, `role[host|developer|both]`, `phone_number`, `phone_verified`, `created_at`)
  - `sessions` (`id`, `user_id`, `refresh_token`, `expires_at`)
  - `audit_logs` (`id`, `actor_id`, `action`, `resource_type`, `resource_id`, `metadata`, `created_at`) — append-only, immutable audit trail.
- **API Surface**:
  - `POST /auth/signup`
  - `POST /auth/login`
  - `POST /auth/refresh`
  - `POST /auth/logout`
  - `GET /auth/me`
  - `POST /auth/phone/send-otp`
  - `POST /auth/phone/verify-otp`

---

### Phase 2: Host Onboarding, Hardware Verification & Benchmarking
- **Objective**: Package an automated host probe binary to detect hardware, cross-check specs against spoofing, run PyTorch benchmarks, and ingest real-time heartbeats.
- **Key Modules & Files**:
  - `host_agent/`: PyInstaller-packaged Python binary running `psutil` (CPU cores, RAM, NVMe capacity) and `pynvml`/`GPUtil` (GPU model, VRAM, temp, power draw).
  - `services/host_service/`: Backend API ingesting agent registrations over mTLS and heartbeats every 10 seconds.
  - `host_agent/benchmark_runner.py`: PyTorch-based hardware benchmark suite measuring LLM inference tokens/sec, Stable Diffusion step latency, and matrix-multiplication TFLOPs.
- **Database Tables**:
  - `hosts` (`id`, `user_id`, `status[pending_verification|benchmarking|verified|flagged|suspended]`, `os_type`, `agent_version`, `mtls_cert_fingerprint`, `created_at`)
  - `host_hardware_specs` (`host_id`, `cpu_cores`, `ram_gb`, `disk_type`, `disk_gb`, `gpu_model`, `gpu_vram_gb`, `driver_version`, `reported_at`)
  - `host_benchmarks` (`id`, `host_id`, `benchmark_type`, `score`, `raw_metrics`, `run_at`)
  - `host_heartbeats` (`host_id`, `status[idle|busy|offline]`, `temperature_c`, `power_draw_w`, `recorded_at`)
- **API Surface**:
  - `POST /hosts/register`
  - `POST /hosts/heartbeat`
  - `GET /hosts/{id}`
  - `GET /hosts/{id}/benchmarks`
  - `POST /hosts/{id}/benchmarks/rerun`

---

### Phase 3: Compute-First Marketplace & Wallet/Billing Core
- **Objective**: Create a resource-agnostic listing engine and a dual-currency usage-metered wallet system with Stripe integration.
- **Key Modules & Files**:
  - `services/marketplace_service/`: Inventory management treating compute as bundled GPU + CPU + RAM + Storage.
  - `services/wallet_billing_service/`: Developer wallet accounting, per-second usage metering pipelines, Stripe SDK integration, and Stripe Connect host payouts.
- **Database Tables**:
  - `listings` (`id`, `host_id`, `resource_type[gpu|cpu|ram|nvme|workstation_bundle]`, `gpu_model`, `cpu_cores`, `ram_gb`, `storage_gb`, `price_per_hour_usd`, `price_per_hour_inr`, `status`, `region`, `created_at`)
  - `wallets` (`id`, `user_id`, `balance_usd`, `balance_inr`, `preferred_currency`, `created_at`)
  - `wallet_transactions` (`id`, `wallet_id`, `type[topup|debit|refund|payout]`, `amount`, `currency`, `reference_id`, `created_at`)
  - `stripe_accounts` (`user_id`, `stripe_customer_id`, `stripe_connect_account_id`)
- **API Surface**:
  - `POST /listings` | `GET /listings` | `GET /listings/{id}` | `PATCH /listings/{id}` | `DELETE /listings/{id}`
  - `GET /wallet/balance` | `GET /wallet/transactions` | `POST /wallet/topup`
  - `POST /billing/webhooks/stripe`

---

### Phase 4: Provisioning, Scheduling & Instance Lifecycle
- **Objective**: Orchestrate isolated compute instances with ephemeral NVMe storage, WireGuard NAT relays, short-lived SSH keys, and cryptographic deletion receipts.
- **Key Modules & Files**:
  - `services/provisioning_service/`: Celery task orchestration for instance deployment, start, stop, and teardown.
  - Host Firecracker MicroVM & Docker Control Engine: Double-isolated workload execution blocking host OS filesystem access.
  - Ephemeral SSH & WireGuard Relay: Automated SSH key generation and encrypted NAT traversal for non-public IP hosts.
- **Database Tables**:
  - `instances` (`id`, `developer_id`, `listing_id`, `host_id`, `status[pending|provisioning|running|stopping|terminated|failed]`, `ssh_key_id`, `started_at`, `stopped_at`, `billed_seconds`, `hold_amount`, `currency`)
  - `ssh_sessions` (`id`, `instance_id`, `public_key`, `private_key_encrypted`, `issued_at`, `rotated_at`, `revoked_at`)
  - `secure_deletion_receipts` (`instance_id`, `verified_at`, `method`)
- **API Surface**:
  - `POST /instances`
  - `GET /instances/{id}`
  - `POST /instances/{id}/start` | `POST /instances/{id}/stop` | `POST /instances/{id}/terminate`
  - `GET /instances/{id}/connection`

---

### Phase 5: Security Hardening & Zero-Trust Safeguards
- **Objective**: Implement container malware scanning, real-time cryptomining signature detection, API rate limiting, trust tier limits, and an emergency admin kill switch.
- **Key Modules & Files**:
  - `services/security_service/`: Image malware scanning pipeline, runtime cryptomining signature detection, and multi-account fingerprinting.
  - Gateway Rate Limiter: Redis-backed token bucket protecting public API routes.
  - Admin Kill Switch: Instant workload termination and account suspension protocol.
- **Database Tables**:
  - `device_fingerprints` (`user_id`, `fingerprint_hash`, `first_seen`, `last_seen`)
  - `trust_tiers` (`user_id`, `tier`, `instance_size_cap`, `gpu_hour_cap`, `spend_cap`, `updated_at`)
  - `security_event_logs` (`id`, `event_type`, `severity`, `resource_type`, `resource_id`, `details`, `created_at`)
  - `kill_switch_events` (`id`, `target_type[instance|host|account]`, `target_id`, `triggered_by`, `reason`, `triggered_at`)
- **API Surface**:
  - `POST /admin/kill-switch`
  - `GET /admin/security-events`
  - `POST /identity/verify/id-document`
  - `GET /users/{id}/trust-tier`

---

### Phase 6: Zero-Setup App Templates & AI-Native Entry Point
- **Objective**: Deliver 1-click execution for popular AI workloads (Stable Diffusion, Ollama, ComfyUI, Llama 3) with secure web UI routing.
- **Key Modules & Files**:
  - `services/provisioning_service/templates.py`: Pre-scanned, verified template registry.
  - WireGuard HTTP Proxy Relay: Exposes container web UIs (e.g. ComfyUI) securely over encrypted tunnels.
  - Frontend Intent Launcher: Landing screen asking *"What do you want to run?"*.
- **Database Tables**:
  - `templates` (`id`, `name`, `base_image`, `required_gpu_vram_gb`, `required_ram_gb`, `startup_command`, `exposed_web_ui_path`, `status[pending_scan|available|disabled]`, `created_at`)
- **API Surface**:
  - `GET /templates` | `POST /templates` (admin)
  - `POST /instances` (extended with `template_id`)
  - `GET /instances/{id}/web-ui`

---

### Phase 7: AI Resource Router & AI Copilot
- **Objective**: Build a grounded budget/speed ranking engine and a conversational WebSocket assistant.
- **Key Modules & Files**:
  - `services/ai_router_copilot_service/router.py`: Rule-based weighted scoring engine taking price, benchmarks, availability, and reputation to recommend machine candidates.
  - `services/ai_router_copilot_service/copilot.py`: LangChain-powered conversational agent operating over WebSockets, transforming free-text requirements into grounded recommendations with cost/time estimations.
- **Database Tables**:
  - `router_recommendations` (`id`, `developer_id`, `request_payload`, `recommended_listing_ids`, `created_at`)
  - `copilot_sessions` (`id`, `developer_id`, `created_at`)
  - `copilot_messages` (`id`, `session_id`, `role[user|assistant]`, `content`, `created_at`)
- **API Surface**:
  - `POST /router/recommend`
  - `POST /copilot/chat` (WebSocket)
  - `GET /copilot/sessions/{id}/history`

---

### Phase 8: Host Experience, Auto-Pricing & Reputation Layer
- **Objective**: Automate host pricing with machine learning models and score hosts transparently across 6 performance metrics.
- **Key Modules & Files**:
  - `services/reputation_pricing_service/auto_pricing.py`: `scikit-learn` regression model suggesting hourly pricing based on hardware class and market utilization.
  - `services/reputation_pricing_service/reputation.py`: 6-factor composite score calculation (uptime, latency, network quality, job success rate, benchmark score, responsiveness).
  - Host Analytics Engine: Electricity cost calculator and monthly idle-time revenue projections.
- **Database Tables**:
  - `reputation_scores` (`id`, `host_id`, `uptime_score`, `latency_score`, `network_score`, `job_success_rate`, `benchmark_score`, `response_time_score`, `composite_score`, `computed_at`)
  - `pricing_suggestions` (`id`, `listing_id`, `suggested_price_usd`, `suggested_price_inr`, `accepted`, `created_at`)
  - `idle_predictions` (`host_id`, `predicted_idle_hours_per_day`, `income_projection_monthly`, `computed_at`)
- **API Surface**:
  - `GET /hosts/{id}/dashboard`
  - `GET /hosts/{id}/reputation`
  - `GET /pricing/suggest?listing_id=...`

---

### Phase 9: External Marketplace Listings & Transparent Fallbacks
- **Objective**: Provide transparent alternative recommendations to external cloud providers when local supply is unavailable.
- **Key Modules & Files**:
  - `apps/frontend/app/marketplace/page.tsx`: Detects zero search results on GPU model filters and renders a *"No {GPU} currently available"* card.
  - `apps/frontend/components/RecommendationResults.tsx`: Displays fallback provider recommendations (RunPod, Vast.ai, Lambda, Crusoe).
- **Security Controls**:
  - All external provider links enforce `rel="noopener noreferrer"` to prevent tab-nabbing attacks.
- **API Surface**: Purely frontend presentation tier.

---

### Phase 10: India-First Regional Billing, Unified Monitoring & Dashboard
- **Objective**: Complete the regional India billing stack, unified Prometheus observability, and developer dashboard.
- **Key Modules & Files**:
  - `services/wallet_billing_service/razorpay_client.py`: `RazorpayClient` with mock-mode support for INR UPI top-ups and payouts.
  - `services/wallet_billing_service/invoice.py`: Sequential Indian fiscal year invoice generator (`KYN/2024-25/000001`) calculating 18% inclusive GST via row-level locking (`SELECT FOR UPDATE`).
  - `services/notifications_service/`: Microservice on port 8010 handling event-driven emails (low balance, instance lifecycle, GST invoice ready, payouts).
  - `services/monitoring_service/`: Microservice on port 8011 exposing `/monitoring/metrics` for Prometheus and Grafana dashboards.
  - `apps/frontend/app/dashboard/page.tsx`: Tabbed frontend interface for Billing History, GST Invoices, and Regional Support Tickets.
- **Database Tables**:
  - `invoices` (`id`, `transaction_id`, `gstin`, `invoice_number`, `pdf_url`, `issued_at`)
  - `invoice_sequences` (`fiscal_year`, `last_sequence`) — atomic sequence counter with row locking.
  - `notifications` (`id`, `user_id`, `type`, `channel`, `payload`, `sent_at`, `read_at`)
  - `notification_preferences` (`user_id`, `email_enabled`, `sms_enabled`, `low_balance_threshold`)
  - `support_tickets` (`id`, `user_id`, `region[india|global]`, `subject`, `status`, `created_at`)
- **API Surface**:
  - `POST /wallet/topup/upi`
  - `POST /billing/webhooks/razorpay`
  - `GET /billing/invoices/{id}` | `GET /billing/invoices`
  - `GET /notifications` | `POST /notifications/{id}/read` | `POST /notifications/mark-all-read`
  - `GET /notifications/preferences` | `PUT /notifications/preferences`
  - `POST /support/tickets` | `GET /support/tickets`
  - `GET /monitoring/metrics` (Prometheus scrape endpoint)

---

## Launch Readiness: What Remains to be Built for Commercial MVP

While the entire core platform logic (Phases 1 through 10) is fully implemented and tested with mock modes, the following **production enablement tasks** are required before launching to live paying customers:

### 1. Payment Gateway Live Production Credentials
- **Razorpay**: Switch `mock_mode=True` to `False` in `services/wallet_billing_service/config.py` and supply live `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET`. Verify live Webhook HMAC signatures.
- **Stripe**: Replace test-mode API keys with live Publishable and Secret keys. Configure live Stripe Connect webhook endpoints.

### 2. Real PDF Invoice Generation & S3 Storage
- **Current State**: `generate_invoice_pdf` task generates an S3 stub URL (`https://storage.kynetic.ai/invoices/...`).
- **Production Need**: Integrate `ReportLab` or `WeasyPrint` to render formal PDF documents containing Kynetic AI's corporate GSTIN, line-item breakdowns, and digital signature, then upload to an AWS S3 or MinIO bucket.

### 3. Production Infrastructure & Cloud Deployment
- **Kubernetes Deployment**: Apply the manifests in `infra/k8s/` to an EKS/GKE cluster.
- **Ingress & TLS**: Configure NGINX Ingress Controller or AWS ALB with `cert-manager` for automated Let's Encrypt SSL certificates across all microservices.
- **Domain DNS**: Point production domain names (`api.kynetic.ai`, `app.kynetic.ai`) to the API Gateway.

### 4. Hardware Host Pool Seed & Binary Signing
- **Host Agent Binaries**: Code-sign the compiled PyInstaller Host Agent executable for Windows (.exe) and Linux to prevent OS security warnings.
- **Initial Supply Onboarding**: Seed the marketplace with 10–20 verified host nodes (RTX 4090 / RTX 3090 / A100) running the Host Agent.

### 5. Production Email & Observability Services
- **SendGrid**: Supply a live `SENDGRID_API_KEY` to `services/notifications_service/config.py` and verify domain authentication (DKIM/SPF).
- **Log Aggregation**: Connect `structlog` output to a hosted Loki or ELK instance.

---

## Local Development & Operations Summary

Refer to [DEVELOPMENT.md](file:///Users/divyebhatnagar/Desktop/KyneticSoftware/kynetic-ai/DEVELOPMENT.md) for detailed instructions.

```bash
# Clone the repository
git clone https://github.com/KyneticSoftware/kynetic-ai.git
cd kynetic-ai

# Copy environment variables
cp .env.example .env

# Start microservices via Docker Compose
docker-compose up --build -d

# Execute Database Migrations
docker-compose exec auth_service alembic upgrade head

# Run Pytest Suite
python3 -m pytest tests/wallet_billing_service/test_razorpay.py tests/notifications_service/test_notifications.py -v
```

---

## Test Suite & Verification

The repository includes comprehensive unit and integration test suites covering billing calculations, Razorpay integration, GST invoice generation, email dispatchers, metrics, and API endpoints.

```
============================== 41 passed in 0.13s ==============================
```

- **Razorpay & GST Tests**: 21 passed (INR/paise conversion, signature verification, 18% inclusive GST logic, Indian fiscal year calculations).
- **Notifications & Monitoring Tests**: 20 passed (email templates, SendGrid mock dispatcher, Prometheus metric counters/gauges).
