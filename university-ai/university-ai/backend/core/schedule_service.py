"""
backend/core/schedule_service.py
════════════════════════════════
Modul SEPARAT pentru orarul grupei (independent de RAG / ChromaDB / auth).

Sursa datelor: API-ul public schedule.ulbsibiu.ro, descărcat în prealabil cu
`python -m scripts.sync_schedule` în `data/schedule/schedule.json`. Aici doar
CITIM acel JSON, îl parsăm și răspundem la întrebări despre orar — fără rețea,
fără LLM, fără să atingem restul aplicației.

Dacă fișierul nu există (orar nesincronizat), `ScheduleService.is_loaded()`
este False și chat-ul rămâne pe fluxul normal (RAG) — nimic nu se schimbă.
"""

import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional

from backend.config import settings
from backend.logging_config import logger
from backend.text_utils import markdown_table, normalize


# ── Mapare zile EN → RO ───────────────────────────────────────────────────────

_DAY_EN_TO_RO = {
    "monday": "Luni", "tuesday": "Marți", "wednesday": "Miercuri",
    "thursday": "Joi", "friday": "Vineri", "saturday": "Sâmbătă",
    "sunday": "Duminică",
}

# Token RO normalizat → numele EN al zilei (pentru filtrare din întrebare)
_RO_TOKEN_TO_EN = {
    "luni": "Monday", "marti": "Tuesday", "miercuri": "Wednesday",
    "joi": "Thursday", "vineri": "Friday", "sambata": "Saturday",
    "duminica": "Sunday",
}

# weekday() (Luni=0) → numele EN
_WEEKDAY_TO_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                  "Saturday", "Sunday"]


# ── Detectarea întrebărilor despre orar ───────────────────────────────────────

_SCHEDULE_KEYWORDS = (
    "orar", "azi", "maine", "luni", "marti", "miercuri", "joi", "vineri",
    "sambata", "duminica", "sala", "laborator", "seminar", "curs", "profesor",
    "la ce ora", "unde am", "ce am", "cine preda", "cine tine", "in ce sala",
    "ce cursuri", "ce laboratoare", "ce seminarii", "saptamana asta",
)


def is_schedule_question(question: str) -> bool:
    """True dacă întrebarea pare să fie despre orar."""
    n = normalize(question)
    return any(k in n for k in _SCHEDULE_KEYWORDS)


def mentions_group(question: str) -> bool:
    """True dacă mesajul pare să indice o grupă/semigrupă (sau o încercare de a o da)."""
    n = normalize(question)
    if any(t in n for t in ("grupa", "semigrupa", "sg ", "/1", "/2", "/3")):
        return True
    return bool(_GROUP_RE.search(n) or _BARE_NUMBER_RE.search(n))


# ── Mapare grupă/semigrupă → studyFormationId ─────────────────────────────────

# Mapă implicită (fallback dacă lipsește data/schedule/formation_map.json).
_DEFAULT_FORMATION_MAP = {
    "C_31": {"1": 541, "2": 542, "3": 543},
    "C_32": {"1": 544, "2": 545, "3": 546},
    "TI_31": {"1": 557, "2": 558},
    "ISM_31": {"1": 564, "2": 565},
}

# Aliasuri pentru PREFIXUL grupei (litere) → cheia canonică din mapă.
# Permite scrieri variate: „calculatoare 31" → C, „c_31"/„c31" → C, „ti_31" → TI.
_GROUP_PREFIX_ALIASES = {
    "calculatoare": "C",
    "calc": "C",
    "c": "C",
    "ti": "TI",
    "ism": "ISM",
}

# Grupă explicită: prefix (litere/alias) + separator opțional (_ sau spațiu) + număr.
_GROUP_RE = re.compile(r"\b(calculatoare|calc|ism|ti|c)\s*[_ ]?\s*(3[12])\b")
# Număr „gol" (fără prefix) — posibil ambiguu (ex. „grupa 31").
_BARE_NUMBER_RE = re.compile(r"\b(3[12])\b")
# Semigrupă: „/1", „semigrupa 1", „sg 1", „semigrupa1".
_SUBGROUP_RES = (
    re.compile(r"/\s*([123])\b"),
    re.compile(r"\bsemigrupa\s*([123])\b"),
    re.compile(r"\bsg\s*([123])\b"),
)


