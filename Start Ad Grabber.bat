@echo off
REM Starts the local capture server in its own window,
REM then launches the throwaway Chrome profile with the Ad Grabber extension.

REM 1. Start the capture server in a new PowerShell window (stays open).
start "Capture Server" powershell -NoExit -Command ^
  "python 'C:\Users\saeed\My Windows Feature Expansion Project\Facebook MarketPlace ad parser\Capture_server.py'"

REM 2. Give the server a moment to bind to port 9999.
timeout /t 2 /nobreak >nul

REM 3. Launch the throwaway Chrome profile.
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir="C:\tmp\mitm-chrome"

exit
