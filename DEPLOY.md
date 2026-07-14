# Colocar a Donna no ar pelo navegador ☁️

Sem usar seu PC e sem terminal. A Donna roda 24/7 na nuvem; você usa pelo
Telegram. Passo a passo com a plataforma **Render** (a mais simples para isto).
No fim tem uma alternativa (Railway).

## Antes de começar, tenha em mãos
1. **Token do Telegram** — no app, abra o **@BotFather** → `/newbot` → copie o token.
2. **Chave da OpenAI** — em <https://platform.openai.com/> → ative **Billing**
   (cartão) → **API keys** → **Create** → copie (`sk-...`).
   > ⚠️ É separado do ChatGPT Plus.
3. Este repositório no seu **GitHub** (já está).

---

## Deploy no Render (recomendado)

1. Crie conta em <https://render.com> (pode entrar com o GitHub).
2. No painel: **New +** → **Blueprint**.
3. Conecte/escolha este repositório. O Render detecta o arquivo `render.yaml`
   e já monta o serviço "donna".
4. Ele vai pedir os **valores secretos**. Preencha:
   - `OPENAI_API_KEY` → sua chave `sk-...`
   - `TELEGRAM_BOT_TOKEN` → seu token do BotFather
   - `TELEGRAM_OWNER_CHAT_ID` → **deixe em branco por enquanto** (a gente pega no passo 7)
   - Os campos de e-mail/agenda (`IMAP_*`, `MS_GRAPH_*`, `CALENDAR_ICS_URL`) →
     **deixe em branco** (fazemos depois).
5. Clique **Apply / Deploy**. Espere o build terminar (alguns minutos).
6. Abra a aba **Logs** do serviço. Se aparecer "Bot do Telegram iniciado", está no ar.
7. **Travar o acesso a você:**
   - No Telegram, mande `/start` para o seu bot.
   - Ele responde com o seu **chat id** (um número).
   - No Render: serviço **donna** → **Environment** → edite
     `TELEGRAM_OWNER_CHAT_ID` com esse número → **Save** (ele reinicia sozinho).

✅ **Teste:** mande `/nota testar a Donna` e depois `/tarefas`. Se aparecer, está
funcionando! Use `/ajuda` para ver tudo.

> A partir daqui, para ligar **e-mail** (Passo 2 do GUIA) e **agenda** (Passo 3),
> é só voltar em **Environment** e preencher as variáveis correspondentes — sem
> mexer em código. O guia dessas variáveis está no [GUIA.md](GUIA.md).

---

## Alternativa: Railway (<https://railway.app>)
1. **New Project** → **Deploy from GitHub repo** → escolha este repositório.
   O Railway detecta o `Dockerfile` e faz o build.
2. Na aba **Variables**, adicione: `OPENAI_API_KEY`, `TELEGRAM_BOT_TOKEN`,
   `OPENAI_MODEL=gpt-4o-mini`, `DONNA_TIMEZONE=America/Sao_Paulo`,
   `DONNA_DB_PATH=/app/data/donna.db`.
3. Em **Settings → Volumes**, crie um volume montado em **`/app/data`** (guarda a
   memória da Donna).
4. Deploy. Depois pegue o chat id com `/start` e adicione
   `TELEGRAM_OWNER_CHAT_ID` nas Variables.

---

## Custo
- Render worker (menor plano): ~US$7/mês. Railway: ~US$5/mês (uso).
- OpenAI com `gpt-4o-mini`: normalmente menos de US$1–2/mês para uso pessoal.

## Observação sobre o WhatsApp
O WhatsApp (opcional) precisa escanear um QR e é um segundo serviço — dá para
adicionar depois, com calma. Comece pelo núcleo (Telegram + e-mail); o WhatsApp
entra quando você quiser.
