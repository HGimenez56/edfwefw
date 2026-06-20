"""Ponto de entrada da Dona.

Fase 0: inicializa configuração, banco e cérebro, valida o que está pronto e
sobe o bot do Telegram. As fases seguintes plugam aqui o agendador
(briefings/lembretes) e os adapters de ingestão (e-mail, calendário, whatsapp).

Uso:
    python -m dona.main          # sobe a Dona
    python -m dona.main --check  # só checa a configuração e sai
"""

from __future__ import annotations

import argparse
import logging
import sys

from .brain import Brain
from .config import get_settings
from .interfaces.telegram_bot import DonaTelegramBot
from .storage import Storage


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )


def _print_status(settings, brain: Brain) -> None:
    """Imprime um resumo de prontidão das integrações."""
    def mark(ok: bool) -> str:
        return "✅" if ok else "⬜"

    print("— Status da Dona —")
    print(f"{mark(brain.ready)} Cérebro (OpenAI)      modelo={settings.openai_model}")
    print(f"{mark(settings.telegram_ready)} Telegram (interface)")
    print(f"{mark(settings.email_ready)} E-mail (IMAP)         [Fase 1]")
    print(f"{mark(settings.whatsapp_enabled)} WhatsApp (opcional)   [Fase 3]")
    print(f"   Fuso: {settings.timezone} | Banco: {settings.db_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dona — assistente pessoal")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Apenas valida a configuração e sai.",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    _setup_logging(settings.log_level)
    logger = logging.getLogger("dona")

    storage = Storage(settings.db_path)
    brain = Brain(settings, storage)

    _print_status(settings, brain)

    if args.check:
        return 0

    if not settings.telegram_ready:
        logger.error(
            "TELEGRAM_BOT_TOKEN ausente. Crie um bot com o @BotFather, "
            "preencha o .env e tente de novo."
        )
        return 1

    bot = DonaTelegramBot(settings, storage, brain)
    bot.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
