from __future__ import annotations

import pytest
from app.core.config import AppConfig, get_config
from app.digital_twin.board_twin import BoardTwinStore, InkObject
from app.digital_twin.execution_state import ExecutionStore
from app.digital_twin.reconciler import CommitReconciler, ReconcilerEvent
from app.schemas.ink import CoordinateFrame, PhysicalState
from app.schemas.perception import ObservationType
from app.schemas.planner import ExecutionState, ResidualTier


def test_reclean_safety_cap_progression():
    """Verify that an ink stroke transitions to PERMANENT_DEFECT after MAX_RECLEAN_ATTEMPTS."""
    config = get_config()
    max_recleans = config.cleaning.max_reclean_attempts  # default 3
    assert max_recleans == 3

    twin = BoardTwinStore(config)
    exec_store = ExecutionStore(config)
    reconciler = CommitReconciler(twin, exec_store, config)

    obj_id = "stubborn_marker_stroke"
    obj = InkObject(
        id=obj_id,
        state=PhysicalState.PARTIALLY_CLEANED,
        frame_id=CoordinateFrame.FRAME_BOARD,
        points=[[200.0, 300.0], [250.0, 300.0], [250.0, 350.0], [200.0, 350.0]],
        bbox=(200.0, 300.0, 250.0, 350.0),
        centroid=(225.0, 325.0),
        confidence=1.0,
        reclean_attempts=0,
    )
    twin.add_object(obj)

    # Progression through allowable re-cleans
    for attempt in range(1, max_recleans + 1):
        event = ReconcilerEvent(
            target_object_id=obj_id,
            evidence_type=ObservationType.OBS_INK,
            spatial_match=True,
            residual_ratio=0.035,  # 3.5% residual
        )
        twin, exec_store, actions = reconciler.reconcile(twin, exec_store, event)
        current_obj = twin.get_object(obj_id)

        assert current_obj.state == PhysicalState.PARTIALLY_CLEANED
        assert current_obj.reclean_attempts == attempt
        assert exec_store.state == ExecutionState.RECLEAN_PENDING
        assert exec_store.residual_detected is True
        assert exec_store.residual_tier == ResidualTier.TIER_2_FINE_RESIDUAL
        assert obj_id in exec_store.reclean_queue
        assert any(a.action_type == "SCHEDULE_RECLEAN" for a in actions)

    # Next attempt (attempt 4, reclean_attempts == 3 >= MAX_RECLEAN_ATTEMPTS):
    # Must trigger Row 21: Cap hit -> PERMANENT_DEFECT
    cap_event = ReconcilerEvent(
        target_object_id=obj_id,
        evidence_type=ObservationType.OBS_INK,
        spatial_match=True,
        residual_ratio=0.035,
    )
    twin, exec_store, actions = reconciler.reconcile(twin, exec_store, cap_event)
    final_obj = twin.get_object(obj_id)

    assert final_obj.state == PhysicalState.PERMANENT_DEFECT, (
        f"Expected PERMANENT_DEFECT after {max_recleans} attempts, got {final_obj.state}"
    )
    assert exec_store.state == ExecutionState.IDLE
    assert obj_id not in exec_store.reclean_queue
    assert any(a.action_type == "RECLEAN_CAP_HIT" for a in actions)
    assert any(a.action_type == "PROMOTE_PERMANENT_DEFECT" for a in actions)


def test_successful_reclean_clears_queue():
    """Verify that successful clean before reaching cap clears reclean_queue and sets CLEANED."""
    config = get_config()
    twin = BoardTwinStore(config)
    exec_store = ExecutionStore(config)
    reconciler = CommitReconciler(twin, exec_store, config)

    obj_id = "partially_cleaned_stroke"
    obj = InkObject(
        id=obj_id,
        state=PhysicalState.PARTIALLY_CLEANED,
        frame_id=CoordinateFrame.FRAME_BOARD,
        points=[[100.0, 100.0], [150.0, 100.0], [150.0, 150.0]],
        centroid=(125.0, 116.6),
        confidence=1.0,
        reclean_attempts=1,
    )
    twin.add_object(obj)
    exec_store.reclean_queue.append(obj_id)
    exec_store.set_state(ExecutionState.VERIFYING)

    clean_event = ReconcilerEvent(
        target_object_id=obj_id,
        evidence_type=ObservationType.OBS_ABSENT,
        spatial_match=False,
        residual_ratio=0.005,  # 0.5% residual <= clean_threshold (1%)
    )
    twin, exec_store, actions = reconciler.reconcile(twin, exec_store, clean_event)
    cleaned_obj = twin.get_object(obj_id)

    assert cleaned_obj.state == PhysicalState.CLEANED
    assert obj_id not in exec_store.reclean_queue
    assert exec_store.state == ExecutionState.IDLE
    assert any(a.action_type == "MARK_CLEANED" for a in actions)


def test_configurable_safety_cap_threshold():
    """Verify that safety cap threshold dynamically adapts when config value changes."""
    custom_config = AppConfig()
    custom_config.cleaning.max_reclean_attempts = 1  # Cap at 1 attempt

    twin = BoardTwinStore(custom_config)
    exec_store = ExecutionStore(custom_config)
    reconciler = CommitReconciler(twin, exec_store, custom_config)

    obj_id = "test_custom_cap_obj"
    obj = InkObject(
        id=obj_id,
        state=PhysicalState.PARTIALLY_CLEANED,
        reclean_attempts=0,
    )
    twin.add_object(obj)

    # First attempt: increments reclean_attempts to 1
    event1 = ReconcilerEvent(
        target_object_id=obj_id,
        evidence_type=ObservationType.OBS_INK,
        spatial_match=True,
    )
    twin, exec_store, _ = reconciler.reconcile(twin, exec_store, event1)
    assert twin.get_object(obj_id).reclean_attempts == 1

    # Second attempt: reclean_attempts == 1 >= max_reclean_attempts (1) -> Cap Hit!
    event2 = ReconcilerEvent(
        target_object_id=obj_id,
        evidence_type=ObservationType.OBS_INK,
        spatial_match=True,
    )
    twin, exec_store, actions = reconciler.reconcile(twin, exec_store, event2)
    assert twin.get_object(obj_id).state == PhysicalState.PERMANENT_DEFECT
    assert any(a.action_type == "RECLEAN_CAP_HIT" for a in actions)
