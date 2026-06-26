"""
Jarvis Mark II — SQLite state database.
Persistent storage for sessions, conversation history, agent state, and metadata.
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional

from ..constants import STATE_DB


class StateDB:
    """Thread-safe SQLite-backed state persistence.

    Schema is designed for:
      - Session management (create / list / delete)
      - Message history per session (append / query / prune)
      - Agent metadata (key-value store for arbitrary agent state)

    All write operations acquire a ``threading.RLock`` so callers from
    multiple threads (e.g. websocket + background tasks) are safe.
    """

    def __init__(self, db_path: Path = STATE_DB):
        self._path = db_path
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        self._connect()

    # ── Connection management ─────────────────────────────────────────────

    def _connect(self):
        """Open (or create) the database and ensure schema exists."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self._path),
            check_same_thread=False,
            isolation_level=None,
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA wal_autocheckpoint=500")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def _migrate(self):
        """Idempotent schema creation / migration."""
        with self._lock:
            cur = self._conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='sessions'")
            if cur.fetchone()[0] == 0:
                self._conn.executescript("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        id          TEXT PRIMARY KEY,
                        created_at  REAL NOT NULL,
                        updated_at  REAL NOT NULL,
                        title       TEXT DEFAULT '',
                        metadata    TEXT DEFAULT '{}'
                    );

                    CREATE TABLE IF NOT EXISTS messages (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                        role        TEXT NOT NULL,
                        content     TEXT NOT NULL,
                        tool_calls  TEXT,
                        tool_results TEXT,
                        created_at  REAL NOT NULL,
                        token_count INTEGER DEFAULT 0
                    );

                    CREATE TABLE IF NOT EXISTS kv_store (
                        key         TEXT PRIMARY KEY,
                        value       TEXT NOT NULL,
                        updated_at  REAL NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_messages_session
                        ON messages(session_id, created_at);

                    CREATE INDEX IF NOT EXISTS idx_messages_created
                        ON messages(created_at);
                """)

    def close(self):
        """Close the database connection gracefully — checkpoint then close."""
        with self._lock:
            if self._conn:
                try:
                    self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                except Exception:
                    pass
                self._conn.close()
                self._conn = None

    def checkpoint(self):
        """Explicitly checkpoint the WAL file to reclaim space.
        Call during idle periods or after batch writes."""
        with self._lock:
            self._conn.execute("PRAGMA wal_checkpoint(PASSIVE)")

    # ── Sessions ──────────────────────────────────────────────────────────

    def create_session(self, session_id: str, title: str = "", metadata: Optional[dict] = None) -> dict:
        """Create a new session record. Returns the session dict."""
        now = time.time()
        meta_json = json.dumps(metadata or {})
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO sessions (id, created_at, updated_at, title, metadata) VALUES (?, ?, ?, ?, ?)",
                (session_id, now, now, title, meta_json),
            )
        return self.get_session(session_id) or {"id": session_id, "created_at": now, "updated_at": now, "title": title}

    def get_session(self, session_id: str) -> Optional[dict]:
        """Fetch a single session dict, or None."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, created_at, updated_at, title, metadata FROM sessions WHERE id = ?",
                (session_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "created_at": row[1],
            "updated_at": row[2],
            "title": row[3],
            "metadata": json.loads(row[4]) if row[4] else {},
        }

    def list_sessions(self, limit: int = 50, offset: int = 0) -> list[dict]:
        """List sessions ordered by most-recently-upated first."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, created_at, updated_at, title, metadata FROM sessions ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            rows = cur.fetchall()
        return [
            {
                "id": r[0],
                "created_at": r[1],
                "updated_at": r[2],
                "title": r[3],
                "metadata": json.loads(r[4]) if r[4] else {},
            }
            for r in rows
        ]

    def update_session(self, session_id: str, title: Optional[str] = None, metadata: Optional[dict] = None):
        """Update session title and/or metadata."""
        now = time.time()
        with self._lock:
            if title is not None:
                self._conn.execute(
                    "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
                    (title, now, session_id),
                )
            if metadata is not None:
                self._conn.execute(
                    "UPDATE sessions SET metadata = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(metadata), now, session_id),
                )
            if title is None and metadata is None:
                self._conn.execute(
                    "UPDATE sessions SET updated_at = ? WHERE id = ?",
                    (now, session_id),
                )

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its messages. Returns True if deleted."""
        with self._lock:
            cur = self._conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            return cur.rowcount > 0

    # ── Messages ──────────────────────────────────────────────────────────

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_calls: Optional[list] = None,
        tool_results: Optional[list] = None,
        token_count: int = 0,
    ) -> int:
        """Append a message to a session's history. Returns the message id."""
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO messages (session_id, role, content, tool_calls, tool_results, created_at, token_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    role,
                    content,
                    json.dumps(tool_calls) if tool_calls else None,
                    json.dumps(tool_results) if tool_results else None,
                    now,
                    token_count,
                ),
            )
            msg_id = self._conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            # Touch session updated_at
            self._conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (now, session_id),
            )
            return msg_id

    def get_messages(
        self,
        session_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """Get messages for a session, oldest-first."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, role, content, tool_calls, tool_results, created_at, token_count "
                "FROM messages WHERE session_id = ? ORDER BY created_at ASC LIMIT ? OFFSET ?",
                (session_id, limit, offset),
            )
            rows = cur.fetchall()
        return [
            {
                "id": r[0],
                "role": r[1],
                "content": r[2],
                "tool_calls": json.loads(r[3]) if r[3] else None,
                "tool_results": json.loads(r[4]) if r[4] else None,
                "created_at": r[5],
                "token_count": r[6],
            }
            for r in rows
        ]

    def get_recent_messages(self, session_id: str, count: int = 20) -> list[dict]:
        """Get the *count* most recent messages, oldest-first."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, role, content, tool_calls, tool_results, created_at, token_count "
                "FROM messages WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
                (session_id, count),
            )
            rows = cur.fetchall()
        rows.reverse()
        return [
            {
                "id": r[0],
                "role": r[1],
                "content": r[2],
                "tool_calls": json.loads(r[3]) if r[3] else None,
                "tool_results": json.loads(r[4]) if r[4] else None,
                "created_at": r[5],
                "token_count": r[6],
            }
            for r in rows
        ]

    def count_messages(self, session_id: str) -> int:
        """Return the total number of messages in a session."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT count(*) FROM messages WHERE session_id = ?",
                (session_id,),
            )
            return cur.fetchone()[0]

    def prune_messages(self, session_id: str, keep: int = 50):
        """Delete oldest messages beyond *keep* for a session."""
        with self._lock:
            self._conn.execute(
                "DELETE FROM messages WHERE id IN ("
                "  SELECT id FROM messages WHERE session_id = ? "
                "  ORDER BY created_at ASC LIMIT -1 OFFSET ?"
                ")",
                (session_id, keep),
            )

    # ── Key-value store ───────────────────────────────────────────────────

    def kv_get(self, key: str, default: Any = None) -> Any:
        """Get a value from the agent KV store."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT value FROM kv_store WHERE key = ?",
                (key,),
            )
            row = cur.fetchone()
            if row is None:
                return default
            try:
                return json.loads(row[0])
            except (json.JSONDecodeError, TypeError):
                return row[0]

    def kv_set(self, key: str, value: Any):
        """Set a value in the agent KV store (persisted as JSON)."""
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO kv_store (key, value, updated_at) VALUES (?, ?, ?)",
                (key, json.dumps(value), now),
            )

    def kv_delete(self, key: str):
        """Delete a key from the KV store."""
        with self._lock:
            self._conn.execute("DELETE FROM kv_store WHERE key = ?", (key,))

    def kv_keys(self, pattern: str = "%") -> list[str]:
        """List keys matching an SQL LIKE pattern."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT key FROM kv_store WHERE key LIKE ?",
                (pattern,),
            )
            return [r[0] for r in cur.fetchall()]

    # ── Maintenance ───────────────────────────────────────────────────────

    def vacuum(self):
        """Recover disk space (VACUUM). Call during idle periods."""
        with self._lock:
            self._conn.execute("VACUUM")

    def get_stats(self) -> dict:
        """Return basic database statistics."""
        with self._lock:
            sessions = self._conn.execute("SELECT count(*) FROM sessions").fetchone()[0]
            messages = self._conn.execute("SELECT count(*) FROM messages").fetchone()[0]
            kv_entries = self._conn.execute("SELECT count(*) FROM kv_store").fetchone()[0]
            db_size = self._path.stat().st_size if self._path.exists() else 0
        return {
            "sessions": sessions,
            "messages": messages,
            "kv_entries": kv_entries,
            "db_size_bytes": db_size,
        }


# ── Singleton ─────────────────────────────────────────────────────────────
_db_instance: Optional[StateDB] = None
_db_lock = threading.Lock()


def get_state_db() -> StateDB:
    """Return the global StateDB singleton."""
    global _db_instance
    if _db_instance is None:
        with _db_lock:
            if _db_instance is None:
                _db_instance = StateDB()
    return _db_instance
