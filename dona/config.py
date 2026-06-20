"""Configuração central da Dona.

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
    timezone: str = Field(default="America/Sao_Paulo", alias="DONA_TIMEZONE")
    db_path: Path = Field(default=Path("data/dona.db"), alias="DONA_DB_PATH")
    log_level: str = Field(default="INFO", alias="DONA_LOG_LEVEL")

    # --- E-mail (Fase 1, IMAP) ---
    imap_host: str = Field(default="", alias="IMAP_HOST")
    imap_port: int = Field(default=993, alias="IMAP_PORT")
    imap_user: str = Field(default="", alias="IMAP_USER")
    imap_password: str = Field(default="", alias="IMAP_PASSWORD")

    # --- Microsoft Graph (Fase 1, opcional) ---
    ms_graph_client_id: str = Field(default="", alias="MS_GRAPH_CLIENT_ID")
    ms_graph_tenant_id: str = Field(default="", alias="MS_GRAPH_TENANT_ID")

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
    def email_ready(self) -> bool:
        """True se a ingestão de e-mail via IMAP está configurada."""
        return bool(self.imap_host and self.imap_user and self.imap_password)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retorna a configuração (cacheada) da aplicação."""
    return Settings()
