# =============================================================
# Stage 1: Build Next.js React Dashboard Static Assets
# =============================================================
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

COPY V2.1/frontend/package*.json ./
RUN npm ci --prefer-offline --no-audit || npm install

COPY V2.1/frontend/ ./
ENV NEXT_OUTPUT=export
RUN npm run build

# =============================================================
# Stage 2: Production Python Runtime (Digital Twin Engine)
# =============================================================
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    PORT=24666 \
    RTP_PORT=25343 \
    RTP_HOST=127.0.0.1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY V2.1/backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY V2.1/backend/ ./
COPY V2.1/config.yaml ./

COPY --from=frontend-builder /app/frontend/out /app/frontend_out
COPY V2.1/docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 24666
EXPOSE 25343/udp

ENTRYPOINT ["/app/docker-entrypoint.sh"]
