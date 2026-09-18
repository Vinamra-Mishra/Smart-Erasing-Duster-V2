"""Coverage path planner API endpoints with smooth actuator motion and real-time digital twin erasing."""
from __future__ import annotations

import asyncio
from datetime import datetime
import logging
import math
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.config import get_config
from app.planning.coverage import plan_boustrophedon_coverage
from app.planning.transit import plan_full_mission
from app.schemas.events import BusEvent, EventType
from app.schemas.ink import CoordinateFrame, PhysicalState
from app.schemas.planner import CleaningPlan, ExecutionState, MissionStatus, ResidualTier, Waypoint

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/planner", tags=["planner"])

# Internal runtime state for planning missions
_ACTIVE_PLAN: Optional[CleaningPlan] = None
_MISSION_STATUS: MissionStatus = MissionStatus()
_EXECUTION_TASK: Optional[asyncio.Task] = None


class PlanRequest(BaseModel):
    """Request payload for generating a cleaning trajectory."""
    target_object_ids: List[str] = Field(default_factory=list)
    target_ids: Optional[List[str]] = None
    polygons: Optional[List[List[List[float]]]] = None
    lane_overlap: Optional[float] = None
    use_full_transit: bool = True


class DispatchRequest(BaseModel):
    """Request payload for dispatching a planned trajectory."""
    plan_id: Optional[str] = None
    plan: Optional[CleaningPlan] = None


@router.post("/generate", response_model=CleaningPlan)
@router.post("/plan", response_model=CleaningPlan)
async def create_plan(request: Request, payload: Optional[PlanRequest] = None) -> CleaningPlan:
    """Generate a Boustrophedon coverage plan with exterior U-turns and Home transit."""
    global _ACTIVE_PLAN, _MISSION_STATUS
    config = getattr(request.app.state, "config", None) or get_config()
    req = payload or PlanRequest()
    polys: List[Any] = []

    target_ids = req.target_ids if req.target_ids is not None else req.target_object_ids

    # 1. Check if direct polygons supplied
    if req.polygons:
        for poly_coords in req.polygons:
            polys.append(poly_coords)

    # 2. Check digital twin store if target ids provided
    elif target_ids and hasattr(request.app.state, "manager"):
        twin = request.app.state.manager.twin_store
        for oid in target_ids:
            obj = twin.get_object(oid)
            if obj and obj.points and len(obj.points) >= 3:
                cx, cy = obj.centroid
                if cx >= 130.0 and cy >= 140.0:
                    polys.append(obj.points)

    # 3. If no specific targets, check all active ink in the digital twin
    elif hasattr(request.app.state, "manager"):
        twin = request.app.state.manager.twin_store
        active_objs = twin.get_active_ink_objects()
        for obj in active_objs:
            cx, cy = obj.centroid
            # Exclude known toolbar dock (x < 130), header (y < 140), and zoom controls
            if cx < 130.0 or cy < 140.0:
                continue
            if cx > (config.system.board_width_mm - 240.0) and cy > (config.system.board_height_mm - 75.0):
                continue
            if obj.points and len(obj.points) >= 3:
                polys.append(obj.points)

    if not polys:
        # Generate default center target scaled to dynamic board dimensions
        bw = config.system.board_width_mm
        bh = config.system.board_height_mm
        cx, cy = bw / 2.0, bh / 2.0
        w_box = min(200.0, bw * 0.4)
        h_box = min(100.0, bh * 0.4)
        polys.append([
            [round(cx - w_box / 2.0, 1), round(cy - h_box / 2.0, 1)],
            [round(cx + w_box / 2.0, 1), round(cy - h_box / 2.0, 1)],
            [round(cx + w_box / 2.0, 1), round(cy + h_box / 2.0, 1)],
            [round(cx - w_box / 2.0, 1), round(cy + h_box / 2.0, 1)],
        ])

    from shapely.ops import unary_union
    from shapely.geometry import MultiPolygon
    from app.planning.geometry import points_to_polygon

    shapely_polys = [points_to_polygon(p) for p in polys]

    # Spatial clustering: group nearby polygons (within 60mm) into distinct clusters
    # This prevents sweeping across empty space when ink is in localized clusters!
    buffered = [p.buffer(60.0) for p in shapely_polys]
    union_all = unary_union(buffered)

    if isinstance(union_all, MultiPolygon):
        cluster_hulls = list(union_all.geoms)
    else:
        cluster_hulls = [union_all] if not union_all.is_empty else []

    shapely_clusters = []
    for i, c_hull in enumerate(cluster_hulls):
        contained = [p for p in shapely_polys if c_hull.intersects(p)]
        if contained:
            shapely_clusters.append((f"cluster_{i}", unary_union(contained)))

    if not shapely_clusters:
        shapely_clusters = [(f"target_{i}", p) for i, p in enumerate(shapely_polys)]

    plan = plan_full_mission(
        target_clusters=shapely_clusters,
        lane_overlap=req.lane_overlap,
        board_height_mm=config.system.board_height_mm,
    )

    # Populate compatibility fields for frontend
    for wp in plan.waypoints:
        wp.theta = wp.theta_deg
        wp.v = wp.speed_mm_s
        wp.segment_type = wp.action.lower() if wp.action else "sweep"

    plan.estimated_duration_sec = plan.estimated_duration_s
    plan.created_at = datetime.utcnow().isoformat()

    _ACTIVE_PLAN = plan
    _MISSION_STATUS = MissionStatus(
        state=ExecutionState.PLANNING,
        total_waypoints=len(plan.waypoints),
        active_waypoint_index=0,
    )

    # Broadcast generated plan to WebSocket clients
    if hasattr(request.app.state, "manager") and hasattr(request.app.state.manager, "event_bus"):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(
                    request.app.state.manager.event_bus.broadcast_event(
                        BusEvent(
                            type=EventType.PLAN_GENERATED,
                            payload=plan.model_dump(),
                        )
                    )
                )
        except Exception:
            pass

    return plan


