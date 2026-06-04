"""Teste pentru funcționalitățile noi: diacritice, pin, arhivare, căutare,
partajare, editare mesaje."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import settings
from backend.auth import database as db
from backend.auth import service as svc
from backend.text_utils import (
    normalize, strip_diacritics, looks_repetitive, trim_repetition,
    looks_like_no_answer,
)
from backend.core.retriever import tokenize
from backend.core.prompts import detect_appellative, build_rag_prompt


# ── Diacritice ────────────────────────────────────────────────────────────────

def test_strip_diacritics():
    assert strip_diacritics("condiții") == "conditii"
    assert strip_diacritics("ședință") == "sedinta"
    assert strip_diacritics("ÂÎĂȘȚ") == "AIAST"
    # variantele vechi cu sedilă
    assert strip_diacritics("şedinţă") == "sedinta"


def test_tokenize_diacritic_insensitive():
    assert tokenize("condiții de promovare") == tokenize("conditii de promovare")
    assert "conditii" in tokenize("Condiții")


# ── Protecție anti-buclă (repetiție LLM) ─────────────────────────────────────

def test_looks_repetitive_detects_loop():
    s = "Aceasta este o propoziție repetată la nesfârșit. " * 15  # > 300 caractere
    assert looks_repetitive(s) is True


def test_looks_repetitive_false_on_normal_text():
    s = ("Bursa socială se acordă în condiții de venit. "
         "Bursa de merit se acordă pentru rezultate. "
         "Procedura se desfășoară la secretariat.")
    assert looks_repetitive(s) is False


def test_trim_repetition_keeps_one_copy():
    s = "Conținut util. Repet. Repet. Repet. Repet."
    out = trim_repetition(s)
    assert out.count("Repet.") == 1
    assert "Conținut util." in out


# ── Detectarea răspunsurilor „nu am găsit" (pentru a NU afișa surse) ─────────

def test_looks_like_no_answer_true():
    assert looks_like_no_answer(
        "Îmi pare rău, dar nu am găsit nicio meniu pentru cantină în documente.")
    assert looks_like_no_answer(
        "Pe baza documentelor, vă recomand să consultați direct secretariatul facultății.")
    assert looks_like_no_answer("Nu am identificat această informație.")


def test_looks_like_no_answer_false():
    assert not looks_like_no_answer(
        "Conform Art. 5, media minimă pentru promovare este 5.")
    assert not looks_like_no_answer(
        "Bursa socială se acordă studenților cu venituri reduse.")


# ── Fixture DB temporară ────────────────────────────────────────────────────

@pytest.fixture
def fresh_db(tmp_path):
    settings.database_path = str(tmp_path / "test.db")
    db._INITIALIZED = False
    user = svc.register_user("tester", "tester@example.com", "parola123")
    yield user


# ── Pin / ordonare ────────────────────────────────────────────────────────────

def test_pin_orders_first(fresh_db):
    user = fresh_db
    svc.create_chat(user["id"], "Prima")
    c2 = svc.create_chat(user["id"], "A doua")
    assert svc.set_pinned(c2["id"], user["id"], True)
    chats = svc.list_user_chats(user["id"])
    assert chats[0]["id"] == c2["id"]  # fixată → prima
    assert svc.set_pinned(c2["id"], user["id"], False)


# ── Arhivare ────────────────────────────────────────────────────────────────

def test_archive_hides_chat(fresh_db):
    user = fresh_db
    c = svc.create_chat(user["id"], "De arhivat")
    svc.set_archived(c["id"], user["id"], True)
    visible = svc.list_user_chats(user["id"])
    assert all(x["id"] != c["id"] for x in visible)
    with_arch = svc.list_user_chats(user["id"], include_archived=True)
    assert any(x["id"] == c["id"] for x in with_arch)


# ── Căutare după titlu (insensibilă la diacritice) ────────────────────────────

def test_search_by_title_diacritic_insensitive(fresh_db):
    user = fresh_db
    svc.create_chat(user["id"], "Ședință de promovare")
    svc.create_chat(user["id"], "Cu totul altceva")
    res = svc.list_user_chats(user["id"], search="sedinta")
    assert len(res) == 1
    assert "Ședință" in res[0]["title"]


# ── Partajare ────────────────────────────────────────────────────────────────

def test_sharing_lifecycle(fresh_db):
    user = fresh_db
    c = svc.create_chat(user["id"], "Partajabilă")
    token = svc.enable_sharing(c["id"], user["id"])
    assert token
    assert svc.get_shared_chat(token)["id"] == c["id"]
    # reapelarea refolosește același token
    assert svc.enable_sharing(c["id"], user["id"]) == token
    # oprire → token invalid
    assert svc.disable_sharing(c["id"], user["id"])
    assert svc.get_shared_chat(token) is None


# ── Editare mesaj (trunchiere + marcaj edited) ───────────────────────────────

def test_edit_truncates_following_messages(fresh_db):
    user = fresh_db
    c = svc.create_chat(user["id"], "Edit")
    m1 = svc.add_message(c["id"], "user", "intrebarea 1")
    svc.add_message(c["id"], "assistant", "raspuns 1")
    svc.add_message(c["id"], "user", "intrebarea 2")
    # editarea lui m1 șterge m1 + tot ce urmează (3 mesaje)
    assert svc.delete_messages_from(c["id"], m1) == 3
    assert svc.get_messages(c["id"]) == []


# ── Ton adaptiv + regula anti-duplicat (prompt) ──────────────────────────────

def test_detect_appellative():
    assert detect_appellative("Sefule, cine e X?") == "șefule"
    assert detect_appellative("Regele meu, cât e media?") == "regele meu"
    assert detect_appellative("frate, ajuta-ma") == "frate"
    assert detect_appellative("Care sunt condițiile de promovare?") is None


def test_prompt_includes_tone_and_dedup_rule():
    chunks = [{"text": "tabel", "source": "t.pdf", "page": 1, "section": ""}]
    # Instrucțiunea generală de ton e prezentă MEREU (și fără apelativ explicit)
    p = build_rag_prompt("Sefule cine e Florea?", chunks)
    p2 = build_rag_prompt("Care sunt condițiile?", chunks)
    assert "ADAPTARE TON" in p and "ADAPTARE TON" in p2
    assert "ENTITĂȚI DUPLICATE" in p           # regula anti-duplicat prezentă
    # nuanța „familiar" apare doar când utilizatorul folosește un apelativ
    assert "la fel de" in p
    assert "la fel de" not in p2


def test_update_message_marks_edited(fresh_db):
    user = fresh_db
    c = svc.create_chat(user["id"], "Edit2")
    mid = svc.add_message(c["id"], "user", "text vechi")
    assert svc.update_message(mid, c["id"], "text nou")
    msgs = svc.get_messages(c["id"])
    assert msgs[0]["content"] == "text nou"
    assert msgs[0]["edited"] == 1
