"""Session recorder for persisting digital twin execution to JSONL format."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional


class SessionRecorder:
    """Records timestamped telemetry, twin states, and actuator poses to disk."""

    def __init__(self, output_dir: str | Path = "data/sessions") -> None:
        self.output_dir = Path(output_dir)
        self.is_recording = False
        self.current_session_id: Optional[str] = None
        self._file_handle: Optional[Any] = None
        self.frame_count = 0

    def start(self, session_id: str | None = None, metadata: Dict[str, Any] | None = None) -> str:
        """Start a new recording session."""
        if self.is_recording:
            self.stop()

        self.output_dir.mkdir(parents=True, exist_ok=True)
        sid = session_id or f"session_{int(time.time())}"
        self.current_session_id = sid
        session_file = self.output_dir / f"{sid}.jsonl"

        self._file_handle = open(session_file, "w", encoding="utf-8")
        self.is_recording = True
        self.frame_count = 0

        # Write header
        header = {
            "type": "HEADER",
            "session_id": sid,
            "start_time_utc": time.time(),
            "metadata": metadata or {},
        }
        self._file_handle.write(json.dumps(header) + "\n")
        self._file_handle.flush()
        return sid

    def record_frame(
        self,
        timestamp_sec: float,
        duster_pose: Dict[str, Any],
        metrics: Dict[str, Any] | None = None,
        active_waypoint: Dict[str, Any] | None = None,
        events: list | None = None,
    ) -> None:
        """Append a single state/telemetry frame to the current recording."""
        if not self.is_recording or self._file_handle is None:
            return

        frame = {
            "type": "FRAME",
            "frame_idx": self.frame_count,
            "timestamp_sec": timestamp_sec,
            "duster_pose": duster_pose,
            "metrics": metrics or {},
            "active_waypoint": active_waypoint,
            "events": events or [],
        }
        self._file_handle.write(json.dumps(frame) + "\n")
        self._file_handle.flush()
        self.frame_count += 1

    def stop(self) -> Optional[str]:
        """Stop current recording session."""
        if not self.is_recording:
            return None

        if self._file_handle is not None:
            self._file_handle.close()
            self._file_handle = None

        sid = self.current_session_id
        self.is_recording = False
        self.current_session_id = None
        return sid
