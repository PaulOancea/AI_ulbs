"""
backend/api/documents.py
════════════════════════
Endpoint-uri pentru gestionarea documentelor:
  • POST   /documents/upload    → upload + indexare unul/mai multe fișiere
  • POST   /documents/folder    → indexare toate fișierele dintr-un folder
  • GET    /documents           → listă documente indexate
  • DELETE /documents           → resetare completă a bazei
"""

from typing import List

from fastapi import APIRouter, File, HTTPException, UploadFile, Query

from backend.config import settings
from backend.core.ingestion import IngestionService
from backend.core.vector_store import VectorStore
from backend.logging_config import logger
from backend.schemas import DocumentInfo, IngestFolderResult, IngestResult

router = APIRouter(prefix="/documents", tags=["documents"])

_service = IngestionService()


@router.post("/upload", response_model=List[IngestResult])
async def upload_documents(
    files: List[UploadFile] = File(...),
    force: bool = Query(False, description="Re-indexează chiar dacă există"),
):
    """Indexează unul sau mai multe fișiere uploadate."""
    results: List[IngestResult] = []
    for file in files:
        content = await file.read()
        result = _service.ingest_file_bytes(content, file.filename, force=force)
        results.append(IngestResult(**result))
    return results


@router.post("/folder", response_model=IngestFolderResult)
async def index_folder(
    folder: str = Query(None, description="Cale absolută sau relativă"),
    force: bool = Query(False),
):
    """Indexează toate documentele dintr-un folder de pe server."""
    folder = folder or settings.docs_folder
    result = _service.ingest_folder(folder, force=force)
    return IngestFolderResult(**result)


@router.get("", response_model=List[DocumentInfo])
async def list_documents():
    """Returnează lista documentelor indexate."""
    vs = VectorStore()
    ingested = vs.get_ingested_files()
    return [DocumentInfo(filename=name, chunks=n) for name, n in ingested.items()]


@router.delete("", status_code=204)
async def reset_database():
    """Șterge tot conținutul bazei vectoriale. ATENȚIE: ireversibil!"""
    vs = VectorStore()
    vs.clear_all()
    logger.warning("Baza vectorială a fost resetată prin API.")
    return None
