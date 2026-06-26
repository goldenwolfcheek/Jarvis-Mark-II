"""
Jarvis Mark II — Desktop Native Window Wrapper.
Wraps the FastAPI web UI in a native desktop window using pywebview.
No browser tabs needed — looks and feels like a real desktop application.
"""

import io
import json
import logging
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("jarvis.desktop")

# ── Globals ────────────────────────────────────────────────────────────────
_server_thread: Optional[threading.Thread] = None


# ── Port management ────────────────────────────────────────────────────────

def _find_pid_on_port(host: str, port: int) -> Optional[str]:
    """Return the PID of any process listening on host:port, or None."""
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        target = f"{host}:{port}"
        for line in result.stdout.splitlines():
            if target in line and "LISTEN" in line:
                parts = line.strip().split()
                if parts:
                    pid = parts[-1].strip()
                    if pid.isdigit():
                        return pid
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def _free_port(host: str, port: int):
    """Kill any process listening on host:port (Windows taskkill)."""
    pid = _find_pid_on_port(host, port)
    if pid is None:
        return  # port already free

    logger.warning(
        f"Port {port} is held by PID {pid}. Killing it..."
    )
    try:
        subprocess.run(
            ["taskkill", "/F", "/PID", pid],
            capture_output=True,
            text=True,
            timeout=5,
        )
        time.sleep(0.5)
        if _find_pid_on_port(host, port) is None:
            logger.info(f"Freed port {port} (killed PID {pid})")
        else:
            logger.error(f"Failed to kill PID {pid} on port {port}")
    except subprocess.TimeoutExpired:
        logger.error(f"Timeout killing PID {pid} on port {port}")


# ── Port readiness polling ────────────────────────────────────────────────

