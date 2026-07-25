# Kynetic AI — Things Left To Do for Live Production Launch
## Itemized Production Activation Playbook, MVP Classification & Security Hardening Guide

> **Status**: All 33 core architectural phases, v6 CLI runtime, v7 three-party marketplace payments & double-entry financial ledger, v8 GPU benchmark & verification engines, Next.js 16 web application, and 56 passing integration tests are **100% implemented**.
> **Purpose**: This document tracks all remaining tasks for live launch and clearly demarcates **what is strictly MANDATORY for a Day 1 Lean MVP** versus **what can be DEFERRED for post-launch scaling**, including advanced multi-layer security hardening.

---

## 🎯 Executive Guide: Lean MVP vs. Full Enterprise Production Strategy

To launch fast without over-engineering or spending unnecessary money, use this clear decision framework:

### 1. Terraform IaC AWS EKS 1.29 Cluster & Helm External Secrets Operator
- 💡 **Plain Language**: Automated scripts that set up enterprise-grade Kubernetes server clusters on Amazon Web Services (AWS) and securely load secrets.
- 🎯 **MVP Necessity**: **NO (DEFERRED FOR MVP) ❌**
- 📌 **Why**: For your initial MVP launch, running all microservices on a single cheap VPS (like a $20–$40/month Render, Railway, DigitalOcean Droplet, or single EC2 instance using `docker-compose up -d`) is 100x easier, faster, and cheaper. Multi-node Kubernetes clusters are only needed when serving tens of thousands of concurrent users.

### 2. Cloudflare Edge WAF & SSL/TLS 1.3 Domains (`api.kynetic.ai`, `app.kynetic.ai`, `tunnel.kynetic.ai`)
- 💡 **Plain Language**: Cloudflare acts as a digital shield against hacker attacks (WAF) and secures your website domains with green padlock HTTPS encryption (`https://`).
- 🎯 **MVP Necessity**: **PARTIALLY REQUIRED ⚠️**
  - **Required**: A standard domain (`kynetic.ai`) with free Let's Encrypt / Cloudflare SSL (`https://api.kynetic.ai`).
  - **Deferred**: Enterprise paid WAF custom firewall rules. A **free Cloudflare account** provides free SSL and basic DDoS protection out of the box in 5 minutes.

### 3. EV Code Signing for Windows `.exe` & Apple Notarization for macOS Host Agent Binaries
- 💡 **Plain Language**: Paying $300–$500/year to Microsoft and Apple for official digital certificates so Windows/macOS don't display "Publisher Unknown / Unsafe File" warning popups when someone downloads the Host Agent.
- 🎯 **MVP Necessity**: **NO (DEFERRED FOR MVP) ❌**
- 📌 **Why**: Users can simply click *"Run Anyway"* on Windows or right-click *"Open"* on macOS. For initial testing with friendly hosts, an unsigned executable, zip file, or simple `pip install kynetic-agent` script works perfectly. Buy EV certificates when launching public paid ad campaigns.

### 4. SendGrid SPF/DKIM/DMARC Email DNS Records & Alertmanager PagerDuty/Slack Routing
- 💡 **Plain Language**:
  - *SPF/DKIM/DMARC*: Verification DNS settings so your welcome/invoice emails land in the user's **Inbox** instead of Spam.
  - *Alertmanager / PagerDuty*: Phone calls/Slack alerts waking up engineers if a server crashes at 3 AM.
- 🎯 **MVP Necessity**: **50% REQUIRED ⚠️**
  - **Email DNS (SPF/DKIM)**: **REQUIRED (MANDATORY)** — 5 minutes of free DNS setup so user transactional emails don't go to Spam.
  - **PagerDuty On-Call Paging**: **DEFERRED** — Overkill for MVP; basic log checking is sufficient.

### 5. Supply-Side Seed Pool (15–25 Initial Verified GPU Nodes across Mumbai & US East)
- 💡 **Plain Language**: Onboarding an initial fleet of GPUs (RTX 4090 / A100) so the marketplace catalog isn't an empty shell when the first developer visits.
- 🎯 **MVP Necessity**: **REQUIRED, BUT MUCH SMALLER ⚠️ (2–5 GPUs)**
  - **Why**: You need live compute available on Day 1, but you don't need 25 expensive nodes right away! Having **2 to 5 GPUs** (e.g. 2x RTX 4090s or 1x A100) is more than enough for initial MVP testing.

