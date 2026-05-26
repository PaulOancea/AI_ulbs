"""
frontend/views/chat.py
══════════════════════
Pagina principală de chat — versiunea cu suport pentru:
  • Utilizatori autentificați (istoric persistent în SQLite)
  • Guest mode (limită de N întrebări, fără persistență)
  • Sidebar cu lista chat-urilor
  • Upload de PDF/DOCX/imagini (cu OCR automat)
"""

import uuid

import streamlit as st

from backend.auth import service as auth_service
from backend.config import settings
from backend.core import llm
from backend.core.ingestion import IngestionService
from backend.core.memory import memory_manager
from backend.core.ocr import is_tesseract_available
from backend.core.rag_chain import RAGChain
from backend.core.vector_store import VectorStore
from backend.exceptions import AppException
from backend.logging_config import logger
from frontend.components import session


# ═══════════════════════════════════════════════════════════════════════════════
#  Resurse cached (initializate o singură dată)
# ═══════════════════════════════════════════════════════════════════════════════

@st.cache_resource(show_spinner=False)
def _get_resources():
    vs = VectorStore()
    chain = RAGChain()
    ingestion = IngestionService(vs)
    return vs, chain, ingestion


# ═══════════════════════════════════════════════════════════════════════════════
#  Helpers pentru istoricul chat-urilor (persistent)
# ═══════════════════════════════════════════════════════════════════════════════

def _load_chat_into_session(chat_id: int) -> None:
    """Încarcă un chat din DB în session_state."""
    chat = auth_service.get_chat(chat_id)
    if not chat:
        return
    messages = auth_service.get_messages(chat_id)
    st.session_state.messages = [
        {
            "role": m["role"],
            "content": m["content"],
            "sources": m.get("sources", []) or [],
            "rewritten": m.get("rewritten"),
            "chunks": [],  # nu persistăm chunks (prea mari) — doar sursele
        }
        for m in messages
    ]
    session.set_active_chat(chat_id, session_id=chat["session_id"])

    # Reumplem și memoria RAG cu istoricul
    mem = memory_manager.get_or_create(chat["session_id"])
    mem.clear()
    for m in messages:
        if m["role"] == "user":
            mem.add_user(m["content"])
        else:
            mem.add_assistant(m["content"])


def _ensure_chat_exists(user: dict, first_question: str) -> int:
    """
    Dacă utilizatorul nu are un chat activ, creează unul.
    Returnează chat_id.
    """
    chat_id = st.session_state.get("active_chat_id")
    if chat_id:
        return chat_id

    title = auth_service.auto_title_from_question(first_question)
    chat = auth_service.create_chat(user["id"], title=title)
    # Folosim session_id-ul din DB (consistent cu memoria RAG)
    session.set_active_chat(chat["id"], session_id=chat["session_id"])
    return chat["id"]


# ═══════════════════════════════════════════════════════════════════════════════
#  SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════════

def _render_sidebar(vs, ingestion):
    user = session.get_current_user()
    ollama_ok = llm.is_alive()
    doc_count = vs.get_count()
    file_count = len(vs.get_ingested_files())
    models = llm.list_models() if ollama_ok else []

    with st.sidebar:
        # ── Header / user info ────────────────────────────────────────────────
        if user:
            initials = session.get_user_initials(user)
            display_name = user.get("full_name") or user["username"]
            st.markdown(
                f"""
                <div class="user-chip">
                    <div class="user-avatar">{initials}</div>
                    <div>
                        <div class="user-name">{display_name}</div>
                        <div class="user-meta">@{user['username']}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("🚪 Delogare", use_container_width=True, key="sb_logout"):
                session.logout_user()
                session.navigate_to(session.PAGE_HOME)
        else:
            remaining = session.guest_questions_remaining()
            st.markdown(
                f"""
                <div class="user-chip">
                    <div class="user-avatar" style="background: #6c757d;">👤</div>
                    <div>
                        <div class="user-name">Invitat</div>
                        <div class="user-meta">{remaining} întrebări rămase</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            c1, c2 = st.columns(2)
            with c1:
                if st.button("🔐 Login", use_container_width=True, key="sb_login"):
                    session.navigate_to(session.PAGE_LOGIN)
            with c2:
                if st.button("✨ Cont", use_container_width=True, key="sb_register"):
                    session.navigate_to(session.PAGE_REGISTER)

        if st.button("🏠 Pagina principală", use_container_width=True, key="sb_home"):
            session.navigate_to(session.PAGE_HOME)

        st.divider()

        # ── Istoric chat (doar pentru useri logați) ───────────────────────────
        if user:
            st.markdown("### 💬 Conversațiile tale")

            if st.button("➕ Conversație nouă", type="primary",
                         use_container_width=True, key="sb_new_chat"):
                st.session_state.messages = []
                session.set_active_chat(None)
                st.rerun()

            chats = auth_service.list_user_chats(user["id"], limit=30)
            active_id = st.session_state.get("active_chat_id")

            if not chats:
                st.caption("Nicio conversație încă. Pune prima întrebare!")
            else:
                for chat in chats:
                    is_active = chat["id"] == active_id
                    title = chat["title"]
                    msg_count = chat.get("message_count", 0)

                    col_main, col_del = st.columns([5, 1])
                    with col_main:
                        button_label = ("🟢 " if is_active else "💬 ") + (
                            title[:32] + "…" if len(title) > 32 else title
                        )
                        if st.button(
                            button_label,
                            key=f"chat_btn_{chat['id']}",
                            use_container_width=True,
                            help=f"{msg_count} mesaje · {chat['updated_at']}",
                        ):
                            _load_chat_into_session(chat["id"])
                            st.rerun()
                    with col_del:
                        if st.button("🗑", key=f"del_chat_{chat['id']}",
                                     help="Șterge conversația"):
                            auth_service.delete_chat(chat["id"], user["id"])
                            if is_active:
                                st.session_state.messages = []
                                session.set_active_chat(None)
                            st.rerun()

            st.divider()

        # ── Status sistem ─────────────────────────────────────────────────────
        st.markdown("**Status sistem**")
        c1, c2 = st.columns(2)
        with c1:
            dot = "ok" if ollama_ok else "err"
            text = "Ollama" if ollama_ok else "Offline"
            st.markdown(
                f'<div class="status-pill"><span class="status-dot {dot}"></span> {text}</div>',
                unsafe_allow_html=True,
            )
        with c2:
            dot = "ok" if doc_count > 0 else "warn"
            st.markdown(
                f'<div class="status-pill"><span class="status-dot {dot}"></span> '
                f'{file_count} docs</div>',
                unsafe_allow_html=True,
            )

        ocr_ok = is_tesseract_available()
        ocr_text = "OCR activ" if ocr_ok else "OCR offline"
        ocr_dot = "ok" if ocr_ok else "warn"
        st.markdown(
            f'<div class="status-pill" style="margin-top:8px;">'
            f'<span class="status-dot {ocr_dot}"></span> {ocr_text}</div>',
            unsafe_allow_html=True,
        )

        # ── Model selector ────────────────────────────────────────────────────
        if models:
            st.markdown("**Model AI**")
            idx = (
                models.index(settings.ollama_model)
                if settings.ollama_model in models else 0
            )
            sel = st.selectbox(
                "model", options=models, index=idx,
                label_visibility="collapsed",
            )
            st.session_state.selected_model = sel

        st.divider()

        # ── Upload documente ──────────────────────────────────────────────────
        with st.expander("📂 Adaugă documente"):
            allowed_types = ["pdf", "docx", "txt"]
            if ocr_ok:
                allowed_types += ["png", "jpg", "jpeg", "tiff", "bmp"]

            uploaded = st.file_uploader(
                "Selectează fișiere",
                type=allowed_types,
                accept_multiple_files=True,
                label_visibility="collapsed",
                key="chat_uploader",
            )
            force = st.checkbox("Re-indexează dacă există", value=False, key="force_idx")

            if uploaded and st.button(
                f"Indexează {len(uploaded)}",
                type="primary",
                use_container_width=True,
                key="do_index",
            ):
                progress = st.progress(0)
                results = []
                for i, uf in enumerate(uploaded):
                    with st.spinner(f"Procesez {uf.name}..."):
                        res = ingestion.ingest_file_bytes(uf.read(), uf.name, force=force)
                    results.append(res)
                    progress.progress((i + 1) / len(uploaded))

                for r in results:
                    icon = {"ok": "✅", "skip": "⏭", "error": "❌"}[r["status"]]
                    msg = f"{icon} **{r['filename']}**"
                    if r["status"] == "ok":
                        msg += f" — {r['chunks']} fragmente"
                    elif r.get("message"):
                        msg += f" — {r['message']}"
                    st.write(msg)

                st.cache_resource.clear()
                st.rerun()

        # ── Setări avansate ───────────────────────────────────────────────────
        with st.expander("⚙️ Setări avansate"):
            st.session_state.show_chunks = st.toggle(
                "Afișează fragmentele",
                value=st.session_state.show_chunks,
            )
            st.session_state.show_rewritten = st.toggle(
                "Afișează întrebarea reformulată",
                value=st.session_state.show_rewritten,
            )


# ═══════════════════════════════════════════════════════════════════════════════
#  RANDARE CHAT
# ═══════════════════════════════════════════════════════════════════════════════

def _render_chunks(chunks: list):
    if not chunks:
        return
    with st.expander(f"🔍 {len(chunks)} fragmente folosite ca sursă"):
        for i, ch in enumerate(chunks, 1):
            score_pct = int(ch.get("score", 0) * 100)
            chips = f'<span class="score-chip">dense: {score_pct}%</span>'
            if ch.get("rerank_score") is not None:
                chips += f'<span class="rerank-chip">rerank: {ch["rerank_score"]:.2f}</span>'

            section = ch.get("section", "")
            section_str = f" · {section}" if section else ""
            ocr_chip = ' <span class="ocr-chip">OCR</span>' if ch.get("extra", {}).get("ocr") else ""

            st.markdown(
                f"**Fragment {i}** — `{ch['source']}` · pag. {ch['page']}{section_str} {chips}{ocr_chip}",
                unsafe_allow_html=True,
            )
            text = ch.get("text", "")
            preview = text[:600] + ("..." if len(text) > 600 else "")
            st.markdown(f'<div class="citation-block">{preview}</div>', unsafe_allow_html=True)


def _render_message_history():
    """Afișează istoricul mesajelor curente."""
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

            if msg["role"] == "assistant":
                if msg.get("rewritten") and st.session_state.show_rewritten:
                    st.caption(f'🔄 Reformulat: *„{msg["rewritten"]}"*')

                if msg.get("sources"):
                    badges = " ".join(
                        f'<span class="source-badge">📄 {s}</span>'
                        for s in msg["sources"]
                    )
                    st.markdown(
                        f'<div style="margin-top:8px;"><strong>📚 Surse:</strong><br/>{badges}</div>',
                        unsafe_allow_html=True,
                    )

                if st.session_state.show_chunks and msg.get("chunks"):
                    _render_chunks(msg["chunks"])


def _render_welcome():
    """Mesajul de bun-venit afișat când nu există mesaje încă."""
    user = session.get_current_user()
    vs, _, _ = _get_resources()
    doc_count = vs.get_count()
    file_count = len(vs.get_ingested_files())

    if doc_count == 0:
        st.markdown(
            """
            <div class="intro-box">
            <h4>👋 Bun venit!</h4>
            <p>Pentru a începe, adaugă regulamentele facultății:</p>
            <ol>
            <li>Pornește <code>ollama serve</code> dacă nu rulează</li>
            <li>Încarcă fișiere PDF/DOCX/imagini din meniul lateral</li>
            <li>Pune întrebarea ta!</li>
            </ol>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    if user:
        greeting = f"Bun venit, <strong>{user.get('full_name') or user['username']}</strong>!"
        sub = "Pune-mi orice întrebare despre regulamente."
    else:
        remaining = session.guest_questions_remaining()
        greeting = "👋 <strong>Salut!</strong>"
        sub = (
            f"Ești în modul invitat — mai ai <strong>{remaining} întrebări</strong>. "
            "Creează un cont pentru acces nelimitat și istoric."
        )

    st.markdown(
        f"""
        <div class="intro-box">
        <h4>{greeting}</h4>
        <p>{sub}</p>
        <p>Am acces la <strong>{doc_count} fragmente</strong> din
        <strong>{file_count} documente</strong>.</p>
        <p><strong>Exemple:</strong></p>
        <ul>
        <li><em>„Care sunt condițiile de promovare?"</em></li>
        <li><em>„Cum se calculează media de licență?"</em></li>
        <li><em>„Procedura de contestare a unei note?"</em></li>
        </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  PUNCT DE INTRARE
# ═══════════════════════════════════════════════════════════════════════════════

def render() -> None:
    """Punctul de intrare apelat de router."""
    vs, chain, ingestion = _get_resources()
    _render_sidebar(vs, ingestion)

    user = session.get_current_user()

    # ── Header ────────────────────────────────────────────────────────────────
    st.title("🎓 Asistent Virtual Universitar")
    st.caption(
        "Răspunsuri din regulamentele oficiale, în română, "
        "cu citare directă și memorie conversațională."
    )

    # ── Avertizare guest limită ───────────────────────────────────────────────
    if not user:
        remaining = session.guest_questions_remaining()
        if remaining <= 1:
            st.markdown(
                f"""
                <div class="guest-warning">
                ⚠️ <strong>Mod invitat:</strong> {remaining} întrebare rămasă.
                <a href="#" onclick="return false;">Creează un cont</a>
                pentru acces nelimitat și istoric persistent.
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("✨ Creează cont acum", type="primary", key="warn_register"):
                session.navigate_to(session.PAGE_REGISTER)

    # ── Welcome sau istoric ──────────────────────────────────────────────────
    if not st.session_state.messages:
        _render_welcome()
    else:
        _render_message_history()

    # ── Input utilizator ─────────────────────────────────────────────────────
    chat_disabled = session.guest_limit_reached()
    placeholder_text = (
        "🚫 Limita de întrebări guest atinsă — creează un cont pentru a continua."
        if chat_disabled
        else "Scrie întrebarea ta despre regulamentele universității..."
    )

    question = st.chat_input(
        placeholder_text,
        key="chat_input_main",
        disabled=chat_disabled,
    )

    if chat_disabled:
        col_a, col_b, col_c = st.columns([1, 1, 1])
        with col_b:
            if st.button("✨ Creează cont gratuit", type="primary",
                         use_container_width=True, key="limit_register"):
                session.navigate_to(session.PAGE_REGISTER)

    if not question:
        return

    # ─── Procesare întrebare ─────────────────────────────────────────────────
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    # Asigurăm chat-ul în DB pentru utilizatorii autentificați
    chat_id = None
    if user:
        chat_id = _ensure_chat_exists(user, question)
        # Salvăm mesajul user în DB
        auth_service.add_message(chat_id, role="user", content=question)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        placeholder.markdown(
            '<span class="thinking">Analizez documentele</span>',
            unsafe_allow_html=True,
        )

        try:
            session_id = st.session_state.active_session_id
            token_stream, metadata = chain.stream_answer(
                question=question,
                session_id=session_id,
                model=st.session_state.selected_model,
            )

            rewritten_q = metadata.get("rewritten_query")
            if rewritten_q and st.session_state.show_rewritten:
                st.caption(f'🔄 Reformulat: *„{rewritten_q}"*')

            full_text = ""
            for token in token_stream:
                full_text += token
                placeholder.markdown(full_text + "▌")
            placeholder.markdown(full_text)

            chain.commit_to_memory(session_id, question, full_text)

            sources = metadata["sources"]
            if sources:
                badges = " ".join(
                    f'<span class="source-badge">📄 {s}</span>' for s in sources
                )
                st.markdown(
                    f'<div style="margin-top:12px;"><strong>📚 Surse:</strong><br/>{badges}</div>',
                    unsafe_allow_html=True,
                )

            if st.session_state.show_chunks:
                _render_chunks(metadata["chunks"])

            # Salvăm în session state
            st.session_state.messages.append({
                "role": "assistant",
                "content": full_text,
                "sources": sources,
                "chunks": metadata["chunks"],
                "rewritten": rewritten_q,
            })

            # Persistăm în DB pentru utilizatorii logați
            if user and chat_id:
                auth_service.add_message(
                    chat_id, role="assistant", content=full_text,
                    sources=sources, rewritten=rewritten_q,
                )
            else:
                # Guest: incrementăm contorul
                session.increment_guest_counter()

        except AppException as exc:
            placeholder.error(f"⚠️ {exc.message}")
            logger.warning("Chat AppException: {}", exc.message)
            st.session_state.messages.append({
                "role": "assistant", "content": f"⚠️ {exc.message}",
                "sources": [], "chunks": [],
            })
        except Exception as exc:
            placeholder.error("❌ Eroare neașteptată. Verifică log-urile.")
            logger.exception("Chat exception: {}", exc)
            st.session_state.messages.append({
                "role": "assistant",
                "content": "❌ Eroare internă.",
                "sources": [], "chunks": [],
            })

    # Force rerun ca să apară butonul de limit reached etc.
    if not user:
        st.rerun()
