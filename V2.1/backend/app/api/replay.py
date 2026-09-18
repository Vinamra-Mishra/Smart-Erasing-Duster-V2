"""Replay subsystem API endpoints for recording and playback."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.replay.player import SessionPlayer
from app.replay.recorder import SessionRecorder

router = APIRouter(prefix="/api/replay", tags=["replay"])

_RECORDER = SessionRecorder()
_PLAYER = SessionPlayer()


class StartRecordRequest(BaseModel):
    """Payload to start a telemetry recording session."""
    session_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class PlayRequest(BaseModel):
    """Payload to control playback."""
    session_id: str
    action: str = Field(default="step", description="'step', 'seek', or 'reset'")
    frame_index: Optional[int] = None
    frames_to_advance: int = 1


@router.post("/record/start")
async def start_recording(payload: Optional[StartRecordRequest] = None) -> Dict[str, Any]:
    """Start recording session telemetry."""
    sid = payload.session_id if payload else None
    meta = payload.metadata if payload else None
    actual_sid = _RECORDER.start(session_id=sid, metadata=meta)
    return {"status": "recording", "session_id": actual_sid}


@router.post("/record/stop")
async def stop_recording() -> Dict[str, Any]:
    """Stop active recording session."""
    sid = _RECORDER.stop()
    if not sid:
        raise HTTPException(status_code=400, detail="No active recording session to stop")
    return {"status": "stopped", "session_id": sid, "total_frames": _RECORDER.frame_count}


@router.get("/list")
async def list_recorded_sessions() -> List[Dict[str, Any]]:
    """List all available recorded sessions on disk."""
    p = Path("data/sessions")
    if not p.exists():
        return []
    sessions = []
    for f in p.glob("*.jsonl"):
        sessions.append({
            "session_id": f.stem,
            "filename": f.name,
            "size_bytes": f.stat().st_size,
            "modified_time": f.stat().st_mtime,
        })
    return sessions


@router.post("/play")
async def control_playback(payload: PlayRequest) -> Dict[str, Any]:
    """Control playback of a recorded session."""
    session_path = Path("data/sessions") / f"{payload.session_id}.jsonl"
    if not session_path.exists():
        raise HTTPException(status_code=404, detail=f"Session {payload.session_id} not found")

    if _PLAYER.session_path != session_path:
        loaded = _PLAYER.load_session(session_path)
        if not loaded:
            raise HTTPException(status_code=500, detail="Failed to load session file")

    if payload.action == "reset":
        _PLAYER.reset()
        frame = _PLAYER.current_frame()
    elif payload.action == "seek" and payload.frame_index is not None:
        frame = _PLAYER.seek(payload.frame_index)
    else:  # step
        frame = _PLAYER.step(payload.frames_to_advance)

    return {
        "session_id": payload.session_id,
        "current_frame_index": _PLAYER.current_idx,
        "total_frames": _PLAYER.total_frames,
        "is_finished": _PLAYER.is_finished,
        "frame": frame,
    }
