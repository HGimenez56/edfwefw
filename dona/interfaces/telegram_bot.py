"""Bot de Telegram — o canal por onde a Dona fala com o dono.

Fase 0: comandos básicos e conversa livre (encaminhada ao cérebro). As fases
seguintes adicionam botões de feedback (👍/👎/✅/⏰), aprovação de rascunhos e
o disparo dos briefings agendados.

Segurança: a Dona só responde ao `telegram_owner_chat_id` configurado. Se ele
não estiver setado, o bot ainda responde mas avisa o chat id no log para você
copiar para o `.env` (passo único de configuração).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import time as dtime
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from ..brain import Brain
from ..config import Settings
from ..ingest import email as email_ingest
from ..skills import briefing as briefing_skill
from ..skills import extraction
from ..storage import Storage

logger = logging.getLogger(__name__)


class DonaTelegramBot:
    """Encapsula o app do python-telegram-bot e seus handlers."""

    def __init__(self, settings: Settings, storage: Storage, brain: Brain) -> None:
        self._settings = settings
        self._storage = storage
        self._brain = brain
        self._app = Application.builder().token(settings.telegram_bot_token).build()
        self._register_handlers()
        self._register_jobs()

    def _register_handlers(self) -> None:
        self._app.add_handler(CommandHandler("start", self._cmd_start))
        self._app.add_handler(CommandHandler("ajuda", self._cmd_help))
        self._app.add_handler(CommandHandler("help", self._cmd_help))
        self._app.add_handler(CommandHandler("tarefas", self._cmd_tasks))
        self._app.add_handler(CommandHandler("pendencias", self._cmd_commitments))
        self._app.add_handler(CommandHandler("briefing", self._cmd_briefing))
        self._app.add_handler(CommandHandler("sync", self._cmd_sync))
        self._app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_text)
        )

    def _register_jobs(self) -> None:
        """Agenda poll de e-mail, briefing diário e prévia semanal."""
        jq = self._app.job_queue
        if jq is None:  # extra [job-queue] não instalado
            logger.warning("JobQueue indisponível; jobs não foram agendados.")
            return
        tz = ZoneInfo(self._settings.timezone)

        if self._settings.email_ready:
            jq.run_repeating(
                self._job_poll_email,
                interval=self._settings.email_poll_minutes * 60,
                first=15,  # primeira varredura logo após subir
                name="poll_email",
            )
        else:
            logger.info("Nenhum backend de e-mail configurado; poll desativado.")

        briefing_time = dtime(hour=self._settings.briefing_hour, tzinfo=tz)
        jq.run_daily(self._job_daily_briefing, time=briefing_time, name="briefing")
        # Prévia semanal aos domingos (0 = domingo no python-telegram-bot).
        jq.run_daily(
            self._job_weekly_preview, time=briefing_time, days=(0,), name="weekly"
        )

    # --- Autorização -------------------------------------------------------
    def _is_owner(self, update: Update) -> bool:
        owner = self._settings.telegram_owner_chat_id
        if owner is None:
            # Ainda não configurado: registra o id para o usuário copiar.
            chat_id = update.effective_chat.id if update.effective_chat else "?"
            logger.warning(
                "TELEGRAM_OWNER_CHAT_ID não configurado. Seu chat id é: %s "
                "— copie para o .env para travar o acesso só a você.",
                chat_id,
            )
            return True
        return bool(update.effective_chat and update.effective_chat.id == owner)

    # --- Comandos ----------------------------------------------------------
    async def _cmd_start(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id if update.effective_chat else "?"
        await update.message.reply_text(
            "Oi! Eu sou a Dona, sua assistente. 👋\n\n"
            f"Seu chat id é `{chat_id}` — coloque ele em "
            "`TELEGRAM_OWNER_CHAT_ID` no .env para eu só falar com você.\n\n"
            "Use /ajuda para ver o que já sei fazer.",
            parse_mode="Markdown",
        )

    async def _cmd_help(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "O que eu já faço:\n"
            "• Conversar com você (é só mandar uma mensagem).\n"
            "• /briefing — montar o resumo do dia agora.\n"
            "• /sync — buscar e-mails novos e extrair tarefas/pendências.\n"
            "• /tarefas — listar tarefas em aberto.\n"
            "• /pendencias — listar pendências/compromissos em aberto.\n\n"
            "Automático: leio seus e-mails de tempos em tempos, te aviso de novas "
            "pendências e mando o briefing diário.\n"
            "Em breve: agenda/reuniões e rascunhos para sua aprovação."
        )

    async def _cmd_tasks(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_owner(update):
            return
        tasks = self._storage.open_tasks()
        if not tasks:
            await update.message.reply_text("Sem tarefas em aberto. 🎉")
            return
        lines = [
            f"{i}. [{t['priority']}] {t['title']}"
            + (f" — ⏰ {t['due_at']}" if t["due_at"] else "")
            for i, t in enumerate(tasks, 1)
        ]
        await update.message.reply_text("📋 Tarefas em aberto:\n" + "\n".join(lines))

    async def _cmd_commitments(
        self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not self._is_owner(update):
            return
        items = self._storage.open_commitments()
        if not items:
            await update.message.reply_text("Nenhuma pendência em aberto. 👍")
            return
        lines = [
            f"{i}. ({c['kind']}) {c['summary']}"
            + (f" — com {c['who']}" if c["who"] else "")
            for i, c in enumerate(items, 1)
        ]
        await update.message.reply_text("🔔 Pendências:\n" + "\n".join(lines))

    async def _cmd_briefing(
        self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not self._is_owner(update):
            return
        text = briefing_skill.build_daily_briefing(self._storage)
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_sync(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_owner(update):
            return
        if not self._settings.email_ready:
            await update.message.reply_text(
                "Nenhum backend de e-mail configurado ainda. Veja o .env."
            )
            return
        await update.message.reply_text("🔄 Buscando e-mails...")
        new, res = await self._sync_and_extract()
        await update.message.reply_text(
            f"✅ {new} e-mail(s) novo(s). "
            f"{res.tasks_created} tarefa(s), {res.commitments_created} "
            f"pendência(s), {res.resolved} resolvida(s)."
        )

    # --- Ações compartilhadas ---------------------------------------------
    async def _sync_and_extract(self):
        """Busca e-mails (em thread) e roda a extração. Retorna (novos, result)."""
        new = await asyncio.to_thread(
            email_ingest.sync_emails, self._settings, self._storage
        )
        result = await asyncio.to_thread(
            extraction.run, self._storage, self._brain
        )
        return new, result

    async def _send_owner(self, text: str) -> None:
        """Envia uma mensagem proativa ao dono (se o chat id estiver setado)."""
        owner = self._settings.telegram_owner_chat_id
        if owner is None:
            logger.warning("Sem TELEGRAM_OWNER_CHAT_ID; mensagem proativa ignorada.")
            return
        await self._app.bot.send_message(
            owner, text, parse_mode=ParseMode.MARKDOWN
        )

    # --- Jobs agendados ----------------------------------------------------
    async def _job_poll_email(self, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        new, result = await self._sync_and_extract()
        # Avisa de forma enxuta só quando surge algo que precisa de resposta.
        if result.commitments_created:
            await self._send_owner(
                f"🔔 {result.commitments_created} nova(s) pendência(s) na sua "
                "caixa. Use /pendencias para ver."
            )

    async def _job_daily_briefing(self, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await self._send_owner(briefing_skill.build_daily_briefing(self._storage))

    async def _job_weekly_preview(self, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await self._send_owner(briefing_skill.build_weekly_preview(self._storage))

    # --- Conversa livre ----------------------------------------------------
    async def _on_text(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_owner(update):
            return
        text = update.message.text or ""
        await self._app.bot.send_chat_action(update.effective_chat.id, "typing")
        reply = self._brain.chat(text)
        await update.message.reply_text(reply)

    # --- Ciclo de vida -----------------------------------------------------
    def run(self) -> None:
        """Bloqueia rodando o bot (long polling)."""
        logger.info("Bot do Telegram iniciado (long polling).")
        self._app.run_polling(allowed_updates=Update.ALL_TYPES)
