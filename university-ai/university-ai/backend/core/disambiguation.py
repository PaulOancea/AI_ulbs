"""
backend/core/disambiguation.py
══════════════════════════════
Detectarea întrebărilor AMBIGUE: când utilizatorul întreabă generic despre un
concept care are mai multe TIPURI în documente (ex: „bursa" — există bursă
socială, de merit, doctorală…), chatbotul ar trebui să întrebe întâi „despre
care tip?" în loc să răspundă amestecat.

Descoperire DINAMICĂ: scanăm documentele pentru colocații „concept + calificator"
(ex: „bursă socială", „burse doctorale", „taxă de școlarizare") și păstrăm doar
calificatorii dintr-un vocabular cunoscut (ca să evităm zgomot precum „bursa pot
fi…"). Astfel găsim toate tipurile prezente, nu o listă fixă.

Totul e pe bază de text (regex), fără LLM — rapid și predictibil.
"""

import re
from typing import List, Optional, Tuple

from backend.text_utils import normalize


# Fiecare concept: cuvântul generic + {stem_calificator: etichetă_afișată}.
# Tiparele sunt ASCII (textul e normalizat: litere mici, fără diacritice).
_CONCEPTS = [
    {
        "label": "bursă",
        "concept": r"burs\w*",
        "qualifiers": {
            "social": "bursă socială / de ajutor social",
            "ajutor": "bursă socială / de ajutor social",
            "merit": "bursă de merit",
            "performant": "bursă de performanță",
            "studiu": "bursă de studiu",
            "studi": "bursă de studiu",
            "excelent": "bursă de excelență",
            "special": "bursă specială",
            "doctoral": "bursă doctorală",
            "doctorat": "bursă doctorală",
            "olimpic": "bursă pentru olimpici",
            "sportiv": "bursă sportivă",
            "mobilitat": "bursă pentru mobilitate (Erasmus)",
            "erasmus": "bursă pentru mobilitate (Erasmus)",
        },
        # stems care pot apărea oriunde în text (nu doar lipit de concept)
        "distinctive": {"erasmus", "mobilitat"},
    },
    {
        "label": "taxă",
        "concept": r"tax\w*",
        "qualifiers": {
            "scolariz": "taxă de școlarizare",
            "inmatricul": "taxă de înmatriculare",
            "reinmatricul": "taxă de reînmatriculare",
            "cazare": "taxă de cazare",
            "admitere": "taxă de admitere",
        },
        "distinctive": set(),
    },
    {
        "label": "cerere",
        "concept": r"cereri?",
        "qualifiers": {
            "inmatricul": "cerere de înmatriculare",
            "reinmatricul": "cerere de reînmatriculare",
            "cazare": "cerere de cazare",
            "transfer": "cerere de transfer",
            "retragere": "cerere de retragere",
            "burs": "cerere de bursă",
        },
        "distinctive": set(),
    },
]


def _qualifier_label(spec: dict, word: str) -> Optional[str]:
    for stem, label in spec["qualifiers"].items():
        if stem in word:
            return label
    return None


def find_present_types(spec: dict, corpus_norm: str) -> List[str]:
    """Tipurile conceptului care apar efectiv în documente (descoperire dinamică)."""
    present: List[str] = []
    seen = set()

    # 1) Colocații: concept (+ de/pentru/privind)? + calificator imediat următor
    colloc = re.compile(
        rf"{spec['concept']}\s+(?:de\s+|pentru\s+|privind\s+|tip\s+)?([a-z\-]{{3,}})"
    )
    for m in colloc.finditer(corpus_norm):
        label = _qualifier_label(spec, m.group(1))
        if label and label not in seen:
            seen.add(label)
            present.append(label)

    # 2) Stems „distinctive" (ex: erasmus) — oriunde, dacă conceptul există în text
    if spec["distinctive"] and re.search(spec["concept"], corpus_norm):
        for stem in spec["distinctive"]:
            if stem in corpus_norm:
                label = spec["qualifiers"].get(stem)
                if label and label not in seen:
                    seen.add(label)
                    present.append(label)

    return present


def _question_has_specific_type(spec: dict, qn: str) -> bool:
    """Întrebarea menționează deja un tip specific al conceptului?"""
    return any(stem in qn for stem in spec["qualifiers"])


def needs_clarification(question: str, corpus_text: str) -> Optional[Tuple[str, List[str]]]:
    """
    Returnează (eticheta_concept, listă_tipuri) dacă întrebarea e generică despre
    un concept cu ≥2 tipuri prezente în documente. Altfel None.
    """
    qn = normalize(question)
    cn = normalize(corpus_text)

    for spec in _CONCEPTS:
        if not re.search(spec["concept"], qn):
            continue
        if _question_has_specific_type(spec, qn):
            continue
        present = find_present_types(spec, cn)
        if len(present) >= 2:
            return spec["label"], present

    return None
