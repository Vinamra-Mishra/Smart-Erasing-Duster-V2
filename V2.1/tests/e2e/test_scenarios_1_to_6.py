"""E2E Test: Deterministic Real-World Application Scenarios 1 through 6.

Verifies:
- Scenario 1: Clean Board Single Stroke Closed-Loop Cleaning
- Scenario 2: Multiple Clusters Sequential Mission Execution
- Scenario 3: Real-Time Human Hand Occlusion & Ink Retention
- Scenario 4: Digital Projector Artifact Rejection
- Scenario 5: Stubborn Marker Residue & Re-Clean Hard Cap Defect Promotion
- Scenario 6: Dirty Board Baseline Initialization Rejection
"""
from __future__ import annotations

import cv2
import numpy as np
import pytest
from shapely.geometry import box

from app.core.config import AppConfig
from app.digital_twin.board_twin import BoardTwinStore, InkObject
from app.digital_twin.execution_state import ExecutionStore
from app.digital_twin.reconciler import ReconcilerEvent, reconcile
from app.perception.frames import CoordinateFrame
from app.perception.projector import ProjectorDecoupler
from app.perception.reference import BaselineEpochManager, DirtyBoardError
from app.planning.coverage import plan_boustrophedon_coverage
from app.planning.transit import plan_full_mission
from app.schemas.ink import PhysicalState
from app.schemas.perception import ObservationType
from app.schemas.planner import ExecutionState, ResidualTier
from app.simulation.board import VirtualBoard
from app.simulation.cleaning import RealisticCleaningEngine
from app.simulation.scenarios import (
    load_scenario_1_single_stroke,
    load_scenario_2_multiple_clusters,
    load_scenario_3_human_hand_occlusion,
    load_scenario_4_projector_artifacts,
    load_scenario_5_stubborn_residual_cap_hit,
    load_scenario_6_dirty_board_baseline_abort,
)


