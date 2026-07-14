#!/usr/bin/env sh
# Inicia a Donna. Se WHATSAPP_ENABLED=true, sobe também o sidecar de WhatsApp
# (somente leitura) no MESMO container, compartilhando o banco em /app/data.
set -e

# Pausa temporária do WhatsApp controlada por código. Para PAUSAR os QRs:
# mude para "true" e faça push. "false" = WhatsApp ativo normalmente.
WHATSAPP_PAUSE="false"

if [ "$WHATSAPP_ENABLED" = "true" ] && [ "$WHATSAPP_PAUSE" != "true" ]; then
  echo "[start] WhatsApp habilitado — subindo o sidecar (somente leitura)..."
  # roda em segundo plano; reinicia sozinho se cair, sem derrubar o núcleo
  ( cd /app/donna/ingest/whatsapp && while true; do node index.js; echo "[wa] caiu, reiniciando em 5s"; sleep 5; done ) &
fi

echo "[start] Subindo o núcleo da Donna..."
exec python3 -m donna.main
