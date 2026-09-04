# Kynetic AI — Decentralized Cloud Computer Marketplace

> **The terminal, not the browser, is the product.**

Kynetic AI connects compute hosts (datacenter servers, idle mining rigs, gaming PCs) with developers who need high-performance GPU/CPU Linux compute right now. Kynetic delivers raw, unmediated terminal access (`kynetic connect` / `kynetic launch`) to a remote Linux machine in seconds — with no notebooks, no web IDE, and zero configuration of firewalls, security groups, or IP addresses.

---

## 🏛️ System Architecture

Kynetic AI uses a **Hybrid Go/Python** architecture — Go for I/O-bound high-concurrency infrastructure, Python for business logic:

```
┌─────────────────┐        ┌──────────────────┐        ┌──────────────────────┐
│  Web Dashboard  │◄──────►│   Control Plane  │◄──────►│  PostgreSQL 16 DB    │
│  (Next.js App)  │  REST  │  (FastAPI/Python) │  SQL   │  (source of truth)   │
└─────────────────┘        └────────┬─────────┘        └──────────────────────┘
                                    │
┌─────────────────┐        ┌────────▼─────────┐        ┌──────────────────────┐
│  Kynetic CLI    │◄──────►│   API Gateway    │◄──────►│  Redis 7 Cache /     │
│  [GO BINARY]    │  REST  │   + Auth         │        │  PubSub Event Bus    │
└────────┬────────┘        └────────┬─────────┘        └──────────────────────┘
         │                          │
         │ SSH over WireGuard        │ gRPC mTLS (agent_service.proto)
         ▼                          ▼
┌─────────────────┐        ┌──────────────────┐
│ Tunnel Gateway  │◄──────►│   Host Agent     │
│  [GO BINARY]    │ gorout. │  [GO BINARY]     │
│  10K+ conns     │        │  Firecracker/    │
└─────────────────┘        │  containerd/NVML │
                           └──────────────────┘
```

### Deployable Planes
1. **Control Plane** — Asynchronous FastAPI Python microservices (`api_gateway`, `auth_service`, `marketplace_service`, `provisioning_service`, `billing_service`, `ai_router_copilot_service`, `reputation_pricing_service`, `security_service`, `notifications_service`, `monitoring_service`, `host_service`).
2. **Data Plane** — PostgreSQL (source of truth), Redis (Pub/Sub event bus, rate limiting, session cache, denormalized search index), and Loki (structured log aggregation).
3. **Edge Plane (Tunnel Gateway)** — **Go static binary** (`backend/services/gateway_tunnel_go/`). Handles 10K+ concurrent SSH PTY sessions via goroutines. Replaces Python asyncssh implementation with ~9× lower latency.
4. **Host Plane (Host Agent)** — **Go static binary** (`backend/host_agent_go/`, ~14 MB, ~10 MB idle RAM). Uses cgo NVML for GPU benchmarking, Go SDK for Firecracker VMM + containerd, native LUKS2 with `crypto/rand` key zeroing, nftables via netlink, and LRU GC goroutine. Communicates with Python provisioning service via gRPC mTLS (`backend/proto/agent_service.proto`).
5. **Client Plane (CLI)** — **Go static binary** (`cli_go/`, ~8 MB, ~2 ms startup). Commands: `login`, `launch`, `connect` (native PTY SSH), `instances` (list/stop/terminate/status/logs), `wallet` (balance/transactions), `version`.

### Language Matrix
| Component | Language | Why |
|-----------|----------|-----|
| CLI | **Go** | 2 ms startup, static binary, native PTY |
| Host Agent | **Go** | goroutines, cgo NVML, Firecracker SDK |
| Gateway Tunnel | **Go** | 10K+ concurrent SSH goroutines |
| Provisioning, Auth, Billing, Marketplace, Wallet, Security | **Python** | SQLAlchemy, Stripe SDK, GST math, FastAPI |

---

## 🚀 Key Features

