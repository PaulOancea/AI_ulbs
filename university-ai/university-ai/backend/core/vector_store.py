"""
backend/core/vector_store.py
════════════════════════════
Wrapper peste ChromaDB cu:
  • embeddings calculate de SentenceTransformer (multilingv, optimizat RO);
  • inserții în batch-uri pentru a evita timeout-uri;
  • salvarea unui index BM25 paralel pentru retrieval hibrid;
  • log structurat al fiecărei operații;
  • metoda `query_dense()` care întoarce documente normalizate (similarity 0-1).
"""

import json
import time
import uuid
from pathlib import Path
from threading import Lock
from typing import List, Optional

import chromadb
from sentence_transformers import SentenceTransformer

from backend.config import settings
from backend.core.chunker import Chunk
from backend.exceptions import VectorStoreError
from backend.logging_config import logger


# Locație log pentru fișierele indexate (pentru deduplicare la re-rulare)
INGESTED_LOG_PATH = settings.chroma_path_abs / "ingested_files.json"


def _load_ingested_log() -> dict:
    """Încarcă registrul fișierelor deja indexate."""
    if INGESTED_LOG_PATH.exists():
        try:
            return json.loads(INGESTED_LOG_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Log ingest corupt — reset: {}", exc)
    return {}


def _save_ingested_log(data: dict) -> None:
    INGESTED_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    INGESTED_LOG_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── Vector Store ──────────────────────────────────────────────────────────────

class VectorStore:
    """
    Singleton thread-safe pentru ChromaDB + embedder.

    Folosește pattern-ul "instanță unică" pentru a evita re-încărcarea
    modelului SentenceTransformer (~400 MB) la fiecare request.
    """

    _instance: Optional["VectorStore"] = None
    _lock = Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        logger.info("Inițializez ChromaDB la {}", settings.chroma_path_abs)
        try:
            self.client = chromadb.PersistentClient(path=str(settings.chroma_path_abs))
            self.collection = self.client.get_or_create_collection(
                name=settings.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        except Exception as exc:
            logger.exception("Eroare la inițializarea ChromaDB")
            raise VectorStoreError(
                "Nu am putut inițializa baza de date vectorială."
            ) from exc

        logger.info(
            "ChromaDB OK — {} fragmente existente în colecția '{}'",
            self.collection.count(),
            settings.collection_name,
        )

        logger.info("Încarc modelul de embeddings: {} (device: {})",
                    settings.embed_model, settings.embed_device)
        t0 = time.time()
        self.embedder = SentenceTransformer(
            settings.embed_model,
            device=settings.embed_device,
        )
        logger.info("Embedder gata ({:.1f}s)", time.time() - t0)

        self._ingested = _load_ingested_log()

    # ── Adăugare ─────────────────────────────────────────────────────────────

    def add_chunks(self, chunks: List[Chunk]) -> int:
        """Calculează embeddings și inserează lista de chunk-uri."""
        if not chunks:
            return 0

        texts = [c.text for c in chunks]
        metadatas = [c.to_metadata() for c in chunks]
        ids = [str(uuid.uuid4()) for _ in chunks]

        logger.info("Calculez embeddings pentru {} fragmente...", len(texts))
        t0 = time.time()
        embeddings = self.embedder.encode(
            texts,
            batch_size=32,
            show_progress_bar=False,
            convert_to_numpy=True,
        ).tolist()
        logger.debug("Embeddings gata ({:.1f}s)", time.time() - t0)

        # Inserții în batch-uri de 200 — ChromaDB poate eșua pe loturi mari
        BATCH = 200
        try:
            for i in range(0, len(texts), BATCH):
                self.collection.add(
                    documents=texts[i : i + BATCH],
                    embeddings=embeddings[i : i + BATCH],
                    metadatas=metadatas[i : i + BATCH],
                    ids=ids[i : i + BATCH],
                )
        except Exception as exc:
            logger.exception("Eroare la inserare ChromaDB")
            raise VectorStoreError(
                "Inserarea fragmentelor în baza vectorială a eșuat."
            ) from exc

        return len(texts)

    # ── Căutare dense (semantică) ────────────────────────────────────────────

    def query_dense(self, question: str, top_k: int) -> List[dict]:
        """
        Caută fragmentele cele mai similare semantic.
        Returnează listă de dict-uri normalizate (score în 0..1).
        """
        count = self.collection.count()
        if count == 0:
            return []

        try:
            embedding = self.embedder.encode([question])[0].tolist()
            n = min(top_k, count)
            results = self.collection.query(
                query_embeddings=[embedding],
                n_results=n,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            logger.exception("Query dense eșuat")
            raise VectorStoreError("Căutarea în baza vectorială a eșuat.") from exc

        out: List[dict] = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            # ChromaDB cu cosine returnează distance; similaritate = 1 - dist
            similarity = max(0.0, min(1.0, 1.0 - float(dist)))
            out.append({
                "text": doc,
                "source": meta.get("source", "?"),
                "page": meta.get("page", "?"),
                "section": meta.get("section", ""),
                "score": round(similarity, 4),
            })

        return out

    # ── Toate documentele (pentru BM25 in-memory) ────────────────────────────

    def get_all_documents(self) -> List[dict]:
        """
        Returnează toate documentele din colecție.
        Folosit la construirea indexului BM25 (care e in-memory).
        """
        count = self.collection.count()
        if count == 0:
            return []

        results = self.collection.get(include=["documents", "metadatas"])
        out: List[dict] = []
        for doc, meta in zip(results["documents"], results["metadatas"]):
            out.append({
                "text": doc,
                "source": meta.get("source", "?"),
                "page": meta.get("page", "?"),
                "section": meta.get("section", ""),
            })
        return out

    # ── Administrare ─────────────────────────────────────────────────────────

    def get_count(self) -> int:
        return self.collection.count()

    def get_ingested_files(self) -> dict:
        return dict(self._ingested)

    def mark_ingested(self, filename: str, chunk_count: int) -> None:
        self._ingested[filename] = chunk_count
        _save_ingested_log(self._ingested)

    def is_ingested(self, filename: str) -> bool:
        return filename in self._ingested

    def clear_all(self) -> None:
        """Șterge complet colecția și registrul de fișiere."""
        logger.warning("Resetez baza vectorială!")
        try:
            self.client.delete_collection(settings.collection_name)
        except Exception:
            pass
        self.collection = self.client.get_or_create_collection(
            name=settings.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._ingested = {}
        if INGESTED_LOG_PATH.exists():
            INGESTED_LOG_PATH.unlink()
