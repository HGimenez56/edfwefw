"""Testes da montagem dos briefings (Fase 1)."""

from __future__ import annotations

from pathlib import Path

from donna.skills import briefing
from donna.storage import Storage


def test_daily_briefing_empty(tmp_path: Path) -> None:
    store = Storage(tmp_path / "t.db")
    text = briefing.build_daily_briefing(store)
    assert "Briefing" in text
    assert "nenhuma tarefa em aberto" in text


def test_daily_briefing_with_items(tmp_path: Path) -> None:
    store = Storage(tmp_path / "t.db")
    store.add_task(title="Enviar proposta", priority=1, due_at="2026-06-26")
    store.add_commitment(
        kind="awaiting_my_reply", who="Cliente X", summary="Responder o cliente"
    )
    text = briefing.build_daily_briefing(store)
    assert "Enviar proposta" in text
    assert "Responder o cliente" in text
    assert "Cliente X" in text


def test_weekly_preview(tmp_path: Path) -> None:
    store = Storage(tmp_path / "t.db")
    store.add_task(title="Fechar trimestre", priority=2)
    text = briefing.build_weekly_preview(store)
    assert "Prévia da semana" in text
    assert "Fechar trimestre" in text
