"""
Jarvis Mark II — Constants and default paths.
Mirrors Hermes Agent patterns with Jarvis-specific paths.
"""

import os
import sys
from pathlib import Path

# ── Version ──────────────────────────────────────────────────────────────
VERSION = "2.0.0"
APP_NAME = "Jarvis"


# ── Data directory (user home) ───────────────────────────────────────────
def get_jarvis_home() -> Path:
    """Return the Jarvis data directory (~/.jarvis or custom via JARVIS_HOME)."""
    env = os.environ.get("JARVIS_HOME")
    if env:
        return Path(env).expanduser().resolve()
    return Path.home() / ".jarvis"

JARVIS_HOME = get_jarvis_home()

# ── Subdirectory layout ──────────────────────────────────────────────────
CONFIG_DIR       = JARVIS_HOME
CONFIG_FILE      = CONFIG_DIR / "config.yaml"
MEMORY_DIR       = JARVIS_HOME / "memories"
MEMORY_FILE      = MEMORY_DIR / "MEMORY.md"
USER_FILE        = MEMORY_DIR / "USER.md"
PERSONALITY_FILE = MEMORY_DIR / "PERSONALITY.md"
SKILLS_DIR       = JARVIS_HOME / "skills"
AUDIO_DIR        = JARVIS_HOME / "audio"
SCREENSHOTS_DIR  = JARVIS_HOME / "screenshots"
STATE_DB         = JARVIS_HOME / "state.db"
LOGS_DIR         = JARVIS_HOME / "logs"
UPLOADS_DIR      = JARVIS_HOME / "uploads"
APPS_FILE        = JARVIS_HOME / "registered_apps.json"

# ── Server defaults ──────────────────────────────────────────────────────
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 11711

# ── Memory limits ────────────────────────────────────────────────────────
MEMORY_CHAR_LIMIT = 2200
USER_CHAR_LIMIT = 1375
PERSONALITY_CHAR_LIMIT = 2800

# ── Tool limits ──────────────────────────────────────────────────────────
FILE_READ_MAX_CHARS = 50000
TOOL_OUTPUT_MAX_CHARS = 50000
MAX_TOOL_TURNS = 60
MAX_TOOL_DEFS = 50  # Cap total tool definitions sent to LLM to avoid 400 errors

# ── WebSocket ────────────────────────────────────────────────────────────
WS_RECONNECT_DELAY = 3  # seconds

# ── Default config template (YAML) ──────────────────────────────────────
DEFAULT_CONFIG_YAML = """# Jarvis Mark II Configuration
model: big-pickle
provider: opencode-zen
base_url: "https://opencode.ai/zen/v1"
api_key: null
tts_enabled: true
tts_provider: edge
auto_speak: true
volume: 80
theme: dark
start_on_boot: false
toolsets:
  - core
  - memory
  - files
  - web
  - pc
  - skills

# Provider configurations
providers:
  opencode-zen:
    base_url: "https://opencode.ai/zen/v1"
    api_key: null
  openai:
    base_url: "https://api.openai.com/v1"
    api_key: null
  openrouter:
    base_url: "https://openrouter.ai/api/v1"
    api_key: null
  anthropic:
    base_url: "https://api.anthropic.com/v1"
    api_key: null
  google:
    base_url: "https://generativelanguage.googleapis.com/v1beta/openai"
    api_key: null
  ollama:
    base_url: "http://localhost:11434/v1"
    api_key: null
  lmstudio:
    base_url: "http://localhost:1234/v1"
    api_key: null
  custom:
    base_url: ""
    api_key: null
"""
