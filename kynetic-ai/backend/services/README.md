# Kynetic AI — Microservices Directory

This directory houses the backend microservices powering the Kynetic compute marketplace. The architecture uses a **Hybrid Go/Python** model:
- **Python (FastAPI + SQLAlchemy 2.0 Async)** for control plane business logic, billing math, marketplace matchmaking, zero-trust policy decisions, and AI routing.
- **Go** for the high-concurrency NAT-traversing reverse tunnel gateway (`gateway_tunnel_go/`).

---

## 🗺️ Microservices Registry

| Port | Service Directory | Language | Description |
|---|---|---|---|
| **8000** | [`api_gateway/`](api_gateway/) | Python | Unified reverse proxy, rate limiting, JWT validation & routing |
| **8001** | [`auth_service/`](auth_service/) | Python | OAuth2 Device Grant, user registration, JWT rotation & 2FA |
| **8002** | [`marketplace_service/`](marketplace_service/) | Python | Hardware catalog, smart search engine & listing indexing |
| **8003** | [`provisioning_service/`](provisioning_service/) | Python | Instance state machine & gRPC client to host agent daemons |
| **8004** | [`wallet_billing_service/`](wallet_billing_service/) | Python | Dual-currency wallet (USD/INR), Stripe/Razorpay webhooks & double-entry ledger |
| **8005** | [`ai_router_copilot_service/`](ai_router_copilot_service/) | Python | Natural language intent parser & 6-factor weighted scheduler |
| **8006** | [`reputation_pricing_service/`](reputation_pricing_service/) | Python | Time-decay reputation scoring, host verification & GPU benchmark DB |
| **8007** | [`security_service/`](security_service/) | Python | Zero-Trust PDP, TPM 2.0 attestation, audit hash chaining & risk engine |
| **8008** | [`gateway_tunnel_go/`](gateway_tunnel_go/) | **Go** | **Production NAT reverse tunnel gateway (10K+ concurrent PTY streams)** |
| **8009** | [`gateway_service/`](gateway_service/) | Python | Python reference implementation of reverse-dial WebSocket relay |
| **8010** | [`notifications_service/`](notifications_service/) | Python | Webhooks, email alerts, invoice dispatch & system events |
| **8011** | [`monitoring_service/`](monitoring_service/) | Python | Prometheus metrics scraper & host node liveness tracker |
| **8012** | [`payout_service/`](payout_service/) | Python | Host KYC financial onboarding, priority commission & payout batches |
| **8013** | [`host_service/`](host_service/) | Python | Host node registration, hardware profiling & commission settings |

---

## 🚀 Running Microservices Locally

```bash
# Start all services with Docker Compose
docker compose up -d

# Or run individual Python services
cd backend
uvicorn services.api_gateway.main:app --port 8000 --reload
```
