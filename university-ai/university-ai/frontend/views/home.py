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
                f"💬 Continuă conversația ca {user['username']}",
                type="primary",
                use_container_width=True,
                key="cta_continue",
            ):
                session.navigate_to(session.PAGE_CHAT)
        else:
            cta_a, cta_b = st.columns(2)
            with cta_a:
                if st.button(
                    "🚀 Începe gratuit",
                    type="primary",
                    use_container_width=True,
                    key="cta_start_chat",
                ):
                    session.navigate_to(session.PAGE_CHAT)
            with cta_b:
                if st.button(
                    "✨ Creează cont",
                    use_container_width=True,
                    key="cta_register",
                ):
                    session.navigate_to(session.PAGE_REGISTER)

            st.caption(
                "Poți încerca câteva întrebări gratuit, fără cont. "
                "Creează un cont pentru conversații nelimitate și istoric salvat."
            )

    st.markdown("<div style='height: 70px;'></div>", unsafe_allow_html=True)

    # ─── BENEFICII (prietenoase, fără jargon tehnic) ──────────────────────────
    st.markdown("### De ce ClaudiuAI?")

    benefits = [
        ("💬", "Conversație naturală",
         "Întreabă exact cum ai vorbi cu un coleg. Înțelege întrebări simple "
         "sau complexe și îți răspunde la obiect."),
        ("🇷🇴", "Mereu în limba română",
         "Indiferent cum formulezi întrebarea, primești răspuns clar și corect "
         "în limba română."),
        ("⚡", "Răspunsuri rapide",
         "Fără să cauți prin zeci de pagini — pui întrebarea și ai răspunsul "
         "în câteva secunde."),
        ("📚", "Istoric salvat",
         "Cu un cont, toate conversațiile tale sunt salvate și le poți relua "
         "oricând, de unde ai rămas."),
        ("🔒", "Datele tale, private",
         "Conversațiile tale rămân ale tale. Totul rulează în siguranță, "
         "fără să-ți expună informațiile."),
        ("🕐", "Disponibil non-stop",
         "Zi sau noapte, ClaudiuAI e gata să te ajute ori de câte ori ai nevoie."),
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
            if st.button("💬 Deschide chat-ul", type="primary",
                         use_container_width=True, key="cta_bottom"):
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
