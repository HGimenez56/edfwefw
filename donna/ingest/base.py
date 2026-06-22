"""Tipos e utilidades comuns à ingestão de e-mail.

`IngestedEmail` é o formato normalizado para o qual TODO adapter (IMAP, Graph,
...) converte suas mensagens. `store_emails` persiste essa lista em `messages`
reaproveitando `Storage.add_message`, que já deduplica por `external_id`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, Optional

from ..storage import Storage

logger = logging.getLogger(__name__)


@dataclass
class IngestedEmail:
    """E-mail normalizado, independente da fonte (IMAP/Graph)."""

    external_id: str              # id estável na origem (para dedup)
    direction: str                # 'in' (recebido) | 'out' (enviado)
    sender: str
    recipient: str
    subject: str
    body: str
    received_at: Optional[str] = None  # ISO8601, se disponível

    def __post_init__(self) -> None:
        if self.direction not in ("in", "out"):
            raise ValueError(f"direction inválida: {self.direction!r}")


def store_emails(storage: Storage, emails: Iterable[IngestedEmail]) -> int:
    """Persiste e-mails normalizados. Retorna quantos eram novos (não-dup)."""
    new_count = 0
    for email in emails:
        msg_id = storage.add_message(
            source="email",
            direction=email.direction,
            external_id=email.external_id,
            sender=email.sender,
            recipient=email.recipient,
            subject=email.subject,
            body=email.body,
            received_at=email.received_at,
        )
        if msg_id is not None:
            new_count += 1
    if new_count:
        logger.info("Ingeridos %d e-mail(s) novo(s).", new_count)
    return new_count
