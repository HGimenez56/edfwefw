/**
 * Sidecar de WhatsApp da Donna — SOMENTE LEITURA.
 *
 * Conecta como "aparelho vinculado" (Baileys), lê as mensagens recebidas e
 * enviadas do seu próprio número e as grava na MESMA tabela `messages` do
 * SQLite da Donna (source='whatsapp'). A partir daí, o núcleo Python já cuida de
 * extrair tarefas/pendências — este processo NÃO faz nada além de ler.
 *
 * Importante: este sidecar NUNCA envia mensagens. Não há nenhuma chamada de
 * envio aqui de propósito.
 */

const path = require('path');
const fs = require('fs');
const pino = require('pino');
const qrcode = require('qrcode-terminal');
const QRCode = require('qrcode');
const Database = require('better-sqlite3');
const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
} = require('baileys');

const logger = pino({ level: process.env.DONNA_LOG_LEVEL?.toLowerCase() || 'info' });

// Caminho do banco — o mesmo usado pelo núcleo Python (DONNA_DB_PATH).
const DB_PATH = process.env.DONNA_DB_PATH
  ? path.resolve(process.env.DONNA_DB_PATH)
  : path.resolve(__dirname, '../../../data/donna.db');

// Pasta da sessão. Na nuvem, aponte para o disco persistente (ex.:
// /app/data/wa-auth) via WHATSAPP_AUTH_DIR para não perder o pareamento.
const AUTH_DIR = process.env.WHATSAPP_AUTH_DIR
  ? path.resolve(process.env.WHATSAPP_AUTH_DIR)
  : path.join(__dirname, 'auth');

// Se definido (só dígitos, com DDI, ex.: 5511999998888), a Donna pareia por
// CÓDIGO em vez de QR — muito mais fácil em servidor (você lê um código de 8
// caracteres nos logs e digita no WhatsApp > Aparelhos conectados).
const PAIRING_NUMBER = (process.env.WHATSAPP_PAIRING_NUMBER || '').replace(/\D/g, '');

// Para enviar o QR como IMAGEM no seu Telegram (muito mais fácil que ler dos
// logs). Usa o mesmo bot/chat do núcleo.
const TG_TOKEN = process.env.TELEGRAM_BOT_TOKEN || '';
const TG_CHAT = process.env.TELEGRAM_OWNER_CHAT_ID || '';
let lastQrSentAt = 0;

async function sendQrToTelegram(qrString) {
  if (!TG_TOKEN || !TG_CHAT) return; // sem bot configurado: cai no QR de log
  const now = Date.now();
  if (now - lastQrSentAt < 25000) return; // no máx. 1 envio a cada 25s
  lastQrSentAt = now;
  try {
    const png = await QRCode.toBuffer(qrString, { width: 400, margin: 2 });
    const form = new FormData();
    form.append('chat_id', TG_CHAT);
    form.append(
      'caption',
      '📲 Escaneie no WhatsApp > Aparelhos conectados > Conectar um aparelho. ' +
      'O código muda a cada ~20s; se expirar, envio um novo.'
    );
    form.append('photo', new Blob([png], { type: 'image/png' }), 'qr.png');
    const resp = await fetch(
      `https://api.telegram.org/bot${TG_TOKEN}/sendPhoto`,
      { method: 'POST', body: form }
    );
    if (!resp.ok) {
      logger.error({ status: resp.status }, 'Falha ao enviar QR ao Telegram.');
    }
  } catch (err) {
    logger.error({ err }, 'Erro ao gerar/enviar QR ao Telegram.');
  }
}

const db = new Database(DB_PATH);
db.pragma('journal_mode = WAL');

// Mesmo contrato de `Storage.add_message` (dedup por UNIQUE(source, external_id)).
const insertStmt = db.prepare(`
  INSERT OR IGNORE INTO messages
    (source, direction, external_id, sender, recipient, subject, body,
     category, received_at, ingested_at, processed, raw)
  VALUES
    ('whatsapp', @direction, @external_id, @sender, @recipient, @subject, @body,
     NULL, @received_at, @ingested_at, 0, NULL)
`);

function extractText(message) {
  if (!message) return '';
  return (
    message.conversation ||
    message.extendedTextMessage?.text ||
    message.imageMessage?.caption ||
    message.videoMessage?.caption ||
    message.documentMessage?.caption ||
    ''
  );
}

// Número do dono (preenchido quando a conexão abre). Usado para detectar
// @menções e replies dirigidos a ele em grupos.
let ownNumber = '';

function extractContextInfo(message) {
  if (!message) return undefined;
  return (
    message.extendedTextMessage?.contextInfo ||
    message.imageMessage?.contextInfo ||
    message.videoMessage?.contextInfo ||
    message.documentMessage?.contextInfo ||
    undefined
  );
}

// True se o dono foi @marcado na mensagem ou se ela é uma resposta (reply)
// a uma mensagem dele. O WhatsApp envia as menções como JIDs no campo
// mentionedJid — detecção exata, independente do apelido usado no @.
function isDirectedAtOwner(msg) {
  if (!ownNumber) return false;
  const ctx = extractContextInfo(msg.message);
  if (!ctx) return false;
  const mentioned = (ctx.mentionedJid || []).some((j) =>
    String(j).replace(/\D/g, '').startsWith(ownNumber)
  );
  const replyToOwner = ctx.participant
    ? String(ctx.participant).replace(/\D/g, '').startsWith(ownNumber)
    : false;
  return mentioned || replyToOwner;
}

