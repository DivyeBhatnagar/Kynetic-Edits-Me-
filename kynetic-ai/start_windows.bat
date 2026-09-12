@echo off
REM ==============================================================================
REM Kynetic AI — Windows Batch Quick Launcher
REM ==============================================================================

setlocal
cd /d "%~dp0"

echo ==========================================================
echo          KYNETIC AI — WINDOWS LAUNCH CONTROL             
echo ==========================================================
echo.
echo Select execution mode:
echo   [1] Full Stack via Docker Compose
echo   [2] Native Dev Stack (FastAPI Gateway + Next.js UI)
echo   [3] Host Agent Daemon (kynetic-agent.exe)
echo   [4] Run Verification Test Suite
echo   [5] Automated Setup (First time run)
echo   [6] Exit
echo.

set /p choice="Enter selection (1-6): "

if "%choice%"=="1" goto docker
if "%choice%"=="2" goto native
if "%choice%"=="3" goto agent
if "%choice%"=="4" goto tests
if "%choice%"=="5" goto setup
if "%choice%"=="6" goto exit
goto exit

:docker
echo.
echo [*] Starting Docker Compose stack...
docker compose up --build
goto exit

:native
echo.
echo [*] Launching Native Windows Stack via PowerShell...
powershell -ExecutionPolicy Bypass -File .\start_windows.ps1 -Mode Native
goto exit

:agent
echo.
echo [*] Launching Host Agent Daemon...
powershell -ExecutionPolicy Bypass -File .\start_windows.ps1 -Mode Agent
goto exit

:tests
echo.
echo [*] Running Test Suites...
powershell -ExecutionPolicy Bypass -File .\start_windows.ps1 -Mode Tests
goto exit

:setup
echo.
echo [*] Running Setup Wizard...
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1
goto exit

:exit
endlocal
