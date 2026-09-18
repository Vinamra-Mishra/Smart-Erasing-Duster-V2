"""Unit tests for projector decoupling and core digital twin invariants."""
from __future__ import annotations

import sys
from pathlib import Path
import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.perception.projector import (
    ProjectorDecoupler,
    compute_projector_likelihood,
)


@pytest.fixture
def clean_whiteboard() -> np.ndarray:
    """Simulated clean white whiteboard frame (1000x700, BGR=[200, 200, 200])."""
    return np.full((700, 1000, 3), 200, dtype=np.uint8)


def test_subtractive_ink_yields_zero_projector_likelihood(clean_whiteboard: np.ndarray):
    """Real dry-erase ink subtracts/absorbs light, producing zero projector likelihood."""
    frame_with_ink = clean_whiteboard.copy()
    # Dark black stroke: BGR=[20, 20, 20] (V drops from 200 to 20)
    cv2.circle(frame_with_ink, (500, 350), 30, (20, 20, 20), thickness=-1)

    decoupler = ProjectorDecoupler()
    likelihood = decoupler.compute_likelihood(frame_with_ink, clean_whiteboard)

    # Likelihood at the ink stroke must be exactly 0.0
    assert likelihood[350, 500] == 0.0


def test_bright_additive_projection_yields_high_confidence(clean_whiteboard: np.ndarray):
    """A bright digital slide overlay (additive light V > V_ref) yields L >= 0.80."""
    frame_with_projection = clean_whiteboard.copy()
    # Additive green digital projection: BGR=[200, 255, 200], V=255 vs ref=200
    cv2.rectangle(frame_with_projection, (400, 250), (600, 450), (180, 255, 180), thickness=-1)

    decoupler = ProjectorDecoupler(alpha_brightness=4.0)
    likelihood = decoupler.compute_likelihood(frame_with_projection, clean_whiteboard)
    high_conf, ambiguous, non_proj = decoupler.classify_regions(likelihood)

    # Region center has strong additive boost
    assert likelihood[350, 500] >= 0.80
    assert high_conf[350, 500]
    assert not ambiguous[350, 500]


def test_ambiguous_projection_classified_as_uncertain(clean_whiteboard: np.ndarray):
    """Faint/ambient projection producing 0.30 < L < 0.80 is tagged as ambiguous/uncertain."""
    frame_faint_proj = clean_whiteboard.copy()
    # Slight additive brightness: V rises from 200 (0.784) to 225 (0.882), gain ~0.098
    cv2.rectangle(frame_faint_proj, (400, 250), (600, 450), (225, 225, 225), thickness=-1)

    decoupler = ProjectorDecoupler(alpha_brightness=4.0)
    likelihood = decoupler.compute_likelihood(frame_faint_proj, clean_whiteboard)
    high_conf, ambiguous, non_proj = decoupler.classify_regions(likelihood)

    # Center is in the ambiguous zone
    val = likelihood[350, 500]
    assert 0.30 < val < 0.80, f"Likelihood {val} outside ambiguous range (0.30, 0.80)"
    assert ambiguous[350, 500]
    assert not high_conf[350, 500]


def test_invariant_1_projector_never_deletes_known_twin_ink(clean_whiteboard: np.ndarray):
    """Core Invariant 1: Digital projector overlay beam NEVER erases existing stable ink."""
    h, w = clean_whiteboard.shape[:2]

    # Existing stable ink on the board at (500, 350)
    twin_stable_ink_mask = np.zeros((h, w), dtype=bool)
    cv2.circle(twin_stable_ink_mask.view(np.uint8), (500, 350), 20, 1, thickness=-1)
    twin_stable_ink_mask = twin_stable_ink_mask.astype(bool)

    # Projector beam hits the exact same region (500, 350)
    projector_high_conf_mask = np.zeros((h, w), dtype=bool)
    cv2.circle(projector_high_conf_mask.view(np.uint8), (500, 350), 40, 1, thickness=-1)
    projector_high_conf_mask = projector_high_conf_mask.astype(bool)

    uncertainty_mask = np.zeros((h, w), dtype=bool)
    new_observations = np.zeros((h, w), dtype=bool)

    decoupler = ProjectorDecoupler()
    reconciled_ink = decoupler.reconcile_projector_with_twin(
        twin_stable_ink_mask=twin_stable_ink_mask,
        projector_high_conf_mask=projector_high_conf_mask,
        uncertainty_mask=uncertainty_mask,
        new_observations_mask=new_observations,
    )

    # Ink must be 100% preserved
    assert np.all(reconciled_ink[twin_stable_ink_mask]), "Invariant 1 violated: Twin ink deleted by projector"


def test_invariant_2_unknown_never_creates_new_ink(clean_whiteboard: np.ndarray):
    """Core Invariant 2: Ambiguous / UNKNOWN regions NEVER create new ink in the physical twin."""
    h, w = clean_whiteboard.shape[:2]

    # No existing twin ink
    twin_stable_ink = np.zeros((h, w), dtype=bool)

    # Ambiguous observation at (300, 300)
    uncertainty_mask = np.zeros((h, w), dtype=bool)
    uncertainty_mask[280:320, 280:320] = True

    # Perception detects raw difference here due to ambiguous projector
    raw_observations = np.zeros((h, w), dtype=bool)
    raw_observations[280:320, 280:320] = True

    decoupler = ProjectorDecoupler()
    reconciled_ink = decoupler.reconcile_projector_with_twin(
        twin_stable_ink_mask=twin_stable_ink,
        projector_high_conf_mask=np.zeros((h, w), dtype=bool),
        uncertainty_mask=uncertainty_mask,
        new_observations_mask=raw_observations,
    )

    # No new ink should be created in the uncertainty zone
    assert not np.any(reconciled_ink), "Invariant 2 violated: Ambiguous UNKNOWN created new ink"
