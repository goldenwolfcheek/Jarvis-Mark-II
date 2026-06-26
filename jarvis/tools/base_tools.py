"""
Jarvis Mark II — Base / built-in tools.
Core system, filesystem, web, and utility tools registered by default.

Categories used: core, files, web, memory, system
"""

import asyncio
import json
import os
import platform
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

from ..constants import (
    FILE_READ_MAX_CHARS,
    SCREENSHOTS_DIR,
    APPS_FILE,
)
from ..config import get_config
from .registry import get_tool_registry
from ..memory.store import get_memory_store

# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

_HTTP_TIMEOUT = 30.0


def _now() -> str:
    return datetime.now().isoformat()


# ═══════════════════════════════════════════════════════════════════════════
# Core tools
# ═══════════════════════════════════════════════════════════════════════════

def _tool_get_time() -> str:
    """Get the current date, time, and timezone."""
    return json.dumps({
        "datetime": _now(),
        "timezone": time.tzname,
        "unix_ts": time.time(),
    })


def _tool_get_platform() -> str:
    """Get OS / system platform information."""
    return json.dumps({
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "hostname": platform.node(),
        "user": os.environ.get("USERNAME", os.environ.get("USER", "unknown")),
    })


def _tool_get_config(key: Optional[str] = None) -> str:
    """Get Jarvis configuration value(s).

    Args:
        key: Dot-separated config key (e.g. 'model'). If omitted, returns all config.
    """
    config = get_config()
    if key:
        val = config.get(key)
        return json.dumps({key: val})
    return json.dumps(config.get_all(), default=str)


def _tool_set_config(key: str, value: str) -> str:
    """Set a Jarvis configuration value.

    Args:
        key: Dot-separated config key (e.g. 'tts_enabled').
        value: String value (will be parsed to bool/int where applicable).
    """
    config = get_config()
    # Attempt type coercion
    parsed: object = value
    if value.lower() in ("true", "false"):
        parsed = value.lower() == "true"
    else:
        try:
            parsed = int(value)
        except ValueError:
            try:
                parsed = float(value)
            except ValueError:
                parsed = value
    config.set(key, parsed)
    return json.dumps({"status": "ok", "key": key, "value": parsed})


def _tool_echo(message: str) -> str:
    """Echo back a message (useful for testing tool execution).

    Args:
        message: The message to echo.
    """
    return json.dumps({"echo": message})


# ═══════════════════════════════════════════════════════════════════════════
# File tools
# ═══════════════════════════════════════════════════════════════════════════

