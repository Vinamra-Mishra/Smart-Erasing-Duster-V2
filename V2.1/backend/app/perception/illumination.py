"""Illumination normalization and local background compensation.

Corrects for smooth spatial gradients, ambient light shifts, and uneven lighting
across the whiteboard without corrupting the absolute reference baseline.
"""
from __future__ import annotations

from typing import Tuple
import cv2
import numpy as np


class IlluminationNormalizer:
    """Normalizes non-uniform illumination fields across FRAME_BOARD."""

    def __init__(self, blur_ksize: int = 51) -> None:
        self.blur_ksize = blur_ksize if blur_ksize % 2 == 1 else blur_ksize + 1

    def estimate_illumination_field(self, image_bgr: np.ndarray) -> np.ndarray:
        """Estimate low-frequency ambient illumination field using broad Gaussian filter."""
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY) if image_bgr.ndim == 3 else image_bgr
        field = cv2.GaussianBlur(gray, (self.blur_ksize, self.blur_ksize), 0)
        return field.astype(np.float32)

    def normalize_illumination_ratio(
        self,
        current_bgr: np.ndarray,
        reference_bgr: np.ndarray,
    ) -> np.ndarray:
        """Compensate frame by the ratio of reference background to current illumination field."""
        curr_field = self.estimate_illumination_field(current_bgr)
        ref_field = self.estimate_illumination_field(reference_bgr)

        # Ratio of reference ambient to current ambient
        ratio = (ref_field + 1e-4) / (curr_field + 1e-4)
        ratio_3d = np.repeat(ratio[:, :, np.newaxis], 3, axis=2)

        compensated = np.clip(current_bgr.astype(np.float32) * ratio_3d, 0.0, 255.0).astype(np.uint8)
        return compensated

    def remove_flat_lighting_offset(
        self,
        diff_channel: np.ndarray,
        cutoff_percentile: float = 20.0,
    ) -> np.ndarray:
        """Subtract global flat lighting shift from difference channel."""
        offset = np.percentile(diff_channel, cutoff_percentile)
        return np.maximum(0.0, diff_channel - offset)
