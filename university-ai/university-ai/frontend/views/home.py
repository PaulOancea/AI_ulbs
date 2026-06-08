"""
frontend/views/home.py
══════════════════════
Pagina de start ClaudiuAI — landing page modernă, orientată spre utilizator.

Conține DOAR informații relevante pentru un vizitator obișnuit:
  • navbar cu brand + navigare
  • hero cu logo, titlu și call-to-action
  • beneficii prezentate prietenos (fără jargon tehnic)

NU conține detalii de administrare (status sistem, capabilități tehnice,
„cum funcționează sub capotă") — acelea trăiesc în panoul de admin din chat.
"""

import streamlit as st

from frontend.components import session
from frontend.components.navbar import brand_html, render_navbar


# ── Iconițe SVG simple (line-style, fără emoji) pentru cardurile de funcții ────
# Fiecare SVG e pe o singură linie (altfel Markdown îl tratează drept cod).
_SVG = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
    'stroke-linecap="round" stroke-linejoin="round" width="28" height="28">'
)

ICON_CHAT = _SVG + '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>'
ICON_DOC = _SVG + '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="13" y2="17"/></svg>'
ICON_CALENDAR = _SVG + '<rect x="3" y="4" width="18" height="18" rx="2"/><line x1="3" y1="10" x2="21" y2="10"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="16" y1="2" x2="16" y2="6"/></svg>'
ICON_UPLOAD = _SVG + '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>'
ICON_HISTORY = _SVG + '<circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 14"/></svg>'
ICON_GLOBE = _SVG + '<circle cx="12" cy="12" r="9"/><line x1="3" y1="12" x2="21" y2="12"/><path d="M12 3a14 14 0 0 1 0 18 14 14 0 0 1 0-18"/></svg>'


def render() -> None:
    """Randează pagina home."""
    user = session.get_current_user()

    # ─── NAVBAR ───────────────────────────────────────────────────────────────
    render_navbar(active=session.PAGE_HOME)

    # ─── HERO ─────────────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div class="hero-container">
            <div class="hero-logo">{brand_html(size=72, font_size="2.6em", uid="hero")}</div>
            <h1 class="hero-title">Asistentul tău inteligent,<br/>disponibil oricând</h1>
            <p class="hero-subtitle" style="text-align: center;margin: 0 auto; max-width: 800px;">
                Pune o întrebare în limba română și primești un răspuns clar,
                pe înțelesul tău, în câteva secunde. Simplu, rapid și mereu la îndemână.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ─── CTA Buttons (centrate) ──────────────────────────────────────────────
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if user:
            if st.button(
                f"Continuă conversația ca {user['username']}",
                type="primary",
                use_container_width=True,
                key="cta_continue",
                icon=":material/chat:",
            ):
                session.navigate_to(session.PAGE_CHAT)
        else:
            cta_a, cta_b = st.columns(2)
            with cta_a:
                if st.button(
                    "Începe gratuit",
                    type="primary",
                    use_container_width=True,
                    key="cta_start_chat",
                    icon=":material/rocket_launch:",
                ):
                    session.navigate_to(session.PAGE_CHAT)
            with cta_b:
                if st.button(
                    "Creează cont",
                    use_container_width=True,
                    key="cta_register",
                    icon=":material/person_add:",
                ):
                    session.navigate_to(session.PAGE_REGISTER)

            st.caption(
                "Poți încerca câteva întrebări gratuit, fără cont. "
                "Creează un cont pentru conversații nelimitate și istoric salvat."
            )

    st.markdown("<div style='height: 70px;'></div>", unsafe_allow_html=True)

    # ─── FUNCȚIONALITĂȚI (carduri orientate pe ce poate face produsul) ────────
    st.markdown("### Ce poți face cu ClaudiuAI?")

    benefits = [
        (ICON_CHAT, "Întrebări pe documente",
         "Pune întrebări în limba română despre regulamente și proceduri și "
         "primești răspunsuri clare, cu citarea sursei."),
        (ICON_DOC, "Completare cereri",
         "Spune-mi datele tale și îți completez automat cererea-model, gata "
         "de descărcat ca document .docx."),
        (ICON_CALENDAR, "Deadline-uri + Calendar",
         "Detectez termenele-limită din răspunsuri și îți ofer un buton pentru "
         "a le adăuga direct în Google Calendar."),
        (ICON_UPLOAD, "Upload documente",
         "Atașează un PDF, DOCX sau o imagine și pune întrebări direct pe baza "
         "conținutului lui (cu OCR automat)."),
        (ICON_HISTORY, "Istoric salvat",
         "Cu un cont, toate conversațiile tale sunt salvate și le poți relua "
         "oricând, de unde ai rămas."),
        (ICON_GLOBE, "Mereu în limba română",
         "Indiferent cum formulezi întrebarea, primești răspuns clar și corect "
         "în limba română."),
    ]

    for row in range(0, len(benefits), 3):
        cols = st.columns(3)
        for col, (icon, title, desc) in zip(cols, benefits[row:row + 3]):
            with col:
                st.markdown(
                    f"""
                    <div class="feature-card">
                        <div class="feature-icon">{icon}</div>
                        <div class="feature-title">{title}</div>
                        <div class="feature-desc">{desc}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    st.markdown("<div style='height: 50px;'></div>", unsafe_allow_html=True)

    # ─── CTA final ────────────────────────────────────────────────────────────
    if not user:
        cc1, cc2, cc3 = st.columns([1, 2, 1])
        with cc2:
            st.markdown(
                """
                <div class="cta-banner">
                    <h3>Gata să începi?</h3>
                    <p>Pune prima ta întrebare chiar acum.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("Deschide chat-ul", type="primary",
                         use_container_width=True, key="cta_bottom",
                         icon=":material/chat:"):
                session.navigate_to(session.PAGE_CHAT)

    # ─── FOOTER ───────────────────────────────────────────────────────────────
    st.markdown(
        """
        <div class="app-footer">
            ClaudiuAI · Asistentul tău conversațional inteligent
        </div>
        """,
        unsafe_allow_html=True,
    )
