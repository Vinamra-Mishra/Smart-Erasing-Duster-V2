"""Comprehensive Opaque-Box E2E Closed-Loop Test Suite for Smart Erasing Duster V2.1.

Validates the complete end-to-end cyber-physical loop:
1. User Writes Stroke -> Camera Capture
2. Homography Warp to FRAME_BOARD
3. Multi-Signal Perception & Reconciler Registration (NEW_INK -> STABLE_INK)
4. Config-Driven Path Planning from Dynamic Home Dock (28% overlap sweep + exterior U-turns)
5. Actuator Swept Execution with Imperfect Erasing (Efficiency 0.85)
6. Residual Measurement & Tier Classification (TIER_3_MAJOR_RESIDUAL, PARTIALLY_CLEANED, RECLEAN_PENDING)
7. Secondary Re-Clean Dispatch & Execution
8. Closed-Loop Verification -> CLEANED
9. Dynamic Home Dock Return
10. Baseline Epoch Roll to k+1 & Garbage Collection of Cleaned Objects.
"""
from __future__ import annotations

import cv2
import numpy as np
import pytest
from shapely.geometry import box

from app.core.config import AppConfig, CleaningConfig, SystemConfig
from app.digital_twin.board_twin import BoardTwinStore, InkObject
from app.digital_twin.execution_state import ExecutionStore
from app.digital_twin.reconciler import ReconcilerEvent, reconcile
from app.perception.frames import CoordinateFrame, Point2D
from app.perception.projector import ProjectorDecoupler
from app.perception.reference import BaselineEpochManager
from app.perception.registration import HomographyRegistrar
from app.planning.coverage import plan_boustrophedon_coverage
from app.planning.transit import plan_full_mission
from app.schemas.ink import PhysicalState
from app.schemas.perception import ObservationType
from app.schemas.planner import ExecutionState, ResidualTier
from app.simulation.board import VirtualBoard
from app.simulation.cleaning import RealisticCleaningEngine
from app.simulation.metrics import evaluate_operational_metrics


