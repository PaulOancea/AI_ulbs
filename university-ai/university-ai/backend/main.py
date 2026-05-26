"""
backend/main.py
═══════════════
Aplicația FastAPI principală.

Rulează cu:  uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend import __version__
from backend.api import chat, documents, health
from backend.config import settings
from backend.exceptions import AppException
from backend.logging_config import logger, setup_logging


# ─── Lifecycle: setup + warm-up ───────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inițializare la pornire + cleanup la oprire."""
    setup_logging()
    logger.info("═══════════════════════════════════════════════════════")
    logger.info("  AI Universitar Backend v{} pornește", __version__)
    logger.info("═══════════════════════════════════════════════════════")

    # Warm-up: forțăm inițializarea singleton-urilor pentru a nu plăti
    # costul încărcării modelelor la prima cerere.
    from backend.core.vector_store import VectorStore
    VectorStore()  # → încarcă embedder + ChromaDB

    logger.info("Backend gata pentru cereri pe portul {}", settings.api_port)
    yield
    logger.info("Backend se oprește.")


app = FastAPI(
    title="AI Universitar API",
    description="Asistent virtual pentru regulamentele universității (RAG + Ollama).",
    version=__version__,
    lifespan=lifespan,
)


# ─── CORS ─────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Global exception handler ─────────────────────────────────────────────────

@app.exception_handler(AppException)
async def app_exception_handler(_: Request, exc: AppException):
    """Convertește excepțiile noastre în răspunsuri JSON consistente."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message, "details": exc.details},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(_: Request, exc: Exception):
    """Capturăm orice excepție neașteptată pentru a evita 500 unformatted."""
    logger.exception("Excepție neașteptată: {}", exc)
    return JSONResponse(
        status_code=500,
        content={"error": "Eroare internă a serverului. Verifică log-urile."},
    )


# ─── Routes ───────────────────────────────────────────────────────────────────

app.include_router(health.router)
app.include_router(documents.router)
app.include_router(chat.router)


@app.get("/", tags=["root"])
async def root():
    return {
        "name": "AI Universitar API",
        "version": __version__,
        "docs": "/docs",
        "health": "/health",
    }
