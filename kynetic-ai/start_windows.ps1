# ==============================================================================
# Kynetic AI — Master Windows Application Launcher (PowerShell)
# ==============================================================================
# Usage:
#   .\start_windows.ps1               # Interactive launcher menu
#   .\start_windows.ps1 -Mode Docker  # Direct Docker stack launch
#   .\start_windows.ps1 -Mode Native  # Direct Native Python/Node stack launch
#   .\start_windows.ps1 -Mode Agent   # Run Go Host Agent daemon
#   .\start_windows.ps1 -Mode Tests   # Run Security & Verification test suites
# ==============================================================================

[CmdletBinding()]
param (
    [ValidateSet("Interactive", "Docker", "Native", "Agent", "Frontend", "Tests")]
    [string]$Mode = "Interactive"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

function Show-Banner {
    Write-Host "==========================================================" -ForegroundColor Cyan
    Write-Host "          KYNETIC AI — WINDOWS LAUNCH CONTROL             " -ForegroundColor Green
    Write-Host "==========================================================" -ForegroundColor Cyan
}

function Start-DockerStack {
    # Check if Docker CLI is installed and engine is reachable
    $dockerInstalled = $false
    try {
        $dockerCheck = docker --version 2>&1
        if ($LASTEXITCODE -eq 0 -or $dockerCheck -like "*Docker version*") {
            $dockerInstalled = $true
        }
    } catch {
        $dockerInstalled = $false
    }

    if (-not $dockerInstalled) {
        Write-Host "`n[!] Docker is NOT installed on this machine." -ForegroundColor Red
        Write-Host "    No problem! Kynetic AI can run 100% natively on Windows without Docker." -ForegroundColor Yellow
        Write-Host "    Switching automatically to Native Windows Mode...`n" -ForegroundColor Green
        Start-NativeStack
        return
    }

    # Verify if Docker daemon is running
    try {
        docker info 2>&1 | Out-Null
    } catch {
        Write-Host "`n[!] Docker Desktop is installed but the Docker daemon is not running." -ForegroundColor Yellow
        Write-Host "    Please start Docker Desktop, or press ENTER to run in Native Windows Mode (No Docker)." -ForegroundColor DarkYellow
        $fallback = Read-Host "Run Native Mode without Docker? (Y/n)"
        if ($fallback -ne "n" -and $fallback -ne "N") {
            Start-NativeStack
            return
        }
    }

    Write-Host "`n[*] Starting Kynetic AI via Docker Compose..." -ForegroundColor Yellow
    docker compose up --build
}

function Start-NativeStack {
    Write-Host "`n==========================================================" -ForegroundColor Cyan
    Write-Host "   [*] STARTING KYNETIC AI NATIVE STACK (NO DOCKER)      " -ForegroundColor Green
    Write-Host "==========================================================" -ForegroundColor Cyan
    
    $venvPython = Join-Path $ScriptDir ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        Write-Host "  [.venv] Python virtual environment not found. Running setup..." -ForegroundColor Gray
        & "$ScriptDir\setup_windows.ps1" -SkipGoBuild
        $venvPython = Join-Path $ScriptDir ".venv\Scripts\python.exe"
        if (-not (Test-Path $venvPython)) {
            $venvPython = "python"
        }
    }

    # Set PYTHONPATH
    $env:PYTHONPATH = "$ScriptDir\backend;$ScriptDir"

    Write-Host "  [1/4] Launching API Gateway (http://localhost:8000)..." -ForegroundColor Cyan
    Start-Process -FilePath $venvPython -ArgumentList "-m uvicorn services.api_gateway.main:app --host 0.0.0.0 --port 8000 --reload" -WorkingDirectory "$ScriptDir\backend" -WindowStyle Normal

    Write-Host "  [2/4] Launching Auth Service (http://localhost:8001)..." -ForegroundColor Cyan
    Start-Process -FilePath $venvPython -ArgumentList "-m uvicorn services.auth_service.main:app --host 0.0.0.0 --port 8001 --reload" -WorkingDirectory "$ScriptDir\backend" -WindowStyle Normal

    Write-Host "  [3/4] Launching Marketplace Service (http://localhost:8003)..." -ForegroundColor Cyan
    Start-Process -FilePath $venvPython -ArgumentList "-m uvicorn services.marketplace_service.main:app --host 0.0.0.0 --port 8003 --reload" -WorkingDirectory "$ScriptDir\backend" -WindowStyle Normal

    Write-Host "  [4/4] Launching Next.js Frontend (http://localhost:3000)..." -ForegroundColor Cyan
    $frontDir = Join-Path $ScriptDir "frontend"
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c npm run dev" -WorkingDirectory $frontDir -WindowStyle Normal

    Write-Host "`n==========================================================" -ForegroundColor Green
    Write-Host "      [+] ALL NATIVE SERVICES STARTED SUCCESSFULLY!      " -ForegroundColor Green
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host "  🌐 Next.js Web UI:       http://localhost:3000" -ForegroundColor White
    Write-Host "  🛡️ API Gateway:          http://localhost:8000" -ForegroundColor White
    Write-Host "  📖 Interactive Docs:     http://localhost:8000/docs" -ForegroundColor White
    Write-Host "  🔐 Auth Service API:     http://localhost:8001" -ForegroundColor White
    Write-Host "  🛒 Marketplace Service:  http://localhost:8003" -ForegroundColor White
    Write-Host "`n💡 To stop all native services at once, run: .\stop_windows.ps1" -ForegroundColor Yellow
}

