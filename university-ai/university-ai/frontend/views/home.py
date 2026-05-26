"""
frontend/views/home.py
══════════════════════
Pagina de start — landing page modernă cu:
  • Hero section cu gradient + CTA
  • Cards cu funcționalități cheie
  • Stats live (documente, fragmente)
  • Footer
"""

import streamlit as st

from backend.config import settings
from backend.core import llm
from backend.core.vector_store import VectorStore
from frontend.components import session


def render() -> None:
    """Randează pagina home."""
    user = session.get_current_user()
    vs = VectorStore()

    # ─── HERO ─────────────────────────────────────────────────────────────────
    st.markdown(
        """
        <div class="hero-container">
            <div class="hero-badge">🎓 ASISTENT VIRTUAL UNIVERSITAR</div>
            <h1 class="hero-title">Răspunsuri precise<br/>din regulamentele facultății</h1>
            <p class="hero-subtitle">
                Asistent AI bazat pe arhitectură <strong>RAG hibridă</strong>,
                cu citare directă din documente oficiale, memorie conversațională
                și răspunsuri exclusiv în limba română.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ─── CTA Buttons (centrate) ──────────────────────────────────────────────
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if user:
            # User logat → mergi direct la chat
            if st.button(
                f"💬 Continuă conversația ca {user['username']}",
                type="primary",
                use_container_width=True,
                key="cta_continue",
            ):
                session.navigate_to(session.PAGE_CHAT)

            if st.button(
                "🚪 Delogare",
                use_container_width=True,
                key="cta_logout_home",
            ):
                session.logout_user()
                st.rerun()
        else:
            cta_a, cta_b = st.columns(2)
            with cta_a:
                if st.button(
                    "🚀 Începe conversația",
                    type="primary",
                    use_container_width=True,
                    key="cta_start_chat",
                ):
                    session.navigate_to(session.PAGE_CHAT)
            with cta_b:
                if st.button(
                    "🔐 Autentificare",
                    use_container_width=True,
                    key="cta_login",
                ):
                    session.navigate_to(session.PAGE_LOGIN)

            st.caption(
                f"👀 Poți încerca **{settings.guest_question_limit} întrebări gratuit** "
                "fără cont. Pentru istoric persistent și acces nelimitat, "
                "creează un cont."
            )

    st.markdown("<div style='height: 60px;'></div>", unsafe_allow_html=True)

    # ─── STATS LIVE ───────────────────────────────────────────────────────────
    st.markdown("### 📊 Status sistem", unsafe_allow_html=True)

    ollama_ok = llm.is_alive()
    doc_count = vs.get_count()
    file_count = len(vs.get_ingested_files())
    models_count = len(llm.list_models()) if ollama_ok else 0

    s1, s2, s3, s4 = st.columns(4)
    with s1:
        st.markdown(
            f'<div class="stat-card"><div class="stat-value">{file_count}</div>'
            f'<div class="stat-label">Documente</div></div>',
            unsafe_allow_html=True,
        )
    with s2:
        st.markdown(
            f'<div class="stat-card"><div class="stat-value">{doc_count}</div>'
            f'<div class="stat-label">Fragmente</div></div>',
            unsafe_allow_html=True,
        )
    with s3:
        st.markdown(
            f'<div class="stat-card"><div class="stat-value">{models_count}</div>'
            f'<div class="stat-label">Modele AI</div></div>',
            unsafe_allow_html=True,
        )
    with s4:
        status_text = "Online" if ollama_ok else "Offline"
        color = "#4cc9a7" if ollama_ok else "#ef476f"
        st.markdown(
            f'<div class="stat-card"><div class="stat-value" style="color: {color}; '
            f'background: none; -webkit-text-fill-color: {color};">●</div>'
            f'<div class="stat-label">{status_text}</div></div>',
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 60px;'></div>", unsafe_allow_html=True)

    # ─── FEATURES ─────────────────────────────────────────────────────────────
    st.markdown("### ✨ Capabilități cheie")

    features = [
        ("🎯", "Retrieval hibrid", "Combină BM25 lexical cu căutare semantică prin "
                                   "Reciprocal Rank Fusion, urmată de re-ranking cu cross-encoder "
                                   "pentru acuratețe maximă."),
        ("🇷🇴", "100% Limba română", "Indiferent cum formulezi întrebarea, "
                                       "răspunsul vine întotdeauna în română academică, "
                                       "cu diacritice și ton politicos."),
        ("📖", "Citare directă", "Fiecare răspuns include sursa exactă: "
                                 "documentul, pagina și articolul (Art. X, Capitolul Y) "
                                 "din regulament."),
        ("🧠", "Memorie conversațională",
         "Reține contextul ultimelor 6 schimburi. "
         "Întrebări scurte de tip referențial sunt automat "
         "reformulate folosind contextul anterior."),
        ("📷", "OCR pentru scanate", "Suportă PDF-uri scanate și imagini "
                                      "(PNG, JPG, TIFF). Extrage textul automat cu "
                                      "Tesseract OCR în română."),
        ("🔒", "Privacy first", "Totul rulează local pe propriul tău server. "
                                "Niciun document și nicio întrebare nu părăsesc "
                                "infrastructura ta."),
    ]

    # Două rânduri de 3 carduri
    for row in range(0, len(features), 3):
        cols = st.columns(3)
        for col, (icon, title, desc) in zip(cols, features[row:row + 3]):
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

    st.markdown("<div style='height: 60px;'></div>", unsafe_allow_html=True)

    # ─── HOW IT WORKS ─────────────────────────────────────────────────────────
    st.markdown("### 🔬 Cum funcționează")

    st.markdown(
        """
        <div style="background: var(--bg-card); border: 1px solid var(--border);
                     border-radius: 16px; padding: 32px; margin-top: 16px;">

        <p style="color: var(--text-secondary); line-height: 1.8;">
        Sistemul folosește o <strong>arhitectură RAG modernă</strong>
        (Retrieval-Augmented Generation) optimizată pentru documente juridice
        și regulamente:
        </p>

        <ol style="color: var(--text-secondary); line-height: 2; margin-left: 20px;">
        <li><strong>Chunking inteligent</strong> — segmentare automată pe „Articolul N",
            „Capitolul X", „Secțiunea Y", păstrând unitățile juridice intacte.</li>
        <li><strong>Indexare hibridă</strong> — embeddings multilingv pentru semantică
            + BM25 pentru potriviri exacte (cifre, articole, denumiri).</li>
        <li><strong>Reciprocal Rank Fusion</strong> — combină cele două liste de candidați
            într-un singur ranking unificat.</li>
        <li><strong>Cross-encoder re-ranking</strong> — modelul <code>BAAI/bge-reranker-v2-m3</code>
            validează top-5 cele mai relevante.</li>
        <li><strong>Generare cu LLM local</strong> — Ollama (llama3.1 / mistral / qwen)
            sintetizează răspunsul cu prompt strict ancorat în context.</li>
        </ol>

        </div>
        """,
        unsafe_allow_html=True,
    )

    # ─── FOOTER ───────────────────────────────────────────────────────────────
    st.markdown(
        """
        <div class="app-footer">
            🎓 Asistent Virtual Universitar · Proiect academic ·
            Python · LangChain · Ollama · ChromaDB
        </div>
        """,
        unsafe_allow_html=True,
    )
