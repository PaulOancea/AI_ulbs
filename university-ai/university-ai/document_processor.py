"""
document_processor.py — shim de compatibilitate

Folosește în loc:
    from backend.core.vector_store import VectorStore
    from backend.core.ingestion import IngestionService
"""

from backend.core.ingestion import IngestionService
from backend.core.vector_store import VectorStore


class DocumentStore:
    """Wrapper legacy peste noul VectorStore + IngestionService."""

    def __init__(self):
        self._vs = VectorStore()
        self._ingestion = IngestionService(self._vs)

    def get_count(self) -> int:
        return self._vs.get_count()

    def get_ingested_files(self) -> dict:
        return self._vs.get_ingested_files()

    def ingest_file_bytes(self, file_bytes: bytes, filename: str, force: bool = False):
        return self._ingestion.ingest_file_bytes(file_bytes, filename, force=force)

    def ingest_folder(self, folder: str, force: bool = False):
        r = self._ingestion.ingest_folder(folder, force=force)
        # Adaptăm la formatul legacy
        return {
            "files": r["files_processed"],
            "chunks": r["chunks_added"],
            "skipped": r["skipped"],
        }

    def query(self, question: str, top_k: int = 5):
        return self._vs.query_dense(question, top_k=top_k)

    def clear_all(self):
        self._vs.clear_all()
