# Jarvis Mark II — Installation Guide

A native desktop AI assistant with voice control, web search, memory, and tool execution.
Powered by Python + FastAPI backend and an Electron + React 3D frontend.

---

## Prerequisites

| Requirement | Minimum | Download |
|-------------|---------|----------|
| **Python** | 3.11+ | [python.org](https://python.org) |
| **Node.js** | 18+ | [nodejs.org](https://nodejs.org) |
| **Disk space** | ~2 GB | — |

Make sure both are on your PATH (check with `python --version` and `node --version` in a terminal).

---

## Option A: One-Click Install (Recommended)

Double-click **`install.bat`** in the project folder. It will:

1. Create a Python virtual environment (`venv\`)
2. Install all Python backend dependencies
3. Install all Node.js frontend dependencies
4. Build the Electron frontend
5. Create a `.env` template for API keys

When it finishes, open **`Launch Jarvis (Silent).vbs`** to start.

---

## Option B: Manual Install (3 Commands)

From the project root directory, run:

```batch
python -m venv venv
venv\Scripts\pip install -r requirements.txt
cd electron_frontend && npm install && npx vite build && cd ..
```

That's it. The frontend will be built to `electron_frontend/dist/`.

---

## First Launch

### Start Jarvis

- **Desktop app (recommended):** Double-click **`Launch Jarvis (Silent).vbs`**
  — or — **`Run Jarvis II.bat`** (shows a console window with logs)
- **Web server only:** `venv\Scripts\python run.py --server`
  Then open your browser to `http://127.0.0.1:11711`

The first launch starts the Python backend (visible in the VBS boot log at `%TEMP%\jarvis-boot.log`), then opens the Jarvis desktop window with the holographic 3D interface.

### Set Up an AI Provider

Jarvis needs an AI provider to answer your questions.

**Free option — OpenCode Zen (no key needed):**

1. Open Jarvis, click the **gear icon** (top-right corner)
2. Select **OpenCode Zen** as the provider
3. Leave the API key blank
4. Click **"Test"**, then **"Add"**
5. Click the provider name in the bottom bar, pick a model (e.g. `big-pickle`)

**Paid providers — OpenAI, OpenRouter, etc.:**

1. Open Settings → **Providers** section
2. Click **"Add"** next to your provider
3. Enter your API key, click **"Test"** to verify, then **"Add"**
4. Select the provider and a model from the bottom bar

---

## Auto-Start on PC Boot

Once you have Jarvis running:

1. Open **Settings** → scroll to **Auto-start**
2. Toggle **"Launch on PC Boot"** ON

This writes a registry key under `HKCU\...\Run` that launches `Launch Jarvis (Silent).vbs` on login.
The VBS script starts Jarvis silently — no console windows, no popups. Logs are written to `%TEMP%\jarvis-boot.log`.

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `python` not found | Python not installed or not on PATH | Install Python 3.11+, check "Add to PATH" |
| `node` not found | Node.js not installed | Install Node.js 18+ |
| VBS launches but nothing appears | Backend startup issue | Check `%TEMP%\jarvis-boot.log` |
| Connection shows "Disconnected" | First-run race condition | Wait 2 seconds — auto-reconnect kicks in. If persistent, restart Jarvis |
| Black screen / blank window | Frontend not built | Run `cd electron_frontend && npx vite build` |
| "No providers available" | No API key set | Set up a provider in Settings |
| Backend fails to start | Port 11711 in use | Close any other app on that port, or kill the old Python process |

---

## Project Structure

```
Jarvis Mark II\
├── install.bat                   ← One-click installer
├── Launch Jarvis (Silent).vbs    ← Silent launcher for daily use
├── Run Jarvis II.bat             ← Console-window launcher (with logs)
├── README.md                     ← Full project documentation
├── requirements.txt              ← Python dependencies
├── run.py                        ← Backend entry point
├── jarvis/                       ← Python backend (FastAPI)
│   ├── server.py
│   ├── agent/
│   ├── tools/
│   ├── providers/
│   └── ...
└── electron_frontend/            ← Electron + React frontend
    ├── package.json
    ├── electron/main.cjs         ← Electron main process
    └── src/                      ← React UI
```
