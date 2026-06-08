"""
backend/core/form_filler.py
═══════════════════════════
Completarea automată a cererilor/formularelor model din documentele încărcate.

Flux:
  1. Detectăm intenția de completare a unei cereri (is_form_request).
  2. Găsim șablonul potrivit printre documentele indexate (find_template).
  3. Reasamblăm textul integral al șablonului (get_full_document_text).
  4. LLM-ul: fie cere datele lipsă, fie completează cererea (build_form_prompt).
  5. Generăm un .docx descărcabil din cererea completată (generate_docx).

Notă: producem un .docx nou (text completat), nu modificăm fișierul original —
sistemul stochează doar textul documentelor, nu fișierele binare.
"""

import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from docx import Document

from backend.config import settings
from backend.logging_config import logger
from backend.text_utils import normalize


# ── Detectarea intenției ──────────────────────────────────────────────────────

# Verbe/expresii care semnalează cererea de a COMPLETA/GENERA un formular
_FORM_ACTIONS = [
    "completeaz", "completare", "genereaz", "generez", "intocmeste", "intocmesti",
    "redacteaz", "fa-mi", "fa mi", "fami", "creeaz", "scrie-mi", "scrie mi",
    "umple", "umpli", "vreau o cerere", "vreau o adeverinta", "vreau o declaratie",
    "vreau sa completez", "am nevoie de o cerere", "imi trebuie o cerere",
    "trebuie o cerere", "as vrea o cerere", "as avea nevoie de o cerere",
    "completeaza-mi", "completeaza mi",
]

# Substantive care indică un formular
_FORM_NOUNS = [
    "cerere", "cereri", "formular", "formulare", "adeverinta", "adeverinte",
    "declaratie", "declaratii", "cerere tip", "cerere model",
]

# Cuvinte generice de eliminat la potrivirea subiectului cererii
_GENERIC = {
    "cerere", "cereri", "formular", "formulare", "adeverinta", "declaratie",
    "model", "tip", "completeaza", "completeazami", "completare", "genereaza",
    "vreau", "o", "un", "pentru", "de", "la", "mi", "imi", "fami", "fa",
    "te", "rog", "as", "avea", "nevoie", "trebuie", "sa", "imi", "cu", "din",
    "documentul", "atasat", "vrea", "ma", "numesc", "este", "si",
}

# Cuvinte prin care utilizatorul renunță la completare
_CANCEL = ["renunt", "anuleaza", "anulez", "lasa", "opreste", "stop", "nu mai vreau"]


def is_form_request(question: str) -> bool:
    """True dacă utilizatorul cere completarea/generarea unei cereri sau formular."""
    qn = normalize(question)
    has_action = any(a in qn for a in _FORM_ACTIONS)
    has_noun = any(n in qn for n in _FORM_NOUNS)
    return has_action and has_noun


def is_cancel(question: str) -> bool:
    qn = normalize(question)
    return any(c in qn for c in _CANCEL)


# ── Identificarea șabloanelor de cerere ──────────────────────────────────────

_NAME_MARKERS = ("cerere", "formular", "declaratie", "adeverinta", "model")
_BODY_MARKERS = (
    "subsemnat", "subsemnata", "solicit", "va rog sa", "domnule rector",
    "domnule decan", "domnule director", "doamna rector", "semnatura",
    "prin prezenta", "va adresez",
)


def _looks_like_form(source: str, text: str) -> bool:
    """Heuristică: documentul pare a fi o cerere/formular model?"""
    src_n = normalize(source)
    if any(m in src_n for m in _NAME_MARKERS):
        return True
    body_n = normalize(text[:1500])
    return sum(1 for m in _BODY_MARKERS if m in body_n) >= 2


def list_form_templates(vector_store) -> dict:
    """Returnează {source: text_concatenat} pentru documentele care par cereri model."""
    docs = vector_store.get_all_documents()
    by_source: dict = {}
    for d in docs:
        by_source.setdefault(d["source"], []).append(d.get("text", ""))

    templates: dict = {}
    for src, parts in by_source.items():
        text = " ".join(parts)
        if _looks_like_form(src, text):
            templates[src] = text
    return templates


def find_template(vector_store, request: str) -> Tuple[Optional[str], List[str]]:
    """
    Găsește șablonul de cerere care corespunde cel mai bine cererii utilizatorului.

    Returnează (source_potrivit_sau_None, listă_șabloane_disponibile).
    """
    templates = list_form_templates(vector_store)
    available = sorted(templates.keys())
    if not templates:
        return None, []

    # Tokeni „de subiect" din cerere (fără cuvintele generice)
    req_tokens = {t for t in re.findall(r"\w+", normalize(request)) if t not in _GENERIC and len(t) > 2}

    best_src, best_score = None, 0
    for src, text in templates.items():
        hay = set(re.findall(r"\w+", normalize(src + " " + text[:1200])))
        score = len(req_tokens & hay)
        if score > best_score:
            best_src, best_score = src, score

    if best_score == 0:
        return None, available
    return best_src, available


def get_full_document_text(vector_store, source: str, max_chars: int = 8000) -> str:
    """Reasamblează textul integral al unui document (șablonul), ordonat și limitat."""
    chunks = vector_store.get_documents_by_source(source)
    text = "\n".join(c["text"] for c in chunks).strip()
    if len(text) > max_chars:
        text = text[:max_chars]
    return text


# ── Extragerea deterministă a locurilor goale din șablon ──────────────────────

# Locuri goale: runuri de „_", „.", sau „…"
_BLANK_RE = re.compile(r"_{2,}|\.{4,}|…+")

