"""
Jarvis Mark II — Provider profiles module.

Hermes-style provider declarations that describe each inference provider's
auth, base URL, capabilities, and fallback model list.  The registry loads
these profiles and merges them with user config so LLMCore and agent code
can resolve provider settings in one place.

Usage:
    from jarvis.providers import ProviderProfile, ProviderRegistry

    registry = ProviderRegistry.get_instance()
    profiles = registry.list()
    openai   = registry.get("openai")
    default  = registry.get_default()
"""

from .base import ProviderProfile
from .registry import ProviderRegistry
from .profiles import BUILTIN_PROFILES, get_builtin_profile

__all__ = [
    "ProviderProfile",
    "ProviderRegistry",
    "BUILTIN_PROFILES",
    "get_builtin_profile",
]
