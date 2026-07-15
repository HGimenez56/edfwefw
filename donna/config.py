"""Configuração central da Donna.

Carrega as variáveis de ambiente (a partir de um arquivo `.env`, se existir)
e as expõe de forma tipada via `Settings`. Tudo que é segredo ou específico
do ambiente passa por aqui — o resto do código nunca lê `os.environ` direto.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuração da aplicação, lida do ambiente / arquivo .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Cérebro (OpenAI) ---
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o", alias="OPENAI_MODEL")

    # --- Interface (Telegram) ---
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_owner_chat_id: Optional[int] = Field(
        default=None, alias="TELEGRAM_OWNER_CHAT_ID"
    )

    # --- Geral ---
    timezone: str = Field(default="America/Sao_Paulo", alias="DONNA_TIMEZONE")
    db_path: Path = Field(default=Path("data/donna.db"), alias="DONNA_DB_PATH")
    log_level: str = Field(default="INFO", alias="DONNA_LOG_LEVEL")

    # --- E-mail (Fase 1) ---
    # Qual(is) backend(s) usar: 'imap' (Plano B), 'graph' (Plano A) ou 'both'.
    email_backend: str = Field(default="imap", alias="EMAIL_BACKEND")
    # De quantos em quantos minutos buscar e-mails novos.
    email_poll_minutes: int = Field(default=10, alias="EMAIL_POLL_MINUTES")
    # Quantos e-mails recentes considerar a cada busca.
    email_fetch_limit: int = Field(default=30, alias="EMAIL_FETCH_LIMIT")
    # Hora local (0-23) do briefing diário.
    briefing_hour: int = Field(default=7, alias="BRIEFING_HOUR")
    # Hora local (0-23) do recap de fim de dia.
    recap_hour: int = Field(default=18, alias="RECAP_HOUR")
    # Nomes pelos quais o dono é chamado (separados por vírgula). Em GRUPOS,
    # só vira pendência do dono se a mensagem chamar um desses nomes.
    # O padrão já traz os nomes do dono; a env var OWNER_NAMES sobrescreve.
    owner_names: str = Field(
        default="Henrique,Laplace,Gimenez,Cana", alias="OWNER_NAMES"
    )

    # --- E-mail (Plano B: IMAP) ---
    imap_host: str = Field(default="", alias="IMAP_HOST")
    imap_port: int = Field(default=993, alias="IMAP_PORT")
    imap_user: str = Field(default="", alias="IMAP_USER")
    imap_password: str = Field(default="", alias="IMAP_PASSWORD")
    # Pasta de enviados na caixa IMAP (vazio = não ler enviados por IMAP).
    imap_sent_folder: str = Field(default="", alias="IMAP_SENT_FOLDER")

    # --- E-mail (Plano A: Microsoft Graph) ---
    ms_graph_client_id: str = Field(default="", alias="MS_GRAPH_CLIENT_ID")
    # 'common' funciona para a maioria; use o tenant id se necessário.
    ms_graph_tenant_id: str = Field(default="common", alias="MS_GRAPH_TENANT_ID")

    # --- Calendário (Fase 2) ---
    # URL do ICS publicado do seu calendário do Outlook (read-only).
    calendar_ics_url: str = Field(default="", alias="CALENDAR_ICS_URL")

    # --- WhatsApp (Fase 3, opcional) ---
    whatsapp_enabled: bool = Field(default=False, alias="WHATSAPP_ENABLED")

    # --- Validações de prontidão (não levantam erro; servem de checagem) ---
    @property
    def brain_ready(self) -> bool:
        """True se a integração com a OpenAI está configurada."""
        return bool(self.openai_api_key)

    @property
    def telegram_ready(self) -> bool:
        """True se o bot do Telegram está configurado."""
        return bool(self.telegram_bot_token)

    @property
    def imap_ready(self) -> bool:
        """True se a ingestão de e-mail via IMAP está configurada."""
        return bool(self.imap_host and self.imap_user and self.imap_password)

    @property
    def graph_ready(self) -> bool:
        """True se a ingestão via Microsoft Graph está configurada."""
        return bool(self.ms_graph_client_id)

    @property
    def calendar_ready(self) -> bool:
        """True se há um ICS publicado configurado."""
        return bool(self.calendar_ics_url)

    @property
    def email_ready(self) -> bool:
        """True se ao menos um backend de e-mail ativo está configurado."""
        backend = self.email_backend.lower()
        imap_ok = self.imap_ready and backend in ("imap", "both")
        graph_ok = self.graph_ready and backend in ("graph", "both")
        return imap_ok or graph_ok


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retorna a configuração (cacheada) da aplicação."""
    return Settings()
