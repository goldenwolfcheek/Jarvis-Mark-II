"""
Jarvis Mark II — State management package.
SQLite-backed persistent state for sessions, conversation history, and metadata.
"""

from .db import StateDB, get_state_db

__all__ = ["StateDB", "get_state_db"]