async def _execute_cleaning_plan_worker(manager: Any, plan: CleaningPlan) -> None:
    """Smoothly moves the duster along the trajectory and erases ink in real-time."""
    exec_store = manager.execution_store
    twin_store = manager.twin_store
    bus = manager.event_bus

    exec_store.set_state(ExecutionState.CLEANING_ACTIVE)
    await bus.broadcast_event(BusEvent(
        type=EventType.EXECUTION_STATE_CHANGED,
        payload=exec_store.to_dict(),
    ))

    waypoints = plan.waypoints
    duster_w = 162.0
    duster_h = 58.0

    try:
        dt = 0.025  # 40 Hz smooth kinematics
        for idx, wp in enumerate(waypoints):
            if exec_store.state != ExecutionState.CLEANING_ACTIVE:
                break
            exec_store.active_waypoint_index = idx

            action_name = getattr(wp, "action", "MOVE").upper()
            seg_type = getattr(wp, "segment_type", "").lower()
            is_contacting = action_name in ("WIPE", "SWEEP") or seg_type in ("sweep", "wipe")

            curr_x = float(exec_store.duster_pose.x)
            curr_y = float(exec_store.duster_pose.y)
            curr_theta = float(exec_store.duster_pose.theta)

            target_x = float(wp.x)
            target_y = float(wp.y)
            target_theta = float(getattr(wp, "theta_deg", getattr(wp, "theta", 0.0)))
            raw_speed = float(getattr(wp, "speed_mm_s", getattr(wp, "v", 120.0)))

            # Boosted snappy velocities (1.5x upgrade): transit at 570mm/s, sweep at 390mm/s, uturn at 300mm/s
            if not is_contacting or seg_type == "transit" or action_name in ("TRANSIT", "MOVE", "DOCK"):
                speed = max(570.0, raw_speed * 1.6)
            elif seg_type == "uturn":
                speed = max(300.0, raw_speed * 1.5)
            else:
                speed = max(390.0, raw_speed * 1.8)

            dist = math.hypot(target_x - curr_x, target_y - curr_y)
            d_theta = (target_theta - curr_theta + 180.0) % 360.0 - 180.0

            if dist < 0.5 and abs(d_theta) < 1.0:
                exec_store.update_pose(
                    x=target_x,
                    y=target_y,
                    theta_deg=target_theta,
                    is_contacting=is_contacting,
                    velocity_mm_s=0.0,
                )
                continue

            duration = max(dist / speed, abs(d_theta) / 180.0)
            steps = max(1, int(round(duration / dt)))

            for s in range(1, steps + 1):
                if exec_store.state != ExecutionState.CLEANING_ACTIVE:
                    break
                alpha = s / steps
                interp_x = curr_x + alpha * (target_x - curr_x)
                interp_y = curr_y + alpha * (target_y - curr_y)
                interp_theta = (curr_theta + alpha * d_theta) % 360.0

                exec_store.update_pose(
                    x=interp_x,
                    y=interp_y,
                    theta_deg=interp_theta,
                    is_contacting=is_contacting,
                    velocity_mm_s=speed,
                )

                # Real-time ink erasing when duster pad is contacting surface
                if is_contacting:
                    erased_any = False
                    for obj in twin_store.get_active_ink_objects():
                        dx = abs(obj.centroid[0] - interp_x)
                        dy = abs(obj.centroid[1] - interp_y)
                        if dx <= (duster_w / 2.0 + 15.0) and dy <= (duster_h / 2.0 + 15.0):
                            obj.state = PhysicalState.CLEANED
                            erased_any = True
                    if erased_any:
                        await bus.broadcast_event(BusEvent(
                            type=EventType.PHYSICAL_TWIN_UPDATED,
                            payload=twin_store.to_dict(),
                        ))

                    # Progressive spatial section baseline refresh (>= 98.9% confidence)
                    if hasattr(manager, "baseline_manager") and manager.baseline_manager.current_baseline is not None:
                        active_bbox = (
                            interp_x - duster_w / 2.0,
                            interp_y - duster_h / 2.0,
                            interp_x + duster_w / 2.0,
                            interp_y + duster_h / 2.0,
                        )
                        curr_board = manager.baseline_manager.current_baseline
                        refreshed_secs = manager.baseline_manager.update_section_baseline_if_clean(
                            current_frame=curr_board,
                            active_bbox_mm=active_bbox,
                            confidence_threshold=0.989,
                        )
                        for sec in refreshed_secs:
                            await bus.broadcast_event(BusEvent(
                                type=EventType.BASELINE_SECTION_REFRESHED,
                                payload={
                                    "col": sec.col,
                                    "row": sec.row,
                                    "bbox_mm": list(sec.bbox_mm),
                                    "clean_confidence": sec.clean_confidence,
                                    "refresh_count": sec.refresh_count,
                                },
                            ))

                await asyncio.sleep(dt)

        if exec_store.state == ExecutionState.CLEANING_ACTIVE:
            exec_store.set_state(ExecutionState.IDLE)
            exec_store.reset_to_home()
            exec_store.evaluate_residual(0.0)
            await bus.broadcast_event(BusEvent(
                type=EventType.EXECUTION_STATE_CHANGED,
                payload=exec_store.to_dict(),
            ))
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.warning("Error during cleaning plan execution: %s", e)


