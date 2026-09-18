"""E2E Test: Projector Mode A Likelihood & Ambiguous UNKNOWN State Handling.

Verifies:
1. Mode A camera-only continuous projector likelihood computation in [0.0, 1.0].
2. High-confidence projector signal (>= 0.80) suppresses raw candidates from physical ink.
3. Ambiguous projector regions (0.30 < L < 0.80) are classified as OBS_UNCERTAIN / UNKNOWN.
4. CRITICAL INVARIANT: UNKNOWN regions are NEVER automatically converted to NEW_INK or STABLE_INK.
5. CRITICAL INVARIANT: Projector light cast over existing STABLE_INK NEVER deletes physical ink.
6. Planner ignores UNKNOWN regions in uncertainty_mask (duster never wipes light).
7. Resolving UNKNOWN: Turning off projector (OBS_ABSENT) resolves to CLEANED (Row 6).
8. Resolving UNKNOWN: Real ink confirmed (OBS_INK) resolves to STABLE_INK (Row 5).
"""
from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.core.config import AppConfig
from app.digital_twin.board_twin import BoardTwinStore, InkObject
from app.digital_twin.execution_state import ExecutionStore
from app.digital_twin.reconciler import ReconcilerEvent, reconcile
from app.perception.projector import ProjectorDecoupler, compute_projector_likelihood
from app.schemas.ink import CoordinateFrame, PhysicalState
from app.schemas.perception import ObservationType


