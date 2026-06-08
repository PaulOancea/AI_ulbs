"""Teste pentru modulul de orar (schedule_service) — izolat de RAG."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.core import schedule_service as sch
from backend.core.schedule_service import ScheduleService


# Structură ca cea reală din API: {success, message, data: [{studyFormation, schedules}]};
# activityType.name = denumirea RO; assistant poate fi null; paritate din isEvenWeek/isOddWeek.
_SCHEDULE = {
    "541": {
        "success": True,
        "message": "ok",
        "data": [{
            "studyFormation": {"name": "C_31/1", "label": "C_31/1"},
            "schedules": [
                {
                    "subject": "Inteligență artificială",
                    "professor": "Florea Adrian",
                    "assistant": None,
                    "room": "Lab 202",
                    "day": "Monday",
                    "activityType": {"name": "Laborator", "label": "L"},
                    "timeSlots": [{"startTime": "08:00", "endTime": "10:00", "timeRange": "08:00 - 10:00"}],
                    "isEvenWeek": False, "isOddWeek": False, "parity": 0,
                },
                {
                    "subject": "Rețele de calculatoare",
                    "professor": "Popescu Ion",
                    "assistant": "Ionescu Ana",
                    "room": "A4",
                    "day": "Thursday",
                    "activityType": {"name": "Curs", "label": "C"},
                    "timeSlots": [{"startTime": "12:00", "endTime": "14:00", "timeRange": "12:00 - 14:00"}],
                    "isEvenWeek": False, "isOddWeek": True, "parity": 1,
                },
            ],
        }],
    }
}


@pytest.fixture
def svc(tmp_path):
    p = tmp_path / "schedule.json"
    p.write_text(json.dumps(_SCHEDULE, ensure_ascii=False), encoding="utf-8")
    return ScheduleService(data_path=str(p), default_formation="541")


# ── Detectarea întrebărilor ───────────────────────────────────────────────────

def test_is_schedule_question():
    assert sch.is_schedule_question("Ce am luni?")
    assert sch.is_schedule_question("La ce oră am rețele?")
    assert sch.is_schedule_question("Unde am laboratorul de IA?")
    assert sch.is_schedule_question("Cine predă rețele?")
    assert not sch.is_schedule_question("Cine este Adrian Florea?")
    assert not sch.is_schedule_question("Care sunt condițiile de promovare?")


def test_loaded_and_lessons(svc):
    assert svc.is_loaded()
    lessons = svc.lessons("541")
    assert len(lessons) == 2
    assert lessons[0].day_ro == "Luni"
    assert lessons[0].activity == "Laborator"


# ── Întrebări tipice ──────────────────────────────────────────────────────────

def test_ce_am_luni(svc):
    a = svc.answer("Ce am luni?")
    assert "Inteligență artificială" in a
    assert "Laborator" in a
    assert "Luni" in a


def test_ce_am_joi(svc):
    a = svc.answer("Ce am joi?")
    assert "Rețele de calculatoare" in a
    assert "Curs" in a


def test_la_ce_ora(svc):
    a = svc.answer("La ce oră am rețele?")
    assert "12:00" in a


def test_unde_am(svc):
    a = svc.answer("Unde am rețele?")
    assert "A4" in a


def test_cine_preda(svc):
    a = svc.answer("Cine predă rețele?")
    assert "Popescu Ion" in a


def test_ora_specifica(svc):
    # „luni de la 08:00" → doar lecția care începe la 08:00
    a = svc.answer("Ce am luni de la 08:00?")
    assert "Inteligență artificială" in a
    assert "Rețele" not in a


def test_ora_in_interval(svc):
    # 13:00 cade în intervalul 12:00–14:00 de joi
    a = svc.answer("Ce am joi la 13:00?")
    assert "Rețele de calculatoare" in a


def test_ora_inexistenta(svc):
    a = svc.answer("Ce am luni de la 15:00?")
    assert "Nu am găsit activități" in a


def test_zi_fara_activitati(svc):
    a = svc.answer("Ce am marți?")
    assert "Nu am găsit activități" in a


def test_not_loaded_when_missing(tmp_path):
    svc = ScheduleService(data_path=str(tmp_path / "lipsa.json"))
    assert svc.is_loaded() is False


def test_url_build():
    from scripts.sync_schedule import build_url
    url = build_url("ing", "541", 5)
    assert url == ("https://schedule.ulbsibiu.ro/api/faculties/ing/"
                   "study-formations/541/schedule?planning_time_unit_id=5")


# ══════════════════════════════════════════════════════════════════════════════
#  SUPORT MULTI-GRUPĂ / SEMIGRUPĂ
# ══════════════════════════════════════════════════════════════════════════════

def _payload(name, lessons):
    return {"success": True, "message": "ok",
            "data": [{"studyFormation": {"name": name, "label": name},
                      "schedules": lessons}]}


def _lesson(subject, prof, room, day, activity, start, end):
    return {
        "subject": subject, "professor": prof, "assistant": None, "room": room,
        "day": day, "activityType": {"name": activity, "label": activity[0]},
        "timeSlots": [{"startTime": start, "endTime": end,
                       "timeRange": f"{start} - {end}"}],
        "isEvenWeek": False, "isOddWeek": False, "parity": 0,
    }


# Date pentru mai multe formații (NU includem 546 = C_32/3 → pentru testul „nesincronizat")
_MULTI = {
    "541": _payload("C_31/1", [_lesson("Programare", "Pop Ion", "Lab 1", "Monday", "Laborator", "08:00", "10:00"),
                               _lesson("Rețele", "Ana Ene", "A4", "Thursday", "Curs", "12:00", "14:00")]),
    "542": _payload("C_31/2", [_lesson("Baze de date", "Marin Dan", "Lab 5", "Monday", "Laborator", "10:00", "12:00")]),
    "544": _payload("C_32/1", [_lesson("Sisteme de operare", "Vlad Ema", "C2", "Thursday", "Curs", "09:00", "11:00")]),
    "557": _payload("TI_31/1", [_lesson("Electronică", "Toma Gheo", "Lab TI", "Tuesday", "Laborator", "14:00", "16:00")]),
    "565": _payload("ISM_31/2", [_lesson("Management", "Ilie Rad", "S3", "Wednesday", "Curs", "16:00", "18:00")]),
}


@pytest.fixture
def multi(tmp_path):
    p = tmp_path / "schedule.json"
    p.write_text(json.dumps(_MULTI, ensure_ascii=False), encoding="utf-8")
    return ScheduleService(data_path=str(p), default_formation="541",
                           default_group="C_31", default_subgroup="1")


def test_default_group_ce_am_joi(multi):
    """Fără grupă în întrebare → grupa implicită (C_31/1)."""
    a = multi.answer("Ce am joi?")
    assert "Rețele" in a and "C_31" in a


def test_other_group_with_subgroup(multi):
    """„C_31 semigrupa 2 luni" → folosește 542, nu grupa implicită."""
    a = multi.answer("Ce are C_31 semigrupa 2 luni?")
    assert "Baze de date" in a
    assert "Programare" not in a   # NU e semigrupa 1


