"""Teste pentru detectarea termenelor + link Google Calendar."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.core import deadlines as dl


def test_is_deadline_question():
    assert dl.is_deadline_question("Care e termenul de depunere a cererii?")
    assert dl.is_deadline_question("Până când se depun dosarele Erasmus?")
    assert dl.is_deadline_question("Care este data limită pentru bursă?")
    assert not dl.is_deadline_question("Cine este Adrian Florea?")
    assert not dl.is_deadline_question("Cum se calculează media?")


def test_find_deadline_textual_future():
    d = dl.find_deadline("Dosarele se depun până la data de 15 martie 2026.",
                         today=date(2026, 1, 10))
    assert d is not None
    assert d.date_obj == date(2026, 3, 15)
    assert d.passed is False
    assert "martie" in d.display


def test_find_deadline_passed():
    d = dl.find_deadline("Termenul a fost 15 martie 2026.", today=date(2026, 6, 1))
    assert d.passed is True


def test_find_deadline_numeric():
    d = dl.find_deadline("Termen limită: 01.06.2026 pentru depunere.",
                         today=date(2026, 1, 1))
    assert d.date_obj == date(2026, 6, 1)
    assert d.passed is False


def test_find_deadline_picks_near_keyword():
    txt = ("Cursul a început pe 01.10.2025. Termenul limită de depunere este "
           "20 aprilie 2026.")
    d = dl.find_deadline(txt, today=date(2026, 1, 1))
    assert d.date_obj == date(2026, 4, 20)   # data de lângă „termen limită"


def test_find_deadline_none():
    assert dl.find_deadline("Nu există nicio dată aici.", today=date(2026, 1, 1)) is None


def test_build_gcal_url():
    u = dl.build_gcal_url("Termen bursă", date(2026, 3, 15), "detalii")
    assert "calendar.google.com" in u
    assert "action=TEMPLATE" in u
    assert "20260315" in u and "20260316" in u   # eveniment all-day


def test_suggest_title():
    t = dl.suggest_title("Care e termenul de depunere a cererii de bursă?", "cerere-bursa.pdf")
    assert t.startswith("⏰ Termen limită:")
