# J.A.R.V.I.S. Mark II

**Just A Rather Very Intelligent System** — A native desktop AI assistant inspired by Iron Man's JARVIS.

Built with a Python/FastAPI backend and an Electron + React frontend with a holographic 3D interface. Supports multiple AI providers, persistent memory, tool use, web search, speech-to-text, and text-to-speech.

> ⚠️ **Hobby Project/Concept Idea** — This is a project made by someone who doesn't know how to code but wanted to have something close to a real life Jarvis. The goal is to build the ultimate AI assistant utilizing projects like [Hermes](https://hermes-agent.nousresearch.com/) and [Odysseus](https://github.com/pewdiepie-archdaemon/odysseus).

---

## ⚡ Quick Start

### Requirements

- **Python 3.11+** ([python.org](https://python.org))
- **Node.js 18+** ([nodejs.org](https://nodejs.org))
- Approximately 4GB of free disk space (for dependencies and optional speech models)

### 1. Install Everything

**Option A — One-click installer (recommended):** Double-click **`install.bat`** in the project folder. It will set up the Python virtual environment, install all dependencies, and build the frontend.

**Option B — Manual install (3 commands):**
```batch
python -m venv venv
venv\Scripts\pip install -r requirements.txt
cd electron_frontend && npm install && npx vite build && cd ..
```

### 2. First Launch

Double-click **`Run Jarvis II.bat`**. This will:
- Start the Python backend (console window)
- Launch the Jarvis desktop window with the 3D holographic interface
- Build the frontend automatically if this is your first time

### 3. Subsequent Launches (Recommended)

Once everything is installed and working, use the **silent launcher** for daily use:

Double-click **`Launch Jarvis (Silent).vbs`** — no console windows, no popups. Logs are written to `%TEMP%\jarvis-boot.log` if you ever need to troubleshoot.

### 4. Enable System Tray Minimize & Launch on System Boot (Highly Recommended)

After Jarvis opens:
1. Click the **gear icon** (Settings, top-right)
2. Toggle **"Minimize to system tray"** ON
3. Toggle **"Auto-start Jarvis on system boot"** ON

Closing the window will now minimize Jarvis to your system tray instead of quitting and Jarvis will now launch when your system boots.

You can then right-click the tray icon to show or quit Jarvis at any time.

### Manual Setup (All Platforms)

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/Jarvis-Mark-II.git
cd Jarvis-Mark-II

# 2. Create and activate a virtual environment (recommended)
python -m venv venv
# Windows:
venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Build the frontend
cd electron_frontend
npm install
npm run build
cd ..

# 5. Start Jarvis
venv\Scripts\python run.py --server   # Web server (browser)
```

---

## 🔌 Connecting an AI Provider

Jarvis supports **9+ providers**. You need at least one configured to chat.

### Free Option (No API Key Required)

The default provider is **OpenCode Zen** — it offers free models with no API key needed:

1. Open the Jarvis UI at `http://127.0.0.1:11711`
2. Click the **gear icon** (Settings) in the top-right corner
3. Select **"OpenCode Zen"** from the Provider dropdown
4. Leave the API key field empty
5. Click **"Save Provider"**
6. Click **Save**, then select a free model from the model selector (e.g., `big-pickle`)

### Paid Providers (API Key Required)

1. Open Settings → Provider dropdown
2. Select your provider (OpenAI, OpenRouter, Anthropic, Google Gemini, etc.)
3. Enter your API key in the field
4. Click **"Test Connection"** and then **"Save Provider"** to see available models
5. Select a model, then chat away!

| Provider | Base URL | API Key Needed |
|----------|----------|----------------|
| OpenCode Zen | `https://opencode.ai/zen/v1` | No (free models) |
| OpenAI | `https://api.openai.com/v1` | Yes |
| OpenRouter | `https://openrouter.ai/api/v1` | Yes |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` | Yes |
| Anthropic | `https://api.anthropic.com/v1` | Yes (OpenAI-compatible mode) |
| xAI Grok | `https://api.x.ai/v1` | Yes |
| DeepSeek | `https://api.deepseek.com/v1` | Yes |
| Together AI | `https://api.together.xyz/v1` | Yes |
| Ollama (Local) | `http://localhost:11434/v1` | No |
| Custom | Your own URL | Varies |

> 🔐 **API keys are stored encrypted** in `~/.jarvis/config.yaml`. Keys are encrypted at rest using your system's machine ID as a key. See the Security section for details.

---

## 🧰 What Jarvis Can Do (Tools)

Once connected, Jarvis has these capabilities:

| Tool | What It Does |
|------|-------------|
| `read_file` | Read the contents of any file |
| `create_file` | Create or overwrite files anywhere on your computer |
| `web_search` | Search the web using DuckDuckGo (free, no API key) |
| `web_fetch` | Fetch and extract text from any webpage |
| `open_app` | Launch applications (calculator, notepad, Chrome, Discord, etc.) |
| `list_apps` | Show all registered applications |
| `execute_command` | Run safe shell commands (read-only whitelist) |
| `save_fact` | Store information in long-term memory |
| `recall_facts` | Retrieve information from long-term memory |
| Text-to-Speech | Jarvis speaks responses aloud using Edge TTS |
| Speech-to-Text | Speak to Jarvis using your microphone |

Example conversation:
> **You:** "Search the web for today's top tech news"
> **Jarvis:** Searches the web and returns results with sources
>
> **You:** "Remember that my favorite color is blue"
> **Jarvis:** Saves the fact to persistent memory
>
> **You:** "What do you know about me?"
> **Jarvis:** Recalls your stored memories
>
> **You:** "Create a file called notes.txt on my desktop"
> **Jarvis:** Creates the file with your specified content

---

## 🌐 API Overview

Jarvis provides a WebSocket API for real-time chat and REST endpoints for configuration.

### WebSocket Chat (`ws://127.0.0.1:11711/ws`)

```json
→ {"type": "message", "text": "Hello"}
← {"type": "thinking", "text": ""}
← {"type": "delta", "text": "Hi "}
← {"type": "delta", "text": "there!"}
← {"type": "done", "text": "Hi there!"}
```

### Key REST Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Server health check |
| GET | `/api/config` | Get current config |
| POST | `/api/config` | Update config |
| GET | `/api/providers` | List providers |
| POST | `/api/provider/set` | Set active provider |
| POST | `/api/provider/test` | Test provider connection |
| POST | `/api/provider/models` | Fetch available models |
| POST | `/api/tts` | Text-to-speech |
| POST | `/api/stt` | Speech-to-text |
| GET | `/api/memory` | Get memory contents |
| POST | `/api/memory` | Update memory |
| POST | `/api/provider/key` | Set per-provider API key |
| DELETE | `/api/provider/key` | Remove a provider's API key |

---

## 🌳 Persistent Memory

Jarvis Mark II remembers who you are across sessions using three memory files stored at `~/.jarvis/memories/`:

- **MEMORY.md** — Facts, preferences, and learned information (2,200 char limit)
- **USER.md** — Your name, role, and personality notes (1,375 char limit)
- **PERSONALITY.md** — Jarvis's own personality and behavior rules (2,800 char limit)

Memory updates happen automatically during conversation. You can also view and edit memory directly in the Settings panel.

---

## 🗺️ Project Structure

```
Jarvis Mark II/
├── jarvis/
│   ├── server.py            # FastAPI server (30+ endpoints + WebSocket)
│   ├── config.py             # Configuration management
│   ├── constants.py          # Constants and default paths
│   ├── security.py           # Encrypted API key storage
│   ├── desktop.py            # PyWebView desktop wrapper
│   ├── gui.py                # System tray icon
│   ├── agent/
│   │   ├── agent_loop.py     # Main agent loop (thinking, tool calls, memory)
│   │   ├── llm_core.py       # OpenAI-compatible LLM client
│   │   └── model_discovery.py # Provider model discovery
│   ├── memory/
│   │   └── store.py          # Persistent memory store
│   ├── providers/
│   │   ├── profiles.py       # Provider profiles (9+ providers)
│   │   ├── registry.py       # Provider registry
│   │   └── base.py           # Abstract provider base
│   ├── tools/
│   │   ├── base_tools.py     # Files, memory, and system tools
│   │   ├── web_tools.py      # Web search and fetch tools
│   │   ├── pc_control.py     # Windows PC control tools
│   │   └── registry.py       # Tool registry
│   ├── speech/
│   │   ├── tts.py            # Text-to-speech (Edge TTS)
│   │   └── stt.py            # Speech-to-text (Whisper)
│   ├── skills/
│   │   └── loader.py         # Skill system loader
│   └── state/
│       └── db.py             # Session state database
├── electron_frontend/
│   ├── src/
│   │   ├── App.jsx           # Main React app
│   │   └── components/       # React UI components
│   ├── electron/
│   │   ├── main.cjs          # Electron main process
│   │   └── preload.cjs       # Electron preload script
│   ├── package.json
│   └── vite.config.js
├── run.py                     # Server entry point
├── requirements.txt           # Python dependencies
├── Run Jarvis II.bat          # Electron console launcher
├── Run Jarvis II (Dev).bat    # Hot-reload dev launcher
├── Launch Jarvis (Silent).vbs # Silent desktop launcher (no console)
├── install.bat                # One-click installer
├── INSTALL.md                 # Installation guide
├── ARCHITECTURE.md            # Architecture documentation
├── CHANGELOG.md               # Version history
├── .gitignore
└── README.md
```

---

## 🔐 Security

Jarvis Mark II includes several security measures:

- **Encrypted API key storage** — Keys are encrypted at rest using AES-GCM with a key derived from your machine ID. Stored in `~/.jarvis/config.yaml`.
- **Per-provider key isolation** — Each provider has its own API key entry. Keys are never exposed in the frontend.
- **CORS restricted to localhost** — The server only accepts connections from `127.0.0.1` and `localhost`.
- **Read-only command whitelist** — Shell commands are restricted to a safe subset.
- **No external telemetry** — Jarvis never phones home. All processing happens locally.

---

## 🤖 AI Disclosure

**This project was entirely built using AI tools** — specifically through conversations with the Hermes Agent (by Nous Research) running various models via OpenCode Zen's free tier.

The author (Josh) provided design direction, bug reports, and feature requests. The actual code, documentation, and architecture were generated by AI agents through iterative prompting.

This is not a commercial product — it's a learning project and proof of concept. All sources are linked, and all credit is given where it is due.

---

## 📃 Credits

- Logic / Backend — [Hermes by Nous Research](https://hermes-agent.nousresearch.com/)
- UI Framework — [Electron](https://www.electronjs.org/) + [React](https://react.dev/)
- 3D Graphics — [Three.js](https://threejs.org/)
- Speech — [Edge TTS](https://github.com/rany2/edge-tts) + [Whisper](https://github.com/openai/whisper)

---

## 📜 License

MIT License — free to use, modify, and distribute. See [LICENSE](LICENSE) for details.

---

## 🗺️ Roadmap

- **Mark I** — Web-based UI, multi-provider support, basic tools, TTS
- **Mark II** — Desktop app (Electron), system tray, persistent memory, encrypted API keys, STT, skill system, session history, tool improvements
- **Mark III** — Screen awareness, always-on voice wake word, advanced automation, plugin system
- **Mark IV** — And even more to come .....

This project aims for **20+ versions** until the feature set feels complete.
