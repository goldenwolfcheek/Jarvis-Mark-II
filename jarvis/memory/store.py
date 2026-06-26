"""
Jarvis Mark II — Memory store.
File-based long-term memory (MEMORY.md) and user profile (USER.md)
with enforced character limits.  Inspired by Hermes Agent's memory system.
"""

import os
import threading
import time
from pathlib import Path
from typing import Optional

from ..constants import MEMORY_DIR, MEMORY_FILE, USER_FILE, PERSONALITY_FILE, MEMORY_CHAR_LIMIT, USER_CHAR_LIMIT, PERSONALITY_CHAR_LIMIT

_DEFAULT_MEMORY = (
    "# Jarvis's Long-Term Memory\n\n"
    "_This file persists across sessions. Update it as you learn about the user.\n"
    "Keep it concise — it is included in every system prompt._\n"
)

_DEFAULT_USER = (
    "# User Profile\n\n"
    "_Information about the user (preferences, facts, context)._ \n"
)

_DEFAULT_PERSONALITY = (
    "# Personality\n\n"
    "_Instructions and preferences for Jarvis's behaviour and tone._\n"
)


class MemoryStore:
    """Manages long-term memory and user-profile text files.

    Thread-safe via ``threading.RLock``.  Reads are cached; writes persist
    immediately to disk.
    """

    def __init__(
        self,
        mem_path: Path = MEMORY_FILE,
        user_path: Path = USER_FILE,
        personality_path: Path = PERSONALITY_FILE,
    ):
        self._mem_path = mem_path
        self._user_path = user_path
        self._personality_path = personality_path
        self._lock = threading.RLock()
        self._mem_cache: Optional[str] = None
        self._user_cache: Optional[str] = None
        self._personality_cache: Optional[str] = None
        self._ensure_files()

    # ── Initialisation ────────────────────────────────────────────────────

    def _ensure_files(self):
        """Create default memory files if they don't exist."""
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        if not self._mem_path.exists():
            self._mem_path.write_text(_DEFAULT_MEMORY, encoding="utf-8")
        if not self._user_path.exists():
            self._user_path.write_text(_DEFAULT_USER, encoding="utf-8")
        if not self._personality_path.exists():
            self._personality_path.write_text(_DEFAULT_PERSONALITY, encoding="utf-8")

    # ── Memory (assistant's long-term knowledge) ──────────────────────────

    def get_memory(self) -> str:
        """Return current memory content (cached)."""
        with self._lock:
            if self._mem_cache is None:
                self._mem_cache = self._read_file(self._mem_path)
            return self._mem_cache

    def set_memory(self, content: str):
        """Overwrite memory file, enforcing the character limit."""
        with self._lock:
            truncated = content[:MEMORY_CHAR_LIMIT]
            self._write_file(self._mem_path, truncated)
            self._mem_cache = truncated

    def append_memory(self, text: str, separator: str = "\n") -> str:
        """Append text to memory, truncating to keep within limit.

        Returns the updated full memory text.
        """
        with self._lock:
            current = self.get_memory()
            updated = current.rstrip() + separator + text.strip()
            if len(updated) > MEMORY_CHAR_LIMIT:
                # Keep the NEW content, prepend as much of the old as fits
                overhead = len(separator) + len(text.strip())
                keep = MEMORY_CHAR_LIMIT - overhead
                if keep > 0:
                    updated = current[-keep:].lstrip() + separator + text.strip()
                else:
                    updated = text.strip()[:MEMORY_CHAR_LIMIT]
            self._write_file(self._mem_path, updated)
            self._mem_cache = updated
            return updated

    # ── User profile ──────────────────────────────────────────────────────

    def get_user_profile(self) -> str:
        """Return current user profile (cached)."""
        with self._lock:
            if self._user_cache is None:
                self._user_cache = self._read_file(self._user_path)
            return self._user_cache

    def set_user_profile(self, content: str):
        """Overwrite user profile, enforcing the character limit."""
        with self._lock:
            truncated = content[:USER_CHAR_LIMIT]
            self._write_file(self._user_path, truncated)
            self._user_cache = truncated

    def update_user_profile(self, text: str, append: bool = True):
        """Update the user profile by either appending or replacing.

        Args:
            text: Content to add or replace with.
            append: If True, append. Otherwise replace entirely.
        """
        with self._lock:
            if append:
                current = self.get_user_profile()
                updated = current.rstrip() + "\n" + text.strip()
                if len(updated) > USER_CHAR_LIMIT:
                    overhead = 1 + len(text.strip())
                    keep = USER_CHAR_LIMIT - overhead
                    if keep > 0:
                        updated = current[-keep:].lstrip() + "\n" + text.strip()
                    else:
                        updated = text.strip()[:USER_CHAR_LIMIT]
                self._write_file(self._user_path, updated)
                self._user_cache = updated
            else:
                self.set_user_profile(text)

    # ── Personality ────────────────────────────────────────────────────

    def get_personality(self) -> str:
        """Return current personality content (cached)."""
        with self._lock:
            if self._personality_cache is None:
                self._personality_cache = self._read_file(self._personality_path)
            return self._personality_cache

    def set_personality(self, content: str):
        """Overwrite personality file, enforcing the character limit."""
        with self._lock:
            truncated = content[:PERSONALITY_CHAR_LIMIT]
            self._write_file(self._personality_path, truncated)
            self._personality_cache = truncated

    # ── Bulk read for system prompt ───────────────────────────────────────

    def get_for_system_prompt(self) -> dict:
        """Return memory, user profile and personality for inclusion in the system prompt."""
        return {
            "memory": self.get_memory(),
            "user_profile": self.get_user_profile(),
            "personality": self.get_personality(),
        }

    # ── Disk I/O ──────────────────────────────────────────────────────────

    @staticmethod
    def _read_file(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return ""

    @staticmethod
    def _write_file(path: Path, content: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".md.tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)

    # ── Cache control ─────────────────────────────────────────────────────

    def invalidate_cache(self):
        """Force re-read from disk on next access."""
        with self._lock:
            self._mem_cache = None
            self._user_cache = None
            self._personality_cache = None


# ── Singleton ─────────────────────────────────────────────────────────────
_memory_instance: Optional[MemoryStore] = None
_memory_lock = threading.Lock()


def get_memory_store() -> MemoryStore:
    """Return the global MemoryStore singleton."""
    global _memory_instance
    if _memory_instance is None:
        with _memory_lock:
            if _memory_instance is None:
                _memory_instance = MemoryStore()
    return _memory_instance
