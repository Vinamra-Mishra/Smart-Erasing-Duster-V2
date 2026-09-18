"""Shadow Rejection Filter via Chrominance Ratio Invariance.

Discriminates physical shadow disturbances from real dry-erase marker ink.
Shadows are multiplicative illumination attenuations: luminance drops significantly,
while normalized chromaticity coordinates (r, g, b) and hue remain invariant.
Real marker pigments cause substantial chromaticity shifts and sharp edge boundaries.
"""
from __future__ import annotations

from typing import Tuple
import cv2
import numpy as np


class ShadowRejectionFilter:
    """Detects and isolates shadow regions to prevent false ink detections."""

    def __init__(
        self,
        chroma_threshold: float = 0.06,
        min_luminance_drop: float = 0.06,
        max_hue_shift_deg: float = 20.0,
        max_edge_for_shadow: float = 0.30,
    ) -> None:
        self.chroma_threshold = chroma_threshold
        self.min_luminance_drop = min_luminance_drop
        self.max_hue_shift_norm = max_hue_shift_deg / 180.0
        self.max_edge_for_shadow = max_edge_for_shadow

    def compute_chrominance_coordinates(
        self,
        bgr_frame: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Compute normalized chrominance coordinates r = R/sum, g = G/sum, b = B/sum."""
        b_f = bgr_frame[:, :, 0].astype(np.float32)
        g_f = bgr_frame[:, :, 1].astype(np.float32)
        r_f = bgr_frame[:, :, 2].astype(np.float32)
        total = r_f + g_f + b_f + 1e-6
        return r_f / total, g_f / total, b_f / total

    def detect_shadow_mask(
        self,
        current_bgr: np.ndarray,
        reference_bgr: np.ndarray,
    ) -> np.ndarray:
        """Returns boolean mask where True indicates shadow disturbance (OBS_SHADOW)."""
        if current_bgr.shape != reference_bgr.shape:
            raise ValueError("Frame shapes must match for shadow analysis")

        # 1. Chrominance ratio invariance check
        r_curr, g_curr, b_curr = self.compute_chrominance_coordinates(current_bgr)
        r_ref, g_ref, b_ref = self.compute_chrominance_coordinates(reference_bgr)

        diff_r_chroma = np.abs(r_curr - r_ref)
        diff_g_chroma = np.abs(g_curr - g_ref)
        diff_b_chroma = np.abs(b_curr - b_ref)
        is_chroma_invariant = (
            (diff_r_chroma < self.chroma_threshold)
            & (diff_g_chroma < self.chroma_threshold)
            & (diff_b_chroma < self.chroma_threshold)
        )

        # 2. Luminance drop condition (shadow attenuates brightness)
        curr_hsv = cv2.cvtColor(current_bgr, cv2.COLOR_BGR2HSV)
        ref_hsv = cv2.cvtColor(reference_bgr, cv2.COLOR_BGR2HSV)

        curr_v = curr_hsv[:, :, 2].astype(np.float32) / 255.0
        ref_v = ref_hsv[:, :, 2].astype(np.float32) / 255.0
        luminance_drop = ref_v - curr_v
        is_luminance_drop = luminance_drop > self.min_luminance_drop

        # 3. Minimal hue shift check
        curr_h = curr_hsv[:, :, 0].astype(np.float32)
        ref_h = ref_hsv[:, :, 0].astype(np.float32)
        raw_h_diff = np.abs(curr_h - ref_h)
        diff_h = np.minimum(raw_h_diff, 180.0 - raw_h_diff) / 180.0
        is_hue_invariant = diff_h < self.max_hue_shift_norm

        # 4. Gradient edge sharpness (ink has sharp strokes, shadows are softer)
        curr_gray = cv2.cvtColor(current_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        gx = cv2.Sobel(curr_gray, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(curr_gray, cv2.CV_32F, 0, 1, ksize=3)
        edge_mag = cv2.magnitude(gx, gy) / 4.0
        is_soft_or_diffuse = edge_mag < self.max_edge_for_shadow

        shadow_bool = is_chroma_invariant & is_luminance_drop & is_hue_invariant & is_soft_or_diffuse
        return shadow_bool


_DEFAULT_SHADOW_FILTER = ShadowRejectionFilter()


def detect_shadow_mask(
    current_bgr: np.ndarray,
    reference_bgr: np.ndarray,
) -> np.ndarray:
    """Convenience function to compute shadow boolean mask."""
    return _DEFAULT_SHADOW_FILTER.detect_shadow_mask(current_bgr, reference_bgr)
