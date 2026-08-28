# Kynetic AI — Frontend Rebuild Master Specification

> **Comprehensive Pages, Portals, Components, and Architecture Guide**  
> Target Roles: **AI Developer / User**, **Host Node Operator**, and **Platform Administrator**

---

## 🗺️ 1. Master Route & File Tree Architecture

```text
frontend/
├── app/
│   ├── (public)/                                   # Public & Authentication
│   │   ├── page.tsx                                # 1. Landing & Public Showcase
│   │   ├── login/page.tsx                          # 2. Authentication: Login & OAuth
│   │   ├── register/page.tsx                       # 3. Authentication: Sign Up & Role Selection
│   │   ├── forgot-password/page.tsx                # 4. Authentication: Password Reset
│   │   └── docs/page.tsx                           # 5. Developer API & Architecture Docs Preview
│   │
│   ├── (developer)/                                # User / AI Developer Portal
│   │   ├── dashboard/page.tsx                      # 6. Developer Overview Dashboard
│   │   ├── marketplace/page.tsx                    # 7. Compute Hardware Catalog & Search Grid
│   │   ├── marketplace/[id]/page.tsx               # 8. Compute Listing Detail View & Launch Modal
│   │   ├── copilot/page.tsx                        # 9. Natural Language AI Copilot Workspace
│   │   ├── router/page.tsx                         # 10. Intent-Based Workload Router
│   │   ├── templates/page.tsx                      # 11. 1-Click App Templates Catalog (vLLM, ComfyUI, etc.)
│   │   ├── instances/page.tsx                      # 12. Active Compute Instances Fleet Grid
│   │   ├── instances/[id]/page.tsx                 # 13. Instance Telemetry Hub, SSH & WireGuard Access
│   │   ├── wallet/page.tsx                         # 14. Dual-Currency Wallet & GST Billing Hub
│   │   ├── notifications/page.tsx                  # 15. Notification Center
│   │   └── profile/page.tsx                        # 16. User Profile, Public SSH Keys & API Tokens
│   │
│   ├── host/                                       # Host Node Operator Portal
│   │   ├── page.tsx                                # 17. Host Operator Overview & Fleet Status
│   │   ├── onboarding/page.tsx                     # 18. Host Agent Installation & CLI Setup Wizard
│   │   ├── nodes/[id]/page.tsx                     # 19. Host Node Deep Telemetry & Hardware Gauges
│   │   ├── pricing/page.tsx                        # 20. Dynamic Auto-Pricing Strategy Rules Engine
│   │   ├── earnings/page.tsx                       # 21. Earnings Ledger, Payouts & Banking Details
│   │   └── reputation/page.tsx                     # 22. Benchmarks, Tier Badges & Health Scores
│   │
│   └── admin/                                      # Platform Administrator Portal
│       ├── page.tsx                                # 23. Admin Command Center & Microservice Health
│       ├── hosts/page.tsx                          # 24. Host Verification & Approval Queue
│       ├── users/page.tsx                          # 25. User & Tenant Directory Management
│       ├── instances/page.tsx                      # 26. Global Workload Inspector & Kill-Switch
│       └── finance/page.tsx                        # 27. Platform Revenue, GST Ledger & Payout Settlement
```

---

## 2. 👤 AI Developer & End-User Portal (11 Pages)

### 2.1 🏠 Landing & Public Showcase (`/`)
* **Purpose**: Primary conversion page showcasing live decentralized compute capacity and key differentiators.
* **Core Sections**:
  * **Dynamic Hero Section**: Real-time counter ticker (Total GPUs Online, Total FP32 TFLOPS, Active MicroVMs, Global Uptime SLA).
  * **Interactive Hardware Catalog Preview**: Quick GPU architecture tabs (RTX 4090, A100 SXM, H100 PCIe, L40S) with VRAM sliders and hourly price display.
  * **Interactive Copilot Demo Widget**: Natural language test prompt input (*"Find 2x RTX 4090 under $1.20/hr for LoRA fine-tuning"*).
  * **Interactive Savings Calculator**: Slider comparing AWS/GCP hourly costs against Kynetic per-second micro-metered billing.
  * **Zero-Trust Security & India-First Features**: Explaining Firecracker MicroVMs, LUKS2 volume encryption, and Razorpay UPI + automated 18% GST tax invoices.

### 2.2 🔐 Authentication Suite (`/login`, `/register`, `/forgot-password`)
* **Purpose**: Clean, secure auth workflows supporting credentials, OAuth, and 2FA.
* **Core Components**:
  * Login form with email/password and OAuth (GitHub, Google).
  * Role selection during registration (`Developer / AI Researcher` vs `Compute Host Operator`).
  * Two-Factor Authentication (2FA TOTP) verification step.
  * Password strength checker & instant email verification notice.

