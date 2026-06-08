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


def test_detects_generic_fields_new_template():
    """Șablon nou (echivalare) cu locuri goale = spații înainte de virgulă:
    trebuie detectate TOATE câmpurile, nu doar cele predefinite."""
    tpl = ("Domnule Decan, Subsemnatul(a) la Facultatea de Medicină, specializarea , "
           "an universitar\t, echivalarea examenului la disciplina , examen promovat la "
           "Universitatea , Facultatea , cu nota\t.")
    fields = set(ff.extract_field_names(tpl))
    assert "programul de studii" in fields       # specializarea
    assert "anul universitar" in fields
    assert "disciplina" in fields
    assert "universitatea (de proveniență)" in fields
    assert "facultatea" in fields
    assert "nota" in fields


def test_rejects_junk_fields_free_text_request():
    """Cerere liberă tip PDF: zonele de text liber / semnătură / aprobare NU
    devin câmpuri (altfel formularul cere la nesfârșit date imposibile)."""
    tpl = (
        "Aprobat/Respins\nDomnule Decan\n"
        "Subsemnatul (a), ………, student la Facultatea de Drept, specializarea ......, "
        "anul ...... de studii, an universitar ......, vă rog să-mi aprobați ......\n"
        "Solicit acesta deoarece ......\nMenționez că ......\n"
        "Confirmare secretară specializare/semnătura ......\nMentiuni : ......\n"
        "Sibiu, Semnătură student\nData ......"
    )
    fields = ff.extract_field_names(tpl)
    # Câmpurile reale rămân
    assert "numele și prenumele" in fields
    assert "programul de studii" in fields
    assert "anul de studiu" in fields
    assert "anul universitar" in fields
    # Gunoiul dispare
    joined = " ".join(ff.normalize(f) for f in fields)
    for junk in ("deoarece", "mentionez", "mentiuni", "tiuni", "semnatur",
                 "aprobat", "respins", "confirmare", "informatia ceruta"):
        assert junk not in joined, f"câmp-gunoi detectat: {junk}"


def test_name_asked_and_inserted_without_slot():
    """Cerere cu „Subsemnatul(a) student(a)" fără slot → numele e cerut și inserat."""
    tpl = "Subsemnatul(a) student(a) la Facultatea de X, specializarea , cu nota\t."
    assert "numele și prenumele" in ff.extract_field_names(tpl)
    vals = {ff.normalize("numele și prenumele"): "Ion Popescu"}
    out = ff.fill_template(tpl, vals)
    assert "student(a) Ion Popescu la Facultatea" in out


def test_fill_generic_fields():
    tpl = "disciplina , examen promovat la Universitatea , cu nota\t."
    vals = {
        ff.normalize("disciplina"): "Anatomie",
        ff.normalize("universitatea (de proveniență)"): "UMF Cluj",
        ff.normalize("nota"): "9",
    }
    out = ff.fill_template(tpl, vals)
    assert "disciplina Anatomie" in out
    assert "Universitatea UMF Cluj" in out
    assert "nota 9" in out


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


# ══════════════════════════════════════════════════════════════════════════════
#  SLOT-URI POZIȚIONALE — câmpuri DUPLICATE (cazul „echivalare examen")
# ══════════════════════════════════════════════════════════════════════════════

# Șablon de echivalare ca cel din captura utilizatorului: „specializarea" ×2,
# „anul de studii" ×3, „an universitar" ×2, plus „Facultatea de" (proveniență).
_ECHIV = (
    "Domnule Decan,\n"
    "Subsemnatul(a) student(a)  la Facultatea de Medicina, specializarea , "
    "anul de studii , an universitar , va rog sa imi aprobati echivalarea "
    "examenului la disciplina , anul de studii , examen promovat la Universitatea , "
    "Facultatea de , specializarea  in anul de studii , an universitar , cu nota .\n"
    "Data,  Semnatura student,"
)


def test_extract_slots_preserves_duplicates():
    """Câmpurile repetate NU se contopesc — fiecare apariție = un slot separat."""
    slots = ff.extract_slots(_ECHIV)
    friendly = [s.friendly for s in slots]
    # 12 sloturi, în ordine, cu duplicate păstrate
    assert friendly == [
        "numele și prenumele",
        "programul de studii",            # specializarea TA
        "anul de studiu",                  # an de studii curent
        "anul universitar",
        "disciplina",
        "anul de studiu",                  # anul examenului promovat
        "universitatea (de proveniență)",
        "facultatea",                      # Facultatea de proveniență
        "programul de studii",            # specializarea de proveniență
        "anul de studiu",
        "anul universitar",
        "nota",
    ]
    # indecșii sunt 1-based și unici
    assert [s.index for s in slots] == list(range(1, 13))