# Contexte care NU se completează de utilizator (le sărim).
# NU includem „decan/rector/director" deoarece apar în salut („Domnule Decan,")
# chiar înaintea primului câmp real de completat.
_SKIP_MARKERS = (
    "semnatura", "aprobat", "se completeaza de", "rezervat", "viza", "l.s",
)


def _is_skip_context(text: str) -> bool:
    n = normalize(text)
    return any(s in n for s in _SKIP_MARKERS)


def _clean_snippet(before: str) -> str:
    """Curăță textul dinaintea unui loc gol → o etichetă scurtă, lizibilă."""
    before = before.replace("\n", " ")
    before = _BLANK_RE.sub(" ", before)                  # scoatem alte locuri goale
    # păstrăm doar ultimul fragment (după ultimul punct/punct-virgulă/virgulă)
    before = re.split(r"[.;,]\s*", before)[-1]
    return " ".join(before.split()[-8:]).strip()


def extract_blank_contexts(template_text: str, max_blanks: int = 20) -> List[str]:
    """
    Extrage, DETERMINIST, locurile goale care trebuie completate într-un șablon.

    Returnează o listă de fragmente scurte de context, fiecare terminat cu „___",
    ex: „Subsemnatul/a ___", „la programul de studii ___", „Telefon: ___".
    Acestea constrâng LLM-ul să ceară/completeze DOAR câmpurile reale, nu acte
    inventate sau propoziții-declarație.
    """
    contexts: List[str] = []

    # 1) Locuri goale marcate (linii/puncte) — sunt aproape mereu câmpuri reale.
    # Sărim doar dacă ETICHETA IMEDIATĂ (ultimele cuvinte) e semnătură/aprobare.
    for m in _BLANK_RE.finditer(template_text):
        snippet = _clean_snippet(template_text[max(0, m.start() - 80):m.start()])
        if not snippet:
            continue
        immediate = " ".join(normalize(snippet).split()[-2:])
        if any(s in immediate for s in _SKIP_MARKERS):
            continue
        contexts.append(snippet + " ___")

    # 2) Etichete urmate de „:" la final de linie (ex: „Telefon :")
    for m in re.finditer(r"(?m)^\s*([^\n:]{2,40}):\s*$", template_text):
        label = m.group(1).strip()
        if _is_skip_context(label):
            continue
        contexts.append(label + ": ___")

    # Dedupe păstrând ordinea
    out, seen = [], set()
    for c in contexts:
        key = normalize(c)
        if key and key not in seen:
            seen.add(key)
            out.append(c)
    return out[:max_blanks]


# ── Câmpuri cu nume prietenos + extragere/completare deterministă ─────────────

def friendly_name(text: str) -> str:
    """Transformă contextul unui loc gol într-un nume de câmp scurt și clar."""
    n = normalize(text)
    if "subsemnat" in n or ("nume" in n and "prenume" in n) or "prenume" in n:
        return "numele și prenumele"
    if "specializ" in n or "program" in n:
        return "programul de studii"
    if "universitar" in n:                # „an universitar"
        return "anul universitar"
    if "universitat" in n:                # „Universitatea …" (instituția)
        return "universitatea (de proveniență)"
    if "disciplin" in n:
        return "disciplina"
    if "an de studiu" in n or "anul de studiu" in n or "anul de studii" in n \
            or "an de studii" in n or "anul" in n:
        return "anul de studiu"
    if "studi" in n:                      # „studii"/„studiu" (programul de studii)
        return "programul de studii"
    if "telefon" in n:
        return "numărul de telefon"
    if "cnp" in n:
        return "CNP"
    if "e-mail" in n or "email" in n:
        return "adresa de email"
    if "facultat" in n:
        return "facultatea"
    if "grupa" in n:
        return "grupa"
    if "domicili" in n or "adresa" in n:
        return "adresa de domiciliu"
    if "serie" in n or "seria" in n or "buletin" in n or "identitate" in n:
        return "seria și numărul actului de identitate"
    if "motiv" in n:
        return "motivul cererii"
    if ("nota" in n or "note" in n) and "promovare" not in n and "notare" not in n:
        return "nota"
    if n.strip() == "data" or n.endswith(" data"):
        return "data"
    words = [w for w in re.findall(r"[\wăâîșțĂÂÎȘȚ/]+", text) if w != "___"]
    return " ".join(words[-3:]).strip(" :,.") or "informația cerută"


# Câmpuri uzuale în cereri: (nume prietenos, regex pentru eticheta din șablon).
# Detecția se face după ETICHETĂ urmată de un SLOT GOL — funcționează atât pentru
# PDF (locuri goale cu „____") cât și pentru .docx (locuri goale cu spații/tab-uri).
_FIELD_SPECS = [
    ("numele și prenumele", r"subsemnat\w*(?:/-?a)?"),
    ("programul de studii", r"program(?:ul)?\s+de\s+studii|specializare(?:a)?"),
    ("anul de studiu", r"[îi]n\s+anul|an(?:ul)?\s+de\s+studi\w*"),
    ("numărul de telefon", r"telefon(?:ul)?"),
    ("CNP", r"cod\s+numeric\s+personal|\bc\.?n\.?p\.?\b"),
    ("adresa de email", r"adresa\s+de\s+e-?mail|e-?mail(?:ul)?"),
    ("grupa", r"\bgrupa\b"),
    ("seria și numărul actului de identitate", r"seria\s+și\s+(?:nr|num[ăa]rul)|carte\s+de\s+identitate"),
]

# Slotul gol care urmează unei etichete: spații, tab, underscore, puncte, colon
_SLOT = r"[ 	 _.…:]*"
# Slotul e GOL dacă imediat după el urmează un delimitator sau sfârșit de rând
_SLOT_END = r"(?=[,;.\n]|$)"