### 2.3 📊 Developer Overview Dashboard (`/dashboard`)
* **Purpose**: Fast overview of running workloads, recent spend, and quick-launch shortcuts.
* **Core Components**:
  * **Summary KPI Cards**: Active Instances, Monthly Burn Rate ($ / ₹), Remaining Wallet Balance, Network Status.
  * **Active Workloads Mini-Table**: Quick pause, restart, or SSH connect button for running instances.
  * **1-Click Launch Bar**: Fast shortcuts to popular AI stacks (vLLM, ComfyUI, JupyterLab).

### 2.4 🛍️ Compute Marketplace Catalog (`/marketplace` & `/marketplace/[id]`)
* **Purpose**: Discovery, filtering, hardware inspection, and instance deployment.
* **Core Components**:
  * **Multi-Filter Sidebar**: GPU Model, VRAM Range (24GB to 80GB), Trust Tier (`Silver`, `Gold`, `Enterprise`), Region, Minimum Reputation Score (0.00–1.00), Max Hourly Price ($/hr & ₹/hr).
  * **Hardware Listing Card**:
    * GPU Model, PCIe vs SXM, VRAM, CPU cores, System RAM, Disk size.
    * Host Trust Tier badge, Reputation score, and Verified Benchmark score.
    * Dual-currency price matrix (Hourly + Per-second rate).
  * **Listing Detail Page (`/marketplace/[id]`)**:
    * Normalized FP16/FP32 TFLOPS, NVMe IOPS, and memory bandwidth benchmarks.
    * 7-day rolling health charts (Thermal stability, Clock jitter, Power stability).
    * Dual-currency pricing breakdown and refund dispute history.
  * **Direct Launch Modal**:
    * Pre-flight balance validation check (warns if balance is below minimum 1-hour burn).
    * SSH Public Key selector / generator.
    * Base Docker / MicroVM image selector (Ubuntu 22.04 + CUDA 12.4, PyTorch, vLLM).

### 2.5 🤖 AI Copilot Workspace (`/copilot`)
* **Purpose**: Conversational AI matchmaking assistant for complex compute workloads.
* **Core Components**:
  * Natural language prompt workspace with suggested prompt chips.
  * **6-Factor Weighted Recommendation Cards**:
    1. GPU Compute Match
    2. VRAM Headroom
    3. Host Trust & Reputation
    4. Network Latency
    5. Cost Efficiency
    6. Historical Uptime
  * **Weight Tuning Sliders**: User can adjust importance between Latency vs Price vs Reputation in real-time.
  * 1-Click Instant Deploy modal directly from recommendations.

### 2.6 🎯 Intent-Based Workload Router (`/router`)
* **Purpose**: Automated matching based on strict model architecture and SLA budgets.
* **Core Components**:
  * AI Model Selector (DeepSeek-R1, Llama 3.3 70B, SDXL, Whisper, YOLOv8).
  * Constraints Configuration: Target Latency SLA (ms), Max Hourly Budget, Geo-affinity.
  * Match Preview & Automated Dispatch engine.

### 2.7 📦 1-Click App Templates Catalog (`/templates`)
* **Purpose**: Zero-setup, pre-configured application stack launcher.
* **Core Components**:
  * Categories: **LLM Inference** (vLLM, Ollama), **Generative Media** (ComfyUI, Automatic1111), **Notebooks** (JupyterLab), **Development** (PyTorch, TensorFlow), **Chat UI** (OpenWebUI).
  * Environment variable injector (HuggingFace API Token, Model Weights URL, Custom Startup Script).
  * Direct launch hook routed through Marketplace provisioning.

### 2.8 🖥️ Active Instances Fleet (`/instances` & `/instances/[id]`)
* **Purpose**: Instance lifecycle management, live telemetry streaming, and remote connections.
* **Core Components**:
  * **Fleet Grid / Table**: Status badges (`Provisioning`, `Running`, `Paused`, `Terminating`), Live Per-Second Cost Meter.
  * **Lifecycle Action Controls**: Start, Stop, Restart, Terminate with confirmation modals.
  * **Instance Detail View (`/instances/[id]`)**:
    * **Streaming Telemetry Charts (Recharts)**: GPU VRAM %, GPU Clock (MHz), GPU Temp (°C), CPU %, RAM %, Disk IOPS, Network I/O.
    * **Connection Generator Modal**:
      * One-click SSH command: `ssh -i ~/.ssh/kynetic.pem -p <port> root@<host>`
      * Downloadable ephemeral private key + `chmod 600` clipboard helper.
      * Peer-to-peer WireGuard VPN configuration file download.
    * Interactive Web Terminal / Container Logs viewer.

