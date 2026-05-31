"""Teste pentru filtrul de relevanță post-rerank (eliminarea surselor parazite)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.core.retriever import HybridRetriever


def _mk(scores):
    return [{"source": f"doc{i}.pdf", "text": "x", "rerank_score": s}
            for i, s in enumerate(scores)]


def test_keep_drops_low_tail():
    """Prăpastie clară după vârf → păstrăm doar vârful (o singură sursă)."""
    ranked = _mk([0.073, 0.034, 0.019, 0.002, 0.001])  # ratio 0.5 → prag 0.0365
    kept = HybridRetriever._keep_relevant(ranked)
    assert len(kept) == 1
    assert kept[0]["rerank_score"] == 0.073


def test_keep_multiple_when_close():
    """Mai multe fragmente apropiate de vârf → toate păstrate."""
    ranked = _mk([5.0, 4.0, 3.0, 1.0])  # prag 2.5 → păstrăm 5,4,3; ne oprim la 1
    kept = HybridRetriever._keep_relevant(ranked)
    assert [r["rerank_score"] for r in kept] == [5.0, 4.0, 3.0]


def test_keep_stops_at_first_drop():
    ranked = _mk([1.0, 0.9, 0.1, 0.8])  # 0.1 < 0.5 → break, 0.8 NU mai e considerat
    kept = HybridRetriever._keep_relevant(ranked)
    assert [r["rerank_score"] for r in kept] == [1.0, 0.9]


def test_keep_top_only_when_all_irrelevant():
    """Dacă nici vârful nu e relevant (≤0), păstrăm doar vârful."""
    ranked = _mk([-0.5, -0.6, -1.0])
    kept = HybridRetriever._keep_relevant(ranked)
    assert len(kept) == 1


def test_keep_passthrough_without_rerank_score():
    """Fără scor de rerank (reranker dezactivat) → nu filtrăm."""
    ranked = [{"source": "a.pdf", "text": "x", "score": 0.3},
              {"source": "b.pdf", "text": "y", "score": 0.1}]
    kept = HybridRetriever._keep_relevant(ranked)
    assert len(kept) == 2


def test_keep_empty():
    assert HybridRetriever._keep_relevant([]) == []
