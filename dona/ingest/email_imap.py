"""Adapter de e-mail via IMAP (Plano B).

Lê a caixa dedicada que recebe as cópias encaminhadas do Outlook. Por padrão
lê a INBOX (recebidos); se `IMAP_SENT_FOLDER` estiver setado, também lê a pasta
de enviados (marcados como `direction='out'`). É síncrono — o agendador o roda
num executor para não bloquear o event loop.
"""

from __future__ import annotations

import logging
from typing import Optional

from imap_tools import MailBox

from ..config import Settings
from .base import IngestedEmail

logger = logging.getLogger(__name__)

# Limite de tamanho do corpo enviado ao modelo (controle de custo/tokens).
_BODY_MAX_CHARS = 4000


def _clean_body(text: str) -> str:
    text = (text or "").strip()
    if len(text) > _BODY_MAX_CHARS:
        return text[:_BODY_MAX_CHARS] + "\n[...truncado...]"
    return text


def _fetch_folder(
    mailbox: MailBox, folder: str, direction: str, limit: int
) -> list[IngestedEmail]:
    mailbox.folder.set(folder)
    out: list[IngestedEmail] = []
    # reverse=True => mais recentes primeiro
    for msg in mailbox.fetch(limit=limit, reverse=True, mark_seen=False):
        out.append(
            IngestedEmail(
                external_id=f"{folder}:{msg.uid}",
                direction=direction,
                sender=msg.from_ or "",
                recipient=", ".join(msg.to) if msg.to else "",
                subject=msg.subject or "",
                body=_clean_body(msg.text or msg.html or ""),
                received_at=msg.date.isoformat() if msg.date else None,
            )
        )
    return out


def fetch_emails(settings: Settings, limit: Optional[int] = None) -> list[IngestedEmail]:
    """Busca e-mails recentes via IMAP. Retorna lista normalizada."""
    if not settings.imap_ready:
        logger.debug("IMAP não configurado; pulando.")
        return []

    limit = limit or settings.email_fetch_limit
    emails: list[IngestedEmail] = []
    with MailBox(settings.imap_host, port=settings.imap_port).login(
        settings.imap_user, settings.imap_password, initial_folder="INBOX"
    ) as mailbox:
        emails.extend(_fetch_folder(mailbox, "INBOX", "in", limit))
        if settings.imap_sent_folder:
            try:
                emails.extend(
                    _fetch_folder(mailbox, settings.imap_sent_folder, "out", limit)
                )
            except Exception as exc:  # pasta pode não existir
                logger.warning(
                    "Não consegui ler a pasta de enviados %r: %s",
                    settings.imap_sent_folder,
                    exc,
                )
    logger.info("IMAP: %d e-mail(s) buscado(s).", len(emails))
    return emails
