"""Session player for deterministic playback of recorded JSONL sessions."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class SessionPlayer:
    """Replays recorded telemetry sessions at variable playback speeds."""

    def __init__(self, session_path: str | Path | None = None) -> None:
        self.session_path = Path(session_path) if session_path else None
        self.header: Dict[str, Any] = {}
        self.frames: List[Dict[str, Any]] = []
        self.current_idx: int = 0
        self.speed_multiplier: float = 1.0

        if self.session_path and self.session_path.exists():
            self.load_session(self.session_path)

    def load_session(self, session_path: str | Path) -> bool:
        """Load session file from disk."""
        p = Path(session_path)
        if not p.exists():
            return False

        self.frames.clear()
        self.header.clear()
        self.current_idx = 0
        self.session_path = p

        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                if record.get("type") == "HEADER":
                    self.header = record
                elif record.get("type") == "FRAME":
                    self.frames.append(record)
        return True

    @property
    def total_frames(self) -> int:
        return len(self.frames)

    @property
    def is_finished(self) -> bool:
        return self.current_idx >= len(self.frames)

    def current_frame(self) -> Optional[Dict[str, Any]]:
        """Get the current playback frame."""
        if 0 <= self.current_idx < len(self.frames):
            return self.frames[self.current_idx]
        return None

    def seek(self, frame_index: int) -> Optional[Dict[str, Any]]:
        """Seek to a specific frame index."""
        if not self.frames:
            return None
        self.current_idx = max(0, min(frame_index, len(self.frames) - 1))
        return self.current_frame()

    def step(self, frames_to_advance: int = 1) -> Optional[Dict[str, Any]]:
        """Advance playback by a specified number of frames."""
        if not self.frames:
            return None
        self.current_idx = min(len(self.frames), self.current_idx + frames_to_advance)
        return self.current_frame()

    def reset(self) -> None:
        """Rewind playback to the start."""
        self.current_idx = 0
