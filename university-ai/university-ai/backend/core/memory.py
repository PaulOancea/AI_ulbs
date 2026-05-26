"""
backend/core/memory.py
══════════════════════
Memorie conversațională cu suport pentru multiple sesiuni.

Pattern:
  • fiecare sesiune (session_id) are propriul `ConversationBufferWindow`;
  • păstrăm ultimele K schimburi (k=6 → 12 mesaje);
  • la fiecare întrebare, dăm LLM-ului contextul scurt al conversației;
  • dacă întrebarea curentă e dependentă de context (ex: "Dar la anul II?"),
    se face mai întâi un "query rewrite" cu LLM-ul pentru a o transforma
    într-o întrebare auto-suficientă, apoi se face retrievalul.

De ce window și nu buffer infinit?
  Token budget-ul Ollama e finit. Cu k=6, contextul rămâne sub ~2000 tokeni
  chiar și pentru schimburi lungi. Suficient pentru continuitate.
"""

from collections import deque
from dataclasses import dataclass
from threading import Lock
from typing import Deque, Dict, List, Optional

from backend.config import settings
from backend.logging_config import logger


@dataclass
class Message:
    role: str   # "user" sau "assistant"
    content: str


class ConversationMemory:
    """O memorie pentru o singură sesiune."""

    def __init__(self, window: int = settings.memory_window):
        # Stocăm 2*window mesaje (un schimb = 2 mesaje)
        self.window = window
        self._messages: Deque[Message] = deque(maxlen=window * 2)

    def add_user(self, content: str) -> None:
        self._messages.append(Message(role="user", content=content))

    def add_assistant(self, content: str) -> None:
        self._messages.append(Message(role="assistant", content=content))

    def get_messages(self) -> List[Message]:
        return list(self._messages)

    def get_context_str(self) -> str:
        """Returnează istoricul ca string formatat pentru prompt."""
        if not self._messages:
            return ""
        lines = []
        for m in self._messages:
            label = "Student" if m.role == "user" else "Asistent"
            lines.append(f"{label}: {m.content}")
        return "\n".join(lines)

    def clear(self) -> None:
        self._messages.clear()

    def __len__(self) -> int:
        return len(self._messages)


class MemoryManager:
    """
    Gestionează multiple sesiuni paralele (multi-user friendly).
    Thread-safe pentru utilizare din FastAPI cu workers async.
    """

    _instance: Optional["MemoryManager"] = None
    _singleton_lock = Lock()

    def __new__(cls):
        with cls._singleton_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._sessions: Dict[str, ConversationMemory] = {}
                cls._instance._lock = Lock()
            return cls._instance

    def get_or_create(self, session_id: str) -> ConversationMemory:
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = ConversationMemory()
                logger.debug("Sesiune nouă: {}", session_id)
            return self._sessions[session_id]

    def clear_session(self, session_id: str) -> None:
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id].clear()
                logger.debug("Sesiune resetată: {}", session_id)

    def drop_session(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def active_sessions(self) -> int:
        return len(self._sessions)


# Singleton convenabil
memory_manager = MemoryManager()
