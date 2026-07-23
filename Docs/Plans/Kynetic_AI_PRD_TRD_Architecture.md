# Kynetic AI — Product Requirements, Technical Requirements & Architecture Document

### Compute-First, AI-Native Marketplace — Combined PRD / TRD / Architecture Spec (v1, MVP)

> **Source documents used:** `Kynetic_AI_MVP_Roadmap_v2.md`, `Kynetic_AI_Security_Architecture.md`, `Kynetic_AI_Strategic_Roadmap.md`, and the derived `Kynetic_AI_Implementation_Plan.md` (10-phase build plan).
> **Purpose:** Single reference document for engineering/IDE agents covering *what* to build (PRD), *how* it must behave technically (TRD), and *how the system is structured* (Architecture) — so no other document needs to be consulted to begin implementation.
> **Tech stack constraint:** Only tools/frameworks explicitly named in the source roadmap are specified anywhere in this document.

---

## Table of Contents

1. [Part I — Product Requirements Document (PRD)](#part-i--product-requirements-document-prd)
2. [Part II — Technical Requirements Document (TRD)](#part-ii--technical-requirements-document-trd)
3. [Part III — Architecture Document](#part-iii--architecture-document)
4. [Appendices](#appendices)

---

# Part I — Product Requirements Document (PRD)

## 1. Product Overview

Kynetic AI is a **compute-first, AI-native marketplace** connecting two sides:

- **Hosts** — anyone with idle compute (GPU, CPU, RAM, NVMe storage, or an entire workstation/gaming PC/enterprise server) who wants to rent it out.
- **Developers** — anyone who needs compute to run AI/ML workloads (training, fine-tuning, inference, rendering, agent hosting) without wanting to manage infrastructure.

Unlike GPU-only marketplaces (RunPod, Vast, Lambda), Kynetic treats **all compute resources as one resource-agnostic inventory**, adds an **AI-native "what do you want to run?" entry point** in place of manual GPU picking, guarantees **zero-setup app launches** for popular AI workloads, and is **India-first** on billing and support while remaining globally usable.

## 2. Problem Statement

- Millions of idle GPUs/PCs (consumer and enterprise) exist globally with no trustworthy way to monetize them.
- Developers who need compute must either overpay hyperscalers or navigate GPU-only marketplaces that assume infrastructure fluency (Docker, manual GPU spec comparison).
- No existing marketplace treats compute as a resource-agnostic bundle (GPU + CPU + RAM + storage), which turns away workloads that need balanced (not just GPU-heavy) resources.
- Trust is the single biggest blocker on both sides: hosts don't trust strangers running code on their machine; developers don't trust that a stranger's advertised hardware is real.
- India-based developers/hosts are underserved by US-centric marketplaces (no UPI, no GST invoicing, no regional support).

## 3. Goals & Objectives

| Goal | Success looks like |
|---|---|
| Ship a working two-sided marketplace | Hosts list resources; developers rent and run workloads end-to-end |
| Make onboarding frictionless for both sides | Non-technical gamer can list a GPU; non-infra developer can launch Stable Diffusion in one click |
| Establish trust from day one | Every host is hardware-verified and benchmarked; every workload is isolated; reputation is visible |
| Remove "no supply" as a failure mode | Hybrid bursting to AWS/Azure/GCP/RunPod/Vast covers local supply gaps |
| Win India as a wedge market | UPI billing, GST invoices, INR pricing, India support live at MVP |
| Make resource selection effortless | AI Router + AI Copilot replace manual GPU comparison |

## 4. Target Users / Personas

**Host personas**
- *Individual gamer/PC owner* — has an RTX 3060–4090 idle most of the day; wants passive income with zero technical setup.
- *Small datacenter/server operator* — has multiple machines/workstations; wants revenue analytics and pricing automation.

**Developer personas**
- *Indie AI builder / non-infra-savvy developer* — wants to run Stable Diffusion/Ollama/ComfyUI without knowing Docker.
- *ML engineer / researcher* — wants fine-tuning or training compute at the best price/performance, comfortable with manual GPU selection when needed.
- *India-based startup/student/researcher* — needs INR pricing, UPI payment, and GST-compliant invoicing.

## 5. Complete User Journeys (Product-Level)

### 5.1 Host Journey
1. Sign up (email/OAuth) → phone verification.
2. Install Host Agent (single downloadable binary, guided non-technical flow) → hardware auto-detected.
3. Hardware verification: specs cross-checked + automated benchmark suite scores the machine.
4. Agent sends live heartbeat (idle/busy/offline, temperature, power draw).
5. Auto-pricing suggests a competitive price; host accepts or overrides.
6. Listing goes live (as GPU, full workstation, or CPU/RAM/storage bundle) after verification passes.
7. Host dashboard shows revenue analytics, health/temperature monitoring, electricity cost estimate, idle-time prediction, and expected monthly income.

### 5.2 Developer Journey
1. Sign up (email/OAuth) → wallet auto-created (₹0/$0).
2. Intent-based entry point: "What do you want to run?" (Fine-tune Llama, Train YOLO, Render Blender, Run ComfyUI, Video generation, Agent hosting, or Something custom).
3. AI Copilot / AI Resource Router: developer states a goal or budget → recommendation with machine, estimated time, estimated cost.
4. Manual browse mode remains available (filter by GPU type, price, location, reputation) for power users.
5. Developer confirms selection → wallet balance checked → funds held.
6. Zero-setup launch if intent matches a known template (Stable Diffusion, Ollama, ComfyUI, Llama 3); otherwise standard container/image flow.
7. Scheduler checks Kynetic's own network first; if no match (e.g., no H100 in-network), automatically bursts to the Hybrid Compute Broker (AWS/Azure/GCP/RunPod/Vast) — transparent to the developer.
8. Instance provisioned: isolated microVM/container, ephemeral NVMe volume, ephemeral SSH key.
9. Developer connects via SSH (direct or NAT relay) or, for one-click apps, a web UI link.
10. Workload runs under enforced resource caps; runtime monitoring active.
11. Real-time usage metrics stream to monitoring every few seconds.
12. Usage metered per-second → wallet debited in local currency (INR via UPI wallet, or USD); low-balance warning; zero-balance auto-terminates.
13. On completion, job outcome feeds the host's reputation score.
14. Instance terminated (manual/auto) → container/VM destroyed → NVMe cryptographically wiped → usage reconciled.
15. Host receives payout (platform fee deducted) via UPI (India) or bank/Stripe Connect (global), with GST invoice auto-generated for Indian users.

## 6. Core Feature Set (MVP)

### Marketplace & Compute
- Compute-first marketplace (GPU/CPU/RAM/NVMe/full workstations as one inventory)
- Consumer hardware onboarding flow
- Real-time resource discovery/availability indexing
- Manual browse/search/filter, alongside AI-native mode

### AI-Native Layer
- Intent-based entry point ("what do you want to run?")
- One-click app templates: Stable Diffusion, Ollama, ComfyUI, Llama 3 (extensible)
- AI Resource Router (budget/goal-based automatic machine selection)
- AI Copilot (conversational cost/time estimation before launch)

### Host Experience
- Host dashboard: revenue analytics, health/temperature monitoring, electricity cost estimation
- Auto-pricing engine
- Idle-time prediction and expected monthly income projection

### Hybrid & Multi-Cloud
- Hybrid Compute Broker — automatic burst to AWS/Azure/GCP/RunPod/Vast behind one unified API

### Trust & Reputation
- Reputation Layer: uptime, latency, network, job-success rate, benchmark score, response time — visible per listing

### Regional (India-First)
- UPI billing integration
- GST-compliant invoice generation
- Dual (INR/USD) pricing display
- India-based support channel

### Core Platform
- Authentication, Wallet, Billing (usage-based), Scheduler, Provisioning Service, SSH Access, Developer Dashboard, Monitoring, Usage Tracking, Instance Lifecycle Management, Notifications, Logs, Ephemeral Storage, Networking

## 7. Explicitly Out of Scope (MVP)

- Enterprise SSO/SCIM
- Multi-region orchestration beyond hybrid bursting
- Compute futures/derivatives
- Full confidential computing (hardware-enforced memory encryption / TPM-backed remote attestation)
- Custom enterprise clusters
- Extreme/Future-tier security capabilities: AI-native Security Intelligence, full graph-based ML fraud detection, eBPF kernel-level runtime detection, SOC 2 Type II / ISO 27001 / HIPAA certification, enterprise workspaces/RBAC/SSO/SCIM

## 8. Success Metrics (Launch-Readiness Definition)

Per the source roadmap's launch checklist, the product is considered MVP-complete only when every item below is true:

- Host Agent installs cleanly and verifies hardware on GPUs, full workstations, and consumer gaming PCs
- Benchmark suite runs automatically and flags mismatched specs
- Marketplace lists all resource types correctly
- Auto-pricing engine produces sane, competitive suggestions
- Wallet correctly holds/deducts/refunds in INR and USD with no rounding errors
- Instance provisioning succeeds reliably (>99%) end-to-end, including templates
- One-click launches work for all four launch templates
- AI Resource Router and AI Copilot return sensible, grounded recommendations/estimates
- SSH works for public-IP and NAT'd hosts
- Hybrid Compute Broker successfully bursts to at least one external provider
- Reputation scores update correctly after job completion
- Razorpay/UPI payments and GST invoices work end-to-end
- Per-second metering matches actual consumption within tolerance
- Auto-termination triggers correctly on zero balance/expiry
- Secure deletion is verified after every termination
- Isolation is tested against basic escape attempts
- Rate limiting is active on all public endpoints
- Malware/image scanning is active on every container/template
- Runtime monitoring flags cryptomining/abuse signatures
- Kill switch works across native and hybrid instances
- Audit logs capture every critical action
- Host payout flow works end-to-end
- Notifications fire correctly
- Scheduler and AI Router are load-tested under concurrency
- Incident response runbook and on-call rotation exist
- ToS, acceptable use policy, and refund policy are published

---

# Part II — Technical Requirements Document (TRD)

## 1. Full Tech Stack (Authoritative — nothing outside this list is used)

| Layer | Technology |
|---|---|
| Backend API framework | FastAPI (every service) |
| ASGI server | Uvicorn behind Gunicorn |
| ORM / migrations | SQLAlchemy 2.0 (async) + Alembic |
| Primary database | PostgreSQL |
| Cache / broker | Redis |
| Async task queue | Celery |
| Cron-like scheduling | APScheduler (or Celery Beat) |
| Host Agent | Python, PyInstaller-packaged; `psutil` (CPU/RAM/disk), `pynvml`/`GPUtil` (GPU telemetry) |
| Hardware benchmarking | PyTorch + custom benchmark scripts |
| AI Resource Router / Copilot | LangChain + OpenAI/Anthropic API (or self-hosted LLM via vLLM) |
| Auto-pricing / idle prediction | scikit-learn + pandas |
| Reputation scoring | scikit-learn / weighted-scoring logic |
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

## 2. Functional Requirements by Module

### 2.1 Auth Service
- FR-1: System must support signup/login via email or OAuth, issuing short-lived JWT access tokens + refresh tokens.
- FR-2: System must support both `host` and `developer` roles on a single account (`role` field, extendable).
- FR-3: System must support phone OTP verification.
- FR-4: System must support identity verification tiers (phone → government ID) that drive `trust_tier` limits.
- FR-5: Every authenticated write action must produce an immutable `audit_logs` entry.

### 2.2 Host Onboarding & Verification
- FR-6: Host Agent must detect CPU/RAM/disk via `psutil` and GPU via `pynvml`/`GPUtil`, and register over mTLS.
- FR-7: System must cross-check reported specs against known hardware signatures and flag mismatches.
- FR-8: System must run a PyTorch-based benchmark suite (LLM inference, image-gen, raw FLOPs) automatically post-registration and on a periodic schedule.
- FR-9: System must ingest heartbeats (idle/busy/offline, temperature, power draw) at a regular interval and maintain live host status.

### 2.3 Marketplace
- FR-10: Listings must be resource-agnostic (GPU, CPU, RAM, NVMe, or a full-workstation bundle), not a GPU-type enum.
- FR-11: Listings must only be creatable from a `verified` host.
- FR-12: Marketplace must support browse/search/filter by resource type, price, GPU model, region, and reputation score.
- FR-13: Listing availability must reflect live host heartbeat status.

### 2.4 Wallet & Billing
- FR-14: Every developer account must receive an auto-created wallet (₹0/$0) on signup.
- FR-15: Wallet must support top-up (Stripe for global, Razorpay/UPI for India) and hold/debit/refund operations with no cross-currency rounding drift.
- FR-16: Every instance must be metered per-second and the wallet debited incrementally in near real time.
- FR-17: Zero balance must auto-terminate the associated instance(s); low balance must trigger a notification.
- FR-18: All wallet transactions must be immutable/append-only.
- FR-19: GST-compliant invoices must be auto-generated for Indian transactions.

### 2.5 Provisioning & Scheduling
- FR-20: The Scheduler must match a confirmed rental to an available listing (manual mode) or a Router recommendation (AI mode).
- FR-21: If no in-network match exists, the Scheduler must automatically invoke the Hybrid Compute Broker, transparently to the developer.
- FR-22: Every workload must run inside a container nested in a Firecracker microVM, with zero access to host OS/files.
- FR-23: Ephemeral NVMe storage must be allocated per instance and cryptographically shredded on termination, verified before the instance is marked `terminated`.
- FR-24: SSH access must use short-lived, auto-rotated keys; NAT'd hosts must be reachable via a WireGuard relay.
- FR-25: One-click templates (Stable Diffusion, Ollama, ComfyUI, Llama 3) must auto-configure the container with zero Docker knowledge required from the developer.
- FR-26: Every template/container image must pass malware/image scanning and be signed before it is executable.

### 2.6 AI Resource Router & Copilot
- FR-27: The Router must accept a budget or a goal and return a ranked set of matching listings with estimated cost and time, using live pricing, benchmark, and reputation data.
- FR-28: The Copilot must translate free-text intent into a structured Router call and narrate the result in natural language, without fabricating numbers not returned by the Router.
- FR-29: Router and Copilot endpoints must be rate-limited.

### 2.7 Reputation & Auto-Pricing
- FR-30: Reputation must be computed as a transparent, explainable weighted score (uptime, latency, network, job success rate, benchmark score, response time), recomputed after every completed job.
- FR-31: Auto-pricing must produce a scikit-learn-derived price suggestion at listing creation/update, which the host may accept or override.
- FR-32: Idle-time prediction and income projection must be computed per host on a scheduled basis.

### 2.8 Hybrid Compute Broker
- FR-33: The Broker must expose a single internal interface abstracting AWS, Azure, GCP, RunPod, and Vast.
- FR-34: Hybrid-provisioned instances must feed the same billing/monitoring pipeline as native instances.
- FR-35: The kill switch must be able to revoke hybrid-provisioned instances.

### 2.9 Security (cross-cutting; MVP tier per Security Architecture)
- FR-36: Rate limiting must apply to all public API endpoints.
- FR-37: Runtime monitoring must detect and act on cryptomining/abuse signatures during job execution.
- FR-38: An admin-triggered kill switch must instantly suspend any workload, host, or account (native or hybrid).
- FR-39: Multi-account abuse must be detectable via device fingerprinting.
- FR-40: New accounts must start at a restrictive `trust_tier` (capped instance size/GPU-hours/spend) that unlocks progressively.

### 2.10 Monitoring, Dashboards & Notifications
- FR-41: All services must be instrumented with `prometheus-client`; platform health must be visible in Grafana.
- FR-42: All service logs must be structured (`structlog`) and centrally shipped (Loki/ELK) with correlation IDs.
- FR-43: Event-driven notifications must fire for low balance, instance lifecycle events, payout confirmations, and invoice availability.

## 3. Non-Functional Requirements

| Category | Requirement |
|---|---|
| Availability | Instance provisioning success rate ≥ 99% end-to-end |
| Billing accuracy | Per-second metering must match actual consumption within a defined tolerance; zero rounding errors across INR/USD |
| Security | Every workload isolated via container-in-microVM; zero host OS/file access; ephemeral, auto-rotated credentials only |
| Data integrity | `audit_logs` and `wallet_transactions` are immutable/append-only |
| Performance | Scheduler and AI Router must be load-tested under concurrent request volume before launch |
| Compliance | GDPR-compliant data handling architected in from day one (not retrofitted); GST-compliant invoicing for India |
| Observability | Every service exposes health checks and Prometheus metrics; all logs correlate via request/trace IDs |
| Extensibility | Template registry must support new one-click apps via configuration, not code changes |

## 4. Data Model Summary

See Appendix B for the full entity list. Core entities: `users`, `hosts`, `host_hardware_specs`, `host_benchmarks`, `host_heartbeats`, `listings`, `wallets`, `wallet_transactions`, `instances`, `ssh_sessions`, `templates`, `router_recommendations`, `copilot_sessions`/`copilot_messages`, `reputation_scores`, `pricing_suggestions`, `idle_predictions`, `hybrid_jobs`, `invoices`, `notifications`, `audit_logs`, `security_event_logs`, `trust_tiers`, `device_fingerprints`, `kill_switch_events`.

## 5. External Integrations

| Integration | Purpose | SDK/Client |
|---|---|---|
| Stripe | Global wallet top-up, host payouts | Stripe Python SDK, Stripe Connect |
| Razorpay | India wallet top-up (UPI), payouts, GST invoicing | Razorpay Python SDK |
| AWS | Hybrid compute bursting | boto3 |
| Azure | Hybrid compute bursting | azure-sdk-for-python |
| GCP | Hybrid compute bursting | google-cloud-python |
| RunPod / Vast | Hybrid compute bursting | httpx REST clients |
| OpenAI/Anthropic (or self-hosted vLLM) | AI Copilot conversational layer | LangChain |
| S3-compatible storage | Container images, templates, logs | boto3 (AWS S3 or MinIO) |

## 6. Testing Requirements

- Unit + integration tests via `pytest` + `pytest-asyncio` for every FastAPI service.
- CI (GitHub Actions) runs lint (`ruff`), tests, and `alembic upgrade head` against a test Postgres instance on every PR.
- Load testing required pre-launch for the Scheduler and AI Router under concurrency (async `httpx`-driven concurrency tests, consistent with the existing stack).
- Security testing: isolation must be validated against basic container/VM escape attempts before launch.

---

# Part III — Architecture Document

## 1. System Context

Two external actor types (Host, Developer) interact with the platform through a Next.js frontend. All backend services are Python/FastAPI, share one PostgreSQL database (via SQLAlchemy 2.0 async + Alembic), and communicate internally over async REST (httpx) behind a single API Gateway. Redis backs caching, sessions, and Celery. Object storage is S3-compatible.

## 2. High-Level Architecture Diagram

```
                              ┌─────────────────────┐
                              │   Frontend (Web)      │
                              │ Next.js + React + TS + │
                              │ Tailwind — Developer + │
                              │ Host UI + AI Copilot   │
                              │ Chat Widget            │
                              └──────────┬────────────┘
                                         │ HTTPS/REST + WebSocket (JWT auth)
                              ┌──────────▼────────────┐
                              │      API Gateway        │
                              │ (FastAPI, Auth check,   │
                              │  Rate Limiting)          │
                              └──┬────┬────┬────┬────┬──┘
        ┌─────────────────────────┘    │    │    │    └──────────────────────┐
        ▼                              ▼    ▼    ▼                           ▼
┌───────────────┐   ┌──────────────────┐  ┌──────────────────┐   ┌────────────────────┐
│ Auth Service    │   │ Marketplace /     │  │ AI Resource        │   │  Wallet / Billing    │
│ (FastAPI)       │   │ Scheduler Service  │  │ Router + Copilot   │   │  Service (FastAPI)   │
└────────┬────────┘   │ (FastAPI)          │  │ (FastAPI +          │   └──────────┬──────────┘
         │             └────────┬───────────┘  │  LangChain/LLM API) │              │
         │                      │               └──────────┬─────────┘              │
         │             ┌────────▼───────────┐               │                        │
         │             │ Provisioning Service │◄──────────────┘                        │
         │             │ (FastAPI + Celery)    │                                       │
         │             └────┬─────────────┬────┘                                       │
         │                  │             │                                            │
         │        mTLS      │             │  REST/SDK                                  │
         │        ┌─────────▼──┐    ┌─────▼──────────────┐                             │
         │        │ Host Agent   │    │ Hybrid Compute       │                          │
         │        │ (Python,     │    │ Broker (FastAPI +     │                          │
         │        │ on host PCs) │    │ boto3/azure-sdk/       │                          │
         │        └─────┬────────┘    │ google-cloud SDKs +    │                         │
         │              │              │ RunPod/Vast API clients)│                        │
         │        ┌─────▼────────┐    └────────────┬────────────┘                        │
         │        │ Reputation &   │                │                                     │
         │        │ Auto-Pricing   │                │                                     │
         │        │ Engine (Celery │                │                                     │
         │        │ + scikit-learn)│                │                                     │
         │        └───────┬────────┘                │                                     │
         │                │                          │                                     │
         │        ┌───────▼──────────────────────────▼───────┐                            │
         │        │           Monitoring Service                │◄───────────────────────────┘
         │        │      (FastAPI + Prometheus client)          │
         │        └───────────────────┬───────────────────────┘
         │                            │
┌────────▼────────────────────────────▼──────────────────────┐
│                Primary Database (PostgreSQL)                  │
│ users · hosts · instances · wallets · transactions · listings │
│ · reputation_scores · templates · hybrid_jobs (via SQLAlchemy) │
└────────────────────────────┬──────────────────────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │  Object Storage      │
                    │ (S3-compatible:       │
                    │ container images,     │
                    │ logs, templates)       │
                    └───────────────────────┘
```

## 3. Service Breakdown

| Service | Responsibility | Key Tech |
|---|---|---|
| `api_gateway` | Routing, JWT validation, global rate limiting | FastAPI |
| `auth_service` | Signup/login, JWT issuance, phone/ID verification, trust tiers | FastAPI-Users, python-jose, passlib |
| `marketplace_service` | Listings, discovery, Scheduler, manual browse/filter | FastAPI |
| `provisioning_service` | Instance provisioning/teardown, isolation, SSH, templates | FastAPI + Celery, Docker, Firecracker |
| `wallet_billing_service` | Wallet, per-second metering, Stripe/Razorpay, invoices | FastAPI, Stripe SDK, Razorpay SDK |
| `ai_router_copilot_service` | Budget/goal-based recommendation + conversational copilot | FastAPI, LangChain |
| `reputation_pricing_service` | Reputation scoring, auto-pricing, idle prediction | Celery, scikit-learn, pandas |
| `hybrid_broker_service` | Multi-cloud provisioning abstraction | FastAPI, boto3, azure-sdk, google-cloud-python |
| `monitoring_service` | Metrics ingestion (native + hybrid), health dashboards | FastAPI, prometheus-client |
| `host_agent` | Runs on host machines: hardware detection, benchmarking, telemetry, job execution | Python, PyInstaller, psutil, pynvml/GPUtil, PyTorch |

## 4. Data Flow (Key Paths)

**Host onboarding:** Host Agent → mTLS → `provisioning_service`/`marketplace_service` registration endpoint → hardware cross-check → benchmark suite (PyTorch, run on host, validated server-side) → `hosts.status = verified` → listing created.

**Rental (manual):** Developer browses `marketplace_service` listings → confirms → `wallet_billing_service` places hold → `marketplace_service` Scheduler assigns host or, on no match, calls `hybrid_broker_service` → `provisioning_service` provisions container-in-microVM → SSH/web-UI link returned → `monitoring_service` streams usage → `wallet_billing_service` meters per second → on termination, secure deletion verified → `reputation_pricing_service` updates host score.

**Rental (AI-native):** Developer states intent to `ai_router_copilot_service` (chat or structured) → Router queries `marketplace_service` (availability), `host_benchmarks`, and `reputation_pricing_service` (score) → ranked recommendation returned → developer confirms → same provisioning path as manual rental.

**Billing (India):** `wallet_billing_service` routes India-region top-ups/payouts through Razorpay; generates GST invoice on transaction completion; global routes through Stripe/Stripe Connect.

## 5. Database Architecture

- **Engine:** PostgreSQL, accessed via SQLAlchemy 2.0 (async) across all services; schema evolution via Alembic migrations.
- **Single source of truth:** all services share one primary database (per the source architecture diagram), with tables logically owned per service/domain (see Appendix B).
- **Immutability requirement:** `audit_logs`, `wallet_transactions`, and `security_event_logs` are append-only at the application layer — no update/delete permitted on these tables outside of migrations.
- **Caching/session/queue layer:** Redis backs FastAPI-Users/session cache, Celery broker + result backend, and marketplace availability caching.
- **Object storage:** S3-compatible (AWS S3 or self-hosted MinIO) via boto3, storing container images, templates, and logs.

## 6. Isolation & Execution Architecture

- Every workload executes inside a **Docker container nested inside a Firecracker microVM** on the host machine, orchestrated by the Host Agent's Python control process.
- No shared kernel with the host; no host OS/file access is ever exposed to the workload.
- Ephemeral, per-job NVMe volumes are allocated for the job's lifetime only and cryptographically shredded (key destruction) on termination.
- Per-job private network namespace with default-deny outbound except declared endpoints.
- SSH access uses short-lived, auto-rotated keypairs; NAT'd hosts are reached via a WireGuard relay orchestrated by a Python control service.

## 7. Security Architecture (MVP Tier)

Mapped from `Kynetic_AI_Security_Architecture.md`, MVP-tier items only (Extreme/Future-tier items are explicitly deferred — see PRD §7):

| Pillar | MVP Implementation |
|---|---|
| Zero Trust Compute Isolation | Container-in-microVM, ephemeral storage, auto-rotated SSH keys |
| Network Security & Segmentation | Per-job network namespace, default-deny firewall |
| Hardware & Host Verification | Spec cross-check + periodic PyTorch re-benchmarking |
| Identity, Reputation & Progressive Trust | Phone/ID verification tiers, capped limits for new accounts |
| Runtime Threat Detection | Image scanning pre-execution + basic resource/crypto-mining signature monitoring |
| Fraud & Marketplace Abuse Prevention | Rule-based checks: multi-account (device fingerprinting), payment fraud patterns |
| Supply Chain Security | Basic image scanning + signing |
| Emergency Response | Manual, instant kill switch (native + hybrid) |
| Privacy by Design | Minimal data collection, purpose-scoped log separation |
| Compliance | GDPR-compliant architecture from day one (not certified, compliant) |

Deferred to post-MVP: confidential computing (Pillar 8), full hardware attestation via TPM, AI-native Security Intelligence (Pillar 7), full graph-based ML fraud detection, eBPF kernel-level detection, SOC 2 Type II/ISO 27001/HIPAA, enterprise RBAC/SSO/SCIM (Pillar 13).

## 8. Deployment Architecture

- **Local development:** Docker Compose (Postgres, Redis, all FastAPI services with hot reload).
- **Production:** Kubernetes for all FastAPI services and Celery workers; Terraform for reproducible infra provisioning.
- **CI/CD:** GitHub Actions — lint (`ruff`) + tests (`pytest`/`pytest-asyncio`) + Alembic migration check on every PR; Docker image build/push on merge to main.
- **Observability stack:** `prometheus-client` per service → Grafana dashboards; `structlog` per service → Loki or ELK for centralized, correlated logs.

## 9. Suggested Monorepo Structure

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

## 10. Scalability Considerations

- Stateless FastAPI services scale horizontally behind the API Gateway/Kubernetes.
- Celery workers scale independently per queue (provisioning, billing metering, reputation/pricing, notifications) to isolate load spikes in one domain from another.
- Redis-backed caching of marketplace availability reduces read load on PostgreSQL for high-frequency browse/search traffic.
- Hybrid Compute Broker absorbs local-supply spikes, decoupling developer-facing availability from native host-fleet size.
- Reputation and auto-pricing models are trained/retrained via scheduled Celery jobs, decoupled from the request path.

---

# Appendices

## Appendix A — Full API Surface (Consolidated)

```
# Auth
POST   /auth/signup
POST   /auth/login
POST   /auth/refresh
POST   /auth/logout
GET    /auth/me
POST   /auth/phone/send-otp
POST   /auth/phone/verify-otp
POST   /identity/verify/id-document
GET    /users/{id}/trust-tier

# Hosts
POST   /hosts/register
POST   /hosts/heartbeat
GET    /hosts/{host_id}
GET    /hosts/{host_id}/benchmarks
POST   /hosts/{host_id}/benchmarks/rerun
GET    /hosts/{id}/dashboard
GET    /hosts/{id}/reputation

# Listings / Marketplace
POST   /listings
GET    /listings
GET    /listings/{id}
PATCH  /listings/{id}
DELETE /listings/{id}
GET    /pricing/suggest?listing_id=...

# Wallet / Billing
GET    /wallet/balance
GET    /wallet/transactions
POST   /wallet/topup
POST   /wallet/topup/upi
POST   /billing/webhooks/stripe
POST   /billing/webhooks/razorpay
GET    /billing/invoices/{id}

# Instances / Provisioning
POST   /instances
GET    /instances/{id}
POST   /instances/{id}/stop
POST   /instances/{id}/start
POST   /instances/{id}/terminate
GET    /instances/{id}/connection
GET    /instances/{id}/web-ui

# Templates
GET    /templates
POST   /templates                 (admin)

# AI Router / Copilot
POST   /router/recommend
POST   /copilot/chat              (WebSocket)
GET    /copilot/sessions/{id}/history

# Hybrid Compute
POST   /hybrid/provision          (internal)
POST   /hybrid/terminate          (internal)
GET    /hybrid/{job_id}/status

# Admin / Security
POST   /admin/kill-switch
GET    /admin/security-events

# Monitoring / Notifications
GET    /monitoring/metrics        (Prometheus scrape, per service)
GET    /notifications
POST   /support/tickets

# Health
GET    /healthz                   (every service)
```

## Appendix B — Full Data Model (Consolidated)

- `users` (id, email, hashed_password, role, phone_number, phone_verified, is_active, created_at)
- `sessions` / `refresh_tokens`
- `audit_logs` (id, actor_id, action, resource_type, resource_id, metadata JSONB, created_at)
- `hosts` (id, user_id, status, os_type, agent_version, mtls_cert_fingerprint, created_at)
- `host_hardware_specs` (host_id, cpu_cores, ram_gb, disk_type, disk_gb, gpu_model, gpu_vram_gb, driver_version, reported_at)
- `host_benchmarks` (id, host_id, benchmark_type, score, raw_metrics JSONB, run_at)
- `host_heartbeats` (host_id, status, temperature_c, power_draw_w, recorded_at)
- `listings` (id, host_id, resource_type, gpu_model, cpu_cores, ram_gb, storage_gb, storage_type, price_per_hour_usd, price_per_hour_inr, status, region, created_at)
- `wallets` (id, user_id, balance_usd, balance_inr, preferred_currency, created_at)
- `wallet_transactions` (id, wallet_id, type, amount, currency, reference_id, created_at)
- `stripe_accounts` (user_id, stripe_customer_id, stripe_connect_account_id)
- `instances` (id, developer_id, listing_id, host_id, status, ssh_key_id, started_at, stopped_at, billed_seconds, hold_amount, currency)
- `ssh_sessions` (id, instance_id, public_key, private_key_encrypted, issued_at, rotated_at, revoked_at)
- `secure_deletion_receipts` (instance_id, verified_at, method)
- `device_fingerprints` (user_id, fingerprint_hash, first_seen, last_seen)
- `trust_tiers` (user_id, tier, instance_size_cap, gpu_hour_cap, spend_cap, updated_at)
- `security_event_logs` (id, event_type, severity, resource_type, resource_id, details JSONB, created_at)
- `kill_switch_events` (id, target_type, target_id, triggered_by, reason, triggered_at)
- `templates` (id, name, base_image, required_gpu_vram_gb, required_ram_gb, startup_command, exposed_web_ui_path, status, created_at)
- `router_recommendations` (id, developer_id, request_payload JSONB, recommended_listing_ids JSONB, created_at)
- `copilot_sessions` (id, developer_id, created_at)
- `copilot_messages` (id, session_id, role, content, created_at)
- `reputation_scores` (id, host_id, uptime_score, latency_score, network_score, job_success_rate, benchmark_score, response_time_score, composite_score, computed_at)
- `pricing_suggestions` (id, listing_id, suggested_price_usd, suggested_price_inr, accepted, created_at)
- `idle_predictions` (host_id, predicted_idle_hours_per_day, income_projection_monthly, computed_at)
- `hybrid_jobs` (id, instance_id, provider, provider_instance_id, provisioned_at, terminated_at, provider_cost_raw JSONB)
- `invoices` (id, transaction_id, gstin, invoice_number, pdf_url, issued_at)
- `notifications` (id, user_id, type, channel, payload JSONB, sent_at, read_at)
- `support_tickets` (id, user_id, region, subject, status, created_at)

## Appendix C — Phase Cross-Reference

This PRD/TRD/Architecture spec describes the full target system. For a phased, dependency-ordered build sequence (10 phases with detailed tasks, exit criteria, and per-phase security controls), see the companion document `Kynetic_AI_Implementation_Plan.md`.

## Appendix D — Explicitly Out of Scope

See PRD §7 and Architecture §7 — Extreme/Future-tier security capabilities and enterprise-tier features are intentionally deferred beyond this MVP and are not part of this specification.
