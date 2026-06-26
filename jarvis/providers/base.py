"""
Jarvis Mark II — ProviderProfile base dataclass.

A single declarative description of an inference provider:
auth method, endpoint, capabilities, and fallback model list.
Inspired by Hermes Agent's provider profile system but kept
simple for Jarvis's OpenAI-compatible LLMCore transport.

Profiles are *data*, not clients — they let the rest of the
system discover what a provider supports without hardcoding
URLs or env-var names in business logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderProfile:
    """Declarative description of an LLM inference provider.

    Fields
    ------
    name : str
        Machine-friendly identifier (e.g. ``"openai"``, ``"ollama"``).
        Used as the key in config lookups and as the ``provider``
        argument to ``LLMCore``.
    api_mode : str
        API protocol family.  ``"chat_completions"`` (OpenAI-compatible)
        is the default.  Reserved for future non-compatible modes.
    env_vars : tuple[str, ...]
        Environment variable names that this provider checks for an API
        key, in order of precedence.  First non-empty var wins.
    base_url : str
        Root URL of the provider's API (e.g.
        ``"https://api.openai.com/v1"``).  The transport appends
        ``/chat/completions`` for inference.
    auth_type : str
        Authentication method.  One of:
        - ``"api_key"`` — Bearer token in the Authorization header.
        - ``"none"``    — No auth (local models, Ollama, etc.).
    supports_vision : bool
        Whether the provider's API accepts ``image_url`` content parts
        in messages.
    fallback_models : tuple[str, ...]
        Curated list of model IDs to show in a model picker when a live
        catalog fetch fails or isn't supported.
    display_name : str
        Human-readable label (e.g. ``"OpenAI"``) for UIs and logs.
    description : str
        Short subtitle (e.g. ``"GPT-4o & friends via OpenAI API"``).
    """

    # ── Identity ──────────────────────────────────────────────────────────
    name: str
    api_mode: str = "chat_completions"

    # ── Auth & endpoints ──────────────────────────────────────────────────
    env_vars: tuple[str, ...] = field(default_factory=tuple)
    base_url: str = ""
    auth_type: str = "api_key"  # "api_key" | "none"

    # ── Capabilities ──────────────────────────────────────────────────────
    supports_vision: bool = False
    fallback_models: tuple[str, ...] = field(default_factory=tuple)

    # ── Human-readable metadata ───────────────────────────────────────────
    display_name: str = ""
    description: str = ""

    # ── Convenience ───────────────────────────────────────────────────────

    def requires_auth(self) -> bool:
        """Return True if this provider needs an API key."""
        return self.auth_type == "api_key"

    def resolve_api_key(self) -> str | None:
        """Return the first non-empty env var matching *env_vars*, or None."""
        import os

        for var in self.env_vars:
            val = os.environ.get(var)
            if val:
                return val
        return None

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dict representation (useful for serialisation)."""
        return {
            "name": self.name,
            "api_mode": self.api_mode,
            "env_vars": list(self.env_vars),
            "base_url": self.base_url,
            "auth_type": self.auth_type,
            "supports_vision": self.supports_vision,
            "fallback_models": list(self.fallback_models),
            "display_name": self.display_name,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProviderProfile":
        """Create a profile from a dict (inverse of *to_dict*)."""
        return cls(
            name=data.get("name", ""),
            api_mode=data.get("api_mode", "chat_completions"),
            env_vars=tuple(data.get("env_vars", [])),
            base_url=data.get("base_url", ""),
            auth_type=data.get("auth_type", "api_key"),
            supports_vision=bool(data.get("supports_vision", False)),
            fallback_models=tuple(data.get("fallback_models", [])),
            display_name=data.get("display_name", ""),
            description=data.get("description", ""),
        )
