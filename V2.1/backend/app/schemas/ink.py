from __future__ import annotations

from enum import Enum
from typing import List, Tuple
from pydantic import BaseModel, Field


class CoordinateFrame(str, Enum):
    """Explicitly tagged coordinate systems."""
    FRAME_CAMERA = "FRAME_CAMERA"  # Raw camera sensor coordinates (u, v) px
    FRAME_BOARD = "FRAME_BOARD"    # Homography rectified board coordinates (x, y) mm
    FRAME_DUSTER = "FRAME_DUSTER"  # Actuator body-fixed coordinates (dx, dy) mm
    FRAME_PATH = "FRAME_PATH"      # Ordered waypoint path in FRAME_BOARD


class PhysicalState(str, Enum):
    """Authoritative physical whiteboard surface states.

    INVARIANT:
        RESIDUAL_DETECTED is strictly an execution trigger flag in
        execution_state.py, NEVER a physical state in board_twin.py.
    """
    UNKNOWN = "UNKNOWN"
    NEW_INK = "NEW_INK"
    STABLE_INK = "STABLE_INK"
    OCCLUDED = "OCCLUDED"
    PARTIALLY_CLEANED = "PARTIALLY_CLEANED"
    CLEANED = "CLEANED"
    PERMANENT_DEFECT = "PERMANENT_DEFECT"


class InkObjectDTO(BaseModel):
    """Pydantic model representing an ink stroke/defect on the physical whiteboard."""
    id: str
    state: PhysicalState
    frame_id: CoordinateFrame = CoordinateFrame.FRAME_BOARD
    points: List[List[float]] = Field(default_factory=list)  # Polygon vertices [[x, y], ...]
    bbox: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)  # min_x, min_y, max_x, max_y
    centroid: Tuple[float, float] = (0.0, 0.0)
    confidence: float = 1.0
    reclean_attempts: int = 0
    first_seen: float = 0.0
    last_seen: float = 0.0
    color_bgr: Tuple[int, int, int] = (0, 0, 0)
    area_mm2: float = 0.0
    is_occluded: bool = False
    holes: List[List[List[float]]] = Field(default_factory=list)
