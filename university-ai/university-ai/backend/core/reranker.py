"""
backend/core/reranker.py
════════════════════════
Re-ranking cu un model cross-encoder (BAAI/bge-reranker-v2-m3).

Diferența esențială față de embedding-uri:
  • bi-encoder (embedding): codifică separat întrebarea și documentul →
    rapid, dar pierde interacțiunile fine între termeni;
  • cross-encoder (reranker): codifică perechea (q, d) împreună →
    mult mai precis, dar mai lent. Ideal: aplicăm doar pe top-K candidați.

Workflow:
  1. Retrieverul hibrid întoarce 20 candidați.
  2. Reranker-ul îi scorează pereche cu întrebarea.
  3. Păstrăm doar primii N (final_top_k) pentru promptul LLM.
"""

import time
from threading import Lock
from typing import List, Optional

from backend.config import settings
from backend.logging_config import logger


class Reranker:
    """Cross-encoder lazy-loaded (se inițializează la prima utilizare)."""

    _instance: Optional["Reranker"] = None
    _lock = Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._model = None
                cls._instance._enabled = settings.reranker_enabled
            return cls._instance

    def _load(self):
        """Lazy load — modelul se descarcă la prima utilizare (~570 MB)."""
        if self._model is not None or not self._enabled:
            return

        try:
            from sentence_transformers import CrossEncoder
        except ImportError:
            logger.error("sentence-transformers nu e instalat — reranker dezactivat")
            self._enabled = False
            return

        logger.info("Încarc reranker: {}", settings.reranker_model)
        t0 = time.time()
        try:
            self._model = CrossEncoder(
                settings.reranker_model,
                device=settings.embed_device,
                max_length=512,
            )
            logger.info("Reranker gata ({:.1f}s)", time.time() - t0)
        except Exception as exc:
            logger.exception("Eroare la încărcarea reranker — îl dezactivez")
            self._enabled = False

    # ── API ──────────────────────────────────────────────────────────────────

    def is_enabled(self) -> bool:
        return self._enabled

    def rerank(
        self,
        question: str,
        candidates: List[dict],
        top_n: Optional[int] = None,
    ) -> List[dict]:
        """
        Reordonează lista de candidați după relevanță cross-encoder.

        Args:
            question:   întrebarea utilizatorului
            candidates: listă de dict cu cheile "text", "source", ...
            top_n:      câte rezultate finale (default: settings.reranker_top_n)

        Returns:
            Lista reordonată, cu cheia adițională "rerank_score".
        """
        if not candidates:
            return []
        if not self._enabled:
            return candidates[: top_n or settings.reranker_top_n]

        self._load()
        if self._model is None:
            return candidates[: top_n or settings.reranker_top_n]

        n = top_n or settings.reranker_top_n
        pairs = [(question, c["text"]) for c in candidates]

        t0 = time.time()
        try:
            scores = self._model.predict(pairs, show_progress_bar=False)
        except Exception as exc:
            logger.exception("Eroare rerank — folosesc ordinea originală")
            return candidates[:n]

        # Atașăm scorurile și sortăm descrescător
        for c, s in zip(candidates, scores):
            c["rerank_score"] = float(s)

        candidates.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)
        logger.debug(
            "Rerank {} candidați → top {} ({:.0f}ms)",
            len(candidates), n, (time.time() - t0) * 1000,
        )
        return candidates[:n]
