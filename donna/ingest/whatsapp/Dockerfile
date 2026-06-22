# Sidecar de WhatsApp (somente leitura). Compartilha o volume data/ com o núcleo.
FROM node:20-slim

# better-sqlite3 precisa de toolchain para compilar bindings nativos.
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 make g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/whatsapp

COPY package.json ./
RUN npm install --omit=dev

COPY index.js ./

# A pasta auth/ (sessão) e o banco ficam em volumes montados.
VOLUME ["/app/whatsapp/auth"]

CMD ["node", "index.js"]
