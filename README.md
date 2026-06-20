# Dona 🤖 — Assistente Virtual Pessoal com IA

A **Dona** é uma assistente pessoal (uso individual, não distribuída) que lê
suas comunicações — e-mail do trabalho e, opcionalmente, WhatsApp pessoal —,
extrai o que importa (pedidos, compromissos, follow-ups), te organiza com
briefings e lembretes, e com o tempo prepara rascunhos **sempre pendentes da
sua aprovação**. O "cérebro" usa a **API da OpenAI** (modelos GPT); a memória
e o aprendizado ficam no próprio sistema.

> Status: **Fase 0 (esqueleto)** — conversa pelo Telegram, banco e cérebro
> prontos. Próximas fases adicionam e-mail, agenda, WhatsApp e rascunhos.
> Veja o roteiro completo no plano do projeto.

---

## Arquitetura (resumo)

```
Fontes  →  Núcleo (Dona)  →  Você (Telegram)
e-mail      ingestão           conversa,
whatsapp    cérebro (OpenAI)   aprova rascunhos,
            memória (SQLite)    dá feedback
            agendador
```

- **Interface:** bot de Telegram (push no celular, aprovação com um toque).
- **Banco:** SQLite (`data/dona.db`).
- **Não é** um app pra baixar nem um site — é um serviço que roda 24/7 num
  servidor + o chat no Telegram.

---

## Como rodar (Fase 0)

### 1. Pré-requisitos
- Python 3.12+
- Um **bot do Telegram**: fale com o [@BotFather](https://t.me/BotFather),
  use `/newbot` e copie o token.
- Uma **chave de API da OpenAI** (em https://platform.openai.com/ — billing é
  separado do ChatGPT Plus).

### 2. Configuração
```bash
cp .env.example .env
# edite o .env e preencha OPENAI_API_KEY e TELEGRAM_BOT_TOKEN
```

### 3. Rodar localmente
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# checa a configuração sem subir nada:
python -m dona.main --check

# sobe a Dona:
python -m dona.main
```
Depois mande `/start` para o seu bot no Telegram. Ele vai te responder com o
seu **chat id** — copie para `TELEGRAM_OWNER_CHAT_ID` no `.env` e reinicie,
assim a Dona só conversa com você.

### 4. Rodar com Docker (recomendado para o servidor 24/7)
```bash
docker compose up -d --build
docker compose logs -f
```

---

## Hospedagem (para ficar sempre no ar)

Precisa de um host **persistente** (por causa dos lembretes e, na Fase 3, da
sessão do WhatsApp). Opções:
- **VPS pequena** (ex.: Hetzner ~€4/mês, DigitalOcean) — rode com `docker compose`.
- **Fly.io** com volume persistente em `/app/data`.

Os segredos ficam só no `.env` do servidor (nunca no repositório).

---

## Comandos do bot (Fase 0)
- `/start` — apresentação + mostra seu chat id.
- `/ajuda` — lista o que a Dona já faz.
- `/tarefas` — tarefas em aberto.
- `/pendencias` — pendências/compromissos em aberto.
- Qualquer texto — conversa livre com o cérebro.

---

## Testes
```bash
pip install pytest
pytest -q
```
Os testes da Fase 0 cobrem a camada de armazenamento e rodam **sem nenhuma
credencial**.

---

## Privacidade
Conteúdo de e-mails/mensagens é enviado à API da OpenAI para processamento. A
API não treina com dados de API por padrão, mas é dado seu saindo da máquina —
filtros/redaction podem ser adicionados depois.

---

## Roteiro (fases)
- **Fase 0 — Esqueleto** ✅ (você está aqui): config, banco, cérebro, Telegram.
- **Fase 1 — E-mail + tarefas + briefing**: ingestão IMAP/Graph, extração, briefing diário.
- **Fase 2 — Calendário/agenda**: convites `.ics` + agenda do dia/semana.
- **Fase 3 — WhatsApp (opcional)**: leitura via aparelho vinculado (só leitura).
- **Fase 4 — Rascunhos + aprendizado**: respostas/convites com aprovação + feedback.
- **Fase 5 — Extras**: prep de reunião, recap diário, resumo semanal, captura rápida.
