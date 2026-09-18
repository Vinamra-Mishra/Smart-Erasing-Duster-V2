"""Geometric utility functions for the coverage planner in FRAME_BOARD.

Provides Shapely polygon merging, safety inflation, PCA dominant-axis
orientation estimation, and coordinate transformations.
"""
from __future__ import annotations

import math
from typing import List, Sequence, Tuple, Union
import numpy as np
from shapely.geometry import MultiPolygon, Polygon, box
from shapely.ops import unary_union
import shapely.affinity

from app.schemas.ink import CoordinateFrame


def points_to_polygon(points: Sequence[Sequence[float]] | Polygon | MultiPolygon) -> Polygon | MultiPolygon:
    """Convert a sequence of (x, y) coordinate pairs or existing geometry into a valid Shapely Polygon."""
    if isinstance(points, (Polygon, MultiPolygon)):
        return points if points.is_valid else points.buffer(0)
    if len(points) < 3:
        raise ValueError(f"At least 3 vertices required for a polygon, got {len(points)}")
    poly = Polygon(points)
    if not poly.is_valid:
        poly = poly.buffer(0)
    return poly


def merge_and_inflate_polygons(
    polygons: Sequence[Polygon | MultiPolygon | Sequence[Sequence[float]]],
    buffer_mm: float = 5.0,
) -> Polygon | MultiPolygon:
    """Merge a collection of ink polygons and inflate by a safety buffer.

    Args:
        polygons: List of Shapely Polygons or coordinate vertex lists in FRAME_BOARD.
        buffer_mm: Outward inflation distance in mm to ensure edge cleaning.

    Returns:
        Unified, inflated Shapely Polygon or MultiPolygon in FRAME_BOARD.
    """
    if not polygons:
        raise ValueError("Cannot merge empty polygon list")

    converted_polygons: List[Polygon] = []
    for item in polygons:
        if isinstance(item, Polygon):
            converted_polygons.append(item if item.is_valid else item.buffer(0))
        elif isinstance(item, MultiPolygon):
            for p in item.geoms:
                converted_polygons.append(p if p.is_valid else p.buffer(0))
        else:
            p = points_to_polygon(item)
            if isinstance(p, MultiPolygon):
                for sub_p in p.geoms:
                    converted_polygons.append(sub_p if sub_p.is_valid else sub_p.buffer(0))
            else:
                converted_polygons.append(p)

    unified = unary_union(converted_polygons)
    if buffer_mm > 0.0:
        unified = unified.buffer(buffer_mm)
    return unified


def compute_pca_orientation(geom: Polygon | MultiPolygon) -> float:
    """Calculate dominant principal orientation theta (radians) of an ink polygon.

    Uses PCA on boundary and interior points to align sweep lanes along
    the stroke's natural longitudinal axis, minimizing lane count.

    Returns:
        Angle theta in radians in [-pi/2, pi/2].
    """
    if geom.is_empty:
        return 0.0

    # Extract exterior coordinates without duplicate closing vertex
    if isinstance(geom, MultiPolygon):
        coords_list: List[Tuple[float, float]] = []
        for poly in geom.geoms:
            coords_list.extend(poly.exterior.coords[:-1])
        pts = np.array(coords_list)
    else:
        pts = np.array(geom.exterior.coords[:-1])

    if len(pts) < 3:
        return 0.0

    # Center coordinates
    mean_pt = np.mean(pts, axis=0)
    centered = pts - mean_pt

    # Covariance matrix and eigen-decomposition
    cov = np.cov(centered, rowvar=False)
    if cov.shape != (2, 2) or np.isnan(cov).any():
        return 0.0

    # Clean snapping for axis-aligned geometries
    if abs(float(cov[0, 1])) < 1e-4:
        return 0.0 if cov[0, 0] >= cov[1, 1] else math.pi / 2.0

    eigenvalues, eigenvectors = np.linalg.eigh(cov)
    # Principal axis is eigenvector corresponding to largest eigenvalue
    principal_vector = eigenvectors[:, int(np.argmax(eigenvalues))]

    angle = math.atan2(float(principal_vector[1]), float(principal_vector[0]))
    # Constrain to [-pi/2, pi/2] for sweep line alignment
    if angle > math.pi / 2.0:
        angle -= math.pi
    elif angle < -math.pi / 2.0:
        angle += math.pi

    return angle


def rotate_geometry(
    geom: Polygon | MultiPolygon,
    angle_rad: float,
    origin: Tuple[float, float],
) -> Polygon | MultiPolygon:
    """Rotate a Shapely geometry around a specified origin in FRAME_BOARD."""
    angle_deg = math.degrees(angle_rad)
    return shapely.affinity.rotate(geom, angle_deg, origin=origin)
