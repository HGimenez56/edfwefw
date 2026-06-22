# Imagem da Donna — leve e portável para qualquer host (VPS, Fly.io, etc.)
FROM python:3.12-slim

# Não gerar .pyc e logs sem buffer (melhor para containers)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Instala dependências primeiro (cache de camada)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código
COPY donna ./donna

# Dados persistentes (banco SQLite) ficam em /app/data — monte um volume aqui.
VOLUME ["/app/data"]

# Sobe a Donna
CMD ["python", "-m", "donna.main"]
