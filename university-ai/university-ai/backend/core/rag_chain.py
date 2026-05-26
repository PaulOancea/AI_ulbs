"""
backend/core/rag_chain.py
═════════════════════════
Orchestratorul principal al pipeline-ului RAG.

Flux complet la o întrebare:

    1. Validare întrebare (lungime, conținut)
    2. Recuperare memorie pentru session_id
    3. (Opțional) Rewriting întrebare cu LLM dacă este dependentă de context
    4. Retrieval hibrid + rerank → top K fragmente
    5. Construire prompt complet (system + istoric + context + întrebare)
    6. Generare răspuns (streaming sau sync) prin Ollama
    7. Salvare în memorie (întrebarea originală + răspunsul)
    8. Logare metrice (timp, număr fragmente, sursă)
"""

import time
from typing import AsyncGenerator, Generator, List, Optional, Tuple

from backend.config import settings
from backend.core import llm
from backend.core.memory import ConversationMemory, memory_manager
from backend.core.prompts import build_query_rewrite_prompt, build_rag_prompt
from backend.core.retriever import HybridRetriever
from backend.core.vector_store import VectorStore
from backend.exceptions import (
    EmptyContextError,
    InvalidQueryError,
    OllamaUnavailableError,
)
from backend.logging_config import logger


