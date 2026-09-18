"""Boustrophedon sweep coverage planner with configurable lane overlap.

Generates back-and-forth sweep lines aligned with dominant stroke orientation,
connected by smooth exterior U-turns in clean space outside the ink hull.
"""
from __future__ import annotations

import math
from typing import List, Sequence, Tuple
from shapely.geometry import GeometryCollection, LineString, MultiLineString, MultiPolygon, Polygon
import shapely.affinity

from app.core.config import get_config
from app.planning.geometry import (
    compute_pca_orientation,
    merge_and_inflate_polygons,
)
from app.planning.smoothing import generate_exterior_uturn
from app.schemas.ink import CoordinateFrame
from app.schemas.planner import CleaningPlan, Waypoint


def plan_boustrophedon_coverage(
    polygons: Sequence[Polygon | Sequence[Sequence[float]]],
    lane_overlap: float | None = None,
    duster_width_mm: float | None = None,
    duster_height_mm: float | None = None,
    target_object_ids: Sequence[str] | None = None,
    use_pca_alignment: bool = True,
) -> CleaningPlan:
    """Generate a Boustrophedon coverage plan for the given target ink geometries.

    Args:
        polygons: Target ink polygons in FRAME_BOARD.
        lane_overlap: Fractional lane overlap in [0.0, 0.9] (default from config: 0.28).
        duster_width_mm: Tool width in mm (default from config: 162.0).
        duster_height_mm: Tool height in mm (default from config: 58.0).
        target_object_ids: Optional list of target object IDs being cleaned.
        use_pca_alignment: If True, aligns sweep lanes with PCA dominant axis.

    Returns:
        CleaningPlan containing waypoints, total length, and estimated duration.
    """
    config = get_config()
    overlap = lane_overlap if lane_overlap is not None else config.cleaning.lane_overlap
    tool_w = duster_width_mm if duster_width_mm is not None else config.cleaning.duster_width_mm
    tool_h = duster_height_mm if duster_height_mm is not None else config.cleaning.duster_height_mm

    if not (0.0 <= overlap < 1.0):
        raise ValueError(f"Invalid lane overlap {overlap}, must be in [0.0, 1.0)")

    # Effective lane advance step
    delta_y_lane = tool_h * (1.0 - overlap)

    # Merge and inflate targets
    unified_hull = merge_and_inflate_polygons(polygons, buffer_mm=5.0)
    if unified_hull.is_empty:
        return CleaningPlan(lane_overlap=overlap)

    # Orientation alignment
    theta_pca = compute_pca_orientation(unified_hull) if use_pca_alignment else 0.0
    centroid = (unified_hull.centroid.x, unified_hull.centroid.y)

    # Rotate into aligned frame
    aligned_geom = shapely.affinity.rotate(
        unified_hull, -math.degrees(theta_pca), origin=centroid
    )
    min_x, min_y, max_x, max_y = aligned_geom.bounds
    hull_bounds = (min_x, min_y, max_x, max_y)

    # Calculate sweep lanes along Y
    sweep_y_coords: List[float] = []
    cur_y = min_y + (delta_y_lane / 2.0)
    while cur_y <= max_y + (delta_y_lane * 0.25):
        sweep_y_coords.append(cur_y)
        cur_y += delta_y_lane

    if not sweep_y_coords:
        sweep_y_coords.append((min_y + max_y) / 2.0)

    # Generate lane segments
    raw_lanes: List[List[Tuple[float, float]]] = []
    x_pad = 10.0

    for y_val in sweep_y_coords:
        scan_line = LineString([(min_x - x_pad, y_val), (max_x + x_pad, y_val)])
        intersection = aligned_geom.intersection(scan_line)

        segments = _extract_line_segments(intersection)
        if segments:
            # Span full extent of intersection for robust cleaning
            lane_start_x = min(seg[0][0] for seg in segments)
            lane_end_x = max(seg[1][0] for seg in segments)
            raw_lanes.append([(lane_start_x, y_val), (lane_end_x, y_val)])
        else:
            # Fallback to bounding box center slice if no interior intersection
            raw_lanes.append([(min_x, y_val), (max_x, y_val)])

    # Construct ordered waypoints with Boustrophedon directions and exterior U-turns
    aligned_waypoints = _build_boustrophedon_path(raw_lanes, hull_bounds, tool_w)

    # Rotate all waypoints back to FRAME_BOARD
    board_waypoints = _rotate_waypoints_to_board(aligned_waypoints, theta_pca, centroid)

    # Calculate total length and duration
    total_length = _calculate_trajectory_length(board_waypoints)
    duration = _estimate_duration(board_waypoints)

    return CleaningPlan(
        target_object_ids=list(target_object_ids or []),
        waypoints=board_waypoints,
        total_length_mm=round(total_length, 2),
        estimated_duration_s=round(duration, 2),
        lane_overlap=overlap,
    )