def test_other_group_slash_form(multi):
    a = multi.answer("Ce are C_32/1 joi?")
    assert "Sisteme de operare" in a and "C_32" in a


def test_ti_group_room(multi):
    a = multi.answer("Unde are TI_31 semigrupa 1 laborator?")
    assert "Lab TI" in a


def test_ism_group_time(multi):
    a = multi.answer("La ce oră are ISM_31/2 curs?")
    assert "16:00" in a


def test_bare_number_asks_clarification(multi):
    a = multi.answer("Ce are grupa 31 luni?")
    assert "C_31" in a and "TI_31" in a and "ISM_31" in a
    assert "?" in a   # e o întrebare de clarificare


def test_unsynced_group(multi):
    """Grupă cunoscută în mapă, dar fără orar descărcat (C_32/3 = 546)."""
    a = multi.answer("Ce are C_32 semigrupa 3 joi?")
    assert "sincronizat" in a


def test_writing_variants_map_to_same(multi):
    """Forme diferite de scriere → aceeași semigrupă (C_31/1)."""
    for q in ["Ce are C_31 semigrupa 1 luni?", "Ce are C31/1 luni?",
              "Ce are grupa C_31 sg 1 luni?", "Ce are Calculatoare 31 semigrupa 1 luni?"]:
        a = multi.answer(q)
        assert "Programare" in a, q


# ── „Întreabă o dată, apoi ține minte" (comportamentul din chat) ──────────────

def test_asks_for_group_when_unspecified(multi):
    """Fără grupă în întrebare + ask_if_unspecified → cere grupa (nu presupune)."""
    res = multi.resolve("Ce am joi?", ask_if_unspecified=True)
    assert res.status == "clarify"
    assert res.needs_group is True
    assert "grupă" in res.message.lower()


def test_remembered_group_used_without_reasking(multi):
    """Cu o grupă reținută, întrebările simple NU mai cer grupa."""
    res = multi.resolve("Ce am joi?", remembered="544", ask_if_unspecified=True)
    assert res.status == "ok"
    assert res.formation_id == "544" and res.group == "C_32"


def test_explicit_group_overrides_remembered(multi):
    """O grupă specificată explicit are prioritate față de cea reținută."""
    res = multi.resolve("Ce are TI_31 semigrupa 1 marti?", remembered="544",
                        ask_if_unspecified=True)
    assert res.status == "ok" and res.group == "TI_31" and res.formation_id == "557"


def test_answer_with_forces_formation(multi):
    """answer_with reia întrebarea inițială (chiar cu număr ambiguu) pe grupa aleasă."""
    # întrebarea inițială avea „31" (ambiguu); după ce alegem C_32/1 (544) răspundem pe joi
    a = multi.answer_with("544", "Ce are grupa 31 joi?")
    assert "Sisteme de operare" in a and "C_32" in a


def test_schedule_output_is_markdown_table(multi):
    """Listarea orarului trebuie să fie un TABEL Markdown, nu bullet-uri."""
    a = multi.answer("Ce are C_31 semigrupa 1 luni?")
    assert "| Disciplină |" in a          # antet de tabel
    assert "| --- |" in a                  # separatorul de tabel Markdown
    assert "| Interval |" in a
    assert "•" not in a                    # fără bullet-uri vechi


def test_mentions_group():
    assert sch.mentions_group("C_31 semigrupa 1")
    assert sch.mentions_group("ism_31/2")
    assert sch.mentions_group("grupa 31")
    assert not sch.mentions_group("care e media de promovare?")
    assert not sch.mentions_group("ce am joi")
