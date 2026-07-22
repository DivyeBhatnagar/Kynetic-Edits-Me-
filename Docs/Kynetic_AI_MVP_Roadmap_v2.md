# Kynetic AI — MVP Engineering Roadmap (v2)

### Compute-First Marketplace: From Zero to Production-Ready v1 — Python Backend Edition

---

## What Changed in v2

This version expands Kynetic from a "GPU rental" MVP into a **compute-first, AI-native marketplace**, and rebuilds the tech stack around Python end-to-end on the backend. Ten new capabilities are folded directly into the MVP:

1. Compute-first marketplace (GPU + CPU + RAM + NVMe + full workstations)
2. Consumer hardware onboarding (gaming PCs, RTX cards)
3. Zero-setup, one-click app launches (Stable Diffusion, Ollama, ComfyUI, Llama 3)
4. AI-native intent-based marketplace ("what do you want to run?")
5. Best-in-class host experience (analytics, auto-pricing, idle prediction)
6. AI Resource Router (budget/speed-based auto-selection instead of GPU picking)
7. Hybrid Compute Bursting (AWS/Azure/GCP/RunPod/Vast fallback)
8. India-first billing and support (UPI, GST invoices, regional pricing)
9. Reputation Layer (uptime/latency/network/job-success/benchmark scores)
10. AI Copilot (conversational resource selection and cost estimation)

---

## 1. Complete User Journey (Updated)

### Host Side

| Step | What Happens Behind the Scenes |
|---|---|
| **1. Host signs up** | Email/OAuth signup → account created → phone verification triggered. |
| **2. Host installs Host Agent** | Python-based agent (packaged with PyInstaller) installs, detects GPU/CPU/RAM/NVMe/full-workstation specs via `psutil` + `pynvml`/`GPUtil`, registers over mTLS. |
| **3. Hardware verification** | Agent reports specs → backend cross-checks against known hardware signatures → automated benchmark suite (LLM inference test, image-gen test, raw FLOPs test) runs and scores the machine. |
| **4. GPU/resource discovery** | Agent sends heartbeat every few seconds with live status (idle/busy/offline, temperature, power draw) → indexed in real time. |
| **5. Auto-pricing suggestion** | A pricing model (scikit-learn regression trained on marketplace supply/demand + hardware class) suggests a competitive price; host can accept or override. |
| **6. Listing resources** | Listing goes live — as a GPU, a full workstation, or a bundle of CPU/RAM/storage — after passing verification. |
| **7. Host dashboard experience** | Host sees revenue analytics, health monitoring, temperature trends, electricity cost estimate, idle-time prediction, and expected monthly income. |

### Developer Side