def _extract_line_segments(geom: any) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """Extract line segments from a Shapely intersection result."""
    segments: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
    if geom.is_empty:
        return segments
    if isinstance(geom, LineString):
        coords = list(geom.coords)
        if len(coords) >= 2:
            segments.append((coords[0], coords[-1]))
    elif isinstance(geom, MultiLineString):
        for line in geom.geoms:
            coords = list(line.coords)
            if len(coords) >= 2:
                segments.append((coords[0], coords[-1]))
    elif isinstance(geom, GeometryCollection):
        for sub_geom in geom.geoms:
            segments.extend(_extract_line_segments(sub_geom))
    return segments


def _build_boustrophedon_path(
    raw_lanes: List[List[Tuple[float, float]]],
    hull_bounds: Tuple[float, float, float, float],
    duster_width_mm: float,
) -> List[Waypoint]:
    """Assemble alternating sweep lanes and connecting smooth U-turns."""
    waypoints: List[Waypoint] = []
    for idx, lane in enumerate(raw_lanes):
        p_left, p_right = lane[0], lane[1]
        # Even: left-to-right; Odd: right-to-left
        is_even = (idx % 2 == 0)
        start_pt = p_left if is_even else p_right
        end_pt = p_right if is_even else p_left
        heading = 0.0 if is_even else 180.0

        # Add connecting U-turn if transitioning from previous lane
        if idx > 0:
            prev_exit = waypoints[-1]
            uturn_pts = generate_exterior_uturn(
                exit_pt=(prev_exit.x, prev_exit.y),
                entry_pt=start_pt,
                hull_bounds=hull_bounds,
                duster_width_mm=duster_width_mm,
                is_right_side=(not is_even),  # Exited on right if previous was even
                num_points=7,
            )
            waypoints.extend(uturn_pts)

        # Add sweep start and end
        waypoints.append(
            Waypoint(
                x=round(start_pt[0], 3),
                y=round(start_pt[1], 3),
                theta_deg=round(heading, 2),
                speed_mm_s=390.0,
                action="WIPE",
                frame=CoordinateFrame.FRAME_BOARD,
            )
        )
        waypoints.append(
            Waypoint(
                x=round(end_pt[0], 3),
                y=round(end_pt[1], 3),
                theta_deg=round(heading, 2),
                speed_mm_s=390.0,
                action="WIPE",
                frame=CoordinateFrame.FRAME_BOARD,
            )
        )
    return waypoints


def _rotate_waypoints_to_board(
    waypoints: List[Waypoint],
    theta_rad: float,
    origin: Tuple[float, float],
) -> List[Waypoint]:
    """Rotate waypoints from PCA-aligned frame back to FRAME_BOARD coordinates."""
    if abs(theta_rad) < 1e-6:
        return waypoints

    cos_t = math.cos(theta_rad)
    sin_t = math.sin(theta_rad)
    ox, oy = origin
    rotated: List[Waypoint] = []

    for wp in waypoints:
        dx = wp.x - ox
        dy = wp.y - oy
        new_x = ox + dx * cos_t - dy * sin_t
        new_y = oy + dx * sin_t + dy * cos_t
        new_theta = (wp.theta_deg + math.degrees(theta_rad)) % 360.0

        rotated.append(
            Waypoint(
                x=round(new_x, 3),
                y=round(new_y, 3),
                theta_deg=round(new_theta, 2),
                speed_mm_s=wp.speed_mm_s,
                action=wp.action,
                frame=CoordinateFrame.FRAME_BOARD,
            )
        )
    return rotated


def _calculate_trajectory_length(waypoints: List[Waypoint]) -> float:
    """Calculate cumulative path length across all waypoints in mm."""
    if len(waypoints) < 2:
        return 0.0
    total = 0.0
    for i in range(len(waypoints) - 1):
        dx = waypoints[i + 1].x - waypoints[i].x
        dy = waypoints[i + 1].y - waypoints[i].y
        total += math.sqrt(dx * dx + dy * dy)
    return total


def _estimate_duration(waypoints: List[Waypoint]) -> float:
    """Estimate total execution duration based on waypoint speeds."""
    if len(waypoints) < 2:
        return 0.0
    duration = 0.0
    for i in range(len(waypoints) - 1):
        dx = waypoints[i + 1].x - waypoints[i].x
        dy = waypoints[i + 1].y - waypoints[i].y
        dist = math.sqrt(dx * dx + dy * dy)
        speed = max(10.0, waypoints[i + 1].speed_mm_s)
        duration += dist / speed
    return duration