### 6. 72-Hour Locust Load Soak Testing & 50-Developer Closed Beta Sign-Off Gate
- 💡 **Plain Language**: Stress-testing your servers by bombarding them with 1,000 fake simulated users for 3 days non-stop, plus running a private test with 50 real beta users.
- 🎯 **MVP Necessity**: **NO for 1,000-User Stress Test ❌ | YES for 5 Beta Testers ⚠️**
  - **72-Hour 1,000-User Soak Test**: **DEFERRED** — Waste of time for MVP scale.
  - **Beta Testing**: **REQUIRED** — Test the end-to-end flow with **5 to 10 friends/beta users** to verify payments, instance rentals, and receipts work smoothly.

---

## 📊 Summary Checklist & MVP Classification Matrix

| Category | Task / Component | Required Action | MVP Scope | Status |
|---|---|---|---|---|
| **1. Payments** | **Razorpay Live Activation** | Inject live `rzp_live_...` API credentials & register webhook `https://api.kynetic.ai/v1/billing/webhooks/razorpay` | **MANDATORY DAY 1** | ⏳ Pending Credentials |
| **1. Payments** | **Stripe Live & Connect** | Inject live `sk_live_...` keys, enable Stripe Connect payouts for 85% host split, register webhook | **MANDATORY DAY 1** | ⏳ Pending Credentials |
| **2. Invoices** | **WeasyPrint PDF & S3 Bucket** | Generate 18% GST invoices, store in `s3://kynetic-production-invoices` with 15-min presigned URLs | **MANDATORY DAY 1** | ⏳ Pending AWS S3 Setup |
| **3. Infra** | **Single Server / Docker Compose** | Deploy all 11 microservices on a single VPS ($20–$40/mo) using `docker-compose up -d` | **MANDATORY DAY 1** | ⏳ Ready to Run |
| **3. Infra** | **Terraform IaC & EKS Cluster** | Provision AWS EKS 1.29 cluster, RDS Multi-AZ, ElastiCache Redis via Terraform | **DEFERRED (Post-MVP)** | ⏳ Optional |
| **4. Edge & CDN** | **Free Cloudflare SSL & DNS** | Point A/AAAA records for `api.kynetic.ai` and `app.kynetic.ai` with free Cloudflare SSL certificate | **MANDATORY DAY 1** | ⏳ Pending DNS Config |
| **4. Edge & CDN** | **Cloudflare Enterprise WAF** | Custom OWASP WAF rulesets and 100 req/min rate limiters | **DEFERRED (Post-MVP)** | ⏳ Optional |
| **5. Email** | **SendGrid SPF/DKIM DNS** | Set `EMAIL_MOCK_MODE=false`, add SPF/DKIM DNS records for `kynetic.ai` | **MANDATORY DAY 1** | ⏳ Pending DNS Records |
| **5. Email** | **PagerDuty / Slack Alerting** | Automated 3 AM phone call routing and Slack webhook integration | **DEFERRED (Post-MVP)** | ⏳ Optional |
| **6. Host Agent** | **Unsigned Binary / Script** | Package `kynetic-host-agent` script/executable for host onboarding | **MANDATORY DAY 1** | ⏳ Ready |
| **6. Host Agent** | **EV Code Signing Certificate** | $300/yr DigiCert/Sectigo EV Certificate for Windows `.exe` and Apple Notarization | **DEFERRED (Post-MVP)** | ⏳ Optional |
| **7. Seed Pool** | **Initial 2–5 GPU Seed Pool** | Onboard 2x RTX 4090s and 1x A100 to populate catalog on Day 1 | **MANDATORY DAY 1** | ⏳ Pending Onboarding |
| **7. Seed Pool** | **25+ Global GPU Fleet** | Onboard 25+ nodes across 4 global regions | **DEFERRED (Post-MVP)** | ⏳ Optional |
| **8. Security** | **JWT Token Rotation & SHA Hash Chain** | Single-use JWT refresh token rotation + SHA-256 audit log hash-chaining | **MANDATORY DAY 1** | ⏳ Implemented |
| **8. Security** | **3-Pass DoD Shredding** | Ephemeral LUKS2 volume encryption + 3-pass DoD 5220.22-M storage shredding (`shred -n 3 -z`) | **MANDATORY DAY 1** | ⏳ Implemented |
| **8. Security** | **CI/CD Vulnerability Scanning** | Trivy container image scanning + Semgrep SAST scanning in GitHub Actions | **MANDATORY DAY 1** | ⏳ Configured |
| **8. Security** | **gVisor / Kata Containers** | User-space syscall proxy interposer preventing host root breakouts | **DEFERRED (Post-MVP)** | ⏳ Advanced Hardening |
| **8. Security** | **eBPF/XDP LAN & Mining Blocker** | Kernel XDP filter dropping LAN IPs (`192.168.x.x`) and Stratum mining pools | **DEFERRED (Post-MVP)** | ⏳ Advanced Hardening |
| **8. Security** | **WebAuthn Passkeys / Hardware 2FA** | FIDO2 YubiKey / Touch ID biometric authentication | **DEFERRED (Post-MVP)** | ⏳ Advanced Hardening |
| **8. Security** | **Confidential Computing (SEV/TDX)** | Remote hardware attestation (AMD KDS / Intel PCS / NVIDIA NRAS) | **DEFERRED (Post-MVP)** | ⏳ Advanced Hardening |
| **9. QA Gate** | **5–10 Closed Beta Sign-Off** | Validate end-to-end rental & payment journey with 5–10 friendly beta users | **MANDATORY DAY 1** | ⏳ Pending Beta |
| **9. QA Gate** | **72-Hour 1,000-User Soak Test** | 72-hour continuous Locust load test under 1,000 simulated users | **DEFERRED (Post-MVP)** | ⏳ Optional |

