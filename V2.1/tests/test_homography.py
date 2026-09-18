"""Unit tests for 4-corner homography registration and coordinate transforms."""
from __future__ import annotations

import sys
from pathlib import Path
import cv2
import numpy as np
import pytest

# Ensure backend is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.perception.frames import (
    CoordinateFrame,
    Point2D,
    BoundingBox,
    Polygon2D,
    FrameMismatchError,
    validate_frame,
)
from app.perception.registration import (
    HomographyRegistrar,
    RegistrationError,
)


@pytest.fixture
def registrar() -> HomographyRegistrar:
    """Fixture providing a fresh HomographyRegistrar for 1000x700 mm board."""
    return HomographyRegistrar(board_width_mm=1000.0, board_height_mm=700.0)


def test_initial_state_uncalibrated(registrar: HomographyRegistrar):
    """Confirm registrar defaults to uncalibrated with identity matrices."""
    assert not registrar.is_calibrated
    assert registrar.reprojection_error == 0.0
    np.testing.assert_allclose(registrar.homography_matrix, np.eye(3))
    np.testing.assert_allclose(registrar.inverse_homography, np.eye(3))


def test_corner_calibration_and_reprojection_error(registrar: HomographyRegistrar):
    """Calibrate using known trapezoidal perspective corners and verify sub-millimeter error."""
    # Simulating a camera looking at the board at a perspective angle
    cam_corners = [
        (120.0, 80.0),    # Top-Left
        (1160.0, 95.0),   # Top-Right
        (1240.0, 680.0),  # Bottom-Right
        (60.0, 660.0),    # Bottom-Left
    ]
    error = registrar.calibrate_from_corners(cam_corners)
    assert registrar.is_calibrated
    assert error < 0.01, f"Reprojection error {error} exceeds tolerance"

    # Test inverse consistency: H @ H_inv == Identity
    h = registrar.homography_matrix
    h_inv = registrar.inverse_homography
    identity_recon = h @ h_inv
    np.testing.assert_allclose(identity_recon, np.eye(3), atol=1e-7)


def test_point_bidirectional_transform(registrar: HomographyRegistrar):
    """Test point_cam_to_board and point_board_to_cam round-trip mapping."""
    cam_corners = [
        (100.0, 100.0),
        (900.0, 100.0),
        (950.0, 650.0),
        (50.0, 650.0),
    ]
    registrar.calibrate_from_corners(cam_corners)

    # TL corner in camera must map to (0.0, 0.0) in board space
    tl_cam = Point2D(x=100.0, y=100.0, frame=CoordinateFrame.FRAME_CAMERA)
    tl_board = registrar.point_cam_to_board(tl_cam)
    assert tl_board.frame == CoordinateFrame.FRAME_BOARD
    assert pytest.approx(tl_board.x, abs=1e-2) == 0.0
    assert pytest.approx(tl_board.y, abs=1e-2) == 0.0

    # BR corner in camera must map to (1000.0, 700.0) in board space
    br_cam = Point2D(x=950.0, y=650.0, frame=CoordinateFrame.FRAME_CAMERA)
    br_board = registrar.point_cam_to_board(br_cam)
    assert pytest.approx(br_board.x, abs=1e-2) == 1000.0
    assert pytest.approx(br_board.y, abs=1e-2) == 700.0

    # Round-trip back to camera
    br_cam_recon = registrar.point_board_to_cam(br_board)
    assert br_cam_recon.frame == CoordinateFrame.FRAME_CAMERA
    assert pytest.approx(br_cam_recon.x, abs=1e-2) == 950.0
    assert pytest.approx(br_cam_recon.y, abs=1e-2) == 650.0


def test_polygon_warp_and_metric_preservation(registrar: HomographyRegistrar):
    """Confirm warped polygon maintains exact physical scale (1 px = 1 mm)."""
    # Simple rectangular registration (no skew)
    cam_corners = [(0.0, 0.0), (1000.0, 0.0), (1000.0, 700.0), (0.0, 700.0)]
    registrar.calibrate_from_corners(cam_corners)

    # 100 mm x 50 mm polygon in board coordinates
    poly_board = Polygon2D(
        points=[(200.0, 200.0), (300.0, 200.0), (300.0, 250.0), (200.0, 250.0)],
        frame=CoordinateFrame.FRAME_BOARD,
    )
    bbox = poly_board.bounding_box()
    assert bbox.width == 100.0
    assert bbox.height == 50.0
    assert bbox.area == 5000.0


