# Kynetic AI — Complete Installation & Setup Guide

This guide walks you through setting up a complete Kynetic AI development environment from scratch on macOS, Linux, or Windows (WSL2).

---

## 1. Prerequisites

Ensure your development machine satisfies the following hardware and software requirements:

### Software Requirements

> [!NOTE]
> **Zero Docker Desktop Requirement for Users & Hosts**:
> - **End Users (Developers)**: Require **zero Docker**. You only need the standalone Go CLI binary (`kynetic`).
> - **Compute Hosts**: Require **zero Docker Desktop**. The Go Host Agent runs natively via systemd with Firecracker microVMs and standalone `containerd`.
> - **Backend Cloud Developers**: Docker / Docker Compose is **optional** for running the full local 11-microservice stack. You can also run services natively with Python.

- **Git** (`>= 2.30`)
- **Python** (`3.11` or higher) & `pip` (for backend control plane services)
- **Go** (`1.22+`) — for Go CLI and Go Host Agent daemon
- **Node.js** (`18.x` or higher) & `npm` / `pnpm` (for web frontend)
- **PostgreSQL 16+ & Redis 7+** (native or via optional Docker)
- **Docker Engine / Compose** (*Optional* — only for local multi-service container orchestration)

Install Go on macOS:
```bash
brew install go
go version   # Output: go version go1.22+ darwin/arm64
```

### System Verification
```bash
python3 --version   # Output: Python 3.11.x or 3.12.x
node --version      # Output: v18.x.x or v20.x.x
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

### Option A: Running with Docker Compose (All Services + Web UI)

```bash
cd kynetic-ai

# Build and start all microservices, PostgreSQL, Redis, and Next.js frontend
docker compose up --build
```

The services will be accessible at:
- **Developer Web Portal**: `http://localhost:3000`
- **API Gateway**: `http://localhost:8000`
- **Interactive Swagger Docs**: `http://localhost:8000/docs`
- **Auth Service**: `http://localhost:8001`
- **Marketplace Service**: `http://localhost:8003`

---

### Option B: Running on Windows Natively (1-Click & No Docker Required)

On Windows 10/11:
```powershell
# 1. Run automated setup wizard (PowerShell as Administrator)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\setup_windows.ps1

# 2. Launch native stack (No Docker required)
.\start_windows.ps1 -Mode Native

# Or double-click start_windows.bat in Windows Command Prompt
```
👉 *See the exhaustive [Windows Installation & Execution Guide](WINDOWS_SETUP_AND_RUN_GUIDE.md) for winget one-liners and WSL2 GPU compute host instructions.*

---

### Option C: Running Individual Services Natively (macOS / Linux)

```bash
# Terminal 1: API Gateway
PYTHONPATH=backend:. python3 -m uvicorn services.api_gateway.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2: Auth Service
PYTHONPATH=backend:. python3 -m uvicorn services.auth_service.main:app --host 0.0.0.0 --port 8001 --reload

# Terminal 3: Next.js Frontend
cd frontend && npm run dev
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
