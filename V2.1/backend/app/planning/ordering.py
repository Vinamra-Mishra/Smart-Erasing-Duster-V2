"""Multi-cluster traversal sequence optimizer for coverage planning.

Orders disconnected target ink clusters using nearest-neighbor TSP heuristics
starting from the dynamic Home Dock to minimize deadhead transit distance.
"""
from __future__ import annotations

import math
from typing import List, Sequence, Tuple
from shapely.geometry import MultiPolygon, Polygon


def optimize_cluster_sequence(
    clusters: Sequence[Tuple[str, Polygon | MultiPolygon]],
    start_pos: Tuple[float, float],
) -> List[Tuple[str, Polygon | MultiPolygon]]:
    """Order target clusters to minimize transit distance from start_pos.

    Args:
        clusters: List of tuples (cluster_id, polygon_geometry).
        start_pos: Initial actuator position (e.g. Home Dock (x_home, y_home)).

    Returns:
        Ordered list of (cluster_id, polygon_geometry) tuples.
    """
    if len(clusters) <= 1:
        return list(clusters)

    remaining = list(clusters)
    ordered: List[Tuple[str, Polygon | MultiPolygon]] = []
    current_pos = start_pos

    while remaining:
        # Find closest cluster centroid to current position
        best_idx = 0
        min_dist = float("inf")

        for idx, (_, geom) in enumerate(remaining):
            cx, cy = geom.centroid.x, geom.centroid.y
            dist = math.hypot(cx - current_pos[0], cy - current_pos[1])
            if dist < min_dist:
                min_dist = dist
                best_idx = idx

        chosen = remaining.pop(best_idx)
        ordered.append(chosen)
        current_pos = (chosen[1].centroid.x, chosen[1].centroid.y)

    return ordered
