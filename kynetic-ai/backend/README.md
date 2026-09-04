# Kynetic AI — Backend & Microservices Engine

[![Go Version](https://img.shields.io/badge/Go-1.22%2B-00ADD8.svg)](https://go.dev/)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111.0-009688.svg)](https://fastapi.tiangolo.com/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0%20Async-red.svg)](https://www.sqlalchemy.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791.svg)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-Pub%2FSub%20%26%20Cache-dc382d.svg)](https://redis.io/)
[![Pytest](https://img.shields.io/badge/pytest-81%20passing%20tests-brightgreen.svg)](https://docs.pytest.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

The **Kynetic AI Backend** powers a decentralized compute marketplace connecting GPU compute providers with AI/ML developers. The system employs a high-performance **Hybrid Go/Python** architecture:
- **Go** for performance-critical I/O and low-level virtualization: **Host Agent Daemon** (`backend/host_agent_go/`) and **NAT-Traversing Gateway Tunnel** (`backend/services/gateway_tunnel_go/`).
- **Python (FastAPI)** for core control plane services: provisioning, billing ledger, 3-party marketplace payments, priority commission resolution, host KYC onboarding, zero-trust PDP, GPU benchmark analytics, and multi-attribute smart search.

---

## 🏛️ Architecture Breakdown

```
                             ┌────────────────────────┐
                             │   Developer Terminal   │
                             │   kynetic [GO CLI]     │
                             └───────────┬────────────┘
                                         │
                 ┌───────────────────────┴───────────────────────┐
                 │ REST / OAuth2                                 │ SSH / PTY WebSocket
                 ▼                                               ▼
┌─────────────────────────────────┐             ┌─────────────────────────────────┐
│     FastAPI API Gateway         │             │    Gateway Tunnel [GO BINARY]   │
│     (Port 8000)                 │             │    (Port 8008 - 12K+ conns)     │
└────────────────┬────────────────┘             └────────────────┬────────────────┘
                 │ Internal REST / Event Bus                     │ Reverse WebSocket
                 ▼                                               ▼
┌─────────────────────────────────┐             ┌─────────────────────────────────┐
│ Control Plane Microservices     │◄───gRPC────►│    Host Agent Daemon [GO]       │
│ (Provisioning, Billing, Auth,   │    mTLS     │    (Firecracker VMM, NVML,      │
│  Marketplace, Security, Payout) │             │     LUKS2, nftables isolation)  │
└─────────────────────────────────┘             └─────────────────────────────────┘
```

---

## ⚡ Core Subsystems & Components

### 1. 🖥️ Go Host Agent Daemon ([`host_agent_go/`](host_agent_go/))
- **~14 MB Static Binary / ~10 MB Idle RAM**: 78% reduction in host memory usage compared to Python.
- **cgo NVML Hardware Discovery**: Live 10s streaming of VRAM, GPU core clocks, temperature, power, and fan speed directly from `libnvidia-ml.so`.
- **PyTorch-Free Ctypes & Native GEMM Benchmarking**: Measures FP16/FP32 TFLOPS and VRAM bandwidth without bundling heavy Python ML dependencies.
- **Firecracker MicroVM & containerd eStargz**: Spawns isolated microVMs with minimal Alpine rootfs (`rootfs-min.ext4` ~45 MB) and stripped kernel (`vmlinux-min` ~12 MB) for sub-2s cold starts.
- **LUKS2 Zero-Trace Encryption**: Per-instance 512-bit AES-XTS encrypted disks with in-memory keys zeroed via `crypto/rand`, followed by NVMe `blkdiscard` TRIM sanitization.
- **nftables Tenant Isolation**: Hard blocks to Cloud Metadata (`169.254.169.254`) and cross-tenant network traffic.
- **mTLS gRPC Channel**: Direct control-plane communication via Protobuf (`backend/proto/agent_service.proto`).

### 2. 🔌 Go Gateway Tunnel ([`services/gateway_tunnel_go/`](services/gateway_tunnel_go/))
- **12,000+ Concurrent PTY Tunnels**: Replaces Python async event loop with Go goroutines, eliminating GIL lockups.
- **2 ms First-Byte Latency**: 9× latency reduction for interactive terminal sessions.
- **NAT-Traversing Reverse Dial**: Eliminates firewall port forwarding requirements for compute hosts.

### 3. 🤖 Intent-Based AI Router & 6-Factor Scheduler ([`services/ai_router_copilot_service/`](services/ai_router_copilot_service/))
- **6-Factor Weighted Node Scoring Engine**: Evaluates compute nodes based on GPU Match (30%), Benchmark Score (25%), Host Reputation (20%), Latency (15%), Price Efficiency (10%), and Availability (10%), plus a 5% anti-starvation jitter band.
- **Scheduler Hints**: Supports `balanced`, `budget`, and `fastest` execution profiles.

### 4. 💳 Marketplace Payments, Priority Commission & Double-Entry Ledger ([`services/wallet_billing_service/`](services/wallet_billing_service/), [`services/payout_service/`](services/payout_service/))
- **3-Party Payments**: Platform captures customer payments; per-second usage is metered; host settlement occurs at session termination.
- **Balanced Double-Entry Financial Ledger**: Immutable `LedgerEntry` rows enforcing `debit == credit` across `customer_account`, `platform_revenue`, `host_payable`, `tax_payable`, `provider_clearing`, and `refund_reserve`. Includes daily automated reconciliation.
- **Priority-Based Commission Resolver**: Evaluates rules in priority order (`promotional` ➔ `host` ➔ `enterprise` ➔ `workload` ➔ `gpu_type` ➔ `region` ➔ `global_default`).
- **Host Financial Onboarding & KYC**: App-layer encrypted PAN & bank credentials with automated transfer batching ($50 min threshold) and idempotency keys.

### 5. 🌟 GPU Benchmarks, Rolling Health & Verified Hosts ([`services/reputation_pricing_service/`](services/reputation_pricing_service/))
- **Peer-Group Normalization**: Normalizes measured TFLOPS against expected GPU envelopes to detect throttling or fraudulent reporting.
- **Rolling 7-Day Health Score**: Thermal, clock, and power stability scoring from 10s NVML telemetry.
- **Host Reputation Engine**: Append-only audit logs with exponential time-decay ($e^{-\lambda t}$, 30-day half-life) and anti-gaming cancellation penalties.
- **Tiered Host Verification**: `unverified` ➔ `silver` ➔ `gold` ➔ `enterprise` tiers with automated verification and revocation cascades.

### 6. 🔒 Zero-Trust Security Controls ([`services/security_service/`](services/security_service/))
- **8-Dimension Policy Decision Point (PDP)**: Zero-trust authorization covering identity, attestation, policy, risk, and hardware state.
- **TPM 2.0 Attestation Engine**: Hardware-signed quotes with single-use nonces enforcing hard scheduling gates.
- **SHA-256 Audit Hash Chaining**: Tamper-evident append-only audit trail with external tip checkpointing.
- **Runtime Risk Engine & Abuse Containment**: Composite risk evaluation triggering instant workload quarantine or host suspension.

---

## 🧪 Running the Backend Tests

Run the full platform test suite (81 tests, 100% pass rate):

```bash
DATABASE_URL="sqlite+aiosqlite:///:memory:" pytest \
  backend/tests/security \
  cli/tests/test_cli_auth.py \
  backend/tests/test_v6_phase_a_auth.py \
  backend/tests/test_v6_phase_b_host_marketplace.py \
  backend/tests/test_v6_phase_c_runtime.py \
  backend/tests/test_v6_phase_d_agent_completion.py \
  backend/tests/test_v6_phase_e_f_gateway_cli.py \
  backend/tests/test_v6_phase_g_h_dx_scheduler.py \
  backend/tests/test_v6_phase_i_j_k_l_launch_readiness.py \
  backend/tests/test_v7_phase_1_2_payments_ledger.py \
  backend/tests/test_v7_phase_3_4_kyc_commission.py \
  backend/tests/test_v7_phase_5_6_7_payouts_refunds_dashboards.py \
  backend/tests/test_v8_feature_1_benchmark_health_score.py \
  backend/tests/test_v8_feature_2_3_reputation_verification.py \
  backend/tests/test_v8_feature_4_5_6_search_launch.py
```
