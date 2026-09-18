from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
import time
from typing import Any, Dict, List, Optional
from app.digital_twin.board_twin import BoardTwinStore
from app.digital_twin.execution_state import ExecutionStore


@dataclass
class TwinSnapshot:
    """Immutable point-in-time snapshot of digital twin and execution state."""
    timestamp: float
    epoch_id: int
    twin_data: Dict[str, Any]
    exec_data: Dict[str, Any]


class TwinHistoryTracker:
    """In-memory ring-buffer history logger for state scrubbing and post-mission replay."""

    def __init__(self, max_snapshots: int = 1000):
        self._snapshots: deque[TwinSnapshot] = deque(maxlen=max_snapshots)

    def record_snapshot(self, twin: BoardTwinStore, exec_store: ExecutionStore) -> None:
        """Capture deep copy snapshot of twin and execution state."""
        snapshot = TwinSnapshot(
            timestamp=time.time(),
            epoch_id=twin.epoch_id,
            twin_data=twin.to_dict(),
            exec_data=exec_store.to_dict(),
        )
        self._snapshots.append(snapshot)

    def get_snapshots(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return serialized list of recent snapshots."""
        limit = max(1, min(limit, len(self._snapshots)))
        return [asdict(s) for s in list(self._snapshots)[-limit:]]

    def clear(self) -> None:
        self._snapshots.clear()
