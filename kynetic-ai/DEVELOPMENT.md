# Kynetic AI — Developer Setup & Contribution Guide

Welcome to the **Kynetic AI** codebase! This document provides complete instructions for setting up your local environment, cloning the repository, installing dependencies, running backend microservices and the frontend UI, executing database migrations, running tests, and contributing new features.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Repository Setup & Environment Variables](#2-repository-setup--environment-variables)
3. [Python Backend Environment Setup](#3-python-backend-environment-setup)
4. [Frontend Application Setup](#4-frontend-application-setup)
5. [Running the Application](#5-running-the-application)
   - [Option A: Running with Docker Compose (Recommended)](#option-a-running-with-docker-compose-recommended)
   - [Option B: Native Microservice Execution (Fast Local Reload)](#option-b-native-microservice-execution-fast-local-reload)
6. [Database Management & Migrations](#6-database-management--migrations)
7. [Running the Test Suite](#7-running-the-test-suite)
8. [Codebase Architecture & Extension Guide](#8-codebase-architecture--extension-guide)
   - [Adding a New API Route](#adding-a-new-api-route)
   - [Adding a New Database Model & Migration](#adding-a-new-database-model--migration)
   - [Adding a New Frontend Component or Page](#adding-a-new-frontend-component-or-page)
9. [Code Style, Linting & Formatting](#9-code-style-linting--formatting)

---

## 1. Prerequisites

Before you begin, ensure you have the following installed on your host system:

- **Git** (`>= 2.30`)
- **Python** (`3.11` or higher) & `pip`
- **Node.js** (`18.x` or higher) & `npm` / `pnpm`
- **Docker** & **Docker Compose** (`v2.x+`)
- **PostgreSQL** (`v15+` — if running natively outside Docker)
- **Redis** (`v7+` — if running natively outside Docker)

Check your versions:
```bash
python3 --version
node --version
docker --version
docker compose version
```

---

## 2. Repository Setup & Environment Variables

### Step 1: Clone the Repository
```bash
git clone https://github.com/KyneticSoftware/kynetic-ai.git
cd kynetic-ai
```

### Step 2: Configure Environment Variables
Copy `.env.example` to create your local `.env` file:
```bash
cp .env.example .env
```

Review and adjust the default development keys in `.env` if necessary:
```ini
# Environment
ENVIRONMENT=development
LOG_LEVEL=DEBUG

# Database Connection String
DATABASE_URL=postgresql+asyncpg://kynetic:kynetic@localhost:5432/kynetic

# Redis Connections
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# JWT Security
JWT_SECRET_KEY=dev_secret_key_change_in_production_123456789
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15

# Microservice URLs (Internal REST)
AUTH_SERVICE_URL=http://localhost:8001
MARKETPLACE_SERVICE_URL=http://localhost:8002
PROVISIONING_SERVICE_URL=http://localhost:8003
WALLET_BILLING_SERVICE_URL=http://localhost:8004
AI_ROUTER_COPILOT_SERVICE_URL=http://localhost:8005
REPUTATION_PRICING_SERVICE_URL=http://localhost:8006
SECURITY_SERVICE_URL=http://localhost:8007
NOTIFICATIONS_SERVICE_URL=http://localhost:8010
MONITORING_SERVICE_URL=http://localhost:8011
```

---

## 3. Python Backend Environment Setup

We recommend creating a central Python virtual environment for IDE autocompletion, linting, and local test execution.

### Step 1: Create and Activate Virtual Environment
```bash
# Create virtual environment
python3 -m venv venv

# Activate on macOS/Linux:
source venv/bin/activate

# Activate on Windows (PowerShell):
# .\venv\Scripts\Activate.ps1
```

### Step 2: Install Core Python Dependencies
```bash
# Upgrade pip and setuptools
pip install --upgrade pip setuptools

# Install root dependencies and shared modules in editable mode
pip install -r requirements.txt 2>/dev/null || pip install fastapi uvicorn sqlalchemy asyncpg alembic redis celery pydantic pydantic-settings structlog python-jose passlib bcrypt httpx pytest pytest-asyncio prometheus-client scikit-learn pandas
```

---

## 4. Frontend Application Setup

The user interface is built with **Next.js 14**, **TypeScript**, and **Tailwind CSS**.

```bash
# Navigate to the frontend directory
cd apps/frontend

# Install dependencies
npm install

# Return to root directory
cd ../..
```

---

## 5. Running the Application

### Option A: Running with Docker Compose (Recommended)

This spins up PostgreSQL, Redis, Prometheus, Grafana, and all microservices simultaneously.

```bash
# Build and start all services in detached mode
docker-compose up --build -d

# Check service container status
docker-compose ps

# Tail logs for all services
docker-compose logs -f

# Tail logs for a specific service (e.g., wallet_billing_service)
docker-compose logs -f wallet_billing_service
```

Access ports:
- **API Gateway**: `http://localhost:8000` (OpenAPI Docs: `http://localhost:8000/docs`)
- **Frontend App**: `http://localhost:3000` or `http://localhost:3001`
- **Prometheus UI**: `http://localhost:9090`
- **Grafana UI**: `http://localhost:3000` (admin/admin, if monitoring compose is up)

To shut down containers:
```bash
docker-compose down
```

---

### Option B: Native Microservice Execution (Fast Local Reload)

If you are developing a specific microservice and want instantaneous live reload on file save without waiting for Docker builds:

#### 1. Start Infrastructure Dependencies (Postgres + Redis)
```bash
docker-compose up -d postgres redis
```

#### 2. Run Database Migrations
```bash
alembic upgrade head
```

#### 3. Run Individual Microservices with Uvicorn
Open separate terminal tabs for the services you are working on:

```bash
# Terminal 1: API Gateway (Port 8000)
uvicorn services.api_gateway.main:app --reload --port 8000

# Terminal 2: Auth Service (Port 8001)
uvicorn services.auth_service.main:app --reload --port 8001

# Terminal 3: Wallet & Billing Service (Port 8004)
uvicorn services.wallet_billing_service.main:app --reload --port 8004

# Terminal 4: Notifications Service (Port 8010)
uvicorn services.notifications_service.main:app --reload --port 8010

# Terminal 5: Monitoring Service (Port 8011)
uvicorn services.monitoring_service.main:app --reload --port 8011

# Terminal 6: Frontend App (Port 3000)
cd apps/frontend && npm run dev
```

---

## 6. Database Management & Migrations

Database schema changes are managed via **Alembic** and **SQLAlchemy 2.0 Async**.

### Running Pending Migrations
```bash
# Apply all unapplied migrations to the database
alembic upgrade head
```

### Creating a New Migration
When you modify or add models in `libs/db_models/`:

```bash
# Generate a new auto-detected migration script
alembic revision --autogenerate -m "add_new_feature_table"

# Review the generated file in libs/db_models/migrations/versions/
# Then apply it:
alembic upgrade head
```

### Rolling Back Migrations
```bash
# Roll back the last applied migration
alembic downgrade -1
```

---

## 7. Running the Test Suite

We use `pytest` for backend unit and integration testing.

```bash
# Run all tests
python3 -m pytest

# Run specific Phase 10 billing and notifications tests (No DB required):
python3 -m pytest tests/wallet_billing_service/test_razorpay.py tests/notifications_service/test_notifications.py -v

# Run with verbose output and short traceback
python3 -m pytest -v --tb=short
```

---

## 8. Codebase Architecture & Extension Guide

### Monorepo Layout Quick Reference
- **`services/`**: Independent FastAPI microservices. Each service contains `main.py`, `routes.py`, `schemas.py`, `config.py`, and optional `tasks.py`.
- **`libs/db_models/`**: Central SQLAlchemy ORM model definitions shared across microservices.
- **`libs/schemas/`**: Shared Pydantic request/response validation models.
- **`libs/common/`**: Shared middleware, `structlog` logging, `httpx` async clients, and settings loaders.
- **`apps/frontend/`**: Next.js App Router application (`app/`, `components/`, `lib/api.ts`).

---

### Adding a New API Route

1. Open `services/<target_service>/routes.py`.
2. Add your endpoint function using standard FastAPI decorators:

```python
from fastapi import APIRouter, Depends, HTTPException, status
from libs.schemas.my_schema import MyRequestSchema, MyResponseSchema

router = APIRouter(prefix="/my-feature", tags=["My Feature"])

@router.post("/", response_model=MyResponseSchema)
async def create_my_feature(payload: MyRequestSchema):
    # Business logic here
    return {"id": "123", "status": "created"}
```

3. If exposing through the **API Gateway**, update `services/api_gateway/main.py` or route configuration to forward incoming requests.

---

### Adding a New Database Model & Migration

1. Define your SQLAlchemy model in `libs/db_models/` (e.g., `libs/db_models/my_model.py` or an existing file):

```python
from sqlalchemy import Column, String, DateTime, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime, timezone
from libs.db_models.database import Base

class MyNewTable(Base):
    __tablename__ = "my_new_table"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
```

2. Export the new model in `libs/db_models/__init__.py` so Alembic detects it.
3. Generate and run the migration:
```bash
alembic revision --autogenerate -m "create_my_new_table"
alembic upgrade head
```

---

### Adding a New Frontend Component or Page

1. **API Client Method**: Add the backend API call method to `apps/frontend/lib/api.ts`:
```typescript
export const myFeatureApi = {
  getFeature: async (id: string) => {
    const res = await fetch(`${API_BASE_URL}/my-feature/${id}`, {
      headers: getAuthHeaders(),
    });
    if (!res.ok) throw new Error("Failed to fetch feature");
    return res.json();
  },
};
```

2. **UI Page**: Create a new page under `apps/frontend/app/my-feature/page.tsx`:
```tsx
"use client";
import React, { useEffect, useState } from "react";
import { myFeatureApi } from "@/lib/api";

export default function MyFeaturePage() {
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    myFeatureApi.getFeature("123").then(setData).catch(console.error);
  }, []);

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold text-white mb-4">My Feature</h1>
      {data ? <pre>{JSON.stringify(data, null, 2)}</pre> : <p>Loading...</p>}
    </div>
  );
}
```

---

## 9. Code Style, Linting & Formatting

We use **Ruff** for Python linting and code formatting.

```bash
# Run Ruff lint check
ruff check .

# Fix auto-fixable lint issues
ruff check . --fix

# Format code
ruff format .
```

### Git Commit Guidelines
- Keep commit messages concise and descriptive (e.g., `feat(wallet): add razorpay upi payment route`).
- Ensure all tests pass (`python3 -m pytest`) before committing or opening a pull request.
