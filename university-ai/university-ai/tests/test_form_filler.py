"""Teste pentru completarea automată a cererilor (form_filler)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.core import form_filler as ff


class FakeVS:
    """Vector store minimal pentru teste (doar metodele folosite de form_filler)."""

    def __init__(self, docs):
        # docs: listă de {text, source, page, chunk_index}
        self._docs = docs

    def get_all_documents(self):
        return [{"text": d["text"], "source": d["source"]} for d in self._docs]

    def get_documents_by_source(self, source):
        items = [d for d in self._docs if d["source"] == source]
        return sorted(items, key=lambda d: (int(d.get("page", 0)), int(d.get("chunk_index", 0))))


_DOCS = [
    {"source": "Cerere-bursa.docx", "page": 1, "chunk_index": 0,
     "text": "Subsemnatul .........., student în anul ...., solicit acordarea bursei."},
    {"source": "Cerere-inmatriculare.docx", "page": 1, "chunk_index": 0,
     "text": "Subsemnatul .........., solicit înmatricularea în anul universitar ...."},
    {"source": "Regulament_examene.pdf", "page": 1, "chunk_index": 0,
     "text": "Art. 1. Examenele se desfășoară conform calendarului."},
]


def test_is_form_request():
    assert ff.is_form_request("Completează-mi o cerere de bursă")
    assert ff.is_form_request("Vreau o cerere de înmatriculare")
    assert not ff.is_form_request("Care sunt condițiile pentru bursă?")
    assert not ff.is_form_request("Cine este Adrian Florea?")


def test_list_templates_excludes_non_forms():
    vs = FakeVS(_DOCS)
    templates = ff.list_form_templates(vs)
    assert "Cerere-bursa.docx" in templates
    assert "Cerere-inmatriculare.docx" in templates
    assert "Regulament_examene.pdf" not in templates   # nu e cerere


def test_find_template_matches_subject():
    vs = FakeVS(_DOCS)
    src, available = ff.find_template(vs, "completează-mi o cerere de bursă")
    assert src == "Cerere-bursa.docx"
    src2, _ = ff.find_template(vs, "vreau o cerere de înmatriculare")
    assert src2 == "Cerere-inmatriculare.docx"


def test_find_template_not_found_lists_available():
    vs = FakeVS(_DOCS)
    src, available = ff.find_template(vs, "completează o cerere de cazare la cămin")
    assert src is None
    assert set(available) == {"Cerere-bursa.docx", "Cerere-inmatriculare.docx"}


def test_find_template_no_templates_at_all():
    vs = FakeVS([_DOCS[2]])   # doar regulamentul
    src, available = ff.find_template(vs, "completează o cerere de bursă")
    assert src is None
    assert available == []


def test_get_full_document_text_orders_chunks():
    docs = [
        {"source": "C.docx", "page": 1, "chunk_index": 1, "text": "lume"},
        {"source": "C.docx", "page": 1, "chunk_index": 0, "text": "salut"},
        {"source": "C.docx", "page": 2, "chunk_index": 0, "text": "final"},
    ]
    vs = FakeVS(docs)
    text = ff.get_full_document_text(vs, "C.docx")
    assert text == "salut\nlume\nfinal"


def test_extract_blank_contexts_only_real_fields():
    """Extrage DOAR locurile goale reale — nu declarații, semnătură, aprobări."""
    tpl = (
        "Nr.    /\nDomnule Decan,\n"
        "Subsemnatul/a ____________, vă rog să-mi aprobați reînmatricularea la "
        "programul de studii____________, în anul______, an universitar 2021 – 2022.\n"
        "Mă oblig să achit taxa de reînmatriculare și taxele de școlarizare.\n"
        "Telefon :\nSemnătura,\nData\nAprobat Director departament"
    )
    blanks = " ".join(ff.extract_blank_contexts(tpl)).lower()
    assert "subsemnat" in blanks
    assert "programul de studii" in blanks
    assert "anul" in blanks
    assert "telefon" in blanks
    # NU trebuie să apară declarații/semnătură/aprobare ca și câmpuri
    assert "oblig" not in blanks
    assert "semnatura" not in blanks
    assert "aprobat director" not in blanks


def test_build_form_prompt_lists_blanks():
    blanks = ["Subsemnatul/a ___", "Telefon: ___"]
    p = ff.build_form_prompt("șablon", "date", blanks)
    assert "LOCURI GOALE" in p
    assert "Subsemnatul/a ___" in p and "Telefon: ___" in p


def test_deterministic_extract_and_fill():
    """Extragere valori + completare deterministă a șablonului."""
    tpl = ("Domnule Decan,\nSubsemnatul/a ______, vă rog să-mi aprobați "
           "reînmatricularea la programul de studii______, în anul______, "
           "an universitar 2021 – 2022.\nTelefon :\nSemnătura,")
    fields = ff.extract_field_names(tpl)
    assert "numele și prenumele" in fields
    assert "programul de studii" in fields
    assert "anul de studiu" in fields
    assert "numărul de telefon" in fields

    resp = ("numele și prenumele = Chitoiu Robert\nprogramul de studii = Calculatoare\n"
            "anul de studiu = 3\nnumărul de telefon = 0758240689")
    values = ff.parse_extraction(resp, fields)
    assert ff.missing_fields(fields, values) == []

    filled = ff.fill_template(tpl, values)
    assert "Chitoiu Robert" in filled
    assert "Calculatoare" in filled
    assert "0758240689" in filled


def test_fields_detected_with_whitespace_blanks_docx_style():
    """Locurile goale din .docx sunt spații/tab-uri (nu underscore) — detectate corect."""
    tpl = ("Subsemnatul/a , vă rog să-mi aprobați reînmatricularea la programul "
           "de studii , în anul\t, an universitar 2021 - 2022.\nTelefon :")
    fields = ff.extract_field_names(tpl)
    assert set(fields) == {"numele și prenumele", "programul de studii",
                           "anul de studiu", "numărul de telefon"}
    vals = ff.extract_values_code(
        fields, "numele meu este Ana Pop, programul de studii Drept, anul 2, telefon 0712345678")
    assert ff.missing_fields(fields, vals) == []
    filled = ff.fill_template(tpl, vals)
    assert "Subsemnatul/a Ana Pop," in filled
    assert "programul de studii Drept," in filled
    assert "în anul 2," in filled
    assert "Telefon : 0712345678" in filled


def test_code_extraction_explicit_input():
    """Extragerea în cod ia valorile din formulări explicite, fără LLM."""
    fields = ["numele și prenumele", "programul de studii", "anul de studiu",
              "numărul de telefon"]
    txt = ("Numaru meu matricol este 411322 numele meu este Chitoiu Robert, "
           "programul de studii este Calculatoare anul este 3 telefonu este "
           "0758 240 689 si semnatura o completez eu")
    v = ff.extract_values_code(fields, txt)
    assert v[ff.normalize("numele și prenumele")] == "Chitoiu Robert"
    assert v[ff.normalize("programul de studii")] == "Calculatoare"
    assert v[ff.normalize("anul de studiu")] == "3"
    assert "0758" in v[ff.normalize("numărul de telefon")]
    assert ff.missing_fields(fields, v) == []


def test_code_extraction_partial():
    fields = ["numele și prenumele", "programul de studii"]
    v = ff.extract_values_code(fields, "Nume si prenumele este Chitoiu Robert")
    assert v[ff.normalize("numele și prenumele")] == "Chitoiu Robert"
    assert ff.missing_fields(fields, v) == ["programul de studii"]


def test_missing_fields_detected():
    tpl = "Subsemnatul/a ______, la programul de studii______.\nTelefon :"
    fields = ff.extract_field_names(tpl)
    resp = "numele și prenumele = Ion Pop\nprogramul de studii = LIPSA\nnumărul de telefon = LIPSA"
    values = ff.parse_extraction(resp, fields)
    missing = ff.missing_fields(fields, values)
    assert "programul de studii" in missing
    assert "numărul de telefon" in missing
    assert "numele și prenumele" not in missing


def test_generate_filled_document_pdf_fallback():
    """Pentru un șablon fără original .docx → text docx, layout_kept=False."""
    vals = {ff.normalize("numele și prenumele"): "Ion Pop"}
    tpl = "Subsemnatul/a ______ solicit."
    data, name, layout_kept = ff.generate_filled_document("inexistent.pdf", tpl, vals)
    assert data[:2] == b"PK"           # docx valid
    assert layout_kept is False        # nu există original .docx
    assert name.endswith(".docx")


def test_fill_docx_in_place_preserves_text():
    """Completarea în loc inserează valorile într-un .docx."""
    from io import BytesIO
    from docx import Document
    d = Document()
    d.add_paragraph("Subsemnatul/a ______, în anul______.")
    buf = BytesIO()
    d.save(buf)
    vals = {
        ff.normalize("numele și prenumele"): "Ana Ionescu",
        ff.normalize("anul de studiu"): "2",
    }
    out = ff.fill_docx_in_place(buf.getvalue(), vals)
    text = "\n".join(p.text for p in Document(BytesIO(out)).paragraphs)
    assert "Ana Ionescu" in text and "2" in text


def test_parse_and_generate():
    assert ff.parse_form_response("LIPSESC\n- CNP")[0] == "missing"
    status, body = ff.parse_form_response("COMPLET\nSubsemnatul Ion Popescu solicit bursa.")
    assert status == "complete" and "Ion Popescu" in body
    docx = ff.generate_docx(body)
    assert docx[:2] == b"PK"   # .docx e arhivă zip
