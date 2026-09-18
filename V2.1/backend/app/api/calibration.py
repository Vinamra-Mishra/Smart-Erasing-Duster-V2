"""Calibration API router for 4-corner homography and ArUco markers."""
from __future__ import annotations

from typing import List, Optional, Tuple
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..perception.registration import get_default_registrar, RegistrationError
from ..schemas.calibration import CalibrationStatus, CornerPoints, BoardSizePayload
from ..schemas.planner import ExecutionState

router = APIRouter(prefix="/api/calibration", tags=["calibration"])


class ManualCornersPayload(BaseModel):
    """Payload for manual 4-corner perspective registration."""
    corners: CornerPoints
    board_width_mm: Optional[float] = Field(None, ge=100.0, le=10000.0)
    board_height_mm: Optional[float] = Field(None, ge=100.0, le=10000.0)


def update_system_board_size(request: Request, board_width_mm: float, board_height_mm: float) -> None:
    """Dynamically propagate board dimensions across config, streamer, registrar, and execution stores."""
    width = float(board_width_mm)
    height = float(board_height_mm)

    # 1. Update global config singleton cache
    from ..core.config import get_config
    global_cfg = get_config()
    global_cfg.system.board_width_mm = width
    global_cfg.system.board_height_mm = height

    # 2. Update request.app.state.config
    if hasattr(request.app.state, "config") and request.app.state.config is not None:
        request.app.state.config.system.board_width_mm = width
        request.app.state.config.system.board_height_mm = height

    # 3. Update FrameStreamer
    if hasattr(request.app.state, "streamer") and request.app.state.streamer is not None:
        streamer = request.app.state.streamer
        streamer.width = int(round(width))
        streamer.height = int(round(height))

    # 4. Update HomographyRegistrar
    registrar = get_default_registrar()
    registrar.set_board_dimensions(width, height)

    # 5. Update BoardTwinStore and ExecutionStore in AppStateManager
    if hasattr(request.app.state, "manager") and request.app.state.manager is not None:
        manager = request.app.state.manager
        if hasattr(manager, "twin_store") and manager.twin_store is not None:
            manager.twin_store.set_board_dimensions(width, height)
        if hasattr(manager, "execution_store") and manager.execution_store is not None:
            if manager.execution_store.state == ExecutionState.IDLE:
                manager.execution_store.reset_to_home()

        # Broadcast state changes over WebSocket event bus
        try:
            import asyncio
            from ..schemas.events import BusEvent, EventType
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(
                    manager.event_bus.broadcast_event(
                        BusEvent(
                            type=EventType.PHYSICAL_TWIN_UPDATED,
                            payload=manager.twin_store.to_dict(),
                        )
                    )
                )
                asyncio.create_task(
                    manager.event_bus.broadcast_event(
                        BusEvent(
                            type=EventType.EXECUTION_STATE_CHANGED,
                            payload=manager.execution_store.to_dict(),
                        )
                    )
                )
        except Exception:
            pass

    # 6. Update Simulator Duster and Board if active
    try:
        from app.api.simulator import _SIM_DUSTER, _SIM_BOARD
        _SIM_DUSTER.board_width = width
        _SIM_DUSTER.board_height = height
        _SIM_DUSTER.reset_to_home()
        if hasattr(_SIM_BOARD, "set_board_dimensions"):
            _SIM_BOARD.set_board_dimensions(width, height)
    except Exception:
        pass

    # 7. Update TemporalOcclusionDetector if active
    try:
        from app.api.perception import _occlusion_detector
        if hasattr(_occlusion_detector, "set_board_dimensions"):
            _occlusion_detector.set_board_dimensions(width, height)
    except Exception:
        pass


def _build_status_response(request: Optional[Request] = None) -> CalibrationStatus:
    registrar = get_default_registrar()
    corners_cam = registrar.corners_cam
    corners_model = None
    if corners_cam and len(corners_cam) == 4:
        corners_model = CornerPoints(
            top_left=corners_cam[0],
            top_right=corners_cam[1],
            bottom_right=corners_cam[2],
            bottom_left=corners_cam[3],
        )

    sensor_w, sensor_h = 1920, 1080
    if request is not None and hasattr(request.app.state, "streamer") and request.app.state.streamer is not None:
        sensor_w, sensor_h = request.app.state.streamer.get_sensor_dimensions()

    return CalibrationStatus(
        is_calibrated=registrar.is_calibrated,
        reprojection_error_px=registrar.reprojection_error,
        homography_matrix=registrar.homography_matrix.tolist(),
        board_width_mm=registrar.board_width_mm,
        board_height_mm=registrar.board_height_mm,
        corners=corners_model,
        sensor_width=sensor_w,
        sensor_height=sensor_h,
    )


@router.get("/status", response_model=CalibrationStatus)
async def get_calibration_status(request: Request) -> CalibrationStatus:
    """Query current homography calibration state."""
    return _build_status_response(request)


@router.post("/auto-detect", response_model=CalibrationStatus)
async def auto_detect_corners(request: Request) -> CalibrationStatus:
    """Auto-detect whiteboard corners in live camera frame and calibrate homography."""
    streamer = request.app.state.streamer
    raw_frame, _ = streamer.generate_raw_frame()
    registrar = get_default_registrar()

    success, error, corners = registrar.auto_calibrate(raw_frame)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not automatically detect whiteboard boundary. Please drag corners manually.",
        )
    # Propagate the dynamically measured dimensions to all subsystems
    update_system_board_size(request, registrar.board_width_mm, registrar.board_height_mm)
    return _build_status_response(request)


@router.post("/set-corners", response_model=CalibrationStatus)
async def set_manual_corners(payload: ManualCornersPayload, request: Request) -> CalibrationStatus:
    """Calibrate homography using 4 interactive corner drag points."""
    registrar = get_default_registrar()
    if payload.board_width_mm is not None or payload.board_height_mm is not None:
        target_w = payload.board_width_mm if payload.board_width_mm is not None else registrar.board_width_mm
        target_h = payload.board_height_mm if payload.board_height_mm is not None else registrar.board_height_mm
        update_system_board_size(request, target_w, target_h)

    corners_list = payload.corners.to_list()
    try:
        registrar.calibrate_from_corners(corners_list)
    except RegistrationError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err

    return _build_status_response(request)


@router.post("/board-size", response_model=CalibrationStatus)
async def set_board_size(payload: BoardSizePayload, request: Request) -> CalibrationStatus:
    """Dynamically update physical whiteboard dimensions and recalculate homography/home dock."""
    update_system_board_size(request, payload.board_width_mm, payload.board_height_mm)
    return _build_status_response(request)


@router.post("/reset", response_model=CalibrationStatus)
async def reset_calibration(request: Request) -> CalibrationStatus:
    """Reset homography to identity."""
    registrar = get_default_registrar()
    registrar._h_matrix = np_eye = __import__("numpy").eye(3, dtype=__import__("numpy").float64)
    registrar._h_inv = np_eye.copy()
    registrar._is_calibrated = False
    registrar._reprojection_error_px = 0.0
    registrar._detected_corners_cam = None
    return _build_status_response(request)

