"""
backend/schemas.py
══════════════════
Modele Pydantic pentru request/response — contractul API.
"""

from datetime import datetime
from typing import List, Optional, Literal

from pydantic import BaseModel, Field


# ── Chat ──────────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    """Un mesaj individual din istoricul conversației."""
    role: Literal["user", "assistant"] = Field(..., description="Rolul emițătorului")
    content: str = Field(..., min_length=1, description="Conținutul mesajului")


class ChatRequest(BaseModel):
    """Cererea către endpoint-ul /chat."""
    question: str = Field(..., min_length=2, max_length=2000)
    session_id: str = Field("default", description="ID pentru memoria conversațională")
    model: Optional[str] = None
    history: Optional[List[ChatMessage]] = None


class SourceChunk(BaseModel):
    """Un fragment-sursă folosit pentru construirea răspunsului."""
    source: str
    page: str
    score: float = Field(..., ge=0.0, le=1.0)
    rerank_score: Optional[float] = None
    text: str


class ChatResponse(BaseModel):
    """Răspunsul complet de la /chat (modul non-streaming)."""
    answer: str
    sources: List[str]
    chunks: List[SourceChunk]
    session_id: str
    rewritten_query: Optional[str] = None
    elapsed_ms: int


# ── Documente ─────────────────────────────────────────────────────────────────

class IngestResult(BaseModel):
    """Rezultatul indexării unui fișier."""
    status: Literal["ok", "skip", "error"]
    filename: str
    chunks: int = 0
    message: Optional[str] = None


class IngestFolderResult(BaseModel):
    files_processed: int
    chunks_added: int
    skipped: int
    errors: List[str] = []


class DocumentInfo(BaseModel):
    """Informații despre un document indexat."""
    filename: str
    chunks: int
    indexed_at: Optional[datetime] = None


# ── Health & status ───────────────────────────────────────────────────────────

class HealthStatus(BaseModel):
    status: Literal["ok", "degraded", "down"]
    ollama_reachable: bool
    ollama_models: List[str]
    chromadb_count: int
    indexed_documents: int
    reranker_enabled: bool
    memory_enabled: bool
    version: str