# Loc gol GENERIC într-un .docx: o etichetă (ultimul cuvânt) urmată de un spațiu/
# tab/newline chiar înainte de un delimitator (virgulă/punct) sau capăt de rând.
# Ex: „specializarea ,", „cu nota⇥.", „Universitatea ,", „disciplina⏎⏎,".
_GENERIC_BLANK = re.compile(
    r"([A-Za-zĂÂÎȘȚăâîșț()./\-]{3,})([ \t\xa0\n]+)(?=[,;.]|$)",
    re.UNICODE,
)

# Cuvinte care NU sunt câmpuri (verbe/conjuncții frecvente înaintea unui blank)
_NOT_A_FIELD = {
    "rog", "aprobati", "aprobă", "imi", "îmi", "sa", "să", "vă", "va", "si", "și",
    "cu", "la", "de", "in", "în", "pe", "pentru", "domnule", "doamna", "decan",
    "rector", "director", "semnatura", "semnătura", "data", "titular",
}

# Markeri care indică un nume de câmp FALS, provenit din zone de text liber,
# semnături, aprobări sau secțiuni administrative ale unei cereri. Aceste
# „câmpuri" nu pot fi completate de student (ex: „Solicit acesta deoarece ...",
# „Menționez că ...", „Mențiuni :", „Confirmare secretară/semnătura",
# „Semnătură student / Data"). Le respingem ca să NU cerem la nesfârșit date
# imposibile — formularul trebuie să se poată finaliza din câmpurile reale.
_JUNK_FIELD_MARKERS = (
    "semnatur", "aprobat", "respins", "mentiuni", "mentionez", "ionez",
    "tiuni", "confirmare", "secretar", "deoarece", "solicit", "viza",
    "rezervat", "se completeaza de", "informatia ceruta",
)


def _is_real_field(name: str) -> bool:
    """False dacă numele de câmp e gunoi (text liber/semnătură/aprobare/etc.)."""
    n = normalize(name)
    if not n:
        return False
    if any(m in n for m in _JUNK_FIELD_MARKERS):
        return False
    # Respinge fragmentele formate exclusiv din verbe/conjuncții (nu un câmp real)
    if all(w in _NOT_A_FIELD for w in n.split()):
        return False
    return True


def extract_field_names(template_text: str) -> List[str]:
    """
    Lista câmpurilor de completat. Combină:
      • câmpurile cunoscute (nume frumoase) din _FIELD_SPECS;
      • detectarea GENERICĂ a locurilor goale (orice etichetă urmată de un spațiu
        gol înainte de virgulă/punct) — ca să găsească și câmpuri din șabloane noi
        (disciplină, notă, universitate etc.), nu doar pe cele predefinite.
    """
    names: List[str] = []
    seen = set()

    def _add(name: str):
        key = normalize(name)
        if key and key not in seen and _is_real_field(name):
            seen.add(key)
            names.append(name)

    # 0) Orice cerere care începe cu „Subsemnatul…" are nevoie de numele petentului,
    #    chiar dacă nu există un loc gol explicit lângă el.
    if re.search(r"(?i)subsemnat", template_text):
        _add("numele și prenumele")

    # 1) Câmpuri cunoscute (nume prietenoase)
    for name, pat in _FIELD_SPECS:
        rx = re.compile(rf"(?i)(?:{pat}){_SLOT}{_SLOT_END}", re.UNICODE)
        if rx.search(template_text):
            _add(name)

    # 2) Locuri goale generice (etichetă + spațiu gol înainte de delimitator)
    for m in _GENERIC_BLANK.finditer(template_text):
        label = m.group(1)
        if normalize(label) in _NOT_A_FIELD:
            continue
        _add(friendly_name(label))

    # 3) Locuri goale cu underscore/puncte (PDF)
    for ctx in extract_blank_contexts(template_text):
        _add(friendly_name(ctx))

    return names


# ── Extragere DETERMINISTĂ în cod (robustă pentru intrări explicite) ──────────

def _field_type(name: str) -> Optional[str]:
    n = normalize(name)
    if "nume" in n or "prenume" in n:
        return "name"
    if "program" in n or "specializ" in n:
        return "program"
    if "universitar" in n:        # „anul universitar" (interval, ex 2024-2025) → LLM
        return None
    if "anul" in n or "an de studiu" in n:
        return "year"
    if "telefon" in n:
        return "phone"
    if "cnp" in n:
        return "cnp"
    if "email" in n:
        return "email"
    if "facultat" in n:
        return "faculty"
    if "grupa" in n:
        return "group"
    if "data" in n:
        return "date"
    return None


# stop la delimitatori sau înaintea altui câmp
_STOP = (
    r"(?=$|[,.;\n]|\s+(?:nume|numele|prenume|prenumele|program|programul|"
    r"specializare|anul|telefon|telefonul|data|cnp|e-?mail|facultate|facultatea|"
    r"grupa|matricol|num[ăa]r|nr|si\b|și\b|semnatura|semnătura))"
)

_TEXT_VAL = r"([^\n,.;]+?)" + _STOP

_EXTRACTORS = {
    "name":    (r"nume(?:le)?(?:\s+(?:si|și)\s+prenume(?:le)?)?(?:\s+meu)?|prenume(?:le)?|m[ăa]\s+numesc|subsemnat\w*", _TEXT_VAL),
    "program": (r"program\w*(?:\s+de\s+studii)?|specializare\w*", _TEXT_VAL),
    "year":    (r"an(?:ul)?\b(?:\s+de\s+studiu)?", r"([IVX]{1,4}|\d{1,2})"),
    "phone":   (r"telefon\w*|num[ăa]r\w*\s+de\s+telefon", r"([\d][\d\s.\-+/]{5,}\d)"),
    "date":    (r"data\b", r"(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4})"),
    "cnp":     (r"cnp\b", r"(\d{13})"),
    "email":   (r"e-?mail\w*|adresa\s+de\s+e-?mail", r"([\w.\-]+@[\w.\-]+\.\w+)"),
    "faculty": (r"facultat\w*", _TEXT_VAL),
    "group":   (r"grupa\b", r"([\w.\-]+)"),
}


