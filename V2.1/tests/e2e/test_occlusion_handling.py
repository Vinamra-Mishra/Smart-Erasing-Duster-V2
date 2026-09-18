"""E2E Test: Occlusion Handling & Physical Twin Ink State Retention.

Verifies:
1. Human hand/arm occluding ink transitions Twin state from STABLE_INK to OCCLUDED (Truth Table Row 10).
2. CRITICAL INVARIANT: Occluded ink is NEVER deleted or erased from BoardTwinStore;
   geometry, confidence, and ID are fully preserved.
3. Hand departure restores physical ink to STABLE_INK (Truth Table Row 13).
4. Occlusion over clean whiteboard updates occlusion mask without generating phantom ink (Row 3).
5. Continuous occlusion persistence across consecutive frames (Row 12).
6. Suspected manual erasure while occluded transitions to UNKNOWN (Row 14).
7. Non-MOG2 Temporal Occlusion Detector behaves deterministically on area and frame limits.
"""
from __future__ import annotations

import cv2
import numpy as np
import pytest
from shapely.geometry import Polygon, box

from app.core.config import AppConfig
from app.digital_twin.board_twin import BoardTwinStore, InkObject
from app.digital_twin.execution_state import ExecutionStore
from app.digital_twin.reconciler import ReconcilerEvent, reconcile
from app.perception.frames import CoordinateFrame, Polygon2D
from app.perception.occlusion import TemporalOcclusionDetector
from app.schemas.ink import PhysicalState
from app.schemas.perception import ObservationType
from app.schemas.planner import ExecutionState


