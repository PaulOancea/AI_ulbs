"""
backend/core/ingestion.py
═════════════════════════
Pipeline complet de ingestie: fișier → text → chunks → embeddings → ChromaDB.

Există două puncte de intrare:
  • `ingest_file_path(path)`        — pentru fișiere de pe disc
  • `ingest_file_bytes(bytes, name)` — pentru upload prin browser
  • `ingest_folder(folder)`         — pentru procesare batch
"""

import os
import shutil
import tempfile
from pathlib import Path
from typing import List

from backend.config import settings
from backend.core.chunker import Chunk, default_chunker
from backend.core.loaders import SUPPORTED_EXTENSIONS, load_document
from backend.core.vector_store import VectorStore
from backend.exceptions import DocumentProcessingError
from backend.logging_config import logger


class IngestionService:
    """Serviciul de indexare documente."""

    def __init__(self, vector_store: VectorStore = None):
        self.vs = vector_store or VectorStore()

    # ── Helper: salvează o copie a fișierului original ───────────────────────

    @staticmethod
    def _save_original_bytes(filename: str, data: bytes) -> None:
        """Păstrează fișierul original (pentru completarea cu păstrarea layout-ului)."""
        try:
            dest = settings.originals_folder_abs / Path(filename).name
            dest.write_bytes(data)
        except Exception as exc:
            logger.warning("Nu am putut salva originalul {}: {}", filename, exc)

    @staticmethod
    def _save_original_path(path: Path) -> None:
        try:
            dest = settings.originals_folder_abs / path.name
            shutil.copyfile(path, dest)
        except Exception as exc:
            logger.warning("Nu am putut copia originalul {}: {}", path.name, exc)

    # ── Helper: procesează un singur fișier ──────────────────────────────────

    def _process_file(self, path: Path, display_name: str = None) -> List[Chunk]:
        """Citește, curăță și împarte în chunks un fișier."""
        display_name = display_name or path.name
        pages = load_document(path)
        if not pages:
            logger.warning("Niciun text extras din {}", display_name)
            return []

        all_chunks: List[Chunk] = []
        for page_data in pages:
            chunks = default_chunker.chunk(
                text=page_data.text,
                source=display_name,
                page=page_data.page,
                is_ocr=bool(page_data.extra.get("ocr")),
            )
            all_chunks.extend(chunks)

        logger.info("{}: {} pagini → {} chunks", display_name, len(pages), len(all_chunks))
        return all_chunks

    # ── Public: extragere fără indexare (documente atașate în chat) ──────────

    def extract_chunks_from_bytes(self, file_bytes: bytes, filename: str) -> List[dict]:
        """
        Extrage și împarte în fragmente un document, FĂRĂ a-l adăuga în baza
        vectorială. Folosit pentru documentele atașate de utilizator într-o
        conversație (context efemer, nu persistent/global).

        Returnează listă de dict-uri {text, source, page, section} — pregătite
        pentru a fi folosite direct ca context de către RAGChain.
        """
        ext = Path(filename).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise DocumentProcessingError(f"Format nesuportat: {ext}")

        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = Path(tmp.name)

        try:
            chunks = self._process_file(tmp_path, display_name=filename)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        return [
            {
                "text": c.text,
                "source": c.source,
                "page": c.page,
                "section": c.section or "",
            }
            for c in chunks
        ]

    # ── Public: ingestie fișier pe disc ──────────────────────────────────────

    def ingest_file_path(self, path: str, force: bool = False) -> dict:
        path_obj = Path(path)
        filename = path_obj.name

        if not force and self.vs.is_ingested(filename):
            return {
                "status": "skip",
                "filename": filename,
                "chunks": 0,
                "message": "Deja indexat (folosește force=True pentru re-indexare).",
            }

        try:
            chunks = self._process_file(path_obj)
        except DocumentProcessingError as exc:
            return {
                "status": "error",
                "filename": filename,
                "chunks": 0,
                "message": exc.message,
            }

        if not chunks:
            return {
                "status": "error",
                "filename": filename,
                "chunks": 0,
                "message": "Niciun fragment extras (document gol sau scanat?).",
            }

        self._save_original_path(path_obj)
        # Ștergem eventualele fragmente vechi ale aceluiași fișier (re-indexare)
        # ca să NU se dubleze conținutul în baza vectorială.
        self.vs.delete_by_source(filename)
        added = self.vs.add_chunks(chunks)
        self.vs.mark_ingested(filename, added)

        return {"status": "ok", "filename": filename, "chunks": added}

    # ── Public: ingestie din bytes (Streamlit / FastAPI upload) ──────────────

    def ingest_file_bytes(
        self, file_bytes: bytes, filename: str, force: bool = False,
    ) -> dict:
        if not force and self.vs.is_ingested(filename):
            return {
                "status": "skip",
                "filename": filename,
                "chunks": 0,
                "message": "Deja indexat.",
            }

        ext = Path(filename).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return {
                "status": "error",
                "filename": filename,
                "chunks": 0,
                "message": f"Format nesuportat: {ext}",
            }

        # Salvăm într-un fișier temporar pentru a putea folosi loaderele
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = Path(tmp.name)

        try:
            chunks = self._process_file(tmp_path, display_name=filename)
        except DocumentProcessingError as exc:
            os.unlink(tmp_path)
            return {
                "status": "error",
                "filename": filename,
                "chunks": 0,
                "message": exc.message,
            }
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        if not chunks:
            return {
                "status": "error",
                "filename": filename,
                "chunks": 0,
                "message": "Niciun fragment extras.",
            }

        self._save_original_bytes(filename, file_bytes)
        # Ștergem eventualele fragmente vechi ale aceluiași fișier (re-indexare)
        # ca să NU se dubleze conținutul în baza vectorială.
        self.vs.delete_by_source(filename)
        added = self.vs.add_chunks(chunks)
        self.vs.mark_ingested(filename, added)
        return {"status": "ok", "filename": filename, "chunks": added}

    # ── Public: ingestie folder ──────────────────────────────────────────────

    def ingest_folder(self, folder: str, force: bool = False) -> dict:
        folder_path = Path(folder)
        if not folder_path.exists():
            return {"files_processed": 0, "chunks_added": 0, "skipped": 0,
                    "errors": [f"Folderul {folder} nu există."]}

        files = [
            f for f in folder_path.iterdir()
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
        ]

        processed = skipped = total_chunks = 0
        errors: List[str] = []

        for f in files:
            result = self.ingest_file_path(str(f), force=force)
            if result["status"] == "ok":
                processed += 1
                total_chunks += result["chunks"]
            elif result["status"] == "skip":
                skipped += 1
            else:
                errors.append(f"{f.name}: {result['message']}")

        logger.info(
            "Ingest folder {}: {} procesate, {} sărite, {} chunks, {} erori",
            folder, processed, skipped, total_chunks, len(errors),
        )

        return {
            "files_processed": processed,
            "chunks_added": total_chunks,
            "skipped": skipped,
            "errors": errors,
        }