function Start-HostAgent {
    Write-Host "`n[*] Launching Kynetic Host Agent Daemon (Windows Native)..." -ForegroundColor Yellow
    $agentExe = Join-Path $ScriptDir "kynetic-agent.exe"
    if (Test-Path $agentExe) {
        & "$agentExe"
    } else {
        Write-Host "  kynetic-agent.exe not found. Compiling from backend\host_agent_go..." -ForegroundColor Gray
        Push-Location "$ScriptDir\backend\host_agent_go"
        go build -o "$agentExe" ./cmd/agent
        Pop-Location
        & "$agentExe"
    }
}

function Start-FrontendOnly {
    Write-Host "`n[*] Launching Next.js Frontend on http://localhost:3000..." -ForegroundColor Yellow
    Push-Location "$ScriptDir\frontend"
    npm run dev
    Pop-Location
}

function Run-Tests {
    Write-Host "`n[*] Running Full Kynetic Verification Suite..." -ForegroundColor Yellow
    $venvPython = Join-Path $ScriptDir ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        $venvPython = "python"
    }
    
    $env:PYTHONPATH = "$ScriptDir\backend;$ScriptDir"
    
    Write-Host "`n--- [1/2] Python Security & Cryptography Suite (64+ tests) ---" -ForegroundColor Cyan
    & "$venvPython" -m pytest "$ScriptDir\backend\tests\security" -v
    
    Write-Host "`n--- [2/2] Go Host Agent & Hardware Armor Suite ---" -ForegroundColor Cyan
    Push-Location "$ScriptDir\backend\host_agent_go"
    go test ./pkg/...
    Pop-Location
    
    Write-Host "`n[+] All tests completed!" -ForegroundColor Green
}

# --- Execution Router ---
Show-Banner

if ($Mode -eq "Interactive") {
    Write-Host "Select execution mode:" -ForegroundColor Yellow
    Write-Host "  [1] Full Stack via Docker Compose (Recommended)" -ForegroundColor White
    Write-Host "  [2] Native Dev Stack (FastAPI Gateway + Next.js UI)" -ForegroundColor White
    Write-Host "  [3] Compute Host Agent Daemon (kynetic-agent.exe)" -ForegroundColor White
    Write-Host "  [4] Frontend Only (Next.js Port 3000)" -ForegroundColor White
    Write-Host "  [5] Run Verification Test Suite" -ForegroundColor White
    Write-Host "  [6] Exit" -ForegroundColor Gray
    
    $choice = Read-Host "`nEnter selection (1-6)"
    switch ($choice) {
        "1" { Start-DockerStack }
        "2" { Start-NativeStack }
        "3" { Start-HostAgent }
        "4" { Start-FrontendOnly }
        "5" { Run-Tests }
        default { Write-Host "Exiting." -ForegroundColor Gray }
    }
} else {
    switch ($Mode) {
        "Docker"   { Start-DockerStack }
        "Native"   { Start-NativeStack }
        "Agent"    { Start-HostAgent }
        "Frontend" { Start-FrontendOnly }
        "Tests"    { Run-Tests }
    }
}
