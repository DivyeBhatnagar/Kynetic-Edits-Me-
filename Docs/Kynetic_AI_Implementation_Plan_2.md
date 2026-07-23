# Kynetic AI — Implementation Plan 2: Production Readiness & Launch

### Gap Analysis + Phases 11–18 to Take the Built System from "Functionally Complete" to "Production Launchable"

---

## Executive Summary: What's Built vs. What's Missing

Phases 1–10 gave Kynetic a **functionally complete core product**: auth, host verification, marketplace, wallet/billing, provisioning, security primitives, one-click templates, AI router/copilot, reputation/pricing, and India billing. That is a real, working system.

What it is **not yet** is a system that can survive real users, real money, real attackers, and real outages without supervision. Production launch requires four categories of work that don't show up in a feature-by-feature build plan:

1. **Depth on what already exists** — several Phase 1–10 modules were built to "happy path" completeness but not to production-grade robustness (e.g., malware scanning and Firecracker isolation need to move from "control engine exists" to "hardened and tested against real escape attempts").
2. **Infrastructure that makes the system reliable** — deployment, scaling, backups, disaster recovery, secrets management, multi-environment setup.
3. **Operational tooling** — an internal admin panel, support tooling, financial reconciliation, fraud review workflows — none of which exist yet, and all of which are needed the day real users start transacting.
4. **Verification** — testing, load testing, security auditing, and a hard launch checklist proving the above actually works before opening signups.

This plan is organized as **Phases 12–18**, continuing the same structure as the original build plan, followed by a **Production Launch Checklist**.

*Note: the Hybrid Compute Broker (multi-cloud burst to AWS/Azure/GCP/RunPod/Vast) has been intentionally removed from this plan. Kynetic AI is a compute rental marketplace in its own right — the goal is to grow native host supply, not redirect developers to competing platforms.*

---

### Phase 12: Infrastructure, Deployment & Environments
- **Objective**: Move every service from "runs in dev" to "reliably deployed, scaled, and recoverable in production."
- **Gap being closed**: Nothing in Phases 1–10 addresses how these 10+ microservices actually get deployed, scaled, or kept alive.
- **Key Modules & Files**:
  - `infra/terraform/`: Reproducible infrastructure-as-code for VPC, Kubernetes cluster, managed Postgres, Redis, S3-compatible storage, and DNS.
  - `infra/k8s/`: Kubernetes manifests/Helm charts per service, with resource requests/limits, liveness/readiness probes, and horizontal pod autoscaling.
  - `infra/environments/`: Distinct `staging`, `production`, and `dev` environments with isolated databases, secrets, and domains — **no shared production database with dev/staging, ever.**
  - `infra/secrets/`: HashiCorp Vault (or AWS Secrets Manager) integration replacing any `.env`-file secrets with rotated, access-audited secret injection.
  - `infra/cdn/`: Cloudflare (or equivalent) in front of the frontend and API gateway for DDoS absorption, TLS termination, and edge caching.
- **Operational Additions**:
  - Blue/green or canary deployment strategy for zero-downtime releases.
  - Database migration gating (Alembic migrations run and verified in staging before production promotion).
  - Autoscaling policies for Provisioning Service and AI Router/Copilot Service specifically — these have the least predictable load spikes.
- **Priority**: P0 — nothing else in this plan matters if the system can't reliably run.

---

### Phase 13: Observability, Alerting & Incident Response
- **Objective**: Turn the Phase 10 monitoring stub (`/monitoring/metrics`) into a real operational nervous system with alerting and an actual response process.
- **Gap being closed**: A Prometheus scrape endpoint exists, but there's no alerting, no dashboards beyond raw metrics, no log aggregation, and no on-call process.
- **Key Modules & Files**:
  - `infra/observability/grafana-dashboards/`: Pre-built dashboards for API latency, error rates, instance provisioning success rate, wallet transaction failures, and host heartbeat health.
  - `infra/observability/alertmanager-rules/`: Alert rules (e.g., provisioning failure rate > 2%, wallet debit/heartbeat mismatch, kill-switch triggered, Stripe/Razorpay webhook failures) routed to PagerDuty/Opsgenie or a Slack on-call channel.
  - `services/*/structlog` correlation IDs (already scaffolded in Phase 1) piped into a centralized log store — **Loki** or **ELK** — with per-request tracing across the gateway → service → Host Agent chain.
  - `docs/runbooks/`: Written incident runbooks (kill-switch activation, database failover, Stripe/Razorpay outage handling, mass host disconnection).
- **Priority**: P0 — you cannot safely run a two-sided marketplace with real money without knowing something's broken before your users tell you.

---

