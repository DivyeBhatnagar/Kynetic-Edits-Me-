# Kynetic AI — Full Product Implementation Plan (10 Phases)

### Compute-First, AI-Native Marketplace — Engineering Build Plan (Python-First Stack)

> **Source documents used:** `Kynetic_AI_MVP_Roadmap_v2.md`, `Kynetic_AI_Security_Architecture.md`, `Kynetic_AI_Strategic_Roadmap.md`.
> **Scope:** This document restructures the 14-phase MVP roadmap into **10 consolidated, dependency-ordered build phases**, folds in every MVP-tier (P0/P1) security control from the Security Architecture document, and specifies exact tech stack, services, database tables, API surfaces, background jobs, and exit criteria per phase — written so it can be handed directly to an IDE/AI coding agent and executed phase by phase.
> **Tech stack constraint:** Only tools, libraries, and frameworks explicitly named in the source roadmap are used below. No new/unlisted technology has been introduced.

---

## 0. How to Use This Plan

- Build phases **in order** — each phase lists explicit dependencies on prior phases.
- Every phase includes: **Objective**, **Features In Scope**, **Services/Modules Touched**, **Detailed Build Tasks**, **Database Additions**, **API Surface**, **Background Jobs (Celery/APScheduler)**, **Security Controls to Implement**, **Tech Stack Used**, and **Exit Criteria (Definition of Done)**.
- Treat each phase's **Exit Criteria** as a hard gate — do not start the next phase until the current phase's checklist passes.
- All backend services are FastAPI apps sharing one PostgreSQL database (via SQLAlchemy 2.0 async + Alembic) unless stated otherwise, communicating over internal REST (httpx, async) behind a single API Gateway.

---

## 1. Reference Architecture (Applies to All Phases)

```
Frontend (Next.js + React + TypeScript + Tailwind)
        │  HTTPS/REST + WebSocket, JWT auth
        ▼
API Gateway (FastAPI — auth, rate limiting, routing)
        │
   ┌────┼────────────┬───────────────┬────────────────┬───────────────┐
   ▼    ▼             ▼               ▼                ▼               ▼
 Auth  Marketplace/  AI Router +   Wallet/Billing   Provisioning     Monitoring
Service Scheduler    Copilot       Service          Service          Service
        Service      (FastAPI +   (FastAPI)         (FastAPI +       (FastAPI +
        (FastAPI)    LangChain)                      Celery)          prometheus-client)
                                                       │      │
                                              mTLS      │      │  REST/SDK
                                        ┌──────▼───┐  ┌─▼──────────────┐
                                        │Host Agent │  │Hybrid Compute   │
                                        │(Python,   │  │Broker (FastAPI  │
                                        │on host PC)│  │+ boto3/azure-   │
                                        └─────┬─────┘  │sdk/google-cloud │
                                              │        │+ RunPod/Vast)   │
                                        ┌─────▼─────┐  └─────────────────┘
                                        │Reputation & │
                                        │Auto-Pricing │
                                        │Engine (Celery│
                                        │+ scikit-learn)│
                                        └───────────────┘

Data layer: PostgreSQL (SQLAlchemy 2.0 async + Alembic) · Redis (cache/session/Celery broker)
            S3-compatible object storage (boto3 / MinIO) for images, templates, logs
```

### 1.1 Full Tech Stack (from `Kynetic_AI_MVP_Roadmap_v2.md`, Section 5 — used exactly as specified)

| Layer | Technology |
|---|---|
| Backend API framework | FastAPI (every service) |
| ASGI server | Uvicorn behind Gunicorn |
| ORM / migrations | SQLAlchemy 2.0 (async) + Alembic |
| Primary database | PostgreSQL |
| Cache / broker | Redis |
| Async task queue | Celery |
| Cron-like scheduling | APScheduler (or Celery Beat) |
| Host Agent | Python, packaged with PyInstaller; `psutil` (CPU/RAM/disk), `pynvml`/`GPUtil` (GPU telemetry) |
| Hardware benchmarking | PyTorch + custom benchmark scripts |
| AI Resource Router / Copilot | LangChain + OpenAI/Anthropic API (or self-hosted LLM via vLLM) |
| Auto-pricing / idle prediction | scikit-learn + pandas |
| Reputation scoring | scikit-learn / weighted-scoring logic in Python |
| Hybrid cloud SDKs | boto3 (AWS), azure-sdk-for-python (Azure), google-cloud-python (GCP), httpx-based REST clients (RunPod/Vast) |
| Internal/external HTTP client | httpx (async) |
| Auth | FastAPI-Users or Ory/Keycloak (self-hosted) + python-jose (JWT) + passlib (hashing) |
| Payments (global) | Stripe Python SDK + Stripe Connect |
| Payments (India) | Razorpay Python SDK |
| Monitoring/metrics | prometheus-client + Grafana |
| Logging | structlog + Loki or ELK |
| Containerization | Docker + Firecracker microVMs |
| Object storage | S3-compatible (AWS S3 or self-hosted MinIO) via boto3 |
| Networking / SSH relay | WireGuard, orchestrated via a Python control service |
| Frontend | Next.js (React) + TypeScript + Tailwind |
| Infra / deployment | Kubernetes + Terraform + Docker Compose (local dev) |
| CI/CD | GitHub Actions |
| Testing | pytest + pytest-asyncio |

### 1.2 Suggested Monorepo Structure

```
kynetic-ai/
├── apps/
│   ├── frontend/                 # Next.js + TS + Tailwind
├── services/
│   ├── auth_service/              # FastAPI
│   ├── marketplace_service/       # FastAPI (listings, discovery, scheduler)
│   ├── wallet_billing_service/    # FastAPI
│   ├── provisioning_service/      # FastAPI + Celery workers
│   ├── ai_router_copilot_service/ # FastAPI + LangChain
│   ├── reputation_pricing_service/# FastAPI + Celery + scikit-learn
│   ├── hybrid_broker_service/     # FastAPI + boto3/azure-sdk/google-cloud
│   ├── monitoring_service/        # FastAPI + prometheus-client
│   ├── api_gateway/               # FastAPI (routing, auth check, rate limiting)
├── host_agent/                    # Python, PyInstaller-packaged
├── libs/
│   ├── db_models/                 # shared SQLAlchemy models + Alembic migrations
│   ├── schemas/                   # shared Pydantic schemas
│   ├── common/                    # structlog config, httpx client wrapper, auth deps
├── infra/
│   ├── terraform/
│   ├── k8s/
│   ├── docker-compose.yml
├── .github/workflows/             # GitHub Actions CI/CD
└── tests/
```

---

# PHASE 1 — Foundations & Core Platform Skeleton

**Maps to source roadmap:** Phase 0 (Foundations)
**Dependencies:** None
**Priority:** P0

### Objective
Stand up a deployable, testable backend skeleton with working authentication, database, caching, and CI/CD — the substrate every later phase builds on.

