"""
frontend/components/session.py
══════════════════════════════
Helpers pentru gestionarea stării de sesiune Streamlit:
  • user-ul logat (sau None pentru guest)
  • chat-ul curent activ
  • contorul guest pentru limită de întrebări
  • navigare între pagini
"""

import uuid
from typing import Optional

import streamlit as st

from backend.config import settings


# ── Pagini disponibile în router ──────────────────────────────────────────────

PAGE_HOME = "home"
PAGE_LOGIN = "login"
PAGE_REGISTER = "register"
PAGE_CHAT = "chat"

VALID_PAGES = {PAGE_HOME, PAGE_LOGIN, PAGE_REGISTER, PAGE_CHAT}


def init_session() -> None:
    """Inițializează cheile de session_state la prima rulare."""
    defaults = {
        "page": PAGE_HOME,
        "user": None,                       # dict cu profil sau None
        "active_chat_id": None,             # int — id-ul chat-ului curent
        "active_session_id": uuid.uuid4().hex[:16],   # pentru memoria RAG
        "messages": [],                     # mesaje în chat-ul curent
        "guest_questions_used": 0,          # contor guest
        "selected_model": settings.ollama_model,
        "show_chunks": False,
        "show_rewritten": True,
        "auth_error": None,                 # mesaj de eroare pentru forms
        "auth_success": None,               # mesaj de succes
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


# ── Navigare ──────────────────────────────────────────────────────────────────

def navigate_to(page: str) -> None:
    """Navighează spre o altă pagină."""
    if page not in VALID_PAGES:
        page = PAGE_HOME
    st.session_state.page = page
    # Curățăm mesajele de auth la fiecare navigare
    st.session_state.auth_error = None
    st.session_state.auth_success = None
    st.rerun()


def current_page() -> str:
    return st.session_state.get("page", PAGE_HOME)


# ── User ──────────────────────────────────────────────────────────────────────

def get_current_user() -> Optional[dict]:
    return st.session_state.get("user")


def is_authenticated() -> bool:
    return get_current_user() is not None


def login_user(user: dict) -> None:
    """Setează utilizatorul logat și resetează contorul guest."""
    st.session_state.user = user
    st.session_state.guest_questions_used = 0
    st.session_state.auth_error = None
    st.session_state.auth_success = None
    # Resetăm conversația curentă — utilizatorul își va încărca propriile chat-uri
    st.session_state.messages = []
    st.session_state.active_chat_id = None
    st.session_state.active_session_id = uuid.uuid4().hex[:16]


def logout_user() -> None:
    """Delogare — resetăm toate datele sensibile din sesiune."""
    st.session_state.user = None
    st.session_state.active_chat_id = None
    st.session_state.messages = []
    st.session_state.guest_questions_used = 0
    st.session_state.active_session_id = uuid.uuid4().hex[:16]


# ── Guest limits ──────────────────────────────────────────────────────────────

def increment_guest_counter() -> None:
    st.session_state.guest_questions_used = st.session_state.get(
        "guest_questions_used", 0
    ) + 1


def guest_questions_remaining() -> int:
    used = st.session_state.get("guest_questions_used", 0)
    return max(0, settings.guest_question_limit - used)


def guest_limit_reached() -> bool:
    """True dacă guest-ul a atins limita de întrebări."""
    if is_authenticated():
        return False  # userii logați nu au limită
    return guest_questions_remaining() <= 0


# ── Chat curent ───────────────────────────────────────────────────────────────

def set_active_chat(chat_id: Optional[int], session_id: Optional[str] = None) -> None:
    st.session_state.active_chat_id = chat_id
    if session_id:
        st.session_state.active_session_id = session_id
    else:
        st.session_state.active_session_id = uuid.uuid4().hex[:16]


def get_user_initials(user: dict) -> str:
    """Returnează inițialele utilizatorului pentru avatar (max 2 caractere)."""
    name = user.get("full_name") or user.get("username") or "?"
    parts = name.split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return name[:2].upper()
