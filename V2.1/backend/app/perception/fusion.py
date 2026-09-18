"""Weighted Multi-Signal Evidence Fusion Pipeline.

Fuses 11-channel difference maps with disturbance penalties:
- Weights: RGB (0.25), HSV (0.20), Lab (0.20), Edge (0.20), Contrast (0.15)
- Disturbance Penalties: Shadow (0.40), Glare (0.50), Occlusion (0.80), Projector (0.60)
Produces final normalized ink evidence score [0.0, 1.0] and classified observation states.
"""
from __future__ import annotations

from enum import Enum
from typing import Dict, NamedTuple, Tuple
import cv2
import numpy as np

from .difference import DifferenceMaps
from ..core.config import EvidenceWeights, DisturbancePenalties, get_config


class ObservationState(str, Enum):
    """Categorical observation evidence state emitted to Digital Twin reconciler."""
    OBS_ABSENT = "OBS_ABSENT"
    OBS_INK = "OBS_INK"
    OBS_OCCLUDED = "OBS_OCCLUDED"
    OBS_SHADOW = "OBS_SHADOW"
    OBS_PROJECTOR = "OBS_PROJECTOR"
    OBS_UNCERTAIN = "OBS_UNCERTAIN"


class FusedEvidenceResult(NamedTuple):
    """Container for perception evidence maps and candidate classifications."""
    raw_score: np.ndarray
    fused_score: np.ndarray
    ink_candidate_mask: np.ndarray
    shadow_mask: np.ndarray
    glare_mask: np.ndarray
    projector_mask: np.ndarray
    occlusion_mask: np.ndarray
    uncertainty_mask: np.ndarray


class EvidenceFusionEngine:
    """Fuses multi-space difference channels and applies disturbance penalties."""

    def __init__(
        self,
        weights: EvidenceWeights | None = None,
        penalties: DisturbancePenalties | None = None,
        ink_score_threshold: float = 0.20,
    ) -> None:
        cfg = get_config()
        self.weights = weights or cfg.perception.evidence_weights
        self.penalties = penalties or cfg.perception.disturbance_penalties
        self.ink_score_threshold = ink_score_threshold

    def compute_raw_evidence(self, diff_maps: DifferenceMaps) -> np.ndarray:
        """Compute base evidence score map from 11 normalized difference channels."""
        rgb_term = (diff_maps.delta_r + diff_maps.delta_g + diff_maps.delta_b) / 3.0
        hsv_term = (diff_maps.delta_h + diff_maps.delta_s + diff_maps.delta_v) / 3.0
        lab_term = (diff_maps.delta_l + diff_maps.delta_a + diff_maps.delta_b_lab) / 3.0
        edge_term = diff_maps.delta_edge
        contrast_term = diff_maps.delta_contrast

        raw_score = (
            self.weights.w_rgb * rgb_term
            + self.weights.w_hsv * hsv_term
            + self.weights.w_lab * lab_term
            + self.weights.w_edge * edge_term
            + self.weights.w_contrast * contrast_term
        )
        return np.clip(raw_score, 0.0, 1.0)

    def fuse(
        self,
        diff_maps: DifferenceMaps,
        shadow_mask: np.ndarray,
        glare_mask: np.ndarray,
        projector_likelihood: np.ndarray,
        occlusion_mask: np.ndarray,
    ) -> FusedEvidenceResult:
        """Combine raw evidence with disturbance masks to yield final ink candidate mask."""
        raw_score = self.compute_raw_evidence(diff_maps)

        # Disturbance penalty accumulation
        penalty_field = np.zeros_like(raw_score)
        penalty_field += shadow_mask.astype(np.float32) * self.penalties.w_shadow
        penalty_field += glare_mask.astype(np.float32) * self.penalties.w_glare
        penalty_field += occlusion_mask.astype(np.float32) * self.penalties.w_occlusion
        penalty_field += (projector_likelihood >= 0.80).astype(np.float32) * self.penalties.w_projector

        fused_score = np.clip(raw_score - penalty_field, 0.0, 1.0)

        # Projector masks
        high_conf_proj = projector_likelihood >= 0.80
        ambiguous_proj = (projector_likelihood > 0.30) & (~high_conf_proj)

        uncertainty_mask = glare_mask | ambiguous_proj

        # Ink candidate: exceeds threshold AND not rejected by shadow, projector, glare, occlusion
        ink_candidate_mask = (
            (fused_score >= self.ink_score_threshold)
            & (~shadow_mask)
            & (~high_conf_proj)
            & (~glare_mask)
            & (~occlusion_mask)
            & (~ambiguous_proj)
        )

        return FusedEvidenceResult(
            raw_score=raw_score,
            fused_score=fused_score,
            ink_candidate_mask=ink_candidate_mask,
            shadow_mask=shadow_mask,
            glare_mask=glare_mask,
            projector_mask=high_conf_proj,
            occlusion_mask=occlusion_mask,
            uncertainty_mask=uncertainty_mask,
        )