def _trim_value(val: str, ftype: str) -> str:
    val = val.strip(" :.,-")
    if ftype in ("name", "program", "faculty"):
        # păstrăm primele câteva cuvinte semnificative
        val = " ".join(val.split()[:5]).strip(" :.,-")
    return val


def extract_values_code(field_names: List[str], user_text: str) -> dict:
    """
    Extrage valorile câmpurilor direct din text (regex), pentru formulări
    explicite de tip „numele meu este X", „programul de studii este Y",
    „anul este 3", „telefon: 0712...". Mult mai fiabil decât LLM-ul pentru
    intrări clare. Returnează {normalize(nume): valoare}.
    """
    values: dict = {}
    for name in field_names:
        ftype = _field_type(name)
        if not ftype or ftype not in _EXTRACTORS:
            continue
        trigger, value_pat = _EXTRACTORS[ftype]
        pat = re.compile(
            rf"(?:{trigger})\s*(?:este|e|sunt|:|=)?\s*:?\s*{value_pat}",
            re.IGNORECASE | re.UNICODE,
        )
        m = pat.search(user_text)
        if m and m.group(1).strip():
            values[normalize(name)] = _trim_value(m.group(1), ftype)
    return values


def build_extract_prompt(field_names: List[str], user_data: str) -> str:
    """Prompt simplu de EXTRAGERE a valorilor (sarcină ușoară pentru LLM)."""
    fields_block = "\n".join(f"- {f}" for f in field_names)
    return (
        "Ești un asistent care extrage date pentru completarea unei cereri.\n"
        "Mai jos sunt CÂMPURILE necesare și DATELE oferite de utilizator.\n"
        "Pentru FIECARE câmp, extrage valoarea EXACTĂ din datele utilizatorului.\n"
        "Dacă o valoare nu a fost oferită, scrie exact LIPSA.\n"
        "Răspunde STRICT cu câte o linie per câmp, în formatul:  câmp = valoare\n"
        "Nu adăuga explicații sau alt text.\n\n"
        "CÂMPURI:\n" + fields_block +
        "\n\nDATE OFERITE DE UTILIZATOR:\n" + user_data +
        "\n\nRĂSPUNS (o linie per câmp):\n"
    )


_EMPTY_VALUES = {"lipsa", "", "n/a", "na", "-", "necunoscut", "nespecificat", "none"}


def parse_extraction(resp: str, field_names: List[str]) -> dict:
    """Parsează liniile „câmp = valoare" → {normalize(nume): valoare_sau_None}."""
    norm_to_name = {normalize(f): f for f in field_names}
    values: dict = {}
    for line in (resp or "").splitlines():
        if "=" not in line:
            continue
        left, right = line.split("=", 1)
        left_n = normalize(left.strip().lstrip("-*•").strip())
        val = right.strip()
        matched = norm_to_name.get(left_n)
        if not matched:
            for fn_norm, fn in norm_to_name.items():
                if fn_norm and (fn_norm in left_n or left_n in fn_norm):
                    matched = fn
                    break
        if not matched:
            continue
        values[normalize(matched)] = None if normalize(val) in _EMPTY_VALUES else val
    return values


def missing_fields(field_names: List[str], values: dict) -> List[str]:
    """Câmpurile fără valoare extrasă."""
    return [f for f in field_names if not values.get(normalize(f))]


def fill_template(template_text: str, values: dict) -> str:
    """
    Completează DETERMINIST șablonul: pentru fiecare câmp cu valoare, inserează
    valoarea în locul gol care urmează etichetei (păstrând eticheta și separatorul).
    Funcționează pentru locuri goale cu „____" (PDF) sau cu spații/tab-uri (.docx).
    """
    filled = template_text
    for name, pat in _FIELD_SPECS:
        val = values.get(normalize(name))
        if not val:
            continue
        rx = re.compile(rf"(?i)((?:{pat}){_SLOT}){_SLOT_END}", re.UNICODE)

        def _repl(m, _val=val):
            label = m.group(1).rstrip(" _.…\t")   # eticheta (+ eventual „:")
            sep = " " if not label.endswith(":") else " "
            return f"{label}{sep}{_val}"

        filled = rx.sub(_repl, filled, count=1)

    # Completare GENERICĂ a locurilor goale rămase (câmpuri din șabloane noi:
    # disciplină, notă, universitate etc.) — inserăm valoarea după etichetă.
    def _repl_generic(m):
        label, gap = m.group(1), m.group(2)
        if normalize(label) in _NOT_A_FIELD:
            return m.group(0)
        val = values.get(normalize(friendly_name(label)))
        # păstrăm gap-ul (inclusiv newline-urile) ca structura paragrafelor să rămână
        return f"{label} {val}{gap}" if val else m.group(0)

    filled = _GENERIC_BLANK.sub(_repl_generic, filled)

    # Numele petentului din „Subsemnatul(a) student(a) ___" (când nu există slot)
    name_val = values.get(normalize("numele și prenumele"))
    if name_val:
        filled = re.sub(
            r"(?i)(subsemnat\w*(?:\([aăAĂ]\))?\s+student\w*(?:\([aăAĂ]\))?)(\s+)(?=[a-zăâîșț])",
            lambda m: f"{m.group(1)} {name_val}{m.group(2)}", filled, count=1,
        )

    # Curățare cosmetică: spații multiple → unul; fără spațiu înainte de virgulă/punct
    filled = re.sub(r"[ \t]{2,}", " ", filled)
    filled = re.sub(r"[ \t]+([,.;])", r"\1", filled)
    return filled


