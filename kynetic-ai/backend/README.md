# Kynetic AI — Backend & Microservices Engine

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111.0-009688.svg)](https://fastapi.tiangolo.com/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0%20Async-red.svg)](https://www.sqlalchemy.org/)
[![Redis](https://img.shields.io/badge/Redis-Pub%2FSub%20%26%20Cache-dc382d.svg)](https://redis.io/)
[![Pytest](https://img.shields.io/badge/pytest-88%20passing-brightgreen.svg)](https://docs.pytest.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Kynetic AI Backend** powers a resource-agnostic compute marketplace connecting idle GPU/CPU hardware with AI/ML developers. The backend architecture consists of 11 asynchronous FastAPI microservices, a cross-platform Python Host Agent daemon, shared core libraries, a double-entry financial ledger with per-second billing, and an automated Pytest test suite (88 passing unit and integration tests).

---

## ⚡ Key Backend Capabilities

- 🤖 **Intent-Based AI Copilot & Router**: Natural language workload parser with 6-factor weighted node scoring algorithm (GPU match, VRAM headroom, host reputation, network latency, pricing, uptime history).
- 🖥️ **Host Agent Daemon**: Automated GPU hardware discovery via NVML, compute benchmarking, WireGuard VPN relay, Firecracker MicroVM lifecycle management, and idempotent control channels.
- 🔒 **Zero-Trust Security & Pre-Flight Gate**: Isolated Firecracker microVM runtime, ephemeral storage LUKS2 encryption, admin emergency kill-switch, and DB pre-flight checks validating wallet balance holds & host freshness.
- 💳 **Dual-Currency Billing & Metering Engine**: Per-second micro-billing event bus backed by Redis Pub/Sub, double-entry transaction ledger, Stripe card payments, Razorpay UPI/Netbanking, and automated 18% GST tax invoice generation.
- 📊 **Unified Telemetry & Observability**: Real-time Prometheus metrics, GPU VRAM & temperature monitoring, health scrapers across all 11 microservices, and system notification dispatching.

---

## 🏗️ Backend System Architecture

```
                    ┌────────────────────────────────────────────────────────┐
                    │               FastAPI API Gateway (:8000)              │
                    │   (JWT Validation, Redis Token-Bucket Rate Limiter)    │
                    └───────────────────────────┬────────────────────────────┘
                                                │ Internal REST / mTLS
         ┌───────────────────┬──────────────────┴───────────────────┬───────────────────┐
         ▼                   ▼                                      ▼                   ▼
┌──────────────┐    ┌──────────────┐                       ┌──────────────┐    ┌──────────────┐
│ Auth Service │    │ Marketplace  │                       │ Wallet &     │    │  AI Router   │
│   (:8001)    │    │   (:8002)    │                       │ Billing      │    │  & Copilot   │
└──────────────┘    └───────┬──────┘                       │   (:8004)    │    │   (:8005)    │
                            │                              └──────────────┘    └──────────────┘
                            ▼
                    ┌──────────────┐        mTLS           ┌──────────────────────┐
                    │ Provisioning ├──────────────────────►│ Host Agent Daemon    │
                    │   (:8003)    │                       │ - Firecracker VM     │
                    └──────────────┘                       │ - NVML Telemetry     │
                                                           │ - WireGuard Relay    │
                                                           └──────────────────────┘
         ┌───────────────────┬───────────────────┬───────────────────┐
         ▼                   ▼                   ▼                   ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ Reputation & │    │  Security    │    │Notifications │    │  Monitoring  │
│ Pricing      │    │  Service     │    │  Service     │    │  Service     │
│   (:8006)    │    │   (:8007)    │    │   (:8010)    │    │   (:8011)    │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘

Data Infrastructure:
- PostgreSQL (SQLAlchemy 2.0 Async + Alembic Migrations)
- Redis (Session Cache + Rate Limiting + Pub/Sub Billing Event Bus)
- Prometheus & Grafana (Metrics & Telemetry Scraping)
```

---

## 🧩 Microservices Directory & Services Breakdown

The backend is structured into modular microservices inside `services/`:

| Microservice | Port | Primary Responsibilities | Key Technologies |
| :--- | :--- | :--- | :--- |
| **`api_gateway`** | `:8000` | Single entry point, JWT validation, Redis token-bucket rate limiter, CORS, request routing | FastAPI, Redis, PyJWT |
| **`auth_service`** | `:8001` | User registration, login, JWT token issuance & refresh rotation, bcrypt hashing, OTP verification | FastAPI, bcrypt, PyJWT |
| **`marketplace_service`** | `:8002` | Hardware listing catalog, multi-parameter search (GPU, VRAM, RAM, region, price), listing details | FastAPI, SQLAlchemy Async |
| **`provisioning_service`** | `:8003` | Instance lifecycle (provision, boot, stop, terminate), pre-flight DB gate, WireGuard tunnel setup | FastAPI, mTLS, WireGuard |
| **`wallet_billing_service`** | `:8004` | Multi-currency wallet (USD/INR), Stripe & Razorpay webhooks, per-second metering engine, GST invoicing | FastAPI, Stripe, Razorpay |
| **`ai_router_copilot_service`** | `:8005` | Intent parsing (*"Find RTX 4090 under $1.50/hr"*), 6-factor weighted node scoring, deployment presets | FastAPI, Python Math Engine |
| **`reputation_pricing_service`** | `:8006` | Host 6-factor trust scoring, dynamic auto-pricing engine based on hardware demand & uptime | FastAPI, NumPy |
| **`security_service`** | `:8007` | Admin emergency kill-switch, host trust tier verification, container image scanning validation | FastAPI, Security Audit Engine |
| **`notifications_service`** | `:8010` | Email alerts, in-app notifications, low balance & heartbeat failure warnings | FastAPI, Jinja2 Templates |
| **`monitoring_service`** | `:8011` | Prometheus metrics scrapers, health checks across all 11 services, telemetry aggregation | FastAPI, Prometheus Client |
| **`host_service`** | `:8008` | Host registration, heartbeat ingestion, NVML GPU telemetry processing, hardware benchmarks | FastAPI, NVML / PyNVML |

---

## 🖥️ Host Agent Daemon (`host_agent/`)

The **Host Agent** is a lightweight, cross-platform Python daemon deployed on compute host nodes:
- **GPU Discovery & Telemetry**: Uses NVML to track VRAM usage, GPU core clock, temperature, fan speed, and power draw in real time.
- **Hardware Benchmarking Engine**: Measures FP32 TFLOPS, memory bandwidth (GB/s), NVMe disk IOPS, and network throughput upon registration.
- **Firecracker MicroVM Manager**: Spawns isolated microVM instances with custom rootfs images, ephemeral LUKS2 volume encryption, and non-root execution.
- **WireGuard NAT Relay**: Establishes peer-to-peer encrypted WireGuard tunnels between client developers and hosted instances.
- **Control Channel & Idempotency**: Listens for control commands (start, stop, terminate, snapshot) with idempotent execution tokens preventing duplicate actions.

---

## 📚 Shared Libraries & Modules (`libs/`)

- **`libs/db_models/`**: Centralized SQLAlchemy 2.0 Async models:
  - `User`, `HostNode`, `HardwareBenchmark`, `ComputeListing`, `ComputeInstance`, `Wallet`, `Transaction`, `Invoice`, `Notification`, `SecurityAuditLog`.
- **`libs/common/`**: Shared async HTTP client, structured JSON logging, security middleware, JWT validation utilities, and custom exceptions.
- **`libs/events/`**: Redis Pub/Sub event bus for per-second billing events (`billing.event`), host heartbeats (`host.heartbeat`), and instance status changes (`instance.status_changed`).

---

## 🧪 Test Suite & Verification (`tests/`)

The backend includes a comprehensive Pytest suite with **88 passing tests**:

```bash
# Run unit tests
python3 -m pytest tests/unit/ -v

# Run integration tests
python3 -m pytest tests/integration/ -v

# Run complete test suite
python3 -m pytest tests/ -v
```

### Test Coverage Highlights:
- **Authentication**: User registration, login, token refresh, password hashing, invalid credentials rejection.
- **Marketplace & Search**: Hardware filtering by VRAM, price range, region, host trust rating, availability state.
- **AI Copilot**: Workload intent matching, 6-factor weighted node ranking, edge case fallback handling.
- **Provisioning & Pre-Flight Gate**: Pre-flight validation gate verifying wallet balance hold, listing availability, and heartbeat freshness before instance creation.
- **Wallet & Billing**: Multi-currency wallet operations (USD/INR), double-entry transaction balances, per-second metering calculation, GST invoice formatting.
- **Host Agent & Security**: Idempotent command processing, NVML metric parsing, emergency kill-switch execution.

---

## 🛠️ Local Quickstart Guide

### Prerequisites
- **Python**: `>= 3.11`
- **Docker & Docker Compose**: `v2.x+`
- **PostgreSQL**: `>= 15` (or via Docker)
- **Redis**: `>= 7` (or via Docker)

### 1. Environment Setup
```bash
# Navigate to backend directory
cd KyneticSoftware/kynetic-ai

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt 2>/dev/null || pip install -e .
```

### 2. Run Database Migrations
```bash
alembic upgrade head
```

### 3. Launch Docker Compose Stack
```bash
docker-compose up --build -d
```

### Service Health Checks:
- **API Gateway**: `http://localhost:8000/health`
- **Auth Service**: `http://localhost:8001/health`
- **Marketplace Service**: `http://localhost:8002/health`
- **Provisioning Service**: `http://localhost:8003/health`
- **Wallet Service**: `http://localhost:8004/health`
- **AI Copilot Service**: `http://localhost:8005/health`

---

## 🛡️ Security Architecture

1. **Authentication & Authorization**: Password hashing with `bcrypt` (12 rounds). PyJWT access tokens with short TTL and rotated refresh tokens.
2. **Pre-Flight Business Logic Gate**: Prevents orphaned instance provisioning by locking wallet funds and validating node telemetry prior to schedule execution.
3. **Data Isolation & Encryption**: Ephemeral storage encrypted with LUKS2 per instance. Sensitive API keys encrypted at rest using Fernet symmetric encryption.
4. **Emergency Kill-Switch**: Admin API endpoint (`POST /security/kill-switch`) instantly revokes credentials, isolates WireGuard interface, and shreds active instance storage.
