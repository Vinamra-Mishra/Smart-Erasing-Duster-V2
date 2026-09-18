"""Smooth exterior U-turn trajectory generation for Boustrophedon sweep.

Generates outward-bulging curved U-turns that clear the ink hull boundary,
ensuring turnarounds occur strictly in clean space without smearing ink edges.
"""
from __future__ import annotations

import math
from typing import List, Tuple
from app.schemas.ink import CoordinateFrame
from app.schemas.planner import Waypoint


def generate_exterior_uturn(
    exit_pt: Tuple[float, float],
    entry_pt: Tuple[float, float],
    hull_bounds: Tuple[float, float, float, float],
    duster_width_mm: float = 162.0,
    is_right_side: bool = True,
    num_points: int = 7,
) -> List[Waypoint]:
    """Generate a smooth exterior U-turn connecting two adjacent sweep lanes.

    Args:
        exit_pt: (x, y) coordinates of exiting waypoint from lane k.
        entry_pt: (x, y) coordinates of entering waypoint into lane k+1.
        hull_bounds: (min_x, min_y, max_x, max_y) bounding box of the ink hull.
        duster_width_mm: Width of the duster actuator pad.
        is_right_side: True if turning on the right (max_x) edge, False for left (min_x).
        num_points: Number of discrete waypoints along the U-turn arc.

    Returns:
        List of Waypoint objects forming a smooth exterior curve.
    """
    min_x, min_y, max_x, max_y = hull_bounds
    x1, y1 = exit_pt
    x2, y2 = entry_pt
    mid_y = (y1 + y2) / 2.0
    half_y_span = (y2 - y1) / 2.0

    # Clearance distance: half-width of duster plus safety margin
    clearance = (duster_width_mm / 2.0) + 10.0

    if is_right_side:
        base_x = max(x1, x2, max_x)
        apex_x = base_x + clearance
        radius_x = apex_x - min(x1, x2)
    else:
        base_x = min(x1, x2, min_x)
        apex_x = base_x - clearance
        radius_x = max(x1, x2) - apex_x

    waypoints: List[Waypoint] = []
    # Parametric sweep from -pi/2 to pi/2 (or reversed if y2 < y1)
    phi_start = -math.pi / 2.0 if y2 >= y1 else math.pi / 2.0
    phi_end = math.pi / 2.0 if y2 >= y1 else -math.pi / 2.0

    for i in range(num_points):
        alpha = i / max(1, num_points - 1)
        phi = phi_start + alpha * (phi_end - phi_start)

        # Smooth elliptical transition
        cur_y = mid_y + half_y_span * math.sin(phi)
        cos_val = math.cos(phi)

        if is_right_side:
            # Bulge out towards +X
            cur_x = (x1 * (1.0 - alpha) + x2 * alpha) + radius_x * cos_val
        else:
            # Bulge out towards -X
            cur_x = (x1 * (1.0 - alpha) + x2 * alpha) - radius_x * cos_val

        # Compute heading tangent
        # dy/dphi = half_y_span * cos(phi)
        # dx/dphi = -/+ radius_x * sin(phi)
        dy = half_y_span * math.cos(phi)
        dx = -radius_x * math.sin(phi) if is_right_side else radius_x * math.sin(phi)
        heading_deg = math.degrees(math.atan2(dy, dx)) if (dx != 0 or dy != 0) else 0.0

        waypoints.append(
            Waypoint(
                x=round(cur_x, 3),
                y=round(cur_y, 3),
                theta_deg=round(heading_deg, 2),
                speed_mm_s=300.0,
                action="TRANSIT",
                frame=CoordinateFrame.FRAME_BOARD,
            )
        )

    return waypoints
