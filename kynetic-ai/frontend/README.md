# Kynetic AI — Web Application & Developer Portal

[![Next.js](https://img.shields.io/badge/Next.js-16.2.11-black.svg)](https://nextjs.org/)
[![React](https://img.shields.io/badge/React-19.2.4-61dafb.svg)](https://react.dev/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-v4.0-38bdf8.svg)](https://tailwindcss.com/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0-blue.svg)](https://www.typescriptlang.org/)
[![Zustand](https://img.shields.io/badge/State-Zustand-443e38.svg)](https://zustand-demo.pmnd.rs/)
[![Recharts](https://img.shields.io/badge/Charts-Recharts-22b5bf.svg)](https://recharts.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

The **Kynetic AI Frontend** is a modern web application built with **Next.js 16 (App Router)** and **React 19**. It provides an intuitive, real-time portal for AI developers to discover compute, launch 1-click app templates, interact with the AI Copilot, manage active instances, and top up dual-currency wallets (USD/INR via Stripe & Razorpay), while giving host node operators telemetry gauges and earnings management.

---

## ⚡ Comprehensive Portals & Pages Deep-Dive

The web application contains **11 full-featured portals & pages**:

### 1. 🏠 Landing & Public Showcase (`/`)
- **Dynamic Hero Section**: Live compute capacity counters (total GPUs online, available FP32 TFLOPS, active workloads) and real-time status indicators.
- **Interactive Hardware Catalog Preview**: Live search bar with VRAM sliders, GPU architecture filters (RTX 4090, A100, H100, L40S), and hourly/per-second pricing cards.
- **AI Copilot Showcase**: Embedded interactive natural language intent parser demonstration (*"Find an RTX 4090 under $1.50/hr for LoRA fine-tuning"*).
- **Core Differentiator Highlights**:
  - Zero-Trust Firecracker MicroVM runtime & LUKS2 volume encryption.
  - India-First regional billing: Razorpay UPI, Netbanking, and automated 18% GST tax invoice generation.
  - Transparent external marketplace fallbacks (RunPod, Vast.ai, Lambda, Crusoe).
- **Cost Calculator Widget**: Interactive slider comparing hourly vs per-second billing savings.

### 2. 🤖 AI Copilot Workspace (`/copilot`)
- **Natural Language Intent Assistant**: Text prompt input accepting human workload descriptions.
- **6-Factor Weighted Node Recommendation Cards**:
  - Displays recommendation cards ranked by weighted matching confidence scores.
  - 6-Factor breakdown gauges: GPU Compute Match, VRAM Headroom, Host Reputation, Network Latency, Price Efficiency, Uptime History.
- **Custom Weight Adjuster**: Slider controls to adjust criteria priorities (e.g., prioritize lower latency over price).
- **1-Click Direct Launch Modal**: Instant deployment modal with pre-selected parameters and SSH key assignment.

### 3. 🛍️ Compute Marketplace Catalog (`/marketplace` & `/marketplace/[id]`)
- **Multi-Filter Hardware Catalog**: Search and filter by GPU model, VRAM capacity, CPU core count, RAM size, region, verification level (`Silver`, `Gold`, `Enterprise`), reputation score, and availability state.
- **Listing Detail Page**:
  - Hardware benchmark scores: Peer-group normalized FP16/FP32 TFLOPS, memory bandwidth (GB/s), NVMe IOPS, network throughput.
  - Rolling 7-Day Health Scores: Thermal stability (°C), GPU core clock stability, and power draw stability dials.
  - Dual-currency pricing breakdown: Hourly ($/hr & ₹/hr) and per-second micro-rates.
  - Host node trust & reputation metrics: Time-decayed composite reputation score (0.00–1.00 score), verified trust tier badge (`Silver`, `Gold`, `Enterprise`), dispute/refund history.
- **Direct Deployment Trigger Modal**: Pre-flight balance check alerts, SSH key pair selection, and instance configuration.

### 4. 🖥️ Active Instances Dashboard (`/instances` & `/instances/[id]`)
- **Live Instance Management Grid**: Displays all active, stopped, and provisioning compute instances with state badges.
- **Real-Time Lifecycle Controls**: Buttons to **Start**, **Stop**, **Restart**, and **Terminate** instances.
- **SSH Connection Modal & Key Retrieval**:
  - Ephemeral SSH command generator (`ssh -i ~/.ssh/kynetic_key.pem -p <port> user@host`).
  - One-time private key display with copy-to-clipboard button and `chmod 600` setup guidance.
- **WireGuard VPN Configuration Generator**: Config download button for peer-to-peer encrypted WireGuard connections.
- **Embedded Telemetry Charts**: Live streaming charts powered by Recharts:
  - GPU VRAM & core clock utilization.
  - CPU usage & memory consumption.
  - Disk IOPS & Network I/O throughput.
- **Running Cost Counter**: Live updating meter displaying accumulated per-second charges.

### 5. 💻 Host Node Operator Center (`/host`)
- **Host Agent Installation Wizard**: Download links for cross-platform Python host agent binary and step-by-step registration commands.
- **Real-Time System Telemetry Gauges**:
  - NVML GPU temperature gauges (°C) with warning thresholds.
  - Fan speed (%) and power draw (Watts) dials.
  - Active guest workload allocations and Firecracker microVM container status.
- **Earnings & Financial Ledger**: Revenue charts broken down by USD ($) and INR (₹), pending payouts, and payout history.
- **Auto-Pricing Strategy Rules Engine**: Configurable dynamic pricing parameters allowing host operators to optimize yield based on local hardware demand.
- **Emergency Host Controls**: Node pause button and graceful workload drain triggers.

### 6. 💳 Dual-Currency Wallet & Billing (`/wallet`)
- **Dual-Currency Balance Display**: Live tracking of **USD ($)** and **INR (₹)** balances.
- **Stripe Payment Gateway**: Credit and Debit card top-ups with Stripe Elements UI and instant webhook confirmation.
- **Razorpay Payment Gateway**: India-first payment processing:
  - **UPI** (Google Pay, PhonePe, Paytm, BHIM).
  - **Netbanking** (HDFC, ICICI, SBI, Axis).
  - **Credit & Debit Cards**.
- **Automated 18% GST Tax Invoice Viewer**:
  - Tax-compliant PDF invoice generator (`KYN/2024-25/XXXXXX` format).
  - Tax breakdown: CGST (9%), SGST (9%), or IGST (18%) based on state region.
- **Transaction Ledger History**: Searchable and filterable ledger listing top-ups, reservation holds, usage debits, and refund credits.
- **Auto-Recharge & Alert Thresholds**: Low balance email notification triggers.

### 7. 🎯 Intent Router (`/router`)
- **Workload Submission Workspace**: Direct selection for AI model architectures (Llama-3 70B, DeepSeek-R1, SDXL, ComfyUI, Whisper, YOLOv8).
- **Constraint Selectors**: Target latency SLA (ms), maximum hourly budget, and geographic region constraints.
- **Automated Match Execution**: Directly connects submitted workloads to the optimal host node in the network.

### 8. 📦 App Templates Catalog (`/templates`)
- **1-Click Zero-Setup Launch Library**:
  - **vLLM / Ollama** (High-throughput LLM inference).
  - **ComfyUI / Automatic1111** (AI Image & Video Generation).
  - **PyTorch / TensorFlow** (Deep Learning Development Environments).
  - **JupyterLab** (Data Science Notebook Workspaces).
  - **OpenWebUI** (Chatbot UI Interface).
- **Environment Injector**: Presets allowing custom environment variables, HuggingFace API tokens, and model download URLs.

### 9. 🔔 Real-Time Notifications Hub (`/notifications` & `NotificationBell.tsx`)
- **Live Alert Feed**: Notification list powered by WebSocket updates / polling.
- **Severity Icons & Categories**: Host Disconnects, Low Balance Warnings, Instance Lifecycle Events, GST Invoices, Security Alerts.
- **Navbar Integration**: Bell icon with live unread badge count, dropdown preview, and one-click "Mark All as Read".

### 10. 🛡️ Admin Command Center (`/admin`)
- **Infrastructure Health Overview**: Operational status gauges across all 11 microservices (`api_gateway`, `auth_service`, `marketplace_service`, etc.).
- **Total Compute Capacity Metrics**: Aggregated network TFLOPS, total VRAM online, active host count, active instance count.
- **Host Verification Approval Queue**: Review interface for new host registrations, hardware benchmarks, and verification approvals.
- **User Account Management**: User status controls, role assignments, and permission overrides.
- **Emergency System Kill-Switch**: Master emergency kill-switch trigger to halt compromised compute nodes.
- **Revenue Analytics**: Aggregate volume charts (Stripe + Razorpay) and platform commission fee breakdown.

### 11. 👤 User Profile & Security (`/profile`)
- **User Credentials**: Profile details, email verification status, and password update forms.
- **SSH Key Manager**: Manage public SSH keys (`~/.ssh/id_rsa.pub`) for instance access.
- **API Access Token Generator**: Issue and revoke programmatic API tokens for CLI and SDK usage.
- **Two-Factor Authentication (2FA)**: TOTP / Authenticator app setup.

---

## 🎨 Tech Stack & Component Architecture

- **Framework**: [Next.js 16.2.11](https://nextjs.org/) (App Router, Server & Client Components)
- **UI Engine**: [React 19.2.4](https://react.dev/)
- **Styling**: [Tailwind CSS v4](https://tailwindcss.com/) + CSS Design Tokens (`globals.css`)
- **Icons**: [Lucide React](https://lucide.dev/) (`lucide-react`)
- **State Management**: [Zustand](https://github.com/pmndrs/zustand) (`lib/stores/auth.ts`)
- **Data Visualization**: [Recharts](https://recharts.org/) for telemetry graphs & financial analytics
- **Payment Processing**:
  - `@stripe/stripe-js` & `@stripe/react-stripe-js`
  - Razorpay Checkout SDK
- **API Client**: Centralized API helper (`lib/api.ts`) supporting JWT token injection, automatic token refresh, error handling, and standalone mock preview mode.

---

## 📂 Frontend File Tree

```
frontend/
├── app/                      # Next.js 16 App Router Pages
│   ├── page.tsx              # Landing Page & Public Showcase
│   ├── copilot/              # AI Copilot Natural Language Assistant
│   ├── marketplace/          # Compute Hardware Catalog & Detail Views
│   │   ├── page.tsx          # Catalog Grid & Search
│   │   └── [id]/page.tsx     # Hardware Listing Detail View
│   ├── instances/            # Active Compute Instances & Telemetry
│   │   ├── page.tsx          # Managed Instances Grid
│   │   └── [id]/page.tsx     # Instance Telemetry & SSH Connect Modal
│   ├── host/                 # Host Operator Dashboard & Telemetry
│   ├── wallet/               # Dual-Currency Wallet & Stripe/Razorpay Billing
│   ├── router/               # Intent-Based Workload Router
│   ├── templates/            # 1-Click App Templates Catalog
│   ├── notifications/        # Real-time Notifications Portal
│   ├── admin/                # Platform Admin Command Center
│   ├── profile/              # User Settings, SSH Keys & API Tokens
│   ├── layout.tsx            # Root Layout & Font Providers
│   └── globals.css           # Custom Design Tokens & Tailwind Directives
├── components/               # Shared Reusable UI Components
│   ├── Navbar.tsx            # Global Navigation Bar with Active Route Indicators
│   └── NotificationBell.tsx  # Live Notification Dropdown & Counter
├── lib/                      # Utilities, API Client & State Stores
│   ├── api.ts                # Centralized REST API Client & Standalone Mock Mode
│   └── stores/
│       └── auth.ts           # Zustand Auth State Store (JWT & User Session)
├── public/                   # Static Assets & Favicons
├── package.json              # Dependencies & Scripts
├── tsconfig.json             # TypeScript Configuration
└── tailwind.config.ts        # Tailwind CSS Configuration
```

---

## 🚀 Getting Started & Local Development

### Prerequisites
- **Node.js**: `>= 18.x` (Recommended: `v20.x` or `v22.x`)
- **npm** or **yarn** or **pnpm**

### 1. Installation
```bash
cd frontend
npm install
```

### 2. Environment Variables (`.env.local`)
Create `.env.local` in the `frontend` folder:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_test_...
NEXT_PUBLIC_RAZORPAY_KEY_ID=rzp_test_...
```

### 3. Launch Development Server
```bash
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) in your browser.

### 4. Production Build
```bash
# Type check and build production bundle
npm run build

# Start production server
npm start
```
