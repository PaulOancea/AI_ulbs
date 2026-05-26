"""Teste pentru chunkerul legal-aware."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.core.chunker import LegalAwareChunker, detect_section


def test_detect_section_article():
    text = "Art. 17 — Studentul are dreptul..."
    assert detect_section(text) == "Art. 17"


def test_detect_section_chapter():
    text = "Capitolul II — Drepturi și obligații"
    assert detect_section(text) == "Capitolul II"


def test_detect_section_articolul_long():
    text = "Articolul 23 Procedura de examinare se desfășoară..."
    assert detect_section(text) == "Art. 23"


def test_detect_section_none():
    assert detect_section("Acesta este un text obișnuit.") is None


def test_chunker_keeps_short_articles_intact():
    text = """Art. 5 Studentul are dreptul de a fi informat.

Art. 6 Studentul are obligația de a frecventa cursurile."""

    chunker = LegalAwareChunker(chunk_size=900, chunk_overlap=100, legal_aware=True)
    chunks = chunker.chunk(text, source="test.pdf", page=1)

    # Cele două articole trebuie să fie chunks separate
    assert len(chunks) == 2
    assert chunks[0].section == "Art. 5"
    assert chunks[1].section == "Art. 6"


def test_chunker_splits_large_articles():
    long_text = "Art. 10 " + ("text foarte lung " * 100)
    chunker = LegalAwareChunker(chunk_size=200, chunk_overlap=30)
    chunks = chunker.chunk(long_text, source="test.pdf", page=1)
    assert len(chunks) > 1
    # Toate sub-chunk-urile moștenesc eticheta articolului
    for ch in chunks:
        assert ch.section == "Art. 10"


def test_chunker_handles_empty():
    chunker = LegalAwareChunker()
    assert chunker.chunk("", "x.pdf") == []
    assert chunker.chunk("   ", "x.pdf") == []