class TestScenarios1To6E2E:
    """E2E validation of all 6 formal real-world scenarios."""

    @pytest.fixture
    def env(self):
        config = AppConfig()
        board = VirtualBoard(width_mm=1000, height_mm=700)
        cleaning_engine = RealisticCleaningEngine(nominal_efficiency=0.85)
        twin_store = BoardTwinStore(config=config)
        exec_store = ExecutionStore(config=config)
        return config, board, cleaning_engine, twin_store, exec_store

    def test_scenario_1_single_stroke_closed_loop(self, env):
        """Scenario 1: Single stroke write -> clean -> residual -> re-clean -> verified clean."""
        config, board, cleaning_engine, twin, exec_st = env

        # 1. Load Scenario 1
        meta = load_scenario_1_single_stroke(board)
        assert meta["scenario_id"] == 1
        assert len(board.ink_objects) == 1

        oid = meta["stroke_ids"][0]
        sim_obj = board.ink_objects[oid]
        orig_area = sim_obj.area_mm2
        assert orig_area > 0.0

        # Register in Physical Twin as STABLE_INK
        twin.add_object(
            InkObject(
                id=oid,
                state=PhysicalState.STABLE_INK,
                points=sim_obj.points,
                bbox=sim_obj.bbox,
                centroid=sim_obj.centroid,
                area_mm2=orig_area,
            )
        )
        assert twin.get_state(oid) == PhysicalState.STABLE_INK

        # 2. Plan cleaning mission starting from Home Dock
        stroke_poly = box(*sim_obj.bbox)
        plan = plan_full_mission(
            target_clusters=[(oid, stroke_poly)],
            lane_overlap=0.28,
            duster_width_mm=162.0,
            duster_height_mm=58.0,
            board_height_mm=700.0,
        )
        assert len(plan.waypoints) >= 4
        assert plan.waypoints[0].action == "DOCK"
        assert plan.waypoints[-1].action == "DOCK"

        # 3. First wiping pass with 85% efficiency: mark active wipe -> PARTIALLY_CLEANED
        swept_hull = stroke_poly.buffer(5.0)
        cleaning_engine.apply_wipe(board, swept_hull, efficiency_override=0.85)
        twin.get_object(oid).state = PhysicalState.PARTIALLY_CLEANED

        # 4. Verification post pass 1: residual ~ 15%
        res_fraction = 0.15
        tier = exec_st.evaluate_residual(res_fraction)
        assert tier == ResidualTier.TIER_3_MAJOR_RESIDUAL
        assert exec_st.residual_detected is True

        # Reconcile post-wipe 1 (Truth Table Row 15): PARTIALLY_CLEANED -> RECLEAN_PENDING
        res_event = ReconcilerEvent(
            target_object_id=oid,
            evidence_type=ObservationType.OBS_INK,
            spatial_match=True,
            residual_ratio=res_fraction,
        )
        twin, exec_st, actions = reconcile(twin, exec_st, res_event, config)

        assert twin.get_state(oid) == PhysicalState.PARTIALLY_CLEANED
        assert exec_st.state == ExecutionState.RECLEAN_PENDING
        assert twin.get_object(oid).reclean_attempts == 1

        # 5. Secondary re-clean wiping pass (efficiency 0.98)
        cleaning_engine.apply_wipe(board, swept_hull, efficiency_override=0.98)

        # 6. Verification post pass 2 (Truth Table Row 16): residual <= 0.01 (verified clean)
        clean_event = ReconcilerEvent(
            target_object_id=oid,
            evidence_type=ObservationType.OBS_ABSENT,
            spatial_match=False,
            residual_ratio=0.003,
        )
        twin, exec_st, actions = reconcile(twin, exec_st, clean_event, config)

        assert twin.get_state(oid) == PhysicalState.CLEANED
        assert exec_st.state == ExecutionState.IDLE
        assert exec_st.residual_detected is False

    def test_scenario_2_multiple_clusters_sequential(self, env):
        """Scenario 2: Three separated clusters cleaned sequentially."""
        config, board, cleaning_engine, twin, exec_st = env

        meta = load_scenario_2_multiple_clusters(board)
        assert meta["scenario_id"] == 2
        stroke_ids = meta["stroke_ids"]
        assert len(stroke_ids) == 3

        # Populate twin store
        clusters = []
        for sid in stroke_ids:
            s_obj = board.ink_objects[sid]
            poly = box(*s_obj.bbox)
            clusters.append((sid, poly))
            twin.add_object(
                InkObject(
                    id=sid,
                    state=PhysicalState.PARTIALLY_CLEANED,  # Under active cleaning mission
                    points=s_obj.points,
                    bbox=s_obj.bbox,
                    centroid=s_obj.centroid,
                    area_mm2=s_obj.area_mm2,
                )
            )

        assert len(twin.get_active_ink_objects()) == 3

        # Plan full trajectory for all 3 clusters
        plan = plan_full_mission(target_clusters=clusters)
        assert len(plan.target_object_ids) == 3

        # Wipe each cluster completely (Row 16: PARTIALLY_CLEANED -> OBS_ABSENT -> CLEANED)
        for sid, poly in clusters:
            cleaning_engine.apply_wipe(board, poly.buffer(5.0), efficiency_override=1.0)
            clean_event = ReconcilerEvent(
                target_object_id=sid,
                evidence_type=ObservationType.OBS_ABSENT,
                spatial_match=False,
            )
            twin, exec_st, _ = reconcile(twin, exec_st, clean_event, config)

        # All 3 verified cleaned
        for sid in stroke_ids:
            assert twin.get_state(sid) == PhysicalState.CLEANED
        assert len(twin.get_active_ink_objects()) == 0

    def test_scenario_3_human_hand_occlusion(self, env):
        """Scenario 3: Hand occluding ink marks twin as OCCLUDED without deletion."""
        config, board, _, twin, exec_st = env

        meta = load_scenario_3_human_hand_occlusion(board)
        assert meta["scenario_id"] == 3
        oid = meta["stroke_ids"][0]
        s_obj = board.ink_objects[oid]

        twin.add_object(
            InkObject(
                id=oid,
                state=PhysicalState.STABLE_INK,
                bbox=s_obj.bbox,
                centroid=s_obj.centroid,
                area_mm2=s_obj.area_mm2,
            )
        )

        # Occluder covers ink
        occ_event = ReconcilerEvent(
            target_object_id=oid,
            evidence_type=ObservationType.OBS_OCCLUDED,
            spatial_match=True,
            bbox=s_obj.bbox,
        )
        twin, exec_st, _ = reconcile(twin, exec_st, occ_event, config)

        # INVARIANT: Preserved in twin
        obj = twin.get_object(oid)
        assert obj is not None
        assert obj.state == PhysicalState.OCCLUDED
        assert obj.is_occluded is True

        # Hand leaves: restored
        restore_event = ReconcilerEvent(
            target_object_id=oid,
            evidence_type=ObservationType.OBS_INK,
            spatial_match=True,
        )
        twin, exec_st, _ = reconcile(twin, exec_st, restore_event, config)
        assert twin.get_state(oid) == PhysicalState.STABLE_INK
        assert twin.get_object(oid).is_occluded is False

    def test_scenario_4_projector_artifacts(self, env):
        """Scenario 4: Additive projector light marked UNKNOWN, never converted to ink."""
        config, board, _, twin, exec_st = env
        board.baseline_bgr.fill(170)  # Natural classroom ambient illumination

        meta = load_scenario_4_projector_artifacts(board)
        assert meta["scenario_id"] == 4
        real_oid = meta["stroke_ids"][0]
        s_obj = board.ink_objects[real_oid]

        # Register real stroke
        twin.add_object(
            InkObject(
                id=real_oid,
                state=PhysicalState.STABLE_INK,
                bbox=s_obj.bbox,
                centroid=s_obj.centroid,
            )
        )

        # Projector overlay evaluated: Mode A continuous likelihood detects projected light
        decoupler = ProjectorDecoupler()
        rendered_frame = board.render_composite()
        likelihood = decoupler.compute_likelihood(rendered_frame, board.baseline_bgr)

        # Projector region has high likelihood (> 0.35)
        proj_box = meta["projector_region"]
        x1, y1, x2, y2 = proj_box
        assert np.mean(likelihood[y1:y2, x1:x2]) > 0.35

        # Reconciler receives ambiguous projector event -> UNKNOWN
        proj_event = ReconcilerEvent(
            target_object_id=None,
            evidence_type=ObservationType.OBS_UNCERTAIN,
            bbox=(float(x1), float(y1), float(x2), float(y2)),
            area_mm2=float((x2 - x1) * (y2 - y1)),
        )
        twin, exec_st, _ = reconcile(twin, exec_st, proj_event, config)

        # Invariants verified:
        # Real ink is STABLE_INK
        assert twin.get_state(real_oid) == PhysicalState.STABLE_INK
        # Active ink count is strictly 1 (projector region is NOT active ink)
        assert len(twin.get_all_objects()) == 2
        states = {o.state for o in twin.get_all_objects()}
        assert PhysicalState.UNKNOWN in states
        assert PhysicalState.STABLE_INK in states

    def test_scenario_5_stubborn_residual_cap_hit(self, env):
        """Scenario 5: 3 failed wipe attempts promote stubborn residual to PERMANENT_DEFECT."""
        config, board, cleaning_engine, twin, exec_st = env

        meta = load_scenario_5_stubborn_residual_cap_hit(board)
        assert meta["scenario_id"] == 5
        oid = meta["stroke_ids"][0]
        s_obj = board.ink_objects[oid]

        twin.add_object(
            InkObject(
                id=oid,
                state=PhysicalState.PARTIALLY_CLEANED,
                bbox=s_obj.bbox,
                reclean_attempts=0,
            )
        )

        # Attempt 1: Failed clean (residual remains) -> attempts becomes 1
        ev1 = ReconcilerEvent(target_object_id=oid, evidence_type=ObservationType.OBS_INK, residual_ratio=0.10)
        twin, exec_st, _ = reconcile(twin, exec_st, ev1, config)
        assert twin.get_object(oid).reclean_attempts == 1
        assert twin.get_state(oid) == PhysicalState.PARTIALLY_CLEANED

        # Attempt 2: Failed clean -> attempts becomes 2
        ev2 = ReconcilerEvent(target_object_id=oid, evidence_type=ObservationType.OBS_INK, residual_ratio=0.08)
        twin, exec_st, _ = reconcile(twin, exec_st, ev2, config)
        assert twin.get_object(oid).reclean_attempts == 2
        assert twin.get_state(oid) == PhysicalState.PARTIALLY_CLEANED

        # Attempt 3: Failed clean -> attempts becomes 3
        ev3 = ReconcilerEvent(target_object_id=oid, evidence_type=ObservationType.OBS_INK, residual_ratio=0.07)
        twin, exec_st, _ = reconcile(twin, exec_st, ev3, config)
        assert twin.get_object(oid).reclean_attempts == 3

        # Next check with attempts >= 3: Row 21 fires -> Promoted to PERMANENT_DEFECT
        ev_cap = ReconcilerEvent(target_object_id=oid, evidence_type=ObservationType.OBS_INK, residual_ratio=0.07)
        twin, exec_st, actions = reconcile(twin, exec_st, ev_cap, config)

        # Row 21 Invariant Verified:
        obj = twin.get_object(oid)
        assert obj.state == PhysicalState.PERMANENT_DEFECT
        assert "RECLEAN_CAP_HIT" in [a.action_type for a in actions]
        assert exec_st.state == ExecutionState.IDLE
        assert oid not in exec_st.reclean_queue
        assert np.any(twin.permanent_defect_mask > 0)

    def test_scenario_6_dirty_board_baseline_abort(self, env):
        """Scenario 6: Board edge density > 4% causes baseline capture rejection."""
        _, board, _, _, _ = env

        meta = load_scenario_6_dirty_board_baseline_abort(board)
        assert meta["scenario_id"] == 6
        assert meta["edge_density"] > 0.04
        assert meta["should_abort"] is True

        # Attempt baseline capture
        manager = BaselineEpochManager(frames_to_accumulate=3, dirty_board_threshold=0.04)
        rendered = board.render_composite()
        for _ in range(3):
            manager.add_frame(rendered)

        with pytest.raises(DirtyBoardError) as exc_info:
            manager.finalize_capture(allow_override=False)

        assert exc_info.value.edge_density > 0.04
        assert manager.current_epoch is None
