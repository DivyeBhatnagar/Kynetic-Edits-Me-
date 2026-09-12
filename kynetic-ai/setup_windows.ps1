# ==============================================================================
# Kynetic AI — Automated Windows Setup Script (PowerShell)
# ==============================================================================
# This script sets up the entire Kynetic AI development & production environment
# natively on Windows 10/11 or Windows Server.
#
# Prerequisites:
#   - Windows 10/11 (64-bit) or Windows Server 2022+
#   - PowerShell 5.1+ or PowerShell 7+
#   - Python 3.10+ (added to PATH)
#   - Node.js 18+ & npm (added to PATH)
#   - Go 1.22+ (added to PATH, optional for building CLI/Agent)
#   - Docker Desktop for Windows (optional for full containerized stack)
# ==============================================================================

[CmdletBinding()]
param (
    [switch]$SkipFrontend,
    [switch]$SkipGoBuild,
    [switch]$ForceVenv
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "        KYNETIC AI — WINDOWS SETUP & BUILD WIZARD        " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Working Directory: $ScriptDir" -ForegroundColor Gray

# ------------------------------------------------------------------------------
# 1. Verify Prerequisites
# ------------------------------------------------------------------------------
Write-Host "`n[1/5] Verifying System Prerequisites..." -ForegroundColor Yellow

# Python Check
try {
    $pythonVersion = python --version 2>&1
    Write-Host "  [OK] Python: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "  [ERROR] Python is not installed or not in PATH." -ForegroundColor Red
    Write-Host "          Download from https://www.python.org/downloads/ (Check 'Add python.exe to PATH')" -ForegroundColor DarkYellow
    exit 1
}

# Node.js Check
try {
    $nodeVersion = node --version 2>&1
    $npmVersion = npm --version 2>&1
    Write-Host "  [OK] Node.js: $nodeVersion (npm: $npmVersion)" -ForegroundColor Green
} catch {
    Write-Host "  [WARN] Node.js / npm not detected. Frontend build might fail." -ForegroundColor Yellow
}

# Go Check
try {
    $goVersion = go version 2>&1
    Write-Host "  [OK] Go: $goVersion" -ForegroundColor Green
} catch {
    Write-Host "  [INFO] Go compiler not detected. Pre-compiled binaries will be used if present." -ForegroundColor Gray
}

# Docker Check
try {
    $dockerVersion = docker --version 2>&1
    Write-Host "  [OK] Docker: $dockerVersion" -ForegroundColor Green
} catch {
    Write-Host "  [INFO] Docker Desktop not running/installed. Native Python execution will be used." -ForegroundColor Gray
}

# ------------------------------------------------------------------------------
# 2. Python Virtual Environment & Dependencies
# ------------------------------------------------------------------------------
Write-Host "`n[2/5] Setting up Python Virtual Environment (.venv)..." -ForegroundColor Yellow

$venvPath = Join-Path $ScriptDir ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"
$venvPip = Join-Path $venvPath "Scripts\pip.exe"

if ($ForceVenv -or -not (Test-Path $venvPython)) {
    Write-Host "  Creating fresh virtual environment in .venv..." -ForegroundColor Gray
    python -m venv "$venvPath"
} else {
    Write-Host "  Existing .venv found. Re-using..." -ForegroundColor Gray
}

Write-Host "  Upgrading pip, setuptools, wheel..." -ForegroundColor Gray
& "$venvPython" -m pip install --upgrade pip setuptools wheel --quiet

Write-Host "  Installing backend requirements & dependencies..." -ForegroundColor Gray
$reqFile = Join-Path $ScriptDir "backend\requirements.txt"
if (Test-Path $reqFile) {
    & "$venvPip" install -r "$reqFile" --quiet
} else {
    & "$venvPip" install fastapi uvicorn sqlalchemy asyncpg psycopg2-binary redis pydantic pydantic-settings httpx structlog python-jose cryptography pytest pytest-asyncio anyio --quiet
}

# Install CLI in editable mode
$cliDir = Join-Path $ScriptDir "cli"
if (Test-Path (Join-Path $cliDir "pyproject.toml")) {
    Write-Host "  Installing Python kynetic-cli..." -ForegroundColor Gray
    & "$venvPip" install -e "$cliDir" --quiet
}

Write-Host "  [OK] Python environment configured successfully." -ForegroundColor Green

# ------------------------------------------------------------------------------
# 3. Environment Configuration Files
# ------------------------------------------------------------------------------
Write-Host "`n[3/5] Configuring Environment Variables (.env)..." -ForegroundColor Yellow

$envFile = Join-Path $ScriptDir ".env"
$envExample = Join-Path $ScriptDir "backend\.env.example"

if (-not (Test-Path $envFile)) {
    if (Test-Path $envExample) {
        Copy-Item $envExample $envFile
        Write-Host "  Created .env from backend\.env.example" -ForegroundColor Green
    } else {
        Set-Content -Path $envFile -Value @"
ENVIRONMENT=development
LOG_LEVEL=INFO
JWT_SECRET_KEY=dev_secret_windows_kynetic_key_987654321
DATABASE_URL=postgresql+asyncpg://kynetic:kynetic@localhost:5432/kynetic
REDIS_URL=redis://localhost:6379/0
API_GATEWAY_PORT=8000
"@
        Write-Host "  Created default development .env" -ForegroundColor Green
    }
} else {
    Write-Host "  .env configuration file already exists." -ForegroundColor Gray
}

# Frontend .env.local
$frontEnv = Join-Path $ScriptDir "frontend\.env.local"
if (-not (Test-Path $frontEnv)) {
    Set-Content -Path $frontEnv -Value "NEXT_PUBLIC_API_URL=http://localhost:8000`n"
    Write-Host "  Created frontend\.env.local" -ForegroundColor Green
}

# ------------------------------------------------------------------------------
# 4. Frontend Node Dependencies
# ------------------------------------------------------------------------------
if (-not $SkipFrontend) {
    Write-Host "`n[4/5] Installing Frontend Dependencies (npm install)..." -ForegroundColor Yellow
    $frontDir = Join-Path $ScriptDir "frontend"
    if (Test-Path (Join-Path $frontDir "package.json")) {
        Push-Location $frontDir
        try {
            npm install --quiet
            Write-Host "  [OK] Frontend dependencies installed successfully." -ForegroundColor Green
        } catch {
            Write-Host "  [WARN] npm install encountered warnings: $_" -ForegroundColor Yellow
        } finally {
            Pop-Location
        }
    }
} else {
    Write-Host "`n[4/5] Skipping Frontend setup (-SkipFrontend flag specified)." -ForegroundColor Gray
}

# ------------------------------------------------------------------------------
# 5. Compile Go CLI & Host Agent for Windows
# ------------------------------------------------------------------------------
if (-not $SkipGoBuild) {
    Write-Host "`n[5/5] Compiling Native Windows Binaries (Go)..." -ForegroundColor Yellow
    
    # Compile Go CLI (kynetic.exe)
    $cliGoDir = Join-Path $ScriptDir "cli_go"
    if (Test-Path (Join-Path $cliGoDir "main.go")) {
        Push-Location $cliGoDir
        try {
            $cliOut = Join-Path $ScriptDir "kynetic.exe"
            go build -o "$cliOut" .
            Write-Host "  [OK] Compiled CLI: $cliOut" -ForegroundColor Green
        } catch {
            Write-Host "  [WARN] Could not compile Go CLI: $_" -ForegroundColor Yellow
        } finally {
            Pop-Location
        }
    }

    # Compile Go Host Agent (kynetic-agent.exe)
    $agentGoDir = Join-Path $ScriptDir "backend\host_agent_go"
    if (Test-Path (Join-Path $agentGoDir "cmd\agent\main.go")) {
        Push-Location $agentGoDir
        try {
            $agentOut = Join-Path $ScriptDir "kynetic-agent.exe"
            go build -o "$agentOut" ./cmd/agent
            Write-Host "  [OK] Compiled Host Agent: $agentOut" -ForegroundColor Green
        } catch {
            Write-Host "  [WARN] Could not compile Go Host Agent: $_" -ForegroundColor Yellow
        } finally {
            Pop-Location
        }
    }
} else {
    Write-Host "`n[5/5] Skipping Go binary compilation (-SkipGoBuild flag specified)." -ForegroundColor Gray
}

# ------------------------------------------------------------------------------
# Summary & Next Steps
# ------------------------------------------------------------------------------
Write-Host "`n==========================================================" -ForegroundColor Cyan
Write-Host "            KYNETIC AI SETUP COMPLETE!                  " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Quick Launch Commands:" -ForegroundColor Yellow
Write-Host "  1. Full Stack (Docker):     docker compose up --build" -ForegroundColor White
Write-Host "  2. Interactive Launcher:    .\start_windows.ps1" -ForegroundColor White
Write-Host "  3. Host Agent Daemon:       .\kynetic-agent.exe" -ForegroundColor White
Write-Host "  4. Go CLI:                  .\kynetic.exe --help" -ForegroundColor White
Write-Host "  5. Next.js Frontend:        cd frontend && npm run dev" -ForegroundColor White
Write-Host ""
