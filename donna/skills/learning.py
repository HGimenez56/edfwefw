"""Aprendizado por feedback (Fase 4).

Quando o dono reage a um item (👍 importante / 👎 ignorar / ✅ feito / ⏰ adiar),
a Donna (1) atualiza o estado do item e (2) ajusta preferências — em especial o
peso/prioridade do remetente de origem. Essas preferências são injetadas no
prompt do cérebro (`Brain.system_prompt`), então a priorização e o tom melhoram
a cada interação. É a "memória que vira gente" sem depender do ChatGPT pessoal.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from ..storage import Storage

logger = logging.getLogger(__name__)


def _sender_of_task(storage: Storage, task_row) -> Optional[str]:
    if not task_row["source_msg_id"]:
        return None
    msg = storage.get_message(task_row["source_msg_id"])
    return (msg["sender"] if msg else None) or None


def _bump_sender(storage: Storage, sender: str, direction: int) -> None:
    """Ajusta a preferência de prioridade de um remetente.

    direction > 0 => mais importante; < 0 => menos importante. Acumula peso
    para refletir consistência ao longo do tempo.
    """
    current_weight = 1.0
    current_pri = "normal"
    for p in storage.get_preferences():
        if p["scope"] == "sender" and p["key"] == sender:
            current_weight = p["weight"]
            try:
                current_pri = json.loads(p["value"]).get("priority", "normal")
            except (TypeError, json.JSONDecodeError):
                pass
            break
    new_pri = "high" if direction > 0 else "low" if direction < 0 else current_pri
    storage.set_preference(
        "sender", sender, {"priority": new_pri}, weight=current_weight + 1.0
    )


def apply_task_feedback(storage: Storage, task_id: int, signal: str) -> str:
    """Aplica feedback a uma tarefa. Retorna uma confirmação para o dono."""
    task = storage.get_task(task_id)
    if task is None:
        return "Tarefa não encontrada."
    sender = _sender_of_task(storage, task)

    if signal == "done":
        storage.set_task_status(task_id, "done")
        return "✅ Marquei como feita."
    if signal == "snooze":
        storage.set_task_status(task_id, "snoozed")
        return "⏰ Adiei essa tarefa."
    if signal == "important":
        storage.set_task_priority(task_id, int(task["priority"]) - 1)
        if sender:
            _bump_sender(storage, sender, +1)
        return "👍 Entendi, vou priorizar isso (e itens parecidos)."
    if signal == "ignore":
        storage.set_task_status(task_id, "dismissed")
        if sender:
            _bump_sender(storage, sender, -1)
        return "👎 Ok, dispensei e vou dar menos peso a itens assim."
    return "Sinal de feedback desconhecido."


def apply_commitment_feedback(
    storage: Storage, commitment_id: int, signal: str
) -> str:
    """Aplica feedback a uma pendência."""
    if signal == "resolve":
        storage.set_commitment_status(commitment_id, "resolved")
        return "✅ Pendência resolvida."
    if signal == "ignore":
        storage.set_commitment_status(commitment_id, "dismissed")
        return "👎 Dispensei essa pendência."
    return "Sinal de feedback desconhecido."
