#!/usr/bin/env python3
"""
Jarvis Mark II — Application Launcher.

Opens the beautiful Three.js WebUI in a native desktop window (default),
or starts as a headless web server, or launches the tkinter GUI.

Usage:
    python run.py                        Default: Three.js WebUI in native window
    python run.py --server               Headless web server (open browser to localhost)
    python run.py --gui                  Alternative tkinter desktop GUI
"""

import sys
import argparse
import logging

logger = logging.getLogger("jarvis")


def main():
    parser = argparse.ArgumentParser(description="Jarvis Mark II")
    parser.add_argument("--server", action="store_true", help="Run as headless web server (no GUI)")
    parser.add_argument("--gui", action="store_true", help="Use the old tkinter GUI instead of WebUI")
    parser.add_argument("--port", type=int, default=0, help="Server port (default: 11711)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Bind address")
    parser.add_argument("--log-level", type=str, default="info", help="Log level")
    args = parser.parse_args()

    if args.gui:
        _run_native_gui()
    elif args.server:
        _run_server(args.host, args.port, args.log_level)
    else:
        _run_desktop(args.host, args.port, args.log_level)


def _run_desktop(host, port, log_level):
    """Launch the Three.js WebUI in a native desktop window (pywebview)."""
    from jarvis.desktop import launch_desktop
    # If no port specified, use the desktop default (11711)
    actual_port = port if port else 11711
    sys.exit(launch_desktop(host=host, port=actual_port, log_level=log_level))


def _run_server(host, port, log_level):
    """Start headless web server."""
    from jarvis.constants import DEFAULT_HOST, DEFAULT_PORT

    cfg_host = host or DEFAULT_HOST
    cfg_port = port or DEFAULT_PORT
    cfg_log = log_level or "info"

    # Free any stale process on the target port
    from jarvis.desktop import _free_port
    _free_port(cfg_host, cfg_port)

    import uvicorn
    uvicorn.run(
        "jarvis.server:app",
        host=cfg_host,
        port=cfg_port,
        log_level=cfg_log,
    )


def _run_native_gui():
    """Launch the alternative tkinter desktop GUI."""
    from jarvis.gui import launch_gui
    sys.exit(launch_gui())


if __name__ == "__main__":
    main()
