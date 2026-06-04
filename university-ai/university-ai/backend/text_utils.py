"""
backend/text_utils.py
═════════════════════
Utilitare de normalizare a textului, partajate de retriever și de servicii.

Scopul principal: căutare INSENSIBILĂ LA DIACRITICE — utilizatorul găsește
aceeași informație fie că scrie „condiții" fie „conditii", „ședință" fie
„sedinta". Normalizarea se aplică identic la indexare și la interogare.
"""

import re
import unicodedata


def looks_repetitive(text: str) -> bool:
    """
    Detectează degenerarea unui model LLM care repetă aceeași propoziție la
    nesfârșit (apare ca o „buclă"). True dacă ultimele 3 propoziții sunt identice.
    """
    if len(text) < 300:
        return False
    tail = text[-800:]
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+|\n+", tail) if len(p.strip()) > 12]
    return len(parts) >= 3 and parts[-1] == parts[-2] == parts[-3]


def trim_repetition(text: str) -> str:
    """Elimină propozițiile identice repetate de la final, păstrând o singură copie."""
    parts = re.split(r"(?<=[.!?])\s+", text)
    while len(parts) >= 2 and parts[-1].strip() and parts[-1].strip() == parts[-2].strip():
        parts.pop()
    return " ".join(parts).strip()


_NO_ANSWER_MARKERS = (
    "nu am gasit", "nu am identificat", "nu exista informati", "nu se gaseste",
    "nu dispun de", "nu pot gasi", "nu am putut gasi", "nu am informati",
    "nu am gasit nicio", "nu am gasit informati", "nu este disponibil",
    "nu se regaseste", "nu apare in document", "consultati direct secretariat",
    "nu detin informati", "nu am date despre",
)


def looks_like_no_answer(text: str) -> bool:
    """
    True dacă răspunsul indică faptul că informația NU a fost găsită în documente
    (ex: „nu am găsit…", „vă recomand să consultați direct secretariatul").
    Folosit pentru a NU afișa surse când de fapt nu s-a găsit nimic relevant.
    """
    n = _norm_ascii_lower(text)
    return any(m in n for m in _NO_ANSWER_MARKERS)


def _norm_ascii_lower(text: str) -> str:
    """lower + fără diacritice (helper intern, evită import circular cu normalize)."""
    nfkd = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def strip_diacritics(text: str) -> str:
    """
    Elimină diacriticele dintr-un text (ă→a, â→a, î→i, ș→s, ț→t, plus variantele
    vechi cu sedilă ş/ţ). Folosește descompunere Unicode NFKD + eliminarea
    semnelor combinatorii — funcționează pentru orice limbă, nu doar română.
    """
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize(text: str) -> str:
    """Normalizare pentru comparații/căutare: lowercase + fără diacritice."""
    return strip_diacritics((text or "").lower()).strip()
