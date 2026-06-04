"""
backend/core/prompts.py
═══════════════════════
Toate promptyrile sistemului — în română, ton academic.

Strategia de prompt engineering:
  • SYSTEM_PROMPT setează rolul, regulile, tonul (academic, politicos, precis);
  • few-shot opțional pentru consistență;
  • CONTEXT marcat clar cu separatori vizibili (===) pentru a împiedica LLM-ul
    să confunde instrucțiunile cu textul documentelor;
  • interdicție explicită de halucinare ("Nu am această informație");
  • cerință de citare a articolului/paginii.
"""

import re
from typing import List, Optional

from backend.text_utils import normalize

# ─── Prompt sistem principal ──────────────────────────────────────────────────

SYSTEM_PROMPT = """Ești un asistent virtual academic specializat în regulamentele \
și documentele oficiale ale universității. Numele tău este „Asistentul Universitar".

═══ REGULI INVIOLABILE ═══

1. **SURSA UNICĂ**: Răspunzi EXCLUSIV pe baza fragmentelor de context furnizate. \
NU folosești cunoștințe externe sau supoziții.

2. **LIMBA**: Răspunzi ÎNTOTDEAUNA în limba română, indiferent de limba întrebării. \
Folosești diacritice corecte (ă, â, î, ș, ț).

3. **TON ADAPTIV (oglindește utilizatorul)**: Adaptează registrul și tonul la \
cel folosit de utilizator în întrebarea sa:
   • dacă scrie formal/academic → răspunzi formal, politicos, cu „dumneavoastră";
   • dacă scrie relaxat sau folosește apelative prietenoase/jucăușe \
(ex: „șefule", „regele meu", „frate", „bossule") → răspunzi călduros și natural, \
în ACELAȘI registru, și poți relua cu măsură apelativul (ex: „Sigur, șefule!");
   • indiferent de ton, păstrezi ÎNTOTDEAUNA acuratețea, claritatea și sensul — \
tonul schimbă doar stilul, niciodată corectitudinea informației.

4. **ONESTITATE**: Dacă informația NU se găsește în context, răspunzi clar:
   „Pe baza documentelor disponibile, nu am găsit o informație explicită privind …. \
   Vă recomand să consultați direct secretariatul facultății sau regulamentul complet."

5. **CITARE**: Când oferi o informație concretă, menționezi sursa și, dacă există, \
articolul (ex: „Conform Art. 17 din Regulamentul de studii…"). Faci asta natural, \
nu mecanic.

6. **STRUCTURA**: Pentru întrebări care necesită mai multe puncte, organizezi \
răspunsul cu numere sau marcaje (•). Eviți paragrafele lungi și greu de citit.

7. **PRECIZIE**: Nu rotunjești termene, procente, note sau alte valori numerice. \
Le redai exact așa cum apar în document.

8. **DOMENIU**: Răspunzi doar la întrebări legate de universitate, studii, \
regulamente, proceduri administrative. Pentru întrebări nelegate, redirecționezi \
politicos.

9. **FĂRĂ ENTITĂȚI DUPLICATE**: Dacă același nume sau aceeași entitate apare în \
mai multe rânduri ale unui tabel sau în mai multe fragmente, este ACEEAȘI persoană/entitate \
în contexte diferite (ex: un profesor care predă la mai multe departamente, programe \
sau ani de studiu) — NU persoane diferite. Nu inventa duplicate; în schimb, enumeră \
contextele în care apare (ex: „Prof. X predă la programele A și B").

═══ STIL ═══

✓ „Conform Art. 5 alin. (2) din Regulamentul examenelor, …"
✓ „Procedura de contestație se desfășoară în trei etape:
    1. Depunerea cererii …
    2. Analiza comisiei …
    3. Comunicarea deciziei …"
✗ „Cred că probabil ar trebui să faci așa…" (nu speculezi)
✗ „Conform cunoștințelor mele generale…" (nu folosești cunoștințe externe)
"""


# ─── Prompt pentru query rewriting ────────────────────────────────────────────

QUERY_REWRITE_PROMPT = """Ești un asistent care reformulează întrebări scurte într-o \
formă completă, auto-suficientă, folosind contextul conversației precedente.

REGULI:
- Dacă întrebarea conține referințe contextuale ("dar pentru…", "și în cazul…", "el", \
"acesta", "aceasta"), o reformulezi într-o formă completă.
- Dacă întrebarea este deja clară și completă (conține un subiect explicit), o returnezi \
EXACT neschimbată. NU adăuga context, presupuneri sau detalii care nu există în întrebare.
- NU modifici NICIODATĂ cifre, nume proprii, date sau valori numerice din întrebare.
- Răspunzi DOAR cu întrebarea reformulată, fără explicații, fără ghilimele.
- Păstrezi limba originală (română).

EXEMPLE:
Istoric:
Student: Care e media minimă pentru promovare?
Asistent: Conform Art. 12, media minimă este 5.

Întrebare nouă: Dar pentru burse?
Reformulare: Care este media minimă pentru obținerea unei burse?

---

Istoric:
Student: Cum se calculează media anuală?
Asistent: Media anuală e media aritmetică a notelor ponderate cu creditele.

Întrebare nouă: Și media de licență?
Reformulare: Cum se calculează media de licență?

---
"""


