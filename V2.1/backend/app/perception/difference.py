"""11-Channel Multi-Space Difference Engine.

Computes exact multi-space difference maps between rectified camera frame and baseline:
1.  Delta R: RGB Red absolute difference
2.  Delta G: RGB Green absolute difference
3.  Delta B: RGB Blue absolute difference
4.  Delta H: HSV Hue modular angular difference (mod 180)
5.  Delta S: HSV Saturation absolute difference
6.  Delta V: HSV Value/Luminance absolute difference
7.  Delta L*: CIE Lab Lightness absolute difference
8.  Delta a*: CIE Lab a* (green-red) absolute difference
9.  Delta b*: CIE Lab b* (blue-yellow) absolute difference
10. Delta Edge: Sobel spatial gradient magnitude difference
11. Delta Contrast: Local standard deviation (k=7) energy difference
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple
import cv2
import numpy as np


@dataclass(frozen=True)
class DifferenceMaps:
    """Container holding all 11 normalized difference channels in range [0.0, 1.0]."""
    delta_r: np.ndarray
    delta_g: np.ndarray
    delta_b: np.ndarray
    delta_h: np.ndarray
    delta_s: np.ndarray
    delta_v: np.ndarray
    delta_l: np.ndarray
    delta_a: np.ndarray
    delta_b_lab: np.ndarray
    delta_edge: np.ndarray
    delta_contrast: np.ndarray

    def channel_names(self) -> Tuple[str, ...]:
        return (
            "delta_r",
            "delta_g",
            "delta_b",
            "delta_h",
            "delta_s",
            "delta_v",
            "delta_l",
            "delta_a",
            "delta_b_lab",
            "delta_edge",
            "delta_contrast",
        )

    def to_dict(self) -> Dict[str, np.ndarray]:
        return {name: getattr(self, name) for name in self.channel_names()}

    def to_uint8_heatmaps(self) -> Dict[str, np.ndarray]:
        """Convert all 11 channels to 8-bit [0..255] visualization maps."""
        result: Dict[str, np.ndarray] = {}
        for name in self.channel_names():
            channel_data = getattr(self, name)
            scaled = np.clip(channel_data * 255.0, 0.0, 255.0).astype(np.uint8)
            result[name] = scaled
        return result


def _compute_local_std(image_gray_f32: np.ndarray, ksize: int = 7) -> np.ndarray:
    """Compute local standard deviation over a k x k window."""
    mean = cv2.boxFilter(image_gray_f32, -1, (ksize, ksize), normalize=True)
    mean_sq = cv2.boxFilter(image_gray_f32 ** 2, -1, (ksize, ksize), normalize=True)
    variance = np.maximum(0.0, mean_sq - mean ** 2)
    return np.sqrt(variance)


def _compute_sobel_magnitude(image_gray_f32: np.ndarray) -> np.ndarray:
    """Compute normalized Sobel gradient magnitude."""
    grad_x = cv2.Sobel(image_gray_f32, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(image_gray_f32, cv2.CV_32F, 0, 1, ksize=3)
    mag = cv2.magnitude(grad_x, grad_y)
    # Sobel max magnitude for 0..1 image with ksize=3 is ~4.0 * sqrt(2) ~ 5.66
    return np.clip(mag / 4.0, 0.0, 1.0)


def compute_difference_maps(
    current_frame: np.ndarray,
    reference_frame: np.ndarray,
    contrast_ksize: int = 7,
) -> DifferenceMaps:
    """Compute all 11 difference channels between current frame and reference baseline."""
    if current_frame.shape != reference_frame.shape:
        raise ValueError(
            f"Frame shape mismatch: current {current_frame.shape} vs ref {reference_frame.shape}"
        )

    # Convert to RGB float in [0.0, 1.0] for RGB difference
    if current_frame.ndim == 2:
        curr_bgr = cv2.cvtColor(current_frame, cv2.COLOR_GRAY2BGR)
        ref_bgr = cv2.cvtColor(reference_frame, cv2.COLOR_GRAY2BGR)
    else:
        curr_bgr = current_frame
        ref_bgr = reference_frame

    # 1-3. RGB differences (OpenCV uses BGR order)
    diff_b = np.abs(curr_bgr[:, :, 0].astype(np.float32) - ref_bgr[:, :, 0].astype(np.float32)) / 255.0
    diff_g = np.abs(curr_bgr[:, :, 1].astype(np.float32) - ref_bgr[:, :, 1].astype(np.float32)) / 255.0
    diff_r = np.abs(curr_bgr[:, :, 2].astype(np.float32) - ref_bgr[:, :, 2].astype(np.float32)) / 255.0

    # 4-6. HSV differences
    curr_hsv = cv2.cvtColor(curr_bgr, cv2.COLOR_BGR2HSV)
    ref_hsv = cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2HSV)

    curr_h = curr_hsv[:, :, 0].astype(np.float32)
    ref_h = ref_hsv[:, :, 0].astype(np.float32)
    raw_h_diff = np.abs(curr_h - ref_h)
    diff_h = np.minimum(raw_h_diff, 180.0 - raw_h_diff) / 90.0
    diff_h = np.clip(diff_h, 0.0, 1.0)

    diff_s = np.abs(curr_hsv[:, :, 1].astype(np.float32) - ref_hsv[:, :, 1].astype(np.float32)) / 255.0
    diff_v = np.abs(curr_hsv[:, :, 2].astype(np.float32) - ref_hsv[:, :, 2].astype(np.float32)) / 255.0

    # 7-9. CIE Lab differences
    curr_lab = cv2.cvtColor(curr_bgr, cv2.COLOR_BGR2Lab)
    ref_lab = cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2Lab)

    diff_l = np.abs(curr_lab[:, :, 0].astype(np.float32) - ref_lab[:, :, 0].astype(np.float32)) / 255.0
    diff_a = np.abs(curr_lab[:, :, 1].astype(np.float32) - ref_lab[:, :, 1].astype(np.float32)) / 255.0
    diff_b_lab = np.abs(curr_lab[:, :, 2].astype(np.float32) - ref_lab[:, :, 2].astype(np.float32)) / 255.0

    # 10. Gradient/Sobel difference
    curr_gray_f32 = cv2.cvtColor(curr_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    ref_gray_f32 = cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0

    curr_grad = _compute_sobel_magnitude(curr_gray_f32)
    ref_grad = _compute_sobel_magnitude(ref_gray_f32)
    diff_edge = np.clip(np.abs(curr_grad - ref_grad), 0.0, 1.0)

    # 11. Local Contrast (Standard Deviation) difference
    curr_contrast = _compute_local_std(curr_gray_f32, ksize=contrast_ksize)
    ref_contrast = _compute_local_std(ref_gray_f32, ksize=contrast_ksize)
    # std of 0..1 image rarely exceeds 0.5; normalize by 0.5
    diff_contrast = np.clip(np.abs(curr_contrast - ref_contrast) / 0.5, 0.0, 1.0)

    return DifferenceMaps(
        delta_r=diff_r,
        delta_g=diff_g,
        delta_b=diff_b,
        delta_h=diff_h,
        delta_s=diff_s,
        delta_v=diff_v,
        delta_l=diff_l,
        delta_a=diff_a,
        delta_b_lab=diff_b_lab,
        delta_edge=diff_edge,
        delta_contrast=diff_contrast,
    )
