"""
backend/auth/service.py
═══════════════════════
Logica de autentificare + gestionare chat-uri.

Toate operațiile sunt funcții simple care primesc/returnează dict-uri.
Niciun ORM — query-uri SQL directe, pentru transparență totală.

Securitate:
  • parolele sunt stocate ca hash bcrypt (work factor implicit = 12)
  • validare username (3-32 caractere, alfanumeric + _.-)
  • validare email regex simplu
  • parolă min `password_min_length` caractere
"""

import json
import re
import sqlite3
import uuid
from datetime import datetime
from typing import List, Optional

import bcrypt

from backend.auth.database import get_connection
from backend.config import settings
from backend.exceptions import AppException
from backend.logging_config import logger
from backend.text_utils import normalize


# ── Excepții specifice ───────────────────────────────────────────────────────

class AuthError(AppException):
    """Eroare generică de autentificare."""
    status_code = 401


class UsernameTakenError(AuthError):
    default_message = "Numele de utilizator este deja folosit."
    status_code = 409


class EmailTakenError(AuthError):
    default_message = "Această adresă de email este deja înregistrată."
    status_code = 409


class InvalidCredentialsError(AuthError):
    default_message = "Nume de utilizator sau parolă incorectă."
    status_code = 401


class ValidationError(AuthError):
    status_code = 400


# ── Validatori ───────────────────────────────────────────────────────────────

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _validate_username(username: str) -> str:
    username = (username or "").strip()
    if not _USERNAME_RE.match(username):
        raise ValidationError(
            "Numele de utilizator trebuie să aibă 3-32 caractere "
            "(litere, cifre, _ . -)."
        )
    return username


def _validate_email(email: str) -> str:
    email = (email or "").strip().lower()
    if not _EMAIL_RE.match(email):
        raise ValidationError("Adresa de email nu pare validă.")
    return email


def _validate_password(password: str) -> None:
    if not password or len(password) < settings.password_min_length:
        raise ValidationError(
            f"Parola trebuie să aibă cel puțin {settings.password_min_length} caractere."
        )


def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════════════════
#  USERS
# ═══════════════════════════════════════════════════════════════════════════════

def register_user(
    username: str,
    email: str,
    password: str,
    full_name: Optional[str] = None,
) -> dict:
    """Înregistrează un utilizator nou. Returnează profilul (fără parolă)."""
    username = _validate_username(username)
    email = _validate_email(email)
    _validate_password(password)
    full_name = (full_name or "").strip() or None
    password_hash = _hash_password(password)

    try:
        with get_connection() as conn:
            cur = conn.execute(
                """INSERT INTO users (username, email, password_hash, full_name)
                   VALUES (?, ?, ?, ?)""",
                (username, email, password_hash, full_name),
            )
            user_id = cur.lastrowid
    except sqlite3.IntegrityError as exc:
        msg = str(exc).lower()
        if "username" in msg:
            raise UsernameTakenError() from exc
        if "email" in msg:
            raise EmailTakenError() from exc
        raise ValidationError("Înregistrare eșuată. Date invalide.") from exc

    logger.info("Utilizator nou înregistrat: {} (id={})", username, user_id)
    return _get_user_by_id(user_id)


def authenticate(username_or_email: str, password: str) -> dict:
    """Verifică credentialele. Returnează profilul sau ridică InvalidCredentialsError."""
    identifier = (username_or_email or "").strip()
    if not identifier or not password:
        raise InvalidCredentialsError()

    with get_connection() as conn:
        row = conn.execute(
            """SELECT * FROM users WHERE username = ? OR email = ? LIMIT 1""",
            (identifier, identifier.lower()),
        ).fetchone()

    if not row or not _verify_password(password, row["password_hash"]):
        # Acelaș mesaj indiferent dacă userul nu există sau parola e greșită
        # (evită enumeration attacks)
        raise InvalidCredentialsError()

    # Actualizăm last_login
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET last_login = ? WHERE id = ?",
            (datetime.utcnow(), row["id"]),
        )

    logger.info("Login OK: {} (id={})", row["username"], row["id"])
    return _row_to_user(row)


