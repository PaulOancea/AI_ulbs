"""
frontend/views/auth.py
══════════════════════
Pagini de autentificare: login + register.

Formulare cu validare client-side minimă; validarea reală e în
`backend.auth.service` (care ridică excepții cu mesaje în română).
"""

import streamlit as st

from backend.auth import service as auth_service
from backend.auth.service import (
    AuthError,
    EmailTakenError,
    InvalidCredentialsError,
    UsernameTakenError,
    ValidationError,
)
from backend.config import settings
from backend.logging_config import logger
from frontend.components import session


# ─── Helpers UI ───────────────────────────────────────────────────────────────

def _render_header(title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="auth-container">
            <div class="auth-title">{title}</div>
            <div class="auth-subtitle">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _back_button():
    if st.button("← Înapoi la pagina principală", key="auth_back"):
        session.navigate_to(session.PAGE_HOME)


def _show_messages():
    if st.session_state.get("auth_error"):
        st.error(st.session_state.auth_error)
    if st.session_state.get("auth_success"):
        st.success(st.session_state.auth_success)


# ═══════════════════════════════════════════════════════════════════════════════
#  LOGIN
# ═══════════════════════════════════════════════════════════════════════════════

def render_login() -> None:
    """Pagina de login."""
    col_a, col_b, col_c = st.columns([1, 2, 1])
    with col_b:
        _render_header(
            "Autentificare",
            "Conectează-te pentru istoric persistent și acces nelimitat",
        )

        _show_messages()

        with st.form("login_form", clear_on_submit=False):
            identifier = st.text_input(
                "Nume utilizator sau email",
                placeholder="ex: ion.popescu sau ion@univ.ro",
                key="login_identifier",
            )
            password = st.text_input(
                "Parolă",
                type="password",
                key="login_password",
            )

            submitted = st.form_submit_button(
                "Conectare", type="primary", use_container_width=True
            )

            if submitted:
                try:
                    user = auth_service.authenticate(identifier, password)
                    session.login_user(user)
                    st.session_state.auth_success = (
                        f"Bun venit, {user['full_name'] or user['username']}!"
                    )
                    logger.info("UI: login OK pentru {}", user["username"])
                    session.navigate_to(session.PAGE_CHAT)
                except (InvalidCredentialsError, ValidationError) as exc:
                    st.session_state.auth_error = exc.message
                    st.rerun()
                except AuthError as exc:
                    st.session_state.auth_error = exc.message
                    st.rerun()
                except Exception as exc:
                    logger.exception("Eroare neașteptată la login")
                    st.session_state.auth_error = "Eroare internă. Încearcă din nou."
                    st.rerun()

        st.divider()

        col_l, col_r = st.columns(2)
        with col_l:
            if st.button("Nu ai cont? Creează unul", use_container_width=True):
                session.navigate_to(session.PAGE_REGISTER)
        with col_r:
            if st.button("Continuă ca invitat", use_container_width=True):
                session.navigate_to(session.PAGE_CHAT)

        _back_button()


# ═══════════════════════════════════════════════════════════════════════════════
#  REGISTER
# ═══════════════════════════════════════════════════════════════════════════════

def render_register() -> None:
    """Pagina de înregistrare cont nou."""
    col_a, col_b, col_c = st.columns([1, 2, 1])
    with col_b:
        _render_header(
            "Cont nou",
            "Înregistrare gratuită — toate funcționalitățile activate",
        )

        _show_messages()

        with st.form("register_form", clear_on_submit=False):
            full_name = st.text_input(
                "Nume complet (opțional)",
                placeholder="ex: Ion Popescu",
            )
            username = st.text_input(
                "Nume utilizator *",
                placeholder="3-32 caractere, litere/cifre/_.-",
            )
            email = st.text_input(
                "Email *",
                placeholder="ion.popescu@univ.ro",
            )
            password = st.text_input(
                "Parolă *",
                type="password",
                help=f"Minim {settings.password_min_length} caractere",
            )
            password_confirm = st.text_input(
                "Confirmă parola *",
                type="password",
            )

            agree = st.checkbox(
                "Sunt de acord cu folosirea datelor pentru istoricul propriu de chat",
                value=True,
            )

            submitted = st.form_submit_button(
                "Creează cont", type="primary", use_container_width=True
            )

            if submitted:
                if not agree:
                    st.session_state.auth_error = (
                        "Trebuie să fii de acord cu termenii pentru a continua."
                    )
                    st.rerun()

                if password != password_confirm:
                    st.session_state.auth_error = "Parolele nu coincid."
                    st.rerun()

                try:
                    user = auth_service.register_user(
                        username=username,
                        email=email,
                        password=password,
                        full_name=full_name,
                    )
                    # Autologin după înregistrare reușită
                    session.login_user(user)
                    st.session_state.auth_success = (
                        f"Cont creat cu succes! Bun venit, {user['username']}."
                    )
                    logger.info("UI: cont nou + autologin {}", user["username"])
                    session.navigate_to(session.PAGE_CHAT)
                except (UsernameTakenError, EmailTakenError, ValidationError) as exc:
                    st.session_state.auth_error = exc.message
                    st.rerun()
                except Exception as exc:
                    logger.exception("Eroare la register")
                    st.session_state.auth_error = "Eroare internă. Încearcă din nou."
                    st.rerun()

        st.divider()

        if st.button(
            "Ai deja cont? Conectează-te",
            use_container_width=True,
            key="reg_to_login",
        ):
            session.navigate_to(session.PAGE_LOGIN)

        _back_button()
