# Kynetic AI — Decentralized Cloud Computer Marketplace

> **The terminal, not the browser, is the product.**

Kynetic AI connects compute hosts (datacenter servers, idle mining rigs, gaming PCs) with developers who need high-performance GPU/CPU Linux compute right now. Kynetic delivers raw, unmediated terminal access (`kynetic connect`) to a remote Linux machine in seconds — with no notebooks, no web IDE, and zero configuration of firewalls, security groups, or IP addresses.

---

## 🏛️ System Architecture

Kynetic is built on a 5-plane decoupled architecture operating on a **100% Python Native Stack**:

```
┌─────────────────┐        ┌──────────────────┐        ┌──────────────────────┐
│  Web Dashboard  │◄──────►│   Control Plane  │◄──────►│  PostgreSQL 16 DB    │
│  (Next.js App)  │  REST  │  (FastAPI Async) │  SQL   │  (source of truth)   │
└─────────────────┘        └────────┬─────────┘        └──────────────────────┘
                                    │
┌─────────────────┐        ┌────────▼─────────┐        ┌──────────────────────┐
│   Kynetic CLI   │◄──────►│   API Gateway    │◄──────►│  Redis 7 Cache /     │
│  (Python CLI)   │  REST  │   + Auth         │        │  PubSub Event Bus    │
└────────┬────────┘        └────────┬─────────┘        └──────────────────────┘
         │                          │
         │ WebSocket Tunnel         │ mTLS Command Channel
         ▼                          ▼
┌─────────────────┐        ┌──────────────────┐
│  Tunnel Gateway │◄──────►│    Host Agent    │
│  (Edge Relay)   │ reverse│  (Compute Node)  │
└─────────────────┘  dial  └──────────────────┘
```

### Deployable Planes
1. **Control Plane** — Asynchronous FastAPI microservices for Auth, Marketplace, Provisioning, Billing, Security, and Scheduling.
2. **Data Plane** — PostgreSQL (source of truth), Redis (Pub/Sub event bus, rate limiting, session cache), and Loki (structured log aggregation).
3. **Edge Plane (Tunnel Gateway)** — NAT-traversing reverse-dial WebSocket relay cluster that terminates developer PTY streams and host connections without open inbound ports on the host.
4. **Host Plane (Host Agent)** — Cross-platform Python daemon running on rented compute nodes, managing hardware discovery, NVML telemetry, Firecracker MicroVM containers, and DoD 3-pass storage shredding.
5. **Client Plane (CLI)** — 100% Python CLI (`kynetic-cli`) providing a native, instant developer experience (`login`, `launch`, `connect`, `cp`, `tunnel`, `ssh`).

---

## 🚀 Key Features

### 💻 Developer Experience & CLI Tooling
- **`kynetic login`**: OAuth2 Device Authorization Grant flow for browser authentication from headless terminals.
- **`kynetic connect <instance_id>`**: Instant raw-mode PTY terminal session over reverse-dial WebSocket tunnel.
- **`kynetic cp <src> <dst>`**: 1MB chunked resumable file transfers with SHA-256 integrity checksums.
- **`kynetic ssh <instance_id>`**: Automatic `~/.ssh/config` block generator for seamless VS Code Remote SSH connectivity.
- **`kynetic tunnel`**: Local (`127.0.0.1:port`) and public (`https://tunnel.kynetic.ai/...`) port forwarding endpoints.

### 🧠 Weighted 6-Factor Scheduler (§9)
- Dynamic host selection algorithm:
  - **Price Score** (30%)
  - **FP32 TFLOPS & Benchmark Score** (25%)
  - **Host Reputation Rating** (20%)
  - **Regional Latency** (15%)
  - **Hardware Availability** (10%)
  - **Anti-Starvation Randomization** (+5% jitter)
- CLI Hints: `--budget` (price-weighted), `--fastest` (performance-weighted), or `--balanced` (default).

### 🔒 Zero-Trust Security & Host Agent Hardening
- **Progressive Trust Tiers**: Spend & instance limit caps (`Tier 1`: $10/hr max; `Tier 2`: $50/hr max; `Tier 3`: unlimited).
- **Device Fingerprinting**: Client signal SHA-256 fingerprinting on user authentication.
- **Platform Emergency Kill Switch**: Instant administrative revocation of compromised instances/hosts/accounts (`POST /v1/security/kill-switch`).
- **Cryptomining Abuse Detector**: Pre-execution OCI container image safety scanning and runtime process command-line inspection (`xmrig`, `ethminer`, `stratum+tcp://`).
- **Cryptographic Storage Shredding**: 3-pass DoD 5220.22-M data wiping (`shred -n 3 -z`) with cryptographic `SecureDeletionReceipt`.

