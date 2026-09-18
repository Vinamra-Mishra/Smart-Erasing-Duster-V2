"""Dynamic virtual actuator duster model.

Loads physical dimensions dynamically from config.yaml, maintains kinematic pose
in FRAME_BOARD, and computes realistic swept contact footprints during stepping.
"""
from __future__ import annotations

import math
from typing import Tuple
from shapely.geometry import Polygon, box
import shapely.affinity

from app.core.config import get_config
from app.schemas.ink import CoordinateFrame
from app.schemas.planner import DusterPose, Waypoint


class VirtualDuster:
    """Simulated dry-erase duster actuator in FRAME_BOARD."""

    def __init__(
        self,
        width_mm: float | None = None,
        height_mm: float | None = None,
        thickness_mm: float | None = None,
    ) -> None:
        config = get_config()
        self.width_mm = width_mm if width_mm is not None else config.cleaning.duster_width_mm
        self.height_mm = height_mm if height_mm is not None else config.cleaning.duster_height_mm
        self.thickness_mm = (
            thickness_mm if thickness_mm is not None else config.cleaning.duster_thickness_mm
        )
        self.board_width = config.system.board_width_mm
        self.board_height = config.system.board_height_mm

        # Kinematic state
        self.x = 0.0
        self.y = 0.0
        self.theta_deg = 0.0
        self.velocity_mm_s = 0.0
        self.is_contacting = False

        self.reset_to_home()

    def reset_to_home(self) -> None:
        """Reset actuator to dynamic Home Dock (w/2, H - h/2, 0.0)."""
        self.x = round(self.width_mm / 2.0, 4)
        self.y = round(self.board_height - (self.height_mm / 2.0), 4)
        self.theta_deg = 0.0
        self.velocity_mm_s = 0.0
        self.is_contacting = False

    def get_pose(self) -> DusterPose:
        """Return current actuator pose DTO."""
        return DusterPose(
            x=self.x,
            y=self.y,
            theta_deg=self.theta_deg,
            is_contacting=self.is_contacting,
            velocity_mm_s=self.velocity_mm_s,
            frame=CoordinateFrame.FRAME_BOARD,
        )

    def get_footprint_polygon(
        self,
        x: float | None = None,
        y: float | None = None,
        theta_deg: float | None = None,
    ) -> Polygon:
        """Compute the rectangular wiping contact area in FRAME_BOARD.

        Centered at (x, y) and rotated by theta_deg.
        """
        px = self.x if x is None else x
        py = self.y if y is None else y
        ptheta = self.theta_deg if theta_deg is None else theta_deg

        hw = self.width_mm / 2.0
        hh = self.height_mm / 2.0
        base_box = box(px - hw, py - hh, px + hw, py + hh)

        if abs(ptheta) > 1e-4:
            return shapely.affinity.rotate(base_box, ptheta, origin=(px, py))
        return base_box

    def step(
        self,
        dt_sec: float,
        target: Waypoint | None = None,
    ) -> Tuple[DusterPose, Polygon | None]:
        """Advance actuator kinematics towards target waypoint.

        Returns:
            Tuple of (updated DusterPose, swept footprint polygon during dt).
        """
        if dt_sec <= 0.0 or target is None:
            self.velocity_mm_s = 0.0
            return (self.get_pose(), None)

        start_footprint = self.get_footprint_polygon()

        dx = target.x - self.x
        dy = target.y - self.y
        dist = math.hypot(dx, dy)

        speed = max(10.0, target.speed_mm_s)
        max_dist_step = speed * dt_sec

        if dist <= max_dist_step or dist < 1.0:
            # Reached waypoint
            self.x = target.x
            self.y = target.y
            self.theta_deg = target.theta_deg
            self.velocity_mm_s = speed
        else:
            fraction = max_dist_step / dist
            self.x += dx * fraction
            self.y += dy * fraction
            self.theta_deg = math.degrees(math.atan2(dy, dx))
            self.velocity_mm_s = speed

        self.is_contacting = (target.action == "WIPE")
        end_footprint = self.get_footprint_polygon()

        # Swept region is the union / convex hull of footprints at start and end
        if self.is_contacting:
            swept_poly = start_footprint.union(end_footprint).convex_hull
        else:
            swept_poly = None

        return (self.get_pose(), swept_poly)
