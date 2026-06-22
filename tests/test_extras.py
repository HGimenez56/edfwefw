"""Testes dos extras (Fase 5): recap, resumo semanal e prep de reunião."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from donna.skills import extras
from donna.storage import Storage

TZ = "America/Sao_Paulo"


class FakeBrain:
    ready = True

    def chat(self, *_a, **_k):
        return "Resumo do modelo."


class StubBrain:
    ready = False


def test_recap_lists_done_today(tmp_path: Path) -> None:
    store = Storage(tmp_path / "t.db")
    tid = store.add_task(title="Fechei a proposta", priority=2)
    store.set_task_status(tid, "done")  # updated_at = agora (hoje)
    text = extras.build_daily_recap(store, TZ)
    assert "Recap do dia" in text
    assert "Fechei a proposta" in text


def test_weekly_accomplishments(tmp_path: Path) -> None:
    store = Storage(tmp_path / "t.db")
    tid = store.add_task(title="Entreguei o relatório", priority=1)
    store.set_task_status(tid, "done")
    text = extras.build_weekly_accomplishments(store, TZ)
    assert "Entreguei o relatório" in text


def test_meeting_prep_no_event(tmp_path: Path) -> None:
    store = Storage(tmp_path / "t.db")
    text = extras.build_meeting_prep(store, StubBrain(), TZ)
    assert "nenhuma reunião" in text.lower()


def test_meeting_prep_with_history(tmp_path: Path) -> None:
    store = Storage(tmp_path / "t.db")
    soon = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    store.add_event(
        summary="Reunião Cliente X", start_at=soon, uid="e1",
        organizer="mailto:cliente@x.com", source="ics_url",
    )
    store.add_message(
        source="email", direction="in", external_id="m1",
        sender="cliente@x.com", recipient="eu@x.com",
        subject="Dúvida no contrato", body="Preciso revisar a cláusula 4.",
    )
    # com cérebro real (fake) → resume
    text = extras.build_meeting_prep(store, FakeBrain(), TZ)
    assert "Reunião Cliente X" in text
    assert "Resumo do modelo." in text
    # sem cérebro → mostra o histórico cru
    raw = extras.build_meeting_prep(store, StubBrain(), TZ)
    assert "cláusula 4" in raw
