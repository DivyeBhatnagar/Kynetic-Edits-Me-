# Kynetic AI — Windows Complete Installation & Execution Guide

> **Official Operating Guide for Windows 10, Windows 11, and Windows Server 2022+**  
> Covers: **1-Click Docker Stack**, **Native Windows Development**, **WSL2 GPU Compute Node Setup**, and **CLI/Agent Tools**.

---

## ⚡ Quick Start Options

Choose the execution mode that best fits your workflow:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              KYNETIC AI ON WINDOWS                                     │
├──────────────────────────┬──────────────────────────┬──────────────────────────────────┤
│ 🐳 Option 1: Docker     │ 💻 Option 2: Native Dev  │ 🚀 Option 3: WSL2 GPU Node       │
│  - Full 14-service stack │  - Next.js UI + FastAPI   │  - NVIDIA GPU Passthrough        │
│  - PostgreSQL + Redis    │  - Lightweight RAM usage │  - KVM Virtualization (/dev/kvm) │
│  - 1-Click Launch        │  - Instant hot-reloading │  - Maximum Compute Performance   │
└──────────────────────────┴──────────────────────────┴──────────────────────────────────┘
```

---

## 📋 System Prerequisites

Before starting, ensure your Windows machine meets the following requirements:

| Component | Minimum | Recommended | Notes |
| :--- | :--- | :--- | :--- |
| **Operating System** | Windows 10 (Build 19041+) | Windows 11 (23H2+) | 64-bit required |
| **CPU** | 4 Cores (x86_64) | 8+ Cores (Intel / AMD) | Virtualization (VT-x/AMD-V) enabled in BIOS |
| **RAM** | 8 GB | 16 GB - 32 GB | Docker / Next.js / Python |
| **GPU (Optional)** | NVIDIA GTX 1060 (6GB) | RTX 3080 / 4090 (16-24GB) | For compute hosting |
| **PowerShell** | PowerShell 5.1 | PowerShell 7+ | Set ExecutionPolicy RemoteSigned |

### Essential Software Checklist
1. **Git for Windows**: [Download Git](https://git-scm.com/download/win)
2. **Python 3.10, 3.11, or 3.12**: [Download Python](https://www.python.org/downloads/windows/) *(Check "Add python.exe to PATH")*
3. **Node.js 18+ (LTS)**: [Download Node.js](https://nodejs.org/)
4. **Go 1.22+** *(Optional, for compiling CLI/Agent)*: [Download Go](https://go.dev/dl/)
5. **Docker Desktop for Windows** *(Optional, for containerized stack)*: [Download Docker Desktop](https://www.docker.com/products/docker-desktop/)

---

## 🛠️ Automated 1-Click Setup (PowerShell)

Open **PowerShell as Administrator** in the `kynetic-ai` root folder:

```powershell
# 1. Enable script execution (if not already enabled)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 2. Run the automated setup wizard
.\setup_windows.ps1
```

This wizard automatically:
- Validates Python, Node, Go, and Docker environments.
- Creates the `.venv` virtual environment and installs all Python requirements.
- Configures default `.env` and `frontend\.env.local` files.
- Installs frontend `npm` dependencies.
- Compiles the native Windows CLI (`kynetic.exe`) and Host Agent daemon (`kynetic-agent.exe`).

---

## 🚀 Execution Methods

---

### Method 1: Full Containerized Stack (Docker Desktop) — Recommended

If you have **Docker Desktop** installed and running:

```powershell
# Start all 14 microservices, Postgres, Redis, Celery workers & Next.js UI
docker compose up --build

# Or run in detached background mode:
docker compose up -d
```

#### Accessing the Services:
- **Next.js Web Portal**: `http://localhost:3000`
- **API Gateway**: `http://localhost:8000`
- **Interactive Swagger Docs**: `http://localhost:8000/docs`
- **Auth Service**: `http://localhost:8001`
- **Host Service**: `http://localhost:8002`
- **Marketplace Service**: `http://localhost:8003`

To stop the Docker stack:
```powershell
docker compose down
```

---

### Method 2: 💻 100% Native Windows Stack (When Docker is NOT Installed)

If you **do not have Docker installed** (or do not want to use Docker Desktop), you can run Kynetic AI completely natively on Windows using Python, Node.js, and the pre-compiled Go executables.

#### 📦 1. Fast Tool Installation via Windows Package Manager (`winget`)
Open **PowerShell as Administrator** and install Python and Node.js with one command (if not already installed):

```powershell
# Install Python 3.11
winget install Python.Python.3.11 --silent

# Install Node.js LTS (includes npm)
winget install OpenJS.NodeJS.LTS --silent

# (Optional) Install PostgreSQL for Windows natively
winget install PostgreSQL.PostgreSQL --silent

# (Optional) Install Redis for Windows (Memurai)
winget install Memurai.Memurai --silent
```
*Note: After installing, close and reopen your PowerShell window so your system `PATH` is refreshed.*

---

#### 🛠️ 2. Run the 1-Click Automated Setup Wizard
In the `kynetic-ai` folder, run:

```powershell
# Enable PowerShell scripts (one-time setup)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Run the automated setup wizard (creates .venv, installs Python & npm dependencies, builds kynetic.exe)
.\setup_windows.ps1
```

---

#### 🚀 3. Start the Native Application Stack

##### Option A: 1-Click PowerShell Launch
```powershell
.\start_windows.ps1 -Mode Native
```

##### Option B: 1-Click Command Prompt (cmd.exe) Launch
Double-click `start_windows.bat` or run:
```cmd
start_windows.bat
```
*(Select **Option 2** for Native Dev Stack)*

---

