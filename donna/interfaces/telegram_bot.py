"""Bot de Telegram — o canal por onde a Donna fala com o dono.

Fase 0: comandos básicos e conversa livre (encaminhada ao cérebro). As fases
seguintes adicionam botões de feedback (👍/👎/✅/⏰), aprovação de rascunhos e
o disparo dos briefings agendados.

Segurança: a Donna só responde ao `telegram_owner_chat_id` configurado. Se ele
não estiver setado, o bot ainda responde mas avisa o chat id no log para você
copiar para o `.env` (passo único de configuração).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import time as dtime
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from ..brain import Brain
from ..config import Settings
from ..ingest import calendar as calendar_ingest
from ..ingest import email as email_ingest
from ..skills import agenda as agenda_skill
from ..skills import briefing as briefing_skill
from ..skills import drafts as drafts_skill
from ..skills import extraction
from ..skills import extras as extras_skill
from ..skills import learning
from ..storage import Storage

logger = logging.getLogger(__name__)


class DonnaTelegramBot:
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
        self._app.add_handler(CommandHandler("agenda", self._cmd_agenda))
        self._app.add_handler(CommandHandler("sync", self._cmd_sync))
        self._app.add_handler(CommandHandler("rascunho", self._cmd_draft))
        self._app.add_handler(CommandHandler("nota", self._cmd_note))
        self._app.add_handler(CommandHandler("recap", self._cmd_recap))
        self._app.add_handler(CommandHandler("semana", self._cmd_week))
        self._app.add_handler(CommandHandler("prep", self._cmd_prep))
        self._app.add_handler(CallbackQueryHandler(self._on_callback))
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

        # Processamento de mensagens (extração) roda com QUALQUER fonte — e-mail
        # ou WhatsApp. Fica separado da busca de e-mail de propósito, para
        # também processar o que o sidecar de WhatsApp grava no banco.
        if self._brain.ready:
            jq.run_repeating(
                self._job_process_messages,
                interval=self._settings.email_poll_minutes * 60,
                first=45,
                name="process_messages",
            )

        if self._settings.calendar_ready:
            jq.run_repeating(
                self._job_poll_calendar,
                interval=self._settings.email_poll_minutes * 60,
                first=30,
                name="poll_calendar",
            )

        briefing_time = dtime(hour=self._settings.briefing_hour, tzinfo=tz)
        jq.run_daily(self._job_daily_briefing, time=briefing_time, name="briefing")
        # Prévia semanal aos domingos (0 = domingo no python-telegram-bot).
        jq.run_daily(
            self._job_weekly_preview, time=briefing_time, days=(0,), name="weekly"
        )
        recap_time = dtime(hour=self._settings.recap_hour, tzinfo=tz)
        jq.run_daily(self._job_daily_recap, time=recap_time, name="recap")

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
            "Oi! Eu sou a Donna, sua assistente. 👋\n\n"
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
            "• /agenda — suas reuniões de hoje.\n"
            "• /sync — buscar e-mails/agenda e extrair tarefas/pendências.\n"
            "• /tarefas — tarefas em aberto (com botões ✅👍👎⏰).\n"
            "• /pendencias — pendências em aberto (com botões).\n"
            "• /rascunho <texto> — eu preparo uma resposta para você aprovar.\n"
            "• /nota <texto> — captura rápida (vira tarefa). Encaminhar também vale.\n"
            "• /prep — preparação para sua próxima reunião.\n"
            "• /recap — recap do dia + agenda de amanhã.\n"
            "• /semana — o que você entregou na semana.\n\n"
            "Automático: leio seus e-mails/agenda, te aviso de novas pendências, "
            "mando o briefing de manhã e o recap à noite. Seus 👍/👎 me ensinam "
            "o que priorizar.\n"
            "Em breve: WhatsApp (opcional)."
        )

    async def _cmd_tasks(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_owner(update):
            return
        tasks = self._storage.open_tasks(limit=10)
        if not tasks:
            await update.message.reply_text("Sem tarefas em aberto. 🎉")
            return
        await update.message.reply_text("📋 *Tarefas em aberto*", parse_mode=ParseMode.MARKDOWN)
        for t in tasks:
            due = f"\n⏰ {t['due_at']}" if t["due_at"] else ""
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Feito", callback_data=f"t|done|{t['id']}"),
                InlineKeyboardButton("👍", callback_data=f"t|important|{t['id']}"),
                InlineKeyboardButton("👎", callback_data=f"t|ignore|{t['id']}"),
                InlineKeyboardButton("⏰", callback_data=f"t|snooze|{t['id']}"),
            ]])
            await update.message.reply_text(
                f"[P{t['priority']}] {t['title']}{due}", reply_markup=keyboard
            )

    async def _cmd_commitments(
        self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not self._is_owner(update):
            return
        items = self._storage.open_commitments(limit=10)
        if not items:
            await update.message.reply_text("Nenhuma pendência em aberto. 👍")
            return
        await update.message.reply_text("🔔 *Pendências*", parse_mode=ParseMode.MARKDOWN)
        for c in items:
            who = f" — {c['who']}" if c["who"] else ""
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Resolvi", callback_data=f"c|resolve|{c['id']}"),
                InlineKeyboardButton("👎 Ignorar", callback_data=f"c|ignore|{c['id']}"),
            ]])
            await update.message.reply_text(
                f"{c['summary']}{who}", reply_markup=keyboard
            )

    async def _cmd_briefing(
        self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not self._is_owner(update):
            return
        text = briefing_skill.build_daily_briefing(
            self._storage, self._settings.timezone
        )
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_agenda(
        self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not self._is_owner(update):
            return
        text = agenda_skill.build_agenda(self._storage, self._settings.timezone)
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_draft(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """/rascunho <texto da mensagem recebida> → gera resposta para aprovar."""
        if not self._is_owner(update):
            return
        original = (update.message.text or "").partition(" ")[2].strip()
        if not original:
            await update.message.reply_text(
                "Use: /rascunho <cole aqui a mensagem que quer responder>"
            )
            return
        await self._app.bot.send_chat_action(update.effective_chat.id, "typing")
        body = await asyncio.to_thread(
            drafts_skill.generate_reply_draft, self._brain, original
        )
        draft_id = self._storage.add_draft(kind="email_reply", body=body)
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Aprovar", callback_data=f"d|approve|{draft_id}"),
            InlineKeyboardButton("❌ Descartar", callback_data=f"d|discard|{draft_id}"),
        ]])
        await update.message.reply_text(
            f"✏️ *Rascunho de resposta:*\n\n{body}",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )

    async def _on_callback(
        self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Trata os botões inline (feedback de itens e aprovação de rascunhos)."""
        query = update.callback_query
        if self._settings.telegram_owner_chat_id is not None and (
            query.message.chat.id != self._settings.telegram_owner_chat_id
        ):
            await query.answer()
            return
        await query.answer()
        try:
            domain, signal, raw_id = (query.data or "").split("|", 2)
            item_id = int(raw_id)
        except ValueError:
            return

        if domain == "t":
            msg = learning.apply_task_feedback(self._storage, item_id, signal)
        elif domain == "c":
            msg = learning.apply_commitment_feedback(self._storage, item_id, signal)
        elif domain == "d":
            if signal == "approve":
                self._storage.set_draft_status(item_id, "approved")
                msg = "✅ Aprovado! Copie o texto acima e envie. (Eu nunca envio sozinha.)"
            else:
                self._storage.set_draft_status(item_id, "rejected")
                msg = "❌ Rascunho descartado."
        else:
            return

        # Reflete o resultado removendo os botões e anexando a confirmação.
        original = query.message.text or ""
        await query.edit_message_text(f"{original}\n\n— {msg}")

    async def _cmd_note(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """/nota <texto> → captura rápida: vira uma tarefa."""
        if not self._is_owner(update):
            return
        text = (update.message.text or "").partition(" ")[2].strip()
        if not text:
            await update.message.reply_text("Use: /nota <o que você quer lembrar>")
            return
        self._storage.add_task(title=text[:200], category="pessoal", priority=3)
        await update.message.reply_text("📝 Anotado como tarefa. Veja em /tarefas.")

    async def _cmd_recap(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_owner(update):
            return
        text = extras_skill.build_daily_recap(self._storage, self._settings.timezone)
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_week(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_owner(update):
            return
        text = extras_skill.build_weekly_accomplishments(
            self._storage, self._settings.timezone
        )
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_prep(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_owner(update):
            return
        await self._app.bot.send_chat_action(update.effective_chat.id, "typing")
        text = await asyncio.to_thread(
            extras_skill.build_meeting_prep,
            self._storage, self._brain, self._settings.timezone,
        )
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_sync(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_owner(update):
            return
        await update.message.reply_text("🔄 Buscando mensagens...")
        new, res = await self._sync_and_extract()
        fonte = f"{new} e-mail(s) novo(s). " if self._settings.email_ready else ""
        await update.message.reply_text(
            f"✅ {fonte}{res.tasks_created} tarefa(s), {res.commitments_created} "
            f"pendência(s), {res.resolved} resolvida(s)."
        )

    # --- Ações compartilhadas ---------------------------------------------
    async def _sync_and_extract(self):
        """Busca fontes (e-mail/calendário, se houver) e roda a extração.

        A extração processa mensagens de QUALQUER fonte no banco — inclusive as
        que o sidecar de WhatsApp grava — então funciona mesmo sem e-mail.
        """
        new = 0
        if self._settings.email_ready:
            new = await asyncio.to_thread(
                email_ingest.sync_emails, self._settings, self._storage
            )
        if self._settings.calendar_ready:
            try:
                await asyncio.to_thread(
                    calendar_ingest.sync_calendar, self._settings, self._storage
                )
            except Exception as exc:
                logger.error("Falha ao sincronizar calendário: %s", exc)
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
        """Só busca e-mails novos; a extração fica no job de processamento."""
        try:
            await asyncio.to_thread(
                email_ingest.sync_emails, self._settings, self._storage
            )
        except Exception as exc:
            logger.error("Falha ao buscar e-mails: %s", exc)

    async def _job_process_messages(self, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Processa mensagens não-lidas de qualquer fonte (e-mail, WhatsApp)."""
        result = await asyncio.to_thread(extraction.run, self._storage, self._brain)
        # Avisa de forma enxuta só quando surge algo que precisa de resposta.
        if result.commitments_created:
            await self._send_owner(
                f"🔔 {result.commitments_created} nova(s) pendência(s). "
                "Use /pendencias para ver."
            )

    async def _job_poll_calendar(self, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            await asyncio.to_thread(
                calendar_ingest.sync_calendar, self._settings, self._storage
            )
        except Exception as exc:
            logger.error("Falha ao sincronizar calendário: %s", exc)

    async def _job_daily_briefing(self, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await self._send_owner(
            briefing_skill.build_daily_briefing(self._storage, self._settings.timezone)
        )

    async def _job_weekly_preview(self, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await self._send_owner(
            briefing_skill.build_weekly_preview(self._storage, self._settings.timezone)
        )

    async def _job_daily_recap(self, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await self._send_owner(
            extras_skill.build_daily_recap(self._storage, self._settings.timezone)
        )

    # --- Conversa livre ----------------------------------------------------
    async def _on_text(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_owner(update):
            return
        text = update.message.text or ""

        # Captura rápida: mensagem encaminhada vira tarefa automaticamente.
        is_forwarded = bool(
            getattr(update.message, "forward_origin", None)
            or update.message.forward_date
        )
        if is_forwarded:
            self._storage.add_task(title=text[:200] or "(encaminhado)", priority=3)
            await update.message.reply_text(
                "📝 Encaminhado guardado como tarefa. Veja em /tarefas."
            )
            return

        await self._app.bot.send_chat_action(update.effective_chat.id, "typing")
        reply = self._brain.chat(text)
        await update.message.reply_text(reply)

    # --- Ciclo de vida -----------------------------------------------------
    def run(self) -> None:
        """Bloqueia rodando o bot (long polling)."""
        logger.info("Bot do Telegram iniciado (long polling).")
        self._app.run_polling(allowed_updates=Update.ALL_TYPES)
