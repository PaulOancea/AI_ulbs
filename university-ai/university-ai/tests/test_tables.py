"""Teste pentru extragerea și chunking-ul tabelelor (rânduri/coloane)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.core.chunker import LegalAwareChunker
from backend.core.loaders import render_table_md


def test_render_table_basic():
    rows = [["Nume", "An"], ["Popescu", "I"], ["Ionescu", "II"]]
    md = render_table_md(rows)
    assert "| Nume | An |" in md
    assert "| --- | --- |" in md
    assert "| Popescu | I |" in md


def test_render_table_forward_fills_merged_cells():
    """Celulele îmbinate pe verticală (None) trebuie propagate pe fiecare rând."""
    rows = [
        ["Program", "Anul", "Nume"],
        ["Calculatoare", "I", "FLOREA Adrian"],
        [None, "II", "BREAZU Macarie"],   # 'Program' îmbinat → None
        [None, "III", "BARGLAZAN Adrian"],
    ]
    md = render_table_md(rows)
    # Fiecare rând trebuie să poarte numele programului
    assert "| Calculatoare | II | BREAZU Macarie |" in md
    assert "| Calculatoare | III | BARGLAZAN Adrian |" in md


def test_render_table_drops_empty_rows_and_flattens_newlines():
    rows = [["A", "B"], ["", ""], ["x\ny", "z"]]
    md = render_table_md(rows)
    assert "| x y | z |" in md          # newline aplatizat
    assert md.count("\n") == 2          # header + sep + 1 rând de date (rândul gol eliminat)


def test_render_table_empty():
    assert render_table_md([]) == ""
    assert render_table_md([[None, ""], ["", None]]) == ""


def test_chunker_repeats_header_for_large_table():
    """Fiecare bucată dintr-un tabel mare trebuie să păstreze antetul + marcajul."""
    header = "| Anul | Nume | Email |"
    sep = "| --- | --- | --- |"
    data = [f"| {i} | Tutore {i} Popescu | t{i}@ulbsibiu.ro |" for i in range(1, 40)]
    segment = "[Tabel 1]\n" + header + "\n" + sep + "\n" + "\n".join(data)

    chunker = LegalAwareChunker(chunk_size=300, chunk_overlap=30, legal_aware=True)
    chunks = chunker.chunk(segment, source="Tutori.pdf", page=1)

    assert len(chunks) > 1  # tabelul a fost împărțit
    for ch in chunks:
        assert "Anul | Nume | Email" in ch.text   # antetul prezent peste tot
        assert "[Tabel 1]" in ch.text              # marcajul prezent peste tot


def test_chunker_keeps_small_table_intact():
    header = "| Anul | Nume |"
    sep = "| --- | --- |"
    segment = "[Tabel 1]\n" + header + "\n" + sep + "\n| I | Popescu |\n| II | Ionescu |"
    chunker = LegalAwareChunker(chunk_size=900, legal_aware=True)
    chunks = chunker.chunk(segment, source="x.pdf", page=1)
    assert len(chunks) == 1
    assert "Popescu" in chunks[0].text and "Ionescu" in chunks[0].text
