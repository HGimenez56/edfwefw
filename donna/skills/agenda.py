"""Agenda: janelas de tempo e formatação de eventos para exibição.

Os eventos ficam guardados em UTC; aqui convertemos de volta para o fuso do
dono na hora de mostrar, e calculamos as janelas de "hoje" e "esta semana"
nesse fuso. Reutilizado pelo briefing e pelo comando /agenda.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from ..storage import Storage


def _day_bounds_utc(tz_name: str, day_offset: int = 0) -> tuple[str, str]:
    tz = ZoneInfo(tz_name)
    today = datetime.now(tz).date() + timedelta(days=day_offset)
    start = datetime.combine(today, time(0, 0), tzinfo=tz)
    end = start + timedelta(days=1)
    return start.astimezone(ZoneInfo("UTC")).isoformat(), end.astimezone(
        ZoneInfo("UTC")
    ).isoformat()


def _week_bounds_utc(tz_name: str) -> tuple[str, str]:
    tz = ZoneInfo(tz_name)
    today = datetime.now(tz).date()
    start = datetime.combine(today, time(0, 0), tzinfo=tz)
    end = start + timedelta(days=7)
    return start.astimezone(ZoneInfo("UTC")).isoformat(), end.astimezone(
        ZoneInfo("UTC")
    ).isoformat()


def _fmt_event(row, tz_name: str, with_date: bool = False) -> str:
    tz = ZoneInfo(tz_name)
    start = datetime.fromisoformat(row["start_at"]).astimezone(tz)
    when = start.strftime("%d/%m %H:%M") if with_date else start.strftime("%H:%M")
    loc = f" 📍{row['location']}" if row["location"] else ""
    return f"  🕘 {when} — {row['summary']}{loc}"


def today_events(storage: Storage, tz_name: str) -> list[str]:
    start, end = _day_bounds_utc(tz_name)
    rows = storage.events_between(start, end)
    if not rows:
        return ["  • (sem reuniões hoje) 🙌"]
    return [_fmt_event(r, tz_name) for r in rows]


def week_events(storage: Storage, tz_name: str) -> list[str]:
    start, end = _week_bounds_utc(tz_name)
    rows = storage.events_between(start, end)
    if not rows:
        return ["  • (sem reuniões na semana)"]
    return [_fmt_event(r, tz_name, with_date=True) for r in rows]


def build_agenda(storage: Storage, tz_name: str) -> str:
    """Texto da agenda de hoje (comando /agenda)."""
    lines = ["🗓️ *Sua agenda de hoje*", ""]
    lines.extend(today_events(storage, tz_name))
    return "\n".join(lines)
