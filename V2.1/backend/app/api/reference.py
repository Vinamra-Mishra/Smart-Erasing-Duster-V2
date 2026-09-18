"""Reference baseline epoch management API router."""
from __future__ import annotations

from typing import List, Optional
import numpy as np
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..perception.reference import (
    get_default_baseline_manager,
    BaselineEpoch,
    DirtyBoardError,
    EpochRollRejectedError,
)
from ..schemas.events import BusEvent, EventType

router = APIRouter(prefix="/api/reference", tags=["reference"])


class CaptureBaselineRequest(BaseModel):
    """Payload to trigger baseline capture."""
    allow_dirty_board_override: bool = False


class RollEpochRequest(BaseModel):
    """Payload to roll epoch after verified cleaning pass."""
    verified_residual_fraction: float = Field(..., ge=0.0, le=1.0)
    clean_threshold: float = Field(default=0.01, ge=0.0, le=1.0)


@router.get("/current", response_model=Optional[BaselineEpoch])
async def get_current_epoch() -> Optional[BaselineEpoch]:
    """Retrieve metadata of the currently active baseline reference epoch."""
    manager = get_default_baseline_manager()
    return manager.current_epoch


@router.get("/history", response_model=List[BaselineEpoch])
async def get_epoch_history() -> List[BaselineEpoch]:
    """List chronological baseline epoch history."""
    manager = get_default_baseline_manager()
    return manager.epoch_history


@router.post("/capture", response_model=BaselineEpoch)
async def capture_baseline(request: Request, payload: Optional[CaptureBaselineRequest] = None) -> BaselineEpoch:
    """Finalize accumulated frames into an authoritative baseline epoch."""
    manager = get_default_baseline_manager()
    streamer = getattr(request.app.state, "streamer", None)
    req = payload or CaptureBaselineRequest()

    # If buffer is empty, grab live frame from camera streamer
    if not manager._frame_buffer:
        canvas = None
        if streamer is not None:
            try:
                canvas, _ = streamer.generate_frame()
            except Exception:
                pass
        if canvas is None:
            canvas = np.full((700, 1000, 3), 245, dtype=np.uint8)
        for _ in range(manager.frames_to_accumulate):
            manager.add_frame(canvas)

    try:
        epoch = manager.finalize_capture(allow_override=req.allow_dirty_board_override)
        # Broadcast over WebSocket event bus
        app_manager = getattr(request.app.state, "manager", None)
        if app_manager is not None and hasattr(app_manager, "event_bus"):
            app_manager.twin_store.objects.clear()
            await app_manager.event_bus.broadcast_event(BusEvent(
                type=EventType.PHYSICAL_TWIN_UPDATED,
                payload=app_manager.twin_store.to_dict(),
            ))
            await app_manager.event_bus.broadcast_event(BusEvent(
                type=EventType.BASELINE_EPOCH_ROLLED,
                payload=epoch.model_dump(),
            ))
            await app_manager.event_bus.broadcast_event(BusEvent(
                type=EventType.RECONCILER_ACTION_DISPATCHED,
                payload={
                    "row_matched": 1,
                    "summary": f"Baseline Epoch #{epoch.epoch_id} captured (edge density: {epoch.edge_density * 100:.2f}%)",
                },
            ))
        return epoch

    except DirtyBoardError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "DIRTY_BOARD_DETECTED",
                "message": str(err),
                "edge_density": err.edge_density,
                "threshold": err.threshold,
            },
        ) from err
    except RuntimeError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err


@router.post("/roll", response_model=BaselineEpoch)
async def roll_baseline_epoch(payload: RollEpochRequest) -> BaselineEpoch:
    """Roll epoch after verified cleaning pass within tolerance."""
    manager = get_default_baseline_manager()
    current_img = manager.current_baseline
    if current_img is None:
        current_img = np.full((700, 1000, 3), 245, dtype=np.uint8)

    try:
        epoch = manager.roll_epoch(
            new_frame=current_img,
            verified_residual_fraction=payload.verified_residual_fraction,
            permanent_defect_mask=manager.permanent_defect_mask,
            clean_threshold=payload.clean_threshold,
        )
        return epoch
    except EpochRollRejectedError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "RESIDUAL_ABOVE_TOLERANCE",
                "message": str(err),
                "residual_fraction": err.residual_fraction,
                "clean_threshold": err.clean_threshold,
            },
        ) from err
