# Kynetic AI — Things Left To Do for Live Production Launch
## Itemized Production Activation Playbook & Checklist for 100% Bug-Free Commercial Launch

> **Status**: All 33 core architectural phases, v6 CLI runtime, v7 three-party marketplace payments & double-entry financial ledger, v8 GPU benchmark & verification engines, Next.js 16 web application, and 56 passing integration tests are **100% implemented**.
> **Purpose**: This document tracks all remaining external credential switches, cloud infrastructure provisioning, PDF invoice engine setups, EV code signing, and seed host onboarding tasks required to go live with paying customers.

---

## 📊 Summary Checklist of Remaining Production Activation Tasks

| Category | Component / Task | Required Action / Specification | Priority | Status |
|---|---|---|---|---|
| **1. Payments** | **Razorpay Live Activation (India)** | Set `RAZORPAY_MOCK_MODE=false`, inject live `rzp_live_...` API credentials & register webhook `https://api.kynetic.ai/billing/webhooks/razorpay` | **P0** | ⏳ Pending Credentials |
| **1. Payments** | **Stripe Live & Connect (Global)** | Inject live `sk_live_...` & `pk_live_...` keys, enable Stripe Connect payouts for 85% host split, register `https://api.kynetic.ai/billing/webhooks/stripe` | **P0** | ⏳ Pending Credentials |
| **2. Invoices** | **WeasyPrint PDF Engine & S3 Bucket** | Replace S3 URL stubs with `WeasyPrint` HTML-to-PDF rendering (GSTIN `27AAAAA0000A1Z5`, 18% GST breakdown), provision `s3://kynetic-production-invoices` with 15-min presigned URLs | **P0** | ⏳ Pending AWS S3 Setup |
| **3. Infra** | **Terraform IaC & EKS Bootstrap** | Provision S3/DynamoDB state lock, execute `terraform apply` in `infra/terraform/` to launch AWS EKS 1.29 cluster, RDS PostgreSQL 16 Multi-AZ, ElastiCache Redis 7.2 | **P0** | ⏳ Pending Deploy |
| **3. Infra** | **Kubernetes Production Rollout** | Install External Secrets Operator via Helm, deploy `infra/k8s/` manifests for all microservices with topology spread & HPA autoscaling | **P0** | ⏳ Pending Deploy |
| **4. Edge & CDN** | **Cloudflare WAF, DNS & SSL/TLS** | Point A/AAAA records for `api.kynetic.ai`, `app.kynetic.ai`, `tunnel.kynetic.ai` to NGINX Ingress Load Balancer, enable OWASP WAF rules & TLS 1.3 | **P0** | ⏳ Pending Domain Config |
| **5. Email** | **SendGrid Domain Authentication** | Set `EMAIL_MOCK_MODE=false`, supply live `SG.xxx` API key, configure SPF (`v=spf1 include:sendgrid.net ~all`), DKIM, and DMARC DNS records for `kynetic.ai` | **P0** | ⏳ Pending DNS Records |
| **5. Email** | **Production Alertmanager Routing** | Deploy Promtail DaemonSet for container logs, configure Alertmanager with live PagerDuty integration key and Slack webhook `#kynetic-ops-critical` | **P1** | ⏳ Pending Webhook Keys |
| **6. Host Agent** | **EV Code Signing & Binary Packaging** | Sign Windows `kynetic-host-agent.exe` with DigiCert/Sectigo EV certificate, notarize macOS `.app` via Apple NotaryTool, GPG sign Linux installer script | **P1** | ⏳ Pending Certificate |
| **7. Seed Pool** | **Supply-Side Node Onboarding** | Seed marketplace catalog with 15–25 verified hardware host nodes across Mumbai (`ap-south-1`) and US East (`us-east-1`) (RTX 4090 / A100 / H100) | **P0** | ⏳ Pending Onboarding |
| **8. Security** | **Vendor Attestation Endpoints** | Connect hardware attestation verification to live AMD KDS (`kdsintf.amd.com`), Intel PCS, and NVIDIA NRAS (`nras.attestation.nvidia.com`) endpoints | **P1** | ⏳ Pending Endpoint Link |
| **8. Security** | **eBPF XDP Kernel Attachment** | Attach compiled `xdp_filter.o` eBPF C program to host primary network interface during `kynetic-host-agent` startup to enforce hardware-level drop of LAN IPs | **P1** | ⏳ Pending Script Hook |
| **9. QA & Gate** | **72-Hour Load Soak & Closed Beta** | Run 72-hour Locust soak test (`tests/load/locustfile.py`) under 1,000 concurrent sessions; execute 50-developer closed beta test with $0 error rate | **P0** | ⏳ Pending Final Gate |

