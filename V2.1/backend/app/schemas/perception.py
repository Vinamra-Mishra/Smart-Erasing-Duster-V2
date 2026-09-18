from __future__ import annotations

from enum import Enum
from typing import List, Tuple
from pydantic import BaseModel, Field


class ObservationType(str, Enum):
    """Observation classifications from the computer vision perception pipeline."""
    OBS_ABSENT = "OBS_ABSENT"        # Pristine white surface; difference ~ 0
    OBS_INK = "OBS_INK"              # Confirmed physical dry-erase marker stroke
    OBS_OCCLUDED = "OBS_OCCLUDED"    # Large coherent occluder (human arm/hand/body)
    OBS_SHADOW = "OBS_SHADOW"        # Illumination drop with invariant chrominance
    OBS_PROJECTOR = "OBS_PROJECTOR"  # Additive optical projection overlay
    OBS_UNCERTAIN = "OBS_UNCERTAIN"  # Specular glare or ambiguous contrast


class PerceptionMetrics(BaseModel):
    """Exact operational metrics computed in FRAME_BOARD mm^2."""
    precision: float = 1.0
    recall: float = 1.0
    iou: float = 1.0
    false_positive_rate: float = 0.0
    residual_fraction: float = 0.0
    cleaning_coverage: float = 1.0
    tracking_stability: float = 1.0


class ObservationRegion(BaseModel):
    """Segmented region evaluated by the vision pipeline."""
    evidence_type: ObservationType
    points: List[List[float]] = Field(default_factory=list)
    bbox: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    centroid: Tuple[float, float] = (0.0, 0.0)
    confidence: float = 1.0
    area_mm2: float = 0.0
    is_spatial_match: bool = False
    matched_object_id: str | None = None
    residual_ratio: float = 0.0


class ProjectorStatus(BaseModel):
    """Projector decoupling state."""
    is_active: bool = False
    mode: str = "MODE_A"  # MODE_A: Camera-only likelihood; MODE_B: Synchronized reference
    likelihood: float = 0.0