def _tool_list_files(path: str = ".") -> str:
    """List files and directories at the given path.

    Args:
        path: Directory path to list (default: current working directory).
    """
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return json.dumps({"error": f"Path does not exist: {path}"})
        if not p.is_dir():
            return json.dumps({"error": f"Not a directory: {path}"})

        entries = []
        for entry in sorted(p.iterdir()):
            try:
                stat = entry.stat()
                entries.append({
                    "name": entry.name,
                    "type": "dir" if entry.is_dir() else "file",
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
            except OSError:
                entries.append({"name": entry.name, "type": "unknown"})
        return json.dumps({"path": str(p), "entries": entries})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _tool_read_file(path: str, offset: int = 0, limit: Optional[int] = None) -> str:
    """Read a text file from disk.

    Args:
        path: Absolute or relative path to the file.
        offset: Line number to start reading from (0-indexed, default: 0).
        limit: Maximum number of lines to read. If omitted, reads the whole file.
    """
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return json.dumps({"error": f"File not found: {path}"})
        if not p.is_file():
            return json.dumps({"error": f"Not a file: {path}"})

        content = p.read_text(encoding="utf-8")
        lines = content.splitlines(keepends=True)

        if offset > 0 or limit is not None:
            lines = lines[offset: (offset + limit) if limit else None]

        result = "".join(lines)
        if len(result) > FILE_READ_MAX_CHARS:
            result = result[:FILE_READ_MAX_CHARS] + "\n...[TRUNCATED]"

        return json.dumps({
            "path": str(p),
            "size": len(content),
            "lines": len(content.splitlines()),
            "content": result,
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


def _tool_write_file(path: str, content: str) -> str:
    """Write text content to a file (creates parent directories).

    Args:
        path: Absolute or relative path to the file.
        content: Text content to write.
    """
    try:
        p = Path(path).expanduser().resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return json.dumps({
            "status": "ok",
            "path": str(p),
            "bytes_written": len(content),
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


def _tool_append_file(path: str, content: str) -> str:
    """Append text content to a file (creates if not exists).

    Args:
        path: Absolute or relative path to the file.
        content: Text content to append.
    """
    try:
        p = Path(path).expanduser().resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(content)
        return json.dumps({"status": "ok", "path": str(p)})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _tool_delete_file(path: str) -> str:
    """Delete a file or empty directory.

    Args:
        path: Path to the file or empty directory.
    """
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return json.dumps({"error": f"Path not found: {path}"})
        if p.is_dir():
            p.rmdir()  # only works for empty dirs
        else:
            p.unlink()
        return json.dumps({"status": "ok", "deleted": str(p)})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _tool_search_files(pattern: str, path: str = ".", max_results: int = 50) -> str:
    """Search for files matching a glob pattern.

    Args:
        pattern: Glob pattern (e.g. '*.py', '**/*.txt').
        path: Root directory to search from.
        max_results: Maximum number of results to return.
    """
    try:
        root = Path(path).expanduser().resolve()
        matches = []
        for f in root.rglob(pattern):
            if len(matches) >= max_results:
                break
            try:
                matches.append({
                    "path": str(f.relative_to(root)),
                    "size": f.stat().st_size,
                    "type": "dir" if f.is_dir() else "file",
                })
            except OSError:
                matches.append({"path": str(f.relative_to(root)), "type": "unknown"})
        return json.dumps({"root": str(root), "matches": matches, "count": len(matches)})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ═══════════════════════════════════════════════════════════════════════════
# Web tools
# ═══════════════════════════════════════════════════════════════════════════

async def _tool_http_get(url: str, timeout: int = _HTTP_TIMEOUT) -> str:
    """Make an HTTP GET request.

    Args:
        url: The URL to fetch.
        timeout: Request timeout in seconds (default: 30).
    """
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "Jarvis-Mark-II/2.0"})
            content = resp.text
            if len(content) > FILE_READ_MAX_CHARS:
                content = content[:FILE_READ_MAX_CHARS] + "\n...[TRUNCATED]"
            return json.dumps({
                "status_code": resp.status_code,
                "headers": dict(resp.headers),
                "content": content,
            })
    except Exception as e:
        return json.dumps({"error": str(e)})


def _tool_take_screenshot(filename: Optional[str] = None) -> str:
    """Take a screenshot and save it to the Jarvis screenshots directory.

    Args:
        filename: Optional filename (without extension). Defaults to timestamp.
    """
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    name = filename or f"screenshot_{int(time.time())}.png"
    path = SCREENSHOTS_DIR / name

    try:
        if platform.system() == "Windows":
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            hdc = user32.GetDC(None)
            if not hdc:
                return json.dumps({"error": "Failed to get desktop DC"})

            width = user32.GetSystemMetrics(0)
            height = user32.GetSystemMetrics(1)

            # Use PIL or MSS if available, else fallback
            try:
                import mss
                with mss.mss() as sct:
                    sct.shot(output=str(path))
                return json.dumps({"status": "ok", "path": str(path), "width": width, "height": height})
            except ImportError:
                pass

            try:
                from PIL import ImageGrab
                img = ImageGrab.grab()
                img.save(path)
                return json.dumps({"status": "ok", "path": str(path), "width": img.width, "height": img.height})
            except ImportError:
                pass

            return json.dumps({"error": "No screenshot library available. Install mss or Pillow."})
        else:
            # Linux/macOS — try import
            try:
                import mss
                with mss.mss() as sct:
                    sct.shot(output=str(path))
                return json.dumps({"status": "ok", "path": str(path)})
            except ImportError:
                pass

            # Try scrot / screencapture
            cmd = ["screencapture", "-x", str(path)] if platform.system() == "Darwin" else ["scrot", str(path)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return json.dumps({"status": "ok", "path": str(path)})
            return json.dumps({"error": f"Screenshot failed: {result.stderr.strip()}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ═══════════════════════════════════════════════════════════════════════════
# Registered apps
# ═══════════════════════════════════════════════════════════════════════════

def _tool_get_registered_apps() -> str:
    """List all registered applications from the registered_apps.json file."""
    try:
        if APPS_FILE.exists():
            data = json.loads(APPS_FILE.read_text(encoding="utf-8"))
            return json.dumps({"apps": data, "count": len(data)})
        return json.dumps({"apps": [], "count": 0})
    except Exception as e:
        return json.dumps({"error": str(e), "apps": []})


def _tool_register_app(name: str, path: str, category: str = "general") -> str:
    """Register an application so Jarvis can launch it later.

    Args:
        name: A friendly name for the app (e.g. 'Visual Studio Code').
        path: The executable path or shell command.
        category: Optional category (e.g. 'dev', 'browser', 'media').
    """
    try:
        apps = []
        if APPS_FILE.exists():
            apps = json.loads(APPS_FILE.read_text(encoding="utf-8"))

        # Update or append
        entry = {"name": name, "path": path, "category": category}
        for i, app in enumerate(apps):
            if app.get("name") == name:
                apps[i] = entry
                break
        else:
            apps.append(entry)

        APPS_FILE.parent.mkdir(parents=True, exist_ok=True)
        APPS_FILE.write_text(json.dumps(apps, indent=2), encoding="utf-8")
        return json.dumps({"status": "ok", "app": entry})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ═══════════════════════════════════════════════════════════════════════════
# Memory tools
# ═══════════════════════════════════════════════════════════════════════════

def _tool_save_fact(key: str, value: str) -> str:
    """Save a specific fact about the user for future reference.

    Args:
        key: The category or label for the fact (e.g. 'name', 'occupation', 'favourite_colour').
        value: The value of the fact.
    """
    try:
        store = get_memory_store()
        store.append_memory(text=f"{key}: {value}")
        return json.dumps({"status": "ok", "fact": {"key": key, "value": value}})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _tool_remember(text: str) -> str:
    """Save important information for future reference into long-term memory.

    Args:
        text: The information to remember.
    """
    try:
        store = get_memory_store()
        store.append_memory(text)
        return json.dumps({"status": "ok", "remembered": text[:100] + ("..." if len(text) > 100 else "")})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ═══════════════════════════════════════════════════════════════════════════
# Loader
# ═══════════════════════════════════════════════════════════════════════════

def load_base_tools():
    """Register all base/built-in tools into the global registry."""
    registry = get_tool_registry()

    # ── Core ──
    registry.register_fn(_tool_get_time, category="core")
    registry.register_fn(_tool_get_platform, category="core")
    registry.register_fn(_tool_get_config, category="core")
    registry.register_fn(_tool_set_config, category="core")
    registry.register_fn(_tool_echo, category="core")

    # ── Files ──
    registry.register_fn(_tool_list_files, category="files")
    registry.register_fn(_tool_read_file, category="files")
    registry.register_fn(_tool_write_file, category="files")
    registry.register_fn(_tool_append_file, category="files")
    registry.register_fn(_tool_delete_file, category="files")
    registry.register_fn(_tool_search_files, category="files")

    # ── Web ──
    registry.register_fn(
        _tool_http_get,
        name="http_get",
        category="web",
        description="Make an HTTP GET request to a URL and return the response.",
    )

    # ── System / Screenshot ──
    registry.register_fn(_tool_take_screenshot, category="system")

    # ── Apps ──
    registry.register_fn(_tool_get_registered_apps, category="system")
    registry.register_fn(_tool_register_app, category="system")

    # ── Memory ──
    registry.register_fn(
        _tool_save_fact,
        name="save_fact",
        category="memory",
        description="Save a specific fact about the user for future reference.",
    )
    registry.register_fn(
        _tool_remember,
        name="remember",
        category="memory",
        description="Save important information for future reference into long-term memory.",
    )