---

## Category 1: Payment Gateway Production Switch & Financial Flow

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

## Category 2: Automated PDF Invoice Engine & S3 Storage Bucket

### 2.1 WeasyPrint / ReportLab PDF Rendering Engine
- **Target File**: `backend/services/wallet_billing_service/invoice.py`
- **Steps**:
  1. Replace S3 URL stub string with an automated HTML-to-PDF rendering pipeline using `WeasyPrint` or `ReportLab`.
  2. **Invoice Template Layout Requirements**:
     - **Header**: Kynetic AI Corporate Logo, Corporate Address, GSTIN (`27AAAAA0000A1Z5`), PAN (`ABCDE1234F`).
     - **Invoice Metadata**: Sequential Fiscal Year Number (`KYN/2024-25/000001` via `SELECT FOR UPDATE` locking), Invoice Date, Due Date.
     - **Line Items**: Per-second compute rental breakdown (GPU model, total seconds, hourly rate, subtotal).
     - **Tax Calculation**: 18% GST Breakdown (CGST 9% + SGST 9% for intra-state; IGST 18% for inter-state India; 0% Export for foreign developers).
     - **Digital Signature**: Embedded PKCS#7 digital signature for tax authenticity.

### 2.2 S3 Bucket Provisioning & Presigned Download URLs
- **Steps**:
  1. Provision private AWS S3 bucket: `s3://kynetic-production-invoices` with AES-256 server-side encryption (`SSE-S3`) and public access blocked.
  2. Configure IAM Policy granting `wallet_billing_service` permission to `s3:PutObject` and `s3:GetObject`.
  3. Implement presigned URL generation (15-minute expiration) when developers click "Download Invoice PDF" in the web portal.

---

## Category 3: Production Infrastructure & IaC Bootstrap

### 3.1 Remote Terraform State Bootstrap
- **Location**: `infra/terraform/`
- **Steps**:
  1. Execute one-time S3 bucket and DynamoDB lock table setup for Terraform state locking:
     ```bash
     aws s3api create-bucket --bucket kynetic-terraform-state-prod --region ap-south-1
     aws dynamodb create-table --table-name kynetic-tf-locks --attribute-definitions AttributeName=LockID,AttributeType=S --key-schema AttributeName=LockID,KeyType=HASH --billing-mode PAY_PER_REQUEST
     ```
  2. Initialize and deploy IaC:
     ```bash
     cd infra/terraform
     terraform init -backend-config="bucket=kynetic-terraform-state-prod"
     terraform apply -var-file=environments/production.tfvars -auto-approve
     ```

### 3.2 Kubernetes Production Deployment & Helm Operators
- **Location**: `infra/k8s/`
- **Steps**:
  1. Connect `kubectl` to the newly created EKS cluster:
     ```bash
     aws eks update-kubeconfig --region ap-south-1 --name kynetic-prod-eks
     ```
  2. Install **External Secrets Operator** via Helm to automatically sync AWS Secrets Manager into Kubernetes secrets:
     ```bash
     helm repo add external-secrets https://charts.external-secrets.io
     helm install external-secrets external-secrets/external-secrets -n external-secrets --create-namespace
     ```
  3. Apply Kubernetes production manifests:
     ```bash
     kubectl apply -f infra/k8s/namespace.yaml
     kubectl apply -f infra/secrets/secret-mappings.yaml
     kubectl apply -f infra/k8s/services/
     kubectl apply -f infra/k8s/workers/
     ```

### 3.3 Cloudflare WAF, DNS & SSL/TLS Ingress Setup
- **Location**: `infra/cdn/`
- **Steps**:
  1. Execute Terraform script in `infra/cdn/` with domain `kynetic.ai`.
  2. Point A/AAAA records for `api.kynetic.ai`, `app.kynetic.ai`, `tunnel.kynetic.ai`, and `kynetic.ai` to NGINX Ingress Load Balancer.
  3. Enable Cloudflare WAF OWASP Managed Ruleset, Rate Limiting (100 req/min per IP on `/auth/`), and Universal SSL with strict TLS 1.3 requirement.

---

## Category 4: Email Domain Authentication & Telemetry Pipeline