### 💻 Developer Experience & One-Command Launch Tooling
- **`kynetic launch`**: Single-command terminal workflow orchestrating search (`GET /search/listings`) ➔ listing selection ➔ instance provisioning (`POST /v1/instances`) ➔ auto-connection PTY shell without opening a browser. Supports `--gpu`, `--region`, `--max-price`, `--hours`, `--yes` (`-y`), and `--resume <instance_id>`.
- **`kynetic login`**: OAuth2 Device Authorization Grant flow for browser authentication from headless terminals.
- **`kynetic connect <instance_id>`**: Instant raw-mode PTY terminal session over reverse-dial WebSocket tunnel.
- **`kynetic cp <src> <dst>`**: 1MB chunked resumable file transfers with SHA-256 integrity checksums.
- **`kynetic ssh <instance_id>`**: Automatic `~/.ssh/config` block generator for seamless VS Code Remote SSH connectivity.
- **`kynetic tunnel`**: Local (`127.0.0.1:port`) and public (`https://tunnel.kynetic.ai/...`) port forwarding endpoints.

### 🧠 Weighted 6-Factor Scheduler & Smart Search Engine
- **Weighted 6-Factor Node Scoring (§9)**: Evaluates compute nodes based on Price Score (30%), FP32 TFLOPS & Benchmark Score (25%), Host Reputation Rating (20%), Regional Latency (15%), Hardware Availability (10%), plus a 5% anti-starvation randomization jitter band.
- **Multi-Attribute Smart Search Engine (v8 Feature 5)**: High-speed composable search query engine (`GET /v1/search/listings`) over a denormalized catalog (`searchable_listings`), filtering by GPU model, VRAM capacity, TFLOPS, health score, reputation composite score, verification level, price, region, and OS with cursor pagination.
- **GPU Benchmark Database (v8 Feature 4)**: Aggregated read-optimized analytics layer (`gpu_model_stats`, `price_performance_stats`) exposing aggregate TFLOPS, memory bandwidth, and score-per-dollar price/performance rankings (`GET /benchmarks/gpu-models`, `GET /benchmarks/price-performance`).

### 🌟 Host Reputation, Health Scores & Tiered Verification Program
- **GPU Benchmark & Rolling Health Engine (v8 Feature 1)**: Peer-group normalized FP16/FP32 TFLOPS and VRAM bandwidth benchmark scoring, min/max envelope fraud detection (`check_envelope`), and rolling 7-day thermal, clock, and power stability health scores.
- **Host Reputation System (v8 Feature 2)**: Immutable append-only audit event log (`reputation_events`), exponential time-decay score engine ($e^{-\lambda t}$, 30-day half-life), anti-gaming cancellation penalties (`-0.0200`), and automatic trust state transitions (`building_trust` ➔ `established` or `flagged`).
- **Verified Hosts Program (v8 Feature 3)**: Tiered host verification (`unverified` ➔ `silver` ➔ `gold` ➔ `enterprise`). Supports automated Silver auto-checks, Gold eligibility verification, admin document review queue, and revocation cascades (`-0.3500` reputation penalty).

### 💳 Marketplace Payments, Commission & Double-Entry Ledger (v7 Architecture)
- **3-Party Marketplace Payments**: Direct metered billing where customer payments are captured by the platform; per-second compute usage is recorded in the double-entry ledger; session termination triggers host earnings split.
- **Balanced Double-Entry Financial Ledger**: Immutable `LedgerEntry` rows (`debit == credit`) across `customer_account:{user_id}`, `platform_revenue`, `host_payable`, `tax_payable`, `provider_clearing`, and `refund_reserve`.
- **Priority-Based Commission Engine**: Priority rule resolution (`promotional` ➔ `host` ➔ `enterprise` ➔ `workload` ➔ `gpu_type` ➔ `region` ➔ `global_default`), splitting charges into platform commission and host net earnings.
- **Host Financial Onboarding & KYC**: App-layer encrypted PAN & bank credentials (`enc_v1_...`), onboarding state machine (`registered` ➔ `kyc_approved` ➔ `active`), and provider linked account creation.
- **Host Payout & Refund Engine**: Idempotent transfer execution (`reference_id = payout.id`), line-item traceability, manual review escalation, and platform `refund_reserve` buffer handling.