def _get_user_by_id(user_id: int) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _row_to_user(row) if row else None


def _row_to_user(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "email": row["email"],
        "full_name": row["full_name"],
        "created_at": row["created_at"],
        "last_login": row["last_login"],
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  CHATS
# ═══════════════════════════════════════════════════════════════════════════════

def create_chat(user_id: int, title: str = "Conversație nouă") -> dict:
    """Creează o nouă conversație pentru un utilizator."""
    session_id = uuid.uuid4().hex[:16]
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO chats (user_id, title, session_id)
               VALUES (?, ?, ?)""",
            (user_id, title, session_id),
        )
        chat_id = cur.lastrowid
    logger.debug("Chat nou: id={} user_id={}", chat_id, user_id)
    return get_chat(chat_id)


def get_chat(chat_id: int) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
    return dict(row) if row else None


def list_user_chats(
    user_id: int,
    limit: int = 50,
    include_archived: bool = False,
    search: Optional[str] = None,
) -> List[dict]:
    """
    Returnează chat-urile unui utilizator.

    Ordonare: fixate (pin) întâi, apoi cele mai recente.
    `include_archived` False → ascunde conversațiile arhivate.
    `search` → filtrare după titlu, INSENSIBILĂ la diacritice și majuscule.
    """
    query = (
        "SELECT c.*, "
        "(SELECT COUNT(*) FROM messages m WHERE m.chat_id = c.id) AS message_count "
        "FROM chats c WHERE c.user_id = ?"
    )
    params: list = [user_id]
    if not include_archived:
        query += " AND c.archived = 0"
    query += " ORDER BY c.pinned DESC, c.updated_at DESC LIMIT ?"
    params.append(limit)

    with get_connection() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()

    chats = [dict(r) for r in rows]

    if search and search.strip():
        needle = normalize(search)
        chats = [c for c in chats if needle in normalize(c.get("title", ""))]

    return chats


def set_pinned(chat_id: int, user_id: int, pinned: bool) -> bool:
    """Fixează / defixează o conversație (doar dacă aparține utilizatorului)."""
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE chats SET pinned = ? WHERE id = ? AND user_id = ?",
            (1 if pinned else 0, chat_id, user_id),
        )
        return cur.rowcount > 0


def set_archived(chat_id: int, user_id: int, archived: bool) -> bool:
    """Arhivează / dezarhivează o conversație."""
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE chats SET archived = ? WHERE id = ? AND user_id = ?",
            (1 if archived else 0, chat_id, user_id),
        )
        return cur.rowcount > 0


# ── Partajare ────────────────────────────────────────────────────────────────

def enable_sharing(chat_id: int, user_id: int) -> Optional[str]:
    """
    Activează partajarea publică (read-only) a unei conversații și returnează
    token-ul. Dacă există deja un token, îl refolosește.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT share_token FROM chats WHERE id = ? AND user_id = ?",
            (chat_id, user_id),
        ).fetchone()
        if not row:
            return None
        token = row["share_token"]
        if not token:
            token = uuid.uuid4().hex
            conn.execute(
                "UPDATE chats SET share_token = ? WHERE id = ? AND user_id = ?",
                (token, chat_id, user_id),
            )
    return token


def disable_sharing(chat_id: int, user_id: int) -> bool:
    """Oprește partajarea (invalidează link-ul)."""
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE chats SET share_token = NULL WHERE id = ? AND user_id = ?",
            (chat_id, user_id),
        )
        return cur.rowcount > 0


def get_shared_chat(token: str) -> Optional[dict]:
    """Returnează conversația partajată după token (fără verificare de user)."""
    if not token:
        return None
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM chats WHERE share_token = ? LIMIT 1", (token,)
        ).fetchone()
    return dict(row) if row else None