def _is_port_open(host: str, port: int) -> bool:
    """Return True if a TCP connection to host:port succeeds."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        return s.connect_ex((host, port)) == 0


def _wait_for_port(
    host: str, port: int, timeout: float = 8.0, interval: float = 0.3
) -> bool:
    """Poll until port is accepting connections, or return False on timeout."""
    start = time.time()
    while time.time() - start < timeout:
        if _is_port_open(host, port):
            return True
        time.sleep(interval)
    return False


# ── Server thread ──────────────────────────────────────────────────────────

def _start_server(host: str, port: int, log_level: str):
    """Start uvicorn server in a background thread.

    Does NOT signal readiness — the main thread discovers readiness
    by polling the port + health endpoint.
    """
    os.environ["UVICORN_NO_SIGNAL"] = "1"

    import uvicorn

    config = uvicorn.Config(
        "jarvis.server:app",
        host=host,
        port=port,
        log_level=log_level,
        reload=False,
    )
    server = uvicorn.Server(config)

    try:
        server.run()
    except Exception as e:
        logger.error(f"Server error: {e}")


# ── Desktop launcher ───────────────────────────────────────────────────────

def launch_desktop(
    host: str = "127.0.0.1",
    port: int = 11711,
    title: str = "Jarvis Mark II",
    width: int = 1200,
    height: int = 800,
    min_width: int = 800,
    min_height: int = 600,
    log_level: str = "info",
    icon_path: Optional[str] = None,
    fullscreen: bool = False,
    resizable: bool = True,
    frameless: bool = False,
) -> int:
    """Launch Jarvis as a native desktop application.

    Kills any stale process on the target port, starts the FastAPI
    server in a background thread, polls until it is ready, opens a
    native pywebview window with the Three.js UI, and keeps the server
    alive until the window closes.

    Args:
        host: Server bind address (default: 127.0.0.1)
        port: Server port (default: 11711)
        title: Window title (default: "Jarvis Mark II")
        width: Window width (default: 1200)
        height: Window height (default: 800)
        min_width: Minimum window width (default: 800)
        min_height: Minimum window height (default: 600)
        log_level: Logging level (default: "info")
        icon_path: Path to window icon file (optional)
        fullscreen: Start fullscreen (default: False)
        resizable: Allow window resize (default: True)
        frameless: Frameless window (default: False)

    Returns:
        Exit code (0 = success, nonzero = error)
    """
    global _server_thread

    # ── Ensure port is free ────────────────────────────────────────────────
    _free_port(host, port)

    # ── Start server thread ────────────────────────────────────────────────
    logger.info(f"Starting server on {host}:{port}...")
    _server_thread = threading.Thread(
        target=_start_server,
        args=(host, port, log_level),
        daemon=True,
        name="jarvis-server",
    )
    _server_thread.start()

    # ── Wait for server to actually bind and respond ───────────────────────
    logger.info("Waiting for server to become ready...")
    if not _wait_for_port(host, port, timeout=8.0):
        logger.error(
            f"Server did not start within 8 seconds. "
            f"Port {port} may be blocked or inaccessible."
        )
        return 1

    # Verify the health endpoint responds correctly
    try:
        import httpx

        for attempt in range(3):
            try:
                resp = httpx.get(
                    f"http://{host}:{port}/api/health", timeout=2
                )
                if resp.status_code == 200:
                    logger.info("Server is healthy and ready")
                    break
            except (httpx.HTTPError, httpx.ConnectError):
                time.sleep(0.5)
        else:
            logger.warning("Server health check did not return 200 OK")
    except Exception as e:
        logger.warning(f"Server health check failed (server may still work): {e}")

    # ── Launch native window ───────────────────────────────────────────────
    import webview

    window_kwargs = {
        "url": f"http://{host}:{port}",
        "title": title,
        "width": width,
        "height": height,
        "resizable": resizable,
        "fullscreen": fullscreen,
        "min_size": (min_width, min_height),
    }

    if icon_path and Path(icon_path).exists():
        window_kwargs["icon"] = icon_path

    if frameless:
        window_kwargs["frameless"] = True

    logger.info(f"Opening desktop window ({width}x{height})...")
    webview.create_window(**window_kwargs)
    # webview.start() blocks until window closes
    webview.start()

    logger.info("Desktop window closed. Shutting down server...")
    return 0


# ── CLI Entry ──────────────────────────────────────────────────────────────

def main():
    """CLI entry for `python -m jarvis.desktop`."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Jarvis Mark II — Desktop Native Application",
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="Server host (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port", type=int, default=11711, help="Server port (default: 11711)"
    )
    parser.add_argument(
        "--title", default="Jarvis Mark II", help="Window title"
    )
    parser.add_argument(
        "--width", type=int, default=1200, help="Window width (default: 1200)"
    )
    parser.add_argument(
        "--height", type=int, default=800, help="Window height (default: 800)"
    )
    parser.add_argument(
        "--log-level",
        default="info",
        choices=["debug", "info", "warning", "error"],
        help="Logging level (default: info)",
    )
    parser.add_argument(
        "--fullscreen", action="store_true", help="Start fullscreen"
    )
    parser.add_argument(
        "--frameless", action="store_true", help="Frameless window"
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Install dependencies from requirements.txt and exit",
    )

    args = parser.parse_args()

    if args.install:
        _install_deps()
        return

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="[Jarvis] %(levelname)s: %(message)s",
    )

    sys.exit(
        launch_desktop(
            host=args.host,
            port=args.port,
            title=args.title,
            width=args.width,
            height=args.height,
            log_level=args.log_level,
            fullscreen=args.fullscreen,
            frameless=args.frameless,
        )
    )


def _install_deps():
    """Install dependencies using pip or uv."""
    req_path = Path(__file__).resolve().parent.parent / "requirements.txt"
    if not req_path.exists():
        print("[Jarvis] requirements.txt not found")
        return

    print("[Jarvis] Installing dependencies...")
    try:
        import subprocess

        subprocess.check_call(
            [sys.executable, "-m", "uv", "pip", "install", "-r", str(req_path)]
        )
        print("[Jarvis] Dependencies installed via uv")
    except Exception:
        try:
            import subprocess

            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "-r", str(req_path)]
            )
            print("[Jarvis] Dependencies installed via pip")
        except Exception as e:
            print(f"[Jarvis] Failed to install dependencies: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
