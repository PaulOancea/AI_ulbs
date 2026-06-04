"""
frontend/views/shared.py
════════════════════════
Vizualizare PUBLICĂ (read-only) a unei conversații partajate.

Accesibilă fără autentificare, prin parametrul de adresă `?share=<token>`.
Afișează doar mesajele, fără posibilitatea de a scrie sau modifica.
"""

import streamlit as st

from backend.auth import service as auth_service
from frontend.components import session
from frontend.components.navbar import brand_html


def render(token: str) -> None:
    """Randează o conversație partajată după token."""
    # Brand (logo) sus
    st.markdown(brand_html(uid="shared"), unsafe_allow_html=True)
    st.markdown('<div class="nav-rule"></div>', unsafe_allow_html=True)

    chat = auth_service.get_shared_chat(token)
    if not chat:
        st.error("🔗 Link invalid sau conversația nu mai este partajată.")
        if st.button("🏠 Mergi la ClaudiuAI"):
            st.query_params.clear()
            session.navigate_to(session.PAGE_HOME)
        return

    st.markdown(f"### {chat['title']}")
    st.caption("Conversație partajată · doar citire")

    messages = auth_service.get_messages(chat["id"])
    for m in messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            if m["role"] == "assistant" and m.get("sources"):
                badges = " ".join(
                    f'<span class="source-badge">📄 {s}</span>' for s in m["sources"]
                )
                st.markdown(
                    f'<div style="margin-top:8px;"><strong>📚 Surse:</strong><br/>{badges}</div>',
                    unsafe_allow_html=True,
                )

    st.divider()
    cc1, cc2, cc3 = st.columns([1, 2, 1])
    with cc2:
        st.caption("Vrei să pui propriile întrebări?")
        if st.button("💬 Încearcă ClaudiuAI", type="primary",
                     use_container_width=True, key="shared_cta"):
            st.query_params.clear()
            session.navigate_to(session.PAGE_CHAT)