def test_slot_year_not_misclassified_as_program():
    """Regresie: locul gol de după „anul de studii" NU mai devine „programul de studii"."""
    slots = ff.extract_slots(_ECHIV)
    years = [s.index for s in slots if s.friendly == "anul de studiu"]
    assert len(years) == 3        # toate cele 3 „anul de studii" sunt câmpuri de an


def test_facultatea_de_provenienta_detected_not_hardcoded():
    """„Facultatea de ___" (proveniență) e slot; „Facultatea de Medicina" (deja scris) NU."""
    slots = ff.extract_slots(_ECHIV)
    fac = [s for s in slots if s.friendly == "facultatea"]
    assert len(fac) == 1                       # doar cea de proveniență
    assert "Medicina" not in fac[0].context    # nu e cea hardcodată


def test_parse_slot_reply_numbered_and_fill():
    """Răspuns NUMEROTAT → fiecare câmp (inclusiv duplicatele) primește valoarea lui."""
    slots = ff.extract_slots(_ECHIV)
    reply = ("1=Cretu Crina, 2=Calculatoare, 3=3, 4=2025-2026, 5=Baze de Date, "
             "6=2, 7=ULBS, 8=Inginerie, 9=Informatica, 10=2, 11=2024-2025, 12=10")
    vals = ff.parse_slot_reply(reply, slots)
    assert ff.missing_slots(slots, vals) == []
    out = ff.fill_slots(_ECHIV, vals)
    # duplicatele completate cu valori DISTINCTE, nu cu aceeași
    assert "specializarea Calculatoare," in out
    assert "specializarea Informatica in anul de studii" in out
    assert "Facultatea de Inginerie," in out
    assert "Universitatea ULBS," in out
    assert "cu nota 10." in out                       # punctul final păstrat
    assert "anul de studii Calculatoare" not in out   # vechea eroare a dispărut


def test_parse_slot_reply_ordered_lines():
    """Răspuns în ORDINE (câte o valoare pe linie) pentru sloturile lipsă."""
    slots = ff.extract_slots("Subsemnatul/a ______, programul de studii ______, în anul______.")
    # 3 sloturi: nume, program, an
    assert len(slots) == 3
    vals = ff.parse_slot_reply("Ana Pop\nDrept\n2", slots)
    assert ff.missing_slots(slots, vals) == []
    out = ff.fill_slots("Subsemnatul/a ______, programul de studii ______, în anul______.", vals)
    assert "Ana Pop" in out and "Drept" in out


def test_merge_named_fills_first_empty_duplicate():
    """Pre-completarea pe nume umple PRIMUL slot liber cu acel nume; duplicatul rămâne."""
    slots = ff.extract_slots(_ECHIV)
    named = {ff.normalize("programul de studii"): "Calculatoare"}
    vals = ff.merge_named_into_slots(slots, {}, named)
    # doar prima „specializare" (index 2) e pre-completată; a doua (index 9) rămâne
    assert vals.get(2) == "Calculatoare"
    assert 9 not in vals


def test_slots_skip_signature_and_junk():
    """Semnătura/aprobarea/textul liber NU devin sloturi (doar câmpurile reale)."""
    tpl = (
        "Aprobat/Respins\nDomnule Decan\n"
        "Subsemnatul(a) , specializarea , va rog sa-mi aprobati ceva.\n"
        "Semnatura student\nData ______\nAprobat Director ______"
    )
    slots = ff.extract_slots(tpl)
    # exact 2 câmpuri reale: numele și specializarea; restul (semnătură/aprobare/
    # data) NU produc sloturi
    assert [s.friendly for s in slots] == ["numele și prenumele", "programul de studii"]


def test_fill_slots_name_inserted_after_student():
    tpl = "Subsemnatul(a) student(a)  la Facultatea de X, cu nota ."
    slots = ff.extract_slots(tpl)
    name_idx = next(s.index for s in slots if s.friendly == "numele și prenumele")
    nota_idx = next(s.index for s in slots if s.friendly == "nota")
    out = ff.fill_slots(tpl, {name_idx: "Ion Popescu", nota_idx: "9"})
    assert "student(a) Ion Popescu la Facultatea" in out
    assert "cu nota 9." in out
