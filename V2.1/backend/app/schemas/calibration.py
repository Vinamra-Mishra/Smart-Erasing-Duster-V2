from __future__ import annotations

from typing import List, Tuple
from pydantic import BaseModel, Field


class CornerPoints(BaseModel):
    """4-corner polygon coordinates in FRAME_CAMERA (pixels)."""
    top_left: Tuple[float, float]
    top_right: Tuple[float, float]
    bottom_right: Tuple[float, float]
    bottom_left: Tuple[float, float]

    def to_list(self) -> List[Tuple[float, float]]:
        return [self.top_left, self.top_right, self.bottom_right, self.bottom_left]


class CalibrationStatus(BaseModel):
    """Board perspective calibration state and homography parameters."""
    is_calibrated: bool = False
    reprojection_error_px: float = 0.0
    homography_matrix: List[List[float]] = Field(
        default_factory=lambda: [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    )
    board_width_mm: float = 1000.0
    board_height_mm: float = 700.0
    corners: CornerPoints | None = None
    sensor_width: int = 1920
    sensor_height: int = 1080


class BoardSizePayload(BaseModel):
    """Payload to update dynamic whiteboard physical dimensions."""
    board_width_mm: float = Field(..., ge=100.0, le=10000.0, description="Board width in millimeters")
    board_height_mm: float = Field(..., ge=100.0, le=10000.0, description="Board height in millimeters")

