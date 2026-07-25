# Kynetic AI — Backend & Microservices Engine

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111.0-009688.svg)](https://fastapi.tiangolo.com/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0%20Async-red.svg)](https://www.sqlalchemy.org/)
[![Redis](https://img.shields.io/badge/Redis-Pub%2FSub%20%26%20Cache-dc382d.svg)](https://redis.io/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791.svg)](https://www.postgresql.org/)
[![Pytest](https://img.shields.io/badge/pytest-88%20passing-brightgreen.svg)](https://docs.pytest.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

The **Kynetic AI Backend** powers a resource-agnostic compute marketplace connecting idle GPU/CPU hardware with AI/ML developers. The backend architecture consists of **11 asynchronous FastAPI microservices**, a cross-platform **Python Host Agent daemon**, shared core libraries, a **double-entry financial ledger** with per-second micro-metering, and an automated Pytest test suite with **88 passing unit and integration tests**.

---

## ⚡ Comprehensive Feature Breakdown

### 1. 🤖 Intent-Based AI Router & Copilot
- **Natural Language Parsing**: Accepts human intent (e.g., *"Find an RTX 4090 under $1.50/hr for LoRA fine-tuning"*) and extracts hardware requirements (VRAM headroom, compute TFLOPS, memory bandwidth).
- **6-Factor Weighted Node Scoring Engine**: Evaluates available compute nodes based on:
  1. **GPU/Compute Match Score** (30%)
  2. **VRAM Headroom** (20%)
  3. **Host Reputation & Trust Rating** (20%)
  4. **Network Latency & Geo Proximity** (15%)
  5. **Price Efficiency** (10%)
  6. **Uptime History & Health** (5%)
- **Custom Parameters Tuner**: Allows developers to adjust weights, set max hourly rates, specify preferred regions, and select isolation tiers.

### 2. 🖥️ Host Agent Daemon (`host_agent/`)
- **GPU Discovery & NVML Telemetry**: Utilizes `pynvml` to inspect GPU models (RTX 4090, A100, H100, L40S) and capture real-time telemetry: VRAM utilization, GPU core clock, temperature (°C), fan speed (%), and power draw (Watts).
- **Hardware Benchmarking Suite**: Automatically benchmarks compute nodes upon onboarding: FP32 TFLOPS, memory bandwidth (GB/s), NVMe disk sequential/random IOPS, and network upload/download throughput.
- **Firecracker MicroVM & Container Isolation**: Spawns isolated microVM runtimes with custom rootfs images, non-root execution, and ephemeral volume allocation.
- **WireGuard NAT Relay**: Configures point-to-point encrypted WireGuard VPN tunnels for nodes operating behind NAT or residential firewalls.
- **Control Channel & Idempotency Store**: Receives control commands (`launch`, `stop`, `terminate`, `snapshot`) backed by an idempotency token store preventing duplicate executions.

### 3. 🔒 Zero-Trust Security & Pre-Flight Logic Gate
- **Pre-Flight Validation Gate**: Enforces business logic rules before scheduling instance creation:
  - Validates user wallet balance against estimated rental holds (USD or INR).
  - Checks compute listing availability and host reservation lock.
  - Verifies host node heartbeat freshness (< 120s) and NVML health indicators.
  - Verifies host trust tier and rejection of suspended or unverified hosts.
- **Fernet Ephemeral SSH Key Management**:
  - Generates 4096-bit RSA keypairs (`OpenSSH` public key + PKCS8 PEM private key).
  - Encrypts private keys using **AES-256 Fernet** prior to database storage (`ssh_sessions`).
  - Automatically formats ready-to-use SSH commands (`ssh -i kynetic_key.pem -p <port> user@host`).
  - Supports automatic key rotation deadlines and cryptographic private key nulling upon session revocation.
- **Emergency System Kill-Switch**: Admin API endpoint (`POST /security/kill-switch`) that revokes credentials, isolates WireGuard network interfaces, and triggers 3-pass DoD 5220.22-M storage shredding (`shred -n 3 -z`).
- **eBPF XDP Firewall Generator**: Constructs eBPF filters dropping packets bound for RFC 1918 private subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`).

### 4. 💳 Dual-Currency Billing & Metering Engine
- **Multi-Currency Wallet**: Supports both **USD ($)** and **INR (₹)** balances.
- **Stripe & Razorpay Integration**:
  - **Stripe**: Credit/Debit card processing and payment intent webhooks.
  - **Razorpay**: Indian UPI (GPay, PhonePe, Paytm), Netbanking, and Razorpay signature verification.
- **Per-Second Micro-Metering**: Redis Pub/Sub event bus (`billing.event`) tracks running instance duration down to the exact second, executing real-time wallet balance debits.
- **Double-Entry Financial Ledger**: Maintains strict transactional integrity across wallet top-ups, reservation holds, usage debits, and refund credits (`transactions` table).
- **Sequential 18% GST Invoicing**: Automatically generates tax-compliant invoices in `KYN/2024-25/XXXXXX` format with breakdown of CGST (9%), SGST (9%), or IGST (18%).

### 5. 📊 Telemetry, Monitoring & Notifications
- **Prometheus Metrics Exporter**: Collects system-wide scrapers and custom metrics across all microservices.
- **Health Scraper**: Periodically verifies operational status (`/health`) across all 11 microservices.
- **In-App Notification Dispatcher**: Jinja2-rendered email templates and real-time database notifications for low wallet balances, host disconnects, instance state changes, and invoice generation.

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

## 🧩 Comprehensive Microservices Directory

The backend is composed of **11 independent FastAPI services** located in `services/`:

| Service Name | Port | Key Modules & Components | Primary Responsibilities |
| :--- | :--- | :--- | :--- |
| **`api_gateway`** | `:8000` | `main.py`, `rate_limiter.py`, `router.py` | Single public entry point, JWT validation, Redis token-bucket rate limiting, CORS configuration, request routing. |
| **`auth_service`** | `:8001` | `main.py`, `routes.py`, `security.py`, `otp.py` | User signup & login, bcrypt password hashing (12 salt rounds), PyJWT token issuance & refresh rotation, email/SMS OTP verification. |
| **`marketplace_service`** | `:8002` | `main.py`, `routes.py`, `repository.py`, `search.py` | Compute hardware catalog, multi-param search engine (GPU model, VRAM, RAM, region, price), hardware listing management. |
| **`provisioning_service`** | `:8003` | `main.py`, `routes.py`, `validators.py`, `ssh_keys.py`, `wireguard.py`, `host_commands.py`, `audit.py` | Instance lifecycle state machine (`PENDING` ➔ `PROVISIONING` ➔ `RUNNING` ➔ `STOPPED` ➔ `TERMINATED`), pre-flight gate, Fernet SSH key encryption, WireGuard IP allocation, audit logging. |
| **`wallet_billing_service`** | `:8004` | `main.py`, `routes.py`, `stripe_client.py`, `razorpay_client.py`, `metering.py`, `invoice.py` | Dual-currency wallets (USD/INR), Stripe card checkout, Razorpay UPI/Netbanking, per-second metering engine, double-entry ledger, 18% GST tax invoices. |
| **`ai_router_copilot_service`** | `:8005` | `main.py`, `routes.py`, `copilot.py`, `ranking.py` | Natural language intent parser, 6-factor weighted node scoring algorithm, workload preset matcher, Copilot session manager. |
| **`reputation_pricing_service`** | `:8006` | `main.py`, `routes.py`, `reputation.py`, `pricing.py` | Host 6-factor trust score calculation, dynamic auto-pricing engine based on hardware demand & node uptime. |
| **`security_service`** | `:8007` | `main.py`, `routes.py`, `kill_switch.py`, `trust_tier.py`, `image_scanner.py` | Admin emergency kill-switch, host trust tier verification, container image security scanner, fraud detector. |
| **`notifications_service`** | `:8010` | `main.py`, `routes.py`, `notifier.py`, `templates/` | Email dispatching via Jinja2 templates, in-app notification center, low balance alerts, heartbeat disconnect alerts. |
| **`monitoring_service`** | `:8011` | `main.py`, `routes.py`, `metrics.py`, `health_check.py` | Prometheus metrics scrapers, health check polling across all 11 microservices, telemetry aggregation. |
| **`host_service`** | `:8008` | `main.py`, `routes.py`, `telemetry.py`, `benchmarks.py` | Host node onboarding, heartbeat ingestion, NVML GPU telemetry processing, hardware benchmark result storage. |

---

## 🗄️ Database Schema & Models (`libs/db_models/`)

Managed via **SQLAlchemy 2.0 Async** and **Alembic**:

1. **`User`**: `id`, `email`, `password_hash`, `full_name`, `role` (`developer`, `host`, `admin`), `is_active`, `is_verified`, `created_at`.
2. **`HostNode`**: `id`, `user_id`, `name`, `ip_address`, `wireguard_ip`, `status` (`pending`, `active`, `suspended`), `reputation_score`, `trust_tier`, `last_heartbeat_at`.
3. **`HardwareBenchmark`**: `id`, `host_id`, `gpu_model`, `gpu_vram_mb`, `fp32_tflops`, `memory_bandwidth_gbps`, `nvme_iops`, `network_mbps`, `tested_at`.
4. **`ComputeListing`**: `id`, `host_id`, `title`, `gpu_model`, `gpu_count`, `vram_gb`, `cpu_cores`, `ram_gb`, `hourly_rate_usd`, `hourly_rate_inr`, `is_available`, `region`.
5. **`ComputeInstance`**: `id`, `developer_id`, `listing_id`, `host_id`, `status` (`provisioning`, `running`, `stopped`, `terminated`), `ssh_port`, `wireguard_ip`, `started_at`, `stopped_at`, `billed_seconds`, `hold_amount`.
6. **`SSHSession`**: `id`, `instance_id`, `public_key`, `private_key_encrypted`, `issued_at`, `revoked_at`.
7. **`Wallet`**: `id`, `user_id`, `usd_balance`, `inr_balance`, `preferred_currency`, `updated_at`.
8. **`Transaction`**: `id`, `wallet_id`, `amount`, `currency`, `type` (`topup`, `hold`, `debit`, `refund`), `reference_id`, `description`, `created_at`.
9. **`Invoice`**: `id`, `user_id`, `invoice_number`, `amount_total`, `tax_amount`, `gst_number`, `currency`, `pdf_url`, `created_at`.
10. **`Notification`**: `id`, `user_id`, `title`, `message`, `type` (`info`, `warning`, `error`, `success`), `is_read`, `created_at`.
11. **`SecurityAuditLog`**: `id`, `user_id`, `action`, `resource_type`, `resource_id`, `ip_address`, `status`, `metadata_json`, `created_at`.

---

## 🧪 Comprehensive Pytest Test Suite (`tests/`)

The backend contains **88 passing unit and integration tests**:

```bash
# Execute unit test suite
cd backend
PYTHONPATH=. python3 -m pytest tests/unit/ -v

# Execute integration & e2e test suite
PYTHONPATH=. python3 -m pytest tests/integration/ -v

# Execute full test suite
PYTHONPATH=. python3 -m pytest tests/ -v
```

### Complete List of Tested Scenarios (88 Passed):
- `test_log_instance_event_creates_audit_log_row`: Verifies audit log entry creation on instance events.
- `test_log_validation_rejection_creates_audit_log_row`: Tests audit log logging when pre-flight validation fails.
- `test_job_diagnostics_success_metrics`: Verifies job metrics recording upon success.
- `test_job_diagnostics_failure_capture`: Verifies error diagnostic capture on instance failure.
- `test_publish_event_success`: Tests publishing billing events to Redis Pub/Sub.
- `test_publish_event_handles_redis_failure`: Verifies fallback handling when Redis connection drops.
- `test_status_sync_on_instance_running`: Tests Redis status sync when an instance starts running.
- `test_status_sync_on_instance_terminated`: Tests status sync when an instance is terminated.
- `test_status_sync_on_instance_failed`: Tests status sync on instance failure.
- `test_metering_debit_calculation`: Verifies exact per-second billing debit amounts.
- `test_hold_refund_calculation`: Verifies refund calculations when instance runs for less than hold duration.
- `test_gst_inclusive_calculation`: Tests 18% GST tax calculation split (CGST 9% + SGST 9%).
- `test_gst_inclusive_fractional`: Verifies rounding precision for fractional GST amounts.
- `test_fiscal_year_invoice_number_formatting`: Verifies sequential `KYN/2024-25/XXXXXX` invoice formatting.
- `test_per_second_billing_accuracy`: Verifies high-precision per-second billing math.
- `test_currency_conversion`: Tests USD to INR conversion rate calculations.
- `test_reservation_hold_amount`: Verifies pre-flight wallet hold amounts based on hourly rates.
- `test_secure_deletion_receipt_repository`: Verifies storage shredding receipt storage.
- `test_idempotency_store_behavior`: Tests host command idempotency token tracking.
- `test_send_launch_command_success`: Tests dispatching launch commands to host agents.
- `test_send_stop_command_success`: Tests dispatching stop commands to host agents.
- `test_send_terminate_command_success`: Tests dispatching terminate commands to host agents.
- `test_idempotent_replay_prevention`: Verifies that duplicate host commands are rejected.
- `test_command_failure_logged_in_audit_table`: Tests auditing of host command execution failures.
- `test_get_instance_not_found`: Tests HTTP 404 response for invalid instance IDs.
- `test_list_instances_endpoint`: Verifies listing user compute instances via API.
- `test_stop_instance_route_not_running`: Verifies rejection of stop requests for non-running instances.
- `test_stop_instance_route_success`: Tests stopping a running compute instance.
- `test_terminate_instance_route_success`: Tests terminating a compute instance.
- `test_legal_transitions_path`: Tests valid state machine transitions (`PENDING` ➔ `PROVISIONING` ➔ `RUNNING` ➔ `STOPPED` ➔ `TERMINATED`).
- `test_force_terminate_from_any_state`: Verifies admin force-termination from any state.
- `test_illegal_transition_terminated_to_running`: Verifies rejection of illegal state transition (`TERMINATED` ➔ `RUNNING`).
- `test_illegal_transition_stopped_to_provisioning`: Verifies rejection of illegal state transition (`STOPPED` ➔ `PROVISIONING`).
- `test_illegal_transition_failed_to_running`: Verifies rejection of illegal transition (`FAILED` ➔ `RUNNING`).
- `test_agent_protocol_mock_provision`: Tests mock agent provisioning protocol.
- `test_agent_protocol_mock_stop_and_terminate`: Tests mock agent stop and terminate protocol.
- `test_agent_protocol_mock_volume_shred_and_verify`: Tests mock volume shredding verification.
- `test_agent_protocol_http_error_handling`: Verifies agent HTTP error handling.
- `test_valid_state_machine_flow`: Verifies full valid state machine lifecycle flow.
- `test_invalid_state_transition_throws_error`: Verifies state machine exception throwing.
- `test_fernet_ssh_key_encryption_decryption`: Tests Fernet AES-256 SSH key encryption and decryption.
- `test_instance_create_request_valid`: Validates Pydantic schema for instance creation requests.
- `test_instance_create_request_bounds`: Tests boundary limits in instance creation schema.
- `test_instance_action_response`: Validates instance action response schema.
- `test_instance_connection_response`: Validates instance connection response schema (`ssh_command`, `ssh_host`, `ssh_port`).
- `test_generate_keypair`: Tests RSA 4096-bit keypair generation.
- `test_decrypt_corrupt_ciphertext_raises`: Tests invalid Fernet token rejection.
- `test_build_ssh_command`: Tests SSH command string formatting.
- `test_key_expiry_time`: Tests SSH key rotation deadline calculation.
- `test_ssh_session_repository_lifecycle`: Tests SSH session database repository lifecycle.
- `test_valid_request_returns_validated_object`: Tests pre-flight request validator.
- `test_hold_amount_is_hourly_rate_times_hours`: Verifies hold calculation math.
- `test_rejects_when_wallet_missing`: Verifies pre-flight gate rejection when user has no wallet.
- `test_rejects_insufficient_usd_balance`: Verifies pre-flight gate rejection when USD balance is low.
- `test_accepts_exact_balance_match`: Tests pre-flight approval when balance exactly equals hold.
- `test_rejects_unknown_listing`: Tests pre-flight rejection for non-existent listing IDs.
- `test_rejects_paused_listing`: Tests pre-flight rejection for paused compute listings.
- `test_rejects_delisted_listing`: Tests pre-flight rejection for delisted compute listings.
- `test_rejects_suspended_host`: Tests pre-flight rejection for suspended compute hosts.
- `test_rejects_pending_verification_host`: Tests pre-flight rejection for unverified hosts.
- `test_accepts_listed_host`: Tests pre-flight approval for active, verified hosts.
- `test_rejects_host_with_no_heartbeat`: Tests pre-flight rejection for hosts without heartbeats.
- `test_rejects_stale_heartbeat`: Tests pre-flight rejection for hosts with stale heartbeats (> 120s).
- `test_rejects_busy_host`: Tests pre-flight rejection for hosts already running workloads.
- `test_uses_most_recent_heartbeat`: Verifies heartbeat freshness timestamp evaluation.
- `test_rejects_unauthorized_third_party`: Tests security authorization checks for instance actions.
- `test_admin_can_act_for_developer`: Verifies admin authorization override for support actions.
- `test_rejects_nonexistent_requester`: Rejects requests from non-existent user accounts.
- `test_uses_inr_for_inr_preferred_developer`: Tests pre-flight hold calculation in INR for Indian developers.
- `test_rejects_inr_developer_with_insufficient_inr`: Tests pre-flight rejection for low INR balance.
- `test_validation_error_stores_code_and_message`: Verifies error code and message persistence on pre-flight rejections.
- `test_wallet_topup_usd`: Tests wallet balance top-up in USD.
- `test_wallet_topup_inr`: Tests wallet balance top-up in INR.
- `test_wallet_debit_success`: Tests wallet balance debit execution.
- `test_wallet_debit_overdraft_prevention`: Prevents negative wallet balances during debits.
- `test_invalid_negative_topup_or_debit`: Rejects negative top-up or debit amounts.
- `test_razorpay_paise_conversion`: Tests INR Rupee to Razorpay Paise conversion.
- `test_uuid_to_ip_determinism`: Tests deterministic WireGuard IP allocation from instance UUID.
- `test_allocate_wireguard_ip`: Tests WireGuard IP address assignment.
- `test_generate_peer_config`: Tests WireGuard client peer configuration generation.
- `test_resolve_ssh_host`: Tests resolving host IP (direct vs WireGuard NAT relay).
- `test_complete_platform_lifecycle`: E2E test verifying full platform flow from user creation to instance termination.
- `test_full_instance_lifecycle`: E2E test of complete instance lifecycle.
- `test_insufficient_balance_never_reaches_host_agent`: E2E test confirming low balance requests are stopped at API gateway pre-flight gate.
- `test_host_agent_disconnect_mid_provisioning`: E2E test handling host agent disconnects mid-boot.
- `test_zero_balance_auto_termination`: E2E test verifying automatic instance termination when wallet balance reaches zero.
- `test_idempotent_launch_retry`: E2E test verifying idempotent launch retries.

---

## 🛠️ Local Setup & Execution Guide

### Prerequisites
- **Python**: `>= 3.11`
- **PostgreSQL**: `>= 15` (or Docker)
- **Redis**: `>= 7` (or Docker)

### 1. Installation
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt 2>/dev/null || pip install -e .
```

### 2. Database Migrations
```bash
alembic upgrade head
```

### 3. Run Pytest Suite
```bash
PYTHONPATH=. python3 -m pytest tests/unit/ tests/integration/ -v
```

### 4. Running Microservices Locally
```bash
# Start API Gateway
uvicorn services.api_gateway.main:app --host 0.0.0.0 --port 8000 --reload

# Start Auth Service
uvicorn services.auth_service.main:app --host 0.0.0.0 --port 8001 --reload

# Start Marketplace Service
uvicorn services.marketplace_service.main:app --host 0.0.0.0 --port 8002 --reload
```
