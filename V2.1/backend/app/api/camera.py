from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse
from app.api.stream import FrameStreamer
from app.schemas.calibration import CalibrationStatus

router = APIRouter(prefix="/api/camera", tags=["camera"])


@router.get("/stream")
async def get_camera_stream(request: Request) -> StreamingResponse:
    """Low-latency HTTP MJPEG streaming route with composite HUD debug overlays."""
    streamer: FrameStreamer = request.app.state.streamer
    return StreamingResponse(
        streamer.mjpeg_stream_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/frame")
async def get_current_frame(request: Request) -> Response:
    """Return a single snapshot JPEG frame (warped & HUD)."""
    streamer: FrameStreamer = request.app.state.streamer
    _, jpeg_bytes = streamer.generate_frame()
    return Response(content=jpeg_bytes, media_type="image/jpeg")


@router.get("/raw-frame")
async def get_raw_camera_frame(request: Request) -> Response:
    """Return an un-warped raw camera snapshot for calibration and corner alignment."""
    streamer: FrameStreamer = request.app.state.streamer
    _, jpeg_bytes = streamer.generate_raw_frame()
    return Response(content=jpeg_bytes, media_type="image/jpeg")


@router.get("/raw-stream")
async def get_raw_camera_stream(request: Request) -> StreamingResponse:
    """Un-warped raw camera MJPEG stream for interactive corner calibration."""
    streamer: FrameStreamer = request.app.state.streamer
    return StreamingResponse(
        streamer.raw_mjpeg_stream_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )



@router.get("/calibration", response_model=CalibrationStatus)
async def get_calibration_status(request: Request) -> CalibrationStatus:
    """Return board corner calibration status and homography."""
    config = request.app.state.config
    streamer: FrameStreamer = request.app.state.streamer
    sw, sh = streamer.get_sensor_dimensions()
    return CalibrationStatus(
        is_calibrated=streamer.registrar.is_calibrated,
        reprojection_error_px=streamer.registrar.reprojection_error,
        board_width_mm=config.system.board_width_mm,
        board_height_mm=config.system.board_height_mm,
        sensor_width=sw,
        sensor_height=sh,
    )


@router.get("/devices")
async def list_camera_devices(request: Request) -> dict:
    """Enumerate DirectShow video devices and identify active/OBS virtual camera feeds."""
    streamer: FrameStreamer = request.app.state.streamer
    devices = streamer.get_available_cameras()
    sw, sh = streamer.get_sensor_dimensions()

    return {
        "current_source": streamer.config.system.camera_index,
        "is_opened": streamer.cap is not None and streamer.cap.isOpened(),
        "devices": devices,
        "sensor_width": sw,
        "sensor_height": sh,
    }


@router.post("/auto-detect-source")
async def auto_detect_camera_source(request: Request) -> dict:
    """Automatically find and switch to an active OBS virtual camera or high-contrast feed."""
    streamer: FrameStreamer = request.app.state.streamer
    success, source, message = streamer.auto_detect_virtual_camera()
    sw, sh = streamer.get_sensor_dimensions()
    return {
        "success": success,
        "source": source,
        "message": message,
        "is_opened": streamer.cap is not None and streamer.cap.isOpened(),
        "sensor_width": sw,
        "sensor_height": sh,
    }


@router.get("/source")
async def get_current_camera_source(request: Request) -> dict:
    """Get current camera source and capture health."""
    streamer: FrameStreamer = request.app.state.streamer
    sw, sh = streamer.get_sensor_dimensions()
    return {
        "source": streamer.config.system.camera_index,
        "is_opened": streamer.cap is not None and streamer.cap.isOpened(),
        "is_calibrated": streamer.registrar.is_calibrated,
        "sensor_width": sw,
        "sensor_height": sh,
    }


@router.post("/source")
async def set_camera_source(request: Request, payload: dict) -> dict:
    """Dynamically set video source (e.g. index int for OBS Virtual Cam or string URL)."""
    raw_source = payload.get("source")
    if raw_source is None:
        source = 1
    elif isinstance(raw_source, str) and raw_source.strip().isdigit():
        val = int(raw_source.strip())
        source = 1 if val == 0 else val
    elif raw_source == 0 or str(raw_source).strip() in ("0", ""):
        source = 1
    else:
        source = raw_source

    streamer: FrameStreamer = request.app.state.streamer
    success = streamer.set_camera_source(source)
    sw, sh = streamer.get_sensor_dimensions()
    return {
        "success": success,
        "source": streamer.config.system.camera_index,
        "is_opened": streamer.cap is not None and streamer.cap.isOpened(),
        "sensor_width": sw,
        "sensor_height": sh,
    }

