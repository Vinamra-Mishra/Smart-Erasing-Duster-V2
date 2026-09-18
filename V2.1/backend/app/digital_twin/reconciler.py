from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any, Dict, List, Optional, Tuple
import uuid
import numpy as np

from app.core.config import AppConfig, get_config
from app.digital_twin.board_twin import BoardTwinStore, InkObject
from app.digital_twin.execution_state import ExecutionStore
from app.schemas.events import EventType
from app.schemas.ink import CoordinateFrame, PhysicalState
from app.schemas.perception import ObservationType
from app.schemas.planner import ExecutionState, ResidualTier


@dataclass
class ReconcilerAction:
    """Pure data action emitted by the pure reducer."""
    action_type: str
    object_id: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReconcilerEvent:
    """Input event envelope ingested by the Commit Reconciler."""
    event_type: EventType | str = EventType.OBSERVATION_FRAME_EVALUATED
    target_object_id: Optional[str] = None
    evidence_type: ObservationType = ObservationType.OBS_ABSENT
    spatial_match: bool = False
    points: Optional[List[List[float]]] = None
    bbox: Optional[Tuple[float, float, float, float]] = None
    centroid: Optional[Tuple[float, float]] = None
    confidence: float = 1.0
    residual_ratio: float = 0.0
    color_bgr: Tuple[int, int, int] = (0, 0, 0)
    area_mm2: float = 0.0
    holes: Optional[List[List[List[float]]]] = None
    row_hint: Optional[int] = None


