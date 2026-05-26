"""
rag_engine.py — shim de compatibilitate

Folosește în loc:
    from backend.core.rag_chain import RAGChain
"""

from backend.core import llm
from backend.core.rag_chain import RAGChain


class RAGEngine:
    """Wrapper legacy peste noul RAGChain."""

    def __init__(self, store=None):
        self._chain = RAGChain()
        # `store` e ignorat — RAGChain își creează singur VectorStore-ul (singleton)

    def check_ollama(self) -> bool:
        return llm.is_alive()

    def get_available_models(self):
        return llm.list_models()

    def answer_sync(self, question: str, model: str = None):
        result = self._chain.answer(question, model=model)
        return {
            "answer": result["answer"],
            "sources": result["sources"],
            "chunks": result["chunks"],
        }

    def answer_stream(self, question: str, model: str = None):
        """Compatibilitate cu vechiul format: token-uri + sentinel '__META__{json}'."""
        import json as _json
        try:
            gen, meta = self._chain.stream_answer(question, model=model)
        except Exception as exc:
            yield f"❌ {exc}"
            return

        full = ""
        for tok in gen:
            full += tok
            yield tok

        # Salvăm în memorie după streaming
        self._chain.commit_to_memory("default", question, full)

        payload = {
            "sources": meta["sources"],
            "chunks": [
                {"source": c["source"], "page": c["page"], "score": c.get("score", 0)}
                for c in meta["chunks"]
            ],
        }
        yield f"\n__META__{_json.dumps(payload, ensure_ascii=False)}"
