@echo off
cd /d "%~dp0electron_frontend"

echo [JARVIS] Starting Electron + React frontend...
echo [JARVIS] Backend will be auto-started by Electron on port 11711
echo.

REM Check if node is available
where node >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo ERROR: Node.js not found. Please install Node.js.
    pause
    exit /b 1
)

REM Build the frontend first
echo [JARVIS] Building frontend...
call npx vite build
if %ERRORLEVEL% neq 0 (
    echo ERROR: Frontend build failed.
    pause
    exit /b 1
)

REM Launch Electron with the built frontend
echo [JARVIS] Launching application...
call npx electron .

echo.
