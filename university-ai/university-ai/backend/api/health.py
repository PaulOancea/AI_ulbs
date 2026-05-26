"""
backend/api/health.py
═════════════════════
Endpoint-ul de status pentru monitorizare (folosit de UI, de Docker healthcheck etc.).
"""

from fastapi import APIRouter

from backend import __version__
from backend.config import settings
from backend.core import llm
from backend.core.vector_store import VectorStore
from backend.schemas import HealthStatus

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthStatus)
async def health() -> HealthStatus:
    """Verifică sănătatea componentelor cheie."""
    vs = VectorStore()
    ollama_ok = llm.is_alive()
    models = llm.list_models() if ollama_ok else []

    if not ollama_ok:
        status = "down"
    elif vs.get_count() == 0:
        status = "degraded"
    else:
        status = "ok"

    return HealthStatus(
        status=status,
        ollama_reachable=ollama_ok,
        ollama_models=models,
        chromadb_count=vs.get_count(),
        indexed_documents=len(vs.get_ingested_files()),
        reranker_enabled=settings.reranker_enabled,
        memory_enabled=settings.memory_enabled,
        version=__version__,
    )
