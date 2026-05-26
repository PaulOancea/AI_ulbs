"""
frontend/streamlit_app.py
═════════════════════════
ROUTER PRINCIPAL al aplicației Streamlit.

Această aplicație este structurată ca un SPA (single-page-app) cu navigare
prin `st.session_state.page`. Pagini disponibile:
  • home      — landing page modernă (default la primul acces)
  • login     — autentificare
  • register  — creare cont nou
  • chat      — interfața principală de chat cu istoric persistent

Rulare:
    streamlit run frontend/streamlit_app.py
"""

import sys
from pathlib import Path

# Asigurăm că backend e importabil indiferent de unde rulăm
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from backend.logging_config import setup_logging
from frontend.components import session
from frontend.components.styles import inject_global_css
from frontend.views import auth as auth_view
from frontend.views import chat as chat_view
from frontend.views import home as home_view


# ═══════════════════════════════════════════════════════════════════════════════
#  CONFIGURARE PAGINĂ
# ═══════════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="🎓 AI Universitar",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": None,
        "Report a bug": None,
        "About": "Asistent Virtual Universitar — proiect academic RAG.",
    },
)


# ═══════════════════════════════════════════════════════════════════════════════
#  SETUP UNIC
# ═══════════════════════════════════════════════════════════════════════════════

@st.cache_resource
def _bootstrap():
    """Inițializare unică: logging + ensure DB."""
    setup_logging()
    # Forțăm crearea tabelelor SQLite la primul start
    from backend.auth.database import _ensure_initialized
    _ensure_initialized()
    return True


_bootstrap()

# CSS global (re-injectat la fiecare rerun — necesar pentru Streamlit)
inject_global_css()

# Inițializare session state
session.init_session()


# ═══════════════════════════════════════════════════════════════════════════════
#  ROUTER
# ═══════════════════════════════════════════════════════════════════════════════

PAGE_DISPATCH = {
    session.PAGE_HOME: home_view.render,
    session.PAGE_LOGIN: auth_view.render_login,
    session.PAGE_REGISTER: auth_view.render_register,
    session.PAGE_CHAT: chat_view.render,
}


def main():
    current = session.current_page()
    render_func = PAGE_DISPATCH.get(current, home_view.render)
    render_func()


main()
