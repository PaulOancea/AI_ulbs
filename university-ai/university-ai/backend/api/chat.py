"""
backend/api/chat.py
═══════════════════
Endpoint-uri pentru chat:
  • POST     /chat                  → răspuns complet (non-streaming)
  • WS       /chat/stream           → streaming WebSocket (token-cu-token)
  • DELETE   /chat/session/{id}     → resetează memoria unei sesiuni
"""

import json

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from backend.core.memory import memory_manager
from backend.core.rag_chain import RAGChain
from backend.exceptions import AppException
from backend.logging_config import logger
from backend.schemas import ChatRequest, ChatResponse, SourceChunk

router = APIRouter(prefix="/chat", tags=["chat"])

_chain = RAGChain()


# ─── REST: răspuns sync ───────────────────────────────────────────────────────

@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Generează un răspuns complet pentru o întrebare (non-streaming)."""
    try:
        result = _chain.answer(
            question=req.question,
            session_id=req.session_id,
            model=req.model,
        )
    except AppException as exc:
        logger.warning("Chat error: {}", exc.message)
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    # Convertim chunk-urile la SourceChunk Pydantic
    chunks = [
        SourceChunk(
            source=c["source"],
            page=str(c["page"]),
            score=c.get("score", 0.0),
            rerank_score=c.get("rerank_score"),
            text=c["text"][:500],  # trunchiem pentru payload
        )
        for c in result["chunks"]
    ]

    return ChatResponse(
        answer=result["answer"],
        sources=result["sources"],
        chunks=chunks,
        session_id=result["session_id"],
        rewritten_query=result["rewritten_query"],
        elapsed_ms=result["elapsed_ms"],
    )


# ─── WebSocket: streaming token-cu-token ──────────────────────────────────────

@router.websocket("/stream")
async def chat_stream(ws: WebSocket):
    """
    Protocol mesaje:
      Client → server (JSON):
        {"question": "...", "session_id": "...", "model": "..."}
      Server → client (JSON):
        {"type": "metadata", "sources": [...], "chunks": [...], ...}
        {"type": "token", "token": "..."}
        {"type": "done", "elapsed_ms": 1234}
        {"type": "error", "message": "..."}
    """
    await ws.accept()
    logger.info("WebSocket client connected")

    try:
        while True:
            raw = await ws.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "message": "JSON invalid"})
                continue

            question = payload.get("question", "")
            session_id = payload.get("session_id", "default")
            model = payload.get("model")

            async for event in _chain.astream_answer(
                question=question, session_id=session_id, model=model,
            ):
                await ws.send_json(event)

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as exc:
        logger.exception("WebSocket error neașteptat")
        try:
            await ws.send_json({"type": "error", "message": "Eroare internă"})
        except Exception:
            pass


# ─── Reset sesiune ────────────────────────────────────────────────────────────

@router.delete("/session/{session_id}", status_code=204)
async def reset_session(session_id: str):
    """Șterge istoricul conversațional al unei sesiuni."""
    memory_manager.clear_session(session_id)
    return None
