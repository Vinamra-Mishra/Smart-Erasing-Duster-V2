"""Coordinate frame hierarchy and spatial geometry representations.

Explicitly manages transformations and metadata tags across:
- FRAME_CAMERA: Raw sensor pixels (u, v) in [0, W_cam] x [0, H_cam]
- FRAME_BOARD: Rectified physical whiteboard coordinates (x, y) in mm
- FRAME_DUSTER: Body-fixed actuator tool coordinates (-w/2..w/2, -h/2..h/2)
- FRAME_PATH: Ordered trajectory waypoints in FRAME_BOARD
"""
from __future__ import annotations

from enum import Enum
from typing import Any, List, Sequence, Tuple
from pydantic import BaseModel, Field


class CoordinateFrame(str, Enum):
    """Explicit coordinate reference frames in the digital twin pipeline."""
    FRAME_CAMERA = "FRAME_CAMERA"
    FRAME_BOARD = "FRAME_BOARD"
    FRAME_DUSTER = "FRAME_DUSTER"
    FRAME_PATH = "FRAME_PATH"


class FrameMismatchError(ValueError):
    """Raised when an operation attempts to combine geometries from different frames."""
    pass


class Point2D(BaseModel):
    """2D spatial point tagged with an explicit coordinate frame."""
    x: float
    y: float
    frame: CoordinateFrame = CoordinateFrame.FRAME_BOARD

    def as_tuple(self) -> Tuple[float, float]:
        return (self.x, self.y)

    def distance_to(self, other: Point2D) -> float:
        validate_frame(self, other.frame)
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2) ** 0.5


class BoundingBox(BaseModel):
    """Axis-aligned bounding box tagged with an explicit coordinate frame."""
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    frame: CoordinateFrame = CoordinateFrame.FRAME_BOARD

    @property
    def width(self) -> float:
        return max(0.0, self.x_max - self.x_min)

    @property
    def height(self) -> float:
        return max(0.0, self.y_max - self.y_min)

    @property
    def min_x(self) -> float:
        return self.x_min

    @property
    def min_y(self) -> float:
        return self.y_min

    @property
    def max_x(self) -> float:
        return self.x_max

    @property
    def max_y(self) -> float:
        return self.y_max

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def centroid(self) -> Tuple[float, float]:
        return ((self.x_min + self.x_max) / 2.0, (self.y_min + self.y_max) / 2.0)

    def to_tlbr(self) -> Tuple[float, float, float, float]:
        return (self.x_min, self.y_min, self.x_max, self.y_max)

    def to_xywh(self) -> Tuple[float, float, float, float]:
        return (self.x_min, self.y_min, self.width, self.height)

    def intersection_area(self, other: BoundingBox) -> float:
        validate_frame(self, other.frame)
        ix_min = max(self.x_min, other.x_min)
        iy_min = max(self.y_min, other.y_min)
        ix_max = min(self.x_max, other.x_max)
        iy_max = min(self.y_max, other.y_max)
        if ix_max <= ix_min or iy_max <= iy_min:
            return 0.0
        return (ix_max - ix_min) * (iy_max - iy_min)

    def iou(self, other: BoundingBox) -> float:
        validate_frame(self, other.frame)
        intersection = self.intersection_area(other)
        union = self.area + other.area - intersection
        if union <= 0.0:
            return 0.0
        return intersection / union


class Polygon2D(BaseModel):
    """2D polygon boundary tagged with an explicit coordinate frame."""
    points: List[Tuple[float, float]]
    holes: List[List[Tuple[float, float]]] = Field(default_factory=list)
    frame: CoordinateFrame = CoordinateFrame.FRAME_BOARD

    @property
    def vertex_count(self) -> int:
        return len(self.points)

    def compute_centroid(self) -> Tuple[float, float]:
        if not self.points:
            return (0.0, 0.0)
        mean_x = sum(p[0] for p in self.points) / len(self.points)
        mean_y = sum(p[1] for p in self.points) / len(self.points)
        return (round(mean_x, 4), round(mean_y, 4))

    def bounding_box(self) -> BoundingBox:
        if not self.points:
            return BoundingBox(x_min=0.0, y_min=0.0, x_max=0.0, y_max=0.0, frame=self.frame)
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        return BoundingBox(
            x_min=min(xs),
            y_min=min(ys),
            x_max=max(xs),
            y_max=max(ys),
            frame=self.frame,
        )


class Waypoint(BaseModel):
    """Trajectory waypoint in FRAME_PATH (expressed in physical mm on FRAME_BOARD)."""
    x: float
    y: float
    theta_rad: float = 0.0
    velocity_mm_s: float = 0.0
    frame: CoordinateFrame = CoordinateFrame.FRAME_PATH


def validate_frame(geometry: Any, expected_frame: CoordinateFrame) -> None:
    """Ensure geometry matches the expected coordinate frame."""
    actual = getattr(geometry, "frame", None)
    if actual != expected_frame:
        raise FrameMismatchError(
            f"Coordinate frame mismatch: expected {expected_frame.value}, got {actual}"
        )
