"""
backend/core/deadlines.py
═════════════════════════
Detectarea termenelor limită (deadline-uri) din documente și generarea unui
link „Adaugă în Google Calendar" (varianta simplă, fără OAuth).

Flux:
  1. `is_deadline_question(q)`  — întrebarea e despre un termen?
  2. `find_deadline(text)`      — extrage data limită din context (RO: numerice
     „15.03.2026" sau textuale „15 martie 2026"), compară cu ziua curentă.
  3. `build_gcal_url(...)`      — link Google Calendar cu eveniment precompletat.

Nu stochează nimic și nu necesită cont Google — doar deschide Google Calendar
cu evenimentul gata completat; utilizatorul apasă Save.
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional, Tuple
from urllib.parse import quote_plus, urlencode


# ── Fold diacritice (păstrează lungimea, pentru poziții consistente) ──────────

_FOLD = str.maketrans("ăâîșțĂÂÎȘȚşţŞŢ", "aaistAAISTstST")


def _fold(text: str) -> str:
    return text.translate(_FOLD).lower()


# ── Detectarea intenției (întrebare despre termen) ────────────────────────────

_DEADLINE_KEYWORDS = (
    "termen", "deadline", "data limita", "data-limita", "data limită",
    "pana cand", "pana la", "scadent", "termen limita", "termen de depunere",
    "termen de predare", "expira", "expirare", "ultima zi", "limita de depunere",
    "se depun pana", "depunere pana", "se depune pana", "data depunerii",
    "data pana la care",
)


def is_deadline_question(question: str) -> bool:
    """True dacă întrebarea pare să fie despre un termen / deadline."""
    f = _fold(question)
    return any(k in f for k in _DEADLINE_KEYWORDS)


# ── Parsarea datelor (română) ─────────────────────────────────────────────────

_MONTHS = {
    "ianuarie": 1, "februarie": 2, "martie": 3, "aprilie": 4, "mai": 5,
    "iunie": 6, "iulie": 7, "august": 8, "septembrie": 9, "octombrie": 10,
    "noiembrie": 11, "decembrie": 12,
    "ian": 1, "feb": 2, "mar": 3, "apr": 4, "iun": 6, "iul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "noi": 11, "nov": 11, "dec": 12,
}

# 15.03.2026 / 15-3-26 / 15/03/2026
_NUM_DATE = re.compile(r"\b(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})\b")
# 15 martie 2026 / 30 aprilie (an opțional)
_TXT_DATE = re.compile(
    r"\b(\d{1,2})\s+([a-zăâîșț]+)\.?(?:\s+(\d{4}))?\b", re.IGNORECASE | re.UNICODE
)


@dataclass
class Deadline:
    date_obj: date
    display: str          # text prietenos, ex: „15 martie 2026"
    passed: bool
    snippet: str          # contextul în care a fost găsită


def _safe_date(y: int, m: int, d: int) -> Optional[date]:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _candidates(text: str, today: date) -> List[Tuple[date, int]]:
    """Returnează lista de (dată, poziție) găsite în text."""
    out: List[Tuple[date, int]] = []

    for m in _NUM_DATE.finditer(text):
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        dt = _safe_date(y, mo, d)
        if dt:
            out.append((dt, m.start()))

    folded = _fold(text)
    for m in _TXT_DATE.finditer(text):
        day = int(m.group(1))
        month_name = _fold(m.group(2))
        month = _MONTHS.get(month_name)
        if not month:
            continue
        year = int(m.group(3)) if m.group(3) else today.year
        dt = _safe_date(year, month, day)
        # dacă anul lipsea și data e deja trecută cu mult, presupunem anul următor
        if dt and m.group(3) is None and dt < today:
            nxt = _safe_date(year + 1, month, day)
            dt = nxt or dt
        if dt:
            out.append((dt, m.start()))

    return out


def find_deadline(text: str, today: Optional[date] = None) -> Optional[Deadline]:
    """
    Extrage termenul limită cel mai relevant din text (preferă datele aflate
    aproape de un cuvânt-cheie de tip „termen / până la / data limită").
    """
    if not text:
        return None
    today = today or date.today()

    cands = _candidates(text, today)
    if not cands:
        return None

    folded = _fold(text)
    kw_positions = []
    for k in _DEADLINE_KEYWORDS:
        start = 0
        while True:
            p = folded.find(k, start)
            if p < 0:
                break
            kw_positions.append(p)
            start = p + 1

    def _score(pos: int):
        """
        Preferă datele care apar DUPĂ un cuvânt-cheie (ex: „termenul … este DATA"),
        în limita a 90 de caractere. Altfel, cade pe distanța absolută.
        """
        if not kw_positions:
            return (1, 0)
        forward = [pos - kp for kp in kw_positions if 0 <= pos - kp <= 90]
        if forward:
            return (0, min(forward))            # după cuvânt-cheie → prioritar
        return (1, min(abs(pos - kp) for kp in kw_positions))

    # scor minim (după keyword > aproape de keyword); la egalitate, cea mai timpurie
    best = min(cands, key=lambda c: (_score(c[1]), c[0]))
    dt, pos = best

    snippet = text[max(0, pos - 40): pos + 40].replace("\n", " ").strip()
    return Deadline(
        date_obj=dt,
        display=_format_ro(dt),
        passed=dt < today,
        snippet=snippet,
    )


_MONTH_NAMES_RO = [
    "", "ianuarie", "februarie", "martie", "aprilie", "mai", "iunie", "iulie",
    "august", "septembrie", "octombrie", "noiembrie", "decembrie",
]


def _format_ro(d: date) -> str:
    return f"{d.day} {_MONTH_NAMES_RO[d.month]} {d.year}"


# ── Link Google Calendar (eveniment precompletat, fără OAuth) ─────────────────

def build_gcal_url(title: str, deadline_date: date, details: str = "") -> str:
    """
    Construiește un link Google Calendar cu un eveniment de o zi precompletat.
    Utilizatorul îl deschide și apasă Save — fără autentificare/OAuth.
    """
    start = deadline_date.strftime("%Y%m%d")
    end = (deadline_date + timedelta(days=1)).strftime("%Y%m%d")
    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": f"{start}/{end}",
        "details": details,
    }
    return "https://calendar.google.com/calendar/render?" + urlencode(
        params, quote_via=quote_plus
    )


_TITLE_STRIP = (
    "care e", "care este", "care sunt", "pana cand", "pana la care", "termenul de",
    "termenul", "termen de", "termen", "deadline", "data limita de", "data limita",
    "data pana la care", "se depune", "se depun", "?", "spune-mi", "spune mi",
    "imi spui", "vreau sa stiu", "as vrea sa stiu",
)


def suggest_title(question: str, source: Optional[str] = None) -> str:
    """Titlu sugestiv pentru evenimentul din calendar."""
    f = _fold(question).strip()
    for s in _TITLE_STRIP:
        f = f.replace(s, " ")
    subject = " ".join(f.split()).strip(" -.,")
    if len(subject) < 3 and source:
        subject = source.rsplit(".", 1)[0]
    subject = subject[:60] if subject else (source or "termen")
    return f"⏰ Termen limită: {subject}"