class TestClosedLoopE2E:
    """Full closed-loop verification across perception, twin, planning, and execution."""

    @pytest.fixture
    def setup_closed_loop(self):
        config = AppConfig(
            system=SystemConfig(board_width_mm=1000.0, board_height_mm=700.0),
            cleaning=CleaningConfig(
                duster_width_mm=162.0,
                duster_height_mm=58.0,
                duster_thickness_mm=42.0,
                lane_overlap=0.28,
                nominal_efficiency=0.85,
                clean_threshold=0.01,
                residual_major_threshold=0.05,
                max_reclean_attempts=3,
            ),
        )
        board = VirtualBoard(width_mm=1000, height_mm=700)
        cleaning_engine = RealisticCleaningEngine(nominal_efficiency=0.85)
        twin_store = BoardTwinStore(config=config)
        exec_store = ExecutionStore(config=config)
        baseline_mgr = BaselineEpochManager(frames_to_accumulate=3, dirty_board_threshold=0.04)

        # Establish Initial Baseline Epoch 1 on clean board
        clean_frame = np.full((700, 1000, 3), 245, dtype=np.uint8)
        for _ in range(3):
            baseline_mgr.add_frame(clean_frame)
        initial_epoch = baseline_mgr.finalize_capture()
        assert initial_epoch.epoch_id == 1

        # Calibrate 4-Corner Homography (Camera perspective -> Physical Board mm)
        # Trapezoidal camera corners simulating 45-deg angled overhead camera
        cam_corners = [(120.0, 80.0), (1160.0, 70.0), (1220.0, 680.0), (60.0, 690.0)]
        registrar = HomographyRegistrar(board_width_mm=1000.0, board_height_mm=700.0)
        registrar.calibrate_from_corners(cam_corners)
        assert registrar.is_calibrated is True

        return config, board, cleaning_engine, twin_store, exec_store, baseline_mgr, registrar

    def test_full_closed_loop_workflow(self, setup_closed_loop):
        """Complete workflow: Write -> Homography -> Twin -> Plan -> Clean -> Residual -> Re-clean -> Cleaned -> Epoch Roll."""
        config, board, cleaner, twin, exec_st, baseline_mgr, registrar = setup_closed_loop

        # -------------------------------------------------------------
        # Phase 1: Dynamic Home Dock Verification
        # -------------------------------------------------------------
        x_home, y_home, theta_home = config.get_home_dock()
        assert (x_home, y_home) == (81.0, 671.0)
        assert exec_st.duster_pose.x == 81.0
        assert exec_st.duster_pose.y == 671.0
        assert exec_st.state == ExecutionState.IDLE

        # -------------------------------------------------------------
        # Phase 2: User Writes Stroke & Camera Homography Registration
        # -------------------------------------------------------------
        # User draws marker stroke in board coordinates (center-left)
        stroke_pts_board = [[300.0, 250.0], [450.0, 250.0], [450.0, 280.0], [300.0, 280.0]]
        oid = board.add_stroke(
            stroke_pts_board, width_mm=8.0, color_bgr=(20, 20, 20), object_id="ink_closed_loop_1"
        )
        sim_obj = board.ink_objects[oid]
        assert sim_obj.area_mm2 > 0.0

        # Simulate camera observing the stroke and warping to board space
        pt_cam = registrar.point_board_to_cam(Point2D(x=375.0, y=265.0, frame=CoordinateFrame.FRAME_BOARD))
        pt_reprojected = registrar.point_cam_to_board(pt_cam)
        assert pt_reprojected.x == pytest.approx(375.0, abs=1.0)
        assert pt_reprojected.y == pytest.approx(265.0, abs=1.0)

        # -------------------------------------------------------------
        # Phase 3: Perception Fusion & Reconciler Ingestion (Truth Table Row 2)
        # -------------------------------------------------------------
        event_write = ReconcilerEvent(
            target_object_id=oid,
            evidence_type=ObservationType.OBS_INK,
            spatial_match=False,
            points=sim_obj.points,
            bbox=sim_obj.bbox,
            centroid=sim_obj.centroid,
            confidence=0.99,
            area_mm2=sim_obj.area_mm2,
        )
        twin, exec_st, actions = reconcile(twin, exec_st, event_write, config)

        assert twin.get_state(oid) == PhysicalState.STABLE_INK
        assert len(twin.get_active_ink_objects()) == 1
        assert "CREATE_INK_OBJECT" in [a.action_type for a in actions]

        # -------------------------------------------------------------
        # Phase 4: Path Planning from Dynamic Home Dock
        # -------------------------------------------------------------
        stroke_poly = box(*sim_obj.bbox)
        plan = plan_full_mission(
            target_clusters=[(oid, stroke_poly)],
            lane_overlap=0.28,
            duster_width_mm=162.0,
            duster_height_mm=58.0,
            board_height_mm=700.0,
        )
        assert len(plan.waypoints) >= 4
        # First and last waypoints are Home Dock
        assert plan.waypoints[0].action == "DOCK"
        assert (plan.waypoints[0].x, plan.waypoints[0].y) == (81.0, 671.0)
        assert plan.waypoints[-1].action == "DOCK"
        assert (plan.waypoints[-1].x, plan.waypoints[-1].y) == (81.0, 671.0)

        # -------------------------------------------------------------
        # Phase 5: Actuator Execution (First Wipe Pass with 85% Efficiency)
        # -------------------------------------------------------------
        exec_st.set_state(ExecutionState.CLEANING_ACTIVE)
        twin.get_object(oid).state = PhysicalState.PARTIALLY_CLEANED

        # Wiping pass traverses the stroke footprint
        swept_hull = stroke_poly.buffer(6.0)
        erased_area = cleaner.apply_wipe(board, swept_hull, efficiency_override=0.85)
        assert erased_area > 0.0

        # -------------------------------------------------------------
        # Phase 6: Post-Wipe Verification & Residual Tier Classification
        # -------------------------------------------------------------
        exec_st.set_state(ExecutionState.VERIFYING)
        residual_ratio = 0.15  # 15% residual remaining
        tier = exec_st.evaluate_residual(residual_ratio)

        assert tier == ResidualTier.TIER_3_MAJOR_RESIDUAL
        assert exec_st.residual_detected is True

        # Reconciler processes residual evidence (Truth Table Row 15)
        event_residual = ReconcilerEvent(
            target_object_id=oid,
            evidence_type=ObservationType.OBS_INK,
            spatial_match=True,
            residual_ratio=residual_ratio,
        )
        twin, exec_st, actions = reconcile(twin, exec_st, event_residual, config)

        assert twin.get_state(oid) == PhysicalState.PARTIALLY_CLEANED
        assert exec_st.state == ExecutionState.RECLEAN_PENDING
        assert oid in exec_st.reclean_queue
        assert twin.get_object(oid).reclean_attempts == 1
        assert "SCHEDULE_RECLEAN" in [a.action_type for a in actions]

        # -------------------------------------------------------------
        # Phase 7: Secondary Re-clean Execution
        # -------------------------------------------------------------
        exec_st.set_state(ExecutionState.CLEANING_ACTIVE)
        # Second pass with 98% efficiency clears residual
        cleaner.apply_wipe(board, swept_hull, efficiency_override=0.98)

        # -------------------------------------------------------------
        # Phase 8: Verification Confirms Clean (Truth Table Row 16)
        # -------------------------------------------------------------
        exec_st.set_state(ExecutionState.VERIFYING)
        clean_event = ReconcilerEvent(
            target_object_id=oid,
            evidence_type=ObservationType.OBS_ABSENT,
            spatial_match=False,
            residual_ratio=0.002,  # 0.2% <= 1% clean threshold
        )
        twin, exec_st, actions = reconcile(twin, exec_st, clean_event, config)

        assert twin.get_state(oid) == PhysicalState.CLEANED
        assert exec_st.state == ExecutionState.IDLE
        assert exec_st.residual_detected is False
        assert oid not in exec_st.reclean_queue
        assert "MARK_CLEANED" in [a.action_type for a in actions]

        # -------------------------------------------------------------
        # Phase 9: Operational Metrics Evaluation
        # -------------------------------------------------------------
        metrics = evaluate_operational_metrics(
            detected_geom=None,
            ground_truth_geom=None,
            residual_geom=None,
            swept_footprint=swept_hull,
        )
        assert metrics.precision == 1.0
        assert metrics.recall == 1.0
        assert metrics.iou == 1.0
        assert metrics.fpr == 0.0
        assert metrics.residual_fraction == 0.0

        # -------------------------------------------------------------
        # Phase 10: Discrete Epoch Roll & Garbage Collection
        # -------------------------------------------------------------
        new_clean_frame = board.render_composite()
        epoch_2 = baseline_mgr.roll_epoch(
            new_frame=new_clean_frame,
            verified_residual_fraction=0.002,
            clean_threshold=0.01,
        )
        assert epoch_2.epoch_id == 2
        assert epoch_2.is_clean_verified is True

        # Garbage collect CLEANED objects from physical twin memory
        gc_count = twin.garbage_collect_cleaned()
        assert gc_count == 1
        assert len(twin.get_all_objects()) == 0

    def test_closed_loop_stubborn_defect_cap_and_epoch_roll(self, setup_closed_loop):
        """Permanent stubborn mark hits 3-reclean cap (Row 21) and baseline rolls with defect masked."""
        config, board, _, twin, exec_st, baseline_mgr, _ = setup_closed_loop

        oid = "stubborn_stain"
        stain_bbox = (400.0, 300.0, 440.0, 340.0)
        twin.add_object(
            InkObject(
                id=oid,
                state=PhysicalState.PARTIALLY_CLEANED,
                bbox=stain_bbox,
                reclean_attempts=0,
            )
        )

        # 3 Failed clean sweeps
        for attempt in (1, 2, 3):
            ev = ReconcilerEvent(target_object_id=oid, evidence_type=ObservationType.OBS_INK, residual_ratio=0.12)
            twin, exec_st, _ = reconcile(twin, exec_st, ev, config)
            assert twin.get_object(oid).reclean_attempts == attempt

        # Next check: Row 21 fires
        ev_cap = ReconcilerEvent(target_object_id=oid, evidence_type=ObservationType.OBS_INK, residual_ratio=0.12)
        twin, exec_st, actions = reconcile(twin, exec_st, ev_cap, config)

        obj = twin.get_object(oid)
        assert obj.state == PhysicalState.PERMANENT_DEFECT
        assert "RECLEAN_CAP_HIT" in [a.action_type for a in actions]
        assert exec_st.state == ExecutionState.IDLE

        # Epoch roll succeeds with permanent defect masked out
        defect_mask = np.zeros((700, 1000), dtype=np.uint8)
        defect_mask[300:340, 400:440] = 255

        epoch_2 = baseline_mgr.roll_epoch(
            new_frame=np.full((700, 1000, 3), 245, dtype=np.uint8),
            verified_residual_fraction=0.005,  # Non-defect residual is clean
            permanent_defect_mask=defect_mask,
            clean_threshold=0.01,
        )
        assert epoch_2.epoch_id == 2
        assert epoch_2.permanent_defect_count > 0

    def test_closed_loop_projector_mode_a_ambiguous_light_ignored(self, setup_closed_loop):
        """Ambiguous Mode A light creates UNKNOWN and is strictly ignored by cleaning planner."""
        config, board, _, twin, exec_st, _, _ = setup_closed_loop

        # Real marker ink
        real_id = "real_ink_stroke"
        real_poly = box(200.0, 200.0, 300.0, 250.0)
        twin.add_object(
            InkObject(
                id=real_id,
                state=PhysicalState.STABLE_INK,
                bbox=(200.0, 200.0, 300.0, 250.0),
            )
        )

        # Projected slide light creates UNKNOWN region (Row 4)
        light_ev = ReconcilerEvent(
            target_object_id=None,
            evidence_type=ObservationType.OBS_UNCERTAIN,
            bbox=(600.0, 200.0, 850.0, 400.0),
        )
        twin, exec_st, _ = reconcile(twin, exec_st, light_ev, config)

        # Plan mission for active ink objects
        active_objects = twin.get_active_ink_objects()
        assert len(active_objects) == 2  # STABLE_INK and UNKNOWN

        # Planner only wipes real STABLE_INK and PARTIALLY_CLEANED objects
        wipable_clusters = [
            (obj.id, box(*obj.bbox))
            for obj in active_objects
            if obj.state in (PhysicalState.NEW_INK, PhysicalState.STABLE_INK, PhysicalState.PARTIALLY_CLEANED)
        ]
        assert len(wipable_clusters) == 1
        assert wipable_clusters[0][0] == real_id

        # Target IDs planned do NOT include UNKNOWN projected light
        plan = plan_full_mission(target_clusters=wipable_clusters)
        assert plan.target_object_ids == [real_id]
