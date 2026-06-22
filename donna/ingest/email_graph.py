"""Adapter de e-mail via Microsoft Graph (Plano A).

Acesso delegado **só-leitura** ao Outlook do trabalho, sem encaminhar nada e
sem precisar de admin (se o tenant permitir consentimento de usuário). Usa o
*device-code flow* da MSAL: no primeiro uso, a Donna mostra uma URL + código
para você autorizar no navegador; depois o token é renovado silenciosamente a
partir de um cache em disco (`data/graph_token.json`, fora do git).

Lê a caixa de entrada (`direction='in'`) e os itens enviados (`direction='out'`).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

import msal
import requests

from ..config import Settings
from .base import IngestedEmail

logger = logging.getLogger(__name__)

_GRAPH = "https://graph.microsoft.com/v1.0"
_SCOPES = ["Mail.Read"]
_BODY_MAX_CHARS = 4000
_TOKEN_CACHE = "graph_token.json"

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(content: str) -> str:
    text = _HTML_TAG_RE.sub(" ", content or "")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > _BODY_MAX_CHARS:
        return text[:_BODY_MAX_CHARS] + " [...truncado...]"
    return text


def _load_cache(path: Path) -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    if path.exists():
        cache.deserialize(path.read_text())
    return cache


def _save_cache(cache: msal.SerializableTokenCache, path: Path) -> None:
    if cache.has_state_changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(cache.serialize())


def _acquire_token(settings: Settings) -> Optional[str]:
    """Obtém um access token (silencioso se possível, device-flow no 1º uso)."""
    cache_path = settings.db_path.parent / _TOKEN_CACHE
    cache = _load_cache(cache_path)
    app = msal.PublicClientApplication(
        settings.ms_graph_client_id,
        authority=f"https://login.microsoftonline.com/{settings.ms_graph_tenant_id}",
        token_cache=cache,
    )

    result = None
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(_SCOPES, account=accounts[0])

    if not result:
        flow = app.initiate_device_flow(scopes=_SCOPES)
        if "user_code" not in flow:
            logger.error("Falha ao iniciar device-flow: %s", flow)
            return None
        # Mensagem com a URL + código para o usuário autorizar.
        logger.warning("AUTORIZAÇÃO NECESSÁRIA (Graph): %s", flow["message"])
        result = app.acquire_token_by_device_flow(flow)

    _save_cache(cache, cache_path)

    if result and "access_token" in result:
        return result["access_token"]
    logger.error("Não obtive token do Graph: %s", result)
    return None


def _fetch_messages(
    token: str, path: str, direction: str, limit: int
) -> list[IngestedEmail]:
    headers = {"Authorization": f"Bearer {token}"}
    date_field = "receivedDateTime" if direction == "in" else "sentDateTime"
    params = {
        "$top": str(limit),
        "$select": f"id,subject,from,toRecipients,body,{date_field}",
        "$orderby": f"{date_field} desc",
    }
    resp = requests.get(f"{_GRAPH}{path}", headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    out: list[IngestedEmail] = []
    for m in resp.json().get("value", []):
        sender = (m.get("from") or {}).get("emailAddress", {}).get("address", "")
        recipients = [
            r.get("emailAddress", {}).get("address", "")
            for r in m.get("toRecipients", [])
        ]
        out.append(
            IngestedEmail(
                external_id=m["id"],
                direction=direction,
                sender=sender,
                recipient=", ".join(filter(None, recipients)),
                subject=m.get("subject") or "",
                body=_strip_html((m.get("body") or {}).get("content", "")),
                received_at=m.get(date_field),
            )
        )
    return out


def fetch_emails(settings: Settings, limit: Optional[int] = None) -> list[IngestedEmail]:
    """Busca e-mails recentes (entrada + enviados) via Microsoft Graph."""
    if not settings.graph_ready:
        logger.debug("Graph não configurado; pulando.")
        return []

    limit = limit or settings.email_fetch_limit
    token = _acquire_token(settings)
    if not token:
        return []

    emails: list[IngestedEmail] = []
    emails.extend(_fetch_messages(token, "/me/messages", "in", limit))
    emails.extend(
        _fetch_messages(
            token, "/me/mailFolders/sentitems/messages", "out", limit
        )
    )
    logger.info("Graph: %d e-mail(s) buscado(s).", len(emails))
    return emails
