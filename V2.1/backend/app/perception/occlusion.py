"""Temporal Occlusion Detector (Multi-Signal Fusion, STRICTLY NO MOG2).

Detects temporary occlusions (presenter bodies, arms, hands, tools) using 3 fused signals:
1. Coherent dynamic motion via Farneback optical flow and temporal differencing
2. Large contiguous spatial footprint (area fraction >= 4.5% = 31,500 mm^2 on 1000x700 board)
3. Temporal persistence across K >= 3 consecutive frames

STRICT INVARIANT:
- Continuous background adaptation (such as Gaussian background mixture models) is BANNED.
- Occluded ink is NEVER erased or deleted from the physical digital twin;
  its state transitions to OCCLUDED while retaining its exact geometry and confidence.
"""
from __future__ import annotations

from collections import deque
from typing import Any, List, Optional, Tuple
import cv2
import numpy as np

from .frames import CoordinateFrame, Polygon2D, BoundingBox
from ..core.config import get_config


class TemporalOcclusionDetector:
    """Detects broad moving occluders without background model corruption."""

    def __init__(
        self,
        board_width_mm: float = 1000.0,
        board_height_mm: float = 700.0,
        min_area_fraction: float = 0.045,
        min_displacement_px: float = 12.0,
        confirmation_frames: int = 3,
    ) -> None:
        self.board_width = board_width_mm
        self.board_height = board_height_mm
        self.total_board_area = float(board_width_mm * board_height_mm)
        self.min_area_fraction = min_area_fraction
        self.min_area_mm2 = self.total_board_area * self.min_area_fraction
        self.min_displacement = min_displacement_px
        self.confirmation_frames = max(1, confirmation_frames)

        self._candidate_history: deque[np.ndarray] = deque(maxlen=self.confirmation_frames)
        self._confirmed_occlusion_mask: Optional[np.ndarray] = None

    def set_board_dimensions(self, width_mm: float, height_mm: float) -> None:
        """Dynamically update board dimensions and area thresholds."""
        self.board_width = float(width_mm)
        self.board_height = float(height_mm)
        self.total_board_area = float(width_mm * height_mm)
        self.min_area_mm2 = self.total_board_area * self.min_area_fraction

    @property
    def confirmed_mask(self) -> Optional[np.ndarray]:
        return self._confirmed_occlusion_mask.copy() if self._confirmed_occlusion_mask is not None else None

    def reset(self) -> None:
        """Clear temporal frame history."""
        self._candidate_history.clear()
        self._confirmed_occlusion_mask = None

    def compute_optical_flow_motion(
        self,
        curr_gray: np.ndarray,
        prev_gray: np.ndarray,
    ) -> np.ndarray:
        """Compute optical flow displacement magnitude using Farneback algorithm."""
        flow = cv2.calcOpticalFlowFarneback(
            prev_gray,
            curr_gray,
            None,
            pyr_scale=0.5,
            levels=3,
            winsize=15,
            iterations=3,
            poly_n=5,
            poly_sigma=1.2,
            flags=0,
        )
        mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
        return mag

    def detect_large_motion_blobs(
        self,
        motion_mag: np.ndarray,
        curr_gray: np.ndarray,
        prev_gray: np.ndarray,
    ) -> Tuple[np.ndarray, List[np.ndarray]]:
        """Identify contiguous motion regions meeting the minimum area fraction threshold."""
        motion_binary = (motion_mag >= self.min_displacement).astype(np.uint8)
        diff_binary = (cv2.absdiff(curr_gray, prev_gray) >= 15).astype(np.uint8)
        combined_motion = cv2.bitwise_or(motion_binary, diff_binary)

        # Morphological close to bridge internal limbs and body contours
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21))
        closed_motion = cv2.morphologyEx(combined_motion, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(closed_motion, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        large_blobs_mask = np.zeros_like(motion_binary)
        large_contours: List[np.ndarray] = []

        for cnt in contours:
            area = cv2.contourArea(cnt)
            hull = cv2.convexHull(cnt)
            hull_area = cv2.contourArea(hull)
            effective_area = max(area, hull_area)
            if effective_area >= self.min_area_mm2:
                cv2.drawContours(large_blobs_mask, [hull], -1, 1, thickness=cv2.FILLED)
                large_contours.append(hull)

        return large_blobs_mask.astype(bool), large_contours

    def evaluate_frame(
        self,
        current_frame: np.ndarray,
        prev_frame: np.ndarray,
    ) -> Tuple[bool, np.ndarray, List[Polygon2D]]:
        """Evaluate current frame against previous frame for temporal occlusion."""
        curr_gray = (
            cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)
            if current_frame.ndim == 3
            else current_frame
        )
        prev_gray = (
            cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
            if prev_frame.ndim == 3
            else prev_frame
        )

        motion_mag = self.compute_optical_flow_motion(curr_gray, prev_gray)
        candidate_mask, raw_contours = self.detect_large_motion_blobs(motion_mag, curr_gray, prev_gray)

        has_candidate = bool(np.any(candidate_mask))
        self._candidate_history.append(candidate_mask)

        # Signal 3: Temporal Persistence Check across confirmation_frames
        # Requires all buffered frames in the window to contain large moving occluder
        if len(self._candidate_history) >= self.confirmation_frames and all(
            np.any(m) for m in self._candidate_history
        ):
            is_occluded = True
            persistent_mask = candidate_mask.copy()
        else:
            is_occluded = False
            persistent_mask = np.zeros_like(candidate_mask)

        self._confirmed_occlusion_mask = persistent_mask

        occlusion_polygons: List[Polygon2D] = []
        if is_occluded:
            cnts, _ = cv2.findContours(
                persistent_mask.astype(np.uint8),
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_SIMPLE,
            )
            for c in cnts:
                if cv2.contourArea(c) >= self.min_area_mm2:
                    pts = [(float(p[0][0]), float(p[0][1])) for p in c]
                    occlusion_polygons.append(
                        Polygon2D(points=pts, frame=CoordinateFrame.FRAME_BOARD)
                    )

        return is_occluded, persistent_mask, occlusion_polygons

    def reconcile_ink_preservation(
        self,
        twin_ink_polygons: List[Polygon2D],
        occlusion_mask: np.ndarray,
    ) -> List[Tuple[Polygon2D, bool]]:
        """Determine which twin ink polygons are occluded, ensuring zero deletion."""
        results: List[Tuple[Polygon2D, bool]] = []
        h, w = occlusion_mask.shape

        for poly in twin_ink_polygons:
            pts_arr = np.array(poly.points, dtype=np.int32).reshape((-1, 1, 2))
            poly_mask = np.zeros((h, w), dtype=np.uint8)
            cv2.fillPoly(poly_mask, [pts_arr], 1)

            overlap = np.logical_and(poly_mask.astype(bool), occlusion_mask)
            is_overlap = bool(np.any(overlap))
            results.append((poly, is_overlap))

        return results
