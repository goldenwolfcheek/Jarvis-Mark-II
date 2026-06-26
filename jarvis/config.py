"""
Jarvis Mark II — Configuration system.
YAML-based config with deep-merge defaults, provider management.
Inspired by Hermes Agent's config system.
"""

import os
import yaml
import threading
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from .constants import DEFAULT_CONFIG_YAML, CONFIG_FILE

logger = logging.getLogger(__name__)


class Config:
    """Thread-safe config loader with deep-merge defaults."""

    def __init__(self):
        self._lock = threading.RLock()
        self._data: Dict[str, Any] = {}
        self._mtime: float = 0
        self._load()

    # ── Loading ───────────────────────────────────────────────────────────

    def _load(self):
        """Load config from disk, merging over defaults."""
        defaults = yaml.safe_load(DEFAULT_CONFIG_YAML) or {}

        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    user_config = yaml.safe_load(f) or {}
                self._mtime = CONFIG_FILE.stat().st_mtime
            except (yaml.YAMLError, OSError) as e:
                logger.warning("[Jarvis] Corrupt config at %s, using defaults. (%s)", CONFIG_FILE, e)
                user_config = {}
        else:
            user_config = {}
            self._save_defaults(defaults)

        self._data = self._deep_merge(defaults, user_config)

    def _save_defaults(self, defaults: dict):
        """Write default config file if none exists."""
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            yaml.dump(defaults, f, default_flow_style=False, allow_unicode=True)

    def _deep_merge(self, base: dict, override: dict) -> dict:
        """Recursively merge override into base."""
        result = dict(base)
        for key, val in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(val, dict):
                result[key] = self._deep_merge(result[key], val)
            elif val is not None:
                result[key] = val
        return result

    def reload(self):
        """Reload config from disk if modified."""
        with self._lock:
            if CONFIG_FILE.exists() and CONFIG_FILE.stat().st_mtime != self._mtime:
                self._load()

    # ── Read access ───────────────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """Get a dot-separated config value (e.g. 'agent.max_turns')."""
        with self._lock:
            parts = key.split(".")
            val = self._data
            for part in parts:
                if isinstance(val, dict):
                    val = val.get(part)
                else:
                    return default
            return val if val is not None else default

    def get_all(self) -> dict:
        """Return a copy of the full config dict."""
        with self._lock:
            return dict(self._data)

    # ── Write access ──────────────────────────────────────────────────────

    def set(self, key: str, value: Any):
        """Set a value and persist to disk."""
        with self._lock:
            parts = key.split(".")
            cursor = self._data
            for part in parts[:-1]:
                if part not in cursor or not isinstance(cursor[part], dict):
                    cursor[part] = {}
                cursor = cursor[part]
            cursor[parts[-1]] = value
            self._persist()

    def update(self, updates: dict):
        """Merge a dict of changes and persist."""
        with self._lock:
            self._data = self._deep_merge(self._data, updates)
            self._persist()

    def _persist(self):
        """Write current config to disk atomically."""
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CONFIG_FILE.with_suffix(".yaml.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            yaml.dump(self._data, f, default_flow_style=False, allow_unicode=True)
        tmp.replace(CONFIG_FILE)
        self._mtime = CONFIG_FILE.stat().st_mtime if CONFIG_FILE.exists() else 0

    # ── Provider helpers ──────────────────────────────────────────────────

    def get_providers(self) -> dict:
        """Get the providers dict from config."""
        return self.get("providers", {})

    def get_provider(self, name: str) -> Optional[dict]:
        """Get a specific provider config by name."""
        providers = self.get_providers()
        return providers.get(name)

    def get_active_provider(self) -> str:
        """Return the currently active provider name."""
        return self.get("provider", "opencode-zen")

    def get_active_model(self) -> str:
        """Return the currently active model."""
        return self.get("model", "big-pickle")

    def set_active_provider(self, name: str):
        """Set the active provider."""
        self.set("provider", name)

    def set_active_model(self, model: str):
        """Set the active model."""
        self.set("model", model)

    def save_provider_key(self, provider: str, api_key: str):
        """Save an API key for a specific provider."""
        self.set(f"providers.{provider}.api_key", api_key)

    def get_provider_key(self, provider: str) -> Optional[str]:
        """Get the API key for a provider."""
        return self.get(f"providers.{provider}.api_key")


# ── Singleton ────────────────────────────────────────────────────────────
_config_instance: Optional[Config] = None
_config_lock = threading.Lock()


def get_config() -> Config:
    """Return the global Config singleton."""
    global _config_instance
    if _config_instance is None:
        with _config_lock:
            if _config_instance is None:
                _config_instance = Config()
    return _config_instance