#### 🖥️ 4. What Gets Started (Native Windows Services):
The launcher automatically initializes:
1. **API Gateway** (`http://localhost:8000`)
2. **Auth Service** (`http://localhost:8001`)
3. **Marketplace Service** (`http://localhost:8003`)
4. **Next.js Web Portal** (`http://localhost:3000`)

#### 🌐 Accessing the Native Web Application:
- **Next.js Developer Portal**: Open your browser at [http://localhost:3000](http://localhost:3000)
- **API Gateway Root**: [http://localhost:8000](http://localhost:8000)
- **Interactive Swagger OpenAPI Explorer**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

#### 🔧 5. Manual Step-by-Step Execution (For Debugging / Individual Terminals)
If you prefer to start each service manually in separate terminal windows:

**Terminal 1 — API Gateway**:
```powershell
# In PowerShell:
$env:PYTHONPATH = "backend;."
.\.venv\Scripts\python.exe -m uvicorn services.api_gateway.main:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal 2 — Auth Service**:
```powershell
# In PowerShell:
$env:PYTHONPATH = "backend;."
.\.venv\Scripts\python.exe -m uvicorn services.auth_service.main:app --host 0.0.0.0 --port 8001 --reload
```

**Terminal 3 — Marketplace Service**:
```powershell
# In PowerShell:
$env:PYTHONPATH = "backend;."
.\.venv\Scripts\python.exe -m uvicorn services.marketplace_service.main:app --host 0.0.0.0 --port 8003 --reload
```

**Terminal 4 — Next.js Frontend Web UI**:
```powershell
cd frontend
npm run dev
```

---

#### 🛑 6. Stopping All Native Services
To cleanly terminate all running backend and frontend processes:
```powershell
.\stop_windows.ps1
```
*(or run `stop_windows.bat` in CMD)*

---

### Method 3: WSL2 (Windows Subsystem for Linux) — For GPU Compute Hosts

For compute node operators running Windows with an NVIDIA GPU (RTX 3090, 4090, A6000), WSL2 provides native Linux kernel performance with full CUDA and KVM support.

#### 1. Enable WSL2 & Install Ubuntu
In PowerShell (as Administrator):
```powershell
wsl --install -d Ubuntu-22.04
```

#### 2. Verify NVIDIA GPU & KVM in WSL2
Open your Ubuntu WSL2 terminal:
```bash
# Check NVIDIA GPU Passthrough
nvidia-smi

# Verify KVM acceleration
ls -l /dev/kvm
```

#### 3. Clone and Run in WSL2
```bash
git clone https://github.com/DivyeBhatnagar/Kynetic-Edits-Me-.git
cd Kynetic-Edits-Me-/kynetic-ai

# Run backend test suite
PYTHONPATH=backend pytest backend/tests/security/

# Compile and run Host Agent daemon
cd backend/host_agent_go
go build -o kynetic-agent ./cmd/agent
./kynetic-agent
```

---

## 💻 Using the Command Line Interface (CLI) on Windows

The native Windows binary `kynetic.exe` is compiled during setup.

```powershell
# View available commands
.\kynetic.exe --help

# Authenticate with the platform
.\kynetic.exe auth login --email user@example.com

# Browse available GPU hardware
.\kynetic.exe marketplace list --gpu "RTX 4090"

# Deploy an instance
.\kynetic.exe instance create --template "vllm-llama3" --gpu "RTX 4090"

# Check active workloads
.\kynetic.exe instance list
```

---

## 🧪 Verification & Test Suites

You can verify that your Windows setup is 100% operational by running the comprehensive security and hardware verification suites:

```powershell
# Run all tests via PowerShell launcher:
.\start_windows.ps1 -Mode Tests
```

Or run manually:
```powershell
# 1. Python Security & Cryptography Suite (64/64 tests)
$env:PYTHONPATH = "backend;."
pytest backend/tests/security -v

# 2. Go Host Agent Suite
cd backend\host_agent_go
go test ./pkg/...
```

---

## 🔧 Troubleshooting Common Windows Issues

### 1. `Set-ExecutionPolicy` Error
**Symptom**: `.\start_windows.ps1 cannot be loaded because running scripts is disabled on this system.`  
**Solution**: Run PowerShell as Administrator and execute:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 2. Port 3000 or 8000 Already in Use
**Symptom**: `Error: listen EADDRINUSE: address already in use :::3000` or `Errno 10048`  
**Solution**: Terminate existing processes on the port or run:
```powershell
.\stop_windows.ps1
```
Or check manually:
```powershell
Get-NetTCPConnection -LocalPort 3000,8000 | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

### 3. Missing `cl.exe` / C++ Compiler Warnings on Python Package Install
**Symptom**: `error: Microsoft Visual C++ 14.0 or greater is required.`  
**Solution**: Pre-compiled wheels are specified in `requirements.txt`. If compiling custom extensions, install [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) (select "Desktop development with C++").

### 4. Docker Desktop WSL2 Engine Not Starting
**Symptom**: `docker: error during connect: In the default daemon configuration on Windows...`  
**Solution**: Open Docker Desktop settings -> General -> Ensure **"Use the WSL 2 based engine"** is checked and restart Docker.

---

## 📞 Support & Community

- **GitHub Issues**: File a ticket on GitHub.
- **Documentation**: Refer to [Docs/Setup/ARCHITECTURE.md](file:///Users/divyebhatnagar/Desktop/KyneticSoftware/kynetic-ai/Docs/Setup/ARCHITECTURE.md) and [Docs/Security/COMPLETE_SECURITY_ARCHITECTURE.md](file:///Users/divyebhatnagar/Desktop/KyneticSoftware/kynetic-ai/Docs/Security/COMPLETE_SECURITY_ARCHITECTURE.md).
- **Security Inquiries**: `security@kynetic.ai`