class RAGChain:
    """
    Componenta centrală — face legătura între retriever, memorie și LLM.

    Folosește singleton-urile VectorStore și MemoryManager pentru a evita
    re-încărcarea modelelor.
    """

    def __init__(self):
        self.vs = VectorStore()
        self.retriever = HybridRetriever(self.vs)
        self.memory = memory_manager

    # ── Validare ─────────────────────────────────────────────────────────────

    @staticmethod
    def _validate_question(q: str) -> str:
        q = (q or "").strip()
        if len(q) < 2:
            raise InvalidQueryError(
                "Întrebarea este prea scurtă. Te rog formulează o întrebare completă."
            )
        if len(q) > 2000:
            raise InvalidQueryError(
                "Întrebarea depășește limita de 2000 caractere."
            )
        return q

    # ── Query rewriting ──────────────────────────────────────────────────────

    def _maybe_rewrite(
        self,
        question: str,
        memory: ConversationMemory,
        model: Optional[str],
    ) -> str:
        """
        Reformulează întrebarea dacă pare să depindă de contextul anterior.
        Returnează întrebarea originală în caz de eroare.
        """
        if not settings.memory_enabled or len(memory) == 0:
            return question

        # Heuristică simplă: dacă întrebarea e foarte scurtă SAU începe cu
        # cuvinte care sugerează dependență contextuală
        short = len(question.split()) < 8
        contextual_starts = (
            "dar", "iar", "și ", "şi ", "el ", "ea ", "acest", "aceast",
            "atunci", "în acest caz", "in acest caz", "la fel",
            "la ce", "cum așa", "de ce așa",
        )
        is_contextual = short or question.lower().startswith(contextual_starts)
        if not is_contextual:
            return question

        try:
            prompt = build_query_rewrite_prompt(memory.get_context_str(), question)
            rewritten = llm.generate(prompt, model=model, temperature=0.0)
            rewritten = rewritten.strip().strip('"').strip("'")
            if rewritten and len(rewritten) > 3:
                logger.info("Query rewrite: '{}' → '{}'", question, rewritten)
                return rewritten
        except Exception as exc:
            logger.warning("Query rewrite a eșuat — folosesc întrebarea originală: {}", exc)
        return question

    # ── Retrieval cu logare ──────────────────────────────────────────────────

    def _retrieve(self, question: str) -> List[dict]:
        chunks = self.retriever.retrieve(question)
        if not chunks:
            logger.info("Niciun chunk relevant pentru: '{}'", question[:80])
        return chunks

    # ── Generare sincronă ────────────────────────────────────────────────────

    def answer(
        self,
        question: str,
        session_id: str = "default",
        model: Optional[str] = None,
    ) -> dict:
        """Răspuns complet (fără streaming). Returnează dict-ul ChatResponse."""
        t0 = time.time()
        question = self._validate_question(question)

        if not llm.is_alive():
            raise OllamaUnavailableError()

        memory = self.memory.get_or_create(session_id)
        effective_q = self._maybe_rewrite(question, memory, model)
        rewritten = effective_q if effective_q != question else None

        chunks = self._retrieve(effective_q)
        if not chunks:
            raise EmptyContextError()

        prompt = build_rag_prompt(
            question=question,  # întrebarea originală a studentului
            chunks=chunks,
            conversation_history=memory.get_context_str() if settings.memory_enabled else "",
        )

        logger.debug("Trimit prompt către Ollama ({} caractere)", len(prompt))
        answer_text = llm.generate(prompt, model=model)

        # Salvăm în memorie
        memory.add_user(question)
        memory.add_assistant(answer_text)

        elapsed_ms = int((time.time() - t0) * 1000)
        sources = sorted({c["source"] for c in chunks})

        logger.info(
            "Răspuns generat: {} caractere, {} surse, {}ms",
            len(answer_text), len(sources), elapsed_ms,
        )

        return {
            "answer": answer_text,
            "sources": sources,
            "chunks": chunks,
            "session_id": session_id,
            "rewritten_query": rewritten,
            "elapsed_ms": elapsed_ms,
        }

    # ── Streaming sincron (pentru Streamlit) ─────────────────────────────────

    def stream_answer(
        self,
        question: str,
        session_id: str = "default",
        model: Optional[str] = None,
    ) -> Tuple[Generator[str, None, None], dict]:
        """
        Returnează (generator_de_tokens, metadata).
        Caller-ul consumă tokenii și are deja metadata cu sursele.

        Salvarea în memorie e responsabilitatea caller-ului DUPĂ ce
        consumă tot stream-ul (avem nevoie de textul complet).
        """
        question = self._validate_question(question)

        if not llm.is_alive():
            raise OllamaUnavailableError()

        memory = self.memory.get_or_create(session_id)
        effective_q = self._maybe_rewrite(question, memory, model)
        rewritten = effective_q if effective_q != question else None

        chunks = self._retrieve(effective_q)
        if not chunks:
            raise EmptyContextError()

        prompt = build_rag_prompt(
            question=question,
            chunks=chunks,
            conversation_history=memory.get_context_str() if settings.memory_enabled else "",
        )

        sources = sorted({c["source"] for c in chunks})
        metadata = {
            "sources": sources,
            "chunks": chunks,
            "session_id": session_id,
            "rewritten_query": rewritten,
        }

        # Returnăm generatorul; caller-ul îl consumă
        return llm.stream(prompt, model=model), metadata

    def commit_to_memory(self, session_id: str, question: str, answer: str) -> None:
        """Apelat după ce streaming-ul s-a încheiat, pentru a salva schimbul."""
        memory = self.memory.get_or_create(session_id)
        memory.add_user(question)
        memory.add_assistant(answer)

    # ── Streaming async (pentru FastAPI WebSocket) ───────────────────────────

    async def astream_answer(
        self,
        question: str,
        session_id: str = "default",
        model: Optional[str] = None,
    ) -> AsyncGenerator[dict, None]:
        """
        Yield-uri de forma:
          {"type": "metadata", "sources": [...], "chunks": [...]}
          {"type": "token", "token": "..."}
          {"type": "done", "elapsed_ms": 1234}
          {"type": "error", "message": "..."}
        """
        t0 = time.time()
        try:
            question = self._validate_question(question)

            if not llm.is_alive():
                raise OllamaUnavailableError()

            memory = self.memory.get_or_create(session_id)
            effective_q = self._maybe_rewrite(question, memory, model)
            rewritten = effective_q if effective_q != question else None

            chunks = self._retrieve(effective_q)
            if not chunks:
                raise EmptyContextError()

            sources = sorted({c["source"] for c in chunks})

            # Trimitem metadata ÎNAINTE de a începe streaming-ul tokenilor
            yield {
                "type": "metadata",
                "sources": sources,
                "chunks": chunks,
                "rewritten_query": rewritten,
                "session_id": session_id,
            }

            prompt = build_rag_prompt(
                question=question,
                chunks=chunks,
                conversation_history=memory.get_context_str() if settings.memory_enabled else "",
            )

            full_answer = ""
            async for token in llm.astream(prompt, model=model):
                full_answer += token
                yield {"type": "token", "token": token}

            # Salvăm în memorie după ce avem răspunsul complet
            memory.add_user(question)
            memory.add_assistant(full_answer)

            yield {"type": "done", "elapsed_ms": int((time.time() - t0) * 1000)}

        except (InvalidQueryError, EmptyContextError, OllamaUnavailableError) as exc:
            yield {"type": "error", "message": exc.message, "code": exc.status_code}
        except Exception as exc:
            logger.exception("Eroare neașteptată în astream_answer")
            yield {"type": "error", "message": "Eroare internă a serverului.", "code": 500}
