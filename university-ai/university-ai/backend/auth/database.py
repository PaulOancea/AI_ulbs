"""
backend/auth/database.py
════════════════════════
SQLite schema + connection helper. Minimal, dependency-free.

Tabele:
  • users     — conturi utilizatori (id, username, email, password_hash, ...)
  • chats     — sesiuni de conversație (id, user_id, title, created_at)
  • messages  — mesaje în conversații (id, chat_id, role, content, sources, ...)

Folosim SQLite pentru că:
  - zero setup (un singur fișier, .db)
  - perfect pentru o aplicație single-server cu sute de utilizatori
  - tranzacționalitate ACID
  - portabil (poate fi mutat ca fișier)
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import Iterator

from backend.config import settings
from backend.logging_config import logger


# Lock global pentru migrațiile inițiale (thread-safe init)
_INIT_LOCK = Lock()
_INITIALIZED = False


# ── Schema DDL ────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name     TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login    TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email    ON users(email);

CREATE TABLE IF NOT EXISTS chats (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    title       TEXT NOT NULL DEFAULT 'Conversație nouă',
    session_id  TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chats_user_id ON chats(user_id);
CREATE INDEX IF NOT EXISTS idx_chats_updated ON chats(updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id     INTEGER NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT NOT NULL,
    sources     TEXT,            -- JSON cu sursele (pentru răspunsuri)
    rewritten   TEXT,            -- întrebarea reformulată (dacă există)
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at);
"""


# ── Inițializare DB ──────────────────────────────────────────────────────────

def _ensure_initialized() -> None:
    """Creează tabelele dacă nu există (idempotent)."""
    global _INITIALIZED
    if _INITIALIZED:
        return
    with _INIT_LOCK:
        if _INITIALIZED:  # double-check după acquire
            return

        db_path = settings.database_path_abs
        db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(db_path))
        try:
            conn.executescript(SCHEMA)
            conn.commit()
        finally:
            conn.close()

        logger.info("SQLite inițializat la {}", db_path)
        _INITIALIZED = True


# ── Connection helper (context manager) ──────────────────────────────────────

@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """
    Returnează o conexiune SQLite cu:
      - row_factory = sqlite3.Row (acces dict-like la rezultate)
      - foreign_keys = ON (pentru CASCADE delete)
      - commit + close automate
    """
    _ensure_initialized()
    conn = sqlite3.connect(
        str(settings.database_path_abs),
        detect_types=sqlite3.PARSE_DECLTYPES,
        timeout=10.0,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
