"""
Jarvis Mark II — FastAPI Server.
WebSocket-driven real-time agent interaction plus REST management APIs.
Serves the Three.js frontend statically.
"""

# ── Windows console encoding safety ──────────────────────────────────
# Python's print() on Windows uses cp1252 which can't encode emoji
# (✅, 📎, etc.).  This causes UnicodeEncodeError crashes in ANY print()
# across the codebase.  Switch to utf-8 with 'replace' error handling
# so emoji and other non-Latin characters degrade to ? instead of crash.
import sys as _sys
if hasattr(_sys.stdout, "reconfigure"):
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(_sys.stderr, "reconfigure"):
    _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
del _sys

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from . import config as config_module
from .constants import (
    VERSION,
    APP_NAME,
    DEFAULT_HOST,
    DEFAULT_PORT,
    LOGS_DIR,
    AUDIO_DIR,
    SKILLS_DIR,
    UPLOADS_DIR,
    WS_RECONNECT_DELAY,
)
from .config import get_config
from .state.db import get_state_db
from .memory.store import get_memory_store
from .tools.registry import get_tool_registry
from .tools import discover_tools
from .skills.loader import get_skill_loader
from .speech.tts import get_tts_engine
from .speech.stt import get_stt_engine
from .agent.llm_core import get_llm_core
from .agent.model_discovery import ModelDiscovery
from .agent.agent_loop import get_agent_loop
from .providers import ProviderRegistry
from .security import resolve_api_key, get_keystore
from datetime import datetime
import platform
import logging

logger = logging.getLogger(__name__)

_start_time = time.time()

# ── Lifespan ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    startup_tasks()
    yield
    shutdown_tasks()


def startup_tasks():
    """Initialise all subsystems on startup."""
    logs_dir = LOGS_DIR
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger.info("[%s] v%s starting up...", APP_NAME, VERSION)
    logger.info("[%s] Data directory: %s", APP_NAME, Path.home() / ".jarvis")

    # Load tools (auto-discovered from jarvis/tools/)
    tool_count = discover_tools()
    registry = get_tool_registry()
    logger.info("[%s] Loaded %d tools (%d registered)", APP_NAME, tool_count, registry.count())

    # Load skills
    try:
        skills = get_skill_loader()
        skills.load_all()
        logger.info("[%s] Loaded %d skills: %s", APP_NAME, len(skills.get_skill_names()), skills.get_skill_names())
    except Exception as e:
        logger.warning("[%s] Skill loading skipped: %s", APP_NAME, e)

    # Init DB
    db = get_state_db()
    logger.info("[%s] State DB ready (%s sessions)", APP_NAME, db.get_stats()["sessions"])


def shutdown_tasks():
    """Clean shutdown."""
    logger.info("[%s] Shutting down...", APP_NAME)


# ── App factory ───────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    config = get_config()
    host = config.get("host", DEFAULT_HOST)
    port = config.get("port", DEFAULT_PORT)

    app = FastAPI(
        title=APP_NAME,
        version=VERSION,
        lifespan=lifespan,
    )

    # ── Middleware ─────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Inject config into app state ──────────────────────────────────────
    app.state.host = host
    app.state.port = port

    # ── Register routes ───────────────────────────────────────────────────
    _register_routes(app)

    return app


# ═══════════════════════════════════════════════════════════════════════════
# Routes
# ═══════════════════════════════════════════════════════════════════════════