### 2.9 💳 Dual-Currency Wallet & GST Billing (`/wallet`)
* **Purpose**: Account funding, payment gateway integrations, and tax invoice compliance.
* **Core Components**:
  * **Dual Balance Cards**: Live USD ($) and INR (₹) balances with currency toggle.
  * **Top-Up Form with Dual Gateways**:
    * **Stripe**: Credit/Debit Cards via Stripe Elements.
    * **Razorpay**: UPI (Google Pay, PhonePe, Paytm), Netbanking, Indian Credit/Debit Cards.
  * **Auto-Recharge Settings**: Low-balance alert threshold toggle and auto-refill triggers.
  * **GST Tax Invoice Viewer**:
    * Compliant invoice preview with automated CGST (9%), SGST (9%), or IGST (18%) breakdown.
    * Downloadable PDF invoice generator (`KYN/2024-25/XXXXXX`).
  * **Transaction Ledger**: Searchable history of top-ups, reservation holds, micro-metered debits, and refunds.

### 2.10 🔔 Notifications Center (`/notifications`)
* **Purpose**: Real-time alert feed for user account and workloads.
* **Core Components**:
  * Category filters: Host Disconnects, Low Balance Warnings, Instance State Transitions, GST Invoices, Security Alerts.
  * Unread badge counter, "Mark All as Read", and actionable deep links.

### 2.11 👤 User Profile & Security (`/profile`)
* **Purpose**: Account credentials, SSH key management, and API access tokens.
* **Core Components**:
  * Profile info & password update form.
  * **Public SSH Key Manager**: Add, label, and delete public keys (`~/.ssh/id_rsa.pub`).
  * **API Access Token Generator**: Create programmatic API tokens for CLI/SDK, display once, revoke.
  * **2FA Authenticator App Setup**: QR code scanner & verification code input.

---

## 3. 💻 Host Node Operator Portal (6 Pages)

### 3.1 🖥️ Host Overview & Capacity Dashboard (`/host`)
* **Purpose**: Central telemetry and status monitoring for node providers.
* **Core Components**:
  * **KPI Metric Cards**: Online Nodes, Total Hosted GPUs, Current Utilization (%), Estimated Today's Revenue ($ & ₹).
  * **Fleet Status Table**: Per-node status, current tenant MicroVM ID, uptime percentage, and quick pause button.

### 3.2 🛠️ Host Agent Onboarding Wizard (`/host/onboarding`)
* **Purpose**: Frictionless node registration and automated benchmarking.
* **Core Components**:
  * OS Selector (Ubuntu 22.04 LTS / Debian / RHEL).
  * 1-Liner Bash Install Command with injected host authentication token:
    ```bash
    curl -sSL https://get.kynetic.ai/install.sh | bash -s -- --token=kyn_host_xyz123
    ```
  * Live registration progress stepper (Agent Connected -> Hardware Discovered -> Benchmark Executing -> Node Verified).

### 3.3 📈 Node Deep Telemetry & Controls (`/host/nodes/[id]`)
* **Purpose**: Real-time hardware health and MicroVM isolation management.
* **Core Components**:
  * **NVML Hardware Dials**: Real-time GPU Temp (°C) with thermal throttle warnings, Fan Speed (%), Power Draw (Watts vs TDP limit).
  * Active MicroVM guest allocation details and encrypted LUKS volume status.
  * **Emergency Node Controls**: Drain workloads gracefully or pause node from accepting new bids.

### 3.4 🏷️ Dynamic Auto-Pricing Strategy Engine (`/host/pricing`)
* **Purpose**: Maximize host yield based on real-time network demand.
* **Core Components**:
  * Strategy mode selector: **Fixed Hourly Rate** vs **Dynamic Yield Optimizer**.
  * Dynamic parameters: Floor price ($/hr), Target utilization %, Surge multiplier on peak network demand.
  * Preview chart showing projected revenue vs historical pricing.

### 3.5 💰 Earnings & Payout Ledger (`/host/earnings`)
* **Purpose**: Settlement management and payouts.
* **Core Components**:
  * Unsettled balance and next scheduled payout date.
  * Payout Method Configuration: Stripe Connect (Global) / Direct Bank Wire & UPI (India).
  * Payout history table with download receipts and transaction IDs.