def load_formation_map(path: Optional[Path] = None) -> dict:
    """Încarcă maparea grupă→semigrupă→formation_id din JSON; fallback la implicit."""
    p = path or settings.schedule_formation_map_path_abs
    try:
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data:
                # normalizăm valorile la str pentru chei și păstrăm id-urile ca int
                return {
                    str(g): {str(sg): int(fid) for sg, fid in subs.items()}
                    for g, subs in data.items() if isinstance(subs, dict)
                }
    except Exception as exc:
        logger.warning("Nu am putut citi maparea formațiilor ({}): {}", p, exc)
    return {k: dict(v) for k, v in _DEFAULT_FORMATION_MAP.items()}


@dataclass
class Resolution:
    """Rezultatul rezolvării grupei/semigrupei dintr-o întrebare."""
    status: str                  # 'ok' | 'clarify' | 'unknown'
    formation_id: Optional[str] = None
    group: Optional[str] = None
    subgroup: Optional[str] = None
    message: Optional[str] = None  # text de afișat pentru 'clarify' / 'unknown'
    # True când clarificarea cere GRUPA (chat-ul reține întrebarea și așteaptă răspunsul)
    needs_group: bool = False


def _join_or(items: List[str]) -> str:
    """['C_31','TI_31','ISM_31'] → 'C_31, TI_31 sau ISM_31'."""
    items = list(items)
    if len(items) <= 1:
        return items[0] if items else ""
    return ", ".join(items[:-1]) + " sau " + items[-1]


# ── Model intern ──────────────────────────────────────────────────────────────

@dataclass
class Lesson:
    day_en: str
    day_ro: str
    subject: str
    professor: str
    assistant: str
    room: str
    activity: str
    start: str
    end: str
    time_range: str
    parity: str