# ══════════════════════════════════════════════════════════════════════════════
#  SLOT-URI POZIȚIONALE — completare numerotată, păstrând câmpurile DUPLICATE
# ══════════════════════════════════════════════════════════════════════════════
# Spre deosebire de `extract_field_names` (care DEDUPLICĂ pe nume), aici păstrăm
# FIECARE apariție a unui câmp ca slot separat, în ordinea din document. Astfel o
# cerere de echivalare cu „specializarea" de două ori (a ta + cea de proveniență)
# sau „anul de studii" de mai multe ori produce câte un slot pentru fiecare → le
# cerem pe TOATE (numerotat) și le completăm POZIȚIONAL, nu o singură dată.

@dataclass
class Slot:
    """Un loc gol din șablon (o apariție; duplicatele NU se contopesc)."""
    index: int          # 1-based, pentru afișare/numerotare
    friendly: str       # nume prietenos (poate fi non-unic între sloturi)
    context: str        # frază scurtă cu „⟦__⟧" pe poziția slotului (dezambiguizare)
    is_name: bool = False


# Etichete de câmp (ordonate). Fiecare APARIȚIE urmată de un slot gol = un Slot.
# Sunt mai permisive decât _FIELD_SPECS: prind și câmpuri repetate / „Facultatea de".
_LABEL_FRIENDLY: List[Tuple[str, str]] = [
    ("programul de studii", r"specializare\w*|program(?:ul)?\s+de\s+studii"),
    # „anul de studii" SAU forma scurtă „în anul ___" (fără „de studii"); NU „an universitar"
    ("anul de studiu",      r"[îi]n\s+anul(?:\s+de\s+studi\w*)?|an(?:ul)?\s+de\s+studi\w*"),
    ("anul universitar",    r"an(?:ul)?\s+universitar"),
    ("disciplina",          r"disciplin\w*"),
    ("universitatea (de proveniență)", r"universita(?:te\w*|tii)"),
    ("facultatea",          r"facultat\w*(?:\s+de)?"),
    ("nota",                r"\bnota\b"),
    ("numărul de telefon",  r"telefon\w*"),
    ("CNP",                 r"cod\s+numeric\s+personal|\bc\.?n\.?p\.?\b"),
    ("adresa de email",     r"adresa\s+de\s+e-?mail|e-?mail\w*"),
    ("grupa",               r"\bgrupa\b"),
    ("adresa de domiciliu", r"domicili\w*"),
    ("seria și numărul actului de identitate", r"seria\s+(?:și|si)\s+(?:nr|num[ăa]rul)"),
]

_LABEL_RE = re.compile(
    "(?i)(?:"
    + "|".join(f"(?P<g{i}>{pat})" for i, (_, pat) in enumerate(_LABEL_FRIENDLY))
    + ")",
    re.UNICODE,
)

# Consumă un loc gol: spații/tab/nbsp/„:" ȘI runuri de marcaje („____", „....", „…").
# NU consumăm un punct SINGUR (e sfârșit de propoziție, nu loc gol) — doar 4+ puncte.
_SLOT_CONSUME = re.compile(r"(?:[ \t\xa0:]+|_{2,}|\.{4,}|…+)*")
_SLOT_MARKER_RE = re.compile(r"_{2,}|\.{4,}|…+")


def _label_friendly_for(match: "re.Match") -> Optional[str]:
    """Numele prietenos al grupului care a făcut potrivirea în _LABEL_RE."""
    for name, val in match.groupdict().items():
        if val is not None and name.startswith("g"):
            return _LABEL_FRIENDLY[int(name[1:])][0]
    return None


def _slot_is_empty(text: str, j: int) -> bool:
    """True dacă, după spațiile/markerii consumați (poziția j), urmează un
    delimitator, capăt de rând sau ÎNCEPUTUL altei etichete → slotul e necompletat
    (în șablonul gol). Așa deosebim „specializarea ⟦gol⟧ în anul…" (urmează altă
    etichetă) de „Facultatea de Medicină" (urmează un cuvânt obișnuit = deja scris)."""
    if j >= len(text):
        return True
    if text[j] in ",;.\n":
        return True
    return bool(_LABEL_RE.match(text, j))


def _context_phrase(text: str, start: int, slot_end: int) -> str:
    """Frază scurtă cu „⟦__⟧" pe poziția slotului — ajută la dezambiguizarea
    câmpurilor duplicate la afișare (ex: „…specializarea ⟦__⟧ în anul de studii…")."""
    pre = " ".join(text[max(0, start - 55):slot_end].replace("\n", " ").split()[-6:])
    post = " ".join(text[slot_end:slot_end + 45].replace("\n", " ").split()[:3])
    pre = _BLANK_RE.sub(" ", pre).strip()
    out = f"…{pre} ⟦__⟧"
    if post:
        out += f" {_BLANK_RE.sub(' ', post).strip()}…"
    return " ".join(out.split())


