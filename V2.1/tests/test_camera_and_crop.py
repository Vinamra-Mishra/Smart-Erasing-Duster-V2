"""Tests for whiteboard auto-cropping, manual calibration, camera discovery, and ink detection."""
from __future__ import annotations

import sys
from pathlib import Path
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

backend_path = Path(__file__).resolve().parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.core.config import load_config
from app.core.state import AppStateManager
from app.api.stream import FrameStreamer
from app.main import create_app
from app.perception.registration import HomographyRegistrar
from app.perception.strokes import StrokeExtractor


@pytest.fixture
def app_client():
    application = create_app()
    with TestClient(application) as client:
        yield client, application


def test_whiteboard_auto_detect_contour():
    """Verify contour-based whiteboard boundary detection when no ArUco markers are present."""
    reg = HomographyRegistrar(board_width_mm=1000.0, board_height_mm=700.0)

    # Synthetic camera frame: dark room background (gray ~40) with bright whiteboard (gray ~240)
    frame = np.full((480, 640, 3), 40, dtype=np.uint8)

    # Insert bright whiteboard quad: TL=(40, 30), TR=(600, 40), BR=(590, 440), BL=(50, 450)
    wb_pts = np.array([[40, 30], [600, 40], [590, 440], [50, 450]], dtype=np.int32)
    cv2.fillPoly(frame, [wb_pts], (240, 240, 240))
    cv2.polylines(frame, [wb_pts], True, (60, 60, 60), 3)

    # Draw some marker text strokes on the board
    cv2.putText(frame, "SMART DUSTER TEST", (100, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (20, 20, 20), 2)
    cv2.line(frame, (100, 230), (450, 230), (0, 0, 180), 3)

    corners = reg.detect_whiteboard_corners(frame)
    assert corners is not None, "Failed to auto-detect whiteboard corners from bright quad contour"
    assert len(corners) == 4

    # Verify corner positions correspond approximately to TL, TR, BR, BL
    tl, tr, br, bl = corners
    assert abs(tl[0] - 40) < 15 and abs(tl[1] - 30) < 15
    assert abs(tr[0] - 600) < 15 and abs(tr[1] - 40) < 15
    assert abs(br[0] - 590) < 15 and abs(br[1] - 440) < 15
    assert abs(bl[0] - 50) < 15 and abs(bl[1] - 450) < 15

    # Verify auto_calibrate succeeds with low reprojection error
    success, error, auto_corners = reg.auto_calibrate(frame)
    assert success
    assert auto_corners is not None
    assert error < 0.05


def test_detect_whiteboard_ink_with_blackhat():
    """Verify ink detection extracts dark marker text and strokes on whiteboard surface."""
    ext = StrokeExtractor(min_area_mm2=10.0, max_thickness_mm=14.0)

    # Whiteboard canvas (1000 x 700 mm)
    board = np.full((700, 1000, 3), 245, dtype=np.uint8)

    # Add gradient shading to simulate non-uniform room illumination
    gradient = np.linspace(220, 255, 1000, dtype=np.uint8)
    for row in range(700):
        board[row, :, 0] = gradient
        board[row, :, 1] = gradient
        board[row, :, 2] = gradient

    # Draw marker text and geometrical strokes
    cv2.putText(board, "ALGEBRA 101", (200, 250), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (25, 25, 30), 4)
    cv2.rectangle(board, (200, 280), (500, 450), (20, 120, 30), 4)
    cv2.circle(board, (700, 350), 60, (180, 30, 20), 4)

    strokes = ext.detect_whiteboard_ink(board)
    assert len(strokes) > 0, "Failed to detect strokes on whiteboard"

    # Verify extracted strokes contain valid polygons, centroids, and areas
    for stroke in strokes:
        assert stroke.area_mm2 > 10.0
        assert len(stroke.polygon.points) >= 3
        assert 0 <= stroke.centroid[0] <= 1000
        assert 0 <= stroke.centroid[1] <= 700


def test_camera_device_enumeration():
    """Verify list_available_cameras returns devices on host."""
    devices = FrameStreamer.list_available_cameras()
    assert isinstance(devices, list)
    # If host has cameras, each entry must have expected fields
    for dev in devices:
        assert "index" in dev
        assert "name" in dev
        assert "is_opened" in dev
        assert "width" in dev
        assert "height" in dev
        assert "is_obs_candidate" in dev


def test_camera_api_endpoints(app_client):
    """Test camera REST endpoints: /devices, /source, /auto-detect-source."""
    client, application = app_client

    # 1. GET /api/camera/devices
    resp = client.get("/api/camera/devices")
    assert resp.status_code == 200
    data = resp.json()
    assert "current_source" in data
    assert "devices" in data

    # 2. GET /api/camera/source
    resp = client.get("/api/camera/source")
    assert resp.status_code == 200
    data = resp.json()
    assert "source" in data
    assert "is_opened" in data

    # 3. POST /api/camera/source (verify default 1 and redirection of index 0 / null / empty)
    for test_payload in [{}, {"source": 0}, {"source": "0"}, {"source": "  0  "}, {"source": None}, {"source": ""}, {"source": 1}, {"source": "1"}]:
        resp = client.post("/api/camera/source", json=test_payload)
        assert resp.status_code == 200
        assert resp.json()["source"] == 1, f"Failed for payload: {test_payload}"

    # 4. POST /api/camera/auto-detect-source
    resp = client.post("/api/camera/auto-detect-source")
    assert resp.status_code == 200
    assert resp.json()["success"] in [True, False]
    assert "source" in resp.json()

    # 4. POST /api/calibration/set-corners
    corners_payload = {
        "corners": {
            "top_left": [20.0, 20.0],
            "top_right": [620.0, 20.0],
            "bottom_right": [620.0, 460.0],
            "bottom_left": [20.0, 460.0],
        }
    }
    resp = client.post("/api/calibration/set-corners", json=corners_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_calibrated"] is True
    assert data["corners"] is not None

    # 5. GET /api/calibration/status
    resp = client.get("/api/calibration/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_calibrated"] is True
    assert len(data["homography_matrix"]) == 3

    # 6. POST /api/calibration/reset
    resp = client.post("/api/calibration/reset")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_calibrated"] is False


def test_twin_sync_with_manager_broadcast():
    """Verify extracted strokes synchronize with twin store and broadcast updates."""
    cfg = load_config()
    manager = AppStateManager(cfg)
    streamer = FrameStreamer(cfg, manager.twin_store, manager.execution_store, manager=manager)

    ext = StrokeExtractor()
    board = np.full((700, 1000, 3), 245, dtype=np.uint8)
    cv2.putText(board, "TESTINK", (100, 150), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (10, 10, 10), 3)

    strokes = ext.detect_whiteboard_ink(board)
    assert len(strokes) > 0

    streamer._sync_strokes_with_twin(strokes)
    assert len(streamer.twin_store.objects) > 0
    # Confirm objects are recognized in twin store
    active_objs = streamer.twin_store.get_active_ink_objects()
    assert len(active_objs) > 0


def test_system_config_camera_index_validator():
    """Verify SystemConfig pydantic model enforces camera_index redirection away from 0."""
    from app.core.config import SystemConfig

    assert SystemConfig(camera_index=0).camera_index == 1
    assert SystemConfig(camera_index="0").camera_index == 1
    assert SystemConfig(camera_index="  0  ").camera_index == 1
    assert SystemConfig(camera_index=1).camera_index == 1
    assert SystemConfig(camera_index="rtsp://test").camera_index == "rtsp://test"


def test_1080p_sensor_resolution_and_raw_frame(app_client):
    """Verify 1080p sensor configuration in FrameStreamer and endpoints."""
    client, application = app_client
    streamer: FrameStreamer = application.state.streamer

    # Streamer default sensor dimension should be 1080p (1920x1080)
    w, h = streamer.get_sensor_dimensions()
    assert w == 1920
    assert h == 1080

    raw_frame, jpeg_bytes = streamer.generate_raw_frame()
    assert raw_frame.shape[0] == 1080
    assert raw_frame.shape[1] == 1920
    assert len(jpeg_bytes) > 0

    # Verify calibration status returns 1080p sensor dimensions
    resp = client.get("/api/calibration/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["sensor_width"] == 1920
    assert data["sensor_height"] == 1080

    # Verify camera devices endpoint returns sensor dimensions
    resp = client.get("/api/camera/devices")
    assert resp.status_code == 200
    data = resp.json()
    assert data["sensor_width"] == 1920
    assert data["sensor_height"] == 1080


def test_dynamic_board_size_endpoint(app_client):
    """Verify POST /api/calibration/board-size dynamically updates dimensions across system."""
    client, application = app_client

    payload = {
        "board_width_mm": 1400.0,
        "board_height_mm": 900.0,
    }
    resp = client.post("/api/calibration/board-size", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["board_width_mm"] == 1400.0
    assert data["board_height_mm"] == 900.0

    # Verify AppConfig was dynamically mutated
    assert application.state.config.system.board_width_mm == 1400.0
    assert application.state.config.system.board_height_mm == 900.0

    # Verify FrameStreamer dimensions were updated
    assert application.state.streamer.width == 1400
    assert application.state.streamer.height == 900

    # Verify HomographyRegistrar dimensions were updated
    from app.perception.registration import get_default_registrar
    reg = get_default_registrar()
    assert reg.board_width_mm == 1400.0
    assert reg.board_height_mm == 900.0

    # Verify dynamic Home Dock recalculated correctly:
    # x = 162/2 = 81.0, y = 900 - 58/2 = 871.0
    x_home, y_home, _ = application.state.config.get_home_dock()
    assert x_home == pytest.approx(81.0)
    assert y_home == pytest.approx(871.0)

    # Verify ExecutionStore duster pose updated to new Home Dock
    exec_store = application.state.manager.execution_store
    assert exec_store.duster_pose.x == pytest.approx(81.0)
    assert exec_store.duster_pose.y == pytest.approx(871.0)


def test_dynamic_board_size_with_set_corners(app_client):
    """Verify POST /api/calibration/set-corners updates board size simultaneously."""
    client, application = app_client

    payload = {
        "corners": {
            "top_left": [30.0, 30.0],
            "top_right": [1890.0, 30.0],
            "bottom_right": [1890.0, 1050.0],
            "bottom_left": [30.0, 1050.0],
        },
        "board_width_mm": 1200.0,
        "board_height_mm": 800.0,
    }
    resp = client.post("/api/calibration/set-corners", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_calibrated"] is True
    assert data["board_width_mm"] == 1200.0
    assert data["board_height_mm"] == 800.0

    from app.perception.registration import get_default_registrar
    from app.perception.frames import Point2D, CoordinateFrame
    reg = get_default_registrar()
    br_cam = Point2D(x=1890.0, y=1050.0, frame=CoordinateFrame.FRAME_CAMERA)
    br_board = reg.point_cam_to_board(br_cam)
    assert br_board.x == pytest.approx(1200.0, abs=1e-1)
    assert br_board.y == pytest.approx(800.0, abs=1e-1)


def test_invalid_board_dimensions_rejected(app_client):
    """Verify pydantic validation rejects unphysical board dimensions."""
    client, _ = app_client

    # Too small (<= 100 mm)
    resp = client.post("/api/calibration/board-size", json={"board_width_mm": 50.0, "board_height_mm": 500.0})
    assert resp.status_code == 422

    # Negative
    resp = client.post("/api/calibration/board-size", json={"board_width_mm": -1000.0, "board_height_mm": 700.0})
    assert resp.status_code == 422

    # Too large (> 10000 mm)
    resp = client.post("/api/calibration/board-size", json={"board_width_mm": 20000.0, "board_height_mm": 700.0})
    assert resp.status_code == 422


def test_1080p_whiteboard_auto_detect_contour():
    """Verify contour-based whiteboard boundary detection on native 1080p frame (1920x1080)."""
    reg = HomographyRegistrar(board_width_mm=1200.0, board_height_mm=800.0)

    # 1080p frame: dark surround with bright board quad
    frame = np.full((1080, 1920, 3), 35, dtype=np.uint8)
    wb_pts = np.array([[150, 90], [1770, 110], [1750, 990], [160, 980]], dtype=np.int32)
    cv2.fillPoly(frame, [wb_pts], (245, 245, 245))
    cv2.polylines(frame, [wb_pts], True, (50, 50, 50), 3)

    cv2.putText(frame, "1080p SENSOR TEST", (400, 500), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (30, 30, 30), 3)

    corners = reg.detect_whiteboard_corners(frame)
    assert corners is not None, "Failed to auto-detect corners on 1080p frame"
    assert len(corners) == 4

    tl, tr, br, bl = corners
    assert abs(tl[0] - 150) < 25 and abs(tl[1] - 90) < 25
    assert abs(tr[0] - 1770) < 25 and abs(tr[1] - 110) < 25
    assert abs(br[0] - 1750) < 25 and abs(br[1] - 990) < 25
    assert abs(bl[0] - 160) < 25 and abs(bl[1] - 980) < 25

    success, error, auto_corners = reg.auto_calibrate(frame)
    assert success
    assert auto_corners is not None
    assert error < 0.05

    # Dimensions are now measured from the detected corner pixel distances (dynamic)
    expected_w = int(round(reg.board_width_mm))
    expected_h = int(round(reg.board_height_mm))
    assert expected_w > 100 and expected_h > 100, "Measured dimensions must be non-trivial"

    # Test warping to the dynamically measured board resolution
    warped = reg.warp_to_board(frame)
    assert warped.shape == (expected_h, expected_w, 3), (
        f"Warp shape mismatch: got {warped.shape}, "
        f"expected ({expected_h}, {expected_w}, 3) from measured corners"
    )


def test_dynamic_board_planner_and_twin_clone(app_client):
    """Verify dynamic board dimensions propagate correctly into planner trajectory and twin clone."""
    client, application = app_client

    # Set dynamic board size to 1500 x 850 mm
    resp = client.post("/api/calibration/board-size", json={
        "board_width_mm": 1500.0,
        "board_height_mm": 850.0,
    })
    assert resp.status_code == 200

    # Dynamic home dock should be at y = 850 - 58/2 = 821.0
    x_home, y_home, _ = application.state.config.get_home_dock()
    assert x_home == pytest.approx(81.0)
    assert y_home == pytest.approx(821.0)

    # Test BoardTwinStore.clone preserves dynamic dimensions
    twin = application.state.manager.twin_store
    assert twin.width_mm == 1500
    assert twin.height_mm == 850
    assert twin.uncertainty_mask.shape == (850, 1500)

    cloned_twin = twin.clone()
    assert cloned_twin.width_mm == 1500
    assert cloned_twin.height_mm == 850
    assert cloned_twin.uncertainty_mask.shape == (850, 1500)
    assert cloned_twin.board_occlusion_mask.shape == (850, 1500)
    assert cloned_twin.permanent_defect_mask.shape == (850, 1500)

    # Test /api/planner/plan generates waypoints starting/ending at dynamic home dock
    resp = client.post("/api/planner/plan", json={"use_full_transit": True})
    assert resp.status_code == 200
    plan = resp.json()
    wps = plan["waypoints"]
    assert len(wps) >= 2
    # First and last waypoint should be at dynamic dock (81.0, 821.0)
    assert wps[0]["x"] == pytest.approx(81.0)
    assert wps[0]["y"] == pytest.approx(821.0)
    assert wps[-1]["x"] == pytest.approx(81.0)
    assert wps[-1]["y"] == pytest.approx(821.0)


def test_stroke_extractor_detects_hollow_loops():
    """Verify that looped marker lines extract inner holes so SVG renders them hollow instead of solid blobs."""
    extractor = StrokeExtractor(min_area_mm2=20.0, approx_epsilon_mm=1.0)

    # 400x400 blank mask
    mask = np.zeros((400, 400), dtype=np.uint8)
    evidence = np.ones((400, 400), dtype=np.float32)

    # Draw a hollow loop (circle with thickness 8)
    cv2.circle(mask, (200, 200), 60, 255, thickness=8)
    # Add an entry/exit stroke tail
    cv2.line(mask, (50, 300), (200, 260), 255, thickness=8)
    cv2.line(mask, (200, 260), (350, 320), 255, thickness=8)

    strokes = extractor.extract_strokes(mask, evidence)
    assert len(strokes) == 1, f"Expected 1 connected stroke with a loop, got {len(strokes)}"

    stroke = strokes[0]
    assert len(stroke.polygon.holes) >= 1, "Expected inner hole to be extracted for hollow loop"
    hole = stroke.polygon.holes[0]
    assert len(hole) >= 3, "Hole should be a valid polygon with at least 3 vertices"

    # Hole centroid should be close to circle center (200, 200)
    hx = sum(p[0] for p in hole) / len(hole)
    hy = sum(p[1] for p in hole) / len(hole)
    assert abs(hx - 200) < 10 and abs(hy - 200) < 10


def test_floating_toolbar_ui_masking():
    """Verify that floating bottom pen toolbar and fixed UI elements are masked out."""
    extractor = StrokeExtractor(min_area_mm2=20.0)

    # Synthetic 1920x1080 online whiteboard
    board = np.full((1080, 1920, 3), 250, dtype=np.uint8)

    # 1. Real marker ink in canvas center
    cv2.putText(board, "REAL INK TEXT", (500, 500), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (20, 20, 20), 4)

    # 2. Floating bottom pen dock icons (like Excalidraw / Miro pen toolbar at y ~ 1020, x ~ 960)
    cv2.rectangle(board, (800, 1000), (1120, 1060), (230, 230, 230), -1)
    cv2.putText(board, "A A A", (850, 1040), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (10, 10, 10), 3)

    # 3. Header title / tabs (y < 100)
    cv2.putText(board, "ONLINE WHITEBOARD", (200, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (10, 10, 10), 3)

    strokes = extractor.detect_whiteboard_ink(board, mask_browser_ui=True)

    # Real ink in the center must be detected
    found_real_ink = any(s.centroid[1] > 400 and s.centroid[1] < 600 for s in strokes)
    assert found_real_ink, "Expected center marker ink to be detected"

    # Floating toolbar at bottom and header at top must be masked out
    found_toolbar_ink = any(s.centroid[1] > 980 for s in strokes)
    assert not found_toolbar_ink, "Floating bottom pen toolbar must NOT be detected as ink"

    found_header_ink = any(s.centroid[1] < 120 for s in strokes)
    assert not found_header_ink, "Top header/tabs must NOT be detected as ink"