### Phase 14: Testing, QA & Chaos Validation
- **Objective**: Prove the system works under real conditions — not just on the happy path a developer tested manually.
- **Gap being closed**: No test suite, load test, or adversarial validation is mentioned anywhere in Phases 1–10.
- **Key Modules & Files**:
  - `tests/unit/`: `pytest` + `pytest-asyncio` unit coverage for every service, with a minimum coverage gate enforced in CI (target: 80%+ on billing, wallet, and provisioning logic specifically).
  - `tests/integration/`: End-to-end flows — signup → host verification → listing → rental → provisioning → billing → termination → payout — run against a staging environment on every merge.
  - `tests/load/`: **Locust** or **k6** load tests simulating concurrent instance provisioning, AI Router requests, and wallet transactions at 10x expected launch traffic.
  - `tests/security/`: Automated container escape attempts against the Firecracker/Docker isolation layer, SSH key rotation abuse tests, and rate-limit bypass attempts.
  - `tests/chaos/`: Chaos engineering scenarios — kill a host mid-job, drop the database connection, simulate a Stripe webhook delay — verifying the system degrades gracefully instead of corrupting billing state.
- **Priority**: P0 — billing correctness and isolation security are the two things that cannot fail silently at launch.

---

### Phase 15: Admin Panel & Internal Operations Tooling
- **Objective**: Give the Kynetic team the tools to actually run the business day-to-day — nothing in Phases 1–10 gives a human operator visibility or control.
- **Gap being closed**: `POST /admin/kill-switch` and `GET /admin/security-events` exist as raw API endpoints, but there is no internal UI, no fraud review workflow, and no support ticket resolution tooling beyond ticket creation.
- **Key Modules & Files**:
  - `apps/admin_dashboard/`: Internal-only Next.js app (behind SSO + IP allowlist) for the ops/support team.
  - Fraud & Trust Review Queue: surfaces flagged accounts (from `device_fingerprints`, `security_event_logs`, low reputation scores) for manual review and action.
  - Support Ticket Resolution UI: full lifecycle management on top of the existing `support_tickets` table (assign, respond, resolve, escalate).
  - Financial Reconciliation View: cross-checks `wallet_transactions` against Stripe/Razorpay ledgers to catch billing drift before it becomes a customer complaint.
  - Host/Listing Moderation UI: manually suspend, re-verify, or de-list a host outside the automated flows.
- **Database Tables**:
  - `admin_users` (`id`, `email`, `role[support|finance|security|superadmin]`, `sso_subject`)
  - `ticket_activity_log` (`ticket_id`, `admin_id`, `action`, `note`, `created_at`)
- **Priority**: P1 — launch is survivable without this for a very small closed beta, but not for public signups.

---

### Phase 16: Financial Operations & Compliance Hardening
- **Objective**: Make the money side of the platform audit-proof, not just functional.
- **Gap being closed**: Phase 3/10 built wallet debits, Stripe/Razorpay integration, and GST invoicing — but not a proper accounting ledger, tax withholding for host payouts, or chargeback/dispute handling.
- **Key Modules & Files**:
  - `services/wallet_billing_service/ledger.py`: Convert wallet transactions into a proper **double-entry ledger** (every debit has a matching credit) — essential for passing any future financial audit or SOC 2 review.
  - `services/wallet_billing_service/tax_withholding.py`: TDS handling for Indian host payouts (as required by Indian tax law) and 1099-equivalent reporting groundwork for future US host payouts.
  - `services/wallet_billing_service/chargeback_handler.py`: Stripe/Razorpay dispute webhook handling — freeze relevant wallet funds automatically pending resolution.
  - `services/wallet_billing_service/reconciliation_job.py`: Scheduled Celery job cross-checking internal ledger totals against payment-provider balances daily, alerting on drift.
- **Database Tables**:
  - `ledger_entries` (`id`, `transaction_id`, `account`, `debit`, `credit`, `currency`, `created_at`)
  - `chargebacks` (`id`, `transaction_id`, `provider`, `status`, `amount`, `opened_at`, `resolved_at`)
- **Priority**: P0 — you are moving real money on day one; this cannot be retrofitted later without pain.

---

