"""Ingestão de calendário (Fase 2).

Lê eventos de duas origens, ambas pela mesma rotina de parsing:
- um **ICS publicado** do Outlook (URL read-only que você gera no Outlook web);
- convites `.ics` que chegam anexados em e-mails (texto `text/calendar`).

O parsing normaliza tudo para `CalendarEvent` com datas *aware* em UTC, para o
filtro de "hoje"/"semana" funcionar de forma consistente independente do fuso
de origem. A busca por URL é a única parte que toca a rede — o parsing em si é
testável com um `.ics` de exemplo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import requests
from icalendar import Calendar

from ..config import Settings
from ..storage import Storage

logger = logging.getLogger(__name__)


@dataclass
class CalendarEvent:
    uid: str
    summary: str
    start_at: datetime          # aware, UTC
    end_at: Optional[datetime]  # aware, UTC
    location: str = ""
    organizer: str = ""
    status: str = ""

    def start_iso(self) -> str:
        return self.start_at.isoformat()

    def end_iso(self) -> Optional[str]:
        return self.end_at.isoformat() if self.end_at else None


def _to_utc(value, tz: ZoneInfo) -> Optional[datetime]:
    """Converte um valor de data/datetime do icalendar para datetime UTC aware."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:  # datetime "flutuante": assume o fuso do dono
            dt = dt.replace(tzinfo=tz)
    elif isinstance(value, date):  # evento de dia inteiro
        dt = datetime.combine(value, time(0, 0), tzinfo=tz)
    else:
        return None
    return dt.astimezone(timezone.utc)


def parse_ics(data: str | bytes, tz_name: str = "UTC") -> list[CalendarEvent]:
    """Faz o parsing de um conteúdo ICS em eventos normalizados (UTC)."""
    tz = ZoneInfo(tz_name)
    cal = Calendar.from_ical(data)
    events: list[CalendarEvent] = []
    for comp in cal.walk("VEVENT"):
        start = _to_utc(_get(comp, "DTSTART"), tz)
        if start is None:
            continue
        events.append(
            CalendarEvent(
                uid=str(comp.get("UID") or ""),
                summary=str(comp.get("SUMMARY") or "(sem título)"),
                start_at=start,
                end_at=_to_utc(_get(comp, "DTEND"), tz),
                location=str(comp.get("LOCATION") or ""),
                organizer=str(comp.get("ORGANIZER") or ""),
                status=str(comp.get("STATUS") or "").lower(),
            )
        )
    return events


def _get(comp, key):
    prop = comp.get(key)
    return prop.dt if prop is not None else None


def store_events(
    storage: Storage, events: list[CalendarEvent], source: str
) -> int:
    """Persiste eventos. Retorna quantos eram novos (não-dup)."""
    new = 0
    for ev in events:
        if storage.add_event(
            summary=ev.summary,
            start_at=ev.start_iso(),
            end_at=ev.end_iso(),
            uid=ev.uid,
            location=ev.location,
            organizer=ev.organizer,
            status=ev.status,
            source=source,
        ) is not None:
            new += 1
    if new:
        logger.info("Calendário: %d evento(s) novo(s) de %s.", new, source)
    return new


def sync_calendar(settings: Settings, storage: Storage) -> int:
    """Busca o ICS publicado (se configurado) e persiste os eventos."""
    if not settings.calendar_ready:
        return 0
    resp = requests.get(settings.calendar_ics_url, timeout=30)
    resp.raise_for_status()
    events = parse_ics(resp.content, settings.timezone)
    return store_events(storage, events, source="ics_url")