| Step | What Happens Behind the Scenes |
|---|---|
| **8. Developer signup** | Email/OAuth signup → wallet auto-created ($0 / ₹0 balance). |
| **9. Intent-based entry point** | Instead of "browse GPUs," developer is asked: *"What do you want to run?"* — Fine-tune Llama, Train YOLO, Render Blender, Run ComfyUI, Video generation, Agent hosting, or "Something custom." |
| **10. AI Copilot / AI Resource Router** | Developer types a goal or budget ("I need GPU for LoRA training," or "I have ₹120 budget," or "I need fastest") → the router (rule engine + LLM via `langchain`/OpenAI SDK, backed by benchmark + pricing data) recommends the exact machine, estimated time, and estimated cost. |
| **11. Browsing marketplace (manual mode)** | For power users who still want manual control: filterable list by GPU type, price, location, reputation score. |
| **12. Selecting & confirming** | Developer reviews recommendation (or manual pick), confirms → wallet balance checked → funds reserved (hold). |
| **13. Zero-setup app launch** | If the intent matches a known template (Stable Diffusion, Ollama, ComfyUI, Llama 3, etc.), the platform auto-configures the container — no Docker knowledge required. Otherwise, standard container/image launch flow applies. |
| **14. Scheduling** | Scheduler checks Kynetic's own network first; if no matching machine is available (e.g., no H100 in-network), it automatically bursts to the **Hybrid Compute Broker**, which checks AWS/Azure/GCP/RunPod/Vast via their APIs and provisions there instead — transparently to the developer. |
| **15. Instance provisioning** | Provisioning service dispatches job to Host Agent (or cloud broker) → isolated microVM/container created → ephemeral NVMe volume attached → ephemeral SSH key generated. |
| **16. SSH connection** | Developer connects via SSH (direct or NAT relay); for one-click apps, a web UI link (e.g., ComfyUI's interface) is also provided instead of raw SSH. |
| **17. Running workloads** | Workload runs under enforced resource caps; runtime monitoring active throughout. |
| **18. Monitoring usage** | Real-time usage metrics streamed to the monitoring service every few seconds. |
| **19. Billing** | Usage metered per-second → wallet debited incrementally in the developer's local currency (INR via UPI-linked wallet, or USD) → low-balance triggers warning, zero balance auto-terminates. |
| **20. Reputation update** | On completion, the job's success/failure, latency, and performance feed into the host's reputation score (uptime, latency, network, job success rate, benchmark score, response time). |
| **21. Instance termination** | Instance stopped (manually or automatically) → container/VM destroyed → NVMe volume cryptographically wiped → usage reconciled. |
| **22. Host receives payout** | Platform fee deducted → net earnings credited to host wallet → payout via UPI (India) or bank/Stripe Connect (global) on schedule, with GST invoice auto-generated for Indian hosts/developers. |

---

## 2. Core Features (MVP — Updated)

### Marketplace & Compute
- **Compute-first marketplace** — list and rent GPUs, CPU cores, RAM, NVMe storage, or entire workstations/AI PCs/gaming PCs/enterprise servers as a single inventory, not GPU-only
- **Consumer hardware onboarding flow** — simplified signup path tuned for individual gamers/PC owners (RTX 30/40-series), not just datacenter operators
- Resource discovery, real-time availability indexing
- Marketplace browse/search/filter (manual mode, kept alongside AI-native mode)

### AI-Native Layer
- **Intent-based entry point** ("what do you want to run?") replacing raw GPU-picking as the default flow
- **One-click app templates**: Stable Diffusion, Ollama, ComfyUI, Llama 3 (extensible template system)
- **AI Resource Router** — budget-based ("₹120 budget") or goal-based ("fastest") automatic machine selection
- **AI Copilot** — conversational cost/time estimation and recommendation before launch

### Host Experience
- Host dashboard: revenue analytics, hardware health monitoring, temperature tracking, electricity cost estimation
- **Auto-pricing engine** with recommended pricing based on live market data
- **Idle-time prediction** and **expected monthly income** projection

### Hybrid & Multi-Cloud
- **Hybrid Compute Broker** — automatic burst to AWS/Azure/GCP/RunPod/Vast when in-network supply is unavailable, behind one unified API

### Trust & Reputation
- **Reputation Layer**: uptime score, latency score, network score, job success rate, benchmark score, response time — all visible per host listing

### Regional (India-First)
- UPI billing integration
- GST-compliant invoice generation
- Regional (INR) pricing display alongside USD
- India-based support channel

### Core Platform (carried over from v1)
- Authentication, Wallet, Billing (usage-based), Scheduler, Provisioning Service, SSH Access, Developer Dashboard, Monitoring, Usage Tracking, Instance Lifecycle Management, Notifications, Logs, Ephemeral Storage, Networking

*Still excluded from MVP:* enterprise SSO/SCIM, multi-region orchestration beyond hybrid bursting, compute futures/derivatives, full confidential computing, custom enterprise clusters.

---

## 3. Security (MVP — Unchanged Core, Still P0)

| Feature | Why It's Necessary |
|---|---|
| **VM/Container Isolation** | Prevents a developer's workload from touching the host OS or other tenants. |
| **No Host File Access** | Ensures rented workloads can't read/modify/exfiltrate host files. |
| **SSH Key Management** | Ephemeral, auto-rotated keys eliminate leaked/long-lived credential risk. |
| **Network Isolation** | Stops cross-tenant scanning or attacks. |
| **Host Verification** | Confirms hardware is real and matches claimed specs — now including full workstations, not just GPUs. |
| **Malware Scanning** | Catches malicious images/templates before execution, including one-click app templates. |
| **Runtime Monitoring** | Detects abuse (cryptomining, resource hijacking) during execution. |
| **Rate Limiting** | Protects APIs, including the AI Copilot/Router endpoints, from abuse. |
| **Encryption (at rest & in transit)** | Protects data and credentials. |
| **Audit Logs** | Immutable record for disputes and incident investigation — including hybrid-cloud burst events. |
| **Secure Deletion** | Guarantees unrecoverable data after instance termination. |
| **Abuse Detection** | Flags cryptomining, wallet fraud, multi-account abuse, and reputation manipulation. |
| **Kill Switch** | Instant shutdown capability, extended to also revoke hybrid-cloud provisioned instances. |

---

## 4. System Architecture (Updated)

```
                              ┌─────────────────────┐
                              │   Frontend (Web)      │
                              │ Developer + Host UI +  │
                              │ AI Copilot Chat Widget │
                              └──────────┬────────────┘
                                         │ HTTPS/REST + WebSocket
                              ┌──────────▼────────────┐
                              │      API Gateway        │
                              │ (FastAPI, Auth, Limits)  │
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

**How services communicate:**
- **Frontend ↔ API Gateway:** HTTPS/REST + WebSocket (for AI Copilot chat and live monitoring), JWT session auth.
- **API Gateway ↔ internal services:** internal REST (FastAPI everywhere) over a private network; gateway enforces auth/rate limits first.
- **AI Resource Router / Copilot ↔ Scheduler & Pricing data:** queries live marketplace + benchmark + reputation data via internal REST calls before returning a recommendation.
- **Provisioning Service ↔ Host Agent:** mTLS channel; Celery task queue (backed by Redis) handles async provisioning/teardown jobs reliably.
- **Provisioning Service ↔ Hybrid Compute Broker:** invoked when no in-network match is found; broker abstracts AWS (`boto3`), Azure (`azure-sdk-for-python`), GCP (`google-cloud-python`), RunPod, and Vast behind one internal interface.
- **Host Agent ↔ Reputation & Auto-Pricing Engine:** telemetry (uptime, temperature, job outcomes) feeds a Celery-scheduled scoring/pricing job running scikit-learn models.
- **Monitoring Service:** ingests metrics from both native Host Agents and hybrid-cloud jobs, unifying them into one usage/billing stream.
- **Database:** PostgreSQL as source of truth; Redis for caching, session state, and Celery queues; S3-compatible storage for images/templates/logs.

---

## 5. Tech Stack (Python-First)

| Component | Recommendation | Why |
|---|---|---|
| **Backend API Framework** | **FastAPI** | Async-native, high performance, automatic OpenAPI docs, ideal for a service-heavy architecture — used across every backend service. |
| **ASGI Server** | **Uvicorn** (behind Gunicorn) | Production-grade async serving for FastAPI. |
| **ORM / DB Access** | **SQLAlchemy 2.0 (async)** + **Alembic** | Mature, flexible ORM with async support; Alembic handles schema migrations cleanly. |
| **Database** | **PostgreSQL** | ACID guarantees essential for wallet/billing correctness. |
| **Cache / Queue Broker** | **Redis** | Backs Celery, session cache, and real-time marketplace data caching. |
| **Async Task Queue** | **Celery** | Handles provisioning, teardown, payout, reputation scoring, and pricing jobs reliably and asynchronously. |
| **Task Scheduling (cron-like)** | **APScheduler** (or Celery Beat) | Periodic jobs: benchmark re-runs, payout batches, idle-prediction updates. |
| **Host Agent** | **Python** (packaged via **PyInstaller**), using **psutil** (CPU/RAM/disk), **pynvml** / **GPUtil** (GPU telemetry) | Keeps the entire stack in one language; these libraries give reliable cross-platform hardware telemetry. |
| **Hardware Benchmarking** | **PyTorch** + custom benchmark scripts | Runs real inference/training micro-benchmarks to verify claimed GPU performance. |
| **AI Resource Router / Copilot** | **LangChain** + OpenAI/Anthropic API (or open-source LLM via **vLLM**) | Fastest path to a conversational, context-aware recommendation engine grounded in live marketplace data. |
| **Auto-Pricing & Idle Prediction** | **scikit-learn** (+ **pandas** for feature engineering) | Lightweight, fast-to-train regression/classification models for pricing and idle-time forecasting; no need for heavy deep learning here. |
| **Reputation Scoring** | **scikit-learn** / plain weighted-scoring logic in Python | Transparent, explainable scoring beats a black-box model for a trust-critical feature. |
| **Hybrid Cloud SDKs** | **boto3** (AWS), **azure-sdk-for-python** (Azure), **google-cloud-python** (GCP), plus REST clients for RunPod/Vast (via `httpx`) | Official, well-maintained Python SDKs for every major hybrid target. |
| **HTTP Client (internal/external)** | **httpx** (async) | Modern async-compatible HTTP client, used for all outbound/internal service calls. |
| **Auth** | **FastAPI-Users** or **Ory/Keycloak** (self-hosted) + **python-jose** (JWT) + **passlib** (hashing) | Fast to integrate, Python-native, avoids reinventing session/JWT handling. |
| **Payments (global)** | **Stripe Python SDK** | Proven reliability for developer billing and Stripe Connect for global host payouts. |
| **Payments (India)** | **Razorpay Python SDK** | UPI support, GST-compliant invoicing, built for the Indian market. |
| **Monitoring / Metrics** | **prometheus-client** (Python) + **Grafana** | Standard, Python-native metrics instrumentation across every service. |
| **Logging** | **structlog** + centralized log shipping (e.g., to **Loki** or **ELK**) | Structured, queryable logs across all services and the Host Agent. |
| **Containerization** | **Docker** + **Firecracker microVMs** | Docker for template/image compatibility; Firecracker for secure, lightweight VM isolation (Firecracker itself is Rust, but orchestrated entirely from Python services). |
| **Object Storage** | **S3-compatible** (AWS S3 or self-hosted **MinIO**), accessed via **boto3** | Standard, and boto3 keeps it consistent with the hybrid-cloud broker. |
| **Networking / SSH Relay** | **WireGuard** tunnels, orchestrated via a Python control service | Secure NAT traversal for hosts without public IPs. |
| **Frontend** | **Next.js (React) + TypeScript + Tailwind** | Only non-Python layer, kept as-is — best-in-class for a fast, SEO-friendly marketplace UI; communicates with the Python backend purely over REST/WebSocket. |
| **Infra / Deployment** | **Kubernetes** + **Terraform** + **Docker Compose** (local dev) | Kubernetes for running the FastAPI services and Celery workers reliably at scale; Terraform for reproducible infra. |
| **CI/CD** | **GitHub Actions** | Python-friendly, integrates cleanly with pytest, linting (ruff), and Docker builds. |
| **Testing** | **pytest** + **pytest-asyncio** | Standard, async-compatible testing across FastAPI services. |

---

## 6. Development Roadmap (Updated — 14 Phases)

### Phase 0 — Foundations
**Features:** FastAPI skeleton, Auth service, PostgreSQL schema, CI/CD (GitHub Actions), Redis setup
**Dependencies:** None
**Expected Outcome:** Deployable backend skeleton with working login/signup
**Priority:** P0

### Phase 1 — Host Onboarding & Verification
**Features:** Python Host Agent, hardware detection (`psutil`/`pynvml`), PyTorch benchmark suite, verification flow
**Dependencies:** Phase 0
**Expected Outcome:** A real machine (GPU or full workstation) can register and be verified
**Priority:** P0

### Phase 2 — Compute-First Marketplace
**Features:** Resource discovery, listing creation supporting GPU/CPU/RAM/NVMe/full workstations, browse/search/filter
**Dependencies:** Phase 1
**Expected Outcome:** Verified hosts appear as rentable listings across all resource types
**Priority:** P0

### Phase 3 — Wallet & Billing Core
**Features:** Wallet, usage metering pipeline (Celery), per-second billing, dual-currency support (INR/USD)
**Dependencies:** Phase 0
**Expected Outcome:** Money moves correctly and in the right currency
**Priority:** P0

### Phase 4 — Provisioning & Scheduling
**Features:** Scheduler, provisioning service (FastAPI + Celery), container/VM isolation, ephemeral storage
**Dependencies:** Phases 1–3
**Expected Outcome:** A developer can rent a machine and get a running instance
**Priority:** P0

### Phase 5 — SSH Access & Instance Lifecycle
**Features:** Ephemeral SSH keys, WireGuard NAT relay, start/stop/terminate flows, secure deletion
**Dependencies:** Phase 4
**Expected Outcome:** Developers can connect, run workloads, and cleanly terminate
**Priority:** P0

### Phase 6 — Security Hardening
**Features:** Malware scanning, runtime monitoring, rate limiting, abuse detection, kill switch, audit logs
**Dependencies:** Phases 4–5
**Expected Outcome:** Platform is safe to open to real, paying strangers
**Priority:** P0 (must complete before public launch)

### Phase 7 — Zero-Setup App Templates
**Features:** One-click launch for Stable Diffusion, Ollama, ComfyUI, Llama 3; extensible template system
**Dependencies:** Phase 4
**Expected Outcome:** Developers launch popular workloads with zero Docker knowledge
**Priority:** P0

### Phase 8 — AI Resource Router
**Features:** Budget/goal-based recommendation engine using benchmark + pricing + availability data
**Dependencies:** Phases 2, 7
**Expected Outcome:** Developers say "₹120 budget" or "fastest" and get a matched machine
**Priority:** P1

### Phase 9 — AI Copilot
**Features:** Conversational interface (LangChain + LLM API) for cost/time estimation before launch
**Dependencies:** Phase 8
**Expected Outcome:** Natural-language resource selection with instant estimates
**Priority:** P1

### Phase 10 — Host Experience & Auto-Pricing
**Features:** Revenue analytics dashboard, health/temperature monitoring, electricity cost estimation, auto-pricing engine, idle prediction, income projection
**Dependencies:** Phase 1, 3
**Expected Outcome:** Hosts get a "Shopify for GPU owners" experience
**Priority:** P1

### Phase 11 — Reputation Layer
**Features:** Uptime, latency, network, job-success, benchmark, and response-time scoring, surfaced on listings
**Dependencies:** Phases 4, 5, 10
**Expected Outcome:** Every host has a trustworthy, Uber-style rating
**Priority:** P1

### Phase 12 — Hybrid Compute Bursting
**Features:** Hybrid Compute Broker integrating AWS/Azure/GCP/RunPod/Vast; automatic fallback when no in-network match exists
**Dependencies:** Phase 4
**Expected Outcome:** Jobs never fail to start due to local supply gaps
**Priority:** P1

### Phase 13 — India-First Billing & Support
**Features:** Razorpay/UPI integration, GST invoice generation, INR pricing display, India support channel
**Dependencies:** Phase 3
**Expected Outcome:** Frictionless experience for Indian hosts and developers
**Priority:** P1

### Phase 14 — Monitoring, Dashboards & Notifications
**Features:** Unified monitoring (native + hybrid), developer/host dashboards, logs, notifications
**Dependencies:** Phases 4, 12
**Expected Outcome:** Full visibility and communication across the platform
**Priority:** P1

---

## 7. Launch Checklist (Updated)

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
- [ ] Hybrid Compute Broker successfully bursts to at least one external provider when local supply is unavailable
- [ ] Reputation scores update correctly after job completion
- [ ] Razorpay/UPI payments and GST invoices work end-to-end for Indian users
- [ ] Per-second usage metering matches actual resource consumption within tolerance
- [ ] Auto-termination triggers correctly on zero balance or expiry
- [ ] Secure deletion verified — no residual data recoverable after termination
- [ ] VM/container isolation tested against basic escape attempts
- [ ] Rate limiting active on all public API endpoints, including AI Router/Copilot
- [ ] Malware/image scanning active on every container and template
- [ ] Runtime monitoring flags basic cryptomining/abuse signatures
- [ ] Kill switch tested across native and hybrid-cloud instances
- [ ] Audit logs capture every critical action, including hybrid bursts
- [ ] Host payout flow tested end-to-end (Stripe Connect + Razorpay)
- [ ] Notifications fire correctly for low balance, instance events, and payouts
- [ ] Load-tested scheduler and AI Router under concurrent requests
- [ ] Incident response runbook documented and on-call rotation established
- [ ] Terms of Service, acceptable use policy, and refund policy published (India + global)

---

## Conclusion: Strategic Roadmap Detail — Each Feature Explained

This section closes the roadmap by detailing exactly what each of the ten strategic features is, why it matters, and how it gets built.

### 1. Become the "Airbnb + Stripe" of Compute
**What it is:** A single marketplace renting GPUs, CPU cores, RAM, NVMe storage, and entire workstations/AI PCs/gaming PCs/enterprise servers — not just GPUs.
**Why it matters:** Every competitor (RunPod, Vast, Lambda) is GPU-first. Being compute-first captures workloads that need balanced resources (e.g., CPU-heavy rendering, RAM-heavy data pipelines) that a GPU-only marketplace turns away.
**How it's built:** The listings schema (Phase 2) is resource-agnostic from day one — a listing is a bundle of GPU/CPU/RAM/storage attributes, not a GPU-type enum. The Host Agent already reports all of these via `psutil`/`pynvml`, so no extra onboarding friction is needed.

### 2. Consumer Hardware (RTX 3060–4090)
**What it is:** A simplified onboarding path specifically for individual gamers and PC owners, not just server operators.
**Why it matters:** Millions of idle gaming PCs are a far larger, cheaper supply pool than datacenters — and nobody has aggregated this market properly.
**How it's built:** Phase 1's Host Agent is a single downloadable binary (PyInstaller-packaged) with a guided, non-technical install flow — no CLI expertise required, unlike most competitor onboarding.

### 3. Zero Setup (One-Click Apps)
**What it is:** One-click launch for Stable Diffusion, Ollama, ComfyUI, Llama 3, and similar popular workloads — no Docker knowledge required.
**Why it matters:** Today's marketplaces assume Docker fluency. Removing that barrier expands the addressable developer base to non-infra-savvy AI builders — "Vercel for GPUs."
**How it's built:** Phase 7 introduces a template registry — each template is a pre-built, scanned, verified container image mapped to a specific launch configuration, selectable with a single click from the intent-based entry point.

### 4. AI-Native Marketplace
**What it is:** Replacing "pick a GPU" with "what do you want to run?" as the primary interaction model.
**Why it matters:** Most users don't know or care which GPU they need — they know their task. Matching on intent rather than hardware spec dramatically lowers the barrier to entry.
**How it's built:** The intent-based entry point (Phase 7–8) routes free-text or menu-selected goals into the template system and AI Resource Router, which together configure the right hardware and software automatically.

### 5. Best Host Experience ("Shopify for GPU Owners")
**What it is:** Revenue analytics, health/temperature monitoring, electricity cost estimation, auto-pricing, idle prediction, and expected monthly income — not just a basic earnings number.
**Why it matters:** Hosts are a scarce, high-churn-risk supply side. A best-in-class host dashboard increases retention and encourages more hardware to be listed.
**How it's built:** Phase 10 combines telemetry already streamed by the Host Agent with a scikit-learn pricing/idle-prediction model, surfaced through the host dashboard.

### 6. AI Resource Router
**What it is:** A scheduler that takes a budget ("₹120") or a goal ("fastest") and automatically selects the best-fit machine, instead of making the user compare specs.
**Why it matters:** Nobody wants to compare 500 GPU listings. This becomes Kynetic's core scheduling moat — the more jobs it routes, the better its recommendations get.
**How it's built:** Phase 8 combines live marketplace pricing/availability data, benchmark scores, and reputation data into a single ranking function; over time this evolves from rule-based to ML-based as job outcome data accumulates.

### 7. Hybrid Compute (Cloud Bursting)
**What it is:** If Kynetic's own network has no matching machine (e.g., no H100 available), the platform automatically provisions from AWS, Azure, GCP, RunPod, or Vast — transparently, behind one API.
**Why it matters:** Developers care that their job starts, not where it runs. This guarantees availability even during Kynetic's early-network growth phase, removing "no supply" as a reason to churn.
**How it's built:** Phase 12's Hybrid Compute Broker wraps `boto3`, `azure-sdk-for-python`, `google-cloud-python`, and RunPod/Vast REST APIs behind one internal provisioning interface, invoked automatically by the Scheduler on a local-supply miss.

### 8. India-First Compute Cloud
**What it is:** UPI billing, GST invoices, INR pricing, and India-based support — targeting Indian startups, students, IITs, universities, researchers, and freelancers specifically.
**Why it matters:** RunPod is US-centric and Vast isn't India-optimized. A dedicated, frictionless India experience is a wide-open regional wedge with a large, underserved developer population.
**How it's built:** Phase 13 integrates Razorpay for UPI payments and GST-compliant invoice generation, alongside dual-currency display throughout the wallet and billing services.

### 9. Reputation Layer
**What it is:** Per-host scoring across uptime, latency, network quality, job success rate, benchmark performance, and response time — an "Uber ratings" system for compute.
**Why it matters:** Trust is the single biggest blocker to renting a stranger's hardware. A visible, earned reputation score lets users trust providers instantly, without manual vetting.
**How it's built:** Phase 11 aggregates telemetry and job outcomes (already captured for monitoring/billing) into a transparent, explainable weighted score, updated after every completed job and displayed on every listing.

### 10. AI Copilot
**What it is:** A conversational assistant that turns "I need GPU for LoRA training" into a concrete answer: recommended hardware, estimated time, and estimated cost — before the user commits.
**Why it matters:** No competitor makes resource selection this conversational. It collapses the entire discovery-to-decision journey into a single chat exchange, which is a strong differentiator for non-expert users.
**How it's built:** Phase 9 layers LangChain (with an OpenAI/Anthropic or self-hosted LLM backend) on top of the AI Resource Router's underlying data — the LLM handles natural language, the router supplies the grounded, accurate numbers.

---

### Final Note

The MVP is no longer just "a GPU rental site" — it is the first version of a **compute-first, AI-native, India-ready marketplace with a hybrid-cloud safety net and a trust layer built in from day one.** Every new feature in this version was chosen because it's buildable with the same Python-first stack and fits directly into the existing 14-phase roadmap — nothing here requires a future re-architecture; it's all shippable as part of v1.
