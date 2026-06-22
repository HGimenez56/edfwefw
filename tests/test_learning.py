"""Testes do aprendizado por feedback (Fase 4)."""

from __future__ import annotations

import json
from pathlib import Path

from donna.skills import learning
from donna.storage import Storage


_counter = 0


def _task_from_sender(store: Storage, sender: str) -> int:
    global _counter
    _counter += 1
    mid = store.add_message(
        source="email", direction="in", external_id=f"m-{sender}-{_counter}",
        sender=sender, subject="x", body="y",
    )
    return store.add_task(title="Tarefa", priority=3, source_msg_id=mid)


def test_done_marks_task_done(tmp_path: Path) -> None:
    store = Storage(tmp_path / "t.db")
    tid = store.add_task(title="X", priority=3)
    learning.apply_task_feedback(store, tid, "done")
    assert store.get_task(tid)["status"] == "done"


def test_important_raises_priority_and_learns_sender(tmp_path: Path) -> None:
    store = Storage(tmp_path / "t.db")
    tid = _task_from_sender(store, "chefe@x.com")
    learning.apply_task_feedback(store, tid, "important")
    assert store.get_task(tid)["priority"] == 2  # 3 -> 2
    prefs = {p["key"]: json.loads(p["value"]) for p in store.get_preferences()}
    assert prefs["chefe@x.com"]["priority"] == "high"


def test_ignore_dismisses_and_deprioritizes_sender(tmp_path: Path) -> None:
    store = Storage(tmp_path / "t.db")
    tid = _task_from_sender(store, "spam@x.com")
    learning.apply_task_feedback(store, tid, "ignore")
    assert store.get_task(tid)["status"] == "dismissed"
    prefs = {p["key"]: json.loads(p["value"]) for p in store.get_preferences()}
    assert prefs["spam@x.com"]["priority"] == "low"


def test_repeated_feedback_accumulates_weight(tmp_path: Path) -> None:
    store = Storage(tmp_path / "t.db")
    t1 = _task_from_sender(store, "vip@x.com")
    t2 = _task_from_sender(store, "vip@x.com")
    learning.apply_task_feedback(store, t1, "important")
    learning.apply_task_feedback(store, t2, "important")
    weight = next(
        p["weight"] for p in store.get_preferences()
        if p["key"] == "vip@x.com"
    )
    assert weight >= 3.0  # 1.0 base + 1 + 1


def test_commitment_feedback(tmp_path: Path) -> None:
    store = Storage(tmp_path / "t.db")
    cid = store.add_commitment(kind="awaiting_my_reply", summary="responder")
    learning.apply_commitment_feedback(store, cid, "resolve")
    assert store.open_commitments() == []
