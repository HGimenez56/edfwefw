/**
 * Sidecar de WhatsApp da Dona — SOMENTE LEITURA.
 *
 * Conecta como "aparelho vinculado" (Baileys), lê as mensagens recebidas e
 * enviadas do seu próprio número e as grava na MESMA tabela `messages` do
 * SQLite da Dona (source='whatsapp'). A partir daí, o núcleo Python já cuida de
 * extrair tarefas/pendências — este processo NÃO faz nada além de ler.
 *
 * Importante: este sidecar NUNCA envia mensagens. Não há nenhuma chamada de
 * envio aqui de propósito.
 */

const path = require('path');
const pino = require('pino');
const qrcode = require('qrcode-terminal');
const Database = require('better-sqlite3');
const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
} = require('@whiskeysockets/baileys');

const logger = pino({ level: process.env.DONA_LOG_LEVEL?.toLowerCase() || 'info' });

// Caminho do banco — o mesmo usado pelo núcleo Python (DONA_DB_PATH).
const DB_PATH = process.env.DONA_DB_PATH
  ? path.resolve(process.env.DONA_DB_PATH)
  : path.resolve(__dirname, '../../../data/dona.db');

const AUTH_DIR = path.join(__dirname, 'auth');

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
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  const { version } = await fetchLatestBaileysVersion();

  const sock = makeWASocket({
    version,
    auth: state,
    logger: pino({ level: 'silent' }),
    markOnlineOnConnect: false, // não altera seu status; leitura passiva
  });

  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('connection.update', (update) => {
    const { connection, lastDisconnect, qr } = update;
    if (qr) {
      console.log('\nEscaneie este QR no WhatsApp > Aparelhos conectados:\n');
      qrcode.generate(qr, { small: true });
    }
    if (connection === 'open') {
      logger.info('WhatsApp conectado (somente leitura).');
    }
    if (connection === 'close') {
      const code = lastDisconnect?.error?.output?.statusCode;
      const loggedOut = code === DisconnectReason.loggedOut;
      logger.warn({ code }, 'Conexão fechada.');
      if (!loggedOut) {
        setTimeout(start, 3000); // reconecta
      } else {
        logger.error('Deslogado. Apague a pasta auth/ e pareie de novo.');
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
