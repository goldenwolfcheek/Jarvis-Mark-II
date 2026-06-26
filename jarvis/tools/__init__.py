"""Jarvis Mark II — Tools package.
Registry-driven tool system for agent function calling.
"""

import importlib
import inspect
import pkgutil
import sys
from pathlib import Path

from .registry import ToolRegistry, tool, get_tool_registry
from .base_tools import load_base_tools
from .pc_control import load_pc_control_tools
from .web_tools import load_web_tools

__all__ = [
    "ToolRegistry",
    "tool",
    "get_tool_registry",
    "load_base_tools",
    "load_pc_control_tools",
    "load_web_tools",
    "discover_tools",
]


def discover_tools() -> int:
    """Auto-discover and load all tool modules in the ``jarvis/tools/`` package.

    Scans every ``.py`` module in this package and calls any function whose
    name starts with ``load_`` and ends with ``_tools`` (e.g. ``load_base_tools``,
    ``load_pc_control_tools``, ``load_web_tools``).

    Returns the total number of tools registered after discovery.
    """
    registry = get_tool_registry()
    this_package = __name__  # "jarvis.tools"

    # Modules already loaded explicitly — call their loaders directly
    # so we don't double-scan them.
    explicit_loaders = [load_base_tools, load_pc_control_tools, load_web_tools]
    for loader in explicit_loaders:
        loader()

    # Auto-discover additional tool modules (skills, plugins, third-party)
    pkg_path = Path(__file__).parent
    for importer, mod_name, is_pkg in pkgutil.iter_modules([str(pkg_path)]):
        if mod_name.startswith("_") or is_pkg:
            continue
        full_name = f"{this_package}.{mod_name}"
        if full_name in sys.modules:
            continue  # already imported above

        try:
            module = importlib.import_module(full_name)
            for attr_name in dir(module):
                if attr_name.startswith("load_") and attr_name.endswith("_tools"):
                    loader_fn = getattr(module, attr_name)
                    if inspect.isfunction(loader_fn):
                        loader_fn()
        except Exception:
            pass  # best-effort; skip broken modules

    return registry.count()
