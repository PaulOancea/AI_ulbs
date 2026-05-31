"""
backend/core/retriever.py
═════════════════════════
Retriever hibrid: combină căutarea **densă** (embeddings) cu **BM25** (lexicală)
prin algoritmul Reciprocal Rank Fusion (RRF). Apoi aplică **re-ranking** cu un
cross-encoder pentru acuratețe maximă.

De ce hibrid?
  • Dense (semantic) e excelent la sinonime, parafrazări, întrebări vagi.
  • BM25 (lexical) excelează la potriviri exacte: "Art. 17", "Legea 1/2011",
    nume proprii, cifre, sintagme rare.
  • RRF unifică cele două liste rankuite fără a necesita scoruri comparabile.

RRF formula (Cormack et al., 2009):
    RRF_score(d) = Σ  1 / (k + rank_i(d))      [k tipic = 60]
"""

import time
from threading import Lock
from typing import Dict, List, Optional, Tuple

from rank_bm25 import BM25Okapi

from backend.config import settings
from backend.core.reranker import Reranker
from backend.core.vector_store import VectorStore
from backend.logging_config import logger


# ── Tokenizator simplu pentru BM25 (compatibil RO) ────────────────────────────

import re

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)

# Stopwords românești (lista scurtă, focused pe regulamente)
RO_STOPWORDS = {
    "a", "ai", "al", "ale", "alta", "alte", "altă", "am", "ar", "are", "as",
    "asta", "astea", "așa", "au", "avea", "avem", "avut", "ca", "care", "ce",
    "cea", "cei", "cel", "cele", "cu", "cum", "către", "da", "de", "deci",
    "decât", "din", "doar", "dupa", "după", "ea", "ei", "el", "ele", "eu",
    "este", "și", "şi", "sa", "să", "săi", "sale", "sau", "se", "si", "sub",
    "sunt", "te", "tu", "tot", "toate", "un", "una", "unei", "unele", "unor",
    "vor", "vom", "voi", "lui", "la", "le", "lor", "noi", "nu", "ne", "ni",
    "nostru", "noastră", "pe", "pentru", "prin", "până", "poate", "fi", "fie",
    "fără", "in", "în", "iar", "ii", "îi", "îl", "îmi", "îți", "îi",
}


def tokenize(text: str) -> List[str]:
    """Tokenizator simplu lowercase, fără stopwords."""
    tokens = [t.lower() for t in _TOKEN_RE.findall(text)]
    return [t for t in tokens if t not in RO_STOPWORDS and len(t) > 1]


# ── BM25 wrapper (in-memory) ──────────────────────────────────────────────────

class BM25Index:
    """
    Index BM25 in-memory peste toate fragmentele din vector store.
    Construit lazy și re-construit când se adaugă documente noi.
    """

    def __init__(self):
        self._bm25: Optional[BM25Okapi] = None
        self._docs: List[dict] = []
        self._lock = Lock()

    def build(self, documents: List[dict]) -> None:
        """Reconstruiește indexul de la zero."""
        with self._lock:
            self._docs = documents
            if not documents:
                self._bm25 = None
                return
            corpus = [tokenize(d["text"]) for d in documents]
            t0 = time.time()
            self._bm25 = BM25Okapi(corpus)
            logger.info(
                "BM25 index construit: {} documente ({:.1f}s)",
                len(documents), time.time() - t0,
            )

    def query(self, question: str, top_k: int) -> List[Tuple[dict, float]]:
        """Returnează listă de (document, score) sortată descrescător."""
        if self._bm25 is None or not self._docs:
            return []
        tokens = tokenize(question)
        if not tokens:
            return []

        scores = self._bm25.get_scores(tokens)
        # Argsort descrescător
        ranked = sorted(
            zip(self._docs, scores),
            key=lambda x: x[1],
            reverse=True,
        )
        return ranked[:top_k]

    def is_ready(self) -> bool:
        return self._bm25 is not None


# ── Reciprocal Rank Fusion ────────────────────────────────────────────────────

def reciprocal_rank_fusion(
    dense_results: List[dict],
    bm25_results: List[Tuple[dict, float]],
    alpha: float = settings.hybrid_alpha,
    k: int = 60,
) -> List[dict]:
    """
    Combină două liste rankuite folosind RRF ponderat.

    Args:
        dense_results: rezultate din vector store (ordine = rank)
        bm25_results:  rezultate BM25 (document, score)
        alpha:         pondere pentru dense; (1 - alpha) pentru BM25
        k:             constanta RRF (tipic 60)

    Returns:
        Lista finală unificată, deduplicată, sortată după scor RRF.
    """
    fused: Dict[str, dict] = {}

    def _key(doc: dict) -> str:
        """Cheie unică pentru deduplicare (text trunchiat = suficient)."""
        return f"{doc.get('source','?')}::{doc.get('page','?')}::{hash(doc['text'][:100])}"

    # Componenta dense
    for rank, doc in enumerate(dense_results):
        k_doc = _key(doc)
        rrf = alpha * (1.0 / (k + rank + 1))
        if k_doc not in fused:
            fused[k_doc] = {**doc, "rrf_score": 0.0}
        fused[k_doc]["rrf_score"] += rrf

    # Componenta BM25
    for rank, (doc, _bm25_score) in enumerate(bm25_results):
        k_doc = _key(doc)
        rrf = (1.0 - alpha) * (1.0 / (k + rank + 1))
        if k_doc not in fused:
            # BM25 docs nu au "score" dense, marcăm cu 0
            fused[k_doc] = {**doc, "score": 0.0, "rrf_score": 0.0}
        fused[k_doc]["rrf_score"] += rrf

    # Sortare descrescătoare după scorul RRF
    merged = sorted(fused.values(), key=lambda x: x["rrf_score"], reverse=True)
    return merged