---

## Category 1: Payment Gateway Production Switch & Financial Flow `[MANDATORY DAY 1]`

### 1.1 Razorpay Production Activation (India UPI / Netbanking / Cards)
- **Target File**: `backend/services/wallet_billing_service/config.py`
- **Steps**:
  1. Update environment variable `RAZORPAY_MOCK_MODE=false`.
  2. Inject live Razorpay API credentials into AWS Secrets Manager at path `kynetic/production/wallet_billing_service`:
     - `RAZORPAY_KEY_ID`: `rzp_live_XXXXXXXXXXXXXXXXXX`
     - `RAZORPAY_KEY_SECRET`: `XXXXXXXXXXXXXXXXXXXXXXXX`
     - `RAZORPAY_WEBHOOK_SECRET`: `whsec_live_XXXXXXXXXXXXXXXX`
  3. Register production webhook endpoint in Razorpay Dashboard:
     - **URL**: `https://api.kynetic.ai/v1/billing/webhooks/razorpay`
     - **Subscribed Events**: `payment.captured`, `payment.failed`, `order.paid`, `dispute.created`, `refund.processed`.

### 1.2 Stripe Production Activation (Global Cards & Stripe Connect Payouts)
- **Target File**: `backend/services/wallet_billing_service/config.py`
- **Steps**:
  1. Inject production Stripe credentials into AWS Secrets Manager:
     - `STRIPE_SECRET_KEY`: `sk_live_XXXXXXXXXXXXXXXXXXXXXXXX`
     - `STRIPE_PUBLISHABLE_KEY`: `pk_live_XXXXXXXXXXXXXXXXXXXXXXXX`
     - `STRIPE_WEBHOOK_SECRET`: `whsec_XXXXXXXXXXXXXXXXXXXXXXXX`
  2. Enable **Stripe Connect** in Stripe Dashboard for host payouts (Express Connect accounts for 85% host revenue split).
  3. Register production webhook endpoint:
     - **URL**: `https://api.kynetic.ai/v1/billing/webhooks/stripe`
     - **Events**: `payment_intent.succeeded`, `payment_intent.payment_failed`, `charge.dispute.created`, `account.updated`.

---

## Category 2: Automated PDF Invoice Engine & S3 Storage Bucket `[MANDATORY DAY 1]`

### 2.1 WeasyPrint / ReportLab PDF Rendering Engine
- **Target File**: `backend/services/wallet_billing_service/invoice.py`
- **Steps**:
  1. Replace S3 URL stub string with an automated HTML-to-PDF rendering pipeline using `WeasyPrint` or `ReportLab`.
  2. **Invoice Template Layout Requirements**:
     - **Header**: Kynetic AI Corporate Logo, Corporate Address, GSTIN (`27AAAAA0000A1Z5`), PAN (`ABCDE1234F`).
     - **Invoice Metadata**: Sequential Fiscal Year Number (`KYN/2024-25/000001` via `SELECT FOR UPDATE` locking), Invoice Date, Due Date.
     - **Line Items**: Per-second compute rental breakdown (GPU model, total seconds, hourly rate, subtotal).
     - **Tax Calculation**: 18% GST Breakdown (CGST 9% + SGST 9% for intra-state; IGST 18% for inter-state India; 0% Export for foreign developers).

