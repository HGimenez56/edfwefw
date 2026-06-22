# Guia da Dona — do zero ao 24/7 🚀

Este guia te leva da pasta vazia até a Dona funcionando no seu dia a dia.
Siga na ordem: cada passo já entrega valor sozinho, então você pode parar em
qualquer ponto e continuar depois.

| Passo | O que liga | Tempo |
|---|---|---|
| 1 | **Telegram + OpenAI** (a Dona "ganha vida") | ~15 min |
| 2 | **E-mail do Outlook** (lê pedidos e pendências) | ~20 min |
| 3 | **Agenda** (reuniões no briefing) | ~5 min |
| 4 | **WhatsApp** (opcional, só leitura) | ~10 min |
| 5 | **Hospedagem 24/7** (rodar sempre) | ~20 min |

> 💡 Comece pelo Passo 1. Só ele já te dá uma assistente com quem conversar,
> anotar tarefas (`/nota`) e receber lembretes. O resto você acrescenta quando quiser.

---

## Pré-requisitos
- **Um celular com Telegram** (a Dona fala com você por lá).
- **Conta na OpenAI com billing ativo** — atenção: é **separado do ChatGPT Plus**.
  Você adiciona um cartão em <https://platform.openai.com/> → Billing.
- **Para rodar:** ou **Docker** (recomendado), ou **Python 3.11+**. Tanto faz para
  começar; para o 24/7 do Passo 5 o Docker é mais fácil.

---

## Passo 1 — Dar vida à Dona (Telegram + OpenAI)

### 1.1 Criar o bot do Telegram
1. No Telegram, abra o **@BotFather**.
2. Envie `/newbot`, escolha um nome (ex.: "Dona") e um usuário terminado em `bot`.
3. Ele te dá um **token** parecido com `123456:ABC-xyz...`. Guarde.

### 1.2 Gerar a chave da OpenAI
1. Em <https://platform.openai.com/> → **API keys** → **Create new secret key**.
2. Copie a chave (`sk-...`). Confirme que o **billing** está ativo (senão a Dona
   não consegue pensar).

### 1.3 Configurar o `.env`
Na raiz do projeto:
```bash
cp .env.example .env
```
Edite o `.env` e preencha pelo menos:
```ini
OPENAI_API_KEY=sk-sua-chave
TELEGRAM_BOT_TOKEN=123456:seu-token
DONA_TIMEZONE=America/Sao_Paulo
```

