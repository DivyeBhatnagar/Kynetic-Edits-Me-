# Kynetic AI — System Architecture & Design Specification

This document details the architectural layout, component interactions, security boundaries, control-plane channels, and data flows of the **Kynetic AI** platform.

---

## 1. High-Level System Architecture

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
                                    │ - Ephemeral LUKS2    │
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
- Redis (Session Cache + Rate Limiting + Celery Message Broker + Billing Event Bus)
- Prometheus & Grafana (Platform Metrics & Telemetry)
```

---

## 2. Microservice Topology

Kynetic AI comprises 11 decoupled Python FastAPI microservices:

1. **API Gateway (`:8000`)**: Single entry point for client requests. Enforces JWT signature verification, IP rate limiting (token bucket algorithm), and request proxying.
2. **Auth Service (`:8001`)**: Handles developer/host registration, password hashing (`bcrypt`), JWT token issuance/rotation (`PyJWT`), and phone OTP validation.
3. **Marketplace Service (`:8002`)**: Manages hardware listings, real-time compute availability search, and multi-resource scheduling (GPU + CPU + RAM + Storage).
4. **Provisioning Service (`:8003`)**: Orchestrates Firecracker MicroVM container creation, pre-flight validators, ephemeral LUKS2 disk formatting/shredding (`ephemeral_crypto.py`), and WireGuard peer tunnels.
5. **Wallet & Billing Service (`:8004`)**: Manages developer wallet balances, per-second metering tasks, dual-currency billing (USD/INR), Stripe payment integration, and 18% GST invoice generation.
6. **AI Router & Copilot Service (`:8005`)**: Matches natural language workload requests (e.g. *"Fine-tune Llama 3 8B"*) to optimal hardware listings with transparent scoring algorithms.
7. **Reputation & Pricing Service (`:8006`)**: Computes dynamic hourly pricing using machine learning algorithms and maintains a 6-factor host reputation score.
8. **Security Service (`:8007`)**: Executes platform security controls, kill-switch suspensions, container image scanning, trust tier governance, and security event audit logs.
9. **Host Service (`:8008`)**: Ingests host hardware heartbeats, NVML GPU telemetry, and agent status.
10. **Notifications Service (`:8010`)**: Dispatches email alerts (SendGrid/SMTP), low-balance warnings, and rental event webhooks.
11. **Monitoring Service (`:8011`)**: Exposes Prometheus metrics scrapers and platform health check aggregators.

---

## 3. Five-Layer Zero-Trust Security Fortress

```
+-----------------------------------------------------------------------------------+
| LAYER 1: CHACHA20-POLY1305 RAM ENCRYPTION OVERLAY + MADV_DONTDUMP (0x11)          |
+-----------------------------------------------------------------------------------+
                                       |
                                       v  [Interception via gVisor User-Space Kernel]
+-----------------------------------------------------------------------------------+
| LAYER 2: gVISOR (runsc) + SECCOMP-BPF SYSCALL FIREWALL                            |
+-----------------------------------------------------------------------------------+
                                       |
                                       v  [Anti-Debugging: prctl(PR_SET_DUMPABLE, 0)]
+-----------------------------------------------------------------------------------+
| LAYER 3: ANTI-DEBUGGING & ANTI-PTRACE ENFORCEMENT                                 |
+-----------------------------------------------------------------------------------+
                                       |
                                       v  [eBPF XDP RFC 1918 LAN Micro-Segmentation]
+-----------------------------------------------------------------------------------+
| LAYER 4: eBPF KERNEL NETWORK FIREWALL                                             |
+-----------------------------------------------------------------------------------+
                                       |
                                       v  [15-Second Challenge Nonce Attestation]
+-----------------------------------------------------------------------------------+
| LAYER 5: DYNAMIC TPM 2.0 PCR ATTESTATION ENGINE                                   |
+-----------------------------------------------------------------------------------+
```

---

## 4. Phase 27–33 Control-Plane Infrastructure Architecture

### 4.1 Pre-Flight Validation Gate (`validators.py`)
Centralized atomic DB pre-flight checks executed prior to instance scheduling:
- **Permission Check**: Verifies requester is either the developer or a system administrator.
- **Listing Availability**: Ensures target listing is active (not paused or delisted).
- **Host Status & Freshness**: Confirms host is verified/listed and has emitted a heartbeat within 60 seconds (`status != offline`).
- **Wallet Balance Calculation**: Calculates required hold amount ($\text{hold\_amount} = \text{price\_per\_hour} \times \text{requested\_hours}$) and verifies developer wallet balance exceeds hold requirement.

### 4.2 Billing Event Integration (`bus.py` & `metering.py`)
- **Redis Pub/Sub Event Bus**: Runs on Redis DB 3 for lifecycle state events (`INSTANCE_RUNNING`, `INSTANCE_TERMINATED`, `INSTANCE_FAILED`).
- **Status Sync Publisher**: Formats canonical events with microsecond timestamps and publishes events upon state machine transitions.
- **Per-Second Metering Worker**: Celery task `debit_running_instance` executes every 10 seconds per running instance, deducting per-second usage from wallet balance and releasing unspent hold balances upon termination.

### 4.3 Host Agent Command Channel (`host_commands.py` & `command_listener.py`)
- **Typed gRPC / mTLS Contract**: Enforces strict payload contracts (`proto/host_agent.proto`) for `Launch`, `Stop`, `Terminate`, and `StreamStatus`.
- **Deduplication Ring Buffer**: Agent-side `idempotency_store` maintains a thread-safe ring buffer preventing duplicate execution of replayed command keys.
- **DB Audit Logging**: Every command invocation records a row in `host_commands` (`idempotency_key`, `dispatched_at`, `completed_at`, `status`, `error_message`).

### 4.4 Audit & Provisioning Diagnostics (`audit.py` & `diagnostics.py`)
- **Audit Logging**: `log_instance_event` and `log_validation_rejection` record structured logs to stdout and append-only rows to `audit_logs`.
- **Diagnostics Collector**: `JobDiagnostics` tracks timing breakdowns (image pull, volume creation, microVM boot) and captures failure stack traces.

### 4.5 Testing Architecture
- **82 Unit Tests**: Covers state machine legal/illegal transitions, host agent workload engine, Fernet SSH encryption, WireGuard IP allocation, deletion receipts, and FastAPI TestClient routes.
- **6 Integration Tests**: Verifies end-to-end lifecycle, pre-flight validation blocks, host agent disconnect recovery, zero-balance auto-termination, and command channel idempotency replay prevention.
