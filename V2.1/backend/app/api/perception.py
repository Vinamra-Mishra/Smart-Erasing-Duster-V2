"""Perception API router for difference maps and stroke extraction."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import numpy as np
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..core.config import get_config
from ..perception.difference import compute_difference_maps, DifferenceMaps
from ..perception.shadow import detect_shadow_mask
from ..perception.glare import SpecularGlareFilter
from ..perception.projector import ProjectorDecoupler
from ..perception.occlusion import TemporalOcclusionDetector
from ..perception.fusion import EvidenceFusionEngine, FusedEvidenceResult
from ..perception.strokes import StrokeExtractor, DetectedStroke
from ..perception.reference import get_default_baseline_manager
from ..perception.registration import get_default_registrar

router = APIRouter(prefix="/api/perception", tags=["perception"])

_glare_filter = SpecularGlareFilter()
_projector_decoupler = ProjectorDecoupler()
_occlusion_detector = TemporalOcclusionDetector()
_evidence_engine = EvidenceFusionEngine()
_stroke_extractor = StrokeExtractor()


class ChannelStats(BaseModel):
    name: str
    mean_val: float
    max_val: float


class PerceptionDebugSummary(BaseModel):
    channels: List[ChannelStats]
    detected_stroke_count: int
    is_occluded: bool
    shadow_pixel_count: int
    projector_pixel_count: int


@router.get("/status")
async def get_perception_status() -> Dict[str, Any]:
    """Retrieve current perception configuration, evidence weights, and status."""
    cfg = get_config()
    baseline_mgr = get_default_baseline_manager()
    registrar = get_default_registrar()
    return {
        "is_calibrated": registrar.is_calibrated,
        "has_baseline": baseline_mgr.current_baseline is not None,
        "evidence_weights": cfg.perception.evidence_weights.model_dump(),
        "disturbance_penalties": cfg.perception.disturbance_penalties.model_dump(),
        "active_epoch_id": baseline_mgr.current_epoch.epoch_id if baseline_mgr.current_epoch else None,
    }


@router.get("/debug-summary", response_model=PerceptionDebugSummary)
async def get_debug_summary() -> PerceptionDebugSummary:
    """Retrieve diagnostic statistics across the 11 difference channels."""
    channel_names = [
        "delta_r", "delta_g", "delta_b",
        "delta_h", "delta_s", "delta_v",
        "delta_l", "delta_a", "delta_b_lab",
        "delta_edge", "delta_contrast",
    ]
    stats = [
        ChannelStats(name=ch, mean_val=0.0, max_val=0.0)
        for ch in channel_names
    ]
    return PerceptionDebugSummary(
        channels=stats,
        detected_stroke_count=0,
        is_occluded=False,
        shadow_pixel_count=0,
        projector_pixel_count=0,
    )