### 2.2 S3 Bucket Provisioning & Presigned Download URLs
- **Steps**:
  1. Provision private AWS S3 bucket: `s3://kynetic-production-invoices` with AES-256 server-side encryption (`SSE-S3`) and public access blocked.
  2. Configure IAM Policy granting `wallet_billing_service` permission to `s3:PutObject` and `s3:GetObject`.
  3. Implement presigned URL generation (15-minute expiration) when developers click "Download Invoice PDF" in the web portal.

---

## Category 3: Single VPS Deployment vs. Enterprise Kubernetes

### 3.1 Lean MVP VPS Deployment `[MANDATORY DAY 1]`
- **Target**: Single Ubuntu 22.04 VPS (DigitalOcean Droplet / AWS EC2 / Railway / Render)
- **Steps**:
  1. Clone repository to server:
     ```bash
     git clone https://github.com/DivyeBhatnagar/KyneticSoftware.git
     cd KyneticSoftware/kynetic-ai
     ```
  2. Start all microservices, PostgreSQL, and Redis:
     ```bash
     docker-compose -f infra/docker-compose.yml up -d --build
     ```

### 3.2 Enterprise Terraform IaC & EKS Cluster `[DEFERRED FOR POST-MVP]`
- **Location**: `infra/terraform/` & `infra/k8s/`
- **Steps**:
  1. Execute Terraform script to provision AWS EKS 1.29 cluster, RDS PostgreSQL 16 Multi-AZ, ElastiCache Redis 7.2.
  2. Deploy Helm External Secrets Operator and apply Kubernetes manifests in `infra/k8s/`.

---

## Category 4: Email Domain Authentication & Telemetry Pipeline

### 4.1 SendGrid Production Email Activation `[MANDATORY DAY 1]`
- **Target File**: `backend/services/notifications_service/config.py`
- **Steps**:
  1. Update environment variable `EMAIL_MOCK_MODE=false`.
  2. Supply live `SENDGRID_API_KEY` (`SG.XXXXXXXXXXXXXXXXXXXXXXXX`) in Secrets Manager.
  3. Configure DNS records for `kynetic.ai` in domain registrar:
     - **SPF**: `v=spf1 include:sendgrid.net ~all`
     - **DKIM**: Add 2 CNAME records provided by SendGrid (`s1._domainkey.kynetic.ai`, `s2._domainkey.kynetic.ai`).
     - **DMARC**: `v=DMARC1; p=quarantine; rua=mailto:dmarc-reports@kynetic.ai`

### 4.2 Production Observability & Alerting Routing `[DEFERRED FOR POST-MVP]`
- **Location**: `infra/observability/`
- **Steps**: Deploy Promtail DaemonSet to stream logs to Grafana Loki; configure Alertmanager with live PagerDuty and Slack webhooks.

---

## Category 5: Host Agent Packaging & Seed Pool Onboarding

### 5.1 Host Agent Packaging `[MANDATORY DAY 1: Script/Unsigned | DEFERRED: EV Certificate]`
- **Lean MVP Steps**:
  1. Distribute Host Agent script via `curl -fsSL https://get.kynetic.ai/host-agent.sh | bash` or `pip install kynetic-agent`.
  2. For Windows users, instruct them to click *"Run Anyway"* on smart screen prompt during initial beta testing.

### 5.2 Supply-Side Seed Pool Onboarding `[MANDATORY DAY 1: 2–5 GPUs | DEFERRED: 25+ Fleet]`
- **Lean MVP Steps**:
  1. Onboard 2x NVIDIA RTX 4090 (24GB VRAM) and 1x NVIDIA A100 (80GB VRAM) host machines to populate catalog on Day 1.
  2. Run automated hardware verification & PyTorch benchmarks to ensure active inventory.

---

## Category 6: Pre-Launch Verification & Go-Live Gate `[MANDATORY DAY 1: 5 Beta Users]`

### 6.1 Closed Beta Sign-Off Gate `[MANDATORY DAY 1]`
- **Steps**: Invite 5–10 friendly developers and 2 host operators. Validate end-to-end user journeys (Host Signup → Benchmark → Listing → Developer Payment → Instance Rental → PTY Session → Termination → Invoice Download) with zero errors.

### 6.2 72-Hour Load & Soak Test `[DEFERRED FOR POST-MVP]`
- **Steps**: Run 72-hour continuous Locust load test (`backend/tests/load/locustfile.py`) under 1,000 simulated users.

---

## Category 7: Advanced Multi-Layer Security Architecture & Anti-Hacker Hardening