def _scan_slots(template_text: str) -> List[dict]:
    """Scanare DETERMINISTĂ a locurilor goale (cu poziții), păstrând ordinea și
    duplicatele. Folosită identic de `extract_slots` (afișare) și `fill_slots`
    (completare) → ordinea/numerotarea coincid mereu."""
    raw: List[dict] = []

    # 1) Numele petentului („Subsemnatul…") — slot special, fără etichetă-slot clasică.
    mname = re.search(r"(?i)subsemnat\w*", template_text)
    if mname:
        raw.append({
            "pos": mname.start(), "friendly": "numele și prenumele",
            "context": _context_phrase(template_text, mname.start(), mname.end()),
            "is_name": True, "slot_start": mname.start(), "slot_end": mname.end(),
        })

    # 2) Sloturi pe etichete (fiecare apariție cu loc gol).
    for m in _LABEL_RE.finditer(template_text):
        friendly = _label_friendly_for(m)
        if not friendly:
            continue
        j = _SLOT_CONSUME.match(template_text, m.end()).end()
        gap = template_text[m.end():j]
        has_marker = bool(_SLOT_MARKER_RE.search(gap))
        if not (has_marker or _slot_is_empty(template_text, j)):
            continue   # eticheta e urmată de text real (câmp deja scris în șablon)
        around = template_text[max(0, m.start() - 30):j]
        if _is_skip_context(around) or not _is_real_field(friendly):
            continue
        raw.append({
            "pos": m.start(), "friendly": friendly,
            "context": _context_phrase(template_text, m.start(), j),
            "is_name": False, "slot_start": m.end(), "slot_end": j,
        })

    # 3) Ordonăm după poziție și eliminăm potriviri suprapuse (păstrând prima).
    raw.sort(key=lambda d: d["pos"])
    out, last_end = [], -1
    for d in raw:
        if d["pos"] < last_end:
            continue
        out.append(d)
        last_end = max(d["slot_end"], d["pos"])
    return out


def extract_slots(template_text: str) -> List[Slot]:
    """Lista locurilor goale ca sloturi numerotate (1-based), în ordinea din
    document, PĂSTRÂND duplicatele. Pentru completarea numerotată/pozițională."""
    return [
        Slot(index=i, friendly=d["friendly"], context=d["context"],
             is_name=d["is_name"])
        for i, d in enumerate(_scan_slots(template_text), 1)
    ]


def missing_slots(slots: List[Slot], values: Dict[int, str]) -> List[Slot]:
    """Sloturile fără valoare (cheie = index 1-based)."""
    return [s for s in slots if not (values.get(s.index) or "").strip()]


def merge_named_into_slots(slots: List[Slot], values: Dict[int, str],
                           named: Dict[str, str]) -> Dict[int, str]:
    """Pre-completează comod: pune fiecare valoare extrasă pe nume (ex. din regex/
    LLM) în PRIMUL slot liber cu același nume prietenos. Pentru câmpuri duplicate,
    doar prima apariție e pre-completată; restul rămân de cerut (numerotat) — ca să
    nu punem aceeași valoare în toate duplicatele."""
    # numele prietenoase care au deja o valoare (nu le re-atingem)
    used = {normalize(s.friendly) for s in slots if (values.get(s.index) or "").strip()}
    for s in slots:
        key = normalize(s.friendly)
        if (values.get(s.index) or "").strip() or key in used:
            continue
        val = named.get(key)
        if val:
            values[s.index] = val
            used.add(key)   # restul duplicatelor cu același nume rămân de cerut
    return values


# Separatori „N=…" / „N:…" → spargem și pe virgulă când urmează „cifră="
_NUMBERED_SPLIT = re.compile(r"[,;]\s*(?=\d{1,2}\s*[=:).\-])")
_NUMBERED_LINE = re.compile(r"^\s*(\d{1,2})\s*[=:).\-]\s*(.+)$")


def parse_slot_reply(reply: str, slots: List[Slot],
                     existing: Optional[Dict[int, str]] = None) -> Dict[int, str]:
    """
    Mapează răspunsul utilizatorului la indici de slot. Acceptă:
      • numerotat: „3=2", „3: Informatică", „7) 10", „3. X" (mai multe pe linie,
        separate cu virgulă/punct-virgulă/linie nouă);
      • în ordine: câte o valoare pe linie, atribuite sloturilor încă goale.
    Returnează {index: valoare} (cumulând peste `existing`).
    """
    values: Dict[int, str] = dict(existing or {})
    text = _NUMBERED_SPLIT.sub("\n", reply or "")

    found_numbered = False
    for line in text.splitlines():
        m = _NUMBERED_LINE.match(line)
        if m:
            idx = int(m.group(1))
            val = m.group(2).strip(" .,-_")
            if 1 <= idx <= len(slots) and val:
                values[idx] = val
                found_numbered = True
    if found_numbered:
        return values

    # Fallback: valori în ORDINE, pentru sloturile rămase goale.
    missing = [s.index for s in slots if not (values.get(s.index) or "").strip()]
    # întâi pe linii (câte o valoare pe linie); reținem doar liniile „scurte"
    # (valori, nu propoziții/întrebări) ca să nu confundăm alt mesaj cu un răspuns.
    lines = [l.strip(" .,-_") for l in (reply or "").splitlines() if l.strip()]
    lines = [l for l in lines if len(l.split()) <= 10]
    if len(lines) >= 2 and len(lines) <= len(missing):
        for idx, val in zip(missing, lines):
            values[idx] = val
        return values
    # apoi o singură linie cu valori separate prin virgulă, dacă numărul se potrivește
    if len(lines) == 1:
        parts = [p.strip(" .,-_") for p in lines[0].split(",") if p.strip()]
        if len(parts) >= 2 and len(parts) <= len(missing):
            for idx, val in zip(missing, parts):
                values[idx] = val
            return values
        # un singur câmp lipsă + un singur răspuns scurt → îl punem acolo
        if len(missing) == 1 and len(parts) == 1:
            values[missing[0]] = parts[0]
    return values