### Features In Scope
- API Gateway skeleton
- Auth Service (signup/login, JWT session auth)
- PostgreSQL schema bootstrap
- Redis setup (cache + Celery broker)
- CI/CD pipeline
- Base repo structure, shared libs (`db_models`, `schemas`, `common`)

### Detailed Build Tasks
1. **Repo scaffolding**: initialize monorepo per structure in §1.2; set up `pyproject.toml`/`requirements.txt` per service, shared `libs/common` for structlog config, httpx async client wrapper, and Pydantic settings (env-based config).
2. **API Gateway** (`services/api_gateway`): FastAPI app that reverse-proxies to internal services, validates JWTs on protected routes, applies global rate limiting middleware (in-memory/Redis-backed token bucket), exposes unified OpenAPI docs.
3. **Auth Service** (`services/auth_service`):
   - Implement with **FastAPI-Users** (or self-hosted **Ory/Keycloak** if preferred) for user CRUD, password hashing via **passlib**, and JWT issuance/verification via **python-jose**.
   - Endpoints: `POST /auth/signup`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me`.
   - Support both **Host** and **Developer** account types via a `role` field (extendable enum) on the `users` table.
   - Add phone verification stub (SMS OTP endpoint — provider-agnostic interface, actual provider wiring can be deferred but the flow/endpoints must exist since Phase 2 host onboarding depends on it).
4. **Database bootstrap** (`libs/db_models`):
   - PostgreSQL via SQLAlchemy 2.0 async engine + session factory.
   - Alembic initialized with `env.py` configured for async migrations.
   - Base tables this phase: `users`, `sessions` (or refresh-token table), `audit_logs` (immutable, append-only — used by every later phase per the security architecture's Pillar 11 requirement).
5. **Redis setup**: single Redis instance for (a) FastAPI-Users/session cache, (b) Celery broker/result backend (Celery itself is wired more fully in Phase 4, but the Redis instance and connection config belong here).
6. **CI/CD** (`.github/workflows/`):
   - `ci.yml`: on PR — install deps, run `ruff` lint, run `pytest`/`pytest-asyncio`, run `alembic upgrade head` against a test Postgres service container.
   - `docker-build.yml`: build and push per-service Docker images on merge to main.
7. **Local dev environment**: `docker-compose.yml` with Postgres, Redis, and each FastAPI service, hot-reload via Uvicorn `--reload`.
8. **Structured logging**: configure `structlog` globally (JSON output in prod, pretty-console in dev) across every service from day one, with a request-ID/correlation-ID middleware so logs are traceable across services — this underpins the audit-log requirements in later phases.

### Database Additions
- `users` (id, email, hashed_password, role[host|developer|both], phone_number, phone_verified, is_active, created_at)
- `sessions` / `refresh_tokens`
- `audit_logs` (id, actor_id, action, resource_type, resource_id, metadata JSONB, created_at) — append-only, no update/delete permission at the application layer

### API Surface (v1)
```
POST   /auth/signup
POST   /auth/login
POST   /auth/refresh
POST   /auth/logout
GET    /auth/me
POST   /auth/phone/send-otp
POST   /auth/phone/verify-otp
GET    /healthz   (every service)
```

### Security Controls to Implement This Phase
- Password hashing via passlib (bcrypt/argon2)
- Short-lived JWT access tokens + refresh token rotation
- Immutable `audit_logs` table wired into every write endpoint from this point forward (Security Architecture Pillar 11)
- TLS termination at the gateway (encryption in transit — Pillar 8 baseline)

### Tech Stack Used
FastAPI, Uvicorn/Gunicorn, SQLAlchemy 2.0 async, Alembic, PostgreSQL, Redis, FastAPI-Users, python-jose, passlib, structlog, GitHub Actions, pytest/pytest-asyncio, Docker Compose.

### Exit Criteria
- [ ] A user can sign up, log in, and receive a valid JWT
- [ ] `GET /auth/me` returns correct user data given a valid token
- [ ] Alembic migrations run cleanly from empty DB
- [ ] CI pipeline passes lint + tests on every PR
- [ ] All services boot via `docker-compose up` and respond on `/healthz`
- [ ] Every write action produces a row in `audit_logs`

---

# PHASE 2 — Host Onboarding, Hardware Verification & Benchmarking

**Maps to source roadmap:** Phase 1 (Host Onboarding & Verification) + Security Architecture Pillar 3 (MVP tier)
**Dependencies:** Phase 1
**Priority:** P0

### Objective
Allow a real machine (GPU, CPU-only, or full workstation — including consumer gaming PCs) to install the Host Agent, report verified hardware specs, and pass an automated benchmark.

### Features In Scope
- Python Host Agent (PyInstaller-packaged binary)
- Hardware detection: `psutil` (CPU/RAM/disk), `pynvml`/`GPUtil` (GPU telemetry)
- mTLS registration channel between Host Agent and backend
- PyTorch-based benchmark suite (LLM inference test, image-gen test, raw FLOPs test)
- Basic hardware/spec cross-check verification (Security Pillar 3, MVP tier)
- Guided, non-technical consumer onboarding flow (simplified install path for gamer/RTX-card hosts)

### Detailed Build Tasks
1. **Host Agent** (`host_agent/`, Python, packaged via PyInstaller):
   - Module `hardware_detect.py`: use `psutil` for CPU core count, RAM, disk (NVMe) capacity/type; use `pynvml` (fallback `GPUtil`) for GPU model, VRAM, driver version, temperature, power draw.
   - Module `agent_client.py`: registers with backend over **mTLS** (client cert issued at agent-download time, tied to the host's user account); sends heartbeat every N seconds (idle/busy/offline, temperature, power draw).
   - Module `benchmark_runner.py`: runs the PyTorch benchmark suite locally (see task 3) and submits signed results.
   - Package with **PyInstaller** into a single downloadable binary per OS (Windows/Linux/macOS priority order: Windows first, since consumer gaming PCs are the primary onboarding target per the roadmap).
   - Build a **guided installer UX** (simple wizard: download → run → auto-detect → confirm → done) — no CLI required, per the "Consumer Hardware Onboarding" requirement.
2. **Verification Service** (extend `marketplace_service` or a dedicated module):
   - `POST /hosts/register`: receives agent registration + hardware manifest, issues host record, returns mTLS client cert/keypair.
   - Cross-check reported specs against a maintained table of known hardware signatures (GPU model → expected VRAM/CUDA cores etc.) to catch grossly spoofed/mismatched claims — this is the MVP-tier version of Security Pillar 3's "GPU authenticity verification."
   - `POST /hosts/heartbeat`: ingest periodic status updates; update `host_status` (idle/busy/offline) and telemetry fields.
3. **Benchmark Suite** (PyTorch + custom scripts, run by the Host Agent, validated server-side):
   - LLM inference micro-benchmark (tokens/sec on a fixed small model)
   - Image-generation micro-benchmark (fixed Stable Diffusion step count, time-to-complete)
   - Raw FLOPs benchmark (matrix-multiply throughput test)
   - Results stored per host, timestamped, and used later by Auto-Pricing (Phase 8) and AI Router (Phase 7).
   - Schedule **periodic re-benchmarking** via APScheduler/Celery Beat (catches degraded/tampered hardware post-onboarding — MVP-tier continuous verification per Security Pillar 3).
4. **Host status/verification state machine**: `pending_verification` → `benchmarking` → `verified` → `listed` (listing itself happens in Phase 3) / `flagged` (on spec mismatch) / `suspended`.
5. **Frontend**: Host signup + agent download page; onboarding wizard UI showing live detection progress and benchmark results.

### Database Additions
- `hosts` (id, user_id FK, status, os_type, agent_version, mtls_cert_fingerprint, created_at)
- `host_hardware_specs` (host_id FK, cpu_cores, ram_gb, disk_type, disk_gb, gpu_model, gpu_vram_gb, driver_version, reported_at)
- `host_benchmarks` (id, host_id FK, benchmark_type[llm_inference|image_gen|flops], score, raw_metrics JSONB, run_at)
- `host_heartbeats` (host_id FK, status[idle|busy|offline], temperature_c, power_draw_w, recorded_at) — consider a time-series-friendly table or partitioning given heartbeat frequency

### API Surface (v1 additions)
```
POST   /hosts/register
POST   /hosts/heartbeat
GET    /hosts/{host_id}
GET    /hosts/{host_id}/benchmarks
POST   /hosts/{host_id}/benchmarks/rerun     (internal/admin + scheduled)
```

### Background Jobs
- Celery Beat/APScheduler: periodic re-benchmark job (e.g., every 24–72h) per active host
- Celery task: process incoming heartbeat payloads asynchronously if volume requires

### Security Controls to Implement This Phase
- mTLS for every Host Agent ↔ backend connection (Security Pillar 1 baseline)
- Signed agent binaries (basic code-signing) so a tampered agent build is detectable
- Spec cross-check against known hardware signatures (Security Pillar 3, MVP tier)
- Continuous benchmark re-validation (MVP tier of "Continuous Host Health Monitoring")

### Tech Stack Used
Python, PyInstaller, psutil, pynvml/GPUtil, PyTorch, FastAPI, Celery/APScheduler, PostgreSQL, mTLS (via standard TLS libraries), structlog.

### Exit Criteria
- [ ] Host Agent installs and runs on Windows/Linux with a guided, non-CLI flow
- [ ] A real GPU machine and a real full-workstation/CPU-only machine can both register successfully
- [ ] Reported specs are cross-checked and mismatches are flagged
- [ ] Benchmark suite runs automatically post-registration and stores results
- [ ] Heartbeats update host status in near real time
- [ ] Periodic re-benchmark job is scheduled and executes

---

# PHASE 3 — Compute-First Marketplace & Wallet/Billing Core

**Maps to source roadmap:** Phase 2 (Compute-First Marketplace) + Phase 3 (Wallet & Billing Core)
**Dependencies:** Phase 2 (marketplace needs verified hosts), Phase 1 (billing needs auth/users)
**Priority:** P0

### Objective
Turn verified hosts into rentable listings (GPU, CPU, RAM, NVMe, or full workstation as one resource-agnostic inventory), and stand up the wallet/billing core that will meter and charge every future rental.

### Features In Scope
- Resource-agnostic listing schema and creation flow
- Marketplace browse/search/filter (manual mode)
- Real-time availability indexing
- Developer wallet (auto-created on signup)
- Usage metering pipeline groundwork (Celery)
- Per-second billing logic, dual-currency (INR/USD) support

### Detailed Build Tasks
1. **Listings schema** (`marketplace_service`):
   - Design listing as a **bundle of resource attributes** (gpu, cpu_cores, ram_gb, storage_gb, storage_type) rather than a GPU-type enum — this is explicitly called out in the roadmap as the resource-agnostic, "compute-first" design decision.
   - `POST /listings`: host creates a listing from a verified host record (requires `status = verified`); pulls hardware specs + latest benchmark scores automatically.
   - `GET /listings`: browse/search/filter by resource type, price range, GPU model, location/region, reputation score (reputation field wired in Phase 8, but the filter parameter should exist now as a no-op/placeholder).
   - `GET /listings/{id}`: full listing detail including specs + benchmark scores.
2. **Availability indexing**: maintain a `listing_availability` state (available/rented/offline) kept in sync with `host_heartbeats` from Phase 2; consider Redis-backed cache of currently-available listings for fast marketplace browse queries.
3. **Wallet Service** (`wallet_billing_service`):
   - `wallets` table auto-created (₹0/$0 balance) on developer signup (hook into Auth Service's signup flow or a listener on user creation).
   - `POST /wallet/topup` (stub for now — real payment provider wiring happens in later phases: Stripe in this phase for global, Razorpay in Phase 10 for India — see note below).
   - `GET /wallet/balance`, `GET /wallet/transactions`.
4. **Billing core — usage metering pipeline**:
   - Define the **per-second billing model**: `rate_per_second` derived from listing price; a Celery task will (in Phase 4/5, once instances exist) tick and debit the wallet incrementally. This phase builds the **pipeline and data model**, since actual instance-driven metering depends on Provisioning (Phase 4).
   - Dual-currency support: every price stored in both INR and USD (or one canonical currency + live/periodic FX conversion); wallets track a `currency` preference; all transaction rows store the currency they were executed in to avoid rounding drift.
5. **Stripe integration (global)**: wire **Stripe Python SDK** for developer wallet top-ups and **Stripe Connect** for host payouts (payout execution itself is exercised end-to-end in Phase 8/10, but the SDK integration and account-linking flow belongs here since it's core billing infrastructure).
6. **Frontend**: marketplace browse/search/filter UI; wallet balance + top-up + transaction history UI.

### Database Additions
- `listings` (id, host_id FK, resource_type[gpu|cpu|ram|nvme|workstation_bundle], gpu_model, cpu_cores, ram_gb, storage_gb, storage_type, price_per_hour_usd, price_per_hour_inr, status[draft|active|paused|delisted], region, created_at)
- `wallets` (id, user_id FK, balance_usd, balance_inr, preferred_currency, created_at)
- `wallet_transactions` (id, wallet_id FK, type[topup|debit|refund|payout], amount, currency, reference_id, created_at)
- `stripe_accounts` (user_id FK, stripe_customer_id, stripe_connect_account_id) — for developers and hosts respectively

### API Surface (v1 additions)
```
POST   /listings
GET    /listings
GET    /listings/{id}
PATCH  /listings/{id}
DELETE /listings/{id}
GET    /wallet/balance
GET    /wallet/transactions
POST   /wallet/topup
POST   /billing/webhooks/stripe
```

### Background Jobs
- Celery task: sync `listing_availability` from `host_heartbeats`
- Celery task: reconcile Stripe webhook events into `wallet_transactions`

### Security Controls to Implement This Phase
- Immutable, append-only `wallet_transactions` (feeds Pillar 6's billing-manipulation detection and Pillar 11's purpose-scoped logging)
- Rate limiting on listing creation/search endpoints (Pillar 2 baseline)
- Encryption at rest for wallet/payment-linked tables (Pillar 8 MVP baseline)

### Tech Stack Used
FastAPI, SQLAlchemy 2.0 async, PostgreSQL, Redis, Celery, Stripe Python SDK, Next.js/React/Tailwind frontend.

### Exit Criteria
- [ ] A verified host can create a listing spanning any resource type (GPU, CPU, RAM, NVMe, or full workstation)
- [ ] Marketplace browse/search/filter returns correct, live results
- [ ] A new developer automatically gets a ₹0/$0 wallet
- [ ] Wallet top-up via Stripe succeeds end-to-end (test mode)
- [ ] Dual-currency amounts display and store correctly with no rounding errors
- [ ] All wallet transactions are immutable and auditable

---

# PHASE 4 — Provisioning, Scheduling & Instance Lifecycle

**Maps to source roadmap:** Phase 4 (Provisioning & Scheduling) + Phase 5 (SSH Access & Instance Lifecycle)
**Dependencies:** Phases 1–3
**Priority:** P0

### Objective
Let a developer actually rent a machine and get a running, reachable, billable instance — from selection through SSH access to clean termination.

### Features In Scope
- Scheduler (matches developer request → available listing)
- Provisioning Service (FastAPI + Celery)
- Container/VM isolation (Docker + Firecracker microVMs)
- Ephemeral NVMe storage
- Ephemeral SSH key generation + WireGuard NAT relay
- Start/stop/terminate lifecycle
- Secure deletion on termination
- Live per-second billing now fully wired (ties back to Phase 3's metering pipeline)

### Detailed Build Tasks
1. **Scheduler** (`marketplace_service` or dedicated module):
   - `POST /instances` (developer confirms a listing): scheduler checks wallet balance, places a **hold** on estimated cost, selects the target host, and hands off to Provisioning.
   - Manual-mode matching only in this phase (AI Router–driven matching is Phase 7; this phase's scheduler just needs to route a specific selected listing to provisioning reliably).
2. **Provisioning Service** (`provisioning_service`, FastAPI + Celery):
   - Celery task `provision_instance`: dispatches job to the target Host Agent over the existing mTLS channel; instructs the agent to create an isolated environment.
   - **Isolation implementation**: Docker container running inside a **Firecracker microVM** on the host machine — Firecracker itself is orchestrated by a Python control process on the Host Agent side per the architecture; this is the MVP-tier baseline of Security Pillar 1 ("container isolation + basic ephemeral storage" — full double-isolation hardening continues in Phase 5).
   - **Ephemeral storage**: allocate a scoped NVMe volume for the instance's lifetime only; no persistent host file access is exposed to the workload.
   - `POST /instances/{id}/stop`, `POST /instances/{id}/terminate`: Celery tasks tear down the container/VM.
3. **SSH access**:
   - Generate a short-lived, auto-rotated SSH keypair per instance session (no long-lived credentials ever touch a host — Security Pillar 1).
   - For hosts without a public IP: route SSH through a **WireGuard**-based NAT relay, orchestrated by a Python control service.
   - `GET /instances/{id}/connection`: returns SSH connection string/key to the developer.
4. **Instance lifecycle state machine**: `pending` → `provisioning` → `running` → `stopping` → `terminated` (+ `failed`).
5. **Secure deletion**: on termination, the Host Agent cryptographically shreds (key destruction, not simple delete) the ephemeral NVMe volume — implement this as a mandatory step in the `terminate_instance` Celery task, verified via a completion callback from the agent before the instance is marked `terminated`.
6. **Live billing wiring**: on `running`, start a Celery periodic task (per-instance) that debits the wallet per second at the listing's rate; on zero balance, auto-trigger `terminate_instance`; on low balance, fire a notification (full notification system lands in Phase 10, but the trigger/event should be emitted here).
7. **Frontend**: instance launch flow, running-instances dashboard (basic — full dashboard polish in Phase 10), SSH connection info display.

### Database Additions
- `instances` (id, developer_id FK, listing_id FK, host_id FK, status, ssh_key_id FK, started_at, stopped_at, billed_seconds, hold_amount, currency)
- `ssh_sessions` (id, instance_id FK, public_key, private_key_encrypted, issued_at, rotated_at, revoked_at)
- `secure_deletion_receipts` (instance_id FK, verified_at, method) — supports audit/compliance trail

### API Surface (v1 additions)
```
POST   /instances
GET    /instances/{id}
POST   /instances/{id}/stop
POST   /instances/{id}/start
POST   /instances/{id}/terminate
GET    /instances/{id}/connection
```

### Background Jobs
- Celery: `provision_instance`, `terminate_instance` (with secure-deletion verification step)
- Celery periodic: `meter_instance_usage` (per running instance, per-second/near-real-time debit)
- Celery: `auto_terminate_on_zero_balance`

### Security Controls to Implement This Phase
- Container-in-microVM isolation (Firecracker) — MVP baseline of Zero Trust Compute Isolation (Pillar 1)
- Zero host OS/file access from workloads (scoped, ephemeral volumes only)
- Ephemeral, auto-rotated SSH keys (Pillar 1)
- Secure/cryptographic deletion on termination, verified before state transitions to `terminated`
- Per-job network namespace with default-deny egress firewall (MVP tier of Network Security, Pillar 2) — implement basic firewall templating per instance now; full DDoS/edge protection and anomaly detection is Phase 5

### Tech Stack Used
FastAPI, Celery, Docker, Firecracker, WireGuard, PostgreSQL, Redis, httpx, structlog.

### Exit Criteria
- [ ] A developer can select a listing, confirm, and receive a running instance reliably (target: >99% success, formally validated in Phase 10's launch checklist)
- [ ] SSH access works for both public-IP and NAT'd hosts via WireGuard relay
- [ ] Per-second billing correctly debits the wallet while an instance runs
- [ ] Zero-balance triggers auto-termination
- [ ] Secure deletion is verified after every termination — no residual data recoverable
- [ ] Every instance runs fully isolated from the host OS and other tenants

---

# PHASE 5 — Security Hardening (Pre-Launch Trust Layer)

**Maps to source roadmap:** Phase 6 (Security Hardening) + MVP-tier items from Security Architecture Pillars 1, 2, 4, 5, 6, 9, 10, 11
**Dependencies:** Phases 4–5 concepts (i.e., this document's Phase 4)
**Priority:** P0 — must complete before public launch

### Objective
Take the platform from "functionally works" to "safe to open to real, paying strangers" — the explicit gate the source roadmap sets before wider rollout.

### Features In Scope
- Malware/image scanning
- Runtime monitoring (resource/process abuse detection)
- Rate limiting across all public APIs
- Abuse detection (crypto-mining signatures, multi-account)
- Kill switch
- Audit logs (formalized across every service)
- Progressive trust / identity verification tiers
- Supply chain basics (image signing)

### Detailed Build Tasks
1. **Malware & image scanning** (Security Pillar 5/9, MVP tier):
   - Integrate a Docker image scanning step into the provisioning pipeline (pre-execution) — every container/template image is scanned before it's allowed to run; block execution on high-severity findings.
   - Basic image signing: only signed images are permitted to execute (Pillar 9 MVP tier).
2. **Runtime monitoring** (Pillar 5, MVP tier):
   - Resource monitoring: CPU/GPU/memory/disk/network usage streamed from the Host Agent during job execution (extends the heartbeat mechanism from Phase 2).
   - Crypto-mining detection: hash-rate/signature pattern matching against known mining-kernel profiles, implemented as a Celery task analyzing streamed telemetry.
   - On detection: auto-kill the workload and freeze the offending wallet (ties into the kill switch below).
3. **Rate limiting**: apply per-endpoint rate limits at the API Gateway (Redis-backed token bucket) across every public route, explicitly including the AI Router/Copilot endpoints that will ship in Phase 7 (build the limiter generically now so it applies automatically as new routes are added).
4. **Abuse & fraud detection (MVP, rule-based)** (Security Pillar 6):
   - Multi-account abuse detection via device fingerprinting on signup/login.
   - Wallet/payment fraud rule checks (e.g., rapid top-up + rapid spend patterns, chargeback flags) as a Celery task scanning `wallet_transactions`.
5. **Progressive trust / identity verification** (Security Pillar 4, MVP tier):
   - Identity verification tiers: phone verification (already stubbed in Phase 1) + basic government-ID upload/check for higher trust tiers.
   - New accounts start with strict limits: capped instance size, GPU-hours, and spend; store a `trust_tier` on `users` and enforce limits in the Provisioning Service based on tier.
6. **Kill switch** (Security Pillar 10, MVP tier — manual):
   - Admin-only endpoint that can instantly suspend any workload, host, or account (broadcasts a suspension signal to the relevant Host Agent(s) over the existing mTLS channel).
7. **Audit logs formalized** (Security Pillar 11): ensure every critical action across every service (auth, listings, wallet, instances, admin actions) writes to the `audit_logs` table established in Phase 1, with purpose-scoped separation (billing logs vs. security logs vs. admin logs, per Pillar 11's "separated by purpose" requirement) — split into `audit_logs`, `security_event_logs`, and `admin_action_logs` if volume/compliance needs warrant it.
8. **Network isolation hardening**: per-job private network namespace with default-deny outbound except declared endpoints (formalizes the basic firewall templating started in Phase 4).

### Database Additions
- `device_fingerprints` (user_id FK, fingerprint_hash, first_seen, last_seen)
- `trust_tiers` (user_id FK, tier, instance_size_cap, gpu_hour_cap, spend_cap, updated_at)
- `security_event_logs` (id, event_type, severity, resource_type, resource_id, details JSONB, created_at)
- `kill_switch_events` (id, target_type[instance|host|account], target_id, triggered_by, reason, triggered_at)

### API Surface (v1 additions)
```
POST   /admin/kill-switch
GET    /admin/security-events
POST   /identity/verify/id-document
GET    /users/{id}/trust-tier
```

### Background Jobs
- Celery: image scan step in provisioning pipeline
- Celery: runtime telemetry analysis (crypto-mining/abuse signature matching)
- Celery: fraud rule scan over recent `wallet_transactions`

### Security Controls to Implement This Phase
This entire phase **is** the security control set — see Features In Scope above. All items are explicitly MVP-tier per the Security Architecture document; Extreme/Future-tier items (confidential computing, hardware attestation via TPM, AI-native security intelligence, eBPF kernel-level detection) are intentionally deferred beyond this MVP build and are not required for launch.

### Tech Stack Used
FastAPI, Celery, Docker (image scanning tooling integrated into the existing Docker pipeline), Redis (rate limiting), PostgreSQL, structlog.

### Exit Criteria
- [ ] Malware/image scanning is active on every container and template
- [ ] Runtime monitoring flags basic cryptomining/abuse signatures
- [ ] Rate limiting is active on all public API endpoints
- [ ] Kill switch is tested and instantly suspends target workloads/hosts/accounts
- [ ] Audit logs capture every critical action across all services
- [ ] Progressive trust tiers correctly cap new-account limits
- [ ] Basic VM/container isolation has been tested against escape attempts

---

# PHASE 6 — Zero-Setup App Templates & AI-Native Entry Point

**Maps to source roadmap:** Phase 7 (Zero-Setup App Templates)
**Dependencies:** Phase 4 (Provisioning)
**Priority:** P0

### Objective
Replace "pick a GPU and configure Docker yourself" with one-click launches for popular AI workloads, and introduce the intent-based entry point that later phases (AI Router, AI Copilot) build on.

### Features In Scope
- One-click launch: Stable Diffusion, Ollama, ComfyUI, Llama 3
- Extensible template registry
- Intent-based entry point UI ("what do you want to run?")

### Detailed Build Tasks
1. **Template registry** (`provisioning_service` extension or new `template_service` module):
   - `templates` table: each row is a pre-built, scanned, verified container image mapped to a launch configuration (base image, required resources, default ports, startup command, exposed web UI path if any).
   - `POST /templates` (admin-only, for adding new templates), `GET /templates` (public listing).
   - Every template image goes through the malware/image scanning pipeline from Phase 5 before being marked `available`.
2. **One-click launch flow**:
   - Extend `POST /instances` to accept a `template_id` instead of (or alongside) raw resource selection — provisioning auto-configures the container from the template with zero Docker knowledge required from the developer.
   - Implement the four launch-day templates: **Stable Diffusion**, **Ollama**, **ComfyUI**, **Llama 3** — each as a signed, verified image + config entry in `templates`.
   - For templates exposing a web UI (e.g., ComfyUI), provision a secure web link (in addition to/instead of raw SSH) — reachable via the same WireGuard relay infrastructure from Phase 4.
3. **Intent-based entry point (frontend + light backend)**:
   - Frontend: replace the default "browse GPUs" landing flow with a "What do you want to run?" prompt offering menu options (Fine-tune Llama, Train YOLO, Render Blender, Run ComfyUI, Video generation, Agent hosting, "Something custom") — menu-driven only in this phase; free-text natural-language routing is layered on top in Phase 7 (AI Router) and Phase 8 (AI Copilot).
   - Manual "browse marketplace" mode from Phase 3 remains available for power users alongside this new default.
4. **Extensibility**: design the template schema so new templates can be added without code changes to the provisioning path (config-driven, not hardcoded per app).

### Database Additions
- `templates` (id, name, base_image, required_gpu_vram_gb, required_ram_gb, startup_command, exposed_web_ui_path, status[pending_scan|available|disabled], created_at)

### API Surface (v1 additions)
```
GET    /templates
POST   /templates              (admin)
POST   /instances               (extended to accept template_id)
GET    /instances/{id}/web-ui   (returns web UI link if template exposes one)
```

### Security Controls to Implement This Phase
- Every template image passes the Phase 5 malware/image scanning + signing pipeline before being marked available (Security Pillar 9)
- Web UI links are scoped, short-lived, and routed through the existing secure relay — never a raw public port exposure

### Tech Stack Used
FastAPI, Docker, Celery (image scan integration), PostgreSQL, Next.js/React frontend.

### Exit Criteria
- [ ] One-click launches work for Stable Diffusion, Ollama, ComfyUI, and Llama 3
- [ ] A developer with zero Docker knowledge can launch any of the four templates successfully
- [ ] Template registry supports adding a new template via config, not a code change
- [ ] Intent-based entry point is the default landing flow; manual browse mode remains accessible

---

# PHASE 7 — AI Resource Router & AI Copilot

**Maps to source roadmap:** Phase 8 (AI Resource Router) + Phase 9 (AI Copilot)
**Dependencies:** Phases 2, 3, 6 (Router needs benchmark + pricing + availability + template data)
**Priority:** P1

### Objective
Let a developer state a budget or a goal ("₹120 budget," "fastest," "I need GPU for LoRA training") and get an automatic, grounded machine recommendation — then layer a conversational copilot on top for cost/time estimation before launch.

### Features In Scope
- AI Resource Router: budget-based and goal-based automatic machine selection
- AI Copilot: conversational interface for natural-language intent → recommendation + cost/time estimate

### Detailed Build Tasks
1. **AI Resource Router** (`ai_router_copilot_service`, FastAPI):
   - Build a **ranking function** combining: live marketplace pricing/availability (`listings`), benchmark scores (`host_benchmarks`), and reputation data (reputation table is introduced in Phase 8 of this plan — if built before that phase lands, treat reputation as a stubbed neutral weight until Phase 8 wires real scores; do not block Router shipping on Reputation).
   - `POST /router/recommend`: accepts `{budget, currency}` or `{goal: "fastest"|"cheapest"|"balanced", template_id?}`; returns a ranked list of matching listings with estimated cost and estimated time.
   - Start rule-based (weighted scoring across price, benchmark score, and availability) per the roadmap's explicit MVP-vs-future note: *"rule-based, evolving to ML-based as job outcome data accumulates."*
2. **AI Copilot** (`ai_router_copilot_service`, LangChain + OpenAI/Anthropic API or self-hosted LLM via vLLM):
   - Conversational layer on top of the Router: LangChain agent that parses free-text intent ("I need GPU for LoRA training," "I have ₹120 budget," "I need fastest") into a structured call to `POST /router/recommend`, then formats the response back into natural language with an explicit cost/time estimate.
   - `POST /copilot/chat`: stateful chat endpoint (session-scoped conversation history) — expose over WebSocket for the frontend's chat widget (per the architecture diagram's "AI Copilot Chat Widget").
   - The LLM **must not fabricate numbers** — it only narrates/summarizes data returned by the Router's grounded recommendation; enforce this via prompt design (LLM handles language, Router supplies numbers, per the roadmap's explicit division of responsibility).
3. **Frontend**: chat widget for the AI Copilot (WebSocket-connected); recommendation results UI showing ranked machine options with estimated cost/time, with a one-click "launch this" action feeding directly into Phase 4/6's instance launch flow.
4. **Rate limiting**: apply the Phase 5 rate-limiting middleware explicitly to `/router/recommend` and `/copilot/chat` (the roadmap explicitly calls these out as endpoints requiring protection).

### Database Additions
- `router_recommendations` (id, developer_id FK, request_payload JSONB, recommended_listing_ids JSONB, created_at) — for auditability and future ML training data
- `copilot_sessions` (id, developer_id FK, created_at)
- `copilot_messages` (id, session_id FK, role[user|assistant], content, created_at)

### API Surface (v1 additions)
```
POST   /router/recommend
POST   /copilot/chat            (WebSocket)
GET    /copilot/sessions/{id}/history
```

### Security Controls to Implement This Phase
- Rate limiting on Router/Copilot endpoints (explicit carry-over requirement from Phase 5/Security Pillar 2)
- Input sanitization on free-text Copilot input before it reaches the LLM and before any structured data derived from it reaches the Router/Provisioning path

### Tech Stack Used
FastAPI, LangChain, OpenAI/Anthropic API (or vLLM for self-hosted), PostgreSQL, WebSocket, Next.js/React frontend.

### Exit Criteria
- [ ] AI Resource Router returns sensible recommendations for both budget-based and speed/goal-based queries
- [ ] AI Copilot gives accurate cost/time estimates before launch, grounded in real Router data (no hallucinated numbers)
- [ ] Recommendation → one-click launch flow works end-to-end
- [ ] Router/Copilot endpoints are rate-limited

---

# PHASE 8 — Host Experience, Auto-Pricing & Reputation Layer

**Maps to source roadmap:** Phase 10 (Host Experience & Auto-Pricing) + Phase 11 (Reputation Layer)
**Dependencies:** Phase 2 (hardware/benchmark data), Phase 3 (wallet/pricing), Phase 4 (job outcomes), Phase 5 (telemetry)
**Priority:** P1

### Objective
Give hosts a "Shopify for GPU owners" experience (analytics, auto-pricing, idle prediction, income projection) and give every listing a trustworthy, Uber-style reputation score.

### Features In Scope
- Host dashboard: revenue analytics, health/temperature monitoring, electricity cost estimation
- Auto-pricing engine (scikit-learn regression)
- Idle-time prediction + expected monthly income projection
- Reputation Layer: uptime, latency, network, job-success, benchmark, response-time scoring

### Detailed Build Tasks
1. **Reputation & Auto-Pricing Engine** (`reputation_pricing_service`, Celery + scikit-learn + pandas):
   - **Auto-pricing model**: scikit-learn regression trained on marketplace supply/demand + hardware class (features: GPU model, benchmark score, region, current listing prices, historical utilization) → suggests a competitive `price_per_hour` on listing creation/update; host can accept or override (per Phase 3's listing flow, extend `POST /listings` to call this service for a suggested price).
   - **Idle-time prediction**: model (scikit-learn) forecasting host idle windows from historical heartbeat/utilization data (`host_heartbeats` from Phase 2) — surfaced on the host dashboard.
   - **Expected monthly income projection**: derived from current price × predicted utilization.
   - **Reputation scoring**: transparent, explainable **weighted-scoring** function (not a black-box model, per the roadmap's explicit preference for trust-critical scoring) combining:
     - uptime score (from `host_heartbeats` history)
     - latency score (from job telemetry)
     - network score (from job telemetry)
     - job success rate (from `instances` outcome data)
     - benchmark score (from `host_benchmarks`, Phase 2)
     - response time (agent responsiveness to provisioning requests)
   - Recompute reputation on a scheduled Celery job after every completed job, and store historical score snapshots for trend display.
2. **Host dashboard** (`marketplace_service` API + frontend):
   - `GET /hosts/{id}/dashboard`: aggregates revenue analytics, health/temperature trends (from `host_heartbeats`), electricity cost estimate (simple formula: power_draw_w × runtime_hours × configurable regional electricity rate), idle prediction, and income projection.
   - Frontend: full host dashboard UI (analytics charts, health/temp trend graphs, pricing suggestion + override control, income projection).
3. **Surface reputation on listings**: extend `GET /listings` (Phase 3) and `GET /listings/{id}` to include the live reputation score and its sub-components; wire the reputation filter parameter (placeholder from Phase 3) to actually filter/sort by score now.
4. **Feed reputation into the Router**: update `ai_router_copilot_service` (Phase 7) to weight real reputation scores into its ranking function, replacing the neutral stub used if Phase 7 shipped first.

### Database Additions
- `reputation_scores` (id, host_id FK, uptime_score, latency_score, network_score, job_success_rate, benchmark_score, response_time_score, composite_score, computed_at)
- `pricing_suggestions` (id, listing_id FK, suggested_price_usd, suggested_price_inr, accepted, created_at)
- `idle_predictions` (host_id FK, predicted_idle_hours_per_day, income_projection_monthly, computed_at)

### API Surface (v1 additions)
```
GET    /hosts/{id}/dashboard
GET    /hosts/{id}/reputation
GET    /pricing/suggest?listing_id=...
```

### Background Jobs
- Celery: `recompute_reputation` (triggered on job completion + scheduled sweep)
- Celery: `train_or_refresh_pricing_model` (periodic retrain as marketplace data accumulates)
- Celery: `predict_idle_time` (periodic per-host)

### Security Controls to Implement This Phase
- Fraud-resistant reputation computation: tie scoring inputs to already-verified telemetry (heartbeats, benchmarks, job outcomes) rather than any self-reported field, to resist the "fake benchmarks / gamed reputation" abuse pattern (Security Pillar 6) at the MVP (rule-based) tier

### Tech Stack Used
Celery, scikit-learn, pandas, PostgreSQL, FastAPI, Next.js/React frontend.

### Exit Criteria
- [ ] Auto-pricing engine produces sane, competitive price suggestions
- [ ] Idle prediction and income projection display correctly on the host dashboard
- [ ] Reputation scores update correctly after every completed job
- [ ] Reputation is visible and filterable on every listing
- [ ] AI Router incorporates live reputation data into its recommendations

---

# PHASE 9 — External Marketplace Listings & Fallbacks

**Maps to source roadmap:** Phase 12 (External Alternatives / Transparent Fallbacks)
**Dependencies:** Phase 3 (Marketplace)
**Priority:** P1

### Objective
Provide developers with transparent alternatives when Kynetic's marketplace or router cannot satisfy a request for specific hardware (e.g. RTX 4090). Instead of silent bursting, we show a clean fallback prompt with direct links to other cloud providers, building long-term developer trust.

### Features In Scope
- Marketplace UI fallback state on query miss
- AI Router recommendation results fallback state
- Direct links to trusted alternatives (RunPod, Vast.ai, Lambda, Crusoe) opening in new tabs

### Detailed Build Tasks
1. **Marketplace Search Fallback**:
   - Update `MarketplacePage.tsx` search state. When `result.items.length === 0`, detect if `gpu_model` or general filter parameters were supplied.
   - Render a custom card: "No [GPU Model] currently available."
   - Display a clean section "Recommended alternatives" with clickable badges/links for RunPod, Vast.ai, Lambda, and Crusoe opening in new tabs.
2. **AI Router Fallback**:
   - Update `RecommendationResults.tsx` to render the same transparent alternative suggestion box when no local listings match the request criteria.

### Database Additions
None (purely frontend presentation tier).

### API Surface
None.

### Security Controls to Implement This Phase
- Secure link tags (use `rel="noopener noreferrer"` to prevent reverse tab-nabbing).

### Tech Stack Used
Next.js/React, CSS.

### Exit Criteria
- [ ] Searching for a non-existent GPU model in the marketplace displays the specific "No {GPU} currently available" message.
- [ ] Recommended alternatives (RunPod, Vast.ai, Lambda, Crusoe) are listed clearly.
- [ ] Clickable links open target provider sites in a new browser tab with correct security attributes.
- [ ] No-results view in Router results displays the identical alternative recommendation layout.

# PHASE 10 — India-First Billing, Unified Monitoring & Launch Readiness

**Maps to source roadmap:** Phase 13 (India-First Billing & Support) + Phase 14 (Monitoring, Dashboards & Notifications) + the full Launch Checklist
**Dependencies:** Phase 3 (wallet/billing), Phase 4 (instances)
**Priority:** P1 (P0 items from the Launch Checklist gate the actual public launch)

### Objective
Complete the India-first regional experience, unify monitoring/notifications, and formally clear the full pre-launch checklist from the source roadmap.

### Features In Scope
- Razorpay/UPI integration + GST invoice generation
- INR pricing display (formalizing dual-currency work from Phase 3)
- India-based support channel
- Unified monitoring service
- Developer/host dashboards (final polish, building on Phase 8's host dashboard)
- Notifications system
- Logs (centralized)
- Final launch checklist validation

### Detailed Build Tasks
1. **Razorpay / UPI integration** (`wallet_billing_service`):
   - Wire **Razorpay Python SDK** for UPI-based wallet top-ups and host payouts, alongside the existing Stripe path from Phase 3 (Stripe = global, Razorpay = India — selected by user region/currency preference).
   - `POST /wallet/topup/upi`, `POST /billing/webhooks/razorpay`.
2. **GST-compliant invoicing**:
   - Auto-generate a GST invoice on every completed transaction for Indian hosts/developers (invoice number sequencing, GSTIN capture on user profile for applicable accounts, PDF generation).
   - `GET /billing/invoices/{id}`.
3. **India support channel**: dedicated support contact/ticket routing flagged for India-region accounts (can be a lightweight routing rule to a support inbox/ticketing integration — implementation detail left to actual support tooling in use, but the routing flag and endpoint must exist).
4. **Unified Monitoring Service** (`monitoring_service`, FastAPI + prometheus-client + Grafana):
   - Ingest metrics from native Host Agents (Phase 2/4/5 telemetry), unifying them into one usage/billing/monitoring stream.
   - Instrument every service with **prometheus-client**; stand up **Grafana** dashboards for platform-wide health, per-instance resource usage, and billing throughput.
   - Centralized logging: ship **structlog** output (already configured from Phase 1) to **Loki or ELK** for searchable, cross-service log correlation.
5. **Developer & Host Dashboards (final)**:
   - Developer dashboard: running instances, usage history, billing history, invoices.
   - Host dashboard: finalize Phase 8's dashboard, plus notification preferences.
6. **Notifications system**:
   - Event-driven notifications (email at minimum; extensible to SMS/push) for: low wallet balance, instance lifecycle events (started/stopped/terminated/failed), payout confirmations, GST invoice availability.
   - Wire this to the low-balance and instance-event triggers stubbed in Phase 4.
7. **Load testing**: load-test the Scheduler and AI Router (Phase 7) under concurrent requests using standard load-testing tooling compatible with the FastAPI/async stack (e.g., via `pytest`-driven concurrency tests or a dedicated load-test script — use `httpx`'s async client to simulate concurrent load, consistent with the existing stack).
8. **Final Launch Checklist** — validate every item from the source roadmap's Launch Checklist (Section 7), consolidated here as the formal exit gate for the whole build:

### Full Launch Checklist (from source roadmap, validated at the end of this phase)
- [ ] Host Agent installs cleanly and verifies hardware on GPUs, full workstations, and consumer gaming PCs
- [ ] Benchmark suite (PyTorch-based) runs automatically and flags mismatched specs
- [ ] Marketplace lists GPU, CPU, RAM, NVMe, and full-workstation inventory correctly
- [ ] Auto-pricing engine produces sane, competitive price suggestions
- [ ] Wallet correctly holds/deducts/refunds in both INR and USD with no rounding errors
- [ ] Instance provisioning succeeds reliably (>99%) end-to-end, including one-click templates
- [ ] One-click launches work for Stable Diffusion, Ollama, ComfyUI, and Llama 3
- [ ] AI Resource Router returns sensible recommendations for budget- and speed-based queries
- [ ] AI Copilot gives accurate cost/time estimates before launch
- [ ] SSH access works for public-IP and NAT'd hosts via WireGuard relay
- [ ] External marketplace alternative recommendations display on marketplace search miss
- [ ] Reputation scores update correctly after job completion
- [ ] Razorpay/UPI payments and GST invoices work end-to-end for Indian users
- [ ] Per-second usage metering matches actual resource consumption within tolerance
- [ ] Auto-termination triggers correctly on zero balance or expiry
- [ ] Secure deletion verified — no residual data recoverable after termination
- [ ] VM/container isolation tested against basic escape attempts
- [ ] Rate limiting active on all public API endpoints, including AI Router/Copilot
- [ ] Malware/image scanning active on every container and template
- [ ] Runtime monitoring flags basic cryptomining/abuse signatures
- [ ] Kill switch tested across native instances
- [ ] Audit logs capture every critical action
- [ ] Host payout flow tested end-to-end (Stripe Connect + Razorpay)
- [ ] Notifications fire correctly for low balance, instance events, and payouts
- [ ] Load-tested scheduler and AI Router under concurrent requests
- [ ] Incident response runbook documented and on-call rotation established
- [ ] Terms of Service, acceptable use policy, and refund policy published (India + global)

### Database Additions
- `invoices` (id, transaction_id FK, gstin, invoice_number, pdf_url, issued_at)
- `notifications` (id, user_id FK, type, channel, payload JSONB, sent_at, read_at)
- `support_tickets` (id, user_id FK, region, subject, status, created_at) — lightweight routing record

### API Surface (v1 additions)
```
POST   /wallet/topup/upi
POST   /billing/webhooks/razorpay
GET    /billing/invoices/{id}
GET    /notifications
POST   /support/tickets
GET    /monitoring/metrics        (Prometheus scrape endpoint, per service)
```

### Background Jobs
- Celery: `generate_gst_invoice` on completed India-region transactions
- Celery: `dispatch_notification` (event-driven, triggered by lifecycle/billing events)
- Celery/APScheduler: metrics aggregation jobs feeding Grafana dashboards

### Security Controls to Implement This Phase
- Invoice/PII data handling compliant with the GDPR-baseline requirement from Security Pillar 12 (architected in, not just certified) — scope invoice PII storage minimally and access-control it
- Centralized logs separated by purpose (billing/notification logs vs. security event logs from Phase 5) per Pillar 11

### Tech Stack Used
Razorpay Python SDK, prometheus-client, Grafana, structlog, Loki/ELK, FastAPI, Celery, PostgreSQL, Next.js/React frontend.

### Exit Criteria
- [ ] Every item in the Full Launch Checklist above is verified and checked off
- [ ] Razorpay/UPI payments and GST invoices work end-to-end
- [ ] Unified monitoring shows native instance data on Grafana dashboards
- [ ] Notifications fire reliably for all defined event types
- [ ] Platform is formally ready for public launch

---

## Appendix A — Phase Dependency Graph

```
Phase 1 (Foundations)
   └─▶ Phase 2 (Host Onboarding & Verification)
          └─▶ Phase 3 (Marketplace & Wallet/Billing Core)
                 └─▶ Phase 4 (Provisioning, Scheduling & Lifecycle)
                        ├─▶ Phase 5 (Security Hardening)  [P0 gate]
                        ├─▶ Phase 6 (Zero-Setup Templates)
                        │        └─▶ Phase 7 (AI Router & Copilot)
                        ├─▶ Phase 9 (External Marketplace Listings & Fallbacks)
                        └─▶ Phase 10 (India Billing, Monitoring, Launch)
                               ▲
                 Phase 8 (Host Experience, Auto-Pricing, Reputation) ──┘
                        (depends on Phases 2, 3, 4, 5)
