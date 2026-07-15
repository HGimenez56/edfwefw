"""Cérebro da Donna — interface com a API da OpenAI.

Centraliza TODA conversa com o modelo. As outras partes do sistema chamam
métodos de alto nível (`chat`, `extract_json`) e nunca falam direto com o
SDK da OpenAI. Assim, trocar de modelo, adicionar caching ou redaction no
futuro fica num lugar só.

Memória/aprendizado: o método `system_prompt` monta o contexto persistente
(perfil + preferências) que é injetado em toda chamada. É isso que faz a
Donna "lembrar" das suas preferências sem depender da memória do ChatGPT.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from openai import OpenAI

from .config import Settings
from .storage import Storage

logger = logging.getLogger(__name__)


# Personalidade base da Donna. O perfil e as preferências aprendidas são
# anexados a isto em tempo de execução por `Brain.system_prompt`.
BASE_PERSONA = """\
Você é a "Donna", a assistente virtual pessoal de um único usuário (o "dono").
Seu papel é ajudá-lo a não deixar passar pedidos, compromissos e follow-ups,
organizar o dia, lembrar do que importa e, quando solicitado, preparar
rascunhos. Princípios:
- Fale português do Brasil, de forma direta, prática e respeitosa.
- Seja concisa: o dono é ocupado. Priorize o que é acionável.
- Você NUNCA envia nada a terceiros por conta própria. Toda comunicação
  externa é apenas um rascunho que depende da aprovação final do dono.
- Separe contexto de trabalho e pessoal, mas cuide dos dois.
- Quando não tiver certeza, diga o que assumiu em vez de inventar.
- Você recebe um bloco "DADOS ATUAIS" com as tarefas, pendências e agenda
  REAIS do dono. Responda SEMPRE com base nesses dados. Se algo não estiver
  lá, diga que não encontrou — NUNCA invente tarefas, pendências, nomes ou
  compromissos que não existam nos dados.
"""


class Brain:
    """Wrapper de alto nível sobre o cliente da OpenAI."""

    def __init__(self, settings: Settings, storage: Storage) -> None:
        self._settings = settings
        self._storage = storage
        self._client: Optional[OpenAI] = None
        if settings.openai_api_key:
            # Timeout curto e 1 retry: se a chamada travar (rede/proxy), o erro
            # aparece em ~30s em vez de pendurar por padrão (10min + retries),
            # o que deixava a Donna "muda" sem nunca reportar o problema.
            self._client = OpenAI(
                api_key=settings.openai_api_key,
                timeout=30.0,
                max_retries=1,
            )
        else:
            logger.warning(
                "OPENAI_API_KEY ausente — o cérebro responderá em modo stub."
            )

    @property
    def ready(self) -> bool:
        return self._client is not None

    def system_prompt(self) -> str:
        """Monta o prompt de sistema com a memória de longo prazo."""
        parts = [BASE_PERSONA]

        profile = self._storage.get_profile().strip()
        if profile:
            parts.append("# Perfil do dono\n" + profile)

        prefs = self._storage.get_preferences()
        if prefs:
            lines = [
                f"- [{p['scope']}] {p['key']}: {p['value']} (peso {p['weight']})"
                for p in prefs
            ]
            parts.append("# Preferências aprendidas\n" + "\n".join(lines))

        return "\n\n".join(parts)

    def chat(self, user_message: str, *, temperature: float = 0.3) -> str:
        """Conversa simples: recebe texto, devolve texto."""
        if not self._client:
            return (
                "⚠️ Cérebro em modo stub (sem OPENAI_API_KEY). "
                f"Você disse: {user_message!r}"
            )
        resp = self._client.chat.completions.create(
            model=self._settings.openai_model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": self.system_prompt()},
                {"role": "user", "content": user_message},
            ],
        )
        return (resp.choices[0].message.content or "").strip()

    def converse(
        self,
        user_message: str,
        *,
        context: str = "",
        history: Optional[list[tuple[str, str]]] = None,
        temperature: float = 0.3,
    ) -> str:
        """Conversa com estado: injeta os DADOS REAIS e o histórico recente.

        `context` é o bloco "DADOS ATUAIS" (tarefas/pendências/agenda vindas
        do banco). `history` são os últimos turnos [(papel, texto)], com papel
        'user' ou 'assistant'. É isso que impede o modelo de inventar dados e
        o faz lembrar do que acabou de ser dito.
        """
        if not self._client:
            return (
                "⚠️ Cérebro em modo stub (sem OPENAI_API_KEY). "
                f"Você disse: {user_message!r}"
            )
        messages: list[dict] = [
            {"role": "system", "content": self.system_prompt()},
        ]
        if context:
            messages.append(
                {"role": "system", "content": f"DADOS ATUAIS:\n{context}"}
            )
        for role, text in history or []:
            if role in ("user", "assistant") and text:
                messages.append({"role": role, "content": text})
        messages.append({"role": "user", "content": user_message})

        resp = self._client.chat.completions.create(
            model=self._settings.openai_model,
            temperature=temperature,
            messages=messages,
        )
        return (resp.choices[0].message.content or "").strip()

    def extract_json(
        self,
        instruction: str,
        content: str,
        *,
        temperature: float = 0.0,
    ) -> Any:
        """Pede ao modelo uma resposta estritamente em JSON e a desserializa.

        Usado nas fases seguintes para extrair tarefas/compromissos de
        e-mails e mensagens. Retorna o objeto Python (dict/list) ou None.
        """
        if not self._client:
            logger.warning("extract_json chamado em modo stub; retornando None")
            return None
        resp = self._client.chat.completions.create(
            model=self._settings.openai_model,
            temperature=temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": self.system_prompt()},
                {"role": "user", "content": f"{instruction}\n\n---\n{content}"},
            ],
        )
        raw = resp.choices[0].message.content or "{}"
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.error("Resposta não-JSON do modelo: %s", raw[:500])
            return None