def _text(value, keys=("name", "label", "shortName", "abbreviation")) -> str:
    """Extrage text dintr-un câmp care poate fi string SAU obiect {name/label/...}."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for k in keys:
            v = value.get(k)
            if v:
                return str(v).strip()
        # fallback: prima valoare string
        for v in value.values():
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""
    return str(value).strip()


_NO_RESULTS = "Nu am găsit activități în orar pentru această întrebare."


class ScheduleService:
    """Citește și interoghează orarul descărcat local (per formație)."""

    def __init__(self, data_path: Optional[str] = None,
                 default_formation: Optional[str] = None,
                 formation_map: Optional[dict] = None,
                 default_group: Optional[str] = None,
                 default_subgroup: Optional[str] = None):
        self.path = Path(data_path) if data_path else settings.schedule_data_path_abs
        self.default_formation = str(
            default_formation or settings.default_schedule_formation_id
        )
        self.default_group = default_group or settings.default_schedule_group
        self.default_subgroup = str(default_subgroup or settings.default_schedule_subgroup)
        # Mapa grupă/semigrupă → formation_id + reverse (formation_id → grupă/semigrupă)
        self._map = formation_map if formation_map is not None else load_formation_map()
        self._reverse = {
            str(fid): (group, sub)
            for group, subs in self._map.items()
            for sub, fid in subs.items()
        }
        self._data = self._load()

    # ── Încărcare ─────────────────────────────────────────────────────────────

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Nu am putut citi orarul ({}): {}", self.path, exc)
            return {}

    def is_loaded(self) -> bool:
        return bool(self._data)

    # ── Rezolvarea grupei/semigrupei din întrebare ───────────────────────────

    def _has_data(self, formation_id: str) -> bool:
        """True dacă orarul pentru această formație a fost descărcat local."""
        d = self._data
        if isinstance(d, dict) and formation_id in d:
            return True
        # payload unic salvat direct (un singur orar) — valabil doar pt. default
        if isinstance(d, dict) and ("schedules" in d or "data" in d or "studyFormation" in d):
            return formation_id == str(self.default_formation)
        return False

    def _parse_request(self, qn: str):
        """Extrage (grupă, semigrupă, număr_gol) dintr-o întrebare normalizată."""
        group = None
        m = _GROUP_RE.search(qn)
        if m:
            prefix = _GROUP_PREFIX_ALIASES.get(m.group(1))
            if prefix:
                group = f"{prefix}_{m.group(2)}"

        bare_number = None
        if not group:
            bn = _BARE_NUMBER_RE.search(qn)
            if bn:
                bare_number = bn.group(1)

        subgroup = None
        for rx in _SUBGROUP_RES:
            sm = rx.search(qn)
            if sm:
                subgroup = sm.group(1)
                break

        return group, subgroup, bare_number

    def _unknown_group_msg(self) -> str:
        groups = " și ".join([", ".join(list(self._map)[:-1]), list(self._map)[-1]]) \
            if len(self._map) > 1 else (list(self._map)[0] if self._map else "")
        return (
            "Nu am orarul sincronizat pentru această grupă. "
            f"Pot răspunde doar pentru: {groups}."
        )

    def _not_synced_msg(self, group: str, subgroup: str) -> str:
        return (
            f"Nu am orarul sincronizat pentru grupa {group}, semigrupa {subgroup}. "
            "Rulează sincronizarea: python -m scripts.sync_schedule."
        )

    def _ask_group_msg(self) -> str:
        return (
            "Pentru ce grupă și semigrupă vrei orarul? De exemplu: "
            "C_31 semigrupa 1, C_31 semigrupa 2, C_32 semigrupa 1, "
            "TI_31 semigrupa 1 sau ISM_31 semigrupa 2."
        )

    def resolve(self, question: str, formation_id: Optional[str] = None,
                remembered: Optional[str] = None,
                ask_if_unspecified: bool = False) -> Resolution:
        """
        Decide ce formație (grupă/semigrupă) corespunde întrebării.

        Reguli:
          • grupă explicită („C_31/2", „TI_31 semigrupa 1") → o folosim;
          • număr gol ambiguu („31") → cerem clarificare (C_31 / TI_31 / ISM_31);
          • grupă necunoscută sau nesincronizată → mesaj clar;
          • fără grupă:
              - dacă avem o grupă reținută (`remembered`) → o folosim;
              - dacă `ask_if_unspecified` → cerem grupa (status 'clarify', needs_group);
              - altfel → folosim formation_id dat sau grupa implicită din config.
        """
        qn = normalize(question)
        group, subgroup, bare = self._parse_request(qn)

        # Număr fără prefix → poate fi ambiguu (ex. „grupa 31")
        if bare and not group:
            cands = sorted(g for g in self._map if g.endswith("_" + bare))
            if len(cands) > 1:
                return Resolution("clarify", needs_group=True,
                                  message=f"Te referi la {_join_or(cands)}?")
            if len(cands) == 1:
                group = cands[0]
            # 0 candidați → ignorăm numărul, mergem mai departe

        if group:
            if group not in self._map:
                return Resolution("unknown", group=group, subgroup=subgroup,
                                  message=self._unknown_group_msg())
            subs = self._map[group]
            if not subgroup or subgroup not in subs:
                subgroup = self.default_subgroup if self.default_subgroup in subs \
                    else sorted(subs)[0]
            fid = str(subs[subgroup])
            if not self._has_data(fid):
                return Resolution("unknown", formation_id=fid, group=group,
                                  subgroup=subgroup,
                                  message=self._not_synced_msg(group, subgroup))
            return Resolution("ok", formation_id=fid, group=group, subgroup=subgroup)

        # ── Fără grupă în întrebare ──────────────────────────────────────────
        # 1) grupă reținută din conversație
        if remembered:
            fid = str(remembered)
            g, s = self._reverse.get(fid, (None, None))
            return Resolution("ok", formation_id=fid,
                              group=g or self.default_group,
                              subgroup=s or self.default_subgroup)
        # 2) cerem explicit grupa (comportamentul dorit în chat)
        if ask_if_unspecified:
            return Resolution("clarify", needs_group=True, message=self._ask_group_msg())
        # 3) fallback (folosit programatic / în teste): formation_id sau implicit
        fid = str(formation_id or self.default_formation or "").strip()
        if not fid:
            return Resolution("clarify", needs_group=True, message=self._ask_group_msg())
        g, s = self._reverse.get(fid, (None, None))
        return Resolution("ok", formation_id=fid,
                          group=g or self.default_group,
                          subgroup=s or self.default_subgroup)

    # ── Extragerea lecțiilor ────────────────────────────────────────────────

    def _formation_payload(self, formation_id: str) -> Optional[dict]:
        """Găsește payload-ul API pentru o formație (tolerant la forma JSON-ului)."""
        data = self._data
        if not isinstance(data, dict):
            return data if isinstance(data, list) else None
        # 1) dict {fid: payload}
        if formation_id in data and isinstance(data[formation_id], (dict, list)):
            return data[formation_id]
        # 2) payload unic salvat direct
        if "schedules" in data or "studyFormation" in data or "data" in data:
            return data
        # 3) altfel, prima formație disponibilă
        for v in data.values():
            if isinstance(v, (dict, list)):
                return v
        return None

    @staticmethod
    def _schedules_list(payload) -> list:
        """
        Găsește lista de lecții 'schedules' oriunde în structură (API-ul o
        împachetează în {success, message, data: [{studyFormation, schedules}]}).
        """
        found: list = []

        def walk(obj):
            if isinstance(obj, dict):
                sched = obj.get("schedules")
                if isinstance(sched, list):
                    found.extend(s for s in sched if isinstance(s, dict))
                for key, val in obj.items():
                    if key == "schedules":
                        continue  # nu coborâm în lecțiile deja colectate
                    if isinstance(val, (dict, list)):
                        walk(val)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item)

        walk(payload)
        return found

    def lessons(self, formation_id: Optional[str] = None) -> List[Lesson]:
        payload = self._formation_payload(str(formation_id or self.default_formation))
        out: List[Lesson] = []
        for s in self._schedules_list(payload):
            if not isinstance(s, dict):
                continue
            day_en = _text(s.get("day")).capitalize()
            slots = [t for t in (s.get("timeSlots") or []) if isinstance(t, dict)]
            start = end = trange = ""
            if slots:
                start = _text(slots[0].get("startTime"))
                end = _text(slots[-1].get("endTime"))   # ultimul slot → durata totală
                trange = _text(slots[0].get("timeRange"))
            # paritate: din isEvenWeek / isOddWeek (mai sigur decât câmpul numeric)
            even, odd = bool(s.get("isEvenWeek")), bool(s.get("isOddWeek"))
            if even and not odd:
                parity = "pare"
            elif odd and not even:
                parity = "impare"
            else:
                parity = ""  # ambele / niciuna → în fiecare săptămână
            out.append(Lesson(
                day_en=day_en,
                day_ro=_DAY_EN_TO_RO.get(day_en.lower(), day_en),
                subject=_text(s.get("subject")),
                professor=_text(s.get("professor")),
                assistant=_text(s.get("assistant")),
                room=_text(s.get("room")),
                # activityType.name = denumirea RO ("Laborator"/"Curs"); label = abreviere
                activity=_text(s.get("activityType"), keys=("name", "label")),
                start=start, end=end, time_range=trange,
                parity=parity,
            ))
        return out

    # ── Răspuns la întrebări ────────────────────────────────────────────────

    def answer(self, question: str, formation_id: Optional[str] = None) -> str:
        """Răspuns complet (cu rezolvare implicită — folosit programatic/în teste)."""
        res = self.resolve(question, formation_id=formation_id)
        return self.answer_for(res, question)

    def answer_with(self, formation_id: str, question: str) -> str:
        """Răspunde la o întrebare folosind o formație IMPUSĂ (grupa deja aleasă).

        Ignoră orice grupă din textul întrebării — folosim doar ziua/ora/activitatea.
        Util când reluăm întrebarea inițială după ce utilizatorul a precizat grupa.
        """
        fid = str(formation_id)
        g, s = self._reverse.get(fid, (self.default_group, self.default_subgroup))
        return self.answer_for(Resolution("ok", formation_id=fid, group=g, subgroup=s),
                               question)

    def answer_for(self, res: "Resolution", question: str) -> str:
        """Produce textul răspunsului pornind de la o rezoluție deja stabilită."""
        if res.status in ("clarify", "unknown"):
            return res.message

        lessons = self.lessons(res.formation_id)
        if not lessons:
            return self._no_results_msg(res, None)

        qn = normalize(question)

        asks_time = any(k in qn for k in ("la ce ora", "la ce ore", "cand am", "ce ora"))
        asks_room = any(k in qn for k in ("unde am", "in ce sala", "ce sala", "unde se tine", "unde e", "unde se"))
        asks_prof = any(k in qn for k in ("cine preda", "cine tine", "ce profesor", "care profesor", "cine face"))

        subj_matches = self._match_subject(qn, lessons)

        # Întrebare punctuală despre o disciplină (oră / sală / profesor)
        if subj_matches and (asks_time or asks_room or asks_prof):
            return self._format_subject(subj_matches, asks_time, asks_room, asks_prof)

        target_day = self._target_day(qn)
        target_time = self._target_time(qn)
        activity = self._target_activity(qn)

        sel = list(subj_matches) if subj_matches else list(lessons)
        if target_day:
            sel = [l for l in sel if l.day_en.lower() == target_day.lower()]
        if activity:
            sel = [l for l in sel if activity in normalize(l.activity)]
        if target_time:
            sel = [l for l in sel if self._matches_time(l, target_time)]

        if not sel:
            return self._no_results_msg(res, target_day)
        return self._format_list(sel, target_day, res)

    def _group_label(self, res: "Resolution") -> str:
        """„C_31, semigrupa 2" — eticheta grupei pentru mesaje."""
        grp = res.group or self.default_group
        sub = res.subgroup or self.default_subgroup
        if grp and sub:
            return f"{grp}, semigrupa {sub}"
        return grp or "grupa selectată"

    def _no_results_msg(self, res: "Resolution", target_day: Optional[str]) -> str:
        label = self._group_label(res)
        if target_day:
            ro = _DAY_EN_TO_RO.get(target_day.lower(), target_day)
            return f"Nu am găsit activități în orar pentru {label}, în ziua de {ro.lower()}."
        return f"Nu am găsit activități în orar pentru {label}."

    # ── Helperi de potrivire ─────────────────────────────────────────────────

    def _match_subject(self, qn: str, lessons: List[Lesson]) -> List[Lesson]:
        """Lecțiile a căror disciplină e menționată în întrebare."""
        matches = []
        for l in lessons:
            sn = normalize(l.subject)
            if not sn:
                continue
            if sn in qn:
                matches.append(l)
                continue
            # potrivire pe cuvinte distinctive (>4 litere) din titlul disciplinei
            words = [w for w in re.findall(r"[a-z]+", sn) if len(w) > 4]
            if words and any(w in qn for w in words):
                matches.append(l)
        return matches

    def _target_day(self, qn: str) -> Optional[str]:
        if "azi" in qn or "astazi" in qn:
            return _WEEKDAY_TO_EN[date.today().weekday()]
        if "maine" in qn:
            return _WEEKDAY_TO_EN[(date.today() + timedelta(days=1)).weekday()]
        for token, en in _RO_TOKEN_TO_EN.items():
            if re.search(rf"\b{token}\b", qn):
                return en
        return None

    @staticmethod
    def _target_time(qn: str) -> Optional[str]:
        """Extrage o oră din întrebare: „11:20" / „de la 11" / „ora 11" → '11:20' sau '11:'."""
        m = re.search(r"(\d{1,2})[:.](\d{2})", qn)
        if m:
            return f"{int(m.group(1)):02d}:{m.group(2)}"
        m = re.search(r"\b(?:ora|orele|de la|incepand cu|la)\s+(\d{1,2})(?!\d)", qn)
        if m:
            return f"{int(m.group(1)):02d}:"   # doar ora (prefix), fără minute
        return None

    @staticmethod
    def _matches_time(l: "Lesson", target: str) -> bool:
        """True dacă lecția se desfășoară la / în jurul orei cerute."""
        if not l.start:
            return False
        if target.endswith(":"):                 # doar ora (ex: '11:')
            return l.start.startswith(target)
        if l.start == target:                     # început exact
            return True
        if l.end and l.start <= target < l.end:   # ora cerută cade în interval
            return True
        return False

    @staticmethod
    def _target_activity(qn: str) -> Optional[str]:
        if "laborator" in qn or "laboratoare" in qn:
            return "lab"
        if "seminar" in qn:
            return "seminar"
        if "curs" in qn or "cursuri" in qn:
            return "curs"
        return None

    # ── Formatare răspuns ─────────────────────────────────────────────────────

    @staticmethod
    def _slot(l: Lesson) -> str:
        if l.start and l.end:
            return f"{l.start}–{l.end}"
        return l.time_range or "interval nespecificat"

    def _describe(self, l: Lesson, with_day: bool = True) -> str:
        parts = []
        if with_day and l.day_ro:
            parts.append(l.day_ro)
        act = l.activity or "activitate"
        line = f"{act} la {l.subject}" if l.subject else act
        who = l.professor or l.assistant
        if who:
            line += f", cu {who}"
        if l.room:
            line += f", în sala {l.room}"
        line += f", {self._slot(l)}"
        if l.parity:
            line += f" (săptămâni {l.parity})"
        prefix = (parts[0] + ": ") if parts else ""
        return prefix + line

    def _format_subject(self, lessons, asks_time, asks_room, asks_prof) -> str:
        out = []
        for l in lessons:
            if asks_room and not (asks_time or asks_prof):
                out.append(f"{l.subject}: {l.day_ro}, sala {l.room or 'nespecificată'} ({self._slot(l)}).")
            elif asks_prof and not (asks_time or asks_room):
                who = l.professor or l.assistant or "nespecificat"
                out.append(f"{l.subject}: predă {who} ({l.activity}, {l.day_ro}).")
            elif asks_time and not (asks_room or asks_prof):
                out.append(f"{l.subject}: {l.day_ro}, {self._slot(l)} ({l.activity}).")
            else:
                out.append(self._describe(l))
        return "\n".join(f"• {o}" for o in out)

    def _format_list(self, lessons, target_day, res: "Resolution" = None) -> str:
        """Listă de activități sub formă de TABEL Markdown (randat de st.markdown)."""
        ordered = sorted(lessons, key=lambda l: (l.day_en, l.start or l.time_range))
        label = self._group_label(res) if res else ""

        if target_day:
            ro = _DAY_EN_TO_RO.get(target_day.lower(), target_day)
            header = f"Pentru {label}, {ro} ai:" if label else f"{ro} ai:"
            # Ziua e deja în antet → nu mai repetăm coloana „Zi".
            cols = ["Interval", "Tip", "Disciplină", "Sală", "Profesor", "Săpt."]
            table_rows = [
                [self._slot(l), l.activity, l.subject,
                 l.room, l.professor or l.assistant, l.parity]
                for l in ordered
            ]
        else:
            header = f"Pentru {label}:" if label else "Orarul tău:"
            cols = ["Zi", "Interval", "Tip", "Disciplină", "Sală", "Profesor", "Săpt."]
            table_rows = [
                [l.day_ro, self._slot(l), l.activity, l.subject,
                 l.room, l.professor or l.assistant, l.parity]
                for l in ordered
            ]

        return header + "\n\n" + markdown_table(cols, table_rows)