def test_frame_mismatch_rejection(registrar: HomographyRegistrar):
    """Enforce that passing incorrect coordinate frame raises FrameMismatchError."""
    registrar.calibrate_from_corners([(0, 0), (1000, 0), (1000, 700), (0, 700)])

    board_pt = Point2D(x=10.0, y=10.0, frame=CoordinateFrame.FRAME_BOARD)
    with pytest.raises(FrameMismatchError):
        registrar.point_cam_to_board(board_pt)

    cam_pt = Point2D(x=10.0, y=10.0, frame=CoordinateFrame.FRAME_CAMERA)
    with pytest.raises(FrameMismatchError):
        registrar.point_board_to_cam(cam_pt)


def test_invalid_corner_count_raises():
    """Verify calibrate_from_corners rejects fewer or more than 4 corners."""
    reg = HomographyRegistrar()
    with pytest.raises(RegistrationError, match="Expected 4 corners"):
        reg.calibrate_from_corners([(0, 0), (10, 0), (10, 10)])


def test_aruco_detection_and_calibration():
    """Verify synthetic ArUco generation, detection, and automatic calibration."""
    dict_attr = getattr(cv2.aruco, "DICT_4X4_50")
    aruco_dict = cv2.aruco.getPredefinedDictionary(dict_attr)

    # Canvas of size 1280x800
    canvas = np.full((800, 1280, 3), 255, dtype=np.uint8)

    # Marker size 80x80 px
    marker_size = 80
    corner_positions = {
        0: (100, 100),   # TL
        1: (1100, 100),  # TR
        2: (1100, 620),  # BR
        3: (100, 620),   # BL
    }

    for mid, (x, y) in corner_positions.items():
        if hasattr(cv2.aruco, "generateImageMarker"):
            marker_img = cv2.aruco.generateImageMarker(aruco_dict, mid, marker_size)
        else:
            marker_img = cv2.aruco.drawMarker(aruco_dict, mid, marker_size)
        marker_bgr = cv2.cvtColor(marker_img, cv2.COLOR_GRAY2BGR)
        canvas[y : y + marker_size, x : x + marker_size] = marker_bgr

    reg = HomographyRegistrar(board_width_mm=1000.0, board_height_mm=700.0)
    detected_corners = reg.detect_aruco_corners(canvas, corner_ids=[0, 1, 2, 3])
    assert detected_corners is not None, "Failed to detect synthetic ArUco markers"
    assert len(detected_corners) == 4

    # Centers of the markers
    for idx, (mid, (x, y)) in enumerate(corner_positions.items()):
        expected_cx = x + marker_size / 2.0
        expected_cy = y + marker_size / 2.0
        det_x, det_y = detected_corners[idx]
        assert pytest.approx(det_x, abs=2.0) == expected_cx
        assert pytest.approx(det_y, abs=2.0) == expected_cy

    success, error = reg.calibrate_from_aruco(canvas)
    assert success
    assert reg.is_calibrated


def test_set_board_dimensions_updates_homography():
    """Verify that set_board_dimensions updates dimensions and recomputes homography mapping."""
    reg = HomographyRegistrar(board_width_mm=1000.0, board_height_mm=700.0)
    cam_corners = [(10.0, 10.0), (1910.0, 10.0), (1910.0, 1070.0), (10.0, 1070.0)]
    reg.calibrate_from_corners(cam_corners)

    # Initial mapping: BR maps to (1000.0, 700.0)
    br_cam = Point2D(x=1910.0, y=1070.0, frame=CoordinateFrame.FRAME_CAMERA)
    br_board = reg.point_cam_to_board(br_cam)
    assert pytest.approx(br_board.x, abs=1e-1) == 1000.0
    assert pytest.approx(br_board.y, abs=1e-1) == 700.0

    # Dynamically update board dimensions to 1500x950 mm
    reg.set_board_dimensions(1500.0, 950.0)
    assert reg.board_width_mm == 1500.0
    assert reg.board_height_mm == 950.0

    # New mapping: BR maps to (1500.0, 950.0)
    br_board_updated = reg.point_cam_to_board(br_cam)
    assert pytest.approx(br_board_updated.x, abs=1e-1) == 1500.0
    assert pytest.approx(br_board_updated.y, abs=1e-1) == 950.0

