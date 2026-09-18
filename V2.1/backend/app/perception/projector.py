"""Projector Decoupling Engine (Mode A Camera-Only Continuous Likelihood).

Distinguishes digital projector overlays from real physical marker ink.
Invariants:
1. Physical ink is subtractive (darkens the board: V < V_ref).
   Projector overlays are additive light (brightens the board: V > V_ref).
2. Continuous likelihood L_proj in [0.0, 1.0].
   - L >= 0.80: High-confidence projector (OBS_PROJECTOR -> suppressed from ink candidates).
   - 0.30 < L < 0.80: Ambiguous region (OBS_UNCERTAIN -> added to uncertainty mask, Twin = UNKNOWN).
   - L <= 0.30: Non-projector region.
3. INVARIANT 1: Projector detection NEVER deletes confirmed twin ink.
4. INVARIANT 2: UNKNOWN state NEVER creates new ink.
"""
from __future__ import annotations

from typing import Tuple
import cv2
import numpy as np


class ProjectorDecoupler:
    """Computes continuous projector likelihood and enforces decoupling invariants."""

    def __init__(
        self,
        high_confidence_threshold: float = 0.80,
        ambiguity_lower_threshold: float = 0.30,
        alpha_brightness: float = 2.5,
        beta_saturation: float = 0.5,
    ) -> None:
        self.high_confidence_threshold = high_confidence_threshold
        self.ambiguity_lower_threshold = ambiguity_lower_threshold
        self.alpha_brightness = alpha_brightness
        self.beta_saturation = beta_saturation

    def compute_likelihood(
        self,
        current_bgr: np.ndarray,
        reference_bgr: np.ndarray,
    ) -> np.ndarray:
        """Compute continuous projector likelihood L_proj in [0.0, 1.0] per pixel."""
        if current_bgr.shape != reference_bgr.shape:
            raise ValueError("Frame shapes must match for projector decoupling")

        curr_hsv = cv2.cvtColor(current_bgr, cv2.COLOR_BGR2HSV)
        ref_hsv = cv2.cvtColor(reference_bgr, cv2.COLOR_BGR2HSV)

        curr_v = curr_hsv[:, :, 2].astype(np.float32) / 255.0
        ref_v = ref_hsv[:, :, 2].astype(np.float32) / 255.0
        curr_s = curr_hsv[:, :, 1].astype(np.float32) / 255.0

        # Physical ink subtracts light; projector adds light
        brightness_gain = np.maximum(0.0, curr_v - ref_v)

        # Raw additive signal
        raw_signal = self.alpha_brightness * brightness_gain + self.beta_saturation * (curr_s * brightness_gain)
        likelihood = np.clip(raw_signal, 0.0, 1.0)
        return likelihood

    def classify_regions(
        self,
        likelihood_map: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Classify into (high_conf_projector_mask, ambiguous_mask, non_projector_mask)."""
        high_conf = likelihood_map >= self.high_confidence_threshold
        ambiguous = (likelihood_map > self.ambiguity_lower_threshold) & (~high_conf)
        non_projector = likelihood_map <= self.ambiguity_lower_threshold
        return high_conf, ambiguous, non_projector

    def filter_ink_candidates(
        self,
        raw_ink_candidates: np.ndarray,
        likelihood_map: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Filter raw ink candidate mask against projector disturbances.

        Returns:
            Tuple[filtered_ink_mask, uncertainty_mask]
        """
        high_conf, ambiguous, _ = self.classify_regions(likelihood_map)
        # Suppress high-confidence projector pixels
        filtered_ink = raw_ink_candidates & (~high_conf) & (~ambiguous)
        # Ambiguous regions are tagged into uncertainty mask
        uncertainty_mask = ambiguous
        return filtered_ink, uncertainty_mask

    def reconcile_projector_with_twin(
        self,
        twin_stable_ink_mask: np.ndarray,
        projector_high_conf_mask: np.ndarray,
        uncertainty_mask: np.ndarray,
        new_observations_mask: np.ndarray,
    ) -> np.ndarray:
        """Enforce core invariants:
        Invariant 1: Projector NEVER deletes existing twin ink.
        Invariant 2: UNKNOWN / ambiguous regions NEVER create new ink.
        """
        # Invariant 2: Candidate pixels inside uncertainty mask cannot create new ink
        valid_new_ink = new_observations_mask & (~uncertainty_mask) & (~projector_high_conf_mask)

        # Invariant 1: Existing stable ink is preserved even if projector beam overlaps it
        reconciled_physical_ink = twin_stable_ink_mask | valid_new_ink
        return reconciled_physical_ink


_DEFAULT_DECOUPLER = ProjectorDecoupler()


def compute_projector_likelihood(
    current_bgr: np.ndarray,
    reference_bgr: np.ndarray,
) -> np.ndarray:
    """Convenience function for projector likelihood computation."""
    return _DEFAULT_DECOUPLER.compute_likelihood(current_bgr, reference_bgr)
