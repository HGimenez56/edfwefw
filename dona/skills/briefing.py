"""Montagem dos textos de briefing diário e prévia semanal.

Fase 1: monta a partir de tarefas e pendências em aberto. A agenda (reuniões do
dia/semana) entra na Fase 2, quando o adapter de calendário existir — os pontos
de inserção já estão marcados.
"""

from __future__ import annotations

from datetime import date

from ..storage import Storage

_PRIORITY_EMOJI = {1: "🔴", 2: "🟠", 3: "🟡", 4: "🟢", 5: "⚪"}


def _format_tasks(storage: Storage, limit: int = 10) -> list[str]:
    tasks = storage.open_tasks(limit=limit)
    if not tasks:
        return ["  • (nenhuma tarefa em aberto) 🎉"]
    lines = []
    for t in tasks:
        emoji = _PRIORITY_EMOJI.get(t["priority"], "🟡")
        due = f" — ⏰ {t['due_at']}" if t["due_at"] else ""
        lines.append(f"  {emoji} {t['title']}{due}")
    return lines


def _format_commitments(storage: Storage, limit: int = 10) -> list[str]:
    items = storage.open_commitments(limit=limit)
    awaiting = [c for c in items if c["kind"] == "awaiting_my_reply"]
    if not awaiting:
        return ["  • (sem pendências de resposta) 👍"]
    lines = []
    for c in awaiting:
        who = f" — {c['who']}" if c["who"] else ""
        lines.append(f"  🔔 {c['summary']}{who}")
    return lines


def build_daily_briefing(storage: Storage) -> str:
    """Texto do briefing diário."""
    today = date.today().strftime("%d/%m/%Y")
    parts = [f"☀️ *Bom dia! Briefing de {today}*", ""]

    # [Fase 2] agenda do dia entra aqui.

    parts.append("📋 *Prioridades de hoje*")
    parts.extend(_format_tasks(storage))
    parts.append("")
    parts.append("🔔 *Esperando sua resposta*")
    parts.extend(_format_commitments(storage))
    return "\n".join(parts)


def build_weekly_preview(storage: Storage) -> str:
    """Texto da prévia semanal (domingo)."""
    parts = ["🗓️ *Prévia da semana*", ""]

    # [Fase 2] reuniões e entregas da semana entram aqui.

    parts.append("📋 *Tarefas em aberto*")
    parts.extend(_format_tasks(storage, limit=15))
    parts.append("")
    parts.append("🔔 *Pendências para resolver*")
    parts.extend(_format_commitments(storage, limit=15))
    return "\n".join(parts)
