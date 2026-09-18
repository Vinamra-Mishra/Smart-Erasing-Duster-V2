from __future__ import annotations

import pytest
from app.core.config import get_config
from app.digital_twin.board_twin import BoardTwinStore, InkObject
from app.digital_twin.execution_state import ExecutionStore
from app.digital_twin.reconciler import CommitReconciler, ReconcilerEvent, reconcile
from app.schemas.ink import CoordinateFrame, PhysicalState
from app.schemas.perception import ObservationType
from app.schemas.planner import ExecutionState


def create_test_setup():
    """Create fresh, isolated instances of twin store, execution store, and reconciler."""
    config = get_config()
    twin_store = BoardTwinStore(config)
    exec_store = ExecutionStore(config)
    reconciler = CommitReconciler(twin_store, exec_store, config)
    return twin_store, exec_store, reconciler


def test_invariant_residual_detected_not_in_physical_state():
    """INVARIANT: RESIDUAL_DETECTED must never be a PhysicalState enum value."""
    physical_values = [state.value for state in PhysicalState]
    assert "RESIDUAL_DETECTED" not in physical_values, (
        "Invariant violation: RESIDUAL_DETECTED found in PhysicalState! "
        "It must be an ExecutionStore trigger flag only."
    )


@pytest.mark.parametrize(
    "row_id, initial_state, initial_exec, obs_type, spatial_match, recleans, expected_state, expected_exec",
    [
        # Row 1: Clean board rejects absent/shadow
        (1, None, ExecutionState.IDLE, ObservationType.OBS_ABSENT, False, 0, None, ExecutionState.IDLE),
        # Row 2: Confirmed ink appearance creates STABLE_INK
        (2, None, ExecutionState.IDLE, ObservationType.OBS_INK, False, 0, PhysicalState.STABLE_INK, ExecutionState.IDLE),
        # Row 3: Human occlusion over clean board updates mask, no phantom ink
        (3, None, ExecutionState.IDLE, ObservationType.OBS_OCCLUDED, False, 0, None, ExecutionState.IDLE),
        # Row 4: Optical disturbance creates UNKNOWN region
        (4, None, ExecutionState.IDLE, ObservationType.OBS_PROJECTOR, False, 0, PhysicalState.UNKNOWN, ExecutionState.IDLE),
        # Row 5: UNKNOWN resolved to STABLE_INK when ink confirmed
        (5, PhysicalState.UNKNOWN, ExecutionState.IDLE, ObservationType.OBS_INK, True, 0, PhysicalState.STABLE_INK, ExecutionState.IDLE),
        # Row 6: UNKNOWN resolved to CLEANED when absent
        (6, PhysicalState.UNKNOWN, ExecutionState.IDLE, ObservationType.OBS_ABSENT, False, 0, PhysicalState.CLEANED, ExecutionState.IDLE),
        # Row 7: UNKNOWN retained when disturbance persists
        (7, PhysicalState.UNKNOWN, ExecutionState.IDLE, ObservationType.OBS_OCCLUDED, False, 0, PhysicalState.UNKNOWN, ExecutionState.IDLE),
        # Row 8: Steady-state STABLE_INK observation maintained
        (8, PhysicalState.STABLE_INK, ExecutionState.IDLE, ObservationType.OBS_INK, True, 0, PhysicalState.STABLE_INK, ExecutionState.IDLE),
        # Row 9: Separate ink stroke creates new ink object, retains original
        (9, PhysicalState.STABLE_INK, ExecutionState.IDLE, ObservationType.OBS_INK, False, 0, PhysicalState.STABLE_INK, ExecutionState.IDLE),
        # Row 10: Human blocks ink -> OCCLUDED (never delete ink)
        (10, PhysicalState.STABLE_INK, ExecutionState.IDLE, ObservationType.OBS_OCCLUDED, True, 0, PhysicalState.OCCLUDED, ExecutionState.IDLE),
        # Row 11: Ink vanishes without wipe -> degrade confidence to UNKNOWN
        (11, PhysicalState.STABLE_INK, ExecutionState.IDLE, ObservationType.OBS_ABSENT, False, 0, PhysicalState.UNKNOWN, ExecutionState.IDLE),
        # Row 12: Occlusion persists
        (12, PhysicalState.OCCLUDED, ExecutionState.IDLE, ObservationType.OBS_OCCLUDED, True, 0, PhysicalState.OCCLUDED, ExecutionState.IDLE),
        # Row 13: Human departs, ink restored
        (13, PhysicalState.OCCLUDED, ExecutionState.IDLE, ObservationType.OBS_INK, True, 0, PhysicalState.STABLE_INK, ExecutionState.IDLE),
        # Row 14: Human departs, ink missing -> suspect external erasure
        (14, PhysicalState.OCCLUDED, ExecutionState.IDLE, ObservationType.OBS_ABSENT, False, 0, PhysicalState.UNKNOWN, ExecutionState.IDLE),
        # Row 15: Post-wipe residual persists below cap -> RECLEAN_PENDING
        (15, PhysicalState.PARTIALLY_CLEANED, ExecutionState.VERIFYING, ObservationType.OBS_INK, True, 1, PhysicalState.PARTIALLY_CLEANED, ExecutionState.RECLEAN_PENDING),
        # Row 16: Post-wipe clean confirmed -> CLEANED
        (16, PhysicalState.PARTIALLY_CLEANED, ExecutionState.VERIFYING, ObservationType.OBS_ABSENT, False, 1, PhysicalState.CLEANED, ExecutionState.IDLE),
        # Row 17: User rewrites ink over cleaned area
        (17, PhysicalState.CLEANED, ExecutionState.IDLE, ObservationType.OBS_INK, False, 0, PhysicalState.STABLE_INK, ExecutionState.IDLE),
        # Row 18: Cleaned area remains clean
        (18, PhysicalState.CLEANED, ExecutionState.IDLE, ObservationType.OBS_ABSENT, False, 0, PhysicalState.CLEANED, ExecutionState.IDLE),
        # Row 19: Permanent defect retained
        (19, PhysicalState.PERMANENT_DEFECT, ExecutionState.IDLE, ObservationType.OBS_INK, True, 3, PhysicalState.PERMANENT_DEFECT, ExecutionState.IDLE),
        # Row 20: Permanent defect temporarily occluded
        (20, PhysicalState.PERMANENT_DEFECT, ExecutionState.IDLE, ObservationType.OBS_OCCLUDED, True, 3, PhysicalState.PERMANENT_DEFECT, ExecutionState.IDLE),
        # Row 21: Stubborn ink exceeds MAX_RECLEAN_ATTEMPTS -> PERMANENT_DEFECT
        (21, PhysicalState.PARTIALLY_CLEANED, ExecutionState.VERIFYING, ObservationType.OBS_INK, True, 3, PhysicalState.PERMANENT_DEFECT, ExecutionState.IDLE),
    ],
)
def test_commit_truth_table_all_21_rows(
    row_id: int,
    initial_state: PhysicalState | None,
    initial_exec: ExecutionState,
    obs_type: ObservationType,
    spatial_match: bool,
    recleans: int,
    expected_state: PhysicalState | None,
    expected_exec: ExecutionState,
):
    """Test every single row of the 21-Row Commit Truth Table deterministically."""
    twin, exec_store, reconciler = create_test_setup()
    exec_store.set_state(initial_exec)

    obj_id = "test_target_obj"

    # Setup initial state in twin store if specified
    if initial_state is not None:
        initial_confidence = 0.5 if row_id == 11 else 1.0  # Allow Row 11 to decrement to UNKNOWN
        obj = InkObject(
            id=obj_id,
            state=initial_state,
            frame_id=CoordinateFrame.FRAME_BOARD,
            points=[[100.0, 100.0], [150.0, 100.0], [150.0, 150.0], [100.0, 150.0]],
            bbox=(100.0, 100.0, 150.0, 150.0),
            centroid=(125.0, 125.0),
            confidence=initial_confidence,
            reclean_attempts=recleans,
            is_occluded=(initial_state == PhysicalState.OCCLUDED),
        )
        twin.add_object(obj)

    # Construct reconciler event
    event = ReconcilerEvent(
        target_object_id=obj_id,
        evidence_type=obs_type,
        spatial_match=spatial_match,
        points=[[100.0, 100.0], [150.0, 100.0], [150.0, 150.0], [100.0, 150.0]],
        bbox=(100.0, 100.0, 150.0, 150.0),
        centroid=(125.0, 125.0),
        residual_ratio=0.03 if row_id == 15 else (0.005 if row_id == 16 else 0.0),
        row_hint=row_id,
    )

    next_twin, next_exec, actions = reconciler.reconcile(twin, exec_store, event)

    # Verify next physical state
    if row_id == 2:
        # For new ink creation, check that an object was created and is STABLE_INK
        active_objs = next_twin.get_all_objects()
        assert len(active_objs) == 1
        assert active_objs[0].state == PhysicalState.STABLE_INK
    elif row_id == 9:
        # Original remains STABLE_INK and new object was added
        assert next_twin.get_state(obj_id) == PhysicalState.STABLE_INK
        assert len(next_twin.get_all_objects()) == 2
    elif row_id == 17:
        # New ink added
        assert len(next_twin.get_all_objects()) == 2
    elif expected_state is None:
        assert next_twin.get_state(obj_id) is None
    else:
        assert next_twin.get_state(obj_id) == expected_state, (
            f"Row {row_id} failed: Expected physical state {expected_state}, "
            f"got {next_twin.get_state(obj_id)}"
        )

    # Verify next execution state
    assert next_exec.state == expected_exec, (
        f"Row {row_id} failed: Expected execution state {expected_exec}, got {next_exec.state}"
    )

    # Special row verification assertions
    if row_id == 10:
        assert next_twin.get_object(obj_id).is_occluded is True
    elif row_id == 13:
        assert next_twin.get_object(obj_id).is_occluded is False
    elif row_id == 15:
        assert next_exec.residual_detected is True
        action_types = [a.action_type for a in actions]
        assert "SCHEDULE_RECLEAN" in action_types
    elif row_id == 21:
        action_types = [a.action_type for a in actions]
        assert "RECLEAN_CAP_HIT" in action_types
        assert "PROMOTE_PERMANENT_DEFECT" in action_types
        assert next_twin.get_state(obj_id) == PhysicalState.PERMANENT_DEFECT
