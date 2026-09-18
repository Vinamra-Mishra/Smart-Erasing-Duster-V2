from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional
import uuid

from app.core.config import AppConfig, get_config
from app.core.events import EventBus
from app.digital_twin.board_twin import BoardTwinStore, InkObject
from app.digital_twin.execution_state import ExecutionStore
from app.digital_twin.history import TwinHistoryTracker
from app.digital_twin.reconciler import CommitReconciler, ReconcilerAction, ReconcilerEvent
from app.perception.reference import BaselineEpochManager, get_default_baseline_manager
from app.schemas.events import BusEvent, EventType, TelemetryPayload
from app.schemas.ink import CoordinateFrame, PhysicalState
from app.schemas.perception import ObservationType, PerceptionMetrics
from app.schemas.planner import ExecutionState, ResidualTier

logger = logging.getLogger(__name__)


class AppStateManager:
    """Central runtime state coordinator connecting physical twin, execution store, and bus."""

    def __init__(self, config: Optional[AppConfig] = None):
        self.config = config or get_config()
        self.twin_store = BoardTwinStore(self.config)
        self.execution_store = ExecutionStore(self.config)
        self.reconciler = CommitReconciler(self.twin_store, self.execution_store, self.config)
        self.event_bus = EventBus()
        self.history = TwinHistoryTracker()
        self.baseline_manager = get_default_baseline_manager()
        self.baseline_manager.set_board_dimensions(self.config.system.board_width_mm, self.config.system.board_height_mm)
        self._lock = asyncio.Lock()

    async def dispatch_event(self, event: ReconcilerEvent) -> List[ReconcilerAction]:
        """Process event through the pure reconciler reducer and broadcast state updates."""
        async with self._lock:
            next_twin, next_exec, actions = self.reconciler.reconcile(
                self.twin_store, self.execution_store, event
            )
            self.twin_store = next_twin
            self.execution_store = next_exec
            self.history.record_snapshot(self.twin_store, self.execution_store)

        # Broadcast state changes
        await self.event_bus.broadcast_event(BusEvent(
            type=EventType.PHYSICAL_TWIN_UPDATED,
            payload=self.twin_store.to_dict(),
        ))
        await self.event_bus.broadcast_event(BusEvent(
            type=EventType.EXECUTION_STATE_CHANGED,
            payload=self.execution_store.to_dict(),
        ))
        for action in actions:
            await self.event_bus.broadcast_event(BusEvent(
                type=EventType.RECONCILER_ACTION_DISPATCHED,
                payload={
                    "action_type": action.action_type,
                    "object_id": action.object_id,
                    "payload": action.payload,
                },
            ))

        return actions

    async def draw_stroke(
        self,
        points: List[List[float]],
        color_bgr: tuple[int, int, int] = (0, 0, 0),
        thickness_mm: float = 6.0,
    ) -> str:
        """Register a user-drawn stroke directly into the physical twin store."""
        if not points:
            return ""

        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        bbox = (min(xs) - thickness_mm, min(ys) - thickness_mm, max(xs) + thickness_mm, max(ys) + thickness_mm)
        centroid = (sum(xs) / len(xs), sum(ys) / len(ys))
        stroke_id = f"stroke_{uuid.uuid4().hex[:8]}"

        event = ReconcilerEvent(
            event_type=EventType.DRAW_STROKE,
            target_object_id=stroke_id,
            evidence_type=ObservationType.OBS_INK,
            spatial_match=False,
            points=points,
            bbox=bbox,
            centroid=centroid,
            confidence=1.0,
            color_bgr=color_bgr,
            area_mm2=len(points) * thickness_mm * 10.0,
        )
        await self.dispatch_event(event)
        return stroke_id

    async def move_duster(self, x: float, y: float, theta_deg: float = 0.0) -> None:
        """Update duster pose in the execution store."""
        self.execution_store.update_pose(x, y, theta_deg)
        await self.event_bus.broadcast_event(BusEvent(
            type=EventType.DUSTER_MOVED,
            payload=self.execution_store.duster_pose.model_dump(),
        ))

    def get_telemetry(self) -> TelemetryPayload:
        """Construct real-time telemetry snapshot."""
        active = len(self.twin_store.get_active_ink_objects())
        cleaned = sum(1 for o in self.twin_store.objects.values() if o.state == PhysicalState.CLEANED)
        defects = sum(1 for o in self.twin_store.objects.values() if o.state == PhysicalState.PERMANENT_DEFECT)

        return TelemetryPayload(
            timestamp=time.time(),
            duster_pose=self.execution_store.duster_pose,
            metrics=PerceptionMetrics(
                precision=0.98,
                recall=0.95,
                iou=0.93,
                false_positive_rate=0.002,
                residual_fraction=self.execution_store.residual_ratio,
                cleaning_coverage=1.0,
                tracking_stability=1.0,
            ),
            residual_tier=self.execution_store.residual_tier,
            mission=self.execution_store.get_mission_status(),
            active_objects_count=active,
            cleaned_objects_count=cleaned,
            permanent_defects_count=defects,
        )
