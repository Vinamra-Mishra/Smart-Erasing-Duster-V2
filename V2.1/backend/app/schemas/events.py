from __future__ import annotations

from enum import Enum
import time
from typing import Any, Dict, List
from pydantic import BaseModel, Field
from app.schemas.ink import InkObjectDTO
from app.schemas.perception import PerceptionMetrics
from app.schemas.planner import DusterPose, ExecutionState, MissionStatus, ResidualTier


class EventType(str, Enum):
    """Event names for Reconciler, WebSocket, and Audit bus."""
    # Sensor / Perception Events
    OBSERVATION_FRAME_EVALUATED = "OBSERVATION_FRAME_EVALUATED"
    PROJECTOR_STATE_TOGGLED = "PROJECTOR_STATE_TOGGLED"
    BASELINE_EPOCH_ROLLED = "BASELINE_EPOCH_ROLLED"
    BASELINE_SECTION_REFRESHED = "BASELINE_SECTION_REFRESHED"

    # Robot Actuator Events
    DUSTER_MOVED = "DUSTER_MOVED"
    WIPE_SWEEP_EXECUTED = "WIPE_SWEEP_EXECUTED"
    VERIFICATION_WINDOW_ELAPSED = "VERIFICATION_WINDOW_ELAPSED"

    # Client / User Actions
    DRAW_STROKE = "DRAW_STROKE"
    MANUAL_ERASE = "MANUAL_ERASE"
    MOVE_DUSTER = "MOVE_DUSTER"
    DISPATCH_PLANNER = "DISPATCH_PLANNER"
    TRIGGER_SCENARIO = "TRIGGER_SCENARIO"
    CAPTURE_BASELINE = "CAPTURE_BASELINE"

    # Reconciler & State Broadcasts
    PHYSICAL_TWIN_UPDATED = "PHYSICAL_TWIN_UPDATED"
    EXECUTION_STATE_CHANGED = "EXECUTION_STATE_CHANGED"
    PLAN_GENERATED = "PLAN_GENERATED"
    RECONCILER_ACTION_DISPATCHED = "RECONCILER_ACTION_DISPATCHED"
    RECLEAN_CAP_HIT = "RECLEAN_CAP_HIT"
    ERROR_ALERT = "ERROR_ALERT"


class BusEvent(BaseModel):
    """Generic event envelope on the system bus."""
    type: EventType | str
    timestamp: float = Field(default_factory=time.time)
    payload: Dict[str, Any] = Field(default_factory=dict)


class TelemetryPayload(BaseModel):
    """High-frequency telemetry broadcast for WebSocket clients."""
    timestamp: float = Field(default_factory=time.time)
    duster_pose: DusterPose = Field(default_factory=DusterPose)
    metrics: PerceptionMetrics = Field(default_factory=PerceptionMetrics)
    residual_tier: ResidualTier = ResidualTier.TIER_1_CLEANED
    mission: MissionStatus = Field(default_factory=MissionStatus)
    active_objects_count: int = 0
    cleaned_objects_count: int = 0
    permanent_defects_count: int = 0
    evidence_score: float = 0.0
    glare: bool = False
    shadow: bool = False
    projector_likelihood: float = 0.0
    perception: Dict[str, Any] = Field(default_factory=dict)