```

## Appendix B — Priority Summary

| Phase | Roadmap Source | Priority |
|---|---|---|
| 1. Foundations | Phase 0 | P0 |
| 2. Host Onboarding & Verification | Phase 1 | P0 |
| 3. Marketplace & Wallet/Billing Core | Phases 2–3 | P0 |
| 4. Provisioning, Scheduling & Lifecycle | Phases 4–5 | P0 |
| 5. Security Hardening | Phase 6 | P0 (launch gate) |
| 6. Zero-Setup App Templates | Phase 7 | P0 |
| 7. AI Resource Router & Copilot | Phases 8–9 | P1 |
| 8. Host Experience, Auto-Pricing & Reputation | Phases 10–11 | P1 |
| 9. External Marketplace Listings & Fallbacks | Phase 12 | P1 |
| 10. India Billing, Monitoring & Launch | Phases 13–14 + Launch Checklist | P1 (checklist items are P0 gates) |

## Appendix C — What's Explicitly Out of Scope for This MVP

Per the source roadmap, the following remain excluded from this build and are not covered in the 10 phases above:
- Enterprise SSO/SCIM
- Multi-region orchestration beyond external alternative recommendations
- Compute futures/derivatives
- Full confidential computing (hardware-enforced memory encryption / TPM-backed remote attestation)
- Custom enterprise clusters
- Extreme/Future-tier security pillars: AI-native Security Intelligence (Pillar 7), full graph-based ML fraud detection, eBPF kernel-level runtime detection, SOC 2 Type II / ISO 27001 / HIPAA certification, enterprise workspaces/RBAC/SSO/SCIM (Pillar 13)

These are natural candidates for a post-MVP Phase 11+ roadmap once the platform has live transaction volume to justify them.
