#!/bin/sh
set -e

# Support HidenCloud/Pterodactyl or standard container environment variables
WEB_PORT="${SERVER_PORT:-${PORT:-24666}}"
STREAM_PORT="${RTP_PORT:-25343}"

echo "==============================================================="
echo "   Smart Erasing Duster V2.1 - Digital Twin Container"
echo "   Primary Web UI / API / WS Port: ${WEB_PORT}"
echo "   RTP UDP Streaming Port:         ${STREAM_PORT}"
echo "==============================================================="

export PORT="${WEB_PORT}"
export SERVER_PORT="${WEB_PORT}"
export RTP_PORT="${STREAM_PORT}"

# Execute Uvicorn server bound to 0.0.0.0
exec uvicorn app.main:app --host 0.0.0.0 --port "${WEB_PORT}"