### 💳 Marketplace Payments, Commission & Double-Entry Ledger (v7 Architecture)
- **3-Party Marketplace Payments**: Customer payments are captured directly by the Kynetic platform account; per-second metered compute usage is recorded in the double-entry ledger; session termination triggers host earnings split.
- **Balanced Double-Entry Financial Ledger**: Immutable `LedgerEntry` rows (`debit == credit`) across `customer_account:{user_id}`, `platform_revenue`, `host_payable`, `tax_payable`, `provider_clearing`, and `refund_reserve`.
- **Priority-Based Commission Engine**: Evaluates active rules in priority order (`promotional` ➔ `host` ➔ `enterprise` ➔ `workload` ➔ `gpu_type` ➔ `region` ➔ `global_default`), splitting charges into platform commission and host net earnings (`v7_host_earnings`).
- **Host Financial Onboarding & KYC**: App-layer encrypted PAN & bank credentials (`enc_v1_...`), onboarding state machine (`registered` ➔ `kyc_approved` ➔ `active`), and provider linked account creation (`PaymentProviderAccount`).
- **Host Payout Engine**: Idempotent transfer execution (`reference_id = payout.id`), line-item traceability, and failure recovery with `manual_review` escalation.
- **Refund Engine & Platform Reserve Buffer**: Refund processing with platform `refund_reserve` handling for refunds requested after host payout.
- **Payment Provider Abstraction**: Unified `PaymentProviderInterface` supporting `RazorpayRouteAdapter`, `CashfreeEasySplitAdapter`, and `StripeConnectAdapter`.

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

# 2. Search compute listings
kynetic search --gpu "RTX 4090" --max-price 2.00

# 3. Launch an instance
kynetic launch --gpu "RTX 4090" --fastest

# 4. Connect to remote PTY terminal
kynetic connect inst-abc12345

# 5. Copy files
kynetic cp ./dataset.tar.gz inst-abc12345:/workspace/

# 6. Configure VS Code Remote SSH
kynetic ssh inst-abc12345

# 7. Terminate instance
kynetic terminate inst-abc12345
```

---

## 🧪 Verification & Test Suite

Run the full platform test suite across all Implementation Plan v6 (Phases A–L) and v7 (Phases P1–P7) Phases:

```bash
DATABASE_URL="sqlite+aiosqlite:///:memory:" .venv/bin/pytest cli/tests/test_cli_auth.py backend/tests/test_v6_phase_a_auth.py backend/tests/test_v6_phase_b_host_marketplace.py backend/tests/test_v6_phase_c_runtime.py backend/tests/test_v6_phase_d_agent_completion.py backend/tests/test_v6_phase_e_f_gateway_cli.py backend/tests/test_v6_phase_g_h_dx_scheduler.py backend/tests/test_v6_phase_i_j_k_l_launch_readiness.py backend/tests/test_v7_phase_1_2_payments_ledger.py backend/tests/test_v7_phase_3_4_kyc_commission.py backend/tests/test_v7_phase_5_6_7_payouts_refunds_dashboards.py
```

### Test Coverage Summary
- `test_cli_auth.py`: **4 passed** (Device authorization flow, credentials storage, token rotation)
- `test_v6_phase_a_auth.py`: **1 passed** (Auth Gateway device verify API)
- `test_v6_phase_b_host_marketplace.py`: **4 passed** (Host hardware detection, FLOPS benchmarking, mTLS certs, marketplace search)
- `test_v6_phase_c_runtime.py`: **3 passed** (Instance state machine, pre-flight validators, account billing readiness check)
- `test_v6_phase_d_agent_completion.py`: **4 passed** (PTY stream allocation, 10s NVML telemetry, 3-pass DoD shredding)
- `test_v6_phase_e_f_gateway_cli.py`: **2 passed** (WebSocket tunnel tickets, multiplexed PTY session)
- `test_v6_phase_g_h_dx_scheduler.py`: **5 passed** (Chunked file transfer checksums, VS Code Remote SSH config, 6-factor scheduler ranking, host reputation & dashboard)
- `test_v6_phase_i_j_k_l_launch_readiness.py`: **5 passed** (Per-second metering & ledger recording, trust tier caps, emergency kill switch, cryptomining abuse detection, Prometheus metrics export)
- `test_v7_phase_1_2_payments_ledger.py`: **3 passed** (Razorpay HMAC signature verification, database-level webhook replay protection, double-entry financial ledger & daily reconciliation validator)
- `test_v7_phase_3_4_kyc_commission.py`: **2 passed** (App-layer encrypted KYC submission, provider linked account creation on admin approval, priority commission resolution & host earnings split)
- `test_v7_phase_5_6_7_payouts_refunds_dashboards.py`: **4 passed** (Payout batching & transfer idempotency, manual_review failure escalation, refund platform reserve buffer, Cashfree adapter, and host/admin financial dashboards)

**Grand Total: 37 passed out of 37 tests in 4.03s (100% Success Rate)**.

---

## 📄 Documentation Index
- [15_Implementation_Plan_v7.md](Docs/Plans/15_Implementation_Plan_v7.md) — Marketplace Payment, Billing, Commission & Payout Architecture v7
- [14_Implementation_Plan_v6.md](Docs/Plans/14_Implementation_Plan_v6.md) — Production Engineering Specification & Master Roadmap v6
- [12_Implemented_Things.md](Docs/Plans/12_Implemented_Things.md) — Master Architecture Specification of Implemented Things (Phases 1–33, A–L, P1–P7)
- [backend/README.md](backend/README.md) — Backend Microservices Architecture & Telemetry Specification
- [cli/README.md](cli/README.md) — 100% Python CLI Installation & Usage Guide
- [07_Security_Architecture.md](Docs/Plans/07_Security_Architecture.md) — Zero-Trust Security Specification
