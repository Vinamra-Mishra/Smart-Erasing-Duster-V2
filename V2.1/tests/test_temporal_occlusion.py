"""Unit tests for multi-signal temporal occlusion detection without MOG2."""
from __future__ import annotations

import sys
from pathlib import Path
import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.perception.frames import CoordinateFrame, Polygon2D
from app.perception.occlusion import TemporalOcclusionDetector


@pytest.fixture
def detector() -> TemporalOcclusionDetector:
    """1000x700 board occlusion detector requiring >= 4.5% area and 3 frames persistence."""
    return TemporalOcclusionDetector(
        board_width_mm=1000.0,
        board_height_mm=700.0,
        min_area_fraction=0.045,  # 31,500 mm^2
        min_displacement_px=12.0,
        confirmation_frames=3,
    )


def test_banned_mog2_is_not_imported_or_referenced():
    """Enforce strict architectural invariant: cv2 MOG2 is completely banned."""
    import app.perception.occlusion as occ_module

    # Check module source code directly
    with open(occ_module.__file__, "r", encoding="utf-8") as f:
        source_code = f.read()

    assert "createBackgroundSubtractorMOG2" not in source_code
    assert "BackgroundSubtractorMOG2" not in source_code
    assert "MOG2" not in source_code or "NO MOG2" in source_code or "BANNED" in source_code


def test_stationary_frame_does_not_trigger_occlusion(detector: TemporalOcclusionDetector):
    """Zero motion between frames produces zero optical flow and no occlusion."""
    frame = np.full((700, 1000, 3), 240, dtype=np.uint8)
    is_occ, mask, polys = detector.evaluate_frame(frame, frame)

    assert not is_occ
    assert not np.any(mask)
    assert len(polys) == 0


def test_small_or_insufficient_motion_rejected(detector: TemporalOcclusionDetector):
    """Small movement (< 12 px displacement) does not meet motion threshold."""
    frame1 = np.full((700, 1000, 3), 240, dtype=np.uint8)
    frame2 = frame1.copy()

    # Move a small patch by 5 pixels (below min_displacement_px = 12)
    cv2.circle(frame1, (300, 300), 40, (50, 50, 50), thickness=-1)
    cv2.circle(frame2, (305, 300), 40, (50, 50, 50), thickness=-1)

    is_occ, mask, _ = detector.evaluate_frame(frame2, frame1)
    assert not is_occ
    assert not np.any(mask)


def test_small_area_blob_rejected(detector: TemporalOcclusionDetector):
    """Fast motion with small spatial footprint (< 31,500 mm^2) is rejected."""
    frame1 = np.full((700, 1000, 3), 240, dtype=np.uint8)
    frame2 = frame1.copy()

    # Small blob of 50x50 = 2,500 mm^2 (well below 31,500 mm^2 threshold) moving 25 px
    cv2.rectangle(frame1, (200, 200), (250, 250), (40, 40, 40), thickness=-1)
    cv2.rectangle(frame2, (225, 200), (275, 250), (40, 40, 40), thickness=-1)

    is_occ, mask, _ = detector.evaluate_frame(frame2, frame1)
    assert not is_occ


def test_multi_signal_occlusion_confirmed_after_3_frames(detector: TemporalOcclusionDetector):
    """Large moving body (200x200 = 40,000 mm^2) confirmed as occlusion after 3 persistent frames."""
    base_frame = np.full((700, 1000, 3), 240, dtype=np.uint8)

    # Realistic presenter body with clothing texture (220x220 = 48,400 mm^2)
    rng = np.random.RandomState(42)
    clothing_texture = rng.randint(40, 120, (220, 220, 3), dtype=np.uint8)

    # Sequence of frames where presenter body moves across by 18 px (>= 12 px)
    frames = []
    for step in range(4):
        f = base_frame.copy()
        x_offset = 350 + step * 18
        f[150:370, x_offset : x_offset + 220] = clothing_texture
        frames.append(f)

    # Frame 1: History length 1 -> not yet persistent across 3 frames
    is_occ1, _, _ = detector.evaluate_frame(frames[1], frames[0])
    assert not is_occ1

    # Frame 2: History length 2 -> still buffering
    is_occ2, _, _ = detector.evaluate_frame(frames[2], frames[1])
    assert not is_occ2

    # Frame 3: History length 3 -> persistence confirmed!
    is_occ3, mask3, polys3 = detector.evaluate_frame(frames[3], frames[2])
    assert is_occ3
    assert np.any(mask3)
    assert len(polys3) >= 1


def test_occluded_twin_ink_is_preserved_without_deletion(detector: TemporalOcclusionDetector):
    """When occlusion overlaps existing twin ink, the ink is tagged occluded but NOT deleted."""
    h, w = 700, 1000
    occlusion_mask = np.zeros((h, w), dtype=bool)
    # Occluder at (400..600, 200..400)
    occlusion_mask[200:400, 400:600] = True

    # Twin ink object located at (450, 250)
    poly_occluded = Polygon2D(
        points=[(430.0, 230.0), (470.0, 230.0), (470.0, 270.0), (430.0, 270.0)],
        frame=CoordinateFrame.FRAME_BOARD,
    )
    # Twin ink object located elsewhere at (800, 500)
    poly_visible = Polygon2D(
        points=[(780.0, 480.0), (820.0, 480.0), (820.0, 520.0), (780.0, 520.0)],
        frame=CoordinateFrame.FRAME_BOARD,
    )

    reconciled = detector.reconcile_ink_preservation(
        twin_ink_polygons=[poly_occluded, poly_visible],
        occlusion_mask=occlusion_mask,
    )

    assert len(reconciled) == 2
    # First poly is occluded
    assert reconciled[0][0] == poly_occluded
    assert reconciled[0][1] is True

    # Second poly is visible
    assert reconciled[1][0] == poly_visible
    assert reconciled[1][1] is False