### 4.1 SendGrid Production Email Activation
- **Target File**: `backend/services/notifications_service/config.py`
- **Steps**:
  1. Update environment variable `EMAIL_MOCK_MODE=false`.
  2. Supply live `SENDGRID_API_KEY` (`SG.XXXXXXXXXXXXXXXXXXXXXXXX`) in Secrets Manager.
  3. Configure DNS records for `kynetic.ai` in domain registrar:
     - **SPF**: `v=spf1 include:sendgrid.net ~all`
     - **DKIM**: Add 2 CNAME records provided by SendGrid (`s1._domainkey.kynetic.ai`, `s2._domainkey.kynetic.ai`).
     - **DMARC**: `v=DMARC1; p=quarantine; rua=mailto:dmarc-reports@kynetic.ai`

### 4.2 Production Observability & Alerting Routing
- **Location**: `infra/observability/`
- **Steps**:
  1. Deploy Promtail DaemonSet to stream JSON logs from all microservice containers to Grafana Loki.
  2. Update `alertmanager.yml` to supply live PagerDuty Integration Key (`PAGERDUTY_SERVICE_KEY`) and Slack Webhook URL (`https://hooks.slack.com/services/XXXXXX`) for critical alerts.

---

## Category 5: Host Agent Code Signing & Supply-Side Seed Pool

### 5.1 Host Agent Binary Signing & Notarization
- **Steps**:
  1. **Windows Host Agent (`kynetic-host-agent.exe`)**:
     - Obtain Sectigo / DigiCert EV Code Signing Certificate.
     - Sign executable using `signtool.exe` to prevent Windows Defender / SmartScreen untrusted publisher warnings:
       ```cmd
       signtool sign /tr http://timestamp.digicert.com /td sha256 /fd sha256 /f kynetic_ev_cert.pfx /p "CERT_PASSWORD" kynetic-host-agent.exe
       ```
  2. **macOS Host Agent (`kynetic-host-agent.app`)**:
     - Sign with Apple Developer ID Application certificate and submit for Apple Notarization via `xcrun notarytool`.
  3. **Linux Installer (`host-agent.sh`)**:
     - Generate GPG detached signature `kynetic-host-agent.asc` and publish public key `https://get.kynetic.ai/kynetic-key.gpg`.

### 5.2 Supply-Side Seed Pool Onboarding
- **Steps**:
  1. Deploy 15 to 25 verified hardware host nodes owned by Kynetic and launch partners across regions:
     - **Mumbai (`ap-south-1`)**: 10x NVIDIA RTX 4090 (24GB VRAM), 4x NVIDIA A100 (80GB VRAM).
     - **US East (`us-east-1`)**: 6x NVIDIA RTX 4090 (24GB VRAM), 2x NVIDIA H100 (80GB VRAM).
  2. Run automated hardware verification & PyTorch benchmarks to populate seed inventory on Day 1.

---

## Category 6: Zero-Trust Security v4 & v5 Production Enforcements

### 6.1 Hardware Remote Attestation Service Endpoints
- **Target File**: `backend/services/security_service/attestation_sealer.py`
- **Steps**:
  1. Connect attestation verification logic to live vendor certificate verification endpoints:
     - **AMD SEV-SNP**: AMD Key Brokerage Service (`https://kdsintf.amd.com/vCEK/v1/`)
     - **Intel TDX**: Intel Provisioning Certification Service (`https://api.trustedservices.intel.com/sgx/certification/v4/`)
     - **NVIDIA GPU CC Mode**: NVIDIA Remote Attestation Service (NRAS API `https://nras.attestation.nvidia.com/v1/attest`)

### 6.2 eBPF XDP Network Firewall Kernel Attachment
- **Target File**: `backend/services/security_service/ebpf_firewall.py`
- **Steps**:
  1. Compile eBPF C program to byte-code (`clang -O2 -target bpf -c xdp_filter.c -o xdp_filter.o`).
  2. Attach XDP program to host primary network interface during `kynetic-host-agent` startup script to enforce hardware-level drop of RFC 1918 private subnets.

---

## Category 7: Final Pre-Launch Verification & Go-Live Gate

### 7.1 Pre-Launch Load & Soak Test
- **Steps**: Run 72-hour continuous soak test using Locust (`backend/tests/load/locustfile.py`) under 1,000 simulated concurrent developer sessions to ensure 0 memory leaks in microservices and Redis connection pools.

### 7.2 Closed Beta Sign-Off Gate
- **Steps**: Invite 50 vetted AI developers and 20 hardware hosts for a 7-day closed beta period. Validate end-to-end user journeys (Host Signup → Benchmark → Listing → Developer Topup → Instance Rental → Workload Run → Termination → Payout → GST Invoice Download) with $0 error rate before removing registration gate.
