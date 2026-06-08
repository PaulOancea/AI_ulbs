"""Teste pentru modulul de examene (exam_service) — izolat de RAG."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.core import exam_service as ex
from backend.core.exam_service import ExamService


def _raw(subject, prof, room, date, start, end, eid=1):
    return {
        "id": eid,
        "subject": {"name": subject},
        "examDate": date,
        "startTime": start,
        "endTime": end,
        "room": room,
        "professor": {"name": prof} if prof else None,
        "assistant": None,
        "type": {"description": "examen"},
        "session": {"name": "Sesiune examene"},
        "studyFormation": None,
    }


# Date de test pe grupe; ISM_31 are un examen fără oră (pentru cazul „fără Calendar").
_EXAMS = {
    "C_31": [
        _raw("Sisteme de operare", "Popescu Ion", "IE101", "2026-06-20", "10:00", "12:00", 1),
        _raw("Rețele de calculatoare", "Ene Ana", "A4", "2026-06-22", "08:00", "10:00", 2),
    ],
    "C_32": [
        _raw("Inteligență artificială", "Bontas George", "IM201", "2026-06-15", "09:40", "11:40", 3),
    ],
    "TI_31": [
        _raw("Electronică", "Toma Gheo", "Lab TI", "2026-06-18", "14:00", "16:00", 4),
    ],
    "ISM_31": [
        _raw("Management", "Ilie Rad", "S3", "2026-06-19", "", "", 5),  # fără oră
    ],
}


@pytest.fixture
def svc(tmp_path):
    p = tmp_path / "exams.json"
    p.write_text(json.dumps(_EXAMS, ensure_ascii=False), encoding="utf-8")
    return ExamService(data_path=str(p), default_group="C_31",
                       groups=["C_31", "C_32", "TI_31", "ISM_31"])


def test_is_exam_question():
    assert ex.is_exam_question("Ce examene am?")
    assert ex.is_exam_question("Când am examenul la Sisteme de operare?")
    assert ex.is_exam_question("Adaugă examenul la Google Calendar")
    assert not ex.is_exam_question("Care sunt condițiile de promovare?")


def test_default_group_ce_examene_am(svc):
    r = svc.answer("Ce examene am?")
    assert r["status"] == "ok"
    assert "C_31" in r["text"]
    assert "Sisteme de operare" in r["text"]
    assert "Rețele de calculatoare" in r["text"]


def test_other_group(svc):
    r = svc.answer("Ce examene are C_32?")
    assert r["status"] == "ok"
    assert "Inteligenț" in r["text"]
    assert "Sisteme de operare" not in r["text"]   # nu e din C_31


def test_when_exam_subject(svc):
    r = svc.answer("Când am examenul la Sisteme de operare?")
    assert "20.06.2026" in r["text"]
    assert "Rețele" not in r["text"]   # doar disciplina cerută


def test_where_exam_subject(svc):
    r = svc.answer("Unde am examenul la Sisteme de operare?")
    assert "IE101" in r["text"]


def test_bare_number_asks_clarification(svc):
    r = svc.answer("Ce examene are grupa 31?")
    assert r["status"] == "clarify"
    assert "C_31" in r["text"] and "TI_31" in r["text"] and "ISM_31" in r["text"]


def test_concrete_exam_has_calendar_link(svc):
    r = svc.answer("Când am examenul la Sisteme de operare?")
    assert len(r["calendar_links"]) == 1
    url = r["calendar_links"][0]["url"]
    assert url.startswith("https://calendar.google.com/calendar/render")
    assert "Google Calendar" in r["calendar_links"][0]["label"]
    assert "Examen" in url                      # titlul evenimentului
    assert "20260620T100000" in url            # dată + oră început
    assert "IE101" in url                       # locație


def test_missing_time_no_calendar(svc):
    """Examen fără oră → fără buton Calendar + notă explicită."""
    r = svc.answer("Ce examene are ISM_31?")
    assert r["status"] == "ok"
    assert r["calendar_links"] == []
    assert "lipsesc data sau ora" in r["text"]


def test_subgroup_note(svc):
    """Examenele sunt la nivel de grupă — menționăm asta dacă se cere semigrupa."""
    r = svc.answer("Ce examene are C_31 semigrupa 2?")
    assert r["status"] == "ok"
    assert "nivel de grup" in r["text"]


def test_no_exams_for_group(tmp_path):
    p = tmp_path / "exams.json"
    p.write_text(json.dumps({"C_31": []}, ensure_ascii=False), encoding="utf-8")
    svc = ExamService(data_path=str(p), default_group="C_32",
                      groups=["C_31", "C_32", "TI_31", "ISM_31"])
    r = svc.answer("Ce examene am?")
    assert r["status"] == "unknown"
    assert "Nu am găsit examene" in r["text"]


def test_exam_output_is_markdown_table(svc):
    """Listarea examenelor trebuie să fie un TABEL Markdown."""
    r = svc.answer("Ce examene am?")
    t = r["text"]
    assert "| Data |" in t and "| Disciplină |" in t
    assert "| --- |" in t
    assert "•" not in t                    # fără bullet-uri vechi


def test_not_loaded_when_missing(tmp_path):
    svc = ExamService(data_path=str(tmp_path / "lipsa.json"))
    assert svc.is_loaded() is False
