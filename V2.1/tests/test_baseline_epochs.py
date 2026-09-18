"""Unit tests for baseline reference epoch management, validation, and rolling."""
from __future__ import annotations

import sys
from pathlib import Path
import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.perception.reference import (
    BaselineEpochManager,
    BaselineEpoch,
    DirtyBoardError,
    EpochRollRejectedError,
)


@pytest.fixture
def manager() -> BaselineEpochManager:
    """Fresh BaselineEpochManager requiring 20 frames and dirty threshold 0.04."""
    return BaselineEpochManager(
        frames_to_accumulate=20,
        dirty_board_threshold=0.04,
    )


def test_frame_accumulation_buffer(manager: BaselineEpochManager):
    """Test frame buffer accumulation reaches complete state after 20 frames."""
    blank_frame = np.full((700, 1000, 3), 245, dtype=np.uint8)

    for i in range(19):
        is_full = manager.add_frame(blank_frame)
        assert not is_full
        assert manager.buffer_count == i + 1
        assert not manager.is_accumulation_complete

    is_full = manager.add_frame(blank_frame)
    assert is_full
    assert manager.buffer_count == 20
    assert manager.is_accumulation_complete


def test_clean_board_capture_succeeds(manager: BaselineEpochManager):
    """Clean board with low edge density passes validation and creates Epoch 1."""
    clean_frame = np.full((700, 1000, 3), 245, dtype=np.uint8)
    for _ in range(20):
        manager.add_frame(clean_frame)

    epoch = manager.finalize_capture()
    assert epoch.epoch_id == 1
    assert epoch.is_clean_verified
    assert epoch.edge_density < 0.01
    assert manager.current_baseline is not None
    assert manager.current_epoch == epoch
    assert len(manager.epoch_history) == 1


def test_dirty_board_capture_aborts_with_error(manager: BaselineEpochManager):
    """Board with dense marker writing (edge density > 0.04) aborts capture."""
    dirty_frame = np.full((700, 1000, 3), 245, dtype=np.uint8)

    # Draw dense grid of marker equations/lines to exceed 4% edge density
    for y in range(50, 650, 20):
        cv2.line(dirty_frame, (50, y), (950, y), (10, 10, 10), thickness=3)
    for x in range(50, 950, 20):
        cv2.line(dirty_frame, (x, 50), (x, 650), (10, 10, 10), thickness=3)

    density = manager.compute_edge_density(dirty_frame)
    assert density > 0.04, f"Synthetic dirty board density {density} should exceed 0.04"

    for _ in range(20):
        manager.add_frame(dirty_frame)

    with pytest.raises(DirtyBoardError) as exc_info:
        manager.finalize_capture()

    assert exc_info.value.edge_density > 0.04
    assert exc_info.value.threshold == 0.04
    # Buffer should be cleared after abort
    assert manager.buffer_count == 0
    assert manager.current_baseline is None


def test_dirty_board_override_allowed_when_explicit(manager: BaselineEpochManager):
    """Maintenance operator override forces acceptance despite dirty markings."""
    dirty_frame = np.full((700, 1000, 3), 245, dtype=np.uint8)
    cv2.circle(dirty_frame, (500, 350), 200, (10, 10, 10), thickness=50)

    for _ in range(20):
        manager.add_frame(dirty_frame)

    epoch = manager.finalize_capture(allow_override=True)
    assert epoch.epoch_id == 1
    assert manager.current_baseline is not None


def test_roll_epoch_succeeds_within_clean_threshold(manager: BaselineEpochManager):
    """Verified cleaning pass with residual <= 1% successfully rolls new epoch."""
    clean_frame = np.full((700, 1000, 3), 245, dtype=np.uint8)
    for _ in range(20):
        manager.add_frame(clean_frame)
    epoch1 = manager.finalize_capture()

    # After cleaning pass, verified residual is 0.4% (<= 1.0%)
    epoch2 = manager.roll_epoch(
        new_frame=clean_frame,
        verified_residual_fraction=0.004,
        clean_threshold=0.01,
    )

    assert epoch2.epoch_id == 2
    assert epoch2.is_clean_verified
    assert len(manager.epoch_history) == 2