### Phase 17: Legal, Policy & Compliance Documentation
- **Objective**: Cover the non-engineering requirements that are still launch-blocking.
- **Gap being closed**: Nothing in Phases 1–10 addresses the legal surface a live marketplace requires.
- **Deliverables**:
  - Terms of Service and Acceptable Use Policy (explicitly covering prohibited workloads — e.g., cryptomining, illegal content, malware — tied directly to the Phase 5 security enforcement).
  - Privacy Policy covering data collection scope (tied to the `audit_logs`, `device_fingerprints`, and hardware telemetry already being collected).
  - Host Agreement — clarifies liability, payout terms, and what happens if hardware is misused by a renter.
  - Refund & Dispute Policy — directly referenced by the Phase 16 chargeback handler.
  - India-specific: GST registration confirmation, data residency statement, and DPDP Act (India's data protection law) compliance review.
  - Basic SOC 2 readiness gap assessment (not certification — just an honest internal audit against SOC 2 Trust Service Criteria using the logging/access-control work already built in Phases 1, 5, and 13).
- **Priority**: P0 — cannot legally onboard paying users or host payouts without this.

---

### Phase 18: Frontend Completion & Cross-Cutting Polish
- **Objective**: Close remaining UX and reliability gaps in the frontend layer referenced only briefly in Phases 9–10.
- **Gap being closed**: Only the marketplace fallback page and dashboard tabs are mentioned; a production launch needs the full authenticated experience to be complete, tested, and accessible.
- **Key Modules & Files**:
  - `apps/frontend/app/onboarding/`: Guided, non-technical host onboarding flow (critical for the "consumer hardware" strategy — a gamer should not need a CLI).
  - `apps/frontend/app/instances/`: Full instance management UI (start/stop/terminate, connection details, live usage graphs) wired to the Phase 4 API surface.
  - `apps/frontend/app/copilot/`: WebSocket-connected AI Copilot chat UI wired to Phase 7.
  - Error-state handling, loading skeletons, and empty states across every page — not just the happy path.
  - Mobile-responsive layout pass and a baseline accessibility (WCAG 2.1 AA) audit.
  - Internationalization scaffold (English/Hindi at minimum) supporting the India-first strategy.
- **Priority**: P1 — required for a credible public launch, not strictly for a closed alpha.

---

## Production Launch Checklist

**Infrastructure & Reliability**
- [ ] All services deployed via Terraform + Kubernetes across isolated dev/staging/production environments
- [ ] Zero secrets in code or `.env` files in production — all via Vault/Secrets Manager
- [ ] Autoscaling verified under load test (Phase 14) for Provisioning and AI Router services
- [ ] Database backups automated with tested restore procedure (not just backup existence)
- [ ] Disaster recovery runbook tested via at least one real failover drill

**Security**
- [ ] Firecracker/Docker isolation tested against real container escape attempts
- [ ] Malware/image scanning verified against known-malicious test images
- [ ] Rate limiting verified against scripted abuse attempts on every public endpoint
- [ ] Kill switch tested end-to-end across all native instance types (GPU, CPU, RAM, workstation bundles)
- [ ] Penetration test (internal or third-party) completed with critical findings resolved

**Financial Integrity**
- [ ] Double-entry ledger (Phase 16) reconciles to zero drift against Stripe/Razorpay in staging simulation
- [ ] GST invoice sequence generation tested for concurrency correctness (row-locking under parallel load)
- [ ] Chargeback/dispute flow tested end-to-end with a real Stripe/Razorpay test dispute
- [ ] Host payout flow tested with real bank/UPI accounts in sandbox mode

**Operations**
- [ ] Admin panel (Phase 15) live and used by the team to resolve at least one simulated support ticket and one simulated fraud flag
- [ ] On-call rotation staffed with alerting (Phase 13) routed correctly
- [ ] Incident runbooks reviewed by the full team, not just written

**Legal & Compliance**
- [ ] ToS, Privacy Policy, Host Agreement, and Refund Policy published and linked in-product
- [ ] DPDP Act and GST compliance reviewed by counsel or a qualified consultant
- [ ] SOC 2 readiness gap assessment completed (even if certification is a later milestone)

**Product Readiness**
- [ ] Full user journey (host signup → verified listing → developer rental → workload run → termination → payout) tested end-to-end with real hardware, not mocks
- [ ] AI Resource Router and AI Copilot validated against at least 50 real, varied prompts for recommendation quality
- [ ] Frontend error states, empty states, and mobile layout reviewed on real devices

**Go-Live Gate**
- [ ] Closed beta run with a small real user group (hosts + developers) for a minimum soak period before public signups open
- [ ] All P0 items above signed off by engineering, security, and finance leads before removing the signup gate

---

## Sequencing Note

Phases 12, 13, 14, and 16 are **P0 and should run in parallel**, not sequentially — infrastructure, testing, observability, and financial hardening all depend on and reinforce each other rather than blocking one another. Phase 15 (admin tooling) and Phase 17 (legal) can proceed alongside them. Phase 18 (frontend polish) is the natural closer, since it depends on every backend surface above being stable. The **Production Launch Checklist** is the final gate — no item on it should be skipped to hit a launch date, since every one of them is protecting either user trust, user money, or user data.
