from __future__ import annotations

import asyncio
from collections import deque
import json
import logging
from typing import Any, Dict, List, Set
from fastapi import WebSocket
from app.schemas.events import BusEvent, TelemetryPayload

logger = logging.getLogger(__name__)


class EventBus:
    """Non-blocking asynchronous event bus and audit logger for WebSockets."""

    def __init__(self, max_audit_entries: int = 1000):
        self._event_clients: Set[WebSocket] = set()
        self._telemetry_clients: Set[WebSocket] = set()
        self._audit_log: deque[Dict[str, Any]] = deque(maxlen=max_audit_entries)
        self._lock = asyncio.Lock()

    async def register_event_client(self, ws: WebSocket) -> None:
        """Register a client for control & state events."""
        await ws.accept()
        async with self._lock:
            self._event_clients.add(ws)
        logger.info("Registered event client. Total: %d", len(self._event_clients))

    async def register_telemetry_client(self, ws: WebSocket) -> None:
        """Register a client for high-frequency telemetry."""
        await ws.accept()
        async with self._lock:
            self._telemetry_clients.add(ws)
        logger.info("Registered telemetry client. Total: %d", len(self._telemetry_clients))

    async def unregister(self, ws: WebSocket) -> None:
        """Remove disconnected websocket client."""
        async with self._lock:
            self._event_clients.discard(ws)
            self._telemetry_clients.discard(ws)

    async def broadcast_event(self, event: BusEvent | Dict[str, Any]) -> None:
        """Broadcast event to all event subscribers and append to audit log."""
        if isinstance(event, BusEvent):
            data = event.model_dump()
        else:
            data = event

        self._audit_log.append(data)

        if not self._event_clients:
            return

        payload = json.dumps(data)
        async with self._lock:
            clients = list(self._event_clients)

        dead_clients = []
        for client in clients:
            try:
                await client.send_text(payload)
            except Exception as e:
                logger.debug("Failed sending to event client: %s", e)
                dead_clients.append(client)

        if dead_clients:
            async with self._lock:
                for dc in dead_clients:
                    self._event_clients.discard(dc)

    async def broadcast_telemetry(self, telemetry: TelemetryPayload | Dict[str, Any]) -> None:
        """Broadcast high-frequency telemetry payload to telemetry subscribers."""
        if not self._telemetry_clients:
            return

        if isinstance(telemetry, TelemetryPayload):
            payload = json.dumps(telemetry.model_dump())
        else:
            payload = json.dumps(telemetry)

        async with self._lock:
            clients = list(self._telemetry_clients)

        dead_clients = []
        for client in clients:
            try:
                await client.send_text(payload)
            except Exception as e:
                logger.debug("Failed sending to telemetry client: %s", e)
                dead_clients.append(client)

        if dead_clients:
            async with self._lock:
                for dc in dead_clients:
                    self._telemetry_clients.discard(dc)

    def get_audit_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return recent audit log entries."""
        limit = max(1, min(limit, len(self._audit_log)))
        return list(self._audit_log)[-limit:]

    async def close(self) -> None:
        """Close all active WebSocket connections cleanly."""
        async with self._lock:
            all_clients = list(self._event_clients.union(self._telemetry_clients))
            self._event_clients.clear()
            self._telemetry_clients.clear()

        for client in all_clients:
            try:
                await client.close()
            except Exception:
                pass
