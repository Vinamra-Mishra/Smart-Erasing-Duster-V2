from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from app.core.config import AppConfig, get_config
from app.core.events import EventBus
from app.api.stream import FrameStreamer, RtpVideoPacketizer
from app.digital_twin.board_twin import BoardTwinStore
from app.digital_twin.execution_state import ExecutionStore
from app.main import create_app
from app.schemas.events import BusEvent, EventType


def test_dynamic_home_dock_calculation():
    """Verify that get_home_dock returns exact (w/2, H - h/2, 0.0) coordinates dynamically."""
    # 1. Default config: 1000 x 700 board, 162 x 58 duster
    config = get_config()
    x, y, theta = config.get_home_dock()
    assert x == 81.0
    assert y == 671.0
    assert theta == 0.0

    # 2. Custom config: 1200 x 800 board, 200 x 60 duster
    custom = AppConfig()
    custom.system.board_width_mm = 1200.0
    custom.system.board_height_mm = 800.0
    custom.cleaning.duster_width_mm = 200.0
    custom.cleaning.duster_height_mm = 60.0
    cx, cy, ctheta = custom.get_home_dock()
    assert cx == 100.0  # 200 / 2
    assert cy == 770.0  # 800 - 60 / 2
    assert ctheta == 0.0


def test_rtp_packetizer_packetization():
    """Verify that RtpVideoPacketizer cleanly fragments and packetizes JPEG bytes without exceptions."""
    packetizer = RtpVideoPacketizer(host="127.0.0.1", port=5004, fps=30)

    # Test small packet (< 1400 bytes)
    small_data = b"\xFF\xD8" + (b"\x00" * 500) + b"\xFF\xD9"
    sent_small = packetizer.send_frame(small_data, width=1000, height=700)
    assert sent_small == 1

    # Test large packet (> 1400 bytes, e.g. 5000 bytes)
    large_data = b"\xFF\xD8" + (b"\xAA" * 4996) + b"\xFF\xD9"
    sent_large = packetizer.send_frame(large_data, width=1000, height=700)
    assert sent_large > 1

    packetizer.close()


def test_frame_streamer_generate_frame():
    """Verify that FrameStreamer renders composite HUD overlays and returns valid JPEG bytes."""
    config = get_config()
    twin = BoardTwinStore(config)
    exec_store = ExecutionStore(config)
    streamer = FrameStreamer(config, twin, exec_store)

    canvas, jpeg_bytes = streamer.generate_frame()
    assert canvas.shape == (streamer.height, streamer.width, 3)
    assert len(jpeg_bytes) > 1000
    assert jpeg_bytes[:2] == b"\xFF\xD8"  # JPEG Magic bytes


    streamer.close()


@pytest.mark.asyncio
async def test_event_bus_audit_log():
    """Verify EventBus non-blocking broadcast and audit log retrieval."""
    bus = EventBus(max_audit_entries=50)

    event = BusEvent(
        type=EventType.DUSTER_MOVED,
        payload={"x": 100.0, "y": 200.0},
    )
    await bus.broadcast_event(event)

    audit = bus.get_audit_log(limit=10)
    assert len(audit) == 1
    assert audit[0]["type"] == EventType.DUSTER_MOVED.value
    assert audit[0]["payload"]["x"] == 100.0

    await bus.close()


@pytest.mark.asyncio
async def test_fastapi_rest_endpoints():
    """Verify core FastAPI REST endpoints using httpx AsyncClient."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Health check
        res = await client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

        # 2. Dynamic config
        res_cfg = await client.get("/api/config")
        assert res_cfg.status_code == 200
        data_cfg = res_cfg.json()
        expected_y = data_cfg["config"]["system"]["board_height_mm"] - 58.0 / 2.0
        assert data_cfg["home_dock"][0] == 81.0
        assert abs(data_cfg["home_dock"][1] - expected_y) < 0.1


        # 3. Calibration
        res_cal = await client.get("/api/camera/calibration")
        assert res_cal.status_code == 200
        assert res_cal.json()["board_width_mm"] > 0