def _insert_name(text: str, name: str) -> str:
    """Inserează numele în cererile cu „Subsemnatul…", indiferent de forma slotului."""
    # a) slot cu underscore/puncte imediat după „Subsemnatul/a"
    rx1 = re.compile(r"(?i)(subsemnat\w*(?:\s*/\s*-?a|\([aă]\))?)(\s*[_.…]{2,}\s*)")
    if rx1.search(text):
        return rx1.sub(lambda m: f"{m.group(1)} {name} ", text, count=1)
    # b) după „student(a)" (fără slot vizibil)
    rx2 = re.compile(
        r"(?i)(subsemnat\w*(?:\([aă]\))?\s+student\w*(?:\([aă]\))?)(\s+)(?=[a-zăâîșțA-ZĂÂÎȘȚ])"
    )
    if rx2.search(text):
        return rx2.sub(lambda m: f"{m.group(1)} {name}{m.group(2)}", text, count=1)
    # c) imediat după „Subsemnatul(a)"
    rx3 = re.compile(r"(?i)(subsemnat\w*(?:\([aă]\))?)(\s+)(?=[a-zăâîșț])")
    return rx3.sub(lambda m: f"{m.group(1)} {name}{m.group(2)}", text, count=1)


def fill_slots(template_text: str, values: Dict[int, str]) -> str:
    """Completează șablonul POZIȚIONAL: fiecare slot (după index 1-based) primește
    valoarea lui. Câmpurile duplicate sunt completate independent (nu cu aceeași
    valoare). Numele se inserează prin `_insert_name`."""
    scanned = _scan_slots(template_text)
    result = template_text
    # Dreapta → stânga, ca pozițiile celorlalte sloturi să rămână valide.
    for i in range(len(scanned) - 1, -1, -1):
        s = scanned[i]
        if s["is_name"]:
            continue
        val = (values.get(i + 1) or "").strip()
        if not val:
            continue
        # Spațiu și înainte, și după valoare; curățarea cosmetică de la final
        # colapsează spațiile duble și scoate spațiul dinaintea unui delimitator.
        result = result[:s["slot_start"]] + " " + val + " " + result[s["slot_end"]:]

    # Numele (după ce restul e completat; pozițiile name sunt la început).
    name_idx = next((i + 1 for i, s in enumerate(scanned) if s["is_name"]), None)
    if name_idx and (values.get(name_idx) or "").strip():
        result = _insert_name(result, values[name_idx].strip())

    # Curățare cosmetică: spații multiple → unul; fără spațiu înainte de delimitator.
    result = re.sub(r"[ \t]{2,}", " ", result)
    result = re.sub(r"[ \t]+([,;.])", r"\1", result)
    return result


def fill_docx_in_place_slots(docx_bytes: bytes, values: Dict[int, str]) -> bytes:
    """Ca `fill_docx_in_place`, dar pe baza sloturilor poziționale (păstrând
    layout-ul). Completăm pe textul ÎMBINAT al paragrafelor (sloturile pot trece
    dintr-un paragraf în altul) și redistribuim pe paragrafe după newline-uri."""
    doc = Document(BytesIO(docx_bytes))

    def _set_text(p, new_text):
        if new_text == p.text:
            return
        if p.runs:
            p.runs[0].text = new_text
            for r in p.runs[1:]:
                r.text = ""
        else:
            p.add_run(new_text)

    paras = list(doc.paragraphs)
    joined = "\n".join(p.text for p in paras)
    filled = fill_slots(joined, values)
    segments = filled.split("\n")
    if len(segments) == len(paras):
        for p, seg in zip(paras, segments):
            _set_text(p, seg)
    else:
        # structura nu se mai potrivește → completăm tot în primul paragraf gol-sigur
        for p in paras:
            _set_text(p, fill_slots(p.text, values))

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    _set_text(p, fill_slots(p.text, values))

    out = BytesIO()
    doc.save(out)
    return out.getvalue()


def generate_filled_document_slots(source: str, template_text: str,
                                   values: Dict[int, str]) -> Tuple[bytes, str, bool]:
    """Ca `generate_filled_document`, dar pe baza sloturilor poziționale.
    Returnează (bytes, nume_fișier, layout_păstrat)."""
    try:
        original = settings.originals_folder_abs / Path(source).name
        if original.suffix.lower() == ".docx" and original.exists():
            filled = fill_docx_in_place_slots(original.read_bytes(), values)
            return filled, docx_filename(source), True
    except Exception:
        logger.exception("Completarea în loc a .docx (sloturi) a eșuat; fallback text")

    filled_text = fill_slots(template_text, values)
    return generate_docx(filled_text), docx_filename(source), False


# ── Prompt LLM (vechi — păstrat pentru compatibilitate) ───────────────────────

FORM_SYSTEM = '''Ești un asistent care completează cereri și formulare oficiale ale universității, în limba română.

Primești ȘABLONUL cererii, LISTA LOCURILOR GOALE de completat (extrasă automat) și DATELE oferite de utilizator.

REGULI STRICTE:
1. Câmpurile de completat sunt EXACT cele din lista „LOCURI GOALE" de mai jos — NIMIC în plus. Fiecare loc gol corespunde unei singure informații (ex: „Subsemnatul/a ___" = numele și prenumele; „la programul de studii ___" = programul de studii; „în anul ___" = anul de studiu; „Telefon: ___" = numărul de telefon).
2. Cere DOAR datele pentru aceste locuri goale. NU cere NICIODATĂ acte, documente justificative, copii, adeverințe, CV, certificate, dovezi, numere matricole sau taxe — decât dacă apar EXPLICIT ca loc gol în listă.
3. Propozițiile-declarație din șablon (ex: „Mă oblig să achit taxa...") NU sunt câmpuri de completat. Antetul, „Nr. /", „Semnătura", „Aprobat Director" NU se completează de utilizator.
4. IGNORĂ orice cunoștințe generale despre ce s-ar cere „de obicei". Dacă nu e în lista de locuri goale, NU îl ceri.
5. NU inventa date. Folosește exclusiv ce a oferit utilizatorul.

RĂSPUNDE STRICT în unul din cele două formate:

• Dacă LIPSESC date pentru locurile goale — prima linie să fie EXACT cuvântul:
LIPSESC
apoi o listă cu fiecare informație lipsă (câte una pe linie, cu „- "), exprimată prietenos (ex: „- numele și prenumele"), apoi o frază politicoasă prin care le ceri.

• Dacă ai TOATE datele pentru locurile goale — prima linie să fie EXACT cuvântul:
COMPLET
apoi textul INTEGRAL al cererii, cu fiecare loc gol înlocuit cu data corespunzătoare, păstrând formularea oficială.'''


