"""
Jarvis Mark II — Model Discovery.
Queries OpenAI-compatible API endpoints to list available models.
Uses ProviderRegistry for base URL and auth resolution.
"""

import json
from typing import Optional

import httpx

from ..config import get_config
from ..providers import ProviderRegistry
from ..security import resolve_api_key

_TIMEOUT = 15.0


class ModelDiscovery:
    """Discover available models from any OpenAI-compatible provider.

    Resolves provider settings via ProviderRegistry (Hermes-style profiles)
    with fallback to legacy config format.

    Usage::

        discovery = ModelDiscovery()
        models = await discovery.discover("ollama")
        models = await discovery.discover("openai")
    """

    @staticmethod
    async def discover(provider: Optional[str] = None) -> list[dict]:
        """Fetch available models from a provider.

        Args:
            provider: Provider name (e.g. 'ollama', 'openai').
                      If None, uses the active provider.

        Returns:
            List of model dicts with keys: id, name, provider.
            Returns empty list on error.
        """
        config = get_config()
        provider_name = provider or config.get_active_provider()

        # Check if provider has fallback_models configured — these act as
        # a whitelist of known-accessible models. When present, return them
        # directly instead of querying the provider's API (which may return
        # models the user lacks access/tokens for).
        registry = ProviderRegistry.get_instance()
        profile = registry.get(provider_name)
        if profile and profile.fallback_models:
            return [
                {"id": m, "name": m, "provider": provider_name}
                for m in profile.fallback_models
            ]

        # Try ProviderRegistry first (Hermes-style profiles)
        if profile and profile.base_url:
            base_url = profile.base_url.rstrip("/")
            api_key = profile.resolve_api_key() or resolve_api_key(provider_name)
        else:
            # Fall back to legacy config format
            provider_cfg = config.get_provider(provider_name) or {}
            base_url = (provider_cfg.get("base_url") or "").rstrip("/")
            if not base_url:
                return []
            api_key = resolve_api_key(provider_name)

        # Skip providers that require auth but have no API key — user hasn't "added" them
        if profile and profile.requires_auth() and not api_key:
            return []

        headers = {
            "User-Agent": "Jarvis-Mark-II/2.0",
            "Accept": "application/json",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        models_url = f"{base_url}/models"

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(models_url, headers=headers)

                if resp.status_code != 200:
                    return []

                data = resp.json()

                # Standard OpenAI format: {"data": [{"id": "...", ...}]}
                raw_models = data.get("data") or data.get("models") or []

                results = []
                for m in raw_models:
                    if isinstance(m, str):
                        results.append({"id": m, "name": m, "provider": provider_name})
                    elif isinstance(m, dict):
                        mid = m.get("id") or m.get("name") or ""
                        results.append({
                            "id": mid,
                            "name": m.get("name", mid),
                            "provider": provider_name,
                            **{k: v for k, v in m.items() if k not in ("id", "name", "provider")},
                        })
                return results

        except (httpx.TimeoutException, httpx.HTTPError, Exception):
            return []

    @staticmethod
    async def discover_all() -> dict[str, list[dict]]:
        """Discover models from all configured providers.

        Iterates over both ProviderRegistry profiles and legacy config providers.

        Returns:
            Dict mapping provider name -> list of model dicts.
        """
        config = get_config()
        results: dict[str, list[dict]] = {}

        # Collect provider names from both sources
        provider_names = set()

        # From ProviderRegistry
        registry = ProviderRegistry.get_instance()
        for profile in registry.list():
            provider_names.add(profile.name)

        # From legacy config
        legacy_providers = config.get_providers()
        for name in legacy_providers:
            provider_names.add(name)

        for provider_name in sorted(provider_names):
            models = await ModelDiscovery.discover(provider_name)
            if models:
                results[provider_name] = models

        return results
