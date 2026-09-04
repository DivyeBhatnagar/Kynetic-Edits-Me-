# Kynetic AI — Complete Installation & Setup Guide

This guide walks you through setting up a complete Kynetic AI development environment from scratch on macOS, Linux, or Windows (WSL2).

---

## 1. Prerequisites

Ensure your development machine satisfies the following hardware and software requirements:

### Software Requirements
- **Git** (`>= 2.30`)
- **Python** (`3.11` or higher) & `pip`
- **Go** (`1.22+`) — for Go CLI and Go Host Agent daemon
- **Node.js** (`18.x` or higher) & `npm` / `pnpm`
- **Docker Engine** & **Docker Compose** (`v2.x+`)
- **PostgreSQL** (`v15+` — if running natively outside Docker)
- **Redis** (`v7+` — if running natively outside Docker)

Install Go on macOS:
```bash
brew install go
go version   # Output: go version go1.22+ darwin/arm64
```

### System Verification
```bash
python3 --version   # Output: Python 3.11.x or 3.12.x
node --version      # Output: v18.x.x or v20.x.x
docker --version    # Output: Docker version 24.x+
go version          # Output: go version go1.22+
```

> **Security & Permissions Note:** For a detailed breakdown of user RBAC scopes, LUKS2 RAM encryption, Seccomp/AppArmor policies, and host system capability bounds, refer to [`PERMISSIONS_AND_SECURITY.md`](file:///Users/divyebhatnagar/Desktop/KyneticSoftware/kynetic-ai/Docs/Setup/PERMISSIONS_AND_SECURITY.md).

---

## 2. Cloning the Repository & Environment Setup

```bash
# Clone the repository
git clone https://github.com/KyneticSoftware/kynetic-ai.git
cd KyneticSoftware

# Copy sample environment configuration
cp kynetic-ai/.env.example kynetic-ai/.env
```

---

## 3. Python Backend Environment Setup

```bash
cd kynetic-ai

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On macOS / Linux:
source venv/bin/activate
# On Windows (PowerShell):
# .\venv\Scripts\Activate.ps1

# Install all backend dependencies in editable mode
pip install --upgrade pip
pip install -e .
pip install pytest ruff black mypy
```

---

## 4. Frontend Application Setup (Next.js 16)

```bash
# Setup Public Developer, Host & Admin Web Application
cd frontend
npm install
```

---

## 5. Running the Application Stack

### Option A: Running with Docker Compose (Recommended — All 11 Services)

```bash
cd kynetic-ai

# Build and start all microservices, PostgreSQL, and Redis in background
docker-compose up --build -d

# Verify all containers are running cleanly
docker-compose ps

# Apply database migrations
docker-compose exec auth_service alembic upgrade head
```

The services will be accessible at:
- **API Gateway**: `http://localhost:8000`
- **Developer Web Portal**: `http://localhost:3000`
- **Admin Operations Console**: `http://localhost:3001`
- **Prometheus Monitoring**: `http://localhost:9090`
- **Grafana Dashboards**: `http://localhost:3002`

### Option B: Running Individual Services Natively

```bash
# Terminal 1: Auth Service
cd kynetic-ai/services/auth_service
python -m uvicorn app:app --port 8001 --reload

# Terminal 2: Provisioning Service
cd kynetic-ai/services/provisioning_service
python -m uvicorn app:app --port 8003 --reload
```

---

## 6. Running the Test Suite

Validate your local installation by running the full 88-test unit and integration suite:

```bash
cd kynetic-ai

# Run all unit tests (82 tests)
python3 -m pytest tests/unit/ -v

# Run all integration tests (6 tests)
python3 -m pytest tests/integration/ -v

# Run complete test suite (88 tests)
python3 -m pytest tests/unit/ tests/integration/ -v
```

---

## 7. Go CLI — Build & Install

The Go CLI replaces the Python Click CLI with a zero-dependency static binary:

```bash
cd kynetic-ai/cli_go

# Download dependencies
go mod tidy

# Build (fast: ~3s)
go build -ldflags="-w -s" -o kynetic .

# Install globally
sudo mv kynetic /usr/local/bin/

# Test
kynetic --help
kynetic version
kynetic launch --gpu "RTX 4090" --yes
```

---

## 8. Go Host Agent — Build & Install (Hardware Providers)

Hardware provider nodes now run the Go host agent daemon:

```bash
cd kynetic-ai/backend/host_agent_go

# Download dependencies
go mod tidy

# Dev build (no NVML — works on macOS)
go build -o kynetic-agent ./cmd/agent/

# Production build (Linux + NVIDIA GPU, requires NVML headers)
CGO_ENABLED=1 go build -tags nvml -ldflags="-w -s" -o kynetic-agent ./cmd/agent/

# Install & enable
sudo mv kynetic-agent /usr/local/bin/
sudo systemctl enable --now kynetic-agent

# Health check
curl http://localhost:8080/healthz
```

### Footprint Verification
```bash
# Measure Go host agent footprint
ls -lh /usr/local/bin/kynetic-agent   # ~14 MB
ps aux | grep kynetic-agent            # ~10 MB RSS at idle

# Legacy Python footprint profiler (reference)
python3 backend/host_agent/scripts/profile_footprint.py
```
