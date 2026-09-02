# Kynetic AI — Backend & Microservices Engine

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111.0-009688.svg)](https://fastapi.tiangolo.com/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0%20Async-red.svg)](https://www.sqlalchemy.org/)
[![Redis](https://img.shields.io/badge/Redis-Pub%2FSub%20%26%20Cache-dc382d.svg)](https://redis.io/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791.svg)](https://www.postgresql.org/)
[![Pytest](https://img.shields.io/badge/pytest-56%20passing%20integration%20tests-brightgreen.svg)](https://docs.pytest.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

The **Kynetic AI Backend** powers a compute marketplace connecting compute hosts with AI/ML developers. The backend architecture consists of **11 asynchronous FastAPI microservices**, a **NAT-Traversing Tunnel Gateway**, a cross-platform **Python Host Agent daemon**, shared core libraries, a **3-party marketplace payment & double-entry financial ledger engine**, priority commission resolver, host KYC financial onboarding, idempotent payout engine, zero-trust security controls, GPU benchmark analytics DB, multi-attribute smart search engine, and an automated Pytest test suite with **56 passing integration tests across all Implementation Plan v6, v7, and v8 Features (Phases A–L, P1–P7, and v8 Features 1–7)**.

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
- **GPU Discovery & NVML Telemetry**: Utilizes `pynvml` & `ctypes` bindings to `libnvidia-ml.so` to inspect GPU models (RTX 4090, A100, H100, L40S) and streams live 10s telemetry: VRAM utilization, GPU core clock, temperature (°C), fan speed (%), and power draw (Watts).
- **Native Ctypes Benchmarking Suite (PyTorch-Free)**: Native Ctypes CUDA driver & NVML GEMM throughput benchmarks for FP16/FP32 TFLOPS without bundling PyTorch or CUDA wheels in the host agent binary (saves ~1.8–2.2 GB). Deep PyTorch benchmarks are run in ephemeral containers.
- **MicroVM & Container Runtime Stack**: Uses Firecracker with minimal Alpine 3.20 rootfs (`rootfs-min.ext4` ~45 MB) and stripped kernel (`vmlinux-min` ~12 MB) alongside `containerd` + `stargz-snapshotter` (~90 MB total) for sub-2s eStargz lazy image pulling.
- **LRU Cache & Volume Manager (`cache_manager.py`, `volume_manager.py`)**: Bounded 1.0–5.0 GB ephemeral storage LRU eviction, automatic log rotation caps (10–25 MB), Firecracker socket cleanup, and NVMe orphan volume TRIM & LUKS2 header erasure.
- **mTLS gRPC Control Channel (`command_listener.py`)**: Direct control-plane command servicer handling Launch, Stop, Terminate, and Rebenchmark RPCs over mTLS without external Redis pub/sub dependencies.
- **PTY Stream Allocator (`host_agent/pty_handler.py`)**: Spawns pseudo-terminals (`pty.openpty()`) inside guest microVM containers.
- **Cryptographic Storage Shredding (`host_agent/volume_manager.py`)**: Executes LUKS2 key destruction and NVMe `blkdiscard` TRIM sanitization, returning a signed `SecureDeletionReceipt`.
- **Runtime Cryptomining Abuse Detector (`host_agent/abuse_detector.py`)**: Pre-execution OCI container image safety scanner and process command-line inspection (`xmrig`, `ethminer`, `stratum+tcp://`).

### 4. 🌟 GPU Benchmarks, Rolling Health & Verified Hosts (v8 Features 1–3)
- **Peer-Group Normalization Engine (`benchmark_suite.py`)**: Normalizes FP16/FP32 TFLOPS and VRAM bandwidth against same-model GPU peer envelopes (`gpu_model_envelopes`). Compares measured output against min/max bounds to flag fraud or hardware throttling (`check_envelope`).
- **Rolling 7-Day Health Score**: Computes rolling thermal, core clock, and power draw stability scores from 10s NVML telemetry using inverse coefficient of variation ($1 - \frac{\text{std}}{\text{mean}}$).
- **Host Reputation System (`reputation_engine.py`)**: Immutable append-only audit event log (`reputation_events`), exponential time-decay score engine ($e^{-\lambda t}$, 30-day half-life), anti-gaming cancellation penalties (`-0.0200`), and automatic trust state transitions (`building_trust` ➔ `established` or `flagged`).
- **Verified Hosts Program (`verification_service.py`)**: Tiered verification (`unverified` ➔ `silver` ➔ `gold` ➔ `enterprise`). Supports automated Silver checks, Gold eligibility validation, admin review queue, and revocation cascades (`-0.3500` reputation penalty).

### 5. 🔍 GPU Benchmark DB & Multi-Attribute Smart Search (v8 Features 4 & 5)
- **GPU Benchmark Database (`benchmark_analytics.py`)**: Aggregated read-optimized analytics layer (`gpu_model_stats`, `price_performance_stats`) exposing aggregate TFLOPS, memory bandwidth, and score-per-dollar price/performance rankings (`GET /benchmarks/gpu-models`, `GET /benchmarks/price-performance`).
- **Multi-Attribute Smart Search Engine (`search_engine.py`)**: High-speed composable search query engine (`GET /v1/search/listings`) over a denormalized catalog (`searchable_listings`), filtering by GPU model, VRAM capacity, TFLOPS, health score, reputation composite score, verification level, price, region, and OS with cursor pagination.

### 6. 💳 Marketplace Payments, Priority Commission & Double-Entry Ledger (v7 Engine)
- **3-Party Marketplace Payments (`provider_interface.py`)**: Decouples payment collection from delayed host settlement. Funds are captured directly by the Kynetic platform account, usage is metered per-second and recorded in the double-entry financial ledger, and session termination triggers host earnings split.
- **Balanced Double-Entry Financial Ledger (`ledger_service.py`)**: Immutable `LedgerEntry` rows (`v7_ledger_entries`) recording balanced debit/credit pairs (`debit == credit`) across `customer_account:{user_id}`, `platform_revenue`, `host_payable`, `tax_payable`, `provider_clearing`, and `refund_reserve`. Includes daily double-entry reconciliation validator.
- **Priority-Based Commission Resolver (`commission_service.py`)**: Evaluates candidate rules in priority order (`promotional` ➔ `host` ➔ `enterprise` ➔ `workload` ➔ `gpu_type` ➔ `region` ➔ `global_default`). Splits gross compute rental cost into platform commission and net host earnings (`v7_host_earnings`).
- **Host Financial Onboarding & KYC (`kyc_service.py`)**: Onboarding state machine (`registered` ➔ `kyc_approved` ➔ `active`), application-layer encryption for PAN & bank credentials (`enc_v1_...`), and provider linked account creation.
- **Host Payout Engine (`payout_engine.py`)**: Batches pending host earnings into `Payout` (`v7_payouts`) when minimum threshold ($50) is reached. Executes transfers passing `payout.id` as provider idempotency key (`reference_id`).
- **Refund & Failure Recovery Engine (`refund_service.py`)**: Processes customer refunds and handles refund-after-host-paid scenario by drawing from platform `refund_reserve` buffer.

---

## 🧪 Running the Backend Tests

Run the full integration test suite across all Implementation Plan v6 (Phases A–L), v7 (Phases P1–P7), and v8 (Features 1–7) features:

```bash
DATABASE_URL="sqlite+aiosqlite:///:memory:" .venv/bin/pytest cli/tests/test_cli_auth.py backend/tests/test_v6_phase_a_auth.py backend/tests/test_v6_phase_b_host_marketplace.py backend/tests/test_v6_phase_c_runtime.py backend/tests/test_v6_phase_d_agent_completion.py backend/tests/test_v6_phase_e_f_gateway_cli.py backend/tests/test_v6_phase_g_h_dx_scheduler.py backend/tests/test_v6_phase_i_j_k_l_launch_readiness.py backend/tests/test_v7_phase_1_2_payments_ledger.py backend/tests/test_v7_phase_3_4_kyc_commission.py backend/tests/test_v7_phase_5_6_7_payouts_refunds_dashboards.py backend/tests/test_v8_feature_1_benchmark_health_score.py backend/tests/test_v8_feature_2_3_reputation_verification.py backend/tests/test_v8_feature_4_5_6_search_launch.py
```─┐    ┌──────────────┐    ┌──────────────┐
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