### 3.6 🏆 Reputation & Benchmark Center (`/host/reputation`)
* **Purpose**: Transparency on trust score and verified tiers.
* **Core Components**:
  * Composite Trust Tier score badge (`Silver`, `Gold`, `Enterprise`).
  * Historical FP16 / FP32 benchmark runs against peer GPUs.
  * SLA metrics: Uptime track record, zero-dispute rating, and thermal stability index.

---

## 4. 🛡️ Platform Admin Portal (5 Pages)

### 4.1 ⚡ Admin Command Center (`/admin`)
* **Purpose**: Platform-wide observability and service orchestration.
* **Core Components**:
  * **Microservice Health Matrix**: Live ping and status for all 11 backend services (`api_gateway`, `marketplace_service`, `provisioning_service`, `wallet_billing_service`, etc.).
  * **Global Capacity Totals**: Network TFLOPS, Total VRAM online, Active Instances, Total Registered Hosts.
  * **Platform Emergency Kill-Switch**: One-click master safety switch with confirmation modal.

### 4.2 📋 Host Verification & Approval Queue (`/admin/hosts`)
* **Purpose**: Quality control and fraud prevention for compute providers.
* **Core Components**:
  * Pending host application queue.
  * Benchmark verification auditor (checks for spoofed hardware / virtualized GPUs).
  * Action controls: Approve Node, Assign Trust Tier (`Silver`/`Gold`/`Enterprise`), or Reject/Blacklist Host.

### 4.3 👥 User & Tenant Directory Management (`/admin/users`)
* **Purpose**: Account moderation and balance management.
* **Core Components**:
  * Searchable user directory with role badges (`User`, `Host`, `Admin`).
  * User detail drawer: Active instances, wallet balances, dispute logs.
  * Administrative actions: Manual balance credit/debit, force password reset, suspend account.

### 4.4 🌐 Global Workload & Instance Inspector (`/admin/instances`)
* **Purpose**: Real-time network-wide compute instance oversight.
* **Core Components**:
  * Live list of all running instances across all hosts and tenants.
  * Resource consumption anomalies detector (e.g., crypto-mining abuse detection).
  * Administrative Force-Terminate action.

### 4.5 📊 Financial & Revenue Analytics (`/admin/finance`)
* **Purpose**: Platform Gross Merchandise Value (GMV) and tax reconciliation.
* **Core Components**:
  * Gross Volume charts: Stripe (USD) vs Razorpay (INR).
  * Platform Commission Fee revenue accumulator (e.g., 10% marketplace take-rate).
  * Host payout batch processing trigger.
  * Aggregated GST tax collection summary (CGST/SGST/IGST breakdown for tax filings).

---

## 5. 🧩 Shared Reusable UI Components

| Component | Path | Description |
| :--- | :--- | :--- |
| `Navbar` | `components/Navbar.tsx` | Global navbar with role toggle, balance pill, and route indicators |
| `NotificationBell` | `components/NotificationBell.tsx` | Dropdown notification preview with live unread badge |
| `StatusBadge` | `components/ui/StatusBadge.tsx` | Colored pill for instance/host state (`Running`, `Provisioning`, `Paused`, `Error`) |
| `TrustTierBadge` | `components/ui/TrustTierBadge.tsx` | `Silver`, `Gold`, `Enterprise` badges with verified icons |
| `DualCurrencyInput` | `components/ui/DualCurrencyInput.tsx` | Input accepting either USD or INR with real-time conversion |
| `TelemetryAreaChart`| `components/charts/TelemetryAreaChart.tsx` | Streaming live Recharts graph for GPU/CPU/Memory/Disk |
| `RadialHealthGauge` | `components/charts/RadialHealthGauge.tsx` | Circular dial for GPU temperature, fan speed, and power draw |
| `SSHConnectModal` | `components/modals/SSHConnectModal.tsx` | SSH command snippet, private key download, WireGuard config |
| `DeployModal` | `components/modals/DeployModal.tsx` | Pre-flight balance check, SSH key picker, image selector |
| `GSTInvoiceViewer` | `components/billing/GSTInvoiceViewer.tsx` | Compliant GST tax invoice preview with print/PDF export |

---

## 6. ⚙️ State Management & API Client

* **Auth Store (`lib/stores/auth.ts`)**: Manages JWT tokens, user role (`developer`, `host`, `admin`), profile data, and session expiry.
* **Wallet Store (`lib/stores/wallet.ts`)**: Dual-currency active toggle, USD/INR balances, payment modal states.
* **Marketplace Store (`lib/stores/marketplace.ts`)**: Search terms, GPU filter selections, VRAM sliders, sorting criteria.
* **API Client (`lib/api.ts`)**: Centralized Axios/Fetch client with automatic token injection, 401 token refresh interceptors, error toasts, and offline mock data fallback.
