"""
Jarvis Mark II — Provider registry singleton.

Loads built-in profiles, merges them with user config overrides,
and provides a single ``get()`` / ``list()`` / ``get_default()``
interface for the rest of the application.
"""

from __future__ import annotations

import threading
from typing import Any

from ..config import get_config
from .base import ProviderProfile
from .profiles import BUILTIN_PROFILES


class ProviderRegistry:
    """Singleton registry of available provider profiles.

    Initialisation order
    --------------------
    1. Start with all built-in profiles from ``profiles.py``.
    2. Merge user config overrides (``config.providers.<name>.*``).
    3. Add any user-defined providers that have no built-in counterpart.

    Thread-safe via an RLock.
    """

    _instance: ProviderRegistry | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._rl = threading.RLock()
        self._profiles: dict[str, ProviderProfile] = {}
        self._loaded = False

    # ── Singleton ───────────────────────────────────────────────────────────

    @classmethod
    def get_instance(cls, force_reload: bool = False) -> ProviderRegistry:
        """Return the global registry singleton.

        Args:
            force_reload: If True, re-initialise from config even if already
                          loaded (useful after config changes).
        """
        if cls._instance is None or force_reload:
            with cls._lock:
                if cls._instance is None or force_reload:
                    inst = cls()
                    inst._load()
                    cls._instance = inst
        return cls._instance  # type: ignore[return-value]

    # ── Loading ─────────────────────────────────────────────────────────────

    def _load(self) -> None:
        """Load profiles from built-ins merged with user config."""
        with self._rl:
            self._profiles = {}

            # 1. Seed with built-in profiles (shallow copy so we don't mutate originals)
            for name, profile in BUILTIN_PROFILES.items():
                self._profiles[name] = ProviderProfile(
                    name=profile.name,
                    api_mode=profile.api_mode,
                    env_vars=profile.env_vars,
                    base_url=profile.base_url,
                    auth_type=profile.auth_type,
                    supports_vision=profile.supports_vision,
                    fallback_models=profile.fallback_models,
                    display_name=profile.display_name,
                    description=profile.description,
                )

            # 2. Merge user config overrides
            config = get_config()
            provider_configs: dict[str, dict[str, Any]] = config.get("providers", {})

            for name, overrides in provider_configs.items():
                if not isinstance(overrides, dict):
                    continue
                if name in self._profiles:
                    self._merge_into(self._profiles[name], overrides)
                else:
                    # User-defined provider not in built-ins
                    self._profiles[name] = self._profile_from_config(name, overrides)

            self._loaded = True

    @staticmethod
    def _merge_into(profile: ProviderProfile, overrides: dict[str, Any]) -> None:
        """Apply config overrides to an existing profile in-place."""
        if "base_url" in overrides and overrides["base_url"]:
            profile.base_url = overrides["base_url"]
        if "api_key" in overrides and overrides["api_key"]:
            # api_key in config is stored separately from env_vars;
            # users also set key via config.set()
            pass  # Handled at runtime by security.resolve_api_key / LLMCore
        if "auth_type" in overrides and overrides["auth_type"]:
            profile.auth_type = overrides["auth_type"]
        if "supports_vision" in overrides:
            profile.supports_vision = bool(overrides["supports_vision"])
        if "fallback_models" in overrides and overrides["fallback_models"]:
            profile.fallback_models = tuple(overrides["fallback_models"])
        if "display_name" in overrides and overrides["display_name"]:
            profile.display_name = overrides["display_name"]
        if "description" in overrides and overrides["description"]:
            profile.description = overrides["description"]
        if "env_vars" in overrides and overrides["env_vars"]:
            profile.env_vars = tuple(overrides["env_vars"])

    @staticmethod
    def _profile_from_config(name: str, cfg: dict[str, Any]) -> ProviderProfile:
        """Build a profile from a user-defined config dict (no built-in counterpart)."""
        return ProviderProfile(
            name=name,
            api_mode=cfg.get("api_mode", "chat_completions"),
            env_vars=tuple(cfg.get("env_vars", [])),
            base_url=cfg.get("base_url", ""),
            auth_type=cfg.get("auth_type", "api_key"),
            supports_vision=bool(cfg.get("supports_vision", False)),
            fallback_models=tuple(cfg.get("fallback_models", [])),
            display_name=cfg.get("display_name", name.title()),
            description=cfg.get("description", ""),
        )

    # ── Query ───────────────────────────────────────────────────────────────

    def get(self, name: str) -> ProviderProfile | None:
        """Return the profile for *name*, or None."""
        with self._rl:
            return self._profiles.get(name)

    def list(self) -> list[ProviderProfile]:
        """Return all registered profiles, sorted by display_name."""
        with self._rl:
            profiles = list(self._profiles.values())
            profiles.sort(key=lambda p: (p.display_name or p.name).lower())
            return profiles

    def get_default(self) -> ProviderProfile | None:
        """Return the profile matching the active provider in config."""
        config = get_config()
        active = config.get_active_provider()
        with self._rl:
            return self._profiles.get(active)

    def names(self) -> list[str]:
        """Return sorted list of registered provider names."""
        with self._rl:
            return sorted(self._profiles.keys())

    def reload(self) -> None:
        """Force-reload profiles from config (thread-safe)."""
        with self._rl:
            self._load()

    def __contains__(self, name: str) -> bool:
        with self._rl:
            return name in self._profiles

    def __len__(self) -> int:
        with self._rl:
            return len(self._profiles)

    def __repr__(self) -> str:
        with self._rl:
            return f"<ProviderRegistry profiles={list(self._profiles)}>"
