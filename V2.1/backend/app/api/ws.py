from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.state import AppStateManager
from app.perception.reference import get_default_baseline_manager
from app.schemas.events import BusEvent, EventType
import numpy as np

logger = logging.getLogger(__name__)


router = APIRouter(tags=["websockets"])


@router.websocket("/ws/events")
async def websocket_events_endpoint(websocket: WebSocket) -> None:
    """Bidirectional WebSocket event bus endpoint."""
    manager: AppStateManager = websocket.app.state.manager
    await manager.event_bus.register_event_client(websocket)

    # Immediately push current initial states upon connection
    try:
        await websocket.send_text(json.dumps({
            "type": EventType.PHYSICAL_TWIN_UPDATED.value,
            "timestamp": asyncio.get_event_loop().time(),
            "payload": manager.twin_store.to_dict(),
        }))
        await websocket.send_text(json.dumps({
            "type": EventType.EXECUTION_STATE_CHANGED.value,
            "timestamp": asyncio.get_event_loop().time(),
            "payload": manager.execution_store.to_dict(),
        }))
    except Exception as e:
        logger.warning("Error sending initial state to client: %s", e)
        await manager.event_bus.unregister(websocket)
        return

    try:
        while True:
            raw_text = await websocket.receive_text()
            try:
                msg = json.loads(raw_text)
                msg_type = msg.get("type", "")
                payload = msg.get("payload")
                if payload is None or not isinstance(payload, dict):
                    payload = {k: v for k, v in msg.items() if k not in ("type", "timestamp")}

                if msg_type == EventType.DRAW_STROKE.value:
                    points = payload.get("points", [])
                    color_bgr = tuple(payload.get("color_bgr", [0, 0, 0]))
                    thickness = float(payload.get("thickness_mm", 6.0))
                    await manager.draw_stroke(points, color_bgr=color_bgr, thickness_mm=thickness)

                elif msg_type == EventType.MOVE_DUSTER.value:
                    x = float(payload.get("x", 81.0))
                    y = float(payload.get("y", 671.0))
                    theta = float(payload.get("theta_deg", 0.0))
                    await manager.move_duster(x, y, theta)

                elif msg_type in ("GENERATE_PLAN", "PLANNER_GENERATE"):
                    from .planner import create_plan, PlanRequest
                    class _MockReq:
                        def __init__(self, app):
                            self.app = app
                    plan_req = PlanRequest(
                        target_ids=payload.get("target_ids"),
                        lane_overlap=payload.get("lane_overlap", 0.28),
                        use_full_transit=payload.get("use_full_transit", True),
                    )
                    await create_plan(_MockReq(websocket.app), plan_req)

                elif msg_type in (EventType.DISPATCH_PLANNER.value, "DISPATCH_PLAN"):
                    from .planner import dispatch_plan, DispatchRequest
                    class _MockReq:
                        def __init__(self, app):
                            self.app = app
                    await dispatch_plan(_MockReq(websocket.app), DispatchRequest(plan_id=payload.get("plan_id")))

                elif msg_type in ("STOP_PLAN", "PLANNER_STOP"):
                    from .planner import stop_actuator
                    class _MockReq:
                        def __init__(self, app):
                            self.app = app
                    await stop_actuator(_MockReq(websocket.app))

                elif msg_type in ("RESET_PLAN", "PLANNER_RESET"):
                    from .planner import reset_planner
                    class _MockReq:
                        def __init__(self, app):
                            self.app = app
                    await reset_planner(_MockReq(websocket.app))

                elif msg_type in (EventType.TRIGGER_SCENARIO.value, "TRIGGER_SCENARIO"):
                    logger.info("Scenario triggered via WebSocket: %s", payload)
                    sc_id = payload.get("scenario_id") or payload.get("scenario") or 1
                    try:
                        sc_id = int(sc_id)
                    except (ValueError, TypeError):
                        sc_id = 1

                    from app.api.simulator import _SIM_BOARD, _SIM_DUSTER
                    from app.simulation.scenarios import load_scenario
                    from app.digital_twin.board_twin import InkObject
                    from app.schemas.ink import CoordinateFrame

                    load_scenario(_SIM_BOARD, sc_id)
                    _SIM_DUSTER.reset_to_home()
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

                    await manager.event_bus.broadcast_event(BusEvent(
                        type=EventType.PHYSICAL_TWIN_UPDATED,
                        payload=manager.twin_store.to_dict(),
                    ))

                elif msg_type == EventType.CAPTURE_BASELINE.value:
                    logger.info("Capture baseline triggered via WebSocket: %s", payload)
                    streamer = getattr(websocket.app.state, "streamer", None)
                    canvas = None
                    if streamer is not None:
                        try:
                            canvas, _ = streamer.generate_frame()
                        except Exception as e:
                            logger.warning("Error generating frame for baseline: %s", e)
                    if canvas is None:
                        canvas = np.full((700, 1000, 3), 245, dtype=np.uint8)

                    baseline_mgr = get_default_baseline_manager()
                    baseline_mgr.reset_buffer()
                    for _ in range(baseline_mgr.frames_to_accumulate):
                        baseline_mgr.add_frame(canvas)

                    allow_override = payload.get("allow_override", True) if isinstance(payload, dict) else True
                    try:
                        epoch = baseline_mgr.finalize_capture(allow_override=allow_override)
                        # All marks currently visible are now baseline / clean board: clear phantom ink
                        manager.twin_store.objects.clear()
                        await manager.event_bus.broadcast_event(BusEvent(
                            type=EventType.PHYSICAL_TWIN_UPDATED,
                            payload=manager.twin_store.to_dict(),
                        ))
                        await manager.event_bus.broadcast_event(BusEvent(
                            type=EventType.BASELINE_EPOCH_ROLLED,
                            payload=epoch.model_dump(),
                        ))
                        await manager.event_bus.broadcast_event(BusEvent(
                            type=EventType.RECONCILER_ACTION_DISPATCHED,
                            payload={
                                "row_matched": 1,
                                "summary": f"Baseline Epoch #{epoch.epoch_id} captured (edge density: {epoch.edge_density * 100:.2f}%)",
                            },
                        ))
                    except Exception as e:
                        logger.warning("Baseline capture error: %s", e)
                        await manager.event_bus.broadcast_event(BusEvent(
                            type=EventType.ERROR_ALERT,
                            payload={"error": "BASELINE_CAPTURE_FAILED", "message": str(e)},
                        ))


            except json.JSONDecodeError:
                logger.warning("Received invalid JSON on /ws/events: %s", raw_text)
            except Exception as e:
                logger.error("Error processing websocket message: %s", e)

    except WebSocketDisconnect:
        logger.info("Event client disconnected.")
    except Exception as e:
        logger.debug("Websocket exception: %s", e)
    finally:
        await manager.event_bus.unregister(websocket)


@router.websocket("/ws/telemetry")
async def websocket_telemetry_endpoint(websocket: WebSocket) -> None:
    """High-frequency telemetry stream endpoint (10-30 Hz)."""
    manager: AppStateManager = websocket.app.state.manager
    await manager.event_bus.register_telemetry_client(websocket)

    try:
        while True:
            # Client can ping or just receive; keep read loop alive
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info("Telemetry client disconnected.")
    except Exception as e:
        logger.debug("Telemetry websocket exception: %s", e)
    finally:
        await manager.event_bus.unregister(websocket)