@router.post("/dispatch")
async def dispatch_plan(request: Request, payload: Optional[DispatchRequest] = None) -> Dict[str, Any]:
    """Dispatch active cleaning plan and start smooth actuator execution."""
    global _ACTIVE_PLAN, _MISSION_STATUS, _EXECUTION_TASK

    plan_to_run = payload.plan if payload and payload.plan else _ACTIVE_PLAN
    if not plan_to_run or not plan_to_run.waypoints:
        # Automatically generate plan for active ink targets, eliminating 400 Bad Request
        plan_to_run = await create_plan(request, PlanRequest(lane_overlap=0.28, use_full_transit=True))

    _ACTIVE_PLAN = plan_to_run
    _MISSION_STATUS.state = ExecutionState.CLEANING_ACTIVE
    _MISSION_STATUS.active_waypoint_index = 0
    _MISSION_STATUS.total_waypoints = len(plan_to_run.waypoints)

    if hasattr(request.app.state, "manager"):
        manager = request.app.state.manager
        # Cancel previous running execution task if active
        if _EXECUTION_TASK and not _EXECUTION_TASK.done():
            _EXECUTION_TASK.cancel()
        _EXECUTION_TASK = asyncio.create_task(_execute_cleaning_plan_worker(manager, plan_to_run))

    return {
        "status": "dispatched",
        "waypoints_count": len(plan_to_run.waypoints),
        "estimated_duration_s": plan_to_run.estimated_duration_s,
    }