### 7.1 MicroVM & Container Sandboxing (Guest-to-Host Protection)
- **gVisor / Kata Containers Interposer `[DEFERRED FOR POST-MVP]`**: Intercept and sanitize Linux system calls at user-space (`ptrace`/`kvm`) to prevent kernel zero-day breakouts (*Dirty COW*, *Use-After-Free*) from guest containers into host root shells.
- **Seccomp-BPF & AppArmor Profile Enforcement `[MANDATORY DAY 1: Basic Seccomp | DEFERRED: Custom AppArmor]`**: Restrict MicroVM container privileges to ~50 essential Linux system calls, blocking dangerous kernel calls (`ptrace`, `bpf`, `kexec_load`, `unshare`, `mount`).
- **Rootless MicroVM Execution (`rootlesskit` / User Namespaces) `[DEFERRED FOR POST-MVP]`**: Run Firecracker/Docker containers without host `root` privileges so breakouts land in an unprivileged `nobody` user namespace.

### 7.2 Network Isolation & Anti-Abuse Firewall
- **eBPF/XDP MicroVM Network Isolation `[DEFERRED FOR POST-MVP]`**: Attach eBPF programs to MicroVM virtual interfaces to block guest instances from scanning host LAN IPs (`192.168.x.x`, `10.x.x.x`, `172.16.x.x`) or accessing cloud metadata (`169.254.169.254`).
- **Real-Time Cryptomining & Egress Blocker `[DEFERRED FOR POST-MVP]`**: Inspect outbound packet headers for Stratum mining pool protocols (`stratum+tcp://`, `xmrig`) and TCP SYN port scanning, auto-terminating abusive instances in **< 1 second**.
- **mTLS with Hardware TPM 2.0 Pinning `[DEFERRED FOR POST-MVP]`**: Pin private mTLS certificates inside host TPM 2.0 chips so host authentication keys cannot be stolen or cloned.

### 7.3 Application & API Security
- **WebAuthn / Passkeys (Hardware 2FA) `[DEFERRED FOR POST-MVP]`**: Add native FIDO2 WebAuthn biometric 2FA (YubiKey / Touch ID / Face ID) for developer and host admin logins.
- **Short-Lived Ephemeral JWTs & Single-Use Refresh Token Rotation `[MANDATORY DAY 1]`**: 15-minute access token lifespan with single-use refresh token rotation; replaying a refresh token instantly revokes all user sessions.
- **AWS KMS / Vault Envelope Encryption `[DEFERRED FOR POST-MVP]`**: Encrypt sensitive database columns (KYC details, API tokens, bank account details) using AES-256-GCM envelope encryption keys stored in Hardware Security Modules (HSM).

### 7.4 Confidential Computing & Cryptographic Data Privacy
- **Hardware Remote Attestation (AMD SEV-SNP / Intel TDX / NVIDIA Hopper TEE) `[DEFERRED FOR POST-MVP]`**: Query hardware security processors (AMD KDS / Intel PCS / NVIDIA NRAS) before deploying workloads to guarantee guest RAM is encrypted at the CPU/GPU hardware level.
- **LUKS2 Storage Encryption & 3-Pass DoD Data Shredding `[MANDATORY DAY 1]`**: Format MicroVM storage with ephemeral LUKS2 keys. Upon instance termination, destroy RAM keys and execute 3-pass DoD 5220.22-M data shredding (`shred -n 3 -z`) to prevent host recovery of developer datasets or model weights.
- **Ed25519 Signed Execution Proof Certificates `[DEFERRED FOR POST-MVP]`**: Issue cryptographically signed execution certificates (`Ed25519`) post-rental confirming zero unauthorized host memory access during compute runs.

### 7.5 Automated SecOps & Threat Intelligence
- **Automated CI/CD Vulnerability Scanning (Trivy + Semgrep) `[MANDATORY DAY 1]`**: Scan container images, Python packages, and npm dependencies for CVEs in GitHub Actions before code merges.
- **Immutable Audit Logs with SHA-256 Hash Chaining `[MANDATORY DAY 1]`**: Link security audit log entries (`SecurityAuditLog`) with SHA-256 cryptographic hashes (`hash_i = Hash(hash_{i-1} + log_data)`), preventing DB admins from tampering with past audit logs.
- **Honeypot Decoy Listings & Multi-Account Fraud Ring Detector `[DEFERRED FOR POST-MVP]`**: Deploy decoy GPU listings to detect automated bot scanners, fake host registration rings, and stolen credit card testing.