def reconcile(
    twin_store: BoardTwinStore,
    exec_store: ExecutionStore,
    event: ReconcilerEvent,
    config: Optional[AppConfig] = None,
) -> Tuple[BoardTwinStore, ExecutionStore, List[ReconcilerAction]]:
    """Pure Event-Sourced Reducer executing the 21-Row Commit Truth Table.

    Signature:
        reconcile(twin, exec, event) -> (next_twin, next_exec, actions)
    """
    cfg = config or twin_store.config or get_config()
    next_twin = twin_store.clone()
    next_exec = exec_store.clone()
    actions: List[ReconcilerAction] = []

    obs = event.evidence_type
    spatial_match = event.spatial_match
    target_id = event.target_object_id
    obj = next_twin.get_object(target_id) if target_id else None

    # Determine current twin state
    current_state: Optional[PhysicalState] = obj.state if obj else None

    # Check for safety cap promotion first (Row 21)
    # Row 21: Any state (typically PARTIALLY_CLEANED) where reclean attempts reach or exceed max
    max_recleans = cfg.cleaning.max_reclean_attempts
    if obj is not None and obj.reclean_attempts >= max_recleans and obs == ObservationType.OBS_INK:
        # Row 21: Force transition to PERMANENT_DEFECT
        obj.state = PhysicalState.PERMANENT_DEFECT
        obj.last_seen = time.time()
        # Update defect mask
        min_x, min_y, max_x, max_y = (int(max(0, v)) for v in obj.bbox)
        next_twin.permanent_defect_mask[min_y:max_y, min_x:max_x] = 255

        # Terminate execution re-clean loop
        if obj.id in next_exec.reclean_queue:
            next_exec.reclean_queue.remove(obj.id)
        next_exec.set_state(ExecutionState.IDLE)
        next_exec.clear_residual()

        actions.append(ReconcilerAction(
            action_type="RECLEAN_CAP_HIT",
            object_id=obj.id,
            payload={"reclean_attempts": obj.reclean_attempts, "max": max_recleans},
        ))
        actions.append(ReconcilerAction(
            action_type="PROMOTE_PERMANENT_DEFECT",
            object_id=obj.id,
            payload={"reason": "Safety cap exceeded"},
        ))
        return next_twin, next_exec, actions

    # Row 1: None -> OBS_ABSENT or OBS_SHADOW
    if current_state is None and obs in (ObservationType.OBS_ABSENT, ObservationType.OBS_SHADOW):
        # Do nothing, remain clean
        return next_twin, next_exec, actions

    # Row 2: None -> OBS_INK (New Ink)
    if current_state is None and obs == ObservationType.OBS_INK:
        new_id = target_id or f"ink_{uuid.uuid4().hex[:8]}"
        pts = event.points or []
        bbox = event.bbox or (0.0, 0.0, 0.0, 0.0)
        centroid = event.centroid or (0.0, 0.0)
        new_obj = InkObject(
            id=new_id,
            state=PhysicalState.STABLE_INK,
            frame_id=CoordinateFrame.FRAME_BOARD,
            points=pts,
            bbox=bbox,
            centroid=centroid,
            confidence=event.confidence,
            color_bgr=event.color_bgr,
            area_mm2=event.area_mm2,
            first_seen=time.time(),
            last_seen=time.time(),
            holes=event.holes or [],
        )
        next_twin.add_object(new_obj)
        actions.append(ReconcilerAction(
            action_type="CREATE_INK_OBJECT",
            object_id=new_id,
            payload={"state": PhysicalState.STABLE_INK.value},
        ))
        return next_twin, next_exec, actions

    # Row 3: None -> OBS_OCCLUDED
    if current_state is None and obs == ObservationType.OBS_OCCLUDED:
        if event.bbox:
            x1, y1, x2, y2 = (int(max(0, v)) for v in event.bbox)
            next_twin.board_occlusion_mask[y1:y2, x1:x2] = 255
        actions.append(ReconcilerAction(
            action_type="UPDATE_OCCLUSION_MASK",
            payload={"event": "OCCLUSION_ENTERED"},
        ))
        return next_twin, next_exec, actions

    # Row 4: None -> OBS_PROJECTOR or OBS_UNCERTAIN
    if current_state is None and obs in (ObservationType.OBS_PROJECTOR, ObservationType.OBS_UNCERTAIN):
        new_id = target_id or f"unk_{uuid.uuid4().hex[:8]}"
        pts = event.points or []
        bbox = event.bbox or (0.0, 0.0, 0.0, 0.0)
        centroid = event.centroid or (0.0, 0.0)
        unk_obj = InkObject(
            id=new_id,
            state=PhysicalState.UNKNOWN,
            frame_id=CoordinateFrame.FRAME_BOARD,
            points=pts,
            bbox=bbox,
            centroid=centroid,
            confidence=0.5,
            area_mm2=event.area_mm2,
        )
        next_twin.add_object(unk_obj)
        if event.bbox:
            x1, y1, x2, y2 = (int(max(0, v)) for v in event.bbox)
            next_twin.uncertainty_mask[y1:y2, x1:x2] = 255
        actions.append(ReconcilerAction(
            action_type="FLAG_UNCERTAINTY",
            object_id=new_id,
            payload={"reason": obs.value},
        ))
        return next_twin, next_exec, actions

    # Row 5: UNKNOWN -> OBS_INK (Spatial match)
    if current_state == PhysicalState.UNKNOWN and obs == ObservationType.OBS_INK and spatial_match:
        obj.state = PhysicalState.STABLE_INK
        obj.confidence = 1.0
        obj.last_seen = time.time()
        actions.append(ReconcilerAction(
            action_type="CONFIRM_INK_OBJECT",
            object_id=obj.id,
            payload={"state": PhysicalState.STABLE_INK.value},
        ))
        return next_twin, next_exec, actions

    # Row 6: UNKNOWN -> OBS_ABSENT
    if current_state == PhysicalState.UNKNOWN and obs == ObservationType.OBS_ABSENT:
        obj.state = PhysicalState.CLEANED
        actions.append(ReconcilerAction(
            action_type="CLEAR_UNCERTAINTY",
            object_id=obj.id,
            payload={"state": PhysicalState.CLEANED.value},
        ))
        return next_twin, next_exec, actions

    # Row 7: UNKNOWN -> OBS_OCCLUDED or OBS_UNCERTAIN
    if current_state == PhysicalState.UNKNOWN and obs in (ObservationType.OBS_OCCLUDED, ObservationType.OBS_UNCERTAIN):
        # Retain UNKNOWN
        return next_twin, next_exec, actions

    # Row 8: STABLE_INK -> OBS_INK (Spatial match)
    if current_state == PhysicalState.STABLE_INK and obs == ObservationType.OBS_INK and spatial_match:
        obj.last_seen = time.time()
        if event.points:
            obj.points = event.points
        if event.bbox:
            obj.bbox = event.bbox
        if event.centroid:
            obj.centroid = event.centroid
        if event.holes is not None:
            obj.holes = event.holes
        actions.append(ReconcilerAction(
            action_type="UPDATE_INK_OBJECT",
            object_id=obj.id,
            payload={"last_seen": obj.last_seen},
        ))
        return next_twin, next_exec, actions

    # Row 9: STABLE_INK -> OBS_INK (No spatial match: create separate new ink)
    if current_state == PhysicalState.STABLE_INK and obs == ObservationType.OBS_INK and not spatial_match:
        new_id = f"ink_{uuid.uuid4().hex[:8]}"
        pts = event.points or []
        bbox = event.bbox or (0.0, 0.0, 0.0, 0.0)
        centroid = event.centroid or (0.0, 0.0)
        new_obj = InkObject(
            id=new_id,
            state=PhysicalState.STABLE_INK,
            frame_id=CoordinateFrame.FRAME_BOARD,
            points=pts,
            bbox=bbox,
            centroid=centroid,
            confidence=event.confidence,
            color_bgr=event.color_bgr,
            area_mm2=event.area_mm2,
            first_seen=time.time(),
            last_seen=time.time(),
        )
        next_twin.add_object(new_obj)
        actions.append(ReconcilerAction(
            action_type="CREATE_INK_OBJECT",
            object_id=new_id,
            payload={"state": PhysicalState.STABLE_INK.value},
        ))
        return next_twin, next_exec, actions

    # Row 10: STABLE_INK -> OBS_OCCLUDED (Spatial match)
    # INVARIANT: NEVER DELETE INK; actor blocks camera line of sight
    if current_state == PhysicalState.STABLE_INK and obs == ObservationType.OBS_OCCLUDED and spatial_match:
        obj.state = PhysicalState.OCCLUDED
        obj.is_occluded = True
        actions.append(ReconcilerAction(
            action_type="INK_OCCLUDED",
            object_id=obj.id,
            payload={"is_occluded": True},
        ))
        return next_twin, next_exec, actions

    # Row 11: STABLE_INK -> OBS_ABSENT (No clean action)
    if current_state == PhysicalState.STABLE_INK and obs == ObservationType.OBS_ABSENT:
        obj.confidence = max(0.0, obj.confidence - 0.5)
        if obj.confidence <= 0.0:
            obj.state = PhysicalState.UNKNOWN
        actions.append(ReconcilerAction(
            action_type="DEGRADE_CONFIDENCE",
            object_id=obj.id,
            payload={"confidence": obj.confidence, "state": obj.state.value},
        ))
        return next_twin, next_exec, actions

    # Row 12: OCCLUDED -> OBS_OCCLUDED
    if current_state == PhysicalState.OCCLUDED and obs == ObservationType.OBS_OCCLUDED:
        # Retain OCCLUDED
        return next_twin, next_exec, actions

    # Row 13: OCCLUDED -> OBS_INK (Actor departed, ink restored)
    if current_state == PhysicalState.OCCLUDED and obs == ObservationType.OBS_INK and spatial_match:
        obj.state = PhysicalState.STABLE_INK
        obj.is_occluded = False
        obj.last_seen = time.time()
        actions.append(ReconcilerAction(
            action_type="RESTORE_INK",
            object_id=obj.id,
            payload={"state": PhysicalState.STABLE_INK.value, "is_occluded": False},
        ))
        return next_twin, next_exec, actions

    # Row 14: OCCLUDED -> OBS_ABSENT (Actor departed, ink vanished: suspect external erasure)
    if current_state == PhysicalState.OCCLUDED and obs == ObservationType.OBS_ABSENT:
        obj.state = PhysicalState.UNKNOWN
        obj.is_occluded = False
        actions.append(ReconcilerAction(
            action_type="EXTERNAL_ERASURE_SUSPECTED",
            object_id=obj.id,
            payload={"state": PhysicalState.UNKNOWN.value},
        ))
        return next_twin, next_exec, actions

    # Row 15: PARTIALLY_CLEANED -> OBS_INK (Residual present)
    if current_state == PhysicalState.PARTIALLY_CLEANED and obs == ObservationType.OBS_INK:
        obj.reclean_attempts += 1
        tier = next_exec.evaluate_residual(
            event.residual_ratio or 0.04,
            clean_threshold=cfg.cleaning.clean_threshold,
            major_threshold=cfg.cleaning.residual_major_threshold,
        )
        next_exec.set_state(ExecutionState.RECLEAN_PENDING)
        if obj.id not in next_exec.reclean_queue:
            next_exec.reclean_queue.append(obj.id)
        actions.append(ReconcilerAction(
            action_type="SCHEDULE_RECLEAN",
            object_id=obj.id,
            payload={"tier": tier.value, "reclean_attempts": obj.reclean_attempts},
        ))
        return next_twin, next_exec, actions

    # Row 16: PARTIALLY_CLEANED -> OBS_ABSENT (Verification confirmed clean)
    if current_state == PhysicalState.PARTIALLY_CLEANED and obs == ObservationType.OBS_ABSENT:
        obj.state = PhysicalState.CLEANED
        if obj.id in next_exec.reclean_queue:
            next_exec.reclean_queue.remove(obj.id)
        next_exec.clear_residual()
        next_exec.set_state(ExecutionState.IDLE)
        actions.append(ReconcilerAction(
            action_type="MARK_CLEANED",
            object_id=obj.id,
            payload={"state": PhysicalState.CLEANED.value},
        ))
        return next_twin, next_exec, actions

    # Row 17: CLEANED -> OBS_INK (New ink over cleaned area)
    if current_state == PhysicalState.CLEANED and obs == ObservationType.OBS_INK:
        new_id = f"ink_{uuid.uuid4().hex[:8]}"
        pts = event.points or []
        bbox = event.bbox or (0.0, 0.0, 0.0, 0.0)
        centroid = event.centroid or (0.0, 0.0)
        new_obj = InkObject(
            id=new_id,
            state=PhysicalState.STABLE_INK,
            frame_id=CoordinateFrame.FRAME_BOARD,
            points=pts,
            bbox=bbox,
            centroid=centroid,
            confidence=event.confidence,
            color_bgr=event.color_bgr,
            area_mm2=event.area_mm2,
            first_seen=time.time(),
            last_seen=time.time(),
        )
        next_twin.add_object(new_obj)
        next_exec.set_state(ExecutionState.IDLE)
        actions.append(ReconcilerAction(
            action_type="CREATE_INK_OBJECT",
            object_id=new_id,
            payload={"state": PhysicalState.STABLE_INK.value},
        ))
        return next_twin, next_exec, actions

    # Row 18: CLEANED -> OBS_ABSENT
    if current_state == PhysicalState.CLEANED and obs == ObservationType.OBS_ABSENT:
        # Retain CLEANED until epoch roll garbage collects it
        return next_twin, next_exec, actions

    # Row 19: PERMANENT_DEFECT -> OBS_INK or OBS_ABSENT
    if current_state == PhysicalState.PERMANENT_DEFECT and obs in (ObservationType.OBS_INK, ObservationType.OBS_ABSENT):
        # Known defect; strictly retain PERMANENT_DEFECT
        return next_twin, next_exec, actions

    # Row 20: PERMANENT_DEFECT -> OBS_OCCLUDED
    if current_state == PhysicalState.PERMANENT_DEFECT and obs == ObservationType.OBS_OCCLUDED:
        obj.is_occluded = True
        return next_twin, next_exec, actions

    # Fallback
    return next_twin, next_exec, actions


class CommitReconciler:
    """Wrapper class coordinating the pure reconciler with configuration and lifecycle."""

    def __init__(
        self,
        twin_store: Optional[BoardTwinStore] = None,
        exec_store: Optional[ExecutionStore] = None,
        config: Optional[AppConfig] = None,
    ):
        self.config = config or get_config()
        self.twin_store = twin_store or BoardTwinStore(self.config)
        self.exec_store = exec_store or ExecutionStore(self.config)

    def reconcile(
        self,
        twin: BoardTwinStore,
        exec_store: ExecutionStore,
        event: ReconcilerEvent,
    ) -> Tuple[BoardTwinStore, ExecutionStore, List[ReconcilerAction]]:
        """Delegate directly to pure reducer function."""
        return reconcile(twin, exec_store, event, self.config)

    def process_event(self, event: ReconcilerEvent) -> List[ReconcilerAction]:
        """Stateful helper for runtime coordinator."""
        self.twin_store, self.exec_store, actions = self.reconcile(
            self.twin_store, self.exec_store, event
        )
        return actions