### 🔒 Zero-Trust Security & Plan v2 Security Enhancements (Parts 1 – 27)
- **Token Rotation & Audit Hash-Chaining**: Single-use `RefreshToken` family rotation with instant reuse revocation; SHA-256 hash-chained `AuditLog` records with external tip checkpointing & tamper verification (`security_service/audit_checkpoint.py`).
- **LUKS2 Ephemeral Encryption & NVMe TRIM**: Per-instance LUKS2 formatted storage with 512-bit AES-XTS keys held in memory only, zeroized on `shred()`, plus NVMe-native `blkdiscard` TRIM sanitization (`host_agent/volume_manager.py`).
- **TPM 2.0 Attestation & Host Trust Score**: TPM 2.0 signed quotes with single-use challenge nonces; Host Trust Score engine enforcing **Part 6.3 Hard Gate Rule** (attestation failure caps trust score at 29.0 `CRITICAL`, blocking scheduling; `trust_manager.py`).
- **8-Dimension Zero Trust PDP**: Policy Decision Point evaluating 8 dimensions (`identity`, `auth`, `authz`, `attestation`, `policy`, `risk`, `resource`, `operation`; `libs/common/zero_trust.py`).
- **Network Isolation & GPU Reset**: Per-instance `nftables` default-deny rulesets **blocking cloud metadata endpoint `169.254.169.254`** and cross-tenant traffic; `nvidia-smi --gpu-reset` VRAM zeroing verification on VM teardown (`network_isolation.py`, `firecracker.py`).
- **Container Hardening & Cosign Gate**: `STANDARD`, `HARDENED`, and `VERIFIED` container profiles with read-only root FS and capability dropping; Cosign Sigstore image signature admission gate (`container_profiles.py`, `image_scanner.py`, `.github/workflows/security_scan.yml`).
- **Runtime Risk Engine & Automated Containment**: 0–100 Composite Runtime Risk Engine with graduated response bands (`ALLOW`..`QUARANTINE`); risk-based Abuse Detector; Kynetic Secret Broker; automated host containment and workload quarantine (`runtime_monitor.py`, `abuse_detector.py`, `secret_broker.py`, `incident_response.py`).
- **Verified Compute Scheduler Filter**: Hard pre-filter stage filtering candidate hosts prior to ranking based on attestation status, secure boot, measured boot, LUKS2 active storage, and risk band (`verified_scheduler.py`).

---

## 🛠️ Installation & Quickstart

### Prerequisites
- Python 3.10+
- PostgreSQL 16+ & Redis 7+

### Install CLI
```bash
cd cli
pip install -e .
```

### Basic Workflow
```bash
# 1. Authenticate
kynetic login

# 2. Search & Launch compute via Smart Search
kynetic launch --gpu "RTX 4090" --max-price 2.00 --yes

# 3. Connect to remote PTY terminal (or auto-connected during launch)
kynetic connect inst-abc12345

# 4. Resume interrupted connection
kynetic launch --resume inst-abc12345

# 5. Copy files
kynetic cp ./dataset.tar.gz inst-abc12345:/workspace/

# 6. Configure VS Code Remote SSH
kynetic ssh inst-abc12345

# 7. Terminate instance
kynetic terminate inst-abc12345
```

---

## 🧪 Verification & Test Suite

Run the full platform test suite across all Implementation Plan v6 (Phases A–L), v7 (Phases P1–P7), v8 (Features 1–7), and Plan v2 Security Enhancements (Parts 1–27):

```bash
PYTHONPATH=backend pytest backend/tests/security cli/tests/test_cli_auth.py backend/tests/test_v6_phase_a_auth.py backend/tests/test_v6_phase_b_host_marketplace.py backend/tests/test_v6_phase_c_runtime.py backend/tests/test_v6_phase_d_agent_completion.py backend/tests/test_v6_phase_e_f_gateway_cli.py backend/tests/test_v6_phase_g_h_dx_scheduler.py backend/tests/test_v6_phase_i_j_k_l_launch_readiness.py backend/tests/test_v7_phase_1_2_payments_ledger.py backend/tests/test_v7_phase_3_4_kyc_commission.py backend/tests/test_v7_phase_5_6_7_payouts_refunds_dashboards.py backend/tests/test_v8_feature_1_benchmark_health_score.py backend/tests/test_v8_feature_2_3_reputation_verification.py backend/tests/test_v8_feature_4_5_6_search_launch.py
```

