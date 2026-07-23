# Kynetic AI — Compute-First, AI-Native Marketplace

[![Build Status](https://img.shields.io/badge/build-passing-brightgreen.svg)](#)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](#)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109%2B-009688.svg)](#)
[![Next.js](https://img.shields.io/badge/Next.js-14-black.svg)](#)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](#)

**Kynetic AI** is a compute-first, AI-native marketplace connecting two sides:
- **Hosts**: Anyone with idle compute (GPUs, CPUs, RAM, NVMe storage, or full workstations/gaming PCs/enterprise servers) who wants to monetize their hardware.
- **Developers**: Anyone needing compute for AI/ML workloads (fine-tuning, training, inference, 3D rendering, agent hosting) without infrastructure overhead.

Unlike legacy GPU-only marketplaces (RunPod, Vast.ai, Lambda), Kynetic AI treats **all compute resources as a single resource-agnostic inventory**, replaces manual hardware selection with an **intent-based AI Resource Router & Copilot**, guarantees **zero-setup 1-click app launches**, and provides **India-first billing (UPI + GST invoicing)** alongside global Stripe support.

---

## Table of Contents

1. [Executive Summary & Core Philosophy](#executive-summary--core-philosophy)
2. [Reference Architecture](#reference-architecture)
3. [Monorepo Directory Structure](#monorepo-directory-structure)
4. [Technology Stack](#technology-stack)
5. [Implementation Plan Deep-Dive (Phases 1 – 10)](#implementation-plan-deep-dive-phases-1--10)
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
7. [Local Development & Operations Guide](#local-development--operations-guide)
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
│   ├── marketplace_service/       # Listing management, hardware search, scheduling
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

## Implementation Plan Deep-Dive (Phases 1 – 10)

### Phase 1: Foundations & Core Platform Skeleton
- **Objective**: Stand up the core async microservices chassis, database ORM layer, authentication engine, and CI/CD pipelines.
- **What Was Built**:
  - **API Gateway** (`services/api_gateway`): Re-routing proxy with token-bucket rate limiting and JWT header validation.
  - **Auth Service** (`services/auth_service`): `passlib` password hashing (bcrypt), `python-jose` JWT rotation, and SMS OTP verification stubs.
  - **Database Schema**: `users` (host/developer roles), `sessions`, and immutable `audit_logs` (Security Pillar 11).
  - **CI/CD**: GitHub Actions workflow running `ruff` linting, `pytest`, and `alembic upgrade head`.

### Phase 2: Host Onboarding, Hardware Verification & Benchmarking
- **Objective**: Package an automated host probe binary to verify hardware claims and score performance.
- **What Was Built**:
  - **Host Agent** (`host_agent/`): PyInstaller-packaged Python binary utilizing `psutil` (CPU/RAM/NVMe) and `pynvml` (GPU model, VRAM, temp, power draw).
  - **Hardware Verification**: Anti-spoofing cross-checks against expected hardware signatures.
  - **PyTorch Benchmark Suite**: Micro-tests scoring LLM inference tokens/sec, Stable Diffusion latency, and matrix-multiplication TFLOPs.
  - **mTLS Registration & Heartbeats**: Mutual TLS channel updating host state (`idle`, `busy`, `offline`) every 10 seconds.

### Phase 3: Compute-First Marketplace & Wallet/Billing Core
- **Objective**: Create a resource-agnostic listing engine and a dual-currency usage-metered wallet system.
- **What Was Built**:
  - **Resource-Agnostic Listings**: Inventory bundled as GPU + CPU + RAM + Storage rather than raw GPU model enums.
  - **Wallet & Billing Engine**: Developer wallet created on signup supporting dual currency (INR / USD).
  - **Global Payments**: Stripe Python SDK integration for wallet top-ups and Stripe Connect for host payouts.
  - **Per-Second Usage Metering**: Celery task infrastructure for high-precision usage-based billing.

### Phase 4: Provisioning, Scheduling & Instance Lifecycle
- **Objective**: Orchestrate isolated compute instances with ephemeral storage and automated SSH connectivity.
- **What Was Built**:
  - **Instance Scheduler**: Checks developer wallet balances, places funds holds, and dispatches provisioning tasks.
  - **Zero-Trust Isolation**: Container-in-Firecracker MicroVM sandboxing, blocking host filesystem access.
  - **Ephemeral Access**: Short-lived auto-rotated SSH keypairs and WireGuard NAT relays for non-public IP hosts.
  - **Cryptographic Deletion**: Mandatory NVMe shredding receipt verification before transition to `terminated`.

### Phase 5: Security Hardening & Zero-Trust Safeguards
- **Objective**: Harden the platform against abuse, malware, and unauthorized access.
- **What Was Built**:
  - **Container Scanning**: Pre-execution Docker image malware scanning pipeline.
  - **Runtime Mining Detection**: Real-time hash-rate and signature profile monitoring for unauthorized cryptomining.
  - **Abuse Prevention**: Multi-account device fingerprinting and progressive trust tiers (`trust_tier` capping spend and GPU hours).
  - **Emergency Kill Switch**: Admin endpoint (`POST /admin/kill-switch`) to immediately revoke workloads and freeze host/developer accounts.

### Phase 6: Zero-Setup App Templates & AI-Native Entry Point
- **Objective**: Deliver 1-click execution for popular AI workloads without requiring Docker expertise.
- **What Was Built**:
  - **Template Registry**: Config-driven pre-scanned images for **Stable Diffusion**, **Ollama**, **ComfyUI**, and **Llama 3**.
  - **1-Click Web UI Provisioning**: Automatic WireGuard secure HTTP relay links for web interfaces (e.g., ComfyUI).
  - **Intent-Based UI**: Landing page asking *"What do you want to run?"* instead of raw hardware picking.

### Phase 7: AI Resource Router & AI Copilot
- **Objective**: Provide automated budget/speed recommendation algorithms and a conversational pre-launch assistant.
- **What Was Built**:
  - **AI Resource Router**: Weighted ranking function balancing live pricing, benchmark performance, and host availability.
  - **AI Copilot**: LangChain-powered assistant exposed over WebSockets (`POST /copilot/chat`), translating natural language requirements into grounded machine picks with cost/time estimations.

### Phase 8: Host Experience, Auto-Pricing & Reputation Layer
- **Objective**: Automate host pricing and provide trust-building transparent reputation scores.
- **What Was Built**:
  - **Auto-Pricing Model**: `scikit-learn` regression model suggesting competitive pricing based on hardware class and market demand.
  - **Host Analytics**: Dashboard tracking revenue, temperature trends, electricity costs, and monthly income projections.
  - **6-Factor Reputation Engine**: Composite host score calculated from uptime, latency, network quality, job success rate, benchmark score, and responsiveness.

### Phase 9: External Marketplace Listings & Transparent Fallbacks
- **Objective**: Avoid "no supply" failures by providing transparent external alternatives when local inventory is exhausted.
- **What Was Built**:
  - **Marketplace & Router Fallbacks**: When hardware searches yield zero results (e.g., no RTX 4090 available), the UI renders a *"No RTX 4090 currently available"* notification.
  - **External Recommendations**: Direct clickable badges to **RunPod**, **Vast.ai**, **Lambda**, and **Crusoe**.
  - **Tab-Nabbing Protection**: All external links enforce `rel="noopener noreferrer"` target attributes.

### Phase 10: India-First Regional Billing, Unified Monitoring & Dashboard
- **Objective**: Complete the regional India billing stack, unified Prometheus observability, and developer dashboard.
- **What Was Built**:
  - **Razorpay / UPI Integration**: `RazorpayClient` with mock-mode support for INR UPI top-ups and payouts.
  - **GST Invoicing Engine**: Sequential Indian fiscal year invoice generator (`KYN/2024-25/000001`) calculating 18% inclusive GST via row-level locking (`SELECT FOR UPDATE`).
  - **Notifications Service**: Microservice on port 8010 handling event-driven emails (low balance, instance lifecycle, GST invoice ready, payouts).
  - **Unified Monitoring Service**: Microservice on port 8011 exposing `/monitoring/metrics` for Prometheus and Grafana dashboards.
  - **Developer Dashboard**: Tabbed frontend interface for Billing History, GST Invoices, and Regional Support Tickets.

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

## Local Development & Operations Guide

### Prerequisites
- Docker & Docker Compose
- Python 3.11+
- Node.js 18+ & `pnpm` / `npm`

### Environment Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

### Running the Full Stack locally

1. **Start all backend microservices, PostgreSQL, and Redis**:
   ```bash
   docker-compose up --build -d
   ```

2. **Run Database Migrations**:
   ```bash
   docker-compose exec auth_service alembic upgrade head
   ```

3. **Start Monitoring Stack (Prometheus & Grafana)**:
   ```bash
   docker-compose -f infra/docker-compose.monitoring.yml up -d
   ```
   - Grafana UI: `http://localhost:3000` (admin / admin)
   - Prometheus UI: `http://localhost:9090`

4. **Start Frontend (Next.js)**:
   ```bash
   cd apps/frontend
   npm install
   npm run dev
   ```
   - App URL: `http://localhost:3001`

---

## Test Suite & Verification

The repository includes comprehensive unit and integration test suites covering billing calculations, Razorpay integration, GST invoice generation, email dispatchers, metrics, and API endpoints.

### Executing Unit Tests
To run the Phase 10 test suite without requiring a local PostgreSQL database:

```bash
python3 -m pytest tests/wallet_billing_service/test_razorpay.py tests/notifications_service/test_notifications.py -v
```

### Test Suite Output
```
============================== 41 passed in 0.13s ==============================
```

- **Razorpay & GST Tests**: 21 passed (INR/paise conversion, signature verification, 18% inclusive GST logic, Indian fiscal year calculations).
- **Notifications & Monitoring Tests**: 20 passed (email templates, SendGrid mock dispatcher, Prometheus metric counters/gauges).
