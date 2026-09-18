from datetime import datetime
from enum import Enum
from typing import List, Optional
import uuid
from pydantic import BaseModel, Field
from app.schemas.ink import CoordinateFrame


class ExecutionState(str, Enum):
    """Robot actuator and mission planning states."""
    IDLE = "IDLE"
    PLANNING = "PLANNING"
    CLEANING_ACTIVE = "CLEANING_ACTIVE"
    VERIFYING = "VERIFYING"
    RECLEAN_PENDING = "RECLEAN_PENDING"
    STOPPED = "STOPPED"
    SAFETY_LOCK = "SAFETY_LOCK"


class ResidualTier(str, Enum):
    """Derived residual severity tiers governing re-cleaning strategy."""
    TIER_1_CLEANED = "TIER_1_CLEANED"            # residual <= clean_threshold (<= 1%)
    TIER_2_FINE_RESIDUAL = "TIER_2_FINE_RESIDUAL"  # clean_threshold < residual < residual_major_threshold (1%-5%)
    TIER_3_MAJOR_RESIDUAL = "TIER_3_MAJOR_RESIDUAL"# residual >= residual_major_threshold (>= 5%)


class DusterPose(BaseModel):
    """Actuator pose in FRAME_BOARD coordinates."""
    x: float = 81.0
    y: float = 671.0
    theta_deg: float = 0.0
    theta: float = 0.0
    is_contacting: bool = False
    velocity_mm_s: float = 0.0
    frame: CoordinateFrame = CoordinateFrame.FRAME_BOARD


class Waypoint(BaseModel):
    """Single trajectory waypoint in FRAME_BOARD."""
    x: float
    y: float
    theta_deg: float = 0.0
    theta: float = 0.0
    speed_mm_s: float = 100.0
    v: float = 100.0
    action: str = "MOVE"  # "TRANSIT", "WIPE", "DOCK"
    segment_type: str = "sweep"
    frame: CoordinateFrame = CoordinateFrame.FRAME_BOARD


class CleaningPlan(BaseModel):
    """Complete planned mission trajectory."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    target_object_ids: List[str] = Field(default_factory=list)
    waypoints: List[Waypoint] = Field(default_factory=list)
    total_length_mm: float = 0.0
    estimated_duration_s: float = 0.0
    estimated_duration_sec: float = 0.0
    lane_overlap: float = 0.28
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())



class MissionStatus(BaseModel):
    """Mission execution progress telemetry."""
    state: ExecutionState = ExecutionState.IDLE
    elapsed_sec: float = 0.0
    max_duration_sec: float = 180.0
    active_waypoint_index: int = 0
    total_waypoints: int = 0
    current_target_id: str | None = None
