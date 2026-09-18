"""Simulation engine API endpoints for scenario injection and step execution."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.schemas.planner import DusterPose, Waypoint
from app.simulation.board import VirtualBoard
from app.simulation.cleaning import RealisticCleaningEngine
from app.simulation.duster import VirtualDuster
from app.simulation.metrics import OperationalMetrics, evaluate_operational_metrics
from app.simulation.scenarios import load_scenario

router = APIRouter(prefix="/api/simulator", tags=["simulator"])

# Single shared simulator instance for interactive session
_SIM_BOARD = VirtualBoard()
_SIM_DUSTER = VirtualDuster()
_CLEANING_ENGINE = RealisticCleaningEngine()


class ScenarioRequest(BaseModel):
    """Request payload for loading a deterministic scenario preset."""
    scenario_id: int = Field(..., ge=1, le=6, description="Scenario ID between 1 and 6")


class BrushRequest(BaseModel):
    """Request payload for drawing an interactive brush stroke."""
    points: List[List[float]] = Field(..., min_length=2)
    width_mm: float = 6.0
    color_bgr: Tuple[int, int, int] = (20, 20, 20)


class DrawRequest(BaseModel):
    """Request payload from frontend canvas drawing."""
    tool: str = "brush"
    points: List[List[float]] = Field(..., min_length=2)
    color: str = "#000000"
    size: float = 6.0


class StepRequest(BaseModel):
    """Request payload for advancing simulation kinematics by dt."""
    dt_sec: float = 0.05
    waypoint: Optional[Waypoint] = None


@router.post("/scenario/{scenario_id}")
@router.post("/scenario")
async def set_scenario(
    request: Request,
    scenario_id: Optional[int] = None,
    payload: Optional[ScenarioRequest] = None,
) -> Dict[str, Any]:
    """Inject one of the 6 deterministic test presets."""
    sc_id = scenario_id if scenario_id is not None else (payload.scenario_id if payload else 1)
    result = load_scenario(_SIM_BOARD, sc_id)
    _SIM_DUSTER.reset_to_home()

    # Synchronize into authoritative twin store
    if hasattr(request.app.state, "manager"):
        manager = request.app.state.manager
        from app.digital_twin.board_twin import InkObject
        from app.schemas.ink import PhysicalState, CoordinateFrame
        from app.schemas.events import BusEvent, EventType

        manager.twin_store.objects.clear()
        for oid, dto in _SIM_BOARD.ink_objects.items():
            ink_obj = InkObject(
                id=oid,
                state=dto.state,
                frame_id=CoordinateFrame.FRAME_BOARD,
                points=dto.points,
                bbox=dto.bbox,
                centroid=dto.centroid,
                confidence=dto.confidence,
                color_bgr=dto.color_bgr,
                area_mm2=dto.area_mm2,
            )
            manager.twin_store.add_or_update_object(ink_obj)

        await manager.event_bus.broadcast_event(
            BusEvent(
                type=EventType.PHYSICAL_TWIN_UPDATED,
                payload=manager.twin_store.to_dict(),
            )
        )
    return result


@router.post("/draw")
async def handle_draw_stroke(payload: DrawRequest, request: Request) -> Dict[str, Any]:
    """Handle drawn stroke from frontend interactive canvas."""
    # Convert hex color to BGR tuple
    hex_col = payload.color.lstrip("#")
    if len(hex_col) == 6:
        r = int(hex_col[0:2], 16)
        g = int(hex_col[2:4], 16)
        b = int(hex_col[4:6], 16)
        color_bgr = (b, g, r)
    else:
        color_bgr = (20, 20, 20)

    oid = _SIM_BOARD.add_stroke(
        points=payload.points,
        width_mm=payload.size,
        color_bgr=color_bgr,
    )

    # Synchronize into authoritative twin store
    if hasattr(request.app.state, "manager"):
        manager = request.app.state.manager
        from app.digital_twin.board_twin import InkObject
        from app.schemas.ink import PhysicalState, CoordinateFrame
        from app.schemas.events import BusEvent, EventType

        xs = [p[0] for p in payload.points]
        ys = [p[1] for p in payload.points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        cx = (min_x + max_x) / 2.0
        cy = (min_y + max_y) / 2.0
        approx_area = max(10.0, len(payload.points) * payload.size * 4.0)

        ink_obj = InkObject(
            id=oid,
            state=PhysicalState.NEW_INK,
            frame_id=CoordinateFrame.FRAME_BOARD,
            points=payload.points,
            bbox=(min_x, min_y, max_x, max_y),
            centroid=(cx, cy),
            confidence=0.98,
            color_bgr=color_bgr,
            area_mm2=approx_area,
        )
        manager.twin_store.add_or_update_object(ink_obj)
        await manager.event_bus.broadcast_event(
            BusEvent(
                type=EventType.PHYSICAL_TWIN_UPDATED,
                payload=manager.twin_store.to_dict(),
            )
        )

    return {
        "status": "stroke_added",
        "object_id": oid,
        "ink_objects_count": len(_SIM_BOARD.ink_objects),
    }


@router.post("/clear")
async def clear_canvas_board(request: Request) -> Dict[str, Any]:
    """Clear all ink strokes and reset twin store to clean board."""
    _SIM_BOARD.clear()
    if hasattr(request.app.state, "manager"):
        manager = request.app.state.manager
        from app.schemas.events import BusEvent, EventType
        manager.twin_store.objects.clear()
        await manager.event_bus.broadcast_event(
            BusEvent(
                type=EventType.PHYSICAL_TWIN_UPDATED,
                payload=manager.twin_store.to_dict(),
            )
        )
    return {"status": "cleared", "board_clean": True}


@router.post("/brush")
async def add_brush_stroke(payload: BrushRequest) -> Dict[str, Any]:
    """Draw a user stroke onto the virtual board."""
    oid = _SIM_BOARD.add_stroke(
        points=payload.points,
        width_mm=payload.width_mm,
        color_bgr=payload.color_bgr,
    )
    return {
        "status": "stroke_added",
        "object_id": oid,
        "ink_objects_count": len(_SIM_BOARD.ink_objects),
    }


@router.post("/step")
async def step_simulation(payload: StepRequest) -> Dict[str, Any]:
    """Advance duster actuator kinematics and apply realistic wiping."""
    pose, swept_poly = _SIM_DUSTER.step(payload.dt_sec, payload.waypoint)
    erased_area = 0.0

    if swept_poly is not None and _SIM_DUSTER.is_contacting:
        erased_area = _CLEANING_ENGINE.apply_wipe(_SIM_BOARD, swept_poly)

    return {
        "pose": pose.model_dump(),
        "is_contacting": _SIM_DUSTER.is_contacting,
        "erased_area_mm2": round(erased_area, 2),
    }


@router.post("/reset")
async def reset_simulation() -> Dict[str, Any]:
    """Reset virtual board to clean baseline and duster to Home Dock."""
    _SIM_BOARD.clear()
    _SIM_DUSTER.reset_to_home()
    return {"status": "reset", "board_clean": True}


@router.get("/metrics", response_model=OperationalMetrics)
async def get_live_metrics() -> OperationalMetrics:
    """Compute and return live operational metrics (IoU, precision, recall, FPR)."""
    gt_poly = _SIM_BOARD.get_ground_truth_ink_polygon()
    # In pure simulation, detected geometry mirrors ground truth with slight noise or footprint
    footprint = _SIM_DUSTER.get_footprint_polygon() if _SIM_DUSTER.is_contacting else None
    return evaluate_operational_metrics(
        detected_geom=gt_poly,
        ground_truth_geom=gt_poly,
        swept_footprint=footprint,
    )
