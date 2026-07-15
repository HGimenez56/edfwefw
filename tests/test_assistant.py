"""Testes da conversa integrada (skills.assistant).

Garantem que a conversa livre recebe os DADOS REAIS do banco (nada de listas
inventadas) e que a Donna lembra do histórico recente.
"""

from __future__ import annotations

from pathlib import Path

from donna.skills import assistant
from donna.storage import Storage

TZ = "America/Sao_Paulo"


class CapturingBrain:
    """Fake que captura o que a conversa envia ao modelo."""

    ready = True

    def __init__(self):
        self.last_context = None
        self.last_history = None

    def converse(self, user_message, *, context="", history=None, **_k):
        self.last_context = context
        self.last_history = history
        return "resposta da donna"


def test_context_contains_real_tasks_and_commitments(tmp_path: Path) -> None:
    store = Storage(tmp_path / "t.db")
    store.add_task(title="Enviar proposta Acme", priority=1, due_at="2026-07-20")
    store.add_commitment(
        kind="awaiting_my_reply", who="Cliente Acme", summary="Responder sobre prazo"
    )
    brain = CapturingBrain()

    reply = assistant.converse(store, brain, TZ, "me mande a lista de pendências")

    assert reply == "resposta da donna"
    assert "Enviar proposta Acme" in brain.last_context
    assert "Responder sobre prazo" in brain.last_context
    assert "AGENDA DE HOJE" in brain.last_context


def test_context_says_empty_when_no_data(tmp_path: Path) -> None:
    store = Storage(tmp_path / "t.db")
    brain = CapturingBrain()
    assistant.converse(store, brain, TZ, "oi")
    assert "(nenhuma)" in brain.last_context


def test_history_is_remembered_between_turns(tmp_path: Path) -> None:
    store = Storage(tmp_path / "t.db")
    brain = CapturingBrain()

    assistant.converse(store, brain, TZ, "meu cliente mais importante é a Acme")
    assistant.converse(store, brain, TZ, "qual é meu cliente mais importante?")

    roles_texts = brain.last_history
    assert ("user", "meu cliente mais importante é a Acme") in roles_texts
    assert ("assistant", "resposta da donna") in roles_texts


def test_chat_log_not_picked_by_extraction(tmp_path: Path) -> None:
    # A conversa com a Donna NÃO pode virar tarefa via extração.
    store = Storage(tmp_path / "t.db")
    brain = CapturingBrain()
    assistant.converse(store, brain, TZ, "oi Donna")
    assert store.unprocessed_messages() == []
