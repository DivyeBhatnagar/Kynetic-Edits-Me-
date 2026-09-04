# Kynetic AI — Things Left To Do for Live Production Launch
## Itemized Production Activation Playbook, MVP Classification & Security Hardening Guide

> **Status**: All 33 core architectural phases, host agent footprint optimizations, 238 passing unit/integration tests, AND the complete **v7.0.0 Hybrid Go/Python migration** (Go CLI binary, Go Host Agent daemon, Go Gateway Tunnel Broker, Protobuf gRPC contract) are **100% implemented and verified**.
> **Purpose**: This document tracks all remaining tasks for live launch and clearly demarcates **what is strictly MANDATORY for a Day 1 Lean MVP** versus **what can be DEFERRED for post-launch scaling**.


---

## 🎯 Executive Guide: Lean MVP vs. Full Enterprise Production Strategy

To launch fast without over-engineering or spending unnecessary money, use this clear decision framework:

### 1. Payment Gateway Live Credentials & Stripe Connect Setup
- 💡 **Plain Language**: Injecting real production API keys for Razorpay (India UPI/cards) and Stripe (Global cards & Host Connect payouts).
- 🎯 **MVP Necessity**: **MANDATORY DAY 1 ⚠️**
- 📌 **Action**: Switch `RAZORPAY_MOCK_MODE=false` and `STRIPE_MOCK_MODE=false`, inject live API secrets into environment/AWS Secrets Manager, and register live webhook URLs.

### 2. WeasyPrint PDF Invoice Engine & S3 Storage Bucket
- 💡 **Plain Language**: Generating GST-compliant PDF invoices for developers and storing them securely in Amazon S3 for download.
- 🎯 **MVP Necessity**: **MANDATORY DAY 1 ⚠️**
- 📌 **Action**: Connect `WeasyPrint` HTML-to-PDF rendering in `invoice.py` and configure private AWS S3 bucket (`s3://kynetic-production-invoices`) with 15-minute presigned download URLs.

### 3. Production VPS Deployment & Cloudflare DNS/SSL
- 💡 **Plain Language**: Deploying the 11 microservices to a production server with free HTTPS encryption (`https://api.kynetic.ai`).
- 🎯 **MVP Necessity**: **MANDATORY DAY 1 ⚠️**
- 📌 **Action**: Point A/AAAA DNS records to your single $20–$40/month production VPS (DigitalOcean / AWS / Render / Railway) running `docker-compose up -d --build`, and enable free Cloudflare SSL. Multi-node Kubernetes (EKS) is deferred.

### 4. SendGrid SPF/DKIM/DMARC Transactional Email DNS
- 💡 **Plain Language**: DNS settings verifying that welcome emails, password resets, and invoices land in the user's Inbox instead of Spam.
- 🎯 **MVP Necessity**: **MANDATORY DAY 1 ⚠️**
- 📌 **Action**: Set `EMAIL_MOCK_MODE=false`, inject SendGrid API key, and add 3 CNAME/TXT records for `kynetic.ai` in domain registrar.

### 5. Supply-Side Seed Pool (2–5 Initial Verified GPU Nodes)
- 💡 **Plain Language**: Onboarding an initial fleet of GPUs so the marketplace catalog has active compute available when developers visit.
- 🎯 **MVP Necessity**: **MANDATORY DAY 1 (2–5 GPUs) ⚠️**
- 📌 **Action**: Onboard 2x RTX 4090s or 1x A100 host machines using `install_kynetic.sh` to populate marketplace inventory.

### 6. Closed Beta Sign-Off Gate (5–10 Testers)
- 💡 **Plain Language**: Testing the complete rental flow with friendly beta testers before public marketing.
- 🎯 **MVP Necessity**: **MANDATORY DAY 1 ⚠️**
- 📌 **Action**: Validate end-to-end journey: Host Registration $\rightarrow$ Benchmark $\rightarrow$ Marketplace Listing $\rightarrow$ Developer Rental $\rightarrow$ SSH/PTY Session $\rightarrow$ Termination $\rightarrow$ Invoice Download.

