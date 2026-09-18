from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request
from app.core.state import AppStateManager
from app.schemas.ink import InkObjectDTO

router = APIRouter(prefix="/api/twin", tags=["digital_twin"])


@router.get("/state")
async def get_twin_state(request: Request) -> Dict[str, Any]:
    """Retrieve authoritative physical twin store status."""
    manager: AppStateManager = request.app.state.manager
    return manager.twin_store.to_dict()


@router.get("/execution")
async def get_execution_state(request: Request) -> Dict[str, Any]:
    """Retrieve authoritative execution action store status."""
    manager: AppStateManager = request.app.state.manager
    return manager.execution_store.to_dict()


@router.get("/objects", response_model=List[InkObjectDTO])
async def get_all_objects(request: Request) -> List[InkObjectDTO]:
    """Retrieve list of all tracked ink objects."""
    manager: AppStateManager = request.app.state.manager
    return [obj.to_dto() for obj in manager.twin_store.get_all_objects()]


@router.get("/objects/{object_id}", response_model=InkObjectDTO)
async def get_object_by_id(object_id: str, request: Request) -> InkObjectDTO:
    """Retrieve details for a specific ink object."""
    manager: AppStateManager = request.app.state.manager
    obj = manager.twin_store.get_object(object_id)
    if not obj:
        raise HTTPException(status_code=404, detail=f"Object '{object_id}' not found in Physical Twin.")
    return obj.to_dto()


@router.get("/history")
async def get_twin_history(request: Request, limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieve historical snapshots of digital twin states."""
    manager: AppStateManager = request.app.state.manager
    return manager.history.get_snapshots(limit=limit)


@router.post("/reset")
async def reset_twin(request: Request) -> Dict[str, str]:
    """Reset physical twin and execution stores to clean initial state.
    Also syncs the FrameStreamer's live twin_store reference so the
    perception pipeline stops re-injecting the just-cleared ink objects.
    """
    manager: AppStateManager = request.app.state.manager

    curr_w = manager.twin_store.width_mm
    curr_h = manager.twin_store.height_mm

    # Replace both stores while retaining current measured board dimensions
    new_twin = manager.twin_store.__class__(manager.config)
    new_twin.set_board_dimensions(curr_w, curr_h)
    manager.twin_store = new_twin
    manager.execution_store.reset_to_home()
    manager.history.clear()

    # Sync FrameStreamer so it writes to the fresh store from now on
    if hasattr(request.app.state, "streamer") and request.app.state.streamer is not None:
        streamer = request.app.state.streamer
        streamer.twin_store = new_twin
        streamer.exec_store = manager.execution_store
        streamer.frame_count = 0  # Re-trigger auto-calibration on next frame

    from app.perception.reference import get_default_baseline_manager
    get_default_baseline_manager()._current_baseline = None

    # Broadcast cleared state to all WebSocket clients
    from app.schemas.events import BusEvent, EventType
    await manager.event_bus.broadcast_event(BusEvent(
        type=EventType.PHYSICAL_TWIN_UPDATED,
        payload=new_twin.to_dict(),
    ))

    return {"status": "success", "message": "Digital Twin flushed to pristine state."}