class TestOcclusionHandlingE2E:
    """E2E verification of occlusion detection and digital twin state invariants."""

    @pytest.fixture
    def setup_stores(self):
        config = AppConfig()
        twin_store = BoardTwinStore(config=config)
        exec_store = ExecutionStore(config=config)
        return config, twin_store, exec_store

    def test_occlusion_preserves_ink_object_in_twin(self, setup_stores):
        """CRITICAL INVARIANT: Occluding hand transitions ink to OCCLUDED without deletion."""
        config, twin, exec_st = setup_stores

        # Step 1: Initial confirmed STABLE_INK on whiteboard
        ink_id = "target_stroke_42"
        ink_poly = [[300.0, 200.0], [450.0, 200.0], [450.0, 250.0], [300.0, 250.0]]
        initial_obj = InkObject(
            id=ink_id,
            state=PhysicalState.STABLE_INK,
            frame_id=CoordinateFrame.FRAME_BOARD,
            points=ink_poly,
            bbox=(300.0, 200.0, 450.0, 250.0),
            centroid=(375.0, 225.0),
            confidence=0.98,
            area_mm2=7500.0,
            is_occluded=False,
        )
        twin.add_object(initial_obj)
        assert twin.get_state(ink_id) == PhysicalState.STABLE_INK

        # Step 2: Presenter's hand/arm occludes the stroke
        occlusion_event = ReconcilerEvent(
            target_object_id=ink_id,
            evidence_type=ObservationType.OBS_OCCLUDED,
            spatial_match=True,
            points=ink_poly,
            bbox=(300.0, 200.0, 450.0, 250.0),
            centroid=(375.0, 225.0),
        )

        next_twin, next_exec, actions = reconcile(twin, exec_st, occlusion_event, config)

        # Step 3: Verify Twin State Invariants
        # Object MUST NOT be deleted
        occluded_obj = next_twin.get_object(ink_id)
        assert occluded_obj is not None, "Ink object was deleted during occlusion!"
        assert occluded_obj.state == PhysicalState.OCCLUDED
        assert occluded_obj.is_occluded is True
        # Geometry and attributes preserved exactly
        assert occluded_obj.bbox == (300.0, 200.0, 450.0, 250.0)
        assert occluded_obj.centroid == (375.0, 225.0)
        assert occluded_obj.confidence == pytest.approx(0.98, abs=1e-3)
        assert occluded_obj.area_mm2 == pytest.approx(7500.0, abs=1e-3)

        # Action emitted
        action_types = [a.action_type for a in actions]
        assert "INK_OCCLUDED" in action_types

    def test_occlusion_departure_restores_stable_ink(self, setup_stores):
        """Actor vacating restores ink from OCCLUDED to STABLE_INK (Truth Table Row 13)."""
        config, twin, exec_st = setup_stores

        ink_id = "target_stroke_99"
        occluded_obj = InkObject(
            id=ink_id,
            state=PhysicalState.OCCLUDED,
            frame_id=CoordinateFrame.FRAME_BOARD,
            points=[[400.0, 300.0], [500.0, 300.0], [500.0, 340.0], [400.0, 340.0]],
            bbox=(400.0, 300.0, 500.0, 340.0),
            centroid=(450.0, 320.0),
            confidence=0.95,
            area_mm2=4000.0,
            is_occluded=True,
        )
        twin.add_object(occluded_obj)

        # Actor departs, camera re-acquires optical ink stroke
        restore_event = ReconcilerEvent(
            target_object_id=ink_id,
            evidence_type=ObservationType.OBS_INK,
            spatial_match=True,
            points=occluded_obj.points,
            bbox=occluded_obj.bbox,
            centroid=occluded_obj.centroid,
            confidence=0.97,
        )

        next_twin, next_exec, actions = reconcile(twin, exec_st, restore_event, config)

        restored_obj = next_twin.get_object(ink_id)
        assert restored_obj is not None
        assert restored_obj.state == PhysicalState.STABLE_INK
        assert restored_obj.is_occluded is False

        action_types = [a.action_type for a in actions]
        assert "RESTORE_INK" in action_types

    def test_occlusion_over_clean_board_creates_no_phantom_ink(self, setup_stores):
        """Human body entering empty board area updates mask but creates NO ink (Row 3)."""
        config, twin, exec_st = setup_stores

        assert len(twin.get_all_objects()) == 0

        # Occlusion detected over pristine area
        event = ReconcilerEvent(
            target_object_id=None,
            evidence_type=ObservationType.OBS_OCCLUDED,
            spatial_match=False,
            bbox=(100.0, 100.0, 400.0, 500.0),
        )

        next_twin, next_exec, actions = reconcile(twin, exec_st, event, config)

        # Invariant: Zero ink objects created
        assert len(next_twin.get_all_objects()) == 0
        assert len(next_twin.get_active_ink_objects()) == 0
        # Occlusion mask updated
        assert np.any(next_twin.board_occlusion_mask > 0)
        action_types = [a.action_type for a in actions]
        assert "UPDATE_OCCLUSION_MASK" in action_types

    def test_continuous_occlusion_persistence(self, setup_stores):
        """While actor remains over stroke, OCCLUDED state persists without mutation (Row 12)."""
        config, twin, exec_st = setup_stores

        ink_id = "persistent_ink"
        twin.add_object(
            InkObject(
                id=ink_id,
                state=PhysicalState.OCCLUDED,
                is_occluded=True,
                bbox=(200.0, 200.0, 300.0, 250.0),
            )
        )

        event = ReconcilerEvent(
            target_object_id=ink_id,
            evidence_type=ObservationType.OBS_OCCLUDED,
            spatial_match=True,
        )

        next_twin, next_exec, actions = reconcile(twin, exec_st, event, config)
        obj = next_twin.get_object(ink_id)
        assert obj.state == PhysicalState.OCCLUDED
        assert obj.is_occluded is True
        assert len(actions) == 0

    def test_external_erasure_while_occluded_transitions_to_unknown(self, setup_stores):
        """Hand moves away revealing erased board -> EXTERNAL_ERASURE_SUSPECTED (Row 14)."""
        config, twin, exec_st = setup_stores

        ink_id = "manually_erased_ink"
        twin.add_object(
            InkObject(
                id=ink_id,
                state=PhysicalState.OCCLUDED,
                is_occluded=True,
            )
        )

        # Hand leaves, but board is now pristine white (OBS_ABSENT)
        vanish_event = ReconcilerEvent(
            target_object_id=ink_id,
            evidence_type=ObservationType.OBS_ABSENT,
            spatial_match=False,
        )

        next_twin, next_exec, actions = reconcile(twin, exec_st, vanish_event, config)
        obj = next_twin.get_object(ink_id)
        assert obj.state == PhysicalState.UNKNOWN
        assert obj.is_occluded is False

        action_types = [a.action_type for a in actions]
        assert "EXTERNAL_ERASURE_SUSPECTED" in action_types

    def test_temporal_occlusion_detector_area_fraction_boundary(self):
        """Detector respects min_area_fraction=0.045 threshold (4.5% board area)."""
        bw, bh = 1000, 700
        detector = TemporalOcclusionDetector(
            board_width_mm=bw,
            board_height_mm=bh,
            min_area_fraction=0.045,
            min_displacement_px=12.0,
            confirmation_frames=1,
        )

        # Total board area = 700,000 mm^2. 4.5% = 31,500 mm^2
        # Blob A: Sub-threshold area = 20,000 mm^2 (e.g. 100x200 mm)
        sub_thresh_mag = np.zeros((bh, bw), dtype=np.float32)
        sub_thresh_mag[100:300, 100:200] = 25.0  # magnitude > 12 px
        dummy_gray = np.zeros((bh, bw), dtype=np.uint8)
        mask_sub, cnts_sub = detector.detect_large_motion_blobs(sub_thresh_mag, dummy_gray, dummy_gray)
        assert not np.any(mask_sub), "Sub-threshold motion triggered occlusion!"
        assert len(cnts_sub) == 0

        # Blob B: Above-threshold area = 40,000 mm^2 (e.g. 200x200 mm > 31,500 mm^2)
        above_thresh_mag = np.zeros((bh, bw), dtype=np.float32)
        above_thresh_mag[100:300, 100:300] = 25.0
        mask_above, cnts_above = detector.detect_large_motion_blobs(above_thresh_mag, dummy_gray, dummy_gray)
        assert np.any(mask_above), "Above-threshold motion failed to trigger occlusion!"
        assert len(cnts_above) >= 1

    def test_temporal_occlusion_detector_confirmation_frames_requirement(self):
        """Requires confirmation_frames=3 consecutive frames before declaring confirmed occlusion."""
        bw, bh = 1000, 700
        detector = TemporalOcclusionDetector(
            board_width_mm=bw,
            board_height_mm=bh,
            min_area_fraction=0.045,
            min_displacement_px=2.0,
            confirmation_frames=3,
        )

        np.random.seed(42)
        # Background board with rich visual texture across full dynamic range
        f0 = np.random.randint(0, 255, (bh, bw), dtype=np.uint8)
        f1 = np.roll(f0, 15, axis=0)
        f2 = np.roll(f1, 15, axis=0)
        f3 = np.roll(f2, 15, axis=0)

        # Frame 1: Candidate added, but confirmation buffer not full (len=1 < 3)
        is_occ_1, mask_1, _ = detector.evaluate_frame(f1, f0)
        assert is_occ_1 is False

        # Frame 2: (len=2 < 3)
        is_occ_2, mask_2, _ = detector.evaluate_frame(f2, f1)
        assert is_occ_2 is False

        # Frame 3: Buffer full (len=3 >= 3) and persistent motion confirmed
        is_occ_3, mask_3, _ = detector.evaluate_frame(f3, f2)
        assert is_occ_3 is True
        assert np.any(mask_3)
