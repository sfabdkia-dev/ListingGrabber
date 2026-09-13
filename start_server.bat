@echo off
REM Starts the local capture server in its own window.

REM 1. Kill any existing capture server to free port 9999.
taskkill /F /FI "WINDOWTITLE eq Capture Server" >nul 2>&1

REM 2. Start the capture server in a new PowerShell window (stays open).
start "Capture Server" powershell -NoExit -Command ^
  "Set-Location '%~dp0'; python server/capture_server.py"

exit
