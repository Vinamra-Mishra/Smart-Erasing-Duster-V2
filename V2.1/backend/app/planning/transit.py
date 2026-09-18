"""Continuous end-to-end mission transit planning in FRAME_BOARD.

Plans complete mission trajectory from the dynamically computed Home Dock
(w/2, H - h/2) to target ink entries, between clusters, and returning home.
"""
from __future__ import annotations

import math
from typing import List, Sequence, Tuple
from shapely.geometry import MultiPolygon, Polygon

from app.core.config import get_config
from app.planning.coverage import (
    _calculate_trajectory_length,
    _estimate_duration,
    plan_boustrophedon_coverage,
)
from app.planning.ordering import optimize_cluster_sequence
from app.schemas.ink import CoordinateFrame
from app.schemas.planner import CleaningPlan, Waypoint


def plan_full_mission(
    target_clusters: Sequence[Tuple[str, Polygon | MultiPolygon]],
    lane_overlap: float | None = None,
    duster_width_mm: float | None = None,
    duster_height_mm: float | None = None,
    board_height_mm: float | None = None,
) -> CleaningPlan:
    """Generate a continuous mission trajectory starting and ending at Home Dock.

    Full sequence:
        Home Dock -> Transit -> Target Sweep -> Inter-Cluster Transit -> Return Home

    Args:
        target_clusters: List of (target_id, target_geometry) tuples in FRAME_BOARD.
        lane_overlap: Fractional lane overlap (default from config: 0.28).
        duster_width_mm: Tool width (default from config: 162.0).
        duster_height_mm: Tool height (default from config: 58.0).
        board_height_mm: Whiteboard height (default from config: 700.0).

    Returns:
        Complete continuous CleaningPlan.
    """
    config = get_config()
    tool_w = duster_width_mm if duster_width_mm is not None else config.cleaning.duster_width_mm
    tool_h = duster_height_mm if duster_height_mm is not None else config.cleaning.duster_height_mm
    board_h = board_height_mm if board_height_mm is not None else config.system.board_height_mm
    overlap = lane_overlap if lane_overlap is not None else config.cleaning.lane_overlap

    # Dynamic Home Dock: (w/2, H - h/2, 0.0)
    x_home = round(tool_w / 2.0, 4)
    y_home = round(board_h - (tool_h / 2.0), 4)
    home_pt = (x_home, y_home)

    all_waypoints: List[Waypoint] = []
    # Initial Home Dock waypoint
    all_waypoints.append(
        Waypoint(
            x=x_home,
            y=y_home,
            theta_deg=0.0,
            speed_mm_s=0.0,
            action="DOCK",
            frame=CoordinateFrame.FRAME_BOARD,
        )
    )

    if not target_clusters:
        return CleaningPlan(
            target_object_ids=[],
            waypoints=all_waypoints,
            total_length_mm=0.0,
            estimated_duration_s=0.0,
            lane_overlap=overlap,
        )

    # Order clusters starting from home dock
    ordered_clusters = optimize_cluster_sequence(target_clusters, home_pt)
    target_ids = [cid for cid, _ in ordered_clusters]

    for cid, geom in ordered_clusters:
        # Generate Boustrophedon sweep plan for this cluster
        cluster_plan = plan_boustrophedon_coverage(
            polygons=[geom],
            lane_overlap=overlap,
            duster_width_mm=tool_w,
            duster_height_mm=tool_h,
            target_object_ids=[cid],
        )
        if not cluster_plan.waypoints:
            continue

        first_wipe_wp = cluster_plan.waypoints[0]
        prev_wp = all_waypoints[-1]

        # Insert transit waypoints to target entry
        transit_wps = _generate_linear_transit(
            start_pos=(prev_wp.x, prev_wp.y),
            end_pos=(first_wipe_wp.x, first_wipe_wp.y),
            target_heading=first_wipe_wp.theta_deg,
            speed_mm_s=570.0,
        )
        all_waypoints.extend(transit_wps)

        # Append cluster coverage waypoints
        all_waypoints.extend(cluster_plan.waypoints)

    # Final transit return to Home Dock
    last_wipe_wp = all_waypoints[-1]
    return_transit = _generate_linear_transit(
        start_pos=(last_wipe_wp.x, last_wipe_wp.y),
        end_pos=home_pt,
        target_heading=0.0,
        speed_mm_s=570.0,
    )
    all_waypoints.extend(return_transit)

    # Final docked waypoint
    all_waypoints.append(
        Waypoint(
            x=x_home,
            y=y_home,
            theta_deg=0.0,
            speed_mm_s=0.0,
            action="DOCK",
            frame=CoordinateFrame.FRAME_BOARD,
        )
    )

    total_len = _calculate_trajectory_length(all_waypoints)
    total_duration = _estimate_duration(all_waypoints)

    return CleaningPlan(
        target_object_ids=target_ids,
        waypoints=all_waypoints,
        total_length_mm=round(total_len, 2),
        estimated_duration_s=round(total_duration, 2),
        lane_overlap=overlap,
    )


def _generate_linear_transit(
    start_pos: Tuple[float, float],
    end_pos: Tuple[float, float],
    target_heading: float,
    speed_mm_s: float = 150.0,
    min_transit_step_mm: float = 100.0,
) -> List[Waypoint]:
    """Generate intermediate transit waypoints between two positions."""
    dx = end_pos[0] - start_pos[0]
    dy = end_pos[1] - start_pos[1]
    distance = math.hypot(dx, dy)

    if distance < 1.0:
        return []

    heading_deg = math.degrees(math.atan2(dy, dx))
    num_steps = max(1, int(distance / min_transit_step_mm))
    waypoints: List[Waypoint] = []

    for step in range(1, num_steps + 1):
        fraction = step / float(num_steps)
        wx = start_pos[0] + dx * fraction
        wy = start_pos[1] + dy * fraction
        # Blend heading smoothly towards target heading on the final step
        wp_heading = heading_deg if step < num_steps else target_heading

        waypoints.append(
            Waypoint(
                x=round(wx, 3),
                y=round(wy, 3),
                theta_deg=round(wp_heading, 2),
                speed_mm_s=speed_mm_s,
                action="TRANSIT",
                frame=CoordinateFrame.FRAME_BOARD,
            )
        )

    return waypoints
