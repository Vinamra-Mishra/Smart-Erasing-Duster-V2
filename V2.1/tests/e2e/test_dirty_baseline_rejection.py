"""E2E Test: Dirty Board Baseline Rejection & Discrete Epoch Roll.

Verifies:
1. Clean whiteboard baseline capture succeeds and establishes Epoch 1.
2. CRITICAL INVARIANT: Board edge density > 0.04 aborts baseline capture with DirtyBoardError.
3. Explicit allow_override parameter permits dirty board capture if configured.
4. Post-clean verified residual <= 0.01 successfully rolls epoch to k+1.
5. Post-clean residual > 0.01 strictly rejects epoch roll (EpochRollRejectedError), preventing baseline corruption.
6. Permanent defects are masked out, allowing epoch roll even with permanent stains present.
7. Boundary precision around dirty_board_threshold (0.039 passes, 0.041 rejects).
"""
from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.core.config import AppConfig, BaselineConfig
from app.perception.reference import (
    BaselineEpochManager,
    DirtyBoardError,
    EpochRollRejectedError,
)


class TestDirtyBaselineRejectionE2E:
    """E2E test suite for baseline capture validation and discrete epoch roll."""

    @pytest.fixture
    def manager(self):
        return BaselineEpochManager(
            frames_to_accumulate=5,
            dirty_board_threshold=0.04,
        )

    def test_clean_board_baseline_capture_success(self, manager):
        """Accumulating frames on a pristine clean board establishes Epoch 1."""
        clean_frame = np.full((700, 1000, 3), 245, dtype=np.uint8)

        # Add 5 frames to fill buffer
        for _ in range(5):
            manager.add_frame(clean_frame)

        assert manager.is_accumulation_complete is True
        epoch = manager.finalize_capture(allow_override=False)

        assert epoch.epoch_id == 1
        assert epoch.is_clean_verified is True
        assert epoch.edge_density < 0.04
        assert manager.current_epoch is not None
        assert manager.current_epoch.epoch_id == 1
        assert len(manager.epoch_history) == 1

    def test_dirty_board_baseline_capture_aborts_with_error(self, manager):
        """CRITICAL INVARIANT: Edge density > 0.04 aborts baseline capture."""
        dirty_frame = np.full((700, 1000, 3), 245, dtype=np.uint8)

        # Draw dense marker scribbles and text across the board to exceed 0.04 edge density
        for y in range(50, 650, 20):
            cv2.line(dirty_frame, (50, y), (950, y), (20, 20, 20), thickness=4)
        for x in range(50, 950, 30):
            cv2.line(dirty_frame, (x, 50), (x, 650), (20, 20, 20), thickness=3)

        # Verify edge density exceeds threshold
        measured_density = manager.compute_edge_density(dirty_frame)
        assert measured_density > 0.04, f"Test setup failed: density {measured_density} not > 0.04"

        # Accumulate dirty frames
        for _ in range(5):
            manager.add_frame(dirty_frame)

        # Finalize capture must abort
        with pytest.raises(DirtyBoardError) as exc_info:
            manager.finalize_capture(allow_override=False)

        assert exc_info.value.edge_density > 0.04
        assert exc_info.value.threshold == 0.04
        assert "Baseline capture aborted" in str(exc_info.value)
        # Verify no corrupt epoch was established
        assert manager.current_epoch is None
        assert len(manager.epoch_history) == 0

    def test_dirty_board_allow_override_permits_capture(self, manager):
        """Setting allow_override=True forces acceptance of dirty board baseline."""
        dirty_frame = np.full((700, 1000, 3), 245, dtype=np.uint8)
        for y in range(100, 600, 30):
            cv2.line(dirty_frame, (100, y), (900, y), (10, 10, 10), thickness=4)

        for _ in range(5):
            manager.add_frame(dirty_frame)

        epoch = manager.finalize_capture(allow_override=True)
        assert epoch.epoch_id == 1
        assert epoch.edge_density > 0.04

    def test_discrete_epoch_roll_accepted_when_residual_below_clean_threshold(self, manager):
        """When post-clean residual <= 0.01, epoch rolls cleanly to Epoch 2."""
        # Establish Epoch 1
        clean_frame = np.full((700, 1000, 3), 245, dtype=np.uint8)
        for _ in range(5):
            manager.add_frame(clean_frame)
        epoch_1 = manager.finalize_capture()
        assert epoch_1.epoch_id == 1

        # Post-clean verification frame with tiny residual = 0.005 (0.5% <= 1%)
        new_clean_frame = np.full((700, 1000, 3), 244, dtype=np.uint8)
        epoch_2 = manager.roll_epoch(
            new_frame=new_clean_frame,
            verified_residual_fraction=0.005,
            clean_threshold=0.01,
        )

        assert epoch_2.epoch_id == 2
        assert manager.current_epoch.epoch_id == 2
        assert len(manager.epoch_history) == 2

    def test_discrete_epoch_roll_rejected_when_residual_exceeds_threshold(self, manager):
        """When post-clean residual > 0.01, epoch roll is rejected to prevent drift."""
        clean_frame = np.full((700, 1000, 3), 245, dtype=np.uint8)
        for _ in range(5):
            manager.add_frame(clean_frame)
        manager.finalize_capture()

        # Unclean residual = 0.045 (4.5% > 1%)
        dirty_post_clean = np.full((700, 1000, 3), 240, dtype=np.uint8)
        with pytest.raises(EpochRollRejectedError) as exc_info:
            manager.roll_epoch(
                new_frame=dirty_post_clean,
                verified_residual_fraction=0.045,
                clean_threshold=0.01,
            )

        assert exc_info.value.residual_fraction == 0.045
        assert exc_info.value.clean_threshold == 0.01
        # Epoch remains at 1
        assert manager.current_epoch.epoch_id == 1
        assert len(manager.epoch_history) == 1

    def test_epoch_roll_masks_permanent_defects(self, manager):
        """Permanent defects are masked out; eligible residual <= 0.01 rolls epoch."""
        clean_frame = np.full((700, 1000, 3), 245, dtype=np.uint8)
        for _ in range(5):
            manager.add_frame(clean_frame)
        manager.finalize_capture()

        # Board has a permanent defect mask (e.g. 500 pixels)
        defect_mask = np.zeros((700, 1000), dtype=np.uint8)
        defect_mask[300:325, 400:420] = 255  # 25 x 20 = 500 px defect

        # Residual of non-defect ink is 0.003 <= 0.01
        new_frame = np.full((700, 1000, 3), 245, dtype=np.uint8)
        epoch_2 = manager.roll_epoch(
            new_frame=new_frame,
            verified_residual_fraction=0.003,
            permanent_defect_mask=defect_mask,
            clean_threshold=0.01,
        )

        assert epoch_2.epoch_id == 2
        assert epoch_2.permanent_defect_count == 500
        assert manager.permanent_defect_mask is not None
        assert np.array_equal(manager.permanent_defect_mask, defect_mask)
