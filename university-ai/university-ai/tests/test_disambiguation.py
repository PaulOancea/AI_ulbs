"""Teste pentru dezambiguizare (întrebări generice pe concepte cu mai multe tipuri)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.core import disambiguation as dis


_CORPUS = (
    "Bursa socială se acordă studenților cu venituri reduse. "
    "Bursa de merit se acordă pentru rezultate bune. "
    "Bursa de performanță se acordă pentru rezultate de excepție. "
    "Taxa de școlarizare se achită semestrial. Taxa de înmatriculare la admitere."
)


def test_generic_question_triggers_clarification():
    r = dis.needs_clarification("În ce condiții se acordă bursa?", _CORPUS)
    assert r is not None
    concept, options = r
    assert concept == "bursă"
    assert len(options) >= 2


def test_specific_type_no_clarification():
    # întrebarea conține deja un tip → NU mai cerem lămurire
    assert dis.needs_clarification("Condițiile pentru bursa socială?", _CORPUS) is None
    assert dis.needs_clarification("Cum obțin bursa de merit?", _CORPUS) is None


def test_refined_question_does_not_loop():
    refined = "În ce condiții se acordă bursa? (bursă socială / de ajutor social)"
    assert dis.needs_clarification(refined, _CORPUS) is None


def test_irrelevant_question_ignored():
    assert dis.needs_clarification("Cine este Adrian Florea?", _CORPUS) is None
    assert dis.needs_clarification("Cum se calculează media?", _CORPUS) is None


def test_single_type_no_clarification():
    corpus = "Bursa de merit se acordă pentru rezultate bune."  # un singur tip
    assert dis.needs_clarification("Cum se acordă bursa?", corpus) is None


def test_taxa_clarification():
    r = dis.needs_clarification("Cât e taxa?", _CORPUS)
    assert r is not None and r[0] == "taxă"
    assert len(r[1]) >= 2
