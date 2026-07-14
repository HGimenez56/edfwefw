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
const Database = require('better-sqlite3');
const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
} = require('@whiskeysockets/baileys');

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

const db = new Database(DB_PATH);
db.pragma('journal_mode = WAL');

// Mesmo contrato de `Storage.add_message` (dedup por UNIQUE(source, external_id)).
const insertStmt = db.prepare(`
  INSERT OR IGNORE INTO messages
    (source, direction, external_id, sender, recipient, subject, body,
     category, received_at, ingested_at, processed, raw)
  VALUES
    ('whatsapp', @direction, @external_id, @sender, @recipient, NULL, @body,
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

function persist(msg) {
  const body = extractText(msg.message).trim();
  if (!body) return; // ignora mídias sem legenda, status, etc.

  const fromMe = !!msg.key.fromMe;
  const chat = msg.key.remoteJid || '';
  const who = msg.pushName || chat;

  const row = {
    direction: fromMe ? 'out' : 'in',
    external_id: msg.key.id,
    sender: fromMe ? 'me' : who,
    recipient: fromMe ? chat : 'me',
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
      console.log('\nEscaneie este QR no WhatsApp > Aparelhos conectados:\n');
      qrcode.generate(qr, { small: true });
    }
    if (connection === 'open') {
      if (pairingTimer) { clearInterval(pairingTimer); pairingTimer = null; }
      logger.info('WhatsApp conectado (somente leitura).');
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