def build_form_prompt(template_text: str, user_data: str,
                      blank_contexts: Optional[List[str]] = None) -> str:
    """Construiește promptul de completare a cererii, cu lista explicită de locuri goale."""
    if blank_contexts:
        blanks_block = "\n".join(f"{i}. {c}" for i, c in enumerate(blank_contexts, 1))
    else:
        blanks_block = "(nu s-au putut detecta automat — deduce-le din șablon)"

    return (
        FORM_SYSTEM
        + "\n\n═══ LOCURI GOALE DE COMPLETAT (DOAR acestea) ═══\n"
        + blanks_block
        + "\n\n═══ ȘABLON CERERE (pentru context) ═══\n"
        + template_text
        + "\n\n═══ DATE OFERITE DE UTILIZATOR ═══\n"
        + user_data
        + "\n\n═══ RĂSPUNSUL TĂU (începe musai cu LIPSESC sau COMPLET) ═══\n"
    )


def parse_form_response(text: str) -> Tuple[str, str]:
    """
    Interpretează răspunsul LLM-ului.

    Returnează (status, body):
      • status = "complete" → body = textul cererii completate
      • status = "missing"  → body = lista/întrebarea cu datele lipsă
      • status = "unknown"  → body = textul brut (tratat ca „missing" la nivel UI)
    """
    t = (text or "").strip()
    head = normalize(t[:30])
    if head.startswith("complet"):
        body = re.sub(r"(?is)^\s*complet[a-zăâîșt]*[:\-\s]*", "", t, count=1).strip()
        return "complete", body
    if head.startswith("lipsesc") or "lipsesc" in head:
        body = re.sub(r"(?is)^\s*lipsesc[:\-\s]*", "", t, count=1).strip()
        return "missing", body
    return "unknown", t


# ── Generare .docx ──────────────────────────────────────────────────────────

def generate_docx(text: str) -> bytes:
    """Creează un fișier .docx din textul cererii completate și returnează bytes."""
    doc = Document()
    for raw_line in text.split("\n"):
        doc.add_paragraph(raw_line.rstrip())
    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def docx_filename(source: str) -> str:
    """Nume de fișier prietenos pentru cererea completată."""
    base = Path(source).stem if source else "cerere"
    base = re.sub(r"[^\w\-]+", "_", base).strip("_") or "cerere"
    return f"{base}_completat.docx"


def fill_docx_in_place(docx_bytes: bytes, values: dict) -> bytes:
    """
    Completează un șablon .docx ÎN LOC, păstrând layout-ul original (antet,
    aliniere, font). Înlocuiește locurile goale din fiecare paragraf și celulă
    de tabel, păstrând formatarea primului run.
    """
    doc = Document(BytesIO(docx_bytes))

    def _set_text(p, new_text):
        if new_text == p.text:
            return
        if p.runs:
            p.runs[0].text = new_text
            for r in p.runs[1:]:
                r.text = ""
        else:
            p.add_run(new_text)

    # Corpul documentului: completăm pe textul ÎMBINAT al paragrafelor, ca să
    # prindem locurile goale care trec dintr-un paragraf în altul (ex: „disciplina"
    # la final de paragraf, virgula în paragraful următor). fill_template păstrează
    # newline-urile, deci numărul de paragrafe rămâne neschimbat.
    paras = list(doc.paragraphs)
    joined = "\n".join(p.text for p in paras)
    filled_joined = fill_template(joined, values)
    segments = filled_joined.split("\n")
    if len(segments) == len(paras):
        for p, seg in zip(paras, segments):
            _set_text(p, seg)
    else:
        # siguranță: dacă structura nu se mai potrivește, completăm paragraf-cu-paragraf
        for p in paras:
            _set_text(p, fill_template(p.text, values))

    # Tabele: completăm pe celule
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    _set_text(p, fill_template(p.text, values))

    out = BytesIO()
    doc.save(out)
    return out.getvalue()


def generate_filled_document(source: str, template_text: str, values: dict) -> Tuple[bytes, str, bool]:
    """
    Produce documentul completat.

    Dacă originalul e un .docx → îl completează în loc (LAYOUT PĂSTRAT).
    Altfel (PDF/TXT) → generează un .docx din text (layout simplu).

    Returnează (bytes, nume_fisier, layout_pastrat).
    """
    try:
        original = settings.originals_folder_abs / Path(source).name
        if original.suffix.lower() == ".docx" and original.exists():
            filled = fill_docx_in_place(original.read_bytes(), values)
            return filled, docx_filename(source), True
    except Exception:
        logger.exception("Completarea în loc a .docx a eșuat; folosesc fallback text")

    filled_text = fill_template(template_text, values)
    return generate_docx(filled_text), docx_filename(source), False