def _register_routes(app: FastAPI):
    """Register all API and WebSocket routes."""

    # ── Health / Info ────────────────────────────────────────────────────

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "app": APP_NAME, "version": VERSION}

    @app.get("/api/info")
    async def info():
        config = get_config()
        db = get_state_db()
        registry = get_tool_registry()
        llm = get_llm_core()
        return {
            "version": VERSION,
            "app": APP_NAME,
            "provider": config.get_active_provider(),
            "model": config.get_active_model(),
            "tools_loaded": registry.count(),
            "sessions": db.get_stats()["sessions"],
            "messages": db.get_stats()["messages"],
            "total_tokens": llm.total_tokens,
        }

    # ── Config ───────────────────────────────────────────────────────────

    @app.get("/api/config")
    async def get_full_config():
        config = get_config()
        return config.get_all()

    @app.get("/api/config/{key:path}")
    async def get_config_key(key: str):
        config = get_config()
        val = config.get(key)
        if val is None:
            raise HTTPException(status_code=404, detail=f"Config key '{key}' not found")
        return {"key": key, "value": val}

    @app.put("/api/config/{key:path}")
    async def set_config_key(key: str, body: dict):
        config = get_config()
        value = body.get("value")
        if value is None:
            raise HTTPException(status_code=400, detail="Body must include 'value'")
        config.set(key, value)
        return {"status": "ok", "key": key, "value": value}

    # ── Providers / Models ───────────────────────────────────────────────

    @app.get("/api/providers")
    async def get_providers():
        config = get_config()
        providers = config.get_providers()
        return {
            "providers": list(providers.keys()),
            "active": config.get_active_provider(),
        }

    @app.get("/api/models")
    async def discover_models(provider: Optional[str] = None):
        discovery = ModelDiscovery()
        if provider:
            models = await discovery.discover(provider)
            return {"provider": provider, "models": models, "count": len(models)}
        results = await discovery.discover_all()
        return results

    # ── Sessions ─────────────────────────────────────────────────────────

    @app.get("/api/sessions")
    async def list_sessions(limit: int = 50, offset: int = 0):
        db = get_state_db()
        sessions = db.list_sessions(limit=limit, offset=offset)
        return {"sessions": sessions, "count": len(sessions)}

    @app.post("/api/sessions")
    async def create_session(title: str = "New Session"):
        db = get_state_db()
        sid = str(uuid.uuid4())
        session = db.create_session(sid, title=title)
        return session

    @app.get("/api/sessions/last")
    async def get_last_session():
        """Return the most recently updated session, or null if none exist."""
        db = get_state_db()
        sessions = db.list_sessions(limit=1, offset=0)
        if sessions:
            return sessions[0]
        return None

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str):
        db = get_state_db()
        session = db.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return session

    @app.delete("/api/sessions/{session_id}")
    async def delete_session(session_id: str):
        db = get_state_db()
        deleted = db.delete_session(session_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"status": "deleted", "session_id": session_id}

    @app.put("/api/sessions/{session_id}")
    async def update_session(session_id: str, body: dict):
        db = get_state_db()
        # Check if session exists first
        existing = db.get_session(session_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Session not found")
        title = body.get("title")
        metadata = body.get("metadata")
        db.update_session(session_id, title=title, metadata=metadata)
        session = db.get_session(session_id)
        return session

    @app.post("/api/sessions/{session_id}/touch")
    async def touch_session(session_id: str):
        """Update the session's updated_at so it becomes the 'last session' on next launch."""
        db = get_state_db()
        existing = db.get_session(session_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Session not found")
        # Touch by re-saving the same title — triggers updated_at update
        db.update_session(session_id, title=existing.get("title", ""))
        return {"status": "ok", "session_id": session_id}

    @app.get("/api/sessions/{session_id}/history")
    async def get_session_history(session_id: str, limit: int = 100, offset: int = 0):
        agent = get_agent_loop()
        messages = await agent.get_history(session_id, limit=limit)
        # Apply offset client-side if agent doesn't support it natively
        if offset > 0:
            messages = messages[offset:]
        return {"messages": messages, "count": len(messages)}

    # ── Memory ───────────────────────────────────────────────────────────

    @app.get("/api/memory")
    async def get_memory():
        memory = get_memory_store()
        return {
            "personality": memory.get_personality(),
            "user_profile": memory.get_user_profile(),
        }

    @app.put("/api/memory")
    async def set_memory(body: dict):
        memory = get_memory_store()
        if "personality" in body:
            memory.set_personality(body["personality"])
        elif "memory" in body and "personality" not in body:
            # Backward compatibility: old "memory" key maps to personality
            memory.set_personality(body["memory"])
        if "user_profile" in body:
            memory.set_user_profile(body["user_profile"])
        return {"status": "ok"}

    @app.post("/api/memory/append")
    async def append_memory(body: dict):
        text = body.get("text", "")
        target = body.get("target", "personality")
        memory = get_memory_store()
        if target == "user":
            memory.update_user_profile(text, append=True)
        else:
            # Default to personality (was memory previously)
            current = memory.get_personality()
            updated = current.rstrip() + "\n" + text.strip()
            memory.set_personality(updated)
        return {"status": "ok"}

    # ── Tools ────────────────────────────────────────────────────────────

    @app.get("/api/tools")
    async def list_tools(category: Optional[str] = None):
        registry = get_tool_registry()
        if category:
            tools = registry.get_by_category(category)
        else:
            tools = registry.get_all()
        return {
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "category": t.category,
                    "parameters": t.parameters,
                }
                for t in tools
            ],
            "count": len(tools),
        }

    @app.post("/api/tools/execute")
    async def execute_tool(body: dict):
        name = body.get("name", "")
        arguments = body.get("arguments", {})
        registry = get_tool_registry()
        if not registry.has_tool(name):
            raise HTTPException(status_code=404, detail=f"Unknown tool: {name}")
        result = await registry.execute(name, **arguments)
        return {"name": name, "result": result}

    # ── Provider Profiles ────────────────────────────────────────────

    @app.get("/api/providers/profiles")
    async def list_provider_profiles():
        registry = ProviderRegistry.get_instance()
        profiles = registry.list()
        return {
            "profiles": [
                {
                    "name": p.name,
                    "display_name": p.display_name,
                    "description": p.description,
                    "base_url": p.base_url,
                    "auth_type": p.auth_type,
                    "supports_vision": p.supports_vision,
                    "fallback_models": list(p.fallback_models) if p.fallback_models else [],
                    "env_vars": list(p.env_vars) if p.env_vars else [],
                    "has_api_key": resolve_api_key(p.name) is not None,
                }
                for p in profiles
            ],
            "count": len(profiles),
        }

    @app.get("/api/providers/profiles/{name}")
    async def get_provider_profile(name: str):
        registry = ProviderRegistry.get_instance()
        profile = registry.get(name)
        if profile is None:
            raise HTTPException(status_code=404, detail=f"Provider profile '{name}' not found")
        return {
            "name": profile.name,
            "display_name": profile.display_name,
            "description": profile.description,
            "base_url": profile.base_url,
            "auth_type": profile.auth_type,
            "supports_vision": profile.supports_vision,
            "fallback_models": list(profile.fallback_models) if profile.fallback_models else [],
            "env_vars": list(profile.env_vars) if profile.env_vars else [],
        }

    @app.put("/api/providers/keys/{name}")
    async def set_provider_key(name: str, body: dict):
        api_key = body.get("api_key", "")
        if not api_key:
            raise HTTPException(status_code=400, detail="'api_key' is required")
        keystore = get_keystore()
        keystore.set(name, api_key)
        return {"status": "ok", "provider": name}

    @app.delete("/api/providers/keys/{name}")
    async def delete_provider_key(name: str):
        keystore = get_keystore()
        keystore.delete(name)
        return {"status": "ok", "provider": name}

    @app.post("/api/providers/{name}/key/test")
    async def test_provider_key(name: str, body: dict = {}):
        """Test a provider's API key by making a lightweight request to their base URL.
        Accepts an optional 'api_key' in the request body. If not provided, reads
        from the keystore or environment."""
        registry = ProviderRegistry.get_instance()
        profile = registry.get(name)
        if not profile:
            raise HTTPException(status_code=404, detail=f"Provider '{name}' not found")

        # Use provided key, or fall back to keystore/env
        key = body.get("api_key") or resolve_api_key(name)
        if not key:
            raise HTTPException(status_code=400, detail=f"No API key provided or available for '{name}'")

        base_url = profile.base_url or ""
        if not base_url:
            return {"status": "warning", "message": f"No base URL configured for '{name}'", "ok": True}

        try:
            headers = {}
            if profile.auth_type == "bearer":
                headers["Authorization"] = f"Bearer {key}"
            elif profile.auth_type == "api-key":
                headers["X-API-Key"] = key
            elif profile.auth_type == "header":
                headers["Authorization"] = f"Bearer {key}"

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(base_url.rstrip("/") + "/models", headers=headers, follow_redirects=True)
                if resp.status_code < 500:
                    return {"status": "ok", "message": f"Connection successful ({resp.status_code})", "ok": True}
                else:
                    return {"status": "error", "message": f"Server error ({resp.status_code})", "ok": False}
        except httpx.TimeoutException:
            return {"status": "error", "message": "Connection timed out", "ok": False}
        except httpx.ConnectError:
            return {"status": "error", "message": f"Could not connect to {base_url}", "ok": False}
        except Exception as e:
            return {"status": "error", "message": str(e)[:100], "ok": False}

    @app.get("/api/providers/default")
    async def get_default_provider():
        registry = ProviderRegistry.get_instance()
        profile = registry.get_default()
        if profile is None:
            raise HTTPException(status_code=404, detail="No default provider configured")
        config = get_config()
        return {
            "provider": config.get_active_provider(),
            "model": config.get_active_model(),
            "profile": {
                "name": profile.name,
                "display_name": profile.display_name,
                "description": profile.description,
                "base_url": profile.base_url,
                "auth_type": profile.auth_type,
                "supports_vision": profile.supports_vision,
                "fallback_models": list(profile.fallback_models) if profile.fallback_models else [],
            },
        }

    @app.post("/api/providers/select")
    async def select_provider(body: dict):
        provider = body.get("provider", "")
        model = body.get("model", "")
        if not provider:
            raise HTTPException(status_code=400, detail="'provider' is required")
        config = get_config()
        registry = ProviderRegistry.get_instance()
        profile = registry.get(provider)
        if profile is None:
            raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")
        config.set_active_provider(provider)
        if model:
            config.set_active_model(model)
        return {
            "status": "ok",
            "provider": provider,
            "model": model or config.get_active_model(),
        }

    # ── System ──────────────────────────────────────────────────────

    @app.get("/api/system")
    async def get_system_info():
        uptime_seconds = time.time() - _start_time
        return {
            "os": platform.system(),
            "os_version": platform.version(),
            "os_release": platform.release(),
            "machine": platform.machine(),
            "python_version": sys.version,
            "python_executable": sys.executable,
            "hostname": platform.node(),
            "uptime_seconds": uptime_seconds,
            "uptime_formatted": f"{int(uptime_seconds // 86400)}d {int((uptime_seconds % 86400) // 3600)}h {int((uptime_seconds % 3600) // 60)}m {int(uptime_seconds % 60)}s",
        }

    # ── MCP Tools ───────────────────────────────────────────────────

    @app.get("/api/mcp/tools")
    async def list_mcp_tools():
        registry = get_tool_registry()
        tools = registry.get_all()
        return {
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.parameters,
                }
                for t in tools
            ],
            "count": len(tools),
        }

    # ── STT (Speech-to-Text) ─────────────────────────────────────────────

    @app.post("/api/stt/transcribe")
    async def stt_transcribe(
        file: bytes = File(...),
        language: Optional[str] = Query(None, description="Language code (auto-detect if omitted)"),
    ):
        """Transcribe audio via faster-whisper.

        Accepts WAV, WebM/Opus, or raw PCM 16-bit mono audio.
        Returns transcribed text with metadata.
        """
        if not file or len(file) < 44:
            raise HTTPException(status_code=400, detail="Empty or invalid audio file")

        stt = get_stt_engine()

        if not stt.is_available:
            raise HTTPException(
                status_code=501,
                detail="faster-whisper is not installed. Run: pip install faster-whisper",
            )

        # Detect format from header magic bytes
        is_wav = file[:4] == b"RIFF" and file[8:12] == b"WAVE"
        is_webm = file[:4] == b"\x1a\x45\xdf\xa3"  # EBML header (WebM/Matroska)
        is_ogg = file[:4] == b"OggS"  # Ogg/Opus

        try:
            if is_wav:
                result = stt.transcribe_wav(file, language=language)
            elif is_webm or is_ogg:
                result = stt.transcribe_webm(file, language=language)
            else:
                # Assume raw PCM 16-bit mono 16kHz
                result = stt.transcribe_bytes(file, sample_rate=16000, language=language)

            if result.get("error"):
                return JSONResponse(
                    status_code=500,
                    content={"status": "error", "detail": result["error"]},
                )

            return {
                "status": "ok",
                "text": result.get("text", ""),
                "language": result.get("language", ""),
                "language_probability": result.get("language_probability", 0),
                "duration_s": result.get("duration_s", 0),
            }

        except Exception as exc:
            logger.exception("[STT] Transcription failed")
            raise HTTPException(status_code=500, detail=str(exc))

    # ── TTS (Text-to-Speech) ────────────────────────────────────────────

    @app.get("/api/tts/voices")
    async def list_voices():
        tts = get_tts_engine()
        voices = await tts.list_voices()
        return {"voices": voices, "count": len(voices)}

    @app.post("/api/tts/speak")
    async def speak(body: dict):
        text = body.get("text", "")
        if not text:
            raise HTTPException(status_code=400, detail="'text' is required")
        tts = get_tts_engine()
        audio_path = await tts.speak_async(text)
        if audio_path and audio_path.exists():
            return {"status": "ok", "path": str(audio_path)}
        return {"status": "error", "detail": "TTS synthesis failed"}

    @app.get("/api/tts/audio/{filename:path}")
    async def serve_tts_audio(filename: str):
        audio_file = AUDIO_DIR / filename
        # Security: ensure we don't escape AUDIO_DIR
        try:
            audio_file = audio_file.resolve()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid path")
        if not str(audio_file).startswith(str(AUDIO_DIR.resolve())):
            raise HTTPException(status_code=403, detail="Access denied")
        if not audio_file.exists() or not audio_file.is_file():
            raise HTTPException(status_code=404, detail="Audio file not found")
        return FileResponse(str(audio_file))

    # ── Skills ───────────────────────────────────────────────────────────
    # ── File Upload ──────────────────────────────────────────────────────

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    @app.post("/api/upload")
    async def upload_file(file: UploadFile = File(...)):
        """Upload a file for use in a chat message. Returns a file ID."""
        file_id = str(uuid.uuid4())
        upload_dir = UPLOADS_DIR / file_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        dest = upload_dir / file.filename

        content = await file.read()
        # Reject files larger than 10MB
        max_bytes = 10 * 1024 * 1024
        if len(content) > max_bytes:
            shutil.rmtree(upload_dir)
            raise HTTPException(status_code=413, detail="File too large (max 10MB)")

        with open(dest, "wb") as f:
            f.write(content)

        return {
            "status": "ok",
            "file_id": file_id,
            "filename": file.filename,
            "size": len(content),
            "content_type": file.content_type or "application/octet-stream",
        }

    @app.delete("/api/upload/{file_id}")
    async def delete_upload(file_id: str):
        """Delete an uploaded file by ID."""
        upload_dir = UPLOADS_DIR / file_id
        if upload_dir.exists():
            shutil.rmtree(upload_dir)
            return {"status": "ok"}
        raise HTTPException(status_code=404, detail="File not found")

    # ── Skills ───────────────────────────────────────────────────────────

    @app.get("/api/skills")
    async def list_skills():
        skills = get_skill_loader()
        return {
            "skills": [
                {"name": s.name, "description": s.description, "functions": list(s.functions.keys())}
                for s in skills.get_all_skills()
            ],
            "count": len(skills.get_skill_names()),
        }

    @app.post("/api/skills/reload")
    async def reload_skills(body: Optional[dict] = None):
        skills = get_skill_loader()
        skill_name = body.get("name") if body else None
        if skill_name:
            skills.reload_skill(skill_name)
            return {"status": "ok", "reloaded": skill_name}
        skills.load_all(reload=True)
        return {"status": "ok", "reloaded": "all", "count": len(skills.get_skill_names())}

    @app.post("/api/skills/import")
    async def import_skill(body: dict):
        skills = get_skill_loader()
        source_path = body.get("path")
        github_url = body.get("github")

        try:
            if source_path:
                # Import from local folder
                src = Path(source_path).expanduser().resolve()
                if not src.exists() or not src.is_dir():
                    raise HTTPException(status_code=400, detail=f"Folder not found: {source_path}")

                # Create a destination folder under skills dir
                dest = SKILLS_DIR / src.name
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(src, dest)
                skills.load_all(reload=True)
                return {"status": "ok", "source": "folder", "path": str(dest), "success": True}

            elif github_url:
                # Import from GitHub repo
                import tempfile
                repo_name = github_url.strip().rstrip("/").split("/")[-1].replace(".git", "")
                dest = SKILLS_DIR / repo_name

                # Clean existing
                if dest.exists():
                    shutil.rmtree(dest)

                # Clone the repo
                result = subprocess.run(
                    ["git", "clone", github_url.strip(), str(dest)],
                    capture_output=True, text=True, timeout=120,
                )
                if result.returncode != 0:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Git clone failed: {result.stderr.strip() or result.stdout.strip()}",
                    )

                skills.load_all(reload=True)
                return {"status": "ok", "source": "github", "repo": repo_name, "path": str(dest), "success": True}

            else:
                raise HTTPException(status_code=400, detail="Provide 'path' or 'github' field")

        except HTTPException:
            raise
        except Exception as e:
            return {"status": "error", "error": str(e), "success": False}

    # ── Stats ────────────────────────────────────────────────────────────

    @app.get("/api/stats")
    async def get_stats():
        db = get_state_db()
        llm = get_llm_core()
        registry = get_tool_registry()
        return {
            "database": db.get_stats(),
            "llm_usage": llm.get_usage_summary(),
            "tools": {"loaded": registry.count()},
        }

    # WebSocket ────────────────────────────────────────────────────────────

    TEXT_EXTENSIONS = frozenset({
        ".txt", ".md", ".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css",
        ".json", ".xml", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
        ".csv", ".log", ".sh", ".bat", ".ps1", ".sql", ".r", ".rb", ".go",
        ".rs", ".java", ".cpp", ".c", ".h", ".hpp", ".swift", ".kt", ".dart",
        ".php", ".pl", ".lua", ".vim", ".tex", ".rst", ".env", ".gitignore",
        ".dockerfile", ".gradle", ".makefile",
    })

    def _build_file_context(file_ids: list[str], uploads_dir: Path) -> str:
        """Load uploaded files and build an injected context block for the LLM."""
        parts = []
        for fid in file_ids:
            fdir = uploads_dir / fid
            if not fdir.exists() or not fdir.is_dir():
                parts.append(f"[File {fid[:8]}: not found]")
                continue
            files_in_dir = list(fdir.iterdir())
            if not files_in_dir:
                parts.append(f"[File {fid[:8]}: empty]")
                continue
            fpath = files_in_dir[0]
            fname = fpath.name
            ext = fpath.suffix.lower()

            # Text files — inline content
            if ext in TEXT_EXTENSIONS:
                try:
                    text = fpath.read_text(encoding="utf-8", errors="replace")
                    # Truncate overly large text files
                    if len(text) > 50000:
                        text = text[:50000] + "\n...[TRUNCATED]"
                    parts.append(f"[File] **{fname}**\n```\n{text}\n```")
                except Exception as e:
                    parts.append(f"[File] **{fname}** (error reading: {e})")
            elif ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"):
                parts.append(f"[Image] **{fname}** saved at `{fpath}` — use a vision tool if available to analyze this image.")
            elif ext == ".pdf":
                parts.append(f"[PDF] **{fname}** saved at `{fpath}`.")
            else:
                # Binary / unknown — mention path
                size_kb = fpath.stat().st_size / 1024
                parts.append(f"[File] **{fname}** ({size_kb:.1f} KB) saved at `{fpath}`.")

        if not parts:
            return ""

        context = "## Attached Files\n" + "\n\n".join(parts)
        return context

    # ── WebSocket ────────────────────────────────────────────────────────

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        agent = get_agent_loop()
        session_id = str(uuid.uuid4())

        try:
            # Send welcome
            await websocket.send_json({
                "type": "connected",
                "session_id": session_id,
                "version": VERSION,
            })

            while True:
                # Receive message
                data = await websocket.receive_text()
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    await websocket.send_json({"type": "error", "error": "Invalid JSON"})
                    continue

                msg_type = payload.get("type", "message")

                if msg_type == "message":
                    content = payload.get("content", "")
                    if not content.strip() and not payload.get("file_ids"):
                        continue
                    reasoning_effort = payload.get("reasoning_effort")

                    # ── Inject uploaded file context ──
                    file_ids = payload.get("file_ids", [])
                    if file_ids:
                        file_context = _build_file_context(file_ids, UPLOADS_DIR)
                        if file_context:
                            content = file_context + "\n\n" + content if content else file_context

                    # Process through agent loop
                    cancel_event = asyncio.Event()

                    async def process_and_send():
                        try:
                            async for event in agent.process_message(
                                session_id=session_id,
                                user_message=content,
                                stream=True,
                                reasoning_effort=reasoning_effort,
                                cancel_event=cancel_event,
                            ):
                                if cancel_event.is_set():
                                    break
                                await websocket.send_json(event)
                        except Exception as e:
                            logger.exception("[%s] process_message error", APP_NAME)
                            try:
                                await websocket.send_json({"type": "error", "error": str(e)})
                            except Exception:
                                logger.exception("[%s] Failed to send error to client", APP_NAME)

                    task = asyncio.create_task(process_and_send())

                    # Sub-loop: process stop/ping while agent runs in background
                    while not task.done():
                        try:
                            cancel_data = await asyncio.wait_for(
                                websocket.receive_text(), timeout=0.2
                            )
                            cancel_payload = json.loads(cancel_data)
                            cancel_type = cancel_payload.get("type", "")
                            if cancel_type == "stop":
                                cancel_event.set()
                                await websocket.send_json({"type": "done"})
                                break
                            elif cancel_type == "ping":
                                await websocket.send_json({"type": "pong"})
                        except asyncio.TimeoutError:
                            continue
                        except json.JSONDecodeError:
                            continue

                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

                elif msg_type == "stop":
                    # Stop can also arrive outside a message (e.g., user spam-clicked)
                    await websocket.send_json({"type": "done"})

                elif msg_type == "ping":
                    await websocket.send_json({"type": "pong"})

                elif msg_type == "set_session":
                    new_sid = payload.get("session_id", "")
                    if new_sid:
                        session_id = new_sid
                        await websocket.send_json({"type": "session_set", "session_id": session_id})

                elif msg_type == "get_history":
                    limit = payload.get("limit", 50)
                    history = await agent.get_history(session_id, limit=limit)
                    await websocket.send_json({"type": "history", "messages": history})

                elif msg_type == "new_session":
                    session_id = await agent.new_session()
                    await websocket.send_json({"type": "session_created", "session_id": session_id})

                else:
                    await websocket.send_json({"type": "error", "error": f"Unknown message type: {msg_type}"})

        except WebSocketDisconnect:
            pass
        except Exception as e:
            try:
                await websocket.send_json({"type": "error", "error": str(e)})
            except Exception:
                logger.exception("[%s] Failed to send error to client on disconnect", APP_NAME)
        finally:
            logger.info("[%s] WebSocket disconnected: %s", APP_NAME, session_id[:8])

    # ── Static frontend ──────────────────────────────────────────────────

    # Try to find the frontend build directory
    _FRONTEND_CANDIDATES = [
        Path(__file__).resolve().parent.parent / "electron_frontend" / "dist",
    ]

    frontend_dir = None
    for cand in _FRONTEND_CANDIDATES:
        if cand.exists() and (cand / "index.html").exists():
            frontend_dir = cand
            break

    if frontend_dir:
        from fastapi.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

        @app.get("/{full_path:path}")
        async def serve_frontend(full_path: str):
            """Catch-all to serve SPA frontend."""
            file_path = frontend_dir / full_path
            if file_path.exists() and file_path.is_file():
                return FileResponse(str(file_path))
            index = frontend_dir / "index.html"
            if index.exists():
                return FileResponse(str(index))
            raise HTTPException(status_code=404)
    else:
        # No frontend found — that's fine, the API still works
        @app.get("/")
        async def root():
            return {
                "app": APP_NAME,
                "version": VERSION,
                "docs": "/docs",
                "api": "/api/health",
                "note": "Frontend not found. Place built frontend in ./frontend/dist/",
            }


# ── App instance ──────────────────────────────────────────────────────────

app = create_app()


# ── Direct run ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    config = get_config()
    host = config.get("host", DEFAULT_HOST)
    port = config.get("port", DEFAULT_PORT)

    logger.info("[%s] Starting server on %s:%s", APP_NAME, host, port)
    uvicorn.run(
        "jarvis.server:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )
