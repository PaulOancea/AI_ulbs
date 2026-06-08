"""
frontend/views/chat.py
══════════════════════
Pagina principală de chat — versiunea cu suport pentru:
  • Utilizatori autentificați (istoric persistent în SQLite)
  • Guest mode (limită de N întrebări, fără persistență)
  • Sidebar cu lista chat-urilor
  • Upload de PDF/DOCX/imagini (cu OCR automat)
"""

import html
import uuid
from typing import Optional

import streamlit as st

from backend.auth import service as auth_service
from backend.config import settings
from backend.core import (
    deadlines, disambiguation, exam_service, form_filler, llm, schedule_service,
)
from backend.core.ingestion import IngestionService
from backend.core.memory import memory_manager
from backend.core.ocr import is_tesseract_available
from backend.core.rag_chain import RAGChain
from backend.core.vector_store import VectorStore
from backend.exceptions import AppException
from backend.logging_config import logger
from backend.text_utils import looks_like_no_answer, looks_repetitive, trim_repetition
from frontend.components import session
from frontend.components.navbar import render_navbar


# ═══════════════════════════════════════════════════════════════════════════════
#  Resurse cached (initializate o singură dată)
# ═══════════════════════════════════════════════════════════════════════════════

@st.cache_resource(show_spinner=False)
def _get_resources():
    vs = VectorStore()
    chain = RAGChain()
    ingestion = IngestionService(vs)
    return vs, chain, ingestion


@st.cache_data(show_spinner=False)
def _corpus_text(doc_count: int) -> str:
    """Tot textul documentelor (cache invalidat când se schimbă nr. de fragmente).
    Folosit pentru detectarea tipurilor multiple (dezambiguizare)."""
    vs = VectorStore()
    return "\n".join(d.get("text", "") for d in vs.get_all_documents())


# ═══════════════════════════════════════════════════════════════════════════════
#  Helpers pentru istoricul chat-urilor (persistent)
# ═══════════════════════════════════════════════════════════════════════════════

def _load_chat_into_session(chat_id: int) -> None:
    """Încarcă un chat din DB în session_state."""
    chat = auth_service.get_chat(chat_id)
    if not chat:
        return
    messages = auth_service.get_messages(chat_id)
    # set_active_chat resetează atașamentele/editarea — îl apelăm ÎNAINTE de a
    # popula mesajele, ca să nu pierdem starea proaspăt încărcată.
    session.set_active_chat(chat_id, session_id=chat["session_id"])
    st.session_state.messages = [
        {
            "id": m.get("id"),
            "role": m["role"],
            "content": m["content"],
            "sources": m.get("sources", []) or [],
            "rewritten": m.get("rewritten"),
            "edited": bool(m.get("edited")),
            "chunks": [],  # nu persistăm chunks (prea mari) — doar sursele
        }
        for m in messages
    ]

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
    # Folosim session_id-ul din DB (consistent cu memoria RAG).
    # clear_attached=False: păstrăm documentul atașat pentru conversația curentă.
    session.set_active_chat(chat["id"], session_id=chat["session_id"], clear_attached=False)
    return chat["id"]


# ═══════════════════════════════════════════════════════════════════════════════
#  SIDEBAR — conversații (listă, fixare, arhivare, căutare, partajare)
# ═══════════════════════════════════════════════════════════════════════════════

def _render_conversations(user: dict) -> None:
    """Lista conversațiilor utilizatorului + căutare + arhivate + opțiuni."""
    st.markdown("### Conversațiile tale")

    if st.button("Conversație nouă", type="primary",
                 use_container_width=True, key="sb_new_chat",
                 icon=":material/add:"):
        st.session_state.messages = []
        session.set_active_chat(None)
        st.rerun()

    # Căutare după titlu (insensibilă la diacritice) + comutator arhivate
    st.session_state.chat_search = st.text_input(
        "Caută", value=st.session_state.get("chat_search", ""),
        placeholder="Caută o conversație...",
        label_visibility="collapsed", key="sb_search",
    )
    st.session_state.show_archived = st.toggle(
        "Arată și arhivate",
        value=st.session_state.get("show_archived", False),
        key="sb_show_archived",
    )

    chats = auth_service.list_user_chats(
        user["id"], limit=100,
        include_archived=st.session_state.show_archived,
        search=st.session_state.chat_search,
    )
    active_id = st.session_state.get("active_chat_id")

    if not chats:
        st.caption("Nicio conversație găsită.")
    else:
        for chat in chats:
            _render_chat_row(chat, user, active_id)

    # Opțiuni pentru conversația activă (redenumire, arhivare, partajare)
    if active_id:
        _render_chat_options(active_id, user)


def _render_chat_row(chat: dict, user: dict, active_id) -> None:
    """Un rând din lista de conversații: deschide · fixează · șterge."""
    is_active = chat["id"] == active_id
    pinned = bool(chat.get("pinned"))
    title = chat["title"]
    msg_count = chat.get("message_count", 0)

    col_main, col_pin, col_del = st.columns([5, 1, 1])
    with col_main:
        label = title[:28] + "…" if len(title) > 28 else title
        if st.button(label, key=f"chat_btn_{chat['id']}", use_container_width=True,
                     type="primary" if is_active else "secondary",
                     icon=":material/push_pin:" if pinned else ":material/chat_bubble:",
                     help=f"{msg_count} mesaje · {chat['updated_at']}"):
            _load_chat_into_session(chat["id"])
            st.rerun()
    with col_pin:
        if st.button("", key=f"pin_{chat['id']}",
                     type="primary" if pinned else "secondary",
                     icon=":material/push_pin:",
                     help="Anulează fixarea" if pinned else "Fixează sus"):
            auth_service.set_pinned(chat["id"], user["id"], not pinned)
            st.rerun()
    with col_del:
        if st.button("", key=f"del_{chat['id']}", icon=":material/close:",
                     help="Șterge conversația"):
            auth_service.delete_chat(chat["id"], user["id"])
            if is_active:
                st.session_state.messages = []
                session.set_active_chat(None)
            st.rerun()


def _render_chat_options(active_id: int, user: dict) -> None:
    """Opțiuni pentru conversația activă: redenumire, arhivare, partajare."""
    chat = auth_service.get_chat(active_id)
    if not chat or chat.get("user_id") != user["id"]:
        return

    with st.expander("Opțiuni conversație", icon=":material/settings:"):
        # Redenumire
        new_title = st.text_input("Titlu", value=chat["title"], key=f"rename_{active_id}")
        if st.button("Salvează titlul", key=f"save_title_{active_id}",
                     use_container_width=True, icon=":material/save:"):
            auth_service.rename_chat(active_id, new_title, user["id"])
            st.rerun()

        # Arhivare / dezarhivare
        archived = bool(chat.get("archived"))
        if st.button("Dezarhivează" if archived else "Arhivează",
                     key=f"arch_{active_id}", use_container_width=True,
                     icon=":material/unarchive:" if archived else ":material/archive:"):
            auth_service.set_archived(active_id, user["id"], not archived)
            if not archived:  # tocmai am arhivat → o scoatem din vizor
                st.session_state.messages = []
                session.set_active_chat(None)
            st.rerun()

        # Partajare publică (read-only)
        token = chat.get("share_token")
        if token:
            st.success("Partajare activă (doar citire)")
            st.code(f"?share={token}", language=None)
            st.caption(
                "Adaugă acest parametru la adresa aplicației și trimite link-ul "
                "(ex: http://localhost:8501/?share=…)."
            )
            if st.button("Oprește partajarea", key=f"unshare_{active_id}",
                         use_container_width=True, icon=":material/link_off:"):
                auth_service.disable_sharing(active_id, user["id"])
                st.rerun()
        else:
            if st.button("Partajează conversația", key=f"share_{active_id}",
                         use_container_width=True, icon=":material/share:"):
                auth_service.enable_sharing(active_id, user["id"])
                st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
#  SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════════

def _render_sidebar(vs, ingestion):
    """
    Sidebar orientat spre utilizator: doar profilul + conversațiile proprii.
    Panoul tehnic (status, model, upload, setări) e vizibil EXCLUSIV pentru
    administratori, în spatele unui buton.
    """
    user = session.get_current_user()

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

            _render_conversations(user)
        else:
            # ── Invitat: doar profil + îndemn la cont (fără detalii tehnice) ───
            remaining = session.guest_questions_remaining()
            st.markdown(
                f"""
                <div class="user-chip">
                    <div class="user-avatar" style="background: #6c757d;">I</div>
                    <div>
                        <div class="user-name">Invitat</div>
                        <div class="user-meta">{remaining} întrebări rămase</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.caption(
                "Creează un cont pentru conversații nelimitate și istoric salvat."
            )
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Login", use_container_width=True, key="sb_login",
                             icon=":material/login:"):
                    session.navigate_to(session.PAGE_LOGIN)
            with c2:
                if st.button("Cont", use_container_width=True, key="sb_register",
                             icon=":material/person_add:"):
                    session.navigate_to(session.PAGE_REGISTER)

        # ── Panou administrare (DOAR pentru admini, în spatele unui buton) ────
        if session.is_admin():
            st.divider()
            label = "Ascunde panoul admin" if st.session_state.show_admin_panel \
                else "Panou administrare"
            if st.button(label, use_container_width=True, key="sb_admin_toggle",
                         icon=":material/tune:"):
                st.session_state.show_admin_panel = not st.session_state.show_admin_panel
                st.rerun()

            if st.session_state.show_admin_panel:
                _render_admin_panel(vs, ingestion)


def _render_admin_panel(vs, ingestion):
    """Panoul tehnic — vizibil doar pentru administratori."""
    ollama_ok = llm.is_alive()
    doc_count = vs.get_count()
    file_count = len(vs.get_ingested_files())
    models = llm.list_models() if ollama_ok else []

    st.caption("Vizibil doar pentru administratori")

    # ── Status sistem ─────────────────────────────────────────────────────────
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

    # ── Model selector ──────────────────────────────────────────────────────
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

    # ── Upload documente ──────────────────────────────────────────────────────
    with st.expander("Adaugă documente", expanded=True, icon=":material/upload_file:"):
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

    # ── Setări avansate ─────────────────────────────────────────────────────
    with st.expander("Setări avansate", icon=":material/settings:"):
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
    with st.expander(f"{len(chunks)} fragmente folosite ca sursă",
                     icon=":material/search:"):
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


def _rebuild_memory() -> None:
    """Reconstruiește memoria RAG din istoricul curent (după editare/trunchiere)."""
    session_id = st.session_state.active_session_id
    mem = memory_manager.get_or_create(session_id)
    mem.clear()
    for m in st.session_state.messages:
        if m["role"] == "user":
            mem.add_user(m["content"])
        else:
            mem.add_assistant(m["content"])


def _apply_edit(index: int, new_text: str, user, chat_id) -> None:
    """
    Aplică editarea unui mesaj user: trunchiază conversația din acel punct și
    pregătește re-procesarea întrebării editate (chatbotul răspunde la noua formă).
    """
    new_text = (new_text or "").strip()
    st.session_state.editing_index = None
    if not new_text:
        st.rerun()
        return

    msg = st.session_state.messages[index]
    # În DB: ștergem mesajul editat + tot ce urmează (conversația se ramifică)
    if user and chat_id and msg.get("id"):
        auth_service.delete_messages_from(chat_id, msg["id"])

    # Trunchiem istoricul din sesiune înainte de mesajul editat
    st.session_state.messages = st.session_state.messages[:index]
    _rebuild_memory()

    # Întrebarea editată va fi procesată ca o întrebare nouă
    st.session_state.pending_question = new_text
    st.rerun()


# Lățimile (proporțiile) coloanelor: Data, Ora, Disciplină, Sală, Profesor, Tip.
_EXAM_COL_WEIGHTS = [1.7, 1.5, 3.6, 1.0, 2.8, 1.2]
_EXAM_BTN_WEIGHT = 1.7   # coloana butonului „Adaugă în Calendar"


def _exam_cell(value, cls: str = "exam-td") -> str:
    """O celulă a tabelului de examene (HTML escapat, „—" pentru gol)."""
    txt = "—" if value in (None, "") else html.escape(str(value))
    return f"<span class='{cls}'>{txt}</span>"


def _render_exam_table(table: dict, msg_index: int) -> None:
    """Randează examenele ca tabel cu butonul „Adaugă în Calendar" PE FIECARE rând.

    Înlocuiește vechea listă de butoane înșiruite sub tabel: fiecare examen are
    butonul lui, aliniat în ultima coloană, vertical-centrat lângă rândul lui.
    """
    cols = table.get("cols") or []
    rows = table.get("rows") or []
    has_btn = any(r.get("url") for r in rows)

    if table.get("header"):
        st.markdown(table["header"])

    spec = list(_EXAM_COL_WEIGHTS[:len(cols)])
    labels = list(cols)
    if has_btn:
        spec.append(_EXAM_BTN_WEIGHT)
        labels.append("Calendar")

    with st.container(border=True):
        # Antet
        head_cols = st.columns(spec, vertical_alignment="center")
        for c, name in zip(head_cols, labels):
            c.markdown(_exam_cell(name, "exam-th"), unsafe_allow_html=True)
        st.markdown("<hr class='exam-rule'>", unsafe_allow_html=True)

        # Rânduri (cu separator subtil între ele)
        for ri, r in enumerate(rows):
            row_cols = st.columns(spec, vertical_alignment="center")
            for c, val in zip(row_cols, r.get("cells", [])):
                c.markdown(_exam_cell(val), unsafe_allow_html=True)
            if has_btn:
                if r.get("url"):
                    row_cols[-1].link_button(
                        "Adaugă", r["url"], icon=":material/calendar_add_on:",
                        use_container_width=True,
                    )
                else:
                    row_cols[-1].markdown(
                        _exam_cell("fără oră", "exam-td muted"),
                        unsafe_allow_html=True,
                    )
            if ri < len(rows) - 1:
                st.markdown("<hr class='exam-rule'>", unsafe_allow_html=True)

    if table.get("notes"):
        st.caption(table["notes"])


def _render_message_history(user) -> None:
    """Afișează istoricul mesajelor curente, cu posibilitatea de editare."""
    chat_id = st.session_state.get("active_chat_id")
    editing = st.session_state.get("editing_index")

    for i, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            # ── Mod editare (doar mesaje user) ───────────────────────────────
            if msg["role"] == "user" and editing == i:
                new_text = st.text_area(
                    "Editează mesajul", value=msg["content"],
                    key=f"edit_area_{i}", label_visibility="collapsed",
                )
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Trimite", key=f"edit_save_{i}",
                                 type="primary", use_container_width=True,
                                 icon=":material/send:"):
                        _apply_edit(i, new_text, user, chat_id)
                with c2:
                    if st.button("Anulează", key=f"edit_cancel_{i}",
                                 use_container_width=True, icon=":material/close:"):
                        st.session_state.editing_index = None
                        st.rerun()
                continue

            # ── Afișare normală ──────────────────────────────────────────────
            # Tabelul de examene are randare bogată (buton Calendar pe fiecare
            # rând); restul mesajelor rămân Markdown simplu (tabele incluse).
            if msg.get("exam_table"):
                _render_exam_table(msg["exam_table"], i)
            else:
                st.markdown(msg["content"])

            if msg["role"] == "user":
                if msg.get("edited"):
                    st.caption("editat")
                if st.button("", key=f"edit_btn_{i}", icon=":material/edit:",
                             help="Editează mesajul"):
                    st.session_state.editing_index = i
                    st.rerun()

            if msg["role"] == "assistant":
                if msg.get("rewritten") and st.session_state.show_rewritten:
                    st.caption(f'Reformulat: *„{msg["rewritten"]}"*')

                # Buton de descărcare pentru cererea completată (.docx)
                if msg.get("docx"):
                    st.download_button(
                        "Descarcă cererea (.docx)",
                        data=msg["docx"],
                        file_name=msg.get("docx_name", "cerere.docx"),
                        mime=("application/vnd.openxmlformats-officedocument."
                              "wordprocessingml.document"),
                        key=f"dl_docx_{i}",
                        type="primary",
                        icon=":material/download:",
                    )

                # Buton „Adaugă în Google Calendar" (doar pentru termene viitoare)
                if msg.get("calendar_url"):
                    st.link_button(
                        "Adaugă în Google Calendar",
                        msg["calendar_url"],
                        icon=":material/calendar_add_on:",
                    )

                # Link-uri Google Calendar pentru examene (câte unul per examen).
                # Sărim peste ele când avem tabelul bogat (butoanele sunt deja
                # pe fiecare rând) — altfel le afișăm ca listă (ex. fallback DB).
                if not msg.get("exam_table"):
                    for _link in msg.get("calendar_links") or []:
                        st.link_button(_link["label"], _link["url"],
                                       icon=":material/calendar_add_on:")


                if msg.get("sources"):
                    badges = " ".join(
                        f'<span class="source-badge">{s}</span>'
                        for s in msg["sources"]
                    )
                    st.markdown(
                        f'<div style="margin-top:8px;"><strong>Surse:</strong><br/>{badges}</div>',
                        unsafe_allow_html=True,
                    )

                if st.session_state.show_chunks and msg.get("chunks"):
                    _render_chunks(msg["chunks"])


def _render_attach_widget(ingestion) -> None:
    """Permite utilizatorului să atașeze un document folosit ca sursă în conversație."""
    with st.expander("Atașează un document (răspund pe baza lui)",
                     icon=":material/attach_file:"):
        ocr_ok = is_tesseract_available()
        allowed = ["pdf", "docx", "txt"]
        if ocr_ok:
            allowed += ["png", "jpg", "jpeg", "tiff", "bmp"]

        files = st.file_uploader(
            "Atașează", type=allowed, accept_multiple_files=True,
            label_visibility="collapsed",
            key=f"attach_uploader_{st.session_state.attach_uploader_version}",
        )
        if files:
            existing = set(st.session_state.attached_names)
            for uf in files:
                if uf.name in existing:
                    continue
                with st.spinner(f"Citesc {uf.name}..."):
                    try:
                        chunks = ingestion.extract_chunks_from_bytes(uf.read(), uf.name)
                    except Exception as exc:
                        st.error(f"❌ {uf.name}: {exc}")
                        continue
                if not chunks:
                    st.warning(f"⚠️ Nu am putut extrage text din {uf.name}.")
                    continue
                st.session_state.attached_chunks.extend(chunks)
                st.session_state.attached_names.append(uf.name)
                existing.add(uf.name)

        if st.session_state.attached_names:
            st.caption("Atașat: " + ", ".join(st.session_state.attached_names))
            if st.button("Elimină atașamentele", key="clear_attach",
                         use_container_width=True, icon=":material/close:"):
                session.clear_attachments()
                # Schimbăm cheia uploader-ului ca să se golească widget-ul
                st.session_state.attach_uploader_version += 1
                st.rerun()


def _render_welcome():
    """Mesajul de bun-venit afișat când nu există mesaje încă."""
    user = session.get_current_user()
    vs, _, _ = _get_resources()
    doc_count = vs.get_count()
    file_count = len(vs.get_ingested_files())

    # Dacă nu există documente indexate: instrucțiuni doar pentru admin,
    # mesaj neutru pentru utilizatorul obișnuit.
    if doc_count == 0:
        if session.is_admin():
            st.markdown(
                """
                <div class="intro-box">
                <h4>Bun venit (admin)!</h4>
                <p>Nu există încă documente indexate. Pentru a începe:</p>
                <ol>
                <li>Pornește <code>ollama serve</code> dacă nu rulează</li>
                <li>Deschide <strong>Panou administrare</strong> → „Adaugă documente"</li>
                <li>Pune prima întrebare!</li>
                </ol>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                """
                <div class="intro-box">
                <h4>Bun venit la ClaudiuAI!</h4>
                <p>Poți <strong>atașa un document</strong> (mai jos) și să-mi pui
                întrebări despre conținutul lui.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        return

    if user:
        greeting = f"Bun venit, <strong>{user.get('full_name') or user['username']}</strong>!"
        sub = "Cu ce te pot ajuta astăzi?"
    else:
        remaining = session.guest_questions_remaining()
        greeting = "<strong>Salut!</strong>"
        sub = (
            f"Ești în modul invitat — mai ai <strong>{remaining} întrebări</strong>. "
            "Creează un cont pentru acces nelimitat și istoric."
        )

    st.markdown(
        f"""
        <div class="intro-box">
        <h4>{greeting}</h4>
        <p>{sub}</p>
        <p>Poți și <strong>atașa un document</strong> (mai jos) ca să-mi pui
        întrebări despre conținutul lui.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  COMPLETARE CERERI / FORMULARE
# ═══════════════════════════════════════════════════════════════════════════════

def _persist_user_msg(question: str, user) -> Optional[int]:
    """Adaugă mesajul utilizatorului în sesiune (+ DB dacă e logat). Întoarce chat_id."""
    st.session_state.messages.append({"role": "user", "content": question})
    chat_id = None
    if user:
        chat_id = _ensure_chat_exists(user, question)
        uid = auth_service.add_message(chat_id, role="user", content=question)
        st.session_state.messages[-1]["id"] = uid
    return chat_id


def _append_assistant(content: str, user, chat_id, sources=None,
                      docx: Optional[bytes] = None, docx_name: Optional[str] = None,
                      calendar_links=None, exam_table=None) -> None:
    """Adaugă un mesaj de asistent în sesiune (+ DB). docx-ul/link-urile rămân doar în sesiune."""
    msg = {"role": "assistant", "content": content, "sources": sources or [],
           "chunks": [], "rewritten": None}
    if docx is not None:
        msg["docx"] = docx
        msg["docx_name"] = docx_name
    if calendar_links:
        msg["calendar_links"] = calendar_links
    if exam_table:
        msg["exam_table"] = exam_table
    st.session_state.messages.append(msg)
    if user and chat_id:
        aid = auth_service.add_message(
            chat_id, role="assistant", content=content, sources=sources or [],
        )
        st.session_state.messages[-1]["id"] = aid


def _maybe_handle_form(question: str, user, vs) -> bool:
    """True dacă mesajul ține de completarea unei cereri (și a fost tratat aici)."""
    pending = st.session_state.get("pending_form")
    if not pending and not form_filler.is_form_request(question):
        return False
    _run_form_step(question, user, vs, pending)
    return True


def _run_form_step(question: str, user, vs, pending) -> None:
    """Un pas din completarea unei cereri: găsește șablonul, cere date sau o completează."""
    chat_id = _persist_user_msg(question, user)

    # Renunțare explicită
    if pending and form_filler.is_cancel(question):
        st.session_state.pending_form = None
        _append_assistant(
            "Am renunțat la completarea cererii. Cu ce altceva te pot ajuta?",
            user, chat_id,
        )
        st.rerun()
        return

    # Determinăm șablonul (din pending sau căutăm acum)
    if pending:
        source = pending["source"]
        template_text = pending.get("text") or form_filler.get_full_document_text(vs, source)
    else:
        # Potrivire ROBUSTĂ: folosim TOATE mesajele utilizatorului (inclusiv cererea
        # inițială), ca să regăsim același șablon chiar dacă starea s-a pierdut.
        convo = " ".join(
            m["content"] for m in st.session_state.messages if m["role"] == "user"
        )
        source, available = form_filler.find_template(vs, convo)
        if source:
            template_text = form_filler.get_full_document_text(vs, source)
        elif st.session_state.attached_chunks:
            # Folosim documentul atașat de utilizator drept șablon
            names = st.session_state.attached_names
            source = names[0] if names else "document atașat"
            template_text = "\n".join(
                c.get("text", "") for c in st.session_state.attached_chunks
            )[:8000]
        else:
            if available:
                lst = "\n".join(f"- {a}" for a in available)
                content = (
                    "Nu am găsit printre documente o cerere care să corespundă "
                    f"solicitării tale. Cereri/formulare disponibile:\n{lst}\n\n"
                    "Spune-mi care dintre ele dorești să o completez."
                )
            else:
                content = (
                    "Nu am găsit nicio cerere sau formular model printre documentele "
                    "încărcate. Poți atașa șablonul cererii (📎 mai jos) sau roagă un "
                    "administrator să îl încarce."
                )
            st.session_state.pending_form = None
            _append_assistant(content, user, chat_id)
            st.rerun()
            return

    if not template_text:
        st.session_state.pending_form = None
        _append_assistant(
            f"Nu am putut citi conținutul șablonului: {source}.", user, chat_id,
        )
        st.rerun()
        return

    # Sloturile (locurile goale), POZIȚIONALE — păstrează câmpurile duplicate
    # (ex. 2× specializare, 3× anul de studii) ca să le putem cere/completa pe TOATE.
    slots = form_filler.extract_slots(template_text)
    if not slots:
        # fallback puțin probabil — niciun loc gol detectat
        st.session_state.pending_form = None
        _append_assistant(
            f"Șablonul {source} nu pare să conțină câmpuri de completat.",
            user, chat_id, sources=[source],
        )
        st.rerun()
        return

    slot_values = dict((pending or {}).get("slot_values") or {})
    already_asked = bool(pending and pending.get("asked"))

    # 1) Dacă am cerut deja lista, interpretăm răspunsul NUMEROTAT / în ordine.
    if already_asked:
        slot_values = form_filler.parse_slot_reply(question, slots, slot_values)

    # 2) Dacă tot mai lipsesc câmpuri, încercăm să le DEDUCEM din text liber
    #    (nume, program, telefon… via cod + LLM). Util la primul pas ȘI când
    #    utilizatorul răspunde în limbaj natural, nu cu numere. Sărim peste LLM
    #    dacă răspunsul numerotat a completat deja tot.
    if form_filler.missing_slots(slots, slot_values):
        named = _form_named_values(slots, user)
        if named is None:
            return   # eroare LLM deja raportată
        slot_values = form_filler.merge_named_into_slots(slots, slot_values, named)

    missing = form_filler.missing_slots(slots, slot_values)

    if missing:
        st.session_state.pending_form = {
            "source": source, "text": template_text,
            "slot_values": slot_values, "asked": True,
        }
        _append_assistant(_render_slot_request(slots, slot_values, missing),
                          user, chat_id, sources=[source])
    else:
        docx_bytes, docx_name, layout_kept = form_filler.generate_filled_document_slots(
            source, template_text, slot_values,
        )
        recap = "\n".join(
            f"- {s.index}. {s.friendly}: {slot_values.get(s.index)}" for s in slots
        )
        nota = (
            "" if layout_kept else
            "\n\n_Notă: șablonul original e PDF, așa că documentul păstrează textul "
            "completat, dar nu și formatarea exactă. Pentru layout identic, încarcă "
            "cererea în format .docx._"
        )
        content = (
            "✅ Am completat cererea cu toate cele "
            f"**{len(slots)} câmpuri**. O poți descărca mai jos.\n\n"
            "**Date folosite:**\n" + recap + nota
        )
        st.session_state.pending_form = None
        _append_assistant(content, user, chat_id, sources=[source],
                          docx=docx_bytes, docx_name=docx_name)

    st.rerun()


def _form_named_values(slots, user):
    """Pre-completare comodă la primul pas: extrage valori pe NUME (cod + LLM) din
    mesajele utilizatorului. Returnează {nume_normalizat: valoare} sau None la
    eroare LLM (caz în care mesajul a fost deja afișat)."""
    field_names = list({s.friendly for s in slots})
    user_msgs = [m["content"] for m in st.session_state.messages if m["role"] == "user"]
    user_data = "\n".join(user_msgs[-15:])

    values = form_filler.extract_values_code(field_names, user_data)
    still = form_filler.missing_fields(field_names, values)
    if still:
        try:
            with st.spinner("Verific datele..."):
                resp = llm.generate(
                    form_filler.build_extract_prompt(still, user_data),
                    model=st.session_state.selected_model,
                )
            for k, v in form_filler.parse_extraction(resp, still).items():
                if v and not values.get(k):
                    values[k] = v
        except AppException as exc:
            chat_id = st.session_state.get("active_chat_id")
            _append_assistant(f"⚠️ {exc.message}", user, chat_id)
            st.rerun()
            return None
        except Exception:
            logger.exception("Eroare la extragerea datelor cererii")
            # continuăm cu ce a prins codul
    return values


def _render_slot_request(slots, slot_values, missing) -> str:
    """Lista NUMEROTATĂ a câmpurilor (bifate ✅ cele completate, ⬜ cele lipsă, cu
    context pentru a deosebi duplicatele) + instrucțiuni de răspuns."""
    lines = []
    for s in slots:
        val = (slot_values.get(s.index) or "").strip()
        if val:
            lines.append(f"**{s.index}.** ✅ {s.friendly}: {val}")
        else:
            lines.append(f"**{s.index}.** ⬜ {s.friendly} — _{s.context}_")
    n = len(missing)
    pre = "Am completat ce mi-ai spus deja. " if any(
        (v or "").strip() for v in slot_values.values()) else ""
    return (
        f"📝 Cererea are **{len(slots)} câmpuri**. {pre}"
        f"Mai am nevoie de **{n}** {'câmp' if n == 1 else 'câmpuri'} "
        "(cele marcate cu ⬜):\n\n"
        + "\n".join(lines)
        + "\n\nTrimite-mi valorile lipsă **cu numărul lor** "
          "(ex: `3=2, 9=Informatică`) sau pur și simplu pe rând, "
          "câte una pe linie, în ordinea de mai sus."
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  EXAMENE — răspuns din ExamService + link Google Calendar per examen
# ═══════════════════════════════════════════════════════════════════════════════

def _maybe_handle_exam(question: str, user) -> bool:
    """True dacă mesajul ține de examene (și a fost tratat aici).

    Răspunde din ExamService (nu din RAG). Dacă examenele nu sunt sincronizate,
    lăsăm fluxul normal (feature dormant → nu schimbă nimic).
    """
    if not exam_service.is_exam_question(question):
        return False
    svc = exam_service.ExamService()
    if not svc.is_loaded():
        return False  # examene nesincronizate → fluxul RAG normal

    chat_id = _persist_user_msg(question, user)
    result = svc.answer(question)
    _append_assistant(result["text"], user, chat_id,
                      calendar_links=result.get("calendar_links"),
                      exam_table=result.get("table"))
    st.rerun()
    return True


# ═══════════════════════════════════════════════════════════════════════════════
#  ORAR — întreabă o dată grupa/semigrupa, apoi o reține în conversație
# ═══════════════════════════════════════════════════════════════════════════════

def _maybe_handle_schedule(question: str, user) -> bool:
    """
    True dacă mesajul ține de orar (și a fost tratat aici).

    Comportament: dacă utilizatorul NU specifică grupa și nu avem una reținută,
    îl întrebăm din ce grupă/semigrupă este și reținem întrebarea inițială. La
    următorul mesaj (răspunsul cu grupa) reluăm întrebarea inițială și memorăm
    grupa pentru tot restul conversației. Nu atinge RAG-ul: dacă orarul nu e
    sincronizat, lăsăm fluxul normal.
    """
    pending = st.session_state.get("pending_schedule")
    if not pending and not schedule_service.is_schedule_question(question):
        return False

    svc = schedule_service.ScheduleService()
    if not svc.is_loaded():
        return False  # orar nesincronizat → fluxul RAG normal (ca înainte)

    remembered = st.session_state.get("schedule_formation")

    # ── Așteptam răspunsul cu grupa la o întrebare anterioară ─────────────────
    if pending:
        reply_res = svc.resolve(question, ask_if_unspecified=True)

        # Utilizatorul a dat o grupă validă → reluăm întrebarea inițială
        if reply_res.status == "ok":
            chat_id = _persist_user_msg(question, user)
            st.session_state.schedule_formation = reply_res.formation_id
            st.session_state.pending_schedule = None
            original = pending.get("question", question)
            _append_assistant(svc.answer_with(reply_res.formation_id, original),
                              user, chat_id, sources=[])
            st.rerun()
            return True

        # Nu e o grupă, dar pare o încercare (ex. „31") sau altă întrebare de orar
        if schedule_service.mentions_group(question) or schedule_service.is_schedule_question(question):
            chat_id = _persist_user_msg(question, user)
            if reply_res.status == "unknown":   # grupă recunoscută dar nesincronizată
                st.session_state.pending_schedule = None
            _append_assistant(reply_res.message, user, chat_id)
            st.rerun()
            return True

        # Utilizatorul a schimbat subiectul → renunțăm la așteptare, lăsăm RAG-ul
        st.session_state.pending_schedule = None
        return False

    # ── Întrebare normală despre orar ─────────────────────────────────────────
    res = svc.resolve(question, remembered=remembered, ask_if_unspecified=True)
    chat_id = _persist_user_msg(question, user)
    if res.status == "clarify" and res.needs_group:
        st.session_state.pending_schedule = {"question": question}   # reținem întrebarea
        _append_assistant(res.message, user, chat_id)
    elif res.status in ("clarify", "unknown"):
        _append_assistant(res.message, user, chat_id)
    else:
        st.session_state.schedule_formation = res.formation_id
        _append_assistant(svc.answer_for(res, question), user, chat_id, sources=[])
    st.rerun()
    return True


# ═══════════════════════════════════════════════════════════════════════════════
#  PROCESARE ÎNTREBARE
# ═══════════════════════════════════════════════════════════════════════════════

def _process_question(chain, question: str, user) -> None:
    """Adaugă întrebarea, generează răspunsul (stream) și persistă, cu suport
    pentru documente atașate ca sursă."""
    # Citim atașamentele ÎNAINTE de a crea/schimba conversația (ca să nu le pierdem)
    attached = st.session_state.attached_chunks or None

    # Mesajul utilizatorului
    st.session_state.messages.append({"role": "user", "content": question})

    chat_id = None
    if user:
        chat_id = _ensure_chat_exists(user, question)
        uid_msg = auth_service.add_message(chat_id, role="user", content=question)
        st.session_state.messages[-1]["id"] = uid_msg

    # ── Dezambiguizare: întrebare generică pe un concept cu mai multe tipuri? ──
    # (nu pentru documente atașate — acolo contextul e strict documentul dat)
    if not attached:
        clar = disambiguation.needs_clarification(
            question, _corpus_text(chain.vs.get_count())
        )
        if clar:
            concept, _options = clar
            content = (
                f"Există mai multe tipuri de **{concept}**. Despre ce tip de "
                f"{concept} este vorba? Te rog precizează, ca să-ți pot răspunde exact."
            )
            _append_assistant(content, user, chat_id)
            st.rerun()
            return

    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        # Butonul „Oprește" stă SUS, deasupra textului în curs, pe toată lățimea →
        # imposibil de ratat cât timp se generează răspunsul. Un click trimite un
        # rerun, iar Streamlit întrerupe bucla la următorul `placeholder.markdown`
        # (yield point), ridicând RerunException. Textul parțial e reținut în
        # `gen_partial` și salvat la rerun de `_flush_stopped_generation`.
        stop_slot = st.empty()
        placeholder = st.empty()
        thinking = "Analizez documentul atașat" if attached else "Analizez documentele"
        stop_slot.button(
            "Oprește generarea", key="stop_generation",
            icon=":material/stop_circle:", use_container_width=True,
            help="Oprește răspunsul în curs",
        )
        placeholder.markdown(
            f'<span class="thinking">{thinking}</span>', unsafe_allow_html=True,
        )

        try:
            session_id = st.session_state.active_session_id
            token_stream, metadata = chain.stream_answer(
                question=question,
                session_id=session_id,
                model=st.session_state.selected_model,
                attached_chunks=attached,
            )

            rewritten_q = metadata.get("rewritten_query")
            if rewritten_q and st.session_state.show_rewritten:
                st.caption(f'Reformulat: *„{rewritten_q}"*')

            # Reținem progresul ca să-l putem salva dacă utilizatorul oprește.
            st.session_state.gen_partial = {"chat_id": chat_id, "text": ""}
            full_text = ""
            for token in token_stream:
                full_text += token
                st.session_state.gen_partial["text"] = full_text
                # Protecție anti-buclă: oprește dacă modelul repetă la nesfârșit
                if looks_repetitive(full_text):
                    try:
                        token_stream.close()
                    except Exception:
                        pass
                    full_text = trim_repetition(full_text)
                    break
                placeholder.markdown(full_text + "▌")
            placeholder.markdown(full_text)
            stop_slot.empty()                      # generare gata → ascundem butonul
            st.session_state.gen_partial = None     # nu mai e nimic de salvat

            chain.commit_to_memory(session_id, question, full_text)

            # Dacă răspunsul spune că NU a găsit informația, nu afișăm surse
            no_answer = looks_like_no_answer(full_text)
            sources = [] if no_answer else metadata["sources"]
            if sources:
                badges = " ".join(
                    f'<span class="source-badge">{s}</span>' for s in sources
                )
                st.markdown(
                    f'<div style="margin-top:12px;"><strong>Surse:</strong><br/>{badges}</div>',
                    unsafe_allow_html=True,
                )

            if st.session_state.show_chunks and not no_answer:
                _render_chunks(metadata["chunks"])

            # ── Termene limită (DOAR la întrebări despre termene, cu răspuns valid) ──
            calendar_url = None
            if not no_answer and deadlines.is_deadline_question(question):
                ctx = full_text + "\n" + "\n".join(
                    c.get("text", "") for c in metadata["chunks"]
                )
                dl = deadlines.find_deadline(ctx)
                if dl and dl.passed:
                    note = (
                        f"\n\n⚠️ **Atenție:** termenul (**{dl.display}**) a trecut deja."
                    )
                    full_text += note
                    st.markdown(note)
                elif dl:
                    note = f"\n\n📅 **Termen:** {dl.display} — încă nu a trecut."
                    full_text += note
                    st.markdown(note)
                    title = deadlines.suggest_title(
                        question, sources[0] if sources else None
                    )
                    details = (
                        f"Termen detectat de ClaudiuAI. "
                        f"Sursa: {sources[0] if sources else 'document'}."
                    )
                    calendar_url = deadlines.build_gcal_url(title, dl.date_obj, details)
                    st.link_button("Adaugă în Google Calendar", calendar_url,
                                   icon=":material/calendar_add_on:")

            msg = {
                "role": "assistant",
                "content": full_text,
                "sources": sources,
                "chunks": [] if no_answer else metadata["chunks"],
                "rewritten": rewritten_q,
            }
            if calendar_url:
                msg["calendar_url"] = calendar_url
            st.session_state.messages.append(msg)

            if user and chat_id:
                aid = auth_service.add_message(
                    chat_id, role="assistant", content=full_text,
                    sources=sources, rewritten=rewritten_q,
                )
                st.session_state.messages[-1]["id"] = aid
            else:
                session.increment_guest_counter()

        except AppException as exc:
            stop_slot.empty()
            st.session_state.gen_partial = None
            placeholder.error(f"⚠️ {exc.message}")
            logger.warning("Chat AppException: {}", exc.message)
            st.session_state.messages.append({
                "role": "assistant", "content": f"⚠️ {exc.message}",
                "sources": [], "chunks": [],
            })
        except Exception as exc:
            stop_slot.empty()
            st.session_state.gen_partial = None
            placeholder.error("❌ Eroare neașteptată. Verifică log-urile.")
            logger.exception("Chat exception: {}", exc)
            st.session_state.messages.append({
                "role": "assistant",
                "content": "❌ Eroare internă.",
                "sources": [], "chunks": [],
            })


# ═══════════════════════════════════════════════════════════════════════════════
#  PUNCT DE INTRARE
# ═══════════════════════════════════════════════════════════════════════════════

def _flush_stopped_generation(user) -> None:
    """Salvează răspunsul parțial dacă generarea a fost oprită din buton.

    Când utilizatorul apasă „Oprește generarea", click-ul declanșează un rerun
    care întrerupe bucla de streaming (RerunException). Aici, la începutul rulării
    următoare, recuperăm textul parțial reținut în `gen_partial` și îl persistăm
    ca răspuns (marcat „generare oprită"). Pe rulările normale e un no-op.
    """
    g = st.session_state.pop("gen_partial", None)
    if not g:
        return
    text = (g.get("text") or "").strip()
    if not text:
        return   # oprit înainte de orice conținut → nu adăugăm o bulă goală
    text += "\n\n_⏹ Generare oprită._"
    msg = {"role": "assistant", "content": text, "sources": [],
           "chunks": [], "rewritten": None, "stopped": True}
    st.session_state.messages.append(msg)
    chat_id = g.get("chat_id")
    if user and chat_id:
        aid = auth_service.add_message(
            chat_id, role="assistant", content=text, sources=[],
        )
        st.session_state.messages[-1]["id"] = aid


def render() -> None:
    """Punctul de intrare apelat de router."""
    vs, chain, ingestion = _get_resources()
    _render_sidebar(vs, ingestion)

    user = session.get_current_user()

    # Dacă răspunsul precedent a fost oprit din buton, salvăm ce s-a generat.
    _flush_stopped_generation(user)

    # ── Navbar + header ─────────────────────────────────────────────────────
    render_navbar(active=session.PAGE_CHAT)
    st.caption("Pune-mi o întrebare — îți răspund clar, în limba română.")

    # ── Banner „cerere în curs de completare" ────────────────────────────────
    pending_form = st.session_state.get("pending_form")
    if pending_form:
        bc1, bc2 = st.columns([4, 1])
        with bc1:
            st.info(
                f"Completez cererea: **{pending_form['source']}**. "
                "Oferă-mi datele cerute, mesaj cu mesaj.",
                icon=":material/edit_document:",
            )
        with bc2:
            if st.button("Renunță", key="cancel_form", use_container_width=True,
                         icon=":material/close:"):
                st.session_state.pending_form = None
                st.rerun()

    # ── Avertizare guest limită ───────────────────────────────────────────────
    if not user:
        remaining = session.guest_questions_remaining()
        if remaining <= 1:
            st.markdown(
                f"""
                <div class="guest-warning">
                <strong>Mod invitat:</strong> {remaining} întrebare rămasă.
                <a href="#" onclick="return false;">Creează un cont</a>
                pentru acces nelimitat și istoric persistent.
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("Creează cont acum", type="primary", key="warn_register",
                         icon=":material/person_add:"):
                session.navigate_to(session.PAGE_REGISTER)

    # ── Welcome sau istoric ──────────────────────────────────────────────────
    if not st.session_state.messages:
        _render_welcome()
    else:
        _render_message_history(user)

    # ── Document atașat (context pentru conversația curentă) ─────────────────
    _render_attach_widget(ingestion)

    # ── Input utilizator ─────────────────────────────────────────────────────
    chat_disabled = session.guest_limit_reached()
    placeholder_text = (
        "Limita de întrebări guest atinsă — creează un cont pentru a continua."
        if chat_disabled
        else "Scrie întrebarea ta..."
    )

    typed = st.chat_input(
        placeholder_text,
        key="chat_input_main",
        disabled=chat_disabled,
    )

    if chat_disabled:
        col_a, col_b, col_c = st.columns([1, 1, 1])
        with col_b:
            if st.button("Creează cont gratuit", type="primary",
                         use_container_width=True, key="limit_register",
                         icon=":material/person_add:"):
                session.navigate_to(session.PAGE_REGISTER)

    # Întrebarea poate veni din input SAU din editarea unui mesaj (pending)
    pending = st.session_state.pop("pending_question", None)
    question = None if chat_disabled else (pending or typed)
    if not question:
        return

    # ─── Completare cerere/formular (prioritar față de RAG) ──────────────────
    if _maybe_handle_form(question, user, vs):
        return

    # ─── Examene (modul separat; răspuns din ExamService + link Calendar) ────
    if _maybe_handle_exam(question, user):
        return

    # ─── Orar (modul separat; întreabă grupa o dată, apoi o reține) ──────────
    if _maybe_handle_schedule(question, user):
        return

    # ─── Procesare întrebare normală (RAG) ───────────────────────────────────
    _process_question(chain, question, user)

    # Force rerun ca să apară butonul de limit reached etc.
    if not user:
        st.rerun()
