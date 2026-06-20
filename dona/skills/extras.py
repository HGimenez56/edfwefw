"""Extras de valor (Fase 5), todos sobre dados já armazenados.

- recap de fim de dia + prévia do dia seguinte;
- resumo semanal do que foi concluído;
- preparação de reunião (junta as mensagens recentes com a contraparte).

Nada aqui exige conexão ativa: opera sobre o que já está no banco. A prep de
reunião usa o cérebro para resumir, mas degrada para uma lista crua se a OpenAI
não estiver configurada.
"""

from __future__ import annotations

import re
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from ..brain import Brain
from ..storage import Storage
from . import agenda

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+")


def _utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def build_daily_recap(storage: Storage, tz_name: str) -> str:
    """Recap do dia: concluídas hoje + agenda de amanhã + pendências quentes."""
    tz = ZoneInfo(tz_name)
    today = datetime.now(tz).date()
    day_start = datetime.combine(today, time(0, 0), tzinfo=tz)
    day_end = day_start + timedelta(days=1)

    done = storage.tasks_completed_between(_utc(day_start), _utc(day_end))
    parts = ["🌙 *Recap do dia*", ""]
    parts.append("✅ *Concluído hoje*")
    if done:
        parts.extend(f"  • {t['title']}" for t in done)
    else:
        parts.append("  • (nada marcado como feito hoje)")

    parts.append("")
    parts.append("🗓️ *Amanhã*")
    tomorrow_start = _utc(day_start + timedelta(days=1))
    tomorrow_end = _utc(day_start + timedelta(days=2))
    rows = storage.events_between(tomorrow_start, tomorrow_end)
    if rows:
        for r in rows:
            start = datetime.fromisoformat(r["start_at"]).astimezone(tz)
            parts.append(f"  🕘 {start.strftime('%H:%M')} — {r['summary']}")
    else:
        parts.append("  • (sem reuniões amanhã)")
    return "\n".join(parts)


def build_weekly_accomplishments(storage: Storage, tz_name: str) -> str:
    """Resumo do que foi concluído nos últimos 7 dias."""
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    start = _utc(now - timedelta(days=7))
    done = storage.tasks_completed_between(start, _utc(now))
    parts = ["🏆 *O que você entregou na semana*", ""]
    if done:
        parts.extend(f"  • {t['title']}" for t in done)
    else:
        parts.append("  • (nenhuma tarefa concluída registrada)")
    return "\n".join(parts)


def build_meeting_prep(storage: Storage, brain: Brain, tz_name: str) -> str:
    """Junta o contexto recente para a próxima reunião."""
    now_utc = datetime.now(timezone.utc).isoformat()
    event = storage.next_event(now_utc)
    if event is None:
        return "Não encontrei nenhuma reunião futura na agenda."

    tz = ZoneInfo(tz_name)
    start = datetime.fromisoformat(event["start_at"]).astimezone(tz)
    header = (
        f"📋 *Prep: {event['summary']}*\n"
        f"🕘 {start.strftime('%d/%m %H:%M')}\n"
    )

    # Tenta achar a contraparte pelo organizador.
    contact = ""
    match = _EMAIL_RE.search(event["organizer"] or "")
    if match:
        contact = match.group(0)

    if not contact:
        return header + "\n(Sem contato identificável para buscar histórico.)"

    msgs = storage.messages_for_contact(contact, limit=8)
    if not msgs:
        return header + f"\nSem mensagens recentes com {contact}."

    digest = "\n\n".join(
        f"[{m['direction']}] {m['subject']}\n{(m['body'] or '')[:500]}"
        for m in msgs
    )
    if not brain.ready:
        return header + f"\nÚltimas trocas com {contact}:\n\n{digest[:1500]}"

    summary = brain.chat(
        "Resuma em tópicos curtos o histórico abaixo e liste 2-3 pontos de "
        f"atenção para a reunião '{event['summary']}'. Seja objetivo.\n\n{digest}"
    )
    return header + "\n" + summary