function persist(msg) {
  const body = extractText(msg.message).trim();
  if (!body) return; // ignora mídias sem legenda, status, etc.

  const fromMe = !!msg.key.fromMe;
  const chat = msg.key.remoteJid || '';
  const who = msg.pushName || chat;
  // Grupos terminam em @g.us. Marcamos no subject para a extração saber que a
  // mensagem NÃO foi (necessariamente) dirigida ao dono — exceto quando ele
  // foi @mencionado ou respondido, marcado como [mencionado].
  const isGroup = chat.endsWith('@g.us');
  const directed = isGroup && !fromMe && isDirectedAtOwner(msg);

  const row = {
    direction: fromMe ? 'out' : 'in',
    external_id: msg.key.id,
    sender: fromMe ? 'me' : who,
    recipient: fromMe ? chat : 'me',
    subject: isGroup ? `[grupo]${directed ? '[mencionado]' : ''} ${chat}` : null,
    body: body.slice(0, 4000),
    received_at: msg.messageTimestamp
      ? new Date(Number(msg.messageTimestamp) * 1000).toISOString()
      : null,
    ingested_at: new Date().toISOString(),
  };

  const info = insertStmt.run(row);
  if (info.changes > 0) {
    logger.info({ direction: row.direction, chat }, 'WhatsApp: mensagem guardada');
  }
}

async function start() {
  // Reset opcional: apaga a sessão para parear do zero. Útil quando o WhatsApp
  // recusa o pareamento ("couldn't link device") por causa de estado travado.
  if (process.env.WHATSAPP_RESET === 'true' && fs.existsSync(AUTH_DIR)) {
    fs.rmSync(AUTH_DIR, { recursive: true, force: true });
    logger.warn('WHATSAPP_RESET=true: sessão apagada; pareando do zero.');
  }

  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  const { version } = await fetchLatestBaileysVersion();

  const usePairingCode = !!PAIRING_NUMBER && !state.creds.registered;
  if (usePairingCode) {
    logger.info(
      `Pareando por código para o número terminado em ...${PAIRING_NUMBER.slice(-4)} ` +
      `(${PAIRING_NUMBER.length} dígitos, com DDI).`
    );
  }

  const sock = makeWASocket({
    version,
    auth: state,
    // Com código de pareamento não imprimimos QR.
    printQRInTerminal: false,
    logger: pino({ level: 'silent' }),
    markOnlineOnConnect: false, // não altera seu status; leitura passiva
  });

  sock.ev.on('creds.update', saveCreds);

  // Pareamento por CÓDIGO (ideal para servidor/nuvem). O código expira em ~2
  // min, então geramos um novo automaticamente a cada 2 min até conectar —
  // assim você sempre tem um código válido nos logs, sem reiniciar o serviço.
  let pairingTimer = null;
  async function askPairingCode() {
    try {
      const code = await sock.requestPairingCode(PAIRING_NUMBER);
      console.log(
        `\n==================================================\n` +
        `  CÓDIGO DE PAREAMENTO: ${code}\n` +
        `  No celular: WhatsApp > Aparelhos conectados >\n` +
        `  Conectar um aparelho > Conectar com número de telefone\n` +
        `  e digite o código acima.\n` +
        `  (vale ~2 min; se expirar, um novo aparece aqui embaixo)\n` +
        `==================================================\n`
      );
    } catch (err) {
      logger.error({ err }, 'Falha ao gerar código de pareamento.');
    }
  }
  if (usePairingCode) {
    setTimeout(askPairingCode, 3000);
    pairingTimer = setInterval(askPairingCode, 120000);
  }

  sock.ev.on('connection.update', (update) => {
    const { connection, lastDisconnect, qr } = update;
    if (qr && !usePairingCode) {
      // Envia como imagem no Telegram (fácil de escanear) e também no log.
      sendQrToTelegram(qr);
      console.log('\nEscaneie este QR no WhatsApp > Aparelhos conectados:\n');
      qrcode.generate(qr, { small: true });
    }
    if (connection === 'open') {
      if (pairingTimer) { clearInterval(pairingTimer); pairingTimer = null; }
      // Guarda o número do dono para detectar @menções/replies em grupos.
      ownNumber = String(sock.user?.id || '').split(':')[0].replace(/\D/g, '');
      logger.info(
        { own: ownNumber ? `...${ownNumber.slice(-4)}` : 'desconhecido' },
        'WhatsApp conectado (somente leitura).'
      );
    }
    if (connection === 'close') {
      if (pairingTimer) { clearInterval(pairingTimer); pairingTimer = null; }
      const code = lastDisconnect?.error?.output?.statusCode;
      const loggedOut = code === DisconnectReason.loggedOut;
      logger.warn({ code }, 'Conexão fechada.');
      if (!loggedOut) {
        setTimeout(start, 3000); // reconecta (uma nova sessão/código será criada)
      } else {
        logger.error('Deslogado. Use WHATSAPP_RESET=true para parear de novo.');
        process.exit(1);
      }
    }
  });

  // Único ponto de ingestão: novas mensagens (recebidas e enviadas).
  sock.ev.on('messages.upsert', ({ messages }) => {
    for (const msg of messages) {
      try {
        persist(msg);
      } catch (err) {
        logger.error({ err }, 'Falha ao guardar mensagem.');
      }
    }
  });
}

start().catch((err) => {
  logger.error({ err }, 'Falha ao iniciar o sidecar de WhatsApp.');
  process.exit(1);
});
