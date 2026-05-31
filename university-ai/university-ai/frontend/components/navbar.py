"""
frontend/components/navbar.py
═════════════════════════════
Brand ClaudiuAI (logo SVG) + bară de navigare partajată între pagini.

Logo-ul e un SVG inline (scalabil, fără fișiere binare): un badge cu gradient
și o bulă de chat cu o scânteie — sugerând „asistent conversațional inteligent".
"""

import streamlit as st

from frontend.components import session


def logo_svg(size: int = 40, uid: str = "main") -> str:
    """
    Returnează marca SVG a brandului, pe o SINGURĂ linie. `uid` evită coliziuni
    de id la gradient. HTML-ul trebuie să fie pe o linie, altfel Streamlit/Markdown
    interpretează liniile indentate drept bloc de cod și afișează tag-urile ca text.
    """
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 48 48" fill="none" '
        f'xmlns="http://www.w3.org/2000/svg" style="flex-shrink:0;display:block;">'
        f'<defs><linearGradient id="lg-{uid}" x1="0" y1="0" x2="48" y2="48" '
        f'gradientUnits="userSpaceOnUse">'
        f'<stop stop-color="#4361ee"/><stop offset="0.55" stop-color="#7209b7"/>'
        f'<stop offset="1" stop-color="#f72585"/></linearGradient></defs>'
        f'<rect width="48" height="48" rx="13" fill="url(#lg-{uid})"/>'
        f'<path d="M13 15.5h22a3 3 0 0 1 3 3v9.5a3 3 0 0 1-3 3H22.5l-6.5 5.2v-5.2H13 '
        f'a3 3 0 0 1-3-3v-9.5a3 3 0 0 1 3-3z" fill="#ffffff" fill-opacity="0.95"/>'
        f'<path d="M24 18.2l1.55 3.45L29 23.2l-3.45 1.55L24 28.2l-1.55-3.45L19 23.2l3.45-1.55z" '
        f'fill="#7209b7"/></svg>'
    )


def brand_html(size: int = 40, font_size: str = "1.45em", uid: str = "main") -> str:
    """Logo + wordmark „ClaudiuAI" (HTML pe o singură linie)."""
    return (
        f'<div class="brand">{logo_svg(size, uid)}'
        f'<span class="brand-name" style="font-size:{font_size};">'
        f'Claudiu<span class="brand-accent">AI</span></span></div>'
    )


def render_navbar(active: str = "") -> None:
    """
    Bară de navigare orizontală: brand în stânga, link-uri în dreapta.
    Link-urile sunt butoane Streamlit (funcționale), stilizate ca un navbar.
    """
    user = session.get_current_user()

    left, right = st.columns([2, 3])
    with left:
        st.markdown(brand_html(uid="nav"), unsafe_allow_html=True)

    with right:
        if user:
            items = [
                ("🏠 Acasă", session.PAGE_HOME),
                ("💬 Chat", session.PAGE_CHAT),
                ("🚪 Logout", "__logout__"),
            ]
        else:
            items = [
                ("🏠 Acasă", session.PAGE_HOME),
                ("💬 Chat", session.PAGE_CHAT),
                ("🔐 Login", session.PAGE_LOGIN),
                ("✨ Cont nou", session.PAGE_REGISTER),
            ]

        cols = st.columns(len(items))
        for col, (label, target) in zip(cols, items):
            with col:
                is_active = target == active
                if st.button(
                    label,
                    key=f"nav_{target}",
                    use_container_width=True,
                    type="primary" if is_active else "secondary",
                ):
                    if target == "__logout__":
                        session.logout_user()
                        session.navigate_to(session.PAGE_HOME)
                    else:
                        session.navigate_to(target)

    st.markdown('<div class="nav-rule"></div>', unsafe_allow_html=True)
