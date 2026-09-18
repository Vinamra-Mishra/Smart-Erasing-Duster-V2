"""Unit tests for shadow rejection filter via chrominance ratio invariance."""
from __future__ import annotations

import sys
from pathlib import Path
import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.perception.shadow import (
    ShadowRejectionFilter,
    detect_shadow_mask,
)
from app.perception.difference import compute_difference_maps
from app.perception.fusion import EvidenceFusionEngine


@pytest.fixture
def clean_white_board() -> np.ndarray:
    """Simulated clean white whiteboard frame (1000x700)."""
    return np.full((700, 1000, 3), 240, dtype=np.uint8)


def test_shadow_classified_and_rejected_from_ink(clean_white_board: np.ndarray):
    """Synthetic shadow (30% multiplicative luminance drop) is classified as shadow and rejected."""
    frame_with_shadow = clean_white_board.copy().astype(np.float32)

    # Cast a soft elliptical shadow (30% brightness drop)
    # Multiply by 0.70 uniformly across R, G, B channels -> chrominance ratio is 100% invariant
    cv2.ellipse(
        frame_with_shadow,
        (500, 350),
        (150, 100),
        0,
        0,
        360,
        (168, 168, 168),  # 240 * 0.70 = 168
        thickness=-1,
    )
    # Soften shadow edges with Gaussian blur to model realistic penumbra
    frame_with_shadow = cv2.GaussianBlur(frame_with_shadow, (15, 15), 0)
    current_frame = np.clip(frame_with_shadow, 0, 255).astype(np.uint8)

    shadow_filter = ShadowRejectionFilter(
        chroma_threshold=0.06,
        min_luminance_drop=0.06,
        max_hue_shift_deg=20.0,
    )
    shadow_mask = shadow_filter.detect_shadow_mask(current_frame, clean_white_board)

    # Shadow core should be detected
    assert np.any(shadow_mask[340:360, 480:520]), "Failed to detect synthetic shadow"

    # Verify chrominance ratios were indeed invariant
    r_curr, g_curr, b_curr = shadow_filter.compute_chrominance_coordinates(current_frame)
    r_ref, g_ref, b_ref = shadow_filter.compute_chrominance_coordinates(clean_white_board)
    assert np.max(np.abs(r_curr[340:360, 480:520] - r_ref[340:360, 480:520])) < 0.02

    # Evidence fusion must reject this shadow from ink candidates
    diff_maps = compute_difference_maps(current_frame, clean_white_board)
    fusion_engine = EvidenceFusionEngine()
    h, w = clean_white_board.shape[:2]

    result = fusion_engine.fuse(
        diff_maps=diff_maps,
        shadow_mask=shadow_mask,
        glare_mask=np.zeros((h, w), dtype=bool),
        projector_likelihood=np.zeros((h, w), dtype=np.float32),
        occlusion_mask=np.zeros((h, w), dtype=bool),
    )

    # All shadow core pixels must be rejected from ink candidates
    assert not np.any(result.ink_candidate_mask[340:360, 480:520]), "Shadow falsely classified as ink"


def test_red_ink_not_rejected_as_shadow(clean_white_board: np.ndarray):
    """Red dry-erase ink causes large chrominance ratio shift and must not be marked as shadow."""
    frame_with_ink = clean_white_board.copy()
    # Draw red stroke: B=30, G=30, R=210
    cv2.circle(frame_with_ink, (500, 350), 25, (30, 30, 210), thickness=-1)

    shadow_filter = ShadowRejectionFilter()
    shadow_mask = shadow_filter.detect_shadow_mask(frame_with_ink, clean_white_board)

    # Red stroke center must NOT be classified as shadow
    assert not shadow_mask[350, 500]


def test_blue_ink_not_rejected_as_shadow(clean_white_board: np.ndarray):
    """Blue dry-erase ink causes blue chrominance spike and must not be marked as shadow."""
    frame_with_ink = clean_white_board.copy()
    # Draw blue stroke: B=220, G=40, R=40
    cv2.circle(frame_with_ink, (500, 350), 25, (220, 40, 40), thickness=-1)

    shadow_filter = ShadowRejectionFilter()
    shadow_mask = shadow_filter.detect_shadow_mask(frame_with_ink, clean_white_board)

    # Blue stroke must NOT be classified as shadow
    assert not shadow_mask[350, 500]


def test_black_ink_with_sharp_edges_not_rejected_as_shadow(clean_white_board: np.ndarray):
    """Black ink has sharp spatial edge gradients and must not be classified as soft shadow."""
    frame_with_black = clean_white_board.copy()
    cv2.rectangle(frame_with_black, (480, 330), (520, 370), (10, 10, 10), thickness=-1)

    shadow_filter = ShadowRejectionFilter(max_edge_for_shadow=0.25)
    shadow_mask = shadow_filter.detect_shadow_mask(frame_with_black, clean_white_board)

    # Black stroke boundary has gradient >> 0.25, ensuring it's recognized as stroke, not shadow
    assert not shadow_mask[330, 500]
    assert not shadow_mask[370, 500]


def test_minor_ambient_dimming_below_threshold(clean_white_board: np.ndarray):
    """Minor illumination dip (e.g. 2% drop) does not trigger shadow threshold."""
    dimmed_frame = np.clip(clean_white_board.astype(np.int16) - 5, 0, 255).astype(np.uint8)
    shadow_filter = ShadowRejectionFilter(min_luminance_drop=0.06)
    shadow_mask = shadow_filter.detect_shadow_mask(dimmed_frame, clean_white_board)

    assert not np.any(shadow_mask)
