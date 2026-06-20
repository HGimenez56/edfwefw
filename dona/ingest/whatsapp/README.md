# Sidecar de WhatsApp (somente leitura) 🔒

Lê suas mensagens do WhatsApp (recebidas **e** enviadas) conectando como um
**aparelho vinculado** — o mesmo mecanismo do WhatsApp Web. Ele **só lê** e grava
as mensagens no banco da Dona (`messages`, `source='whatsapp'`); de lá o núcleo
extrai tarefas/pendências como faz com e-mail.

> ⚠️ **Importante**
> - Este módulo **nunca envia** mensagens (não há código de envio aqui).
> - Usa uma biblioteca não-oficial (Baileys). O risco de bloqueio é baixo para
>   uso pessoal e passivo, mas **não é oficialmente zero** — por isso é opt-in.
> - É o seu **mesmo número**, sem precisar de número novo nem da TI.

## Como parear (uma vez)

### Local (com Node 20+)
```bash
cd dona/ingest/whatsapp
npm install
DONA_DB_PATH=../../../data/dona.db node index.js
```
Vai aparecer um **QR no terminal**. No celular: WhatsApp → **Aparelhos conectados**
→ **Conectar um aparelho** → escaneie. A sessão fica salva em `auth/` (no
`.gitignore`); nas próximas vezes conecta sozinho.

### Docker (junto com a Dona)
```bash
docker compose --profile whatsapp up -d
docker compose logs -f dona-whatsapp   # mostra o QR na primeira vez
```

## Depois de pareado
As mensagens passam a cair no banco automaticamente. Confirme com `/sync` e
`/tarefas` no Telegram. Para desligar, pare o processo/serviço — o resto da Dona
continua funcionando sem ele.

## Reparear do zero
Apague a pasta `auth/` e rode de novo para escanear um novo QR.
