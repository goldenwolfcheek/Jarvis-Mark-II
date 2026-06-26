"""
Jarvis Mark II — Tool Registry.
Decorator-based registry for agent-callable tools with execution limits,
error handling, and OpenAI-compatible schema generation.

Inspired by Hermes Agent's tool registration pattern.
"""

import asyncio
import inspect
import json
import threading
import time
import traceback
from functools import wraps
from typing import Any, Callable, Optional

from ..constants import TOOL_OUTPUT_MAX_CHARS, MAX_TOOL_TURNS


class Tool:
    """Wrapper around a tool function with its metadata and execution logic."""

    def __init__(
        self,
        name: str,
        fn: Callable,
        description: str = "",
        parameters: Optional[dict] = None,
        category: str = "general",
        requires_confirmation: bool = False,
        is_async: bool = False,
    ):
        self.name = name
        self.fn = fn
        self.description = description
        self.parameters = parameters or {"type": "object", "properties": {}, "required": []}
        self.category = category
        self.requires_confirmation = requires_confirmation
        self.is_async = is_async

    def to_openai_schema(self) -> dict:
        """Return an OpenAI-compatible tool definition."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    async def execute(self, **kwargs: Any) -> str:
        """Execute the tool with the given arguments.

        Returns a string result (truncated to TOOL_OUTPUT_MAX_CHARS).
        Handles both sync and async functions transparently.
        """
        try:
            if self.is_async:
                result = await self.fn(**kwargs)
            else:
                result = await asyncio.to_thread(self.fn, **kwargs)

            if result is None:
                result = ""
            elif not isinstance(result, str):
                result = json.dumps(result, ensure_ascii=False, default=str)

            if len(result) > TOOL_OUTPUT_MAX_CHARS:
                result = result[:TOOL_OUTPUT_MAX_CHARS] + "\n[TRUNCATED: output exceeds character limit]"
            return result
        except Exception as exc:
            tb = traceback.format_exc()
            return json.dumps({
                "error": str(exc),
                "traceback": tb,
                "tool": self.name,
            })

    def __repr__(self) -> str:
        return f"Tool(name='{self.name}', category='{self.category}')"


class ToolRegistry:
    """Thread-safe registry for discoverable, callable tools."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._lock = threading.RLock()
        self._turn_count = 0

    # ── Registration ──────────────────────────────────────────────────────

    def register(self, tool: Tool):
        """Register a Tool instance."""
        with self._lock:
            self._tools[tool.name] = tool

    def register_fn(
        self,
        fn: Optional[Callable] = None,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        parameters: Optional[dict] = None,
        category: str = "general",
        requires_confirmation: bool = False,
    ) -> Callable:
        """Decorator that registers a function as a tool.

        Can be used with or without arguments::

            @registry.register_fn
            def my_tool(...): ...

            @registry.register_fn(name="custom", category="web")
            def my_tool(...): ...
        """

        def decorator(func: Callable) -> Callable:
            tool_name = name or func.__name__
            tool_desc = description or func.__doc__ or ""
            tool_params = parameters or self._infer_params(func)
            is_async = inspect.iscoroutinefunction(func)

            tool = Tool(
                name=tool_name,
                fn=func,
                description=tool_desc.strip(),
                parameters=tool_params,
                category=category,
                requires_confirmation=requires_confirmation,
                is_async=is_async,
            )
            self.register(tool)
            return func

        if fn is not None:
            return decorator(fn)
        return decorator

    def unregister(self, name: str):
        """Remove a tool from the registry."""
        with self._lock:
            self._tools.pop(name, None)

    def clear(self):
        """Remove all registered tools."""
        with self._lock:
            self._tools.clear()
            self._turn_count = 0

    # ── Query ─────────────────────────────────────────────────────────────

    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        with self._lock:
            return self._tools.get(name)

    def get_all(self) -> list[Tool]:
        """Return all registered tools."""
        with self._lock:
            return list(self._tools.values())

    def get_names(self) -> list[str]:
        """Return names of all registered tools."""
        with self._lock:
            return list(self._tools.keys())

    def get_by_category(self, category: str) -> list[Tool]:
        """Filter tools by category."""
        with self._lock:
            return [t for t in self._tools.values() if t.category == category]

    def has_tool(self, name: str) -> bool:
        """Check if a tool is registered."""
        with self._lock:
            return name in self._tools

    def count(self) -> int:
        """Return total number of registered tools."""
        with self._lock:
            return len(self._tools)

    # ── Execution ─────────────────────────────────────────────────────────

    async def execute(self, name: str, arguments: dict[str, Any] | None = None) -> str:
        """Execute a tool by name with the given arguments dict.

        Enforces MAX_TOOL_TURNS and returns the tool result string.
        Accepts arguments as a dict (rather than **kwargs) to avoid Python
        method-signature clashes when a tool parameter is itself named 'name'.
        """
        tool = self.get(name)
        if tool is None:
            return json.dumps({"error": f"Unknown tool '{name}'. Available: {self.get_names()}"})

        with self._lock:
            self._turn_count += 1
            if self._turn_count > MAX_TOOL_TURNS:
                return json.dumps({
                    "error": f"Tool execution limit ({MAX_TOOL_TURNS}) reached. Please summarize and stop.",
                    "tool": name,
                })

        return await tool.execute(**(arguments or {}))

    def reset_turn_count(self):
        """Reset the tool turn counter (e.g., at start of a new turn)."""
        with self._lock:
            self._turn_count = 0

    # ── Schema generation ─────────────────────────────────────────────────

    def get_tool_definitions(self, categories: Optional[list[str]] = None) -> list[dict]:
        """Get OpenAI-compatible tool definitions, optionally filtered by category."""
        tools = self.get_all()
        if categories:
            tools = [t for t in tools if t.category in categories]
        return [t.to_openai_schema() for t in tools]

    # ── Parameter inference ───────────────────────────────────────────────

    @staticmethod
    def _infer_params(func: Callable) -> dict:
        """Infer JSON schema from function signature."""
        sig = inspect.signature(func)
        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue

            # Determine type
            param_type = "string"
            if param.annotation is not inspect.Parameter.empty:
                ann = param.annotation
                origin = getattr(ann, "__origin__", None)
                if origin is list:
                    param_type = "array"
                elif origin is dict:
                    param_type = "object"
                else:
                    name_map = {
                        "str": "string",
                        "int": "integer",
                        "float": "number",
                        "bool": "boolean",
                        "list": "array",
                        "dict": "object",
                        "Any": "string",
                    }
                    ann_str = getattr(ann, "__name__", str(ann))
                    param_type = name_map.get(ann_str, "string")

            description = f"Parameter '{param_name}'"
            param_schema = {"type": param_type, "description": description}

            # Add enum hints from Literal types
            args = getattr(origin, "__args__", None) if origin else None
            if args and origin is not None:
                try:
                    param_schema["enum"] = list(args)
                except Exception:
                    pass

            properties[param_name] = param_schema
            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }


# ── Convenience decorator (uses global registry) ──────────────────────────
_registry_instance: Optional[ToolRegistry] = None
_registry_lock = threading.Lock()


def get_tool_registry() -> ToolRegistry:
    """Return the global ToolRegistry singleton."""
    global _registry_instance
    if _registry_instance is None:
        with _registry_lock:
            if _registry_instance is None:
                _registry_instance = ToolRegistry()
    return _registry_instance


def tool(
    fn: Optional[Callable] = None,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    parameters: Optional[dict] = None,
    category: str = "general",
    requires_confirmation: bool = False,
) -> Callable:
    """``@tool`` decorator that registers into the global ToolRegistry.

    Usage::

        @tool
        def my_func(...): ...

        @tool(name="custom", category="web")
        async def my_async_func(...): ...
    """
    registry = get_tool_registry()
    return registry.register_fn(
        fn,
        name=name,
        description=description,
        parameters=parameters,
        category=category,
        requires_confirmation=requires_confirmation,
    )
