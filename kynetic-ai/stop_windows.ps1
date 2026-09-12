# ==============================================================================
# Kynetic AI — Windows Service Shutdown Script (PowerShell)
# ==============================================================================

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "         KYNETIC AI — WINDOWS SERVICE SHUTDOWN            " -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Stop Docker Compose if running
Write-Host "`n[1/3] Stopping Docker Compose containers..." -ForegroundColor Gray
try {
    docker compose down --remove-orphans
    Write-Host "  [OK] Docker containers stopped." -ForegroundColor Green
} catch {
    Write-Host "  [INFO] Docker compose down skipped." -ForegroundColor Gray
}

# 2. Stop Uvicorn Python processes
Write-Host "`n[2/3] Stopping Uvicorn / Python backend processes..." -ForegroundColor Gray
$uvicornProcesses = Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -like "*uvicorn*" -or $_.CommandLine -like "*services.*"
}
if ($uvicornProcesses) {
    $uvicornProcesses | Stop-Process -Force
    Write-Host "  [OK] Terminated $($uvicornProcesses.Count) Python backend process(es)." -ForegroundColor Green
} else {
    Write-Host "  [INFO] No active Python Uvicorn processes found." -ForegroundColor Gray
}

# 3. Stop Node.js Next.js dev server
Write-Host "`n[3/3] Stopping Node.js frontend servers..." -ForegroundColor Gray
$nodeProcesses = Get-Process -Name "node" -ErrorAction SilentlyContinue
if ($nodeProcesses) {
    $nodeProcesses | Stop-Process -Force
    Write-Host "  [OK] Terminated $($nodeProcesses.Count) Node process(es)." -ForegroundColor Green
} else {
    Write-Host "  [INFO] No active Node processes found." -ForegroundColor Gray
}

# 4. Stop Host Agent
$agentProcesses = Get-Process -Name "kynetic-agent" -ErrorAction SilentlyContinue
if ($agentProcesses) {
    $agentProcesses | Stop-Process -Force
    Write-Host "  [OK] Terminated Host Agent process." -ForegroundColor Green
}

Write-Host "`n[+] All Kynetic AI services stopped cleanly." -ForegroundColor Green
