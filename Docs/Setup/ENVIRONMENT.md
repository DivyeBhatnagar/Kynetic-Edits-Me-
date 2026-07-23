# Kynetic AI — Environment Variables & Configuration Reference

This document provides a comprehensive reference of all environment variables used across the 11 backend microservices, Next.js frontend apps, database migrations, and infrastructure configurations.

---

## 1. Global & Shared Variables (`.env`)

| Variable Name | Required | Default Value | Description |
|---|---|---|---|
| `ENVIRONMENT` | Yes | `development` | Deployment environment (`development`, `staging`, `production`) |
| `POSTGRES_HOST` | Yes | `localhost` | PostgreSQL database host address |
| `POSTGRES_PORT` | Yes | `5432` | PostgreSQL database port |
| `POSTGRES_DB` | Yes | `kynetic_db` | PostgreSQL database name |
| `POSTGRES_USER` | Yes | `postgres` | PostgreSQL administrative username |
| `POSTGRES_PASSWORD` | Yes | `postgres` | PostgreSQL administrative password |
| `REDIS_HOST` | Yes | `localhost` | Redis server host address |
| `REDIS_PORT` | Yes | `6379` | Redis server port |
| `JWT_SECRET_KEY` | Yes | `CHANGE_ME_IN_PRODUCTION` | Secret key for signing HS256 JWT auth tokens |
| `JWT_ALGORITHM` | No | `HS256` | JWT signing algorithm |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | No | `60` | Lifespan of access tokens in minutes |

---

## 2. Wallet & Billing Service (`wallet_billing_service`)

| Variable Name | Required | Default Value | Description |
|---|---|---|---|
| `RAZORPAY_MOCK_MODE` | No | `true` | When `true`, simulates Razorpay API calls without hitting endpoints |
| `RAZORPAY_KEY_ID` | Production | `rzp_test_...` | Razorpay Key ID |
| `RAZORPAY_KEY_SECRET` | Production | `...` | Razorpay Key Secret |
| `RAZORPAY_WEBHOOK_SECRET` | Production | `...` | Razorpay Webhook HMAC secret key |
| `STRIPE_SECRET_KEY` | Production | `sk_test_...` | Stripe API secret key |
| `STRIPE_PUBLISHABLE_KEY` | Production | `pk_test_...` | Stripe API publishable key |
| `STRIPE_WEBHOOK_SECRET` | Production | `whsec_...` | Stripe Webhook HMAC secret key |
| `USD_TO_INR_RATE` | No | `84.0` | Fallback FX conversion rate USD to INR |

---

## 3. Notifications Service (`notifications_service`)

| Variable Name | Required | Default Value | Description |
|---|---|---|---|
| `EMAIL_MOCK_MODE` | No | `true` | When `true`, logs email dispatches to console without sending via SendGrid |
| `SENDGRID_API_KEY` | Production | `SG.test_...` | SendGrid API key for production emails |
| `EMAIL_FROM_ADDRESS` | No | `noreply@kynetic.ai` | Sender email address |
| `EMAIL_FROM_NAME` | No | `Kynetic AI` | Sender display name |

---

## 4. Security & Attestation Services (`security_service`)

| Variable Name | Required | Default Value | Description |
|---|---|---|---|
| `ATT_ENCLAVE_SECRET_KEY` | Production | Random 32 bytes | ECDH private key for sealing secrets to hardware enclaves |
| `EBPF_ENABLED` | No | `true` | Enable eBPF XDP network micro-segmentation filter |
| `CHACHA20_RAM_OVERLAY` | No | `true` | Enable ChaCha20-Poly1305 RAM buffer encryption overlay |
| `ANTI_DEBUGGING_ENFORCE` | No | `true` | Enforce `prctl(PR_SET_DUMPABLE, 0)` process isolation |

---

## 5. Frontend Applications (`apps/frontend`, `apps/admin_dashboard`)

| Variable Name | Required | Default Value | Description |
|---|---|---|---|
| `NEXT_PUBLIC_API_GATEWAY_URL` | Yes | `http://localhost:8000` | Gateway URL for public client API requests |
| `NEXT_PUBLIC_WS_COPILOT_URL` | Yes | `ws://localhost:8005/copilot/ws` | WebSocket URL for AI Copilot chat service |
| `NEXT_PUBLIC_RAZORPAY_KEY_ID` | Production | `rzp_test_...` | Client-side Razorpay Key ID for UPI checkout modal |
