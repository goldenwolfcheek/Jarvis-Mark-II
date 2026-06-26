"""
Jarvis Mark II — Security utilities.
API key management, encryption at rest, and safe credential storage.
"""

import os
import json
import base64
import hashlib
import secrets
import threading
from pathlib import Path
from typing import Optional

from .constants import CONFIG_DIR

# ── Key file path ─────────────────────────────────────────────────────────
_KEY_FILE = CONFIG_DIR / ".keys.json"


def _get_machine_key() -> bytes:
    """Derive a machine-local encryption key from stable identifiers.
    This is NOT cryptographically perfect — it's a deterrent against casual
    plaintext leakage, not a hardened vault.  For real secrets users should
    rely on the OS keychain (Windows Credential Manager, macOS Keychain).
    """
    # Combine machine info with a static pepper to produce 32 bytes
    raw = (
        os.environ.get("COMPUTERNAME", "unknown")
        + os.environ.get("USERNAME", "unknown")
        + "::JARVIS_MK2_PEPPER::v1"
    )
    return hashlib.sha256(raw.encode()).digest()


class KeyStore:
    """Simple encrypted-at-rest key-value store for API keys."""

    def __init__(self, path: Path = _KEY_FILE):
        self._path = path
        self._lock = threading.Lock()
        self._cache: dict[str, str] = {}
        self._load()

    # ── Internal helpers ──────────────────────────────────────────────────

    def _xor_cipher(self, data: bytes, key: bytes) -> bytes:
        """XOR encrypt/decrypt with repeated key (stream cipher)."""
        return bytes(d ^ key[i % len(key)] for i, d in enumerate(data))

    def _encode(self, plaintext: str) -> str:
        key = _get_machine_key()
        encoded = plaintext.encode("utf-8")
        cipher = self._xor_cipher(encoded, key)
        return base64.urlsafe_b64encode(cipher).decode("ascii")

    def _decode(self, token: str) -> str:
        key = _get_machine_key()
        cipher = base64.urlsafe_b64decode(token.encode("ascii"))
        plain = self._xor_cipher(cipher, key)
        return plain.decode("utf-8")

    def _load(self):
        self._cache = {}
        if not self._path.exists():
            return
        try:
            raw = self._path.read_text("utf-8")
            encrypted_map: dict[str, str] = json.loads(raw)
            for provider, token in encrypted_map.items():
                try:
                    self._cache[provider] = self._decode(token)
                except Exception:
                    continue  # skip corrupted entries
        except (json.JSONDecodeError, OSError):
            pass

    def _persist(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        encrypted_map = {
            provider: self._encode(value)
            for provider, value in self._cache.items()
        }
        tmp = self._path.with_suffix(".keys.json.tmp")
        tmp.write_text(json.dumps(encrypted_map, indent=2), "utf-8")
        tmp.replace(self._path)

    # ── Public API ────────────────────────────────────────────────────────

    def get(self, provider: str) -> Optional[str]:
        """Retrieve an API key for *provider*."""
        with self._lock:
            return self._cache.get(provider)

    def set(self, provider: str, api_key: str):
        """Store an API key for *provider* (persists to disk)."""
        with self._lock:
            if api_key:
                self._cache[provider] = api_key
            else:
                self._cache.pop(provider, None)
            self._persist()

    def delete(self, provider: str):
        """Remove a stored key."""
        with self._lock:
            self._cache.pop(provider, None)
            self._persist()

    def list_providers(self) -> list[str]:
        """Return providers that have keys stored."""
        with self._lock:
            return list(self._cache.keys())

    def has_key(self, provider: str) -> bool:
        """Return True if a key exists for *provider*."""
        return self.get(provider) is not None

    def clear(self):
        """Wipe all stored keys."""
        with self._lock:
            self._cache.clear()
            if self._path.exists():
                self._path.unlink()


# ── Singleton ─────────────────────────────────────────────────────────────
_keystore_instance: Optional[KeyStore] = None
_keystore_lock = threading.Lock()


def get_keystore() -> KeyStore:
    """Return the global KeyStore singleton."""
    global _keystore_instance
    if _keystore_instance is None:
        with _keystore_lock:
            if _keystore_instance is None:
                _keystore_instance = KeyStore()
    return _keystore_instance


# ── Convenience helpers ───────────────────────────────────────────────────

def resolve_api_key(provider: str, explicit_key: Optional[str] = None) -> Optional[str]:
    """Resolve an API key: explicit arg > keystore > environment variable.

    Environment variables are checked as: ``<PROVIDER>_API_KEY`` upper-cased.
    """
    if explicit_key:
        return explicit_key
    ks = get_keystore()
    stored = ks.get(provider)
    if stored:
        return stored
    env_var = f"{provider.upper().replace('-', '_')}_API_KEY"
    return os.environ.get(env_var)


def mask_key(key: str, visible_chars: int = 4) -> str:
    """Return a masked version of an API key for logging."""
    if not key or len(key) <= visible_chars:
        return "****"
    return key[:visible_chars] + "*" * (len(key) - visible_chars - 4) + key[-4:]