### 1.4 Subir e validar
**Com Python:**
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m dona.main --check     # confere a configuração
python -m dona.main             # sobe a Dona
```
**Com Docker:**
```bash
docker compose up -d --build
docker compose logs -f dona
```

### 1.5 Travar o acesso só para você
1. No Telegram, mande `/start` para o seu bot.
2. Ele responde com o seu **chat id** (um número).
3. Coloque no `.env`:
   ```ini
   TELEGRAM_OWNER_CHAT_ID=seu-numero
   ```
4. Reinicie a Dona. Agora ela só conversa com você.

✅ **Teste:** mande uma mensagem qualquer (ela responde), e `/nota comprar pão`
(vira tarefa). Veja em `/tarefas`. Use `/ajuda` para a lista completa.

---

## Passo 2 — E-mail do Outlook

Escolha **um** caminho em `EMAIL_BACKEND` (`imap`, `graph` ou `both`).

### Opção A — IMAP (mais rápido, via regra de encaminhamento)
A ideia: o Outlook encaminha uma cópia dos e-mails para uma caixa dedicada (ex.:
um Gmail novo) que a Dona lê.
1. Crie um **Gmail dedicado** (ex.: `dona.seunome@gmail.com`).
2. No Gmail, ative a verificação em 2 etapas e gere uma **senha de app** (é ela
   que vai no `.env`, não a senha normal).
3. No **Outlook**, crie uma **regra**: "ao receber um e-mail → encaminhar para
   dona.seunome@gmail.com".
4. No `.env`:
   ```ini
   EMAIL_BACKEND=imap
   IMAP_HOST=imap.gmail.com
   IMAP_PORT=993
   IMAP_USER=dona.seunome@gmail.com
   IMAP_PASSWORD=senha-de-app-do-gmail
   # opcional, para ler também o que você enviou:
   IMAP_SENT_FOLDER=[Gmail]/Sent Mail
   ```
   > Para os **enviados** entrarem, crie no Outlook uma regra que também
   > encaminhe (ou dê BCC) cópia dos seus envios para a mesma caixa.

### Opção B — Microsoft Graph (mais limpo, sem encaminhar nada)
Lê entrada **e** enviados direto, com acesso delegado só-leitura — **se** o seu
tenant permitir consentimento de usuário (sem precisar do admin).
1. Em <https://entra.microsoft.com> → **App registrations** → **New registration**.
   - Tipo: "Public client/native". Guarde o **Application (client) ID**.
   - Em **API permissions**, adicione **Microsoft Graph → Delegated → `Mail.Read`**
     (e `Calendars.Read` se quiser agenda por aqui também).
2. No `.env`:
   ```ini
   EMAIL_BACKEND=graph
   MS_GRAPH_CLIENT_ID=seu-client-id
   MS_GRAPH_TENANT_ID=common
   ```
3. No **primeiro `/sync`**, a Dona mostra no log uma **URL + código** para você
   autorizar uma vez no navegador. Depois renova sozinha.

✅ **Teste (qualquer opção):** mande `/sync` no Telegram → depois `/tarefas`,
`/pendencias` e `/briefing`. Um e-mail tipo "me manda a proposta até sexta" deve
virar tarefa/pendência.

---

## Passo 3 — Agenda (reuniões no briefing)
1. No **Outlook web**: Configurações → Calendário → **Calendários compartilhados**
   → **Publicar** o seu calendário → copie o link **ICS** (termina em `.ics`).
2. No `.env`:
   ```ini
   CALENDAR_ICS_URL=https://outlook.office365.com/.../calendar.ics
   ```
3. Reinicie. Teste com `/agenda` (reuniões de hoje); elas também entram no
   `/briefing` e na prévia de domingo.

---

## Passo 4 — WhatsApp (opcional, somente leitura)
> ⚠️ Mesmo número, **só leitura** (recebidas + enviadas), **nunca envia**. Usa
> biblioteca não-oficial: risco de bloqueio baixo para uso pessoal/passivo, mas
> não oficialmente zero. É opt-in — o resto da Dona funciona sem isso.

Passo a passo completo em [`dona/ingest/whatsapp/README.md`](dona/ingest/whatsapp/README.md). Resumo com Docker:
```bash
docker compose --profile whatsapp up -d
docker compose logs -f dona-whatsapp     # escaneie o QR (1ª vez)
```
No celular: WhatsApp → **Aparelhos conectados** → **Conectar um aparelho** →
escaneie o QR. Pronto: as mensagens passam a virar tarefas/pendências como os
e-mails.

---

## Passo 5 — Deixar no ar 24/7 (hospedagem)
A Dona precisa de uma máquina sempre ligada (por causa dos lembretes e, se usar,
da sessão do WhatsApp). Seu computador pessoal serve para testar, mas o ideal é
um servidor barato.

### Opção recomendada — VPS com Docker
1. Alugue uma VPS pequena (ex.: **Hetzner** ~€4/mês, ou DigitalOcean).
2. Instale Docker, clone o repositório, copie seu `.env` para lá.
3. Suba:
   ```bash
   docker compose up -d                      # núcleo
   docker compose --profile whatsapp up -d   # + WhatsApp (se usar)
   ```
4. Pronto: reinicia sozinho (`restart: unless-stopped`).

### Alternativa — Fly.io
Funciona com um **volume persistente** montado em `/app/data` (onde fica o banco).

### Cuidados
- **Segredos:** o `.env` fica **só no servidor**, nunca no repositório.
- **Backup:** copie a pasta `data/` de vez em quando (é todo o "cérebro" dela).

---

## Custos (estimativa, uso pessoal)
- **OpenAI:** poucos dólares/mês (depende do volume de e-mails). Dá para reduzir
  trocando `OPENAI_MODEL` por um modelo mais barato.
- **VPS:** ~€4–6/mês.
- **Telegram:** grátis. **Gmail dedicado:** grátis.

## Privacidade
O conteúdo de e-mails/mensagens é enviado à API da OpenAI para processamento. A
API **não treina** com dados de API por padrão, mas é dado seu saindo da máquina.
Se quiser, dá para adicionar filtros/redaction depois.

---

## Ajustando a Dona ao longo do tempo
- **Horários:** `BRIEFING_HOUR` (manhã) e `RECAP_HOUR` (noite) no `.env`.
- **Frequência de leitura:** `EMAIL_POLL_MINUTES`.
- **Ela aprende:** use os botões **👍 / 👎 / ✅ / ⏰** em `/tarefas` e
  `/pendencias`. Isso ajusta o que ela prioriza e como te fala.
- **Memória/perfil:** com o tempo dá para editar o "perfil" do dono (texto que a
  Dona usa como contexto fixo) — me peça que eu adiciono um comando para isso.

---

## Solução de problemas
| Sintoma | Provável causa |
|---|---|
| Bot não responde | `TELEGRAM_BOT_TOKEN` errado, ou processo não está rodando |
| Responde a estranhos | falta setar `TELEGRAM_OWNER_CHAT_ID` |
| `/sync` não cria tarefas | `OPENAI_API_KEY`/billing, ou nenhum e-mail novo |
| Graph fica pedindo login | não autorizou o device-code; veja a URL nos logs |
| QR do WhatsApp expira | gere de novo (reinicie o sidecar); apague `auth/` se preciso |
| "database is locked" | raro; o WAL já cobre. Reinicie os containers |

Rode `python -m dona.main --check` a qualquer momento para ver o que está
ligado/faltando.

---

Qualquer passo que travar, me chama aqui que eu te ajudo a destravar. 💪
