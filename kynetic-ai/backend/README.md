# Kynetic AI — Backend & Microservices Engine

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111.0-009688.svg)](https://fastapi.tiangolo.com/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0%20Async-red.svg)](https://www.sqlalchemy.org/)
[![Redis](https://img.shields.io/badge/Redis-Pub%2FSub%20%26%20Cache-dc382d.svg)](https://redis.io/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791.svg)](https://www.postgresql.org/)
[![Pytest](https://img.shields.io/badge/pytest-37%20passing%20integration%20tests-brightgreen.svg)](https://docs.pytest.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

The **Kynetic AI Backend** powers a compute marketplace connecting compute hosts with AI/ML developers. The backend architecture consists of **11 asynchronous FastAPI microservices**, a **NAT-Traversing Tunnel Gateway**, a cross-platform **Python Host Agent daemon**, shared core libraries, a **3-party marketplace payment & double-entry financial ledger engine**, priority commission resolver, host KYC financial onboarding, idempotent payout engine, zero-trust security controls, and an automated Pytest test suite with **37 passing integration tests across all 19 Implementation Plan v6 & v7 Phases (A–L and P1–P7)**.

---

## ⚡ Comprehensive Feature Breakdown

### 1. 🤖 Intent-Based AI Router, 6-Factor Scheduler & Copilot
- **6-Factor Weighted Node Scoring Engine (§9)**: Evaluates compute nodes based on:
  1. **GPU/Compute Match Score** (30%)
  2. **FP32 TFLOPS & Benchmark Score** (25%)
  3. **Host Reputation & Trust Rating** (20%)
  4. **Network Latency & Geo Proximity** (15%)
  5. **Price Efficiency** (10%)
  6. **Hardware Availability** (10%)
  - Plus a **5% anti-starvation randomization jitter band**.
- **Scheduler Hints**: Supports `balanced` (default), `budget` (50% price weighted), and `fastest` (50% benchmark weighted) launch modes.

### 2. 🔌 NAT-Traversing Tunnel Gateway (`gateway_service/`)
- **Reverse-Dial WebSocket Relay**: Eliminates host NAT and firewall requirements. Both CLI and Host Agent dial *outbound* to the Gateway.
- **Session Ticket Allocator**: Issues short-lived cryptographic tickets for CLI shell access.
- **Multiplexed PTY Stream**: Relays raw terminal input/output bytes with automatic reconnect and zero shell state loss.

### 3. 🖥️ Host Agent Daemon (`host_agent/`)
- **GPU Discovery & NVML Telemetry**: Utilizes `pynvml` to inspect GPU models (RTX 4090, A100, H100, L40S) and streams live 10s telemetry: VRAM utilization, GPU core clock, temperature (°C), fan speed (%), and power draw (Watts).
- **Hardware Benchmarking Suite**: Automatically benchmarks compute nodes upon onboarding: FP32 TFLOPS matrix mult and LLM inference performance loops.
- **PTY Stream Allocator (`host_agent/pty_handler.py`)**: Spawns pseudo-terminals (`pty.openpty()`) inside guest microVM containers.
- **Cryptographic Storage Shredding (`host_agent/secure_delete.py`)**: Executes 3-pass DoD 5220.22-M storage shredding (`shred -n 3 -z`) and returns a signed `SecureDeletionReceipt`.
- **Runtime Cryptomining Abuse Detector (`host_agent/abuse_detector.py`)**: Pre-execution OCI container image safety scanner and process command-line inspection (`xmrig`, `ethminer`, `stratum+tcp://`).

### 4. 🔒 Zero-Trust Security & Pre-Flight Logic Gate
- **Pre-Flight Validation Gate**: Enforces business logic rules before scheduling instance creation:
  - Validates developer account status and listing availability before scheduling.
  - Checks compute listing availability and host reservation lock.
  - Verifies host node heartbeat freshness (< 120s) and NVML health indicators.
  - Enforces progressive trust tier spend and instance caps.
- **Progressive Trust Tiers (`security_service/trust_manager.py`)**:
  - `Tier 1`: $10.00/hr max spend, 2 active instances.
  - `Tier 2`: $50.00/hr max spend, 5 active instances.
  - `Tier 3`: Unlimited spend, 20 active instances.
- **Device Fingerprinting**: Client signal SHA-256 fingerprinting on user authentication (`DeviceFingerprint`).
- **Platform Emergency Kill-Switch (`security_service/kill_switch.py`)**: Admin API endpoint (`POST /v1/security/kill-switch`) that instantly revokes instances, suspends host registrations, or locks compromised user accounts across the Control Plane.

### 5. 💳 Marketplace Payments, Priority Commission & Double-Entry Ledger (v7 Engine)
- **3-Party Marketplace Payments (`provider_interface.py`)**: Decouples payment collection from delayed host settlement. Funds are captured directly by the Kynetic platform account, usage is metered per-second and recorded in the double-entry financial ledger, and session termination triggers host earnings split.
- **Balanced Double-Entry Financial Ledger (`ledger_service.py`)**: Immutable `LedgerEntry` rows (`v7_ledger_entries`) recording balanced debit/credit pairs (`debit == credit`) across `customer_account:{user_id}`, `platform_revenue`, `host_payable`, `tax_payable`, `provider_clearing`, and `refund_reserve`. Includes daily double-entry reconciliation validator.
- **Priority-Based Commission Resolver (`commission_service.py`)**: Evaluates candidate rules in priority order (`promotional` ➔ `host` ➔ `enterprise` ➔ `workload` ➔ `gpu_type` ➔ `region` ➔ `global_default`). Lower priority integer = higher precedence. Splits gross compute rental cost into `platform_commission` and net host earnings (`v7_host_earnings`).
- **Host Financial Onboarding & KYC (`kyc_service.py`)**: Onboarding state machine (`registered` ➔ `kyc_approved` ➔ `active`), application-layer encryption for PAN & bank credentials (`enc_v1_...`), and provider linked account creation (`PaymentProviderAccount`).
- **Host Payout Engine (`payout_engine.py`)**: Batches pending host earnings into `Payout` (`v7_payouts`) & `PayoutLineItem` (`v7_payout_line_items`) when minimum threshold ($50) is reached. Executes transfers passing `payout.id` as provider idempotency key (`reference_id`), updating earnings status to `settled` and writing `PAYOUT` double-entry ledger entries. Includes retry logic and `manual_review` failure escalation.
- **Refund & Failure Recovery Engine (`refund_service.py`)**: Processes customer refunds (`v7_refunds`) and handles refund-after-host-paid scenario by drawing from platform `refund_reserve` buffer rather than attempting bank clawbacks.
- **Payment Provider Abstraction**: Unified `PaymentProviderInterface` supporting `RazorpayRouteAdapter` (India linked accounts), `CashfreeEasySplitAdapter` (India vendors), and `StripeConnectAdapter` (global accounts).
- **Financial Dashboard APIs (`dashboard_routes.py`)**: `GET /v1/payouts` (host payout history with line-item traceability), `GET /v1/ledger` (admin double-entry ledger browser), `GET /v1/hosts/{id}/dashboard/financials` (pending earnings, settled balance, effective commission rate).

### 6. 📊 Observability & Metrics
- **Prometheus Metrics Exporter (`libs/common/metrics.py`)**: Exposes Prometheus gauges and counters (`kynetic_instances_active_total`, `kynetic_hosts_verified_total`, `kynetic_metered_seconds_total`, `kynetic_gateway_pty_sessions_active`) via `/metrics` endpoints.

---

## 🏗️ Backend Microservices Architecture

```
                    ┌────────────────────────────────────────────────────────┐
                    │               FastAPI API Gateway (:8000)              │
                    │   (JWT Validation, Redis Token-Bucket Rate Limiter)    │
                    └───────────────────────────┬────────────────────────────┘
                                                │ Internal REST / mTLS
         ┌───────────────────┬──────────────────┴───────────────────┬───────────────────┐
         ▼                   ▼                                      ▼                   ▼
┌──────────────┐    ┌──────────────┐                       ┌──────────────┐    ┌──────────────┐
│ Auth Service │    │ Marketplace  │                       │ Billing &    │    │  AI Router   │
│   (:8001)    │    │   (:8002)    │                       │ Payments     │    │  & Copilot   │
└──────────────┘    └───────┬──────┘                       │   (:8004)    │    │   (:8005)    │
                            │                              └──────────────┘    └──────────────┘
                            ▼
                    ┌──────────────┐        mTLS           ┌──────────────────────┐
                    │ Provisioning ├──────────────────────►│ Host Agent Daemon    │
                    │   (:8003)    │                       │ - Firecracker VM     │
                    └───────┬──────┘                       │ - NVML Telemetry     │
                            │                              │ - Abuse Detector     │
                            ▼                              └──────────────────────┘
                    ┌──────────────┐
                    │ Tunnel       │ WebSocket Relay
                    │ Gateway      ├──────────────────────► Developer PTY Stream
                    │   (:8008)    │
                    └──────────────┘
         ┌───────────────────┬───────────────────┬───────────────────┐
         ▼                   ▼                   ▼                   ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ Reputation & │    │  Security    │    │Notifications │    │  Monitoring  │
│ Pricing      │    │  Service     │    │  Service     │    │  Service     │
│   (:8006)    │    │   (:8007)    │    │   (:8010)    │    │   (:8011)    │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘

Data Infrastructure:
- PostgreSQL 16 (SQLAlchemy 2.0 Async + Alembic Migrations)
- Redis 7 (Session Cache + Rate Limiting + Pub/Sub Billing Event Bus)
- Prometheus & Grafana (Metrics & Telemetry Scraping)
```

---

## 🧪 Running the Backend Tests

Run the full integration test suite across all Implementation Plan v6 (Phases A–L) and v7 (Phases P1–P7) Phases:

```bash
DATABASE_URL="sqlite+aiosqlite:///:memory:" .venv/bin/pytest cli/tests/test_cli_auth.py backend/tests/test_v6_phase_a_auth.py backend/tests/test_v6_phase_b_host_marketplace.py backend/tests/test_v6_phase_c_runtime.py backend/tests/test_v6_phase_d_agent_completion.py backend/tests/test_v6_phase_e_f_gateway_cli.py backend/tests/test_v6_phase_g_h_dx_scheduler.py backend/tests/test_v6_phase_i_j_k_l_launch_readiness.py backend/tests/test_v7_phase_1_2_payments_ledger.py backend/tests/test_v7_phase_3_4_kyc_commission.py backend/tests/test_v7_phase_5_6_7_payouts_refunds_dashboards.py
```