# ── Retrieverul principal ─────────────────────────────────────────────────────

class HybridRetriever:
    """
    Pipeline complet:
        întrebare
            ├─→ dense retrieval (top_k)  ─┐
            ├─→ BM25 retrieval (top_k)   ─┼─→ RRF fusion ─→ rerank ─→ top N
            └─                            ─┘
    """

    def __init__(self, vector_store: VectorStore):
        self.vs = vector_store
        self.bm25 = BM25Index()
        self.reranker = Reranker()
        self._last_built_count = 0  # invalidare cache BM25

    # ── Helper: asigurăm că BM25 e sincronizat cu vector store ───────────────

    def _ensure_bm25(self) -> None:
        """(Re)construiește BM25 dacă numărul de documente s-a schimbat."""
        current_count = self.vs.get_count()
        if current_count == self._last_built_count and self.bm25.is_ready():
            return
        if current_count == 0:
            return
        docs = self.vs.get_all_documents()
        self.bm25.build(docs)
        self._last_built_count = current_count

    # ── Filtru de relevanță post-rerank ──────────────────────────────────────

    @staticmethod
    def _keep_relevant(ranked: List[dict]) -> List[dict]:
        """
        Păstrează doar fragmentele clar relevante după scorul cross-encoder.

        Logica (robustă indiferent de scala scorurilor modelului):
          • păstrăm întotdeauna fragmentul de top (cel mai bun);
          • păstrăm fragmentele următoare DOAR cât timp scorul lor rămâne
            ≥ rerank_keep_ratio × scorul de top ȘI este pozitiv;
          • lista e deja sortată descrescător, deci ne oprim la prima cădere
            sub prag (restul sunt și mai mici).

        Efect: pentru o întrebare cu o singură sursă relevantă, returnăm o
        singură sursă — nu mai apar surse parazite cu scor aproape zero.
        """
        if not ranked:
            return ranked
        # Fără scor de rerank (reranker dezactivat/eșuat) → nu filtrăm aici
        if "rerank_score" not in ranked[0]:
            return ranked

        top_score = ranked[0].get("rerank_score", 0.0)
        kept = [ranked[0]]

        # Dacă nici cel mai bun fragment nu pare relevant (scor ≤ 0), întoarcem
        # doar vârful — LLM-ul va spune onest că nu a găsit informația.
        if top_score <= 0:
            HybridRetriever._log_dropped(ranked, kept)
            return kept

        threshold = top_score * settings.rerank_keep_ratio
        for r in ranked[1:]:
            score = r.get("rerank_score", 0.0)
            if score >= threshold and score > 0:
                kept.append(r)
            else:
                break  # scoruri descrescătoare → restul sunt sub prag

        HybridRetriever._log_dropped(ranked, kept)
        return kept

    @staticmethod
    def _log_dropped(ranked: List[dict], kept: List[dict]) -> None:
        dropped = len(ranked) - len(kept)
        if dropped > 0:
            logger.debug(
                "Filtru relevanță: păstrate {} / {} fragmente (eliminate {} irelevante)",
                len(kept), len(ranked), dropped,
            )

    # ── Public API ───────────────────────────────────────────────────────────

    def retrieve(
        self,
        question: str,
        top_k: Optional[int] = None,
        final_top_k: Optional[int] = None,
    ) -> List[dict]:
        """
        Returnează fragmentele cele mai relevante pentru întrebare.

        Pipeline complet: dense + BM25 → RRF → rerank.
        """
        if self.vs.get_count() == 0:
            logger.debug("Retrieval pe colecție goală — nimic de făcut")
            return []

        top_k = top_k or settings.retrieval_top_k
        final_top_k = final_top_k or settings.final_top_k

        t0 = time.time()

        # 1. Dense retrieval (semantic)
        dense_results = self.vs.query_dense(question, top_k=top_k)
        logger.debug("Dense retrieval: {} candidați", len(dense_results))

        # 2. BM25 retrieval (lexical)
        self._ensure_bm25()
        bm25_results = self.bm25.query(question, top_k=top_k)
        logger.debug("BM25 retrieval: {} candidați", len(bm25_results))

        # 3. RRF fusion
        merged = reciprocal_rank_fusion(
            dense_results=dense_results,
            bm25_results=bm25_results,
            alpha=settings.hybrid_alpha,
        )
        logger.debug("După RRF: {} candidați unici", len(merged))

        # 4. Re-ranking cu cross-encoder (top reranker_top_n)
        if self.reranker.is_enabled() and merged:
            # Limităm la 20 candidați pentru rerank (cost vs. acuratețe)
            ranked = self.reranker.rerank(question, merged[:20], top_n=final_top_k)
            # Cross-encoder-ul a evaluat deja relevanța reală a fiecărui fragment;
            # NU mai filtrăm după scorul dense (fragmentele găsite doar prin BM25
            # au score=0.0 și ar fi eliminate eronat, deși sunt relevante).
            # Aplicăm însă un prag RELATIV pe scorul de rerank, ca să eliminăm
            # fragmentele clar irelevante (și deci sursele lor parazite).
            result = self._keep_relevant(ranked)
        else:
            ranked = merged[:final_top_k]
            # Fără rerank, filtrăm după scorul dense ca prag minim de relevanță.
            filtered = [r for r in ranked if r.get("score", 1.0) >= settings.min_score]
            # Dacă filtrul lasă totul gol, întoarcem totuși ce am găsit
            result = filtered if filtered else ranked

        logger.info(
            "Retrieval pentru '{}': {} fragmente finale ({:.0f}ms)",
            question[:60], len(result), (time.time() - t0) * 1000,
        )
        return result