---

## 📊 Summary Checklist & MVP Classification Matrix

| Category | Task / Component | Required Action | MVP Scope | Status |
|---|---|---|---|---|
| **1. Payments** | **Razorpay Live Activation** | Inject live `rzp_live_...` credentials & register webhook `https://api.kynetic.ai/v1/billing/webhooks/razorpay` | **MANDATORY DAY 1** | ⏳ Pending Credentials |
| **1. Payments** | **Stripe Live & Connect** | Inject live `sk_live_...` keys, enable Stripe Connect payouts for 85% host split, register webhook | **MANDATORY DAY 1** | ⏳ Pending Credentials |
| **2. Invoices** | **WeasyPrint PDF & S3 Bucket** | Generate 18% GST invoices, store in `s3://kynetic-production-invoices` with 15-min presigned URLs | **MANDATORY DAY 1** | ⏳ Pending AWS S3 Setup |
| **3. Infra** | **Single Server / Docker Compose** | Deploy all 11 microservices on a single VPS ($20–$40/mo) using `docker-compose up -d` | **MANDATORY DAY 1** | ✅ Ready to Deploy |
| **3. Infra** | **Terraform IaC & EKS Cluster** | Provision AWS EKS 1.29 cluster, RDS Multi-AZ, ElastiCache Redis via Terraform | **DEFERRED (Post-MVP)** | ⏳ Optional |
| **4. Edge & CDN** | **Free Cloudflare SSL & DNS** | Point A/AAAA records for `api.kynetic.ai` and `app.kynetic.ai` with free Cloudflare SSL certificate | **MANDATORY DAY 1** | ⏳ Pending DNS Config |
| **4. Edge & CDN** | **Cloudflare Enterprise WAF** | Custom OWASP WAF rulesets and 100 req/min rate limiters | **DEFERRED (Post-MVP)** | ⏳ Optional |
| **5. Email** | **SendGrid SPF/DKIM DNS** | Set `EMAIL_MOCK_MODE=false`, add SPF/DKIM DNS records for `kynetic.ai` | **MANDATORY DAY 1** | ⏳ Pending DNS Records |
| **5. Email** | **PagerDuty / Slack Alerting** | Automated 3 AM phone call routing and Slack webhook integration | **DEFERRED (Post-MVP)** | ⏳ Optional |
| **6. Host Agent** | **Footprint & Runtime Optimization** | PyTorch/Redis removed, `ctypes` CUDA/NVML engine, containerd eStargz runtime, LRU cache & TRIM GC | **MANDATORY DAY 1** | ✅ Implemented |
| **6. Host Agent** | **Unsigned Binary / Script** | Package `kynetic-host-agent` script/executable via `install_kynetic.sh` | **MANDATORY DAY 1** | ✅ Ready |
| **6. Host Agent** | **EV Code Signing Certificate** | $300/yr DigiCert/Sectigo EV Certificate for Windows `.exe` and Apple Notarization | **DEFERRED (Post-MVP)** | ⏳ Optional |
| **7. Seed Pool** | **Initial 2–5 GPU Seed Pool** | Onboard 2x RTX 4090s and 1x A100 to populate catalog on Day 1 | **MANDATORY DAY 1** | ⏳ Pending Onboarding |
| **7. Seed Pool** | **25+ Global GPU Fleet** | Onboard 25+ nodes across 4 global regions | **DEFERRED (Post-MVP)** | ⏳ Optional |
| **8. Security** | **JWT Token Rotation & SHA Hash Chain** | Single-use JWT refresh token rotation + SHA-256 audit log hash-chaining | **MANDATORY DAY 1** | ✅ Implemented |
| **8. Security** | **RAM LUKS2 Encryption & TRIM Shredding** | 512-bit AES-XTS RAM LUKS2 volume encryption + NVMe `blkdiscard` hardware TRIM sanitization | **MANDATORY DAY 1** | ✅ Implemented |
| **8. Security** | **TPM 2.0 Host Attestation & Trust Score** | TPM 2.0 signed quote attestation client + Part 6.3 Hard Gate Rule | **MANDATORY DAY 1** | ✅ Implemented |
| **8. Security** | **Zero Trust PDP & Network Isolation** | 8-Dimension Policy Engine + per-instance `nftables` default deny & 169.254.169.254 block | **MANDATORY DAY 1** | ✅ Implemented |
| **8. Security** | **Container Security Profile & Cosign Gate** | `security_profile.py` (Seccomp strict profile, AppArmor `kynetic-hardened`, `cap_drop: [ALL]`) + Cosign gate | **MANDATORY DAY 1** | ✅ Implemented |
| **8. Security** | **Permissions & Security Architecture** | Complete permissions matrix, host capability bounds, and data protection boundaries documented in `PERMISSIONS_AND_SECURITY.md` | **MANDATORY DAY 1** | ✅ Implemented |
| **8. Security** | **Runtime Risk Engine & Incident Response** | 0–100 Risk Engine + graduated response bands (ALLOW..QUARANTINE) + automated containment | **MANDATORY DAY 1** | ✅ Implemented |
| **8. Security** | **Verified Compute & Secret Broker** | Verified Compute hard pre-filter stage + Kynetic Secret Broker & audit tip checkpointing | **MANDATORY DAY 1** | ✅ Implemented |
| **9. QA Gate** | **5–10 Closed Beta Sign-Off** | Validate end-to-end rental & payment journey with 5–10 friendly beta users | **MANDATORY DAY 1** | ⏳ Pending Beta |
| **9. QA Gate** | **72-Hour 1,000-User Soak Test** | 72-hour continuous Locust load test under 1,000 simulated users | **DEFERRED (Post-MVP)** | ⏳ Optional |

