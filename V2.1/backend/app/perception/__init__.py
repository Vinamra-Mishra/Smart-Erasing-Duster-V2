"""Perception and vision processing package for Smart Erasing Duster Digital Twin."""
from __future__ import annotations

from .frames import (
    CoordinateFrame,
    Point2D,
    BoundingBox,
    Polygon2D,
    Waypoint,
    validate_frame,
)

__all__ = [
    "CoordinateFrame",
    "Point2D",
    "BoundingBox",
    "Polygon2D",
    "Waypoint",
    "validate_frame",
]
