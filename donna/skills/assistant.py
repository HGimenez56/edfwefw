"""Conversa integrada: a Donna responde com base nos DADOS REAIS.

Antes, a conversa livre chamava o modelo sem nenhum acesso ao banco — e ele
inventava tarefas/pendências genéricas. Este módulo monta um snapshot real
(tarefas, pendências, agenda, rascunhos) + o histórico recente da conversa e
passa tudo ao cérebro. Também registra cada turno, então a Donna "lembra" do
que acabou de ser dito e o contexto melhora com o uso.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..brain import Brain
from ..storage import Storage
from . import agenda


def build_context(storage: Storage, tz_name: str) -> str:
    """Snapshot em texto do estado real, para injetar no prompt."""
    parts: list[str] = []
    now = datetime.now(timezone.utc).astimezone().strftime("%d/%m/%Y %H:%M")
    parts.append(f"Agora: {now}")

    tasks = storage.open_tasks(limit=20)
    parts.append(f"\nTAREFAS EM ABERTO ({len(tasks)}):")
    if tasks:
        for t in tasks:
            due = f" | prazo: {t['due_at']}" if t["due_at"] else ""
            cat = f" | {t['category']}" if t["category"] else ""
            parts.append(f"- [P{t['priority']}]{cat} {t['title']}{due}")
    else:
        parts.append("- (nenhuma)")

    commitments = storage.open_commitments(limit=20)
    parts.append(f"\nPENDÊNCIAS EM ABERTO ({len(commitments)}):")
    if commitments:
        for c in commitments:
            who = f" | com: {c['who']}" if c["who"] else ""
            parts.append(f"- [{c['kind']}]{who} {c['summary']}")
    else:
        parts.append("- (nenhuma)")

    parts.append("\nAGENDA DE HOJE:")
    parts.extend(agenda.today_events(storage, tz_name))

    drafts = storage.pending_drafts(limit=5)
    if drafts:
        parts.append(f"\nRASCUNHOS AGUARDANDO APROVAÇÃO: {len(drafts)}")

    return "\n".join(parts)


def converse(
    storage: Storage, brain: Brain, tz_name: str, user_text: str
) -> str:
    """Um turno de conversa: contexto real + histórico + registro."""
    context = build_context(storage, tz_name)
    history = [
        ("user" if row["direction"] == "in" else "assistant", row["body"])
        for row in storage.recent_chat(limit=12)
    ]
    reply = brain.converse(user_text, context=context, history=history)
    storage.log_chat("in", user_text)
    storage.log_chat("out", reply)
    return reply
