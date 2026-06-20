"""Testes da normalização/persistência de e-mails (Fase 1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from dona.ingest.base import IngestedEmail, store_emails
from dona.storage import Storage


def _email(ext_id: str, direction: str = "in") -> IngestedEmail:
    return IngestedEmail(
        external_id=ext_id,
        direction=direction,
        sender="cliente@x.com",
        recipient="eu@x.com",
        subject="Proposta",
        body="Pode me mandar a proposta até sexta?",
    )


def test_ingested_email_validates_direction() -> None:
    with pytest.raises(ValueError):
        IngestedEmail(
            external_id="1", direction="sideways",
            sender="", recipient="", subject="", body="",
        )


def test_store_emails_dedups(tmp_path: Path) -> None:
    store = Storage(tmp_path / "t.db")
    new = store_emails(store, [_email("a"), _email("b")])
    assert new == 2
    # reingerir os mesmos não cria nada
    again = store_emails(store, [_email("a"), _email("b")])
    assert again == 0
    # entram como não-processados
    assert len(store.unprocessed_messages()) == 2
