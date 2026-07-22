# Kynetic AI — Monorepo

A **compute-first, AI-native marketplace** connecting hosts with idle compute (GPUs, CPUs, RAM, NVMe, workstations) to developers who need it — without managing infrastructure.

## Monorepo Structure

```
kynetic-ai/
├── apps/
│   └── frontend/              # Next.js + TypeScript + Tailwind
├── services/
│   ├── api_gateway/           # FastAPI — auth check, rate limiting, routing
│   ├── auth_service/          # FastAPI — signup/login, JWT, phone OTP, trust tiers
│   ├── marketplace_service/   # FastAPI — listings, discovery, scheduler
│   ├── wallet_billing_service/# FastAPI — wallet, billing, Stripe/Razorpay
│   ├── provisioning_service/  # FastAPI + Celery — instances, SSH, isolation
│   ├── ai_router_copilot_service/ # FastAPI + LangChain
│   ├── reputation_pricing_service/# FastAPI + Celery + scikit-learn
│   ├── hybrid_broker_service/ # FastAPI + boto3/azure-sdk/google-cloud
│   └── monitoring_service/    # FastAPI + prometheus-client
├── host_agent/                # Python — PyInstaller-packaged agent
├── libs/
│   ├── db_models/             # Shared SQLAlchemy models + Alembic migrations
│   ├── schemas/               # Shared Pydantic schemas
│   └── common/                # structlog config, httpx client, auth deps
├── infra/
│   ├── terraform/
│   ├── k8s/
│   └── docker-compose.yml
├── .github/workflows/         # GitHub Actions CI/CD
└── tests/
```

## Phase 1 — Foundations & Core Platform Skeleton

This phase delivers:
- API Gateway (FastAPI, JWT validation, rate limiting)
- Auth Service (signup/login/refresh/logout, phone OTP stub, roles)
- PostgreSQL schema bootstrap (`users`, `sessions`, `audit_logs`)
- Redis setup (session cache + Celery broker foundation)
- CI/CD pipeline (GitHub Actions — lint, test, migrate)
- Local dev Docker Compose

## Quick Start (Local Dev)

```bash
# Start all services
docker-compose up --build

# Run migrations
docker-compose exec auth_service alembic upgrade head

# Run tests
docker-compose exec auth_service pytest

# Run linter
ruff check .
```

## Tech Stack (Python-First)

| Layer | Technology |
|---|---|
| Backend | FastAPI + Uvicorn/Gunicorn |
| ORM / Migrations | SQLAlchemy 2.0 async + Alembic |
| Database | PostgreSQL |
| Cache / Queue | Redis |
| Auth | FastAPI-Users + python-jose + passlib |
| Testing | pytest + pytest-asyncio |
| Linting | ruff |
| Logging | structlog |
| Frontend | Next.js + TypeScript + Tailwind |
| Infra | Kubernetes + Terraform + Docker Compose |
| CI/CD | GitHub Actions |
