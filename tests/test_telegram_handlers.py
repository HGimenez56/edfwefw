"""Regressão do bug que silenciava a conversa livre.

No python-telegram-bot v21+ o campo `Message.forward_date` foi removido;
acessá-lo direto levanta AttributeError e matava o handler de texto para TODA
mensagem normal (o usuário via silêncio). Estes testes usam objetos REAIS da
biblioteca para garantir que a detecção de encaminhamento nunca mais quebre.
"""

from __future__ import annotations

import datetime

from telegram import Chat, Message, MessageOriginHiddenUser, User

from donna.interfaces.telegram_bot import is_forwarded_message


def _msg(**kwargs) -> Message:
    return Message(
        message_id=1,
        date=datetime.datetime.now(datetime.timezone.utc),
        chat=Chat(id=1, type="private"),
        from_user=User(id=1, first_name="x", is_bot=False),
        text="oi Donna",
        **kwargs,
    )


def test_normal_message_is_not_forwarded_and_does_not_raise() -> None:
    # Era exatamente este caso que estourava AttributeError em produção.
    assert is_forwarded_message(_msg()) is False


def test_forwarded_message_is_detected() -> None:
    origin = MessageOriginHiddenUser(
        date=datetime.datetime.now(datetime.timezone.utc),
        sender_user_name="Fulano",
    )
    assert is_forwarded_message(_msg(forward_origin=origin)) is True
