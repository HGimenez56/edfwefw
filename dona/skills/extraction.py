"""Extração: transforma mensagens cruas em tarefas e pendências.

Pega as mensagens ainda não processadas (`Storage.unprocessed_messages`), pede
ao cérebro (`Brain.extract_json`) uma estrutura com tarefas e compromissos, e
grava no banco. Também faz uma resolução simples de pendências: um e-mail
**enviado** por você para alguém marca como resolvida uma pendência
"awaiting_my_reply" em aberto com aquela pessoa.

Roda sem custo se não houver mensagens novas; em modo stub (sem OpenAI) apenas
marca como processado sem extrair.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..brain import Brain
from ..storage import Storage

logger = logging.getLogger(__name__)

# Tipos de compromisso válidos (espelham o schema em storage.py).
_VALID_KINDS = {"awaiting_my_reply", "i_promised", "awaiting_their_reply"}

_INSTRUCTION = """\
Você está analisando UMA mensagem de e-mail do dono. Extraia o que for
acionável e responda APENAS em JSON com este formato exato:

{
  "category": "trabalho" | "pessoal",
  "tasks": [
    {"title": "curto e acionável",
     "details": "contexto opcional",
     "priority": 1-5,            // 1 = urgente/importante, 5 = baixo
     "due_at": "YYYY-MM-DD" | null}
  ],
  "commitments": [
    {"kind": "awaiting_my_reply" | "i_promised" | "awaiting_their_reply",
     "who": "pessoa/cliente",
     "summary": "o que está pendente"}
  ]
}

Regras:
- Se a mensagem foi RECEBIDA (direction=in) e pede uma ação/resposta sua, gere
  um commitment "awaiting_my_reply".
- Se foi ENVIADA por você (direction=out) e você prometeu algo, gere
  "i_promised"; se você está esperando retorno de alguém, "awaiting_their_reply".
- Não invente prazos: use null quando não houver data clara.
- Se não houver nada acionável, devolva listas vazias.
"""


@dataclass
class ExtractionResult:
    processed: int = 0
    tasks_created: int = 0
    commitments_created: int = 0
    resolved: int = 0


def _format_message(row) -> str:
    return (
        f"direction: {row['direction']}\n"
        f"de: {row['sender']}\n"
        f"para: {row['recipient']}\n"
        f"assunto: {row['subject']}\n"
        f"corpo:\n{row['body']}"
    )


def _resolve_pending(storage: Storage, recipient: str) -> int:
    """Marca pendências 'awaiting_my_reply' com a contraparte como resolvidas."""
    if not recipient:
        return 0
    resolved = 0
    rec = recipient.lower()
    for c in storage.open_commitments():
        who = (c["who"] or "").lower()
        if c["kind"] == "awaiting_my_reply" and who and (who in rec or rec in who):
            storage.set_commitment_status(c["id"], "resolved")
            resolved += 1
    return resolved


def run(storage: Storage, brain: Brain, limit: int = 50) -> ExtractionResult:
    """Processa mensagens não-lidas e popula tarefas/pendências."""
    result = ExtractionResult()
    messages = storage.unprocessed_messages(limit=limit)
    processed_ids: list[int] = []

    for row in messages:
        msg_id = row["id"]
        processed_ids.append(msg_id)
        result.processed += 1

        # E-mails enviados podem resolver pendências antigas.
        if row["direction"] == "out":
            result.resolved += _resolve_pending(storage, row["recipient"] or "")

        if not brain.ready:
            continue  # modo stub: só marca processado

        data = brain.extract_json(_INSTRUCTION, _format_message(row))
        if not isinstance(data, dict):
            continue

        category = data.get("category")
        for t in data.get("tasks", []) or []:
            if not t.get("title"):
                continue
            storage.add_task(
                title=str(t["title"])[:200],
                details=t.get("details"),
                category=category,
                priority=int(t.get("priority") or 3),
                due_at=t.get("due_at") or None,
                source_msg_id=msg_id,
            )
            result.tasks_created += 1

        for c in data.get("commitments", []) or []:
            kind = c.get("kind")
            if kind not in _VALID_KINDS or not c.get("summary"):
                continue
            storage.add_commitment(
                kind=kind,
                summary=str(c["summary"])[:300],
                who=c.get("who"),
                category=category,
                source_msg_id=msg_id,
            )
            result.commitments_created += 1

    storage.mark_processed(processed_ids)
    if result.processed:
        logger.info(
            "Extração: %d msg(s), %d tarefa(s), %d pendência(s), %d resolvida(s).",
            result.processed,
            result.tasks_created,
            result.commitments_created,
            result.resolved,
        )
    return result
