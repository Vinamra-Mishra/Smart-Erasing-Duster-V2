"""Unit tests for the 11-channel multi-space difference engine and evidence fusion."""
from __future__ import annotations

import sys
from pathlib import Path
import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.perception.difference import (
    compute_difference_maps,
    DifferenceMaps,
)
from app.perception.fusion import (
    EvidenceFusionEngine,
    FusedEvidenceResult,
)
from app.core.config import EvidenceWeights, DisturbancePenalties


@pytest.fixture
def clean_baseline_bgr() -> np.ndarray:
    """Fixture providing a simulated clean white whiteboard frame (1000x700)."""
    return np.full((700, 1000, 3), 245, dtype=np.uint8)


def test_identical_frames_yield_zero_difference(clean_baseline_bgr: np.ndarray):
    """Confirm comparing identical frames produces zero across all 11 channels."""
    diff_maps = compute_difference_maps(clean_baseline_bgr, clean_baseline_bgr)

    for name in diff_maps.channel_names():
        channel = getattr(diff_maps, name)
        assert np.max(channel) == pytest.approx(0.0, abs=1e-5), f"Channel {name} is non-zero"


def test_red_ink_stroke_activates_expected_color_channels(clean_baseline_bgr: np.ndarray):
    """Draw a rich red marker stroke and verify RGB, HSV, Lab channel activations."""
    frame_with_red = clean_baseline_bgr.copy()
    # In BGR: Red marker is low B, low G, high R (e.g., [20, 20, 210])
    cv2.circle(frame_with_red, (500, 350), 30, (20, 20, 210), thickness=-1)

    diff_maps = compute_difference_maps(frame_with_red, clean_baseline_bgr)
    roi_center = (350, 500)

    # In BGR, G and B drop significantly relative to white baseline (245) -> high diff_g and diff_b
    assert diff_maps.delta_b[roi_center] > 0.70
    assert diff_maps.delta_g[roi_center] > 0.70
    # Red channel has smaller drop
    assert diff_maps.delta_r[roi_center] < diff_maps.delta_b[roi_center]

    # Saturation diff should be very high
    assert diff_maps.delta_s[roi_center] > 0.60

    # In CIE Lab, a* represents green-red axis (high for red)
    assert diff_maps.delta_a[roi_center] > 0.25

    # Stroke edge boundary should have high gradient
    assert np.max(diff_maps.delta_edge[320:380, 470:530]) > 0.20


def test_black_ink_stroke_activates_luminance_and_edges(clean_baseline_bgr: np.ndarray):
    """Draw a black marker stroke and verify delta_v, delta_l, and delta_edge."""
    frame_with_black = clean_baseline_bgr.copy()
    # Black marker: [15, 15, 15]
    cv2.line(frame_with_black, (200, 200), (800, 200), (15, 15, 15), thickness=10)

    diff_maps = compute_difference_maps(frame_with_black, clean_baseline_bgr)

    # Value and lightness drop significantly
    assert np.mean(diff_maps.delta_v[198:203, 300:700]) > 0.80
    assert np.mean(diff_maps.delta_l[198:203, 300:700]) > 0.80

    # Edge gradient difference along the line border
    assert np.max(diff_maps.delta_edge[190:210, 300:700]) > 0.30

    # Local contrast difference along the stroke
    assert np.max(diff_maps.delta_contrast[190:210, 300:700]) > 0.30


def test_uniform_illumination_offset_rejects_edge_and_contrast(clean_baseline_bgr: np.ndarray):
    """A flat global lighting change should NOT trigger false edges or contrast differences."""
    dimmed_frame = np.clip(clean_baseline_bgr.astype(np.int16) - 40, 0, 255).astype(np.uint8)

    diff_maps = compute_difference_maps(dimmed_frame, clean_baseline_bgr)

    # Global luminance shifts
    assert np.mean(diff_maps.delta_v) > 0.10

    # Edge and contrast should remain virtually zero because spatial gradients cancel the DC shift
    assert np.max(diff_maps.delta_edge) < 0.02
    assert np.max(diff_maps.delta_contrast) < 0.02


def test_uint8_heatmaps_export(clean_baseline_bgr: np.ndarray):
    """Verify all 11 channels export as valid 8-bit [0..255] grayscale heatmaps."""
    diff_maps = compute_difference_maps(clean_baseline_bgr, clean_baseline_bgr)
    heatmaps = diff_maps.to_uint8_heatmaps()

    assert len(heatmaps) == 11
    for name, img in heatmaps.items():
        assert img.dtype == np.uint8
        assert img.shape == clean_baseline_bgr.shape[:2]
        assert np.min(img) >= 0
        assert np.max(img) <= 255


def test_evidence_fusion_weighting_and_penalties(clean_baseline_bgr: np.ndarray):
    """Test weighted multi-channel evidence fusion and disturbance penalization."""
    frame_with_stroke = clean_baseline_bgr.copy()
    cv2.circle(frame_with_stroke, (400, 300), 20, (10, 10, 10), thickness=-1)

    diff_maps = compute_difference_maps(frame_with_stroke, clean_baseline_bgr)
    engine = EvidenceFusionEngine()

    h, w = clean_baseline_bgr.shape[:2]
    zeros_mask = np.zeros((h, w), dtype=bool)
    zeros_float = np.zeros((h, w), dtype=np.float32)

    # Normal case: stroke without disturbances
    res_normal = engine.fuse(
        diff_maps=diff_maps,
        shadow_mask=zeros_mask,
        glare_mask=zeros_mask,
        projector_likelihood=zeros_float,
        occlusion_mask=zeros_mask,
    )

    stroke_score = res_normal.fused_score[300, 400]
    assert stroke_score > 0.30
    assert res_normal.ink_candidate_mask[300, 400]

    # Disturbed case: shadow disturbance covers the stroke
    shadow_mask = np.zeros((h, w), dtype=bool)
    shadow_mask[280:320, 380:420] = True

    res_shadowed = engine.fuse(
        diff_maps=diff_maps,
        shadow_mask=shadow_mask,
        glare_mask=zeros_mask,
        projector_likelihood=zeros_float,
        occlusion_mask=zeros_mask,
    )

    # Ink candidate must be suppressed by shadow rejection
    assert not res_shadowed.ink_candidate_mask[300, 400]
    assert res_shadowed.fused_score[300, 400] < stroke_score
