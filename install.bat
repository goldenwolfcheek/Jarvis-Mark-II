@echo off
cd /d "%~dp0"

title Jarvis Mark II — Installer

echo ============================================
echo    Jarvis Mark II — Installation
echo ============================================
echo.
echo This script will install all dependencies
echo needed to run Jarvis Mark II.
echo.

REM ─── Step 1: Check Python ────────────────────────────────────────────
echo [1/5] Checking Python...
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python not found.
    echo Please install Python 3.11+ from https://python.org
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PY_VER=%%i
echo   Found Python %PY_VER%

REM ─── Step 2: Check Node.js ───────────────────────────────────────────
echo [2/5] Checking Node.js...
where node >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Node.js not found.
    echo Please install Node.js 18+ from https://nodejs.org
    pause
    exit /b 1
)
for /f "tokens=1" %%i in ('node --version') do set NODE_VER=%%i
echo   Found Node.js %NODE_VER%

REM ─── Step 3: Create virtual environment + install Python deps ───────
echo [3/5] Setting up Python virtual environment...

if not exist "venv\Scripts\python.exe" (
    echo   Creating virtual environment...
    python -m venv venv
    if %ERRORLEVEL% neq 0 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo   Virtual environment created.
) else (
    echo   Virtual environment already exists.
)

echo   Installing Python dependencies...
call venv\Scripts\pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo   WARNING: Some packages failed to install.
    echo   You can retry with: venv\Scripts\pip install -r requirements.txt
) else (
    echo   Python dependencies installed successfully.
)

REM ─── Step 4: Install Node dependencies + build frontend ─────────────
echo [4/5] Setting up Node.js frontend...

cd electron_frontend

if not exist "node_modules" (
    echo   Installing npm packages...
    call npm install
    if %ERRORLEVEL% neq 0 (
        echo ERROR: npm install failed.
        cd ..
        pause
        exit /b 1
    )
    echo   npm packages installed.
) else (
    echo   npm packages already installed.
)

if not exist "dist\index.html" (
    echo   Building frontend...
    call npx vite build
    if %ERRORLEVEL% neq 0 (
        echo   WARNING: Vite build had issues. Run manually: cd electron_frontend ^&^& npx vite build
    ) else (
        echo   Frontend built successfully.
    )
) else (
    echo   Frontend already built.
)

cd ..

REM ─── Step 5: Create .env template ───────────────────────────────────
echo [5/5] Creating .env template...

if not exist ".env" (
    (
        echo # Jarvis Mark II — API Keys
        echo # Uncomment and fill in the keys you need.
        echo.
        echo # --- OpenAI ---
        echo # OPENAI_API_KEY=sk-...
        echo.
        echo # --- Anthropic ---
        echo # ANTHROPIC_API_KEY=sk-ant-...
        echo.
        echo # --- OpenRouter ---
        echo # OPENROUTER_API_KEY=sk-or-...
        echo.
        echo # --- OpenCode Zen (default — free, no key needed) ---
        echo # OPENCODE_ZEN_API_KEY=
        echo.
        echo # --- xAI Grok ---
        echo # XAI_API_KEY=...
        echo.
        echo # --- Google Gemini ---
        echo # GEMINI_API_KEY=...
        echo.
        echo # --- DeepSeek ---
        echo # DEEPSEEK_API_KEY=...
    ) > .env
    echo   Created .env template — edit to add your API keys.
) else (
    echo   .env file already exists.
)

REM ─── Done ────────────────────────────────────────────────────────────
echo.
echo ============================================
echo    Installation Complete!
echo ============================================
echo.
echo  To start Jarvis, double-click:
echo    Launch Jarvis (Silent).vbs
echo.
echo  Or run with a visible console:
echo    Run Jarvis II.bat
echo.
echo  First time? See INSTALL.md for setting up
echo  an AI provider (or use OpenCode Zen free).
echo.

pause
