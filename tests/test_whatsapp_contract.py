"""Testes do contrato do sidecar de WhatsApp pelo lado Python (Fase 3).

O sidecar Node escreve na tabela `messages` com source='whatsapp'. Aqui
simulamos exatamente essa inserção e confirmamos que o pipeline existente
(extração) processa a mensagem como qualquer outra — sem precisar do WhatsApp
real nem do Node.
"""

from __future__ import annotations

from pathlib import Path

from donna.skills import extraction
from donna.storage import Storage


class FakeBrain:
    ready = True

    def __init__(self, payload):
        self._payload = payload

    def extract_json(self, _instruction, _content):
        return self._payload


def _insert_like_sidecar(store: Storage, *, direction: str, ext_id: str,
                         sender: str, recipient: str, body: str):
    """Replica o INSERT que o index.js faz (source='whatsapp')."""
    return store.add_message(
        source="whatsapp", direction=direction, external_id=ext_id,
        sender=sender, recipient=recipient, body=body,
    )


def test_whatsapp_incoming_becomes_task(tmp_path: Path) -> None:
    store = Storage(tmp_path / "t.db")
    _insert_like_sidecar(
        store, direction="in", ext_id="wa1",
        sender="Cliente X", recipient="me",
        body="Consegue me mandar a proposta amanhã?",
    )
    brain = FakeBrain({
        "category": "trabalho",
        "tasks": [{"title": "Enviar proposta", "priority": 2, "due_at": None}],
        "commitments": [{"kind": "awaiting_my_reply", "who": "Cliente X",
                         "summary": "Responder sobre a proposta"}],
    })
    res = extraction.run(store, brain)
    assert res.tasks_created == 1
    assert res.commitments_created == 1
    assert len(store.open_tasks()) == 1


def test_whatsapp_dedup_same_id(tmp_path: Path) -> None:
    store = Storage(tmp_path / "t.db")
    first = _insert_like_sidecar(
        store, direction="in", ext_id="wa-dup",
        sender="Amigo", recipient="me", body="bora sábado?",
    )
    dup = _insert_like_sidecar(
        store, direction="in", ext_id="wa-dup",
        sender="Amigo", recipient="me", body="bora sábado?",
    )
    assert isinstance(first, int)
    assert dup is None


def test_whatsapp_sent_resolves_pending(tmp_path: Path) -> None:
    store = Storage(tmp_path / "t.db")
    store.add_commitment(
        kind="awaiting_my_reply", who="Amigo", summary="responder o amigo"
    )
    _insert_like_sidecar(
        store, direction="out", ext_id="wa-out",
        sender="me", recipient="Amigo", body="fechado, sábado então!",
    )
    res = extraction.run(store, FakeBrain({"tasks": [], "commitments": []}))
    assert res.resolved == 1
    assert store.open_commitments() == []
