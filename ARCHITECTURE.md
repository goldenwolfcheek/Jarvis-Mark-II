# Jarvis Mark II — Architecture

## Overview
Jarvis Mark II is a desktop AI agent application combining:
- **Hermes Agent's backend logic** — provider profiles, credential management, agent loop, tool abstraction
- **Odysseus's feature structure** — auth, sessions, memory, skills, calendar, docs, email integrations
- **Custom futuristic UI** — Three.js dot-sphere scene with audio reactivity

## Core Architecture

```
┌─────────────────────────────────────────────┐
│              User (Browser)                  │
│  Three.js Dot Sphere · Chat UI · Settings    │
├─────────────────────────────────────────────┤
│           WebSocket (ws://:11711)            │
│           REST API (http://:11711)           │
├─────────────────────────────────────────────┤
│              FastAPI Server                  │
│  ┌─────────┐ ┌──────────┐ ┌──────────────┐  │
│  │ Routes  │ │WebSocket │ │ Static Files │  │
│  └────┬────┘ └────┬─────┘ └──────────────┘  │
│       │           │                          │
│  ┌────▼───────────▼─────────────────────┐   │
│  │           Agent Loop                  │   │
│  │  ┌──────────┐ ┌────────┐ ┌────────┐  │   │
│  │  │ LLM Core │ │ Tools  │ │ Skills │  │   │
│  │  └────┬─────┘ └────────┘ └────────┘  │   │
│  └───────┼──────────────────────────────┘   │
│          │                                   │
│  ┌───────▼──────────────────────────────┐   │
│  │        Provider Profiles             │   │
│  │  OpenAI · Anthropic · Ollama · etc.  │   │
│  └──────────────────────────────────────┘   │
│                                              │
│  ┌──────────┐ ┌──────────┐ ┌────────────┐  │
│  │ State DB │ │ Memory   │ │ Speech/TTS │  │
│  │ (SQLite) │ │ (Files)  │ │ (edge-tts) │  │
│  └──────────┘ └──────────┘ └────────────┘  │
└─────────────────────────────────────────────┘
```

## Key Backend Modules

### `jarvis/server.py` — FastAPI + WebSocket server
- Serves static frontend files
- REST API endpoints (/api/*)
- WebSocket endpoint (/ws) for real-time chat
- CORS, security headers, error handling

### `jarvis/agent/` — Agent system
- `llm_core.py` — Core LLM interaction with streaming support
- `agent_loop.py` — Turn loop: receive message → call LLM → dispatch tools → return
- `model_discovery.py` — Provider/model discovery and validation

### `jarvis/providers/` — Provider profiles (Hermes-style)
- `base.py` — ProviderProfile dataclass
- Individual provider profiles (OpenAI, Anthropic, Ollama, OpenRouter, etc.)

### `jarvis/tools/` — Tool implementations
- `registry.py` — Tool registration and discovery
- `base_tools.py` — Core tools (file, terminal, web search, code execution)
- `pc_control.py` — PC automation tools
- `web_tools.py` — Web search and browsing
- `knowledge_tools.py` — Memory and knowledge tools

### `jarvis/memory/` — Memory system
- `store.py` — File-based memory for system prompt injection
- Memory search for relevant context retrieval

### `jarvis/state/` — Persistent state
- `db.py` — SQLite-backed sessions, messages, key-value store

### `jarvis/speech/` — Text-to-Speech
- `tts.py` — edge-tts integration

### `jarvis/skills/` — Dynamic skill loading
- `loader.py` — Python module discovery and loading

## Key Frontend

### Three.js Dot-Sphere Scene (`js/sphere.js`)
- Two concentric Fibonacci-sphere particle clouds
- Audio reactivity via Web Audio API
- HUD rings rotating around spheres
- Starfield background

### Chat UI (`js/chat.js`)
- Streaming message display
- Auto-scroll, message history
- Enter to send, Shift+Enter for newline

### Settings Panel (`js/settings.js`)
- Provider/model selection
- API key management
- TTS configuration
- Theme switching (Dark/Cyber/Amber)
- Temperature control

### App Orchestrator (`js/app.js`)
- WebSocket connection with auto-reconnect
- Session management
- Memory editing
- Skills display
- Info bar status

## Windows Install (PowerShell)

```powershell
.\install-jarvis.ps1
# Creates venv, installs deps, creates shortcuts, starts server
```

## Data Directory Structure
```
~/.jarvis/
├── config.yaml
├── memory.md
├── user.md
├── state.db
├── sessions.json
├── skills/
├── audio/
└── logs/
```