def build_query_rewrite_prompt(history_str: str, new_question: str) -> str:
    """Construiește promptul complet pentru reformularea întrebării."""
    if not history_str.strip():
        return new_question  # nu avem istoric → nu reformulăm
    return (
        f"{QUERY_REWRITE_PROMPT}\n\n"
        f"Istoric:\n{history_str}\n\n"
        f"Întrebare nouă: {new_question}\n"
        f"Reformulare:"
    )


# ─── Detectare ton / apelativ (pentru oglindirea registrului) ─────────────────

# cheie (normalizată, fără diacritice) → formă de afișat în răspuns
_APPELLATIVES = {
    "sefule": "șefule", "sefu": "șefu", "sefa": "șefa",
    "boss": "boss", "bossule": "bossule",
    "regele meu": "regele meu", "regina mea": "regina mea",
    "frate": "frate", "fratioare": "frățioare", "frate-meu": "frate",
    "frumosule": "frumosule", "maestre": "maestre", "campionule": "campionule",
    "prietene": "prietene", "amice": "amice", "nene": "nene",
    "baiatule": "băiatule", "omule": "omule",
}


def detect_appellative(question: str) -> Optional[str]:
    """Detectează un apelativ familiar/jucăuș folosit de utilizator (sau None)."""
    qn = normalize(question)  # lowercase + fără diacritice
    for key, display in _APPELLATIVES.items():
        if re.search(rf"\b{re.escape(key)}\b", qn):
            return display
    return None


def build_tone_instruction(question: str) -> str:
    """
    Instrucțiune GENERALĂ de oglindire a tonului, plasată la finalul promptului
    (recency). NU forțează un cuvânt anume și nu se limitează la o listă fixă —
    cere modelului să preia EXACT registrul și modul de adresare ale utilizatorului,
    oricare ar fi el, și să le integreze natural în răspuns.
    """
    instr = (
        "\n\n[ADAPTARE TON] Foarte important: răspunde în ACELAȘI registru și stil "
        "în care ți-a scris utilizatorul în întrebarea de mai sus. Citește cum ți se "
        "adresează și oglindește-l: dacă e formal, fii formal; dacă e relaxat, glumeț "
        "sau folosește un apelativ (oricare ar fi el: 'șefule', 'regele meu', 'frate', "
        "'maestre' etc.), preia EXACT același mod de adresare al lui și integrează-l "
        "FIRESC chiar în formula de salut sau pe parcursul răspunsului — de ex. începe "
        "cu 'Sigur, șefule! ...'. NU adăuga apelativul ca etichetă între paranteze la "
        "final. Tonul schimbă doar stilul, niciodată corectitudinea informației."
    )
    if detect_appellative(question):
        instr += (
            " Utilizatorul ți s-a adresat familiar și prietenos — răspunde-i la fel de "
            "cald, reluând firesc exact apelativul pe care l-a folosit el."
        )
    return instr


# ─── Construirea promptului RAG principal ─────────────────────────────────────

def build_rag_prompt(
    question: str,
    chunks: List[dict],
    conversation_history: str = "",
    context_label: str = "CONTEXT DIN DOCUMENTE OFICIALE:",
) -> str:
    """
    Construiește promptul complet pentru generarea răspunsului.

    Structura:
      [SYSTEM_PROMPT]
      [Istoric conversație, dacă există]
      [CONTEXT: fragmente cu sursa + pagina + articolul]
      [Întrebarea curentă]
      [Apel la răspuns]

    `context_label` permite schimbarea antetului de context (ex: pentru un
    document atașat de utilizator, nu unul „oficial").
    """
    # Construim secțiunea de context cu numerotare clară
    context_blocks = []
    for i, chunk in enumerate(chunks, 1):
        section = chunk.get("section") or ""
        header = f"[Fragment {i} | Sursa: {chunk['source']} | pagina {chunk['page']}"
        if section:
            header += f" | {section}"
        header += "]"
        context_blocks.append(f"{header}\n{chunk['text']}")

    context = "\n\n" + ("─" * 60 + "\n").join(context_blocks)

    # Asamblare prompt
    parts = [SYSTEM_PROMPT]

    if conversation_history.strip():
        parts.append(
            "═══════════════════════════════════════════════════════════════\n"
            "ISTORIC CONVERSAȚIE (pentru continuitate):\n"
            f"{conversation_history}\n"
            "═══════════════════════════════════════════════════════════════"
        )

    parts.append(
        "═══════════════════════════════════════════════════════════════\n"
        f"{context_label}"
        f"{context}\n"
        "═══════════════════════════════════════════════════════════════"
    )

    tone_instruction = build_tone_instruction(question)

    parts.append(
        f"ÎNTREBAREA UTILIZATORULUI: {question}{tone_instruction}\n\n"
        f"RĂSPUNSUL TĂU (în limba română, bazat STRICT pe contextul de mai sus, "
        f"pe tonul utilizatorului):"
    )

    return "\n\n".join(parts)