@router.post("/step")
async def step_actuator(request: Request) -> Dict[str, Any]:
    """Manually advance duster to the next waypoint."""
    global _ACTIVE_PLAN
    if not _ACTIVE_PLAN or not _ACTIVE_PLAN.waypoints:
        raise HTTPException(status_code=400, detail="No active plan to step")
    if not hasattr(request.app.state, "manager"):
        raise HTTPException(status_code=500, detail="App state manager unavailable")

    manager = request.app.state.manager
    exec_store = manager.execution_store
    next_idx = (exec_store.active_waypoint_index + 1) % len(_ACTIVE_PLAN.waypoints)
    wp = _ACTIVE_PLAN.waypoints[next_idx]
    exec_store.active_waypoint_index = next_idx

    action_name = getattr(wp, "action", "MOVE").upper()
    is_contacting = action_name in ("WIPE", "SWEEP")
    exec_store.update_pose(
        x=wp.x,
        y=wp.y,
        theta_deg=getattr(wp, "theta_deg", getattr(wp, "theta", 0.0)),
        is_contacting=is_contacting,
    )
    await manager.event_bus.broadcast_event(BusEvent(
        type=EventType.EXECUTION_STATE_CHANGED,
        payload=exec_store.to_dict(),
    ))
    return {"status": "stepped", "waypoint_index": next_idx}


@router.post("/stop")
async def stop_actuator(request: Request) -> Dict[str, Any]:
    """Emergency stop actuator motion."""
    global _EXECUTION_TASK
    if _EXECUTION_TASK and not _EXECUTION_TASK.done():
        _EXECUTION_TASK.cancel()
    if hasattr(request.app.state, "manager"):
        manager = request.app.state.manager
        manager.execution_store.set_state(ExecutionState.STOPPED)
        await manager.event_bus.broadcast_event(BusEvent(
            type=EventType.EXECUTION_STATE_CHANGED,
            payload=manager.execution_store.to_dict(),
        ))
    return {"status": "stopped"}


@router.get("/status", response_model=MissionStatus)
async def get_mission_status() -> MissionStatus:
    """Return active planner telemetry and execution progress."""
    return _MISSION_STATUS


@router.post("/reset")
async def reset_planner(request: Request) -> Dict[str, Any]:
    """Reset mission plan and return duster to Home Dock."""
    global _ACTIVE_PLAN, _MISSION_STATUS, _EXECUTION_TASK
    if _EXECUTION_TASK and not _EXECUTION_TASK.done():
        _EXECUTION_TASK.cancel()

    _ACTIVE_PLAN = None
    _MISSION_STATUS = MissionStatus(state=ExecutionState.IDLE)

    if hasattr(request.app.state, "manager"):
        manager = request.app.state.manager
        manager.execution_store.reset_to_home()
        manager.execution_store.set_state(ExecutionState.IDLE)
        await manager.event_bus.broadcast_event(BusEvent(
            type=EventType.EXECUTION_STATE_CHANGED,
            payload=manager.execution_store.to_dict(),
        ))

    return {"status": "reset", "state": ExecutionState.IDLE}