### Test Coverage Summary
- **Security Enhancements Suite (`backend/tests/security/`)**: **25 passed** (Token rotation, audit hash chaining, LUKS2 encryption, TPM 2.0 attestation, Trust Score hard gate, Zero Trust PDP, `nftables` isolation, GPU reset, container profiles, Cosign signature gate, Runtime Risk Engine, Abuse Detector, Secret Broker, Incident Response, Verified Scheduler, Audit tip checkpointing)
- **CLI & Core Auth Suite**: **5 passed** (Device authorization flow, credentials storage, token rotation, Auth Gateway API)
- **Host & Marketplace Suite**: **4 passed** (Host hardware detection, FLOPS benchmarking, mTLS certs, marketplace search)
- **Runtime Lifecycle Suite**: **3 passed** (Instance state machine, pre-flight validators, account billing readiness check)
- **Agent Completion Suite**: **4 passed** (PTY stream allocation, NVML telemetry, 3-pass DoD shredding)
- **Gateway & Tunnel Suite**: **2 passed** (WebSocket tunnel tickets, multiplexed PTY session)
- **Developer DX & Scheduler Suite**: **5 passed** (Chunked file transfer checksums, VS Code Remote SSH config, 6-factor scheduler ranking, host reputation & dashboard)
- **Launch Readiness Suite**: **5 passed** (Per-second metering & ledger recording, trust tier caps, emergency kill switch, cryptomining abuse detection, Prometheus metrics export)
- **Payments & Ledger Suite**: **3 passed** (Razorpay HMAC signature verification, database-level webhook replay protection, double-entry financial ledger & daily reconciliation validator)
- **KYC & Commission Suite**: **2 passed** (App-layer encrypted KYC submission, provider linked account creation on admin approval, priority commission resolution & host earnings split)
- **Payouts & Refunds Suite**: **4 passed** (Payout batching & transfer idempotency, manual review failure escalation, refund platform reserve buffer, Cashfree adapter, host/admin financial dashboards)
- **Benchmark & Health Suite**: **9 passed** (Peer-group normalized FP16/FP32 FLOPS, VRAM bandwidth, min/max envelope fraud detection, rolling 7-day health score, HostScore history)
- **Reputation & Verification Suite**: **5 passed** (Append-only reputation event log, time-decay engine, anti-gaming cancellation penalties, automatic Silver/Gold eligibility, admin Enterprise review & revocation cascades)
- **Smart Search & Launch Suite**: **5 passed** (GPU Benchmark Database analytics aggregation, side-by-side model comparison, search listing sync, multi-attribute smart search query engine, API routes, and `kynetic launch` CLI flags)

**Grand Total: 81 passed out of 81 tests (100% Success Rate)**.

---

## 📄 Documentation Index
- [17_Kynetic_AI_Security_Enhancements_Implementation_Plan_v2.md](Docs/Plans/17_Kynetic_AI_Security_Enhancements_Implementation_Plan_v2.md) — 27-Part End-to-End Security Architecture Specification & Roadmap
- [16_Implementation_Plan_v8.md](Docs/Plans/16_Implementation_Plan_v8.md) — GPU Benchmarks, Health Scores, Reputation, Verified Hosts, Smart Search & One Command Launch v8
- [15_Implementation_Plan_v7.md](Docs/Plans/15_Implementation_Plan_v7.md) — Marketplace Payment, Billing, Commission & Payout Architecture v7
- [14_Implementation_Plan_v6.md](Docs/Plans/14_Implementation_Plan_v6.md) — Production Engineering Specification & Master Roadmap v6
- [Implemented_Things.md](Docs/Implemented_Things.md) — Exhaustive Master Specification of Implemented Things (Phases 1–33, A–L, P1–P7, v8 Features 1–7, & Plan v2 Security Enhancements Parts 1–27)
- [Things_Left_To_Do_Live_Production.md](Docs/Things_Left_To_Do_Live_Production.md) — Itemized Production Activation Playbook & Security Hardening Guide
- [backend/README.md](backend/README.md) — Backend Microservices Architecture & Telemetry Specification
- [cli/README.md](cli/README.md) — 100% Python CLI Installation & Usage Guide
- [07_Security_Architecture.md](Docs/Plans/07_Security_Architecture.md) — Zero-Trust Security Specification

