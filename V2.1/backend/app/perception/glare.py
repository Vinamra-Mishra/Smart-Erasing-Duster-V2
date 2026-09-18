"""Specular Glare and Reflection Filter.

Detects specular highlights on glossy whiteboard surfaces.
Specular glare features saturated brightness (V > 240), low color saturation (S < 20),
and local intensity exceeding baseline, tagging regions as OBS_UNCERTAIN.
"""
from __future__ import annotations

import cv2
import numpy as np


class SpecularGlareFilter:
    """Filters specular glare and highlights from dry-erase whiteboard surfaces."""

    def __init__(
        self,
        min_brightness_val: float = 0.94,  # ~240/255
        max_saturation_val: float = 0.12,  # ~30/255
        min_contrast_spike: float = 0.20,
    ) -> None:
        self.min_brightness = min_brightness_val
        self.max_saturation = max_saturation_val
        self.min_contrast_spike = min_contrast_spike

    def detect_glare_mask(
        self,
        current_bgr: np.ndarray,
        reference_bgr: np.ndarray,
    ) -> np.ndarray:
        """Returns boolean mask where True indicates specular reflection."""
        curr_hsv = cv2.cvtColor(current_bgr, cv2.COLOR_BGR2HSV)
        ref_hsv = cv2.cvtColor(reference_bgr, cv2.COLOR_BGR2HSV)

        curr_s = curr_hsv[:, :, 1].astype(np.float32) / 255.0
        curr_v = curr_hsv[:, :, 2].astype(np.float32) / 255.0
        ref_v = ref_hsv[:, :, 2].astype(np.float32) / 255.0

        is_saturated = curr_v >= self.min_brightness
        is_desaturated = curr_s <= self.max_saturation
        is_brightness_spike = (curr_v - ref_v) >= self.min_contrast_spike

        glare_mask = is_saturated & is_desaturated & is_brightness_spike
        return glare_mask
