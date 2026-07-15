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

def build_instruction(owner_names: str = "") -> str:
    """Monta o prompt de extração, com as regras de grupo do dono."""
    names = [n.strip() for n in owner_names.split(",") if n.strip()]
    if names:
        group_rule = (
            "- MENSAGEM DE GRUPO (canal contém '[grupo]'): só gere um "
            "commitment 'awaiting_my_reply' se a mensagem chamar o dono "
            f"explicitamente por um destes nomes: {', '.join(names)} "
            "(ou @menção direta). Perguntas abertas ao grupo (ex.: 'alguém "
            "chamou goleiro?') NÃO são pendência do dono — nesse caso não "
            "gere commitment nenhum.\n"
        )
    else:
        group_rule = (
            "- MENSAGEM DE GRUPO (canal contém '[grupo]'): perguntas abertas "
            "ao grupo NÃO são pendência do dono. Só gere 'awaiting_my_reply' "
            "se a mensagem for claramente dirigida a ele (@menção/nome).\n"
        )
    return f"""\
Você está analisando UMA mensagem do dono (e-mail OU WhatsApp). Extraia o que
for acionável e responda APENAS em JSON com este formato exato:

{{
  "category": "trabalho" | "pessoal",
  "tasks": [
    {{"title": "curto e acionável",
     "details": "contexto opcional",
     "priority": 1-5,            // 1 = urgente/importante, 5 = baixo
     "due_at": "YYYY-MM-DD" | null}}
  ],
  "commitments": [
    {{"kind": "awaiting_my_reply" | "i_promised" | "awaiting_their_reply",
     "who": "pessoa/cliente",
     "summary": "o que está pendente"}}
  ]
}}

Regras:
- Conversa INDIVIDUAL recebida (direction=in) que pede ação/resposta do dono:
  gere um commitment "awaiting_my_reply".
{group_rule}- Se foi ENVIADA por você (direction=out) e você prometeu algo, gere
  "i_promised"; se você está esperando retorno de alguém, "awaiting_their_reply".
- O campo "summary" deve ser AUTOEXPLICATIVO: quem pediu, o quê, e onde.
  Ex.: "João (grupo Futebol) perguntou se já chamaram goleiro" — nunca algo
  vago como "responder mensagem" ou "acompanhar pedido".
- O campo "who" deve ser o nome real de quem pediu (e o grupo, se houver).
- Não invente prazos: use null quando não houver data clara.
- Na dúvida se é pendência do dono, NÃO crie — menos ruído vale mais.
- Se não houver nada acionável, devolva listas vazias.
"""


@dataclass
class ExtractionResult:
    processed: int = 0
    tasks_created: int = 0
    commitments_created: int = 0
    resolved: int = 0


def _format_message(row) -> str:
    subject = row["subject"] or ""
    if subject.startswith("[grupo]"):
        canal = f"GRUPO de WhatsApp ({subject})"
    elif row["source"] == "whatsapp":
        canal = "conversa INDIVIDUAL de WhatsApp"
    else:
        canal = f"e-mail (assunto: {subject})"
    return (
        f"canal: {canal}\n"
        f"direction: {row['direction']}\n"
        f"de: {row['sender']}\n"
        f"para: {row['recipient']}\n"
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


def run(
    storage: Storage,
    brain: Brain,
    limit: int = 50,
    owner_names: str = "",
) -> ExtractionResult:
    """Processa mensagens não-lidas e popula tarefas/pendências."""
    result = ExtractionResult()
    instruction = build_instruction(owner_names)
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

        data = brain.extract_json(instruction, _format_message(row))
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
