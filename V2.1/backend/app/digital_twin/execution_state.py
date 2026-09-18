from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any, Dict, List, Optional
from app.core.config import AppConfig, get_config
from app.schemas.ink import CoordinateFrame
from app.schemas.planner import CleaningPlan, DusterPose, ExecutionState, MissionStatus, ResidualTier


class ExecutionStore:
    """Authoritative Execution Action Store modeling robot state, trajectory, and triggers.

    INVARIANT:
        RESIDUAL_DETECTED is strictly an execution trigger flag in
        execution_state.py, NEVER a physical state in board_twin.py.
    """

    def __init__(self, config: Optional[AppConfig] = None):
        self.config = config or get_config()
        self.state: ExecutionState = ExecutionState.IDLE
        x_home, y_home, theta_home = self.config.get_home_dock()

        self.duster_pose: DusterPose = DusterPose(
            x=x_home,
            y=y_home,
            theta_deg=theta_home,
            is_contacting=False,
            velocity_mm_s=0.0,
            frame=CoordinateFrame.FRAME_BOARD,
        )

        # Ephemeral residual trigger state
        self.residual_detected: bool = False
        self.residual_ratio: float = 0.0
        self.residual_tier: ResidualTier = ResidualTier.TIER_1_CLEANED

        # Mission and planner tracking
        self.reclean_queue: List[str] = []
        self.current_plan: Optional[CleaningPlan] = None
        self.active_waypoint_index: int = 0
        self.mission_start_time: float = 0.0
        self.mission_elapsed_sec: float = 0.0
        self.max_duration_sec: float = self.config.cleaning.max_mission_duration_sec
        self.safety_lock_reason: Optional[str] = None
        self.current_target_id: Optional[str] = None

    def set_state(self, new_state: ExecutionState) -> None:
        self.state = new_state
        if new_state == ExecutionState.CLEANING_ACTIVE and self.mission_start_time == 0.0:
            self.mission_start_time = time.time()
        elif new_state == ExecutionState.IDLE:
            self.mission_start_time = 0.0
            self.mission_elapsed_sec = 0.0

    def update_pose(
        self,
        x: float,
        y: float,
        theta_deg: float = 0.0,
        is_contacting: bool = False,
        velocity_mm_s: float = 0.0,
    ) -> None:
        self.duster_pose.x = x
        self.duster_pose.y = y
        self.duster_pose.theta_deg = theta_deg
        self.duster_pose.is_contacting = is_contacting
        self.duster_pose.velocity_mm_s = velocity_mm_s

    def reset_to_home(self) -> None:
        """Reset actuator to dynamic Home Dock (w/2, H - h/2, 0.0)."""
        x_home, y_home, theta_home = self.config.get_home_dock()
        self.duster_pose.x = x_home
        self.duster_pose.y = y_home
        self.duster_pose.theta_deg = theta_home
        self.duster_pose.is_contacting = False
        self.duster_pose.velocity_mm_s = 0.0

    def evaluate_residual(
        self,
        residual_fraction: float,
        clean_threshold: Optional[float] = None,
        major_threshold: Optional[float] = None,
    ) -> ResidualTier:
        """Evaluate residual against configured thresholds and set execution flags."""
        c_thresh = clean_threshold if clean_threshold is not None else self.config.cleaning.clean_threshold
        m_thresh = major_threshold if major_threshold is not None else self.config.cleaning.residual_major_threshold

        self.residual_ratio = residual_fraction

        if residual_fraction <= c_thresh:
            self.residual_detected = False
            self.residual_tier = ResidualTier.TIER_1_CLEANED
        elif residual_fraction < m_thresh:
            self.residual_detected = True
            self.residual_tier = ResidualTier.TIER_2_FINE_RESIDUAL
        else:
            self.residual_detected = True
            self.residual_tier = ResidualTier.TIER_3_MAJOR_RESIDUAL

        return self.residual_tier

    def clear_residual(self) -> None:
        self.residual_detected = False
        self.residual_ratio = 0.0
        self.residual_tier = ResidualTier.TIER_1_CLEANED

    def check_safety_timeout(self) -> bool:
        """Trip safety lock if mission duration exceeds cap."""
        if self.mission_start_time > 0.0:
            self.mission_elapsed_sec = time.time() - self.mission_start_time
            if self.mission_elapsed_sec > self.max_duration_sec:
                self.state = ExecutionState.SAFETY_LOCK
                self.safety_lock_reason = f"Max mission duration exceeded ({self.mission_elapsed_sec:.1f}s > {self.max_duration_sec}s)"
                return True
        return False

    def clone(self) -> ExecutionStore:
        new_store = ExecutionStore(self.config)
        new_store.state = self.state
        new_store.duster_pose = DusterPose(**self.duster_pose.model_dump())
        new_store.residual_detected = self.residual_detected
        new_store.residual_ratio = self.residual_ratio
        new_store.residual_tier = self.residual_tier
        new_store.reclean_queue = list(self.reclean_queue)
        new_store.current_plan = self.current_plan
        new_store.active_waypoint_index = self.active_waypoint_index
        new_store.mission_start_time = self.mission_start_time
        new_store.mission_elapsed_sec = self.mission_elapsed_sec
        new_store.max_duration_sec = self.max_duration_sec
        new_store.safety_lock_reason = self.safety_lock_reason
        new_store.current_target_id = self.current_target_id
        return new_store

    def get_mission_status(self) -> MissionStatus:
        total = len(self.current_plan.waypoints) if self.current_plan else 0
        return MissionStatus(
            state=self.state,
            elapsed_sec=self.mission_elapsed_sec,
            max_duration_sec=self.max_duration_sec,
            active_waypoint_index=self.active_waypoint_index,
            total_waypoints=total,
            current_target_id=self.current_target_id,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "duster_pose": self.duster_pose.model_dump(),
            "residual_detected": self.residual_detected,
            "residual_ratio": self.residual_ratio,
            "residual_tier": self.residual_tier.value,
            "reclean_queue": self.reclean_queue,
            "mission": self.get_mission_status().model_dump(),
            "safety_lock_reason": self.safety_lock_reason,
        }
