@echo off
cd /d "%~dp0electron_frontend"

echo [JARVIS] Starting in development mode...
echo [JARVIS] Vite dev server + Electron with hot reload
echo.

where node >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo ERROR: Node.js not found. Please install Node.js.
    pause
    exit /b 1
)

echo [JARVIS] Starting Vite + Electron concurrently...
call npx concurrently "npx vite" "npx wait-on http://localhost:5173 && npx electron ."

pause
