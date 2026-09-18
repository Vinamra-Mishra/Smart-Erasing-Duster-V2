# =============================================================
# Stage 1: Build Next.js React Dashboard Static Assets
# =============================================================
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci --prefer-offline --no-audit || npm install

COPY frontend/ ./
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

# Install system libraries for computer vision and networking
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application code and master config
COPY backend/ ./
COPY config.yaml ./

# Copy compiled frontend static assets from builder stage
COPY --from=frontend-builder /app/frontend/out /app/frontend_out

# Copy and setup entrypoint script
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Expose allocations:
# 24666: Web UI + WebSocket Bus + REST API (TCP)
# 25343: RFC 3550 / RFC 2435 Video Stream (UDP)
EXPOSE 24666
EXPOSE 25343/udp

ENTRYPOINT ["/app/docker-entrypoint.sh"]