---

## 🚀 Live Production Activation Action Items (Exact Steps)

### Step 1: Payment Gateway Live Credentials (`[MANDATORY DAY 1]`)
1. **Razorpay Live Mode**:
   - Set `RAZORPAY_MOCK_MODE=false` in environment.
   - Supply `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`.
   - Register webhook: `https://api.kynetic.ai/v1/billing/webhooks/razorpay`.
2. **Stripe Live & Stripe Connect Payouts**:
   - Set `STRIPE_MOCK_MODE=false` in environment.
   - Supply `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`.
   - Enable Stripe Connect for 85% host payouts.
   - Register webhook: `https://api.kynetic.ai/v1/billing/webhooks/stripe`.

### Step 2: Automated PDF Invoice Engine & S3 Storage (`[MANDATORY DAY 1]`)
1. Connect `WeasyPrint` or `ReportLab` in `backend/services/wallet_billing_service/invoice.py` to render 18% GST invoices (CGST/SGST/IGST breakdown with corporate logo and sequential invoice numbers).
2. Create private S3 bucket `s3://kynetic-production-invoices` with `SSE-S3` encryption and 15-minute presigned download URLs.

### Step 3: Server Deployment & Cloudflare SSL (`[MANDATORY DAY 1]`)
1. Deploy `docker-compose -f infra/docker-compose.yml up -d --build` on a single production VPS ($20–$40/month).
2. Add CNAME/A records for `api.kynetic.ai` and `app.kynetic.ai` pointing to VPS IP, with free Cloudflare SSL enabled.

### Step 4: SendGrid Email DNS Records (`[MANDATORY DAY 1]`)
1. Set `EMAIL_MOCK_MODE=false` and inject `SENDGRID_API_KEY`.
2. Add SPF (`v=spf1 include:sendgrid.net ~all`), DKIM, and DMARC DNS records for `kynetic.ai`.

### Step 5: Seed Pool & Closed Beta Validation (`[MANDATORY DAY 1]`)
1. Onboard 2–5 initial GPU host nodes using `infra/host_install/install_kynetic.sh`.
2. Conduct end-to-end beta test with 5–10 users to verify instance provisioning, SSH connectivity, billing meter debits, and invoice downloads.
