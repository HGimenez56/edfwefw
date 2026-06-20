"""Testes do parsing de calendário e da agenda (Fase 2).

Não tocam a rede: usam um ICS de exemplo embutido.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from dona.ingest import calendar as cal
from dona.skills import agenda
from dona.storage import Storage

# ICS com fuso explícito (UTC) e um evento de dia inteiro.
SAMPLE_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Teste//Dona//PT
BEGIN:VEVENT
UID:evt-1
SUMMARY:Reunião com Cliente X
DTSTART:20260622T130000Z
DTEND:20260622T140000Z
LOCATION:Teams
ORGANIZER:mailto:chefe@x.com
STATUS:CONFIRMED
END:VEVENT
BEGIN:VEVENT
UID:evt-2
SUMMARY:Feriado
DTSTART;VALUE=DATE:20260623
END:VEVENT
END:VCALENDAR
"""


def test_parse_ics_normalizes_to_utc() -> None:
    events = cal.parse_ics(SAMPLE_ICS, "America/Sao_Paulo")
    assert len(events) == 2
    e1 = next(e for e in events if e.uid == "evt-1")
    assert e1.summary == "Reunião com Cliente X"
    assert e1.start_at.tzinfo is not None
    assert e1.start_at == datetime(2026, 6, 22, 13, 0, tzinfo=timezone.utc)


def test_store_events_dedups(tmp_path: Path) -> None:
    store = Storage(tmp_path / "t.db")
    events = cal.parse_ics(SAMPLE_ICS, "America/Sao_Paulo")
    assert cal.store_events(store, events, "ics_url") == 2
    assert cal.store_events(store, events, "ics_url") == 0


def test_agenda_filters_today(tmp_path: Path) -> None:
    store = Storage(tmp_path / "t.db")
    tz = "America/Sao_Paulo"
    # cria um evento daqui a 2 horas (hoje) e outro daqui a 3 dias
    now = datetime.now(timezone.utc)
    store.add_event(
        summary="Hoje cedo", start_at=(now + timedelta(hours=2)).isoformat(),
        uid="hoje", source="ics_url",
    )
    store.add_event(
        summary="Daqui a dias", start_at=(now + timedelta(days=3)).isoformat(),
        uid="depois", source="ics_url",
    )
    lines = agenda.today_events(store, tz)
    joined = "\n".join(lines)
    assert "Hoje cedo" in joined
    assert "Daqui a dias" not in joined


def test_cancelled_event_hidden(tmp_path: Path) -> None:
    store = Storage(tmp_path / "t.db")
    now = datetime.now(timezone.utc)
    store.add_event(
        summary="Cancelada", start_at=(now + timedelta(hours=1)).isoformat(),
        uid="x", status="cancelled", source="ics_url",
    )
    assert "Cancelada" not in "\n".join(agenda.today_events(store, "America/Sao_Paulo"))
