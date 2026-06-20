"""Testes da extração de tarefas/pendências (Fase 1).

Usam um cérebro falso (sem chamar a OpenAI), então rodam sem credenciais.
"""

from __future__ import annotations

from pathlib import Path

from dona.skills import extraction
from dona.storage import Storage


class FakeBrain:
    """Cérebro falso: `ready=True` e devolve um JSON canned por chamada."""

    def __init__(self, payload):
        self.ready = True
        self._payload = payload
        self.calls = 0

    def extract_json(self, _instruction, _content):
        self.calls += 1
        return self._payload


def test_extraction_creates_tasks_and_commitments(tmp_path: Path) -> None:
    store = Storage(tmp_path / "t.db")
    store.add_message(
        source="email", direction="in", external_id="m1",
        sender="chefe@x.com", recipient="eu@x.com",
        subject="Relatório", body="Me manda o relatório até sexta.",
    )
    brain = FakeBrain(
        {
            "category": "trabalho",
            "tasks": [
                {"title": "Enviar relatório", "priority": 1, "due_at": "2026-06-26"}
            ],
            "commitments": [
                {"kind": "awaiting_my_reply", "who": "chefe@x.com",
                 "summary": "Responder sobre o relatório"}
            ],
        }
    )

    res = extraction.run(store, brain)

    assert res.processed == 1
    assert res.tasks_created == 1
    assert res.commitments_created == 1
    assert brain.calls == 1
    assert len(store.open_tasks()) == 1
    assert len(store.open_commitments()) == 1
    # mensagem foi marcada como processada
    assert store.unprocessed_messages() == []


def test_sent_email_resolves_pending(tmp_path: Path) -> None:
    store = Storage(tmp_path / "t.db")
    store.add_commitment(
        kind="awaiting_my_reply", who="cliente@x.com",
        summary="Cliente espera retorno",
    )
    store.add_message(
        source="email", direction="out", external_id="s1",
        sender="eu@x.com", recipient="cliente@x.com",
        subject="Re: retorno", body="Segue o retorno que combinamos.",
    )
    brain = FakeBrain({"category": "trabalho", "tasks": [], "commitments": []})

    res = extraction.run(store, brain)

    assert res.resolved == 1
    assert store.open_commitments() == []


def test_stub_brain_only_marks_processed(tmp_path: Path) -> None:
    store = Storage(tmp_path / "t.db")
    store.add_message(source="email", direction="in", external_id="m1", subject="oi")

    class StubBrain:
        ready = False

    res = extraction.run(store, StubBrain())
    assert res.processed == 1
    assert res.tasks_created == 0
    assert store.unprocessed_messages() == []
