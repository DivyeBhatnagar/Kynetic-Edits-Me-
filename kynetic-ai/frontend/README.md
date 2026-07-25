# Kynetic AI — Web Application & Developer Portal

[![Next.js](https://img.shields.io/badge/Next.js-16.2.11-black.svg)](https://nextjs.org/)
[![React](https://img.shields.io/badge/React-19.2.4-61dafb.svg)](https://react.dev/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-v4.0-38bdf8.svg)](https://tailwindcss.com/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0-blue.svg)](https://www.typescriptlang.org/)
[![Zustand](https://img.shields.io/badge/State-Zustand-443e38.svg)](https://zustand-demo.pmnd.rs/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

The **Kynetic AI Frontend** is a modern, unified web application built with **Next.js 16 (App Router)** and **React 19**. It provides an intuitive, real-time portal for AI developers to discover compute, launch 1-click app templates, interact with the AI Copilot, manage active instances, and top up dual-currency wallets (USD/INR via Stripe & Razorpay), while giving host node operators telemetry gauges and earnings management.

---

## ⚡ Features & Portals Overview

The frontend contains **11 full-featured portals & pages**:

### 1. 🏠 Landing & Platform Showcase (`/`)
- Dynamic Hero section with live compute stats and hardware availability badges.
- Interactive hardware catalog preview with search and VRAM sliders.
- AI Copilot natural language workload matching demo.
- Feature highlights: Zero-Trust MicroVM isolation, India-First UPI + 18% GST billing, and transparent external marketplace fallbacks (RunPod, Vast.ai, Lambda).
- Interactive hourly and per-second cost calculator.

### 2. 🤖 AI Copilot Workspace (`/copilot`)
- Natural language intent input (*"Find an RTX 4090 under $1.50/hr for Llama-3 fine-tuning"*).
- Weighted 6-factor node recommendation cards displaying matching confidence scores.
- Detailed scoring breakdown (GPU match, VRAM headroom, host reputation, network latency, price, uptime).
- 1-Click direct instance deployment modal with customizable parameters.

### 3. 🛍️ Compute Marketplace Catalog (`/marketplace` & `/marketplace/[id]`)
- Real-time compute hardware catalog with multi-filter search (GPU model, VRAM capacity, CPU cores, RAM, region, host trust tier).
- Detailed hardware view showing benchmark scores (FP32 TFLOPS, memory bandwidth, NVMe IOPS), pricing breakdown (per hour & per second), host reputation rating, and active availability status.
- Direct deployment trigger modal with SSH key selection and pre-flight validation alerts.

### 4. 🖥️ Active Instances Dashboard (`/instances`)
- Live instance monitor with real-time lifecycle controls (Start, Stop, Restart, Terminate).
- Direct SSH command copy button and Web Terminal quick launch link.
- WireGuard VPN configuration generator and client setup guide.
- Embedded telemetry charts (CPU utilization, GPU core & VRAM usage, memory consumption, network I/O) powered by Recharts.
- Live running cost meter showing accumulated per-second charges.

### 5. 💻 Host Node Operator Center (`/host`)
- Host agent download link & step-by-step registration wizard.
- Real-time system telemetry gauges (NVML GPU temperature, fan speed, power draw, active workloads).
- Earnings dashboard displaying total revenue (USD & INR), pending payouts, and historical breakdown.
- Dynamic auto-pricing rules engine to optimize hardware utilization and yield.
- Emergency host node suspension and workload drain control.

### 6. 💳 Dual-Currency Wallet & Billing (`/wallet`)
- Dual-currency balance management supporting both **USD ($)** and **INR (₹)**.
- **Stripe Checkout & Card Element** integration for global USD payments.
- **Razorpay Checkout SDK** integration for Indian UPI, Netbanking, and Credit/Debit cards.
- Automated 18% GST tax invoice generator (`KYN/2024-25/XXXXXX` format) with PDF download & viewing support.
- Comprehensive transaction ledger history with filterable debits, credits, top-ups, and per-second instance billing entries.
- Low balance alert configuration and auto-recharge settings.

### 7. 🎯 Intent Router (`/router`)
- Direct workload deployment workflow for popular AI models (Llama-3 70B, DeepSeek-R1, SDXL, ComfyUI, Whisper).
- Target latency, maximum budget, and region constraint selectors.
- Automated intelligent matching engine connecting workloads directly to optimal host nodes.

### 8. 📦 App Templates Library (`/templates`)
- 1-Click zero-setup launch catalog for popular AI/ML frameworks & stacks:
  - **vLLM / Ollama** (LLM inference)
  - **ComfyUI / Automatic1111** (AI Image Generation)
  - **PyTorch / TensorFlow** (Deep Learning Workspaces)
  - **JupyterLab** (Data Science Notebooks)
  - **OpenWebUI** (Chatbot Interfaces)
- Pre-configured container environment presets with environment variable injection.

### 9. 🔔 Real-Time Notifications Hub (`/notifications` & `NotificationBell.tsx`)
- Live notification feed with real-time WebSocket / polling alerts.
- Alert types: Host Heartbeat Lost, Low Wallet Balance, Instance Provisioned/Terminated, GST Invoice Generated, Security Alert.
- Unread badge counter in top navbar, category filtering, and single-click mark-as-read.

### 10. 🛡️ Admin Command Center (`/admin`)
- System-wide infrastructure health overview across all 11 microservices.
- Total platform compute metrics (total GPUs registered, active instances, total TFLOPS capacity).
- Host verification approval queue for new compute providers.
- Global user management, account status controls, and role assignment.
- Emergency System-Wide Kill-Switch trigger to halt compromised nodes.
- Global revenue analytics (Stripe + Razorpay volume, platform fee breakdown).

### 11. 👤 User Profile & Security (`/profile`)
- Account credentials management & email verification status.
- SSH Key manager for adding, editing, and deleting public keys.
- API Access Token generator for programmatic marketplace deployment via CLI or SDK.
- Two-Factor Authentication (2FA) setup & billing address management.

---

## 🎨 Tech Stack & UI Architecture

- **Framework**: [Next.js 16.2.11](https://nextjs.org/) (App Router, Server & Client Components)
- **UI Runtime**: [React 19.2.4](https://react.dev/)
- **Styling**: [Tailwind CSS v4](https://tailwindcss.com/) + CSS variables (`globals.css`)
- **Iconography**: [Lucide React](https://lucide.dev/) (`lucide-react`)
- **State Management**: [Zustand](https://github.com/pmndrs/zustand) (`lib/stores/auth.ts`)
- **Data Visualization**: [Recharts](https://recharts.org/) for telemetry graphs & financial analytics
- **Payment Processing**:
  - `@stripe/stripe-js` & `@stripe/react-stripe-js` for global USD transactions
  - Razorpay Checkout SDK for India-first UPI & GST compliance
- **API Client Layer**: Centralized API helper (`lib/api.ts`) supporting JWT header injection, automatic token refresh, error handling, and standalone mock preview mode.

---

## 📂 Frontend Directory Structure

```
frontend/
├── app/                      # Next.js 16 App Router Pages
│   ├── page.tsx              # Landing Page & Public Showcase
│   ├── copilot/              # AI Copilot Natural Language Assistant
│   ├── marketplace/          # Compute Hardware Catalog & Detail Views
│   ├── instances/            # Active Compute Instances & Telemetry
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
│   ├── api.ts                # Centralized REST API Client & Mock Fallback Mode
│   └── stores/
│       └── auth.ts           # Zustand Auth State Store (JWT & User Session)
├── public/                   # Static Assets & Icons
├── package.json              # Dependencies & Scripts
├── tsconfig.json             # TypeScript Configuration
└── tailwind.config.ts        # Tailwind CSS Configuration
```

---

## 🚀 Getting Started

### Prerequisites
- **Node.js**: `>= 18.x` (Recommended: `v20.x` or `v22.x`)
- **npm** or **yarn** or **pnpm**

### 1. Installation
```bash
# Navigate to frontend directory
cd KyneticSoftware/kynetic-ai/frontend

# Install dependencies
npm install
```

### 2. Environment Setup
Create a `.env.local` file in the `frontend` root:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_test_...
NEXT_PUBLIC_RAZORPAY_KEY_ID=rzp_test_...
```

### 3. Run Development Server
```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser to view the portal.

### 4. Build for Production
```bash
# Type check and build Next.js production bundle
npm run build

# Start production server
npm start
```