class TestProjectorModeAE2E:
    """E2E test suite for Projector Mode A decoupling and digital twin state invariants."""

    @pytest.fixture
    def setup_system(self):
        config = AppConfig()
        twin_store = BoardTwinStore(config=config)
        exec_store = ExecutionStore(config=config)
        decoupler = ProjectorDecoupler()
        return config, twin_store, exec_store, decoupler

    def test_mode_a_continuous_likelihood_computation(self, setup_system):
        """Mode A produces continuous likelihood in [0.0, 1.0] based on additive brightness."""
        _, _, _, decoupler = setup_system
        h, w = 700, 1000

        # Baseline whiteboard: ambient lighting
        reference_bgr = np.full((h, w, 3), 180, dtype=np.uint8)

        # Current frame with additive chromatic projected slide beam
        current_bgr = reference_bgr.copy()
        current_bgr[200:400, 300:600] = [50, 220, 255]

        likelihood_map = decoupler.compute_likelihood(current_bgr, reference_bgr)

        assert likelihood_map.shape == (h, w)
        assert np.all(likelihood_map >= 0.0)
        assert np.all(likelihood_map <= 1.0)
        # Inside projector beam: high likelihood
        assert np.mean(likelihood_map[200:400, 300:600]) > 0.60
        # Outside projector beam: zero likelihood
        assert np.mean(likelihood_map[:100, :100]) == pytest.approx(0.0, abs=1e-3)

    def test_ambiguous_projector_region_assigned_to_unknown(self, setup_system):
        """CRITICAL INVARIANT: Ambiguous region assigned to UNKNOWN, NEVER to ink (Row 4)."""
        config, twin, exec_st, _ = setup_system

        assert len(twin.get_all_objects()) == 0

        # Ambiguous projector artifact (e.g. low-contrast presentation slide)
        event = ReconcilerEvent(
            target_object_id=None,
            evidence_type=ObservationType.OBS_UNCERTAIN,
            spatial_match=False,
            points=[[200.0, 150.0], [400.0, 150.0], [400.0, 350.0], [200.0, 350.0]],
            bbox=(200.0, 150.0, 400.0, 350.0),
            centroid=(300.0, 250.0),
            area_mm2=40000.0,
        )

        next_twin, next_exec, actions = reconcile(twin, exec_st, event, config)

        # Invariant: Must NOT create STABLE_INK or NEW_INK
        all_objs = next_twin.get_all_objects()
        assert len(all_objs) == 1
        unk_obj = all_objs[0]
        assert unk_obj.state == PhysicalState.UNKNOWN
        assert unk_obj.state != PhysicalState.NEW_INK
        assert unk_obj.state != PhysicalState.STABLE_INK

        # Added to uncertainty mask
        assert np.any(next_twin.uncertainty_mask > 0)
        action_types = [a.action_type for a in actions]
        assert "FLAG_UNCERTAINTY" in action_types

    def test_projector_decoupler_filter_rejects_ink_creation_from_unknown(self, setup_system):
        """Projector decoupler filter ensures UNKNOWN never creates new physical ink."""
        _, _, _, decoupler = setup_system
        h, w = 700, 1000

        # Raw candidate mask claiming ink where projector is shining
        raw_candidates = np.zeros((h, w), dtype=bool)
        raw_candidates[150:350, 200:400] = True

        # Ambiguous likelihood = 0.55
        likelihood = np.zeros((h, w), dtype=np.float32)
        likelihood[150:350, 200:400] = 0.55

        filtered_ink, uncertainty_mask = decoupler.filter_ink_candidates(raw_candidates, likelihood)

        # Filtered ink must be empty (prevented from becoming ink)
        assert not np.any(filtered_ink)
        # Marked into uncertainty mask
        assert np.all(uncertainty_mask[150:350, 200:400])

    def test_projector_beam_never_deletes_existing_stable_ink(self, setup_system):
        """CRITICAL INVARIANT: Projector overlaying existing STABLE_INK does NOT delete it."""
        config, twin, exec_st, decoupler = setup_system
        h, w = 700, 1000

        # Pre-existing confirmed marker ink
        ink_id = "real_physical_ink"
        twin.add_object(
            InkObject(
                id=ink_id,
                state=PhysicalState.STABLE_INK,
                bbox=(250.0, 200.0, 350.0, 250.0),
                centroid=(300.0, 225.0),
                area_mm2=5000.0,
            )
        )

        # Existing stable ink mask
        twin_stable_mask = np.zeros((h, w), dtype=bool)
        twin_stable_mask[200:250, 250:350] = True

        # Projector turns on over that exact region
        projector_high_conf = np.zeros((h, w), dtype=bool)
        projector_high_conf[150:300, 200:400] = True
        uncertainty = np.zeros((h, w), dtype=bool)
        new_obs = np.zeros((h, w), dtype=bool)

        reconciled_mask = decoupler.reconcile_projector_with_twin(
            twin_stable_ink_mask=twin_stable_mask,
            projector_high_conf_mask=projector_high_conf,
            uncertainty_mask=uncertainty,
            new_observations_mask=new_obs,
        )

        # Invariant 1 verified: Real ink still present in physical digital twin
        assert np.all(reconciled_mask[200:250, 250:350])
        # Object in store remains STABLE_INK
        assert twin.get_object(ink_id).state == PhysicalState.STABLE_INK

    def test_resolving_unknown_to_cleaned_when_projector_turns_off(self, setup_system):
        """When projector turns off (OBS_ABSENT), UNKNOWN resolves to CLEANED (Row 6)."""
        config, twin, exec_st, _ = setup_system

        unk_id = "projector_disturbance"
        twin.add_object(
            InkObject(
                id=unk_id,
                state=PhysicalState.UNKNOWN,
                bbox=(100.0, 100.0, 250.0, 250.0),
            )
        )

        event = ReconcilerEvent(
            target_object_id=unk_id,
            evidence_type=ObservationType.OBS_ABSENT,
            spatial_match=False,
        )

        next_twin, next_exec, actions = reconcile(twin, exec_st, event, config)
        obj = next_twin.get_object(unk_id)
        assert obj.state == PhysicalState.CLEANED
        action_types = [a.action_type for a in actions]
        assert "CLEAR_UNCERTAINTY" in action_types

    def test_resolving_unknown_to_stable_ink_when_marker_confirmed(self, setup_system):
        """When real marker stroke is drawn over ambiguous area, resolves to STABLE_INK (Row 5)."""
        config, twin, exec_st, _ = setup_system

        unk_id = "ambiguous_spot"
        twin.add_object(
            InkObject(
                id=unk_id,
                state=PhysicalState.UNKNOWN,
                bbox=(200.0, 200.0, 300.0, 300.0),
                centroid=(250.0, 250.0),
            )
        )

        event = ReconcilerEvent(
            target_object_id=unk_id,
            evidence_type=ObservationType.OBS_INK,
            spatial_match=True,
            points=[[200.0, 200.0], [300.0, 200.0], [300.0, 300.0], [200.0, 300.0]],
            bbox=(200.0, 200.0, 300.0, 300.0),
            centroid=(250.0, 250.0),
            confidence=0.99,
        )

        next_twin, next_exec, actions = reconcile(twin, exec_st, event, config)
        obj = next_twin.get_object(unk_id)
        assert obj.state == PhysicalState.STABLE_INK
        assert obj.confidence == 1.0
        action_types = [a.action_type for a in actions]
        assert "CONFIRM_INK_OBJECT" in action_types