def test_roll_epoch_fails_when_residual_exceeds_threshold(manager: BaselineEpochManager):
    """Attempting to roll epoch when post-clean residual is 3% (> 1%) is rejected."""
    clean_frame = np.full((700, 1000, 3), 245, dtype=np.uint8)
    for _ in range(20):
        manager.add_frame(clean_frame)
    manager.finalize_capture()

    # Uncleaned residual is 3.5% (> 1%)
    with pytest.raises(EpochRollRejectedError) as exc_info:
        manager.roll_epoch(
            new_frame=clean_frame,
            verified_residual_fraction=0.035,
            clean_threshold=0.01,
        )

    assert exc_info.value.residual_fraction == 0.035
    assert exc_info.value.clean_threshold == 0.01


def test_roll_epoch_masks_permanent_defects(manager: BaselineEpochManager):
    """Stubborn permanent defects masked out allow clean epoch roll."""
    clean_frame = np.full((700, 1000, 3), 245, dtype=np.uint8)
    for _ in range(20):
        manager.add_frame(clean_frame)
    manager.finalize_capture()

    # Permanent defect mask (known physical scratch/stain on board)
    defect_mask = np.zeros((700, 1000), dtype=bool)
    defect_mask[100:150, 100:150] = True

    # When permanent defects are masked out, the remaining active residual is 0.002 <= 0.01
    epoch2 = manager.roll_epoch(
        new_frame=clean_frame,
        verified_residual_fraction=0.002,
        permanent_defect_mask=defect_mask,
        clean_threshold=0.01,
    )

    assert epoch2.epoch_id == 2
    assert epoch2.permanent_defect_count == 2500  # 50x50 defect pixels


def test_spatial_section_grid_initialization():
    """Verify board surface partitions into regular spatial sections."""
    from app.perception.reference import SpatialSectionGrid
    grid = SpatialSectionGrid(board_width_mm=1000.0, board_height_mm=700.0, section_size_mm=50.0)
    assert grid.cols == 20
    assert grid.rows == 14
    assert len(grid.sections) == 280

    # Section (0, 0) covers (0, 0, 50, 50)
    s00 = grid.sections[(0, 0)]
    assert s00.bbox_mm == (0.0, 0.0, 50.0, 50.0)
    assert not s00.is_confirmed_clean

    # Intersecting bounding box (30, 30, 80, 80) should touch (0,0), (1,0), (0,1), (1,1)
    matched = grid.get_sections_in_bbox((30.0, 30.0, 80.0, 80.0))
    coords = {(s.col, s.row) for s in matched}
    assert (0, 0) in coords and (1, 0) in coords and (0, 1) in coords and (1, 1) in coords


def test_section_baseline_refresh_enforces_98_point_9_percent_confidence(manager: BaselineEpochManager):
    """Verify section baseline is updated only when cleaned with >= 98.9% confidence."""
    base_frame = np.full((700, 1000, 3), 240, dtype=np.uint8)
    for _ in range(20):
        manager.add_frame(base_frame)
    manager.finalize_capture()

    # Case A: High-confidence clean (0.5% residual -> 99.5% clean >= 98.9%)
    curr_frame = np.full((700, 1000, 3), 245, dtype=np.uint8)
    # Tiny residual: 5 pixels in 50x50 section (2500 px) -> 0.2% residual, 99.8% confidence
    residual_mask = np.zeros((700, 1000), dtype=np.uint8)
    residual_mask[10:15, 10:11] = 255

    refreshed = manager.update_section_baseline_if_clean(
        current_frame=curr_frame,
        active_bbox_mm=(0.0, 0.0, 50.0, 50.0),
        residual_mask=residual_mask,
        confidence_threshold=0.989,
    )

    assert len(refreshed) == 1
    sec = refreshed[0]
    assert sec.col == 0 and sec.row == 0
    assert sec.is_confirmed_clean
    assert sec.clean_confidence >= 0.989
    assert sec.refresh_count == 1
    # Baseline in that section should now reflect curr_frame (245)
    assert manager.current_baseline[25, 25, 0] == 245

    # Case B: Low-confidence residual (5.0% residual -> 95.0% clean < 98.9%)
    dirty_mask = np.zeros((700, 1000), dtype=np.uint8)
    dirty_mask[50:100, 50:70] = 255  # 1000 pixels out of 2500 in section (1, 1)
    refreshed_unclean = manager.update_section_baseline_if_clean(
        current_frame=curr_frame,
        active_bbox_mm=(50.0, 50.0, 100.0, 100.0),
        residual_mask=dirty_mask,
        confidence_threshold=0.989,
    )
    assert len(refreshed_unclean) == 0, "Section with residual > 1.1% must NOT be refreshed"

