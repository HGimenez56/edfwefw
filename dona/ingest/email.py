"""Orquestra os backends de e-mail conforme `EMAIL_BACKEND`.

Ponto único que o resto do sistema chama. Decide entre IMAP (Plano B), Graph
(Plano A) ou os dois, busca os e-mails, persiste no banco e devolve quantos
eram novos. Erros de um backend não derrubam o outro.
"""

from __future__ import annotations

import logging

from ..config import Settings
from ..storage import Storage
from . import email_graph, email_imap
from .base import IngestedEmail, store_emails

logger = logging.getLogger(__name__)


def fetch_all(settings: Settings) -> list[IngestedEmail]:
    """Busca e-mails de todos os backends habilitados na config."""
    backend = settings.email_backend.lower()
    emails: list[IngestedEmail] = []

    if backend in ("imap", "both"):
        try:
            emails.extend(email_imap.fetch_emails(settings))
        except Exception as exc:
            logger.error("Falha no backend IMAP: %s", exc)

    if backend in ("graph", "both"):
        try:
            emails.extend(email_graph.fetch_emails(settings))
        except Exception as exc:
            logger.error("Falha no backend Graph: %s", exc)

    return emails


def sync_emails(settings: Settings, storage: Storage) -> int:
    """Busca e persiste e-mails novos. Retorna a contagem de novos."""
    emails = fetch_all(settings)
    return store_emails(storage, emails)