def rename_chat(chat_id: int, new_title: str, user_id: int) -> bool:
    """Redenumește un chat (doar dacă aparține utilizatorului)."""
    new_title = (new_title or "").strip()[:100] or "Conversație"
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE chats SET title = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND user_id = ?",
            (new_title, chat_id, user_id),
        )
        return cur.rowcount > 0


def delete_chat(chat_id: int, user_id: int) -> bool:
    """Șterge un chat (CASCADE — și mesajele asociate). Returnează True dacă există."""
    with get_connection() as conn:
        cur = conn.execute(
            "DELETE FROM chats WHERE id = ? AND user_id = ?",
            (chat_id, user_id),
        )
        return cur.rowcount > 0


def touch_chat(chat_id: int) -> None:
    """Actualizează `updated_at` pentru reordonare în listă."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE chats SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (chat_id,),
        )


def auto_title_from_question(question: str) -> str:
    """Generează un titlu scurt dintr-o întrebare (folosit la primul mesaj)."""
    title = (question or "").strip().replace("\n", " ")
    if len(title) > 50:
        title = title[:47].rstrip() + "..."
    return title or "Conversație nouă"


# ═══════════════════════════════════════════════════════════════════════════════
#  MESSAGES
# ═══════════════════════════════════════════════════════════════════════════════

def add_message(
    chat_id: int,
    role: str,
    content: str,
    sources: Optional[List[str]] = None,
    rewritten: Optional[str] = None,
) -> int:
    """Adaugă un mesaj la o conversație și actualizează updated_at-ul chat-ului."""
    if role not in ("user", "assistant"):
        raise ValidationError(f"Role invalid: {role}")

    sources_json = json.dumps(sources, ensure_ascii=False) if sources else None

    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO messages (chat_id, role, content, sources, rewritten)
               VALUES (?, ?, ?, ?, ?)""",
            (chat_id, role, content, sources_json, rewritten),
        )
        conn.execute(
            "UPDATE chats SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (chat_id,),
        )
        return cur.lastrowid


def update_message(message_id: int, chat_id: int, new_content: str) -> bool:
    """Editează conținutul unui mesaj (și îl marchează ca editat)."""
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE messages SET content = ?, edited = 1 WHERE id = ? AND chat_id = ?",
            (new_content, message_id, chat_id),
        )
        return cur.rowcount > 0


def delete_messages_from(chat_id: int, message_id: int) -> int:
    """
    Șterge mesajul `message_id` și TOATE mesajele ulterioare din conversație.
    Folosit la editarea unui mesaj: conversația „se ramifică" din acel punct.
    Returnează numărul de mesaje șterse.
    """
    with get_connection() as conn:
        cur = conn.execute(
            "DELETE FROM messages WHERE chat_id = ? AND id >= ?",
            (chat_id, message_id),
        )
        return cur.rowcount


def get_messages(chat_id: int) -> List[dict]:
    """Returnează mesajele unei conversații în ordine cronologică."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE chat_id = ? ORDER BY id ASC",
            (chat_id,),
        ).fetchall()

    result = []
    for r in rows:
        d = dict(r)
        if d.get("sources"):
            try:
                d["sources"] = json.loads(d["sources"])
            except Exception:
                d["sources"] = []
        else:
            d["sources"] = []
        result.append(d)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  STATS
# ═══════════════════════════════════════════════════════════════════════════════

def user_stats(user_id: int) -> dict:
    """Statistici despre activitatea unui utilizator."""
    with get_connection() as conn:
        chats = conn.execute(
            "SELECT COUNT(*) FROM chats WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        messages = conn.execute(
            """SELECT COUNT(*) FROM messages m
               JOIN chats c ON m.chat_id = c.id
               WHERE c.user_id = ? AND m.role = 'user'""",
            (user_id,),
        ).fetchone()[0]
    return {"chats": chats, "questions_asked": messages}
