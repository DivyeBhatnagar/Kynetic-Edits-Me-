# Kynetic AI — Decentralized GPU & Compute Marketplace

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Next.js Version](https://img.shields.io/badge/next.js-16.2.11-black.svg)](https://nextjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111.0-009688.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Kynetic AI** is a resource-agnostic compute marketplace connecting idle GPU hardware (RTX 4090, A100, H100) with AI developers. Hosts monetize idle consumer and enterprise hardware, while developers deploy microVM instances with 1-click AI Copilot matching, real-time telemetry, and automated billing.

---

## ⚡ Core Features

- 🖥️ **Monetize Idle Hardware**: Host agent discovers GPUs (NVML), benchmarks compute capabilities, and registers nodes automatically.
- 🤖 **AI Resource Copilot**: Natural language workload matching (*"Find an RTX 4090 under $1.50/hr for LoRA fine-tuning"*) with weighted scoring.
- 🔒 **Zero-Trust Hardening**: Isolated Firecracker MicroVM runtime, ephemeral storage encryption, kill-switch suspension, and device fingerprinting.
- 💳 **Dual-Currency Billing**: USD & INR wallet top-ups via Stripe with automated GST tax invoicing.
- 📊 **Real-time Telemetry & Monitoring**: Prometheus metrics, GPU VRAM/temperature tracking, and automated host heartbeats.

---

## 🏗️ System Architecture

```
                    ┌────────────────────────────────────────────────────────┐
                    │     Next.js 16 + React 19 + Tailwind CSS Frontend      │
                    │                   (port 3000)                          │
                    └───────────────────────────┬────────────────────────────┘
                                                │ REST / WebSockets
                                                ▼
                    ┌────────────────────────────────────────────────────────┐
                    │               FastAPI API Gateway (:8000)              │
                    │      (JWT Validation, Redis Token-Bucket Rate Limiter) │
                    └───────────────────────────┬────────────────────────────┘
                                                │ Internal REST / mTLS
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
                                    │ - Ephemeral Storage  │
                                    │ - WireGuard NAT Relay│
                                    └──────────────────────┘
        ┌───────────────────┬───────────────────┼───────────────────┐
        ▼                   ▼                   ▼                   ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ Reputation & │    │  Security    │    │Notifications │    │  Monitoring  │
│ Pricing      │    │  Service     │    │  Service     │    │  Service     │
│   (:8006)    │    │   (:8007)    │    │   (:8009)    │    │   (:8010)    │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘

Data Infrastructure:
- PostgreSQL (SQLAlchemy 2.0 Async + Alembic Migrations)
- Redis (Session Cache + Rate Limiting + Celery Broker)
- Prometheus & Grafana (Metrics & Monitoring)
```

---

## 📂 Repository Structure

```
kynetic-ai/
├── frontend/             # Next.js 16 Unified Web Application (User, Host & Admin)
├── host_agent/           # Cross-platform Python Host Agent & Benchmark Engine
├── services/             # FastAPI Microservices
│   ├── api_gateway/      # Unified entry point & rate limiting middleware
│   ├── auth_service/     # Authentication, bcrypt, PyJWT & OTP verification
│   ├── host_service/     # Host heartbeats & NVML telemetry ingestion
│   ├── marketplace_service/ # Hardware listing catalog & search engine
│   ├── wallet_billing_service/ # Wallet balances, dual-currency billing & Stripe
│   ├── provisioning_service/   # Instance lifecycle & WireGuard tunneling
│   ├── security_service/       # Kill-switch, image scanning & trust tiers
│   ├── ai_router_copilot_service/ # Workload ranking & Copilot matching
│   ├── reputation_pricing_service/ # Host scoring & dynamic pricing
│   ├── notifications_service/  # Email alerts & notification dispatching
│   └── monitoring_service/     # Prometheus metrics scrapers
├── libs/                 # Shared Python Libraries
│   ├── common/           # Logging, async HTTP client & middleware
│   └── db_models/        # Shared SQLAlchemy 2.0 async database models
├── infra/                # Infrastructure & Containerization
│   ├── docker-compose.yml# Local multi-container development stack
│   └── k8s/              # Production Kubernetes manifests
└── Docs/                 # Architecture, API & Setup Documentation
```

---

## 🚀 Quickstart Guide

### Prerequisites
- **Python**: `>= 3.11`
- **Node.js**: `>= 18.x`
- **Docker & Docker Compose**: `v2.x+`

### 1. Backend Setup
```bash
# Clone the repository
git clone https://github.com/DivyeBhatnagar/KyneticSoftware.git
cd KyneticSoftware/kynetic-ai

# Set up virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt 2>/dev/null || pip install -e .
```

### 2. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

### 3. Docker Compose Stack (All Services + Infrastructure)
```bash
docker-compose up --build -d
```

- **Frontend Application**: `http://localhost:3000`
- **API Gateway**: `http://localhost:8000`
- **Prometheus Metrics**: `http://localhost:9090`

---

## 🛡️ Security & Integrity

- **Password Hashing**: `bcrypt` with configurable salt rounds.
- **Token Security**: Short-lived `PyJWT` access tokens with SHA-256 refresh token rotation.
- **Container Hardening**: Image scanning, forbidden syscall filters, and non-root execution.
- **Emergency Suspension**: Admin kill-switch to instantly halt rogue instances or compromised host accounts.

---

## 📄 Documentation

- [System Architecture](Docs/Setup/ARCHITECTURE.md)
- [Development Guide](Docs/Setup/DEVELOPMENT.md)
- [Environment Configuration](Docs/Setup/ENVIRONMENT.md)
- [Database Schema](Docs/Setup/DATABASE.md)
- [Host Agent Setup](Docs/Setup/HOST_AGENT.md)

---

## 📜 License

Distributed under the MIT License. See [LICENSE](Docs/Setup/LICENSE) for details.
