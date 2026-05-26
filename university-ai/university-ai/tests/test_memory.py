"""Teste pentru memoria conversațională."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.core.memory import ConversationMemory, MemoryManager


def test_memory_basic():
    m = ConversationMemory(window=3)
    m.add_user("Ce e media?")
    m.add_assistant("E media notelor.")
    assert len(m) == 2
    ctx = m.get_context_str()
    assert "Student" in ctx
    assert "Asistent" in ctx


def test_memory_window_limit():
    m = ConversationMemory(window=2)  # max 4 mesaje (2 schimburi)
    for i in range(5):
        m.add_user(f"q{i}")
        m.add_assistant(f"a{i}")
    # Ar trebui să rămână doar ultimele 2 schimburi = 4 mesaje
    assert len(m) == 4


def test_memory_manager_sessions():
    mgr = MemoryManager()
    s1 = mgr.get_or_create("user1")
    s2 = mgr.get_or_create("user2")
    s1.add_user("test")
    assert len(s1) == 1
    assert len(s2) == 0  # sesiuni izolate


def test_memory_clear():
    m = ConversationMemory()
    m.add_user("x")
    m.add_assistant("y")
    m.clear()
    assert len(m) == 0
