"""
backend/core/exam_service.py
════════════════════════════
Modul SEPARAT pentru examene (independent de RAG / ChromaDB / auth / orar).

Sursa datelor: API-ul public ULBS Connect, descărcat în prealabil cu
`python -m scripts.sync_exams` în `data/schedule/exams.json`. Aici doar CITIM
acel JSON, îl parsăm și răspundem la întrebări despre examene — fără rețea,
fără LLM, fără să atingem restul aplicației.

Examenele sunt planificate la nivel de GRUPĂ (C_31, C_32, TI_31, ISM_31), nu
de semigrupă. Pentru fiecare examen cu dată și oră putem genera un link
„Adaugă în Google Calendar" precompletat (fără OAuth), folosind aceeași logică
de link ca la deadline-uri.

Dacă fișierul nu există (examene nesincronizate), `ExamService.is_loaded()`
este False și chat-ul rămâne pe fluxul normal — nimic nu se schimbă.
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote_plus, urlencode

from backend.config import settings
from backend.core.schedule_service import load_formation_map
from backend.logging_config import logger
from backend.text_utils import markdown_table, normalize


# ── Detectarea întrebărilor despre examene ────────────────────────────────────

def is_exam_question(question: str) -> bool:
    """True dacă întrebarea pare să fie despre examene (examen/examene/examenul…)."""
    return "examen" in normalize(question)


# ── Parsarea grupei (aceleași forme de scriere ca la orar) ────────────────────

_GROUP_PREFIX_ALIASES = {
    "calculatoare": "C", "calc": "C", "c": "C", "ti": "TI", "ism": "ISM",
}
_GROUP_RE = re.compile(r"\b(calculatoare|calc|ism|ti|c)\s*[_ ]?\s*(3[12])\b")
_BARE_NUMBER_RE = re.compile(r"\b(3[12])\b")
_SUBGROUP_RE = re.compile(r"(?:/\s*[123]\b|\bsemigrupa\s*[123]\b|\bsg\s*[123]\b)")


def _join_or(items: List[str]) -> str:
    items = list(items)
    if len(items) <= 1:
        return items[0] if items else ""
    return ", ".join(items[:-1]) + " sau " + items[-1]


# ── Model intern ──────────────────────────────────────────────────────────────

@dataclass
class Exam:
    group: str            # grupa cerută (cheia din exams.json)
    study_formation: str  # studyFormation.name din API (de obicei identic cu grupa)
    subject: str
    professor: str
    assistant: str
    room: str
    type: str
    session: str
    date: str             # ISO „YYYY-MM-DD"
    start: str            # „HH:MM"
    end: str
    exam_id: str


@dataclass
class ExamResolution:
    status: str                  # 'ok' | 'clarify' | 'unknown'
    group: Optional[str] = None
    message: Optional[str] = None


def _name(value, keys=("name", "description", "label")) -> str:
    """Extrage text dintr-un câmp care poate fi string SAU obiect {name/description/…}."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for k in keys:
            v = value.get(k)
            if v:
                return str(v).strip()
    return str(value).strip()


def to_exam(raw: dict, group: str) -> Exam:
    """Normalizează un examen brut din API la modelul intern."""
    return Exam(
        group=group,
        study_formation=_name(raw.get("studyFormation")) or group,
        subject=_name(raw.get("subject")),
        professor=_name(raw.get("professor")),
        assistant=_name(raw.get("assistant")),
        room=_name(raw.get("room") or raw.get("examRoom")),
        type=_name(raw.get("type")),
        session=_name(raw.get("session")),
        date=_name(raw.get("examDate") or raw.get("date")),
        start=_name(raw.get("startTime") or raw.get("start_time")),
        end=_name(raw.get("endTime") or raw.get("end_time")),
        exam_id=str(raw.get("id") or ""),
    )


# ── Link Google Calendar (eveniment precompletat, fără OAuth) ─────────────────
# Aceeași logică precompletată ca la deadline-uri (calendar render TEMPLATE), dar
# cu oră de început/sfârșit și locație, conform cerinței pentru examene.

