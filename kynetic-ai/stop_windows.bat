@echo off
REM ==============================================================================
REM Kynetic AI — Windows Batch Service Shutdown
REM ==============================================================================

powershell -ExecutionPolicy Bypass -File "%~dp0stop_windows.ps1"
pause
