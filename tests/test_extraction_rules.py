"""Testes das regras de extração: grupos, nomes do dono e contexto no prompt."""

from __future__ import annotations

from pathlib import Path

from donna.skills import extraction
from donna.storage import Storage


class CapturingBrain:
    """Captura instrução e conteúdo enviados ao modelo."""

    ready = True

    def __init__(self):
        self.instructions: list[str] = []
        self.contents: list[str] = []

    def extract_json(self, instruction, content):
        self.instructions.append(instruction)
        self.contents.append(content)
        return {"category": "pessoal", "tasks": [], "commitments": []}


def test_instruction_includes_owner_names_and_group_rule() -> None:
    text = extraction.build_instruction("Henrique, Laplace")
    assert "Henrique" in text
    assert "Laplace" in text
    assert "MENSAGEM DE GRUPO" in text
    assert "AUTOEXPLICATIVO" in text  # summaries legíveis


def test_instruction_without_names_still_protects_groups() -> None:
    text = extraction.build_instruction("")
    assert "MENSAGEM DE GRUPO" in text


def test_group_message_is_flagged_as_group_in_content(tmp_path: Path) -> None:
    store = Storage(tmp_path / "t.db")
    store.add_message(
        source="whatsapp", direction="in", external_id="g1",
        sender="João", recipient="me",
        subject="[grupo] 123@g.us",
        body="alguém chamou goleiro?",
    )
    brain = CapturingBrain()
    extraction.run(store, brain, owner_names="Henrique,Laplace")
    assert "GRUPO de WhatsApp" in brain.contents[0]
    assert "Henrique" in brain.instructions[0]


def test_mentioned_group_message_is_flagged_directed(tmp_path: Path) -> None:
    store = Storage(tmp_path / "t.db")
    store.add_message(
        source="whatsapp", direction="in", external_id="m1",
        sender="João", recipient="me",
        subject="[grupo][mencionado] 123@g.us",
        body="@Cana confirma o goleiro?",
    )
    brain = CapturingBrain()
    extraction.run(store, brain, owner_names="Henrique,Laplace,Gimenez,Cana")
    assert "FOI @MENCIONADO" in brain.contents[0]
    assert "[mencionado]" in brain.instructions[0]
    assert "Cana" in brain.instructions[0]


def test_individual_whatsapp_is_flagged_individual(tmp_path: Path) -> None:
    store = Storage(tmp_path / "t.db")
    store.add_message(
        source="whatsapp", direction="in", external_id="i1",
        sender="Cliente X", recipient="me", body="me manda a proposta?",
    )
    brain = CapturingBrain()
    extraction.run(store, brain)
    assert "conversa INDIVIDUAL" in brain.contents[0]