def build_exam_gcal_url(exam: Exam) -> Optional[str]:
    """
    Link Google Calendar pentru un examen. Returnează None dacă lipsesc data sau
    ora (caz în care NU afișăm buton).
    """
    if not exam.date or not exam.start:
        return None
    try:
        start_dt = datetime.strptime(f"{exam.date} {exam.start}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None

    end_dt = None
    if exam.end:
        try:
            end_dt = datetime.strptime(f"{exam.date} {exam.end}", "%Y-%m-%d %H:%M")
        except ValueError:
            end_dt = None
    if end_dt is None or end_dt <= start_dt:
        end_dt = start_dt + timedelta(hours=2)

    dates = f"{start_dt.strftime('%Y%m%dT%H%M%S')}/{end_dt.strftime('%Y%m%dT%H%M%S')}"
    details_parts = [f"Grupa: {exam.group}"]
    if exam.professor:
        details_parts.append(f"Profesor: {exam.professor}")
    if exam.session:
        details_parts.append(f"Sesiune: {exam.session}")
    if exam.type:
        details_parts.append(f"Tip: {exam.type}")
    params = {
        "action": "TEMPLATE",
        "text": f"Examen - {exam.subject}" if exam.subject else "Examen",
        "dates": dates,
        "location": exam.room or "",
        "details": " · ".join(details_parts),
    }
    return "https://calendar.google.com/calendar/render?" + urlencode(
        params, quote_via=quote_plus
    )


# ── Formatare dată RO ─────────────────────────────────────────────────────────

def _date_ro(iso: str) -> str:
    """„2026-06-20" → „20.06.2026"; întoarce textul brut dacă nu se poate parsa."""
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%d.%m.%Y")
    except (ValueError, TypeError):
        return iso or "dată necunoscută"


_NO_RESULTS = "Nu am găsit examene sincronizate pentru această grupă."


class ExamService:
    """Citește și interoghează examenele descărcate local (per grupă)."""

    def __init__(self, data_path: Optional[str] = None,
                 default_group: Optional[str] = None,
                 groups: Optional[List[str]] = None):
        self.path = Path(data_path) if data_path else settings.exams_data_path_abs
        self.default_group = default_group or settings.default_schedule_group
        # Grupele valide = cheile mapei de formații (C_31, C_32, TI_31, ISM_31)
        self._groups = list(groups) if groups is not None else list(load_formation_map().keys())
        self._data = self._load()

    # ── Încărcare ─────────────────────────────────────────────────────────────

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            logger.warning("Nu am putut citi examenele ({}): {}", self.path, exc)
            return {}

    def is_loaded(self) -> bool:
        return bool(self._data)

    # ── Extragerea examenelor ─────────────────────────────────────────────────

    def exams(self, group: str) -> List[Exam]:
        raw_list = self._data.get(group) or []
        out = [to_exam(r, group) for r in raw_list if isinstance(r, dict)]
        out.sort(key=lambda e: (e.date or "9999-99-99", e.start or "99:99"))
        return out

    # ── Rezolvarea grupei din întrebare ───────────────────────────────────────

    def resolve(self, question: str) -> ExamResolution:
        """
        Grupă explicită → o folosim. Număr ambiguu („31") → cerem clarificare.
        Fără grupă → grupa implicită din config.
        """
        qn = normalize(question)
        group = None
        m = _GROUP_RE.search(qn)
        if m:
            prefix = _GROUP_PREFIX_ALIASES.get(m.group(1))
            if prefix:
                group = f"{prefix}_{m.group(2)}"

        if not group:
            bn = _BARE_NUMBER_RE.search(qn)
            if bn:
                cands = sorted(g for g in self._groups if g.endswith("_" + bn.group(1)))
                if len(cands) > 1:
                    return ExamResolution("clarify", message=f"Te referi la {_join_or(cands)}?")
                if len(cands) == 1:
                    group = cands[0]

        if not group:
            group = self.default_group   # cerința: folosește grupa implicită

        return ExamResolution("ok", group=group)

    # ── Potrivire disciplină ──────────────────────────────────────────────────

    @staticmethod
    def _match_subject(qn: str, exams: List[Exam]) -> List[Exam]:
        matches = []
        for e in exams:
            sn = normalize(e.subject)
            if not sn:
                continue
            if sn in qn:
                matches.append(e)
                continue
            words = [w for w in re.findall(r"[a-z]+", sn) if len(w) > 4]
            if words and any(w in qn for w in words):
                matches.append(e)
        return matches

    # ── Răspuns la întrebări ──────────────────────────────────────────────────

    def answer(self, question: str) -> dict:
        """
        Returnează {status, text, calendar_links}:
          • status = 'clarify' → text = întrebare de clarificare (grupă ambiguă)
          • status = 'unknown' → text = „nu am examene sincronizate…"
          • status = 'ok'      → text = lista examenelor + calendar_links (per examen)
        """
        res = self.resolve(question)
        if res.status == "clarify":
            return {"status": "clarify", "text": res.message, "calendar_links": []}

        exams = self.exams(res.group)
        if not exams:
            return {"status": "unknown", "text": _NO_RESULTS, "calendar_links": []}

        qn = normalize(question)
        subj = self._match_subject(qn, exams)
        sel = subj if subj else exams

        table_rows: List[list] = []   # pentru tabelul Markdown (DB / fallback)
        rich_rows: List[dict] = []     # rânduri structurate (celule + link per rând)
        links: List[dict] = []
        missing = False
        for e in sel:
            when = _date_ro(e.date)
            ora = f"{e.start}–{e.end}" if (e.start and e.end) else (e.start or "—")
            cells = [
                when, ora, e.subject, e.room,
                e.professor or e.assistant, e.type or "examen",
            ]
            table_rows.append(cells)

            url = build_exam_gcal_url(e)
            if url:
                label = f"Adaugă în Google Calendar — {e.subject or 'Examen'} ({when})"
                links.append({"label": label, "url": url})
            elif not e.date or not e.start:
                missing = True
            rich_rows.append({"cells": cells, "url": url})

        header = f"Pentru **{res.group}**, examene găsite:" if not subj \
            else f"Pentru **{res.group}**:"
        cols = ["Data", "Ora", "Disciplină", "Sală", "Profesor", "Tip"]
        body = header + "\n\n" + markdown_table(cols, table_rows)

        notes: List[str] = []
        # Examenele sunt la nivel de grupă — dacă utilizatorul a cerut o semigrupă.
        if _SUBGROUP_RE.search(qn):
            notes.append("_Notă: planificarea examenelor este afișată la nivel de "
                         "grupă; API-ul nu oferă diferențiere pe semigrupă._")
        if missing:
            notes.append("Nu pot genera eveniment Calendar pentru unele examene "
                         "deoarece lipsesc data sau ora examenului.")
        if notes:
            body += "\n\n" + "\n\n".join(notes)

        # `table` = date structurate pentru randarea bogată (buton Calendar pe
        # fiecare rând). `text`/`calendar_links` rămân pentru DB / fallback.
        table = {
            "header": header,
            "cols": cols,
            "rows": rich_rows,
            "notes": "\n\n".join(notes),
        }
        return {"status": "ok", "text": body, "calendar_links": links,
                "table": table}
