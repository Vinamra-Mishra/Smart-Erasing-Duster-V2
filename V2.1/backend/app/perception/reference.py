"""Baseline Reference Epoch Engine.

Manages reference baseline frames, dirty board validation, and verified epoch rolling.
Invariants:
1. Accumulates N frames (default 20) via temporal median/mean.
2. Rejects baseline capture if edge density > dirty_board_threshold (default 0.04).
3. Rolling epochs allowed only after post-clean verified residual <= clean_threshold (default 0.01),
   masking out PERMANENT_DEFECT objects.
"""
from __future__ import annotations

import time
from typing import List, Optional, Tuple
import cv2
import numpy as np
from pydantic import BaseModel, Field

from ..core.config import get_config


class DirtyBoardError(RuntimeError):
    """Raised when baseline capture fails due to dirty board markings exceeding threshold."""
    def __init__(self, edge_density: float, threshold: float) -> None:
        super().__init__(
            f"Baseline capture aborted: dirty board edge density {edge_density:.4f} > {threshold:.4f}"
        )
        self.edge_density = edge_density
        self.threshold = threshold


class EpochRollRejectedError(RuntimeError):
    """Raised when epoch roll is attempted on an unverified or dirty board."""
    def __init__(self, residual_fraction: float, clean_threshold: float) -> None:
        super().__init__(
            f"Epoch roll rejected: residual {residual_fraction:.4f} exceeds clean threshold {clean_threshold:.4f}"
        )
        self.residual_fraction = residual_fraction
        self.clean_threshold = clean_threshold


class BaselineEpoch(BaseModel):
    """Metadata for an accepted baseline reference epoch."""
    epoch_id: int
    timestamp: float
    edge_density: float
    mean_luminance: float
    frame_width: int
    frame_height: int
    is_clean_verified: bool = True
    permanent_defect_count: int = 0


class BoardSection(BaseModel):
    """A spatial section of the board surface for progressive, localized baseline refreshing."""
    col: int
    row: int
    bbox_mm: Tuple[float, float, float, float]  # (x1, y1, x2, y2) in FRAME_BOARD mm
    is_confirmed_clean: bool = False
    clean_confidence: float = 0.0
    last_refreshed_timestamp: float = 0.0
    refresh_count: int = 0


class SpatialSectionGrid:
    """Partitions the board into spatial sections (default 50x50 mm) for localized baseline refreshing."""
    def __init__(
        self,
        board_width_mm: float = 1000.0,
        board_height_mm: float = 700.0,
        section_size_mm: float = 50.0,
        clean_confidence_threshold: float = 0.989,  # 98.9%
    ) -> None:
        self.board_width_mm = float(board_width_mm)
        self.board_height_mm = float(board_height_mm)
        self.section_size_mm = float(section_size_mm)
        self.clean_confidence_threshold = clean_confidence_threshold

        self.cols = max(1, int(np.ceil(self.board_width_mm / self.section_size_mm)))
        self.rows = max(1, int(np.ceil(self.board_height_mm / self.section_size_mm)))
        self.sections: dict = {}
        self._init_sections()

    def _init_sections(self) -> None:
        self.sections.clear()
        for r in range(self.rows):
            y1 = r * self.section_size_mm
            y2 = min(self.board_height_mm, (r + 1) * self.section_size_mm)
            for c in range(self.cols):
                x1 = c * self.section_size_mm
                x2 = min(self.board_width_mm, (c + 1) * self.section_size_mm)
                self.sections[(c, r)] = BoardSection(
                    col=c,
                    row=r,
                    bbox_mm=(x1, y1, x2, y2),
                    is_confirmed_clean=False,
                    clean_confidence=0.0,
                    last_refreshed_timestamp=0.0,
                    refresh_count=0,
                )

    def get_sections_in_bbox(
        self,
        bbox_mm: Tuple[float, float, float, float],
    ) -> List[BoardSection]:
        """Find all grid sections intersecting a given bounding box (e.g. swept footprint)."""
        x1, y1, x2, y2 = bbox_mm
        eps = 1e-4
        c_min = max(0, int(x1 // self.section_size_mm))
        c_max = min(self.cols - 1, int(max(x1, x2 - eps) // self.section_size_mm))
        r_min = max(0, int(y1 // self.section_size_mm))
        r_max = min(self.rows - 1, int(max(y1, y2 - eps) // self.section_size_mm))

        matched = []
        for r in range(r_min, r_max + 1):
            for c in range(c_min, c_max + 1):
                if (c, r) in self.sections:
                    matched.append(self.sections[(c, r)])
        return matched


class BaselineEpochManager:
    """Manages multi-frame baseline capture, validation, and epoch lifecycle."""

    def __init__(
        self,
        frames_to_accumulate: int = 20,
        dirty_board_threshold: float = 0.04,
        board_width_mm: float = 1000.0,
        board_height_mm: float = 700.0,
        section_size_mm: float = 50.0,
    ) -> None:
        self.frames_to_accumulate = max(1, frames_to_accumulate)
        self.dirty_board_threshold = dirty_board_threshold
        self.section_grid = SpatialSectionGrid(
            board_width_mm=board_width_mm,
            board_height_mm=board_height_mm,
            section_size_mm=section_size_mm,
            clean_confidence_threshold=0.989,
        )

        self._frame_buffer: List[np.ndarray] = []
        self._current_baseline: Optional[np.ndarray] = None
        self._current_epoch: Optional[BaselineEpoch] = None
        self._epoch_history: List[BaselineEpoch] = []
        self._permanent_defect_mask: Optional[np.ndarray] = None
        self._epoch_counter: int = 0

    @property
    def buffer_count(self) -> int:
        return len(self._frame_buffer)

    @property
    def is_accumulation_complete(self) -> bool:
        return len(self._frame_buffer) >= self.frames_to_accumulate

    @property
    def current_baseline(self) -> Optional[np.ndarray]:
        return self._current_baseline.copy() if self._current_baseline is not None else None

    @property
    def current_epoch(self) -> Optional[BaselineEpoch]:
        return self._current_epoch

    @property
    def epoch_history(self) -> List[BaselineEpoch]:
        return list(self._epoch_history)

    @property
    def permanent_defect_mask(self) -> Optional[np.ndarray]:
        return self._permanent_defect_mask.copy() if self._permanent_defect_mask is not None else None

    def reset_buffer(self) -> None:
        """Clear accumulation buffer."""
        self._frame_buffer.clear()

    def add_frame(self, frame: np.ndarray) -> bool:
        """Add a rectified frame to the accumulation buffer. Returns True when full."""
        self._frame_buffer.append(frame.copy())
        return self.is_accumulation_complete

    def compute_edge_density(self, image: np.ndarray) -> float:
        """Calculate spatial edge density using Sobel gradient thresholding."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        gray_f32 = gray.astype(np.float32) / 255.0

        gx = cv2.Sobel(gray_f32, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray_f32, cv2.CV_32F, 0, 1, ksize=3)
        mag = cv2.magnitude(gx, gy) / 4.0

        edge_pixels = np.sum(mag >= 0.15)
        total_pixels = float(image.shape[0] * image.shape[1])
        return float(edge_pixels / total_pixels)

    def finalize_capture(
        self,
        allow_override: bool = False,
    ) -> BaselineEpoch:
        """Accumulate buffer into a reference baseline, validate cleanliness, and create epoch."""
        if not self._frame_buffer:
            raise RuntimeError("Cannot finalize baseline: frame buffer is empty")

        # Temporal average across accumulated frames
        stacked = np.stack(self._frame_buffer, axis=0)
        averaged_f32 = np.mean(stacked, axis=0)
        candidate_baseline = np.clip(averaged_f32, 0, 255).astype(np.uint8)

        # Validate board cleanliness
        edge_density = self.compute_edge_density(candidate_baseline)
        if edge_density > self.dirty_board_threshold and not allow_override:
            self._frame_buffer.clear()
            raise DirtyBoardError(edge_density, self.dirty_board_threshold)

        # Accept baseline
        self._epoch_counter += 1
        h, w = candidate_baseline.shape[:2]
        gray_baseline = (
            cv2.cvtColor(candidate_baseline, cv2.COLOR_BGR2GRAY)
            if candidate_baseline.ndim == 3
            else candidate_baseline
        )

        epoch = BaselineEpoch(
            epoch_id=self._epoch_counter,
            timestamp=time.time(),
            edge_density=round(edge_density, 5),
            mean_luminance=round(float(np.mean(gray_baseline)), 2),
            frame_width=w,
            frame_height=h,
            is_clean_verified=True,
            permanent_defect_count=0,
        )

        self._current_baseline = candidate_baseline
        self._current_epoch = epoch
        self._epoch_history.append(epoch)
        self._frame_buffer.clear()
        return epoch

    def roll_epoch(
        self,
        new_frame: np.ndarray,
        verified_residual_fraction: float,
        permanent_defect_mask: Optional[np.ndarray] = None,
        clean_threshold: float = 0.01,
    ) -> BaselineEpoch:
        """Roll to a new baseline epoch after verified clean cleaning pass.

        Excludes known permanent defects from residual calculation.
        """
        if verified_residual_fraction > clean_threshold:
            raise EpochRollRejectedError(verified_residual_fraction, clean_threshold)

        # Update defect mask if provided
        if permanent_defect_mask is not None:
            self._permanent_defect_mask = permanent_defect_mask.copy()

        edge_density = self.compute_edge_density(new_frame)
        self._epoch_counter += 1
        h, w = new_frame.shape[:2]
        gray = cv2.cvtColor(new_frame, cv2.COLOR_BGR2GRAY) if new_frame.ndim == 3 else new_frame

        defect_count = 0
        if self._permanent_defect_mask is not None:
            defect_count = int(np.count_nonzero(self._permanent_defect_mask))

        epoch = BaselineEpoch(
            epoch_id=self._epoch_counter,
            timestamp=time.time(),
            edge_density=round(edge_density, 5),
            mean_luminance=round(float(np.mean(gray)), 2),
            frame_width=w,
            frame_height=h,
            is_clean_verified=True,
            permanent_defect_count=defect_count,
        )

        self._current_baseline = new_frame.copy()
        self._current_epoch = epoch
        self._epoch_history.append(epoch)
        return epoch

    def set_board_dimensions(self, width_mm: float, height_mm: float) -> None:
        """Update section grid for new board dimensions."""
        self.section_grid = SpatialSectionGrid(
            board_width_mm=width_mm,
            board_height_mm=height_mm,
            section_size_mm=self.section_grid.section_size_mm,
            clean_confidence_threshold=self.section_grid.clean_confidence_threshold,
        )

    def update_section_baseline_if_clean(
        self,
        current_frame: np.ndarray,
        active_bbox_mm: Tuple[float, float, float, float],
        residual_mask: Optional[np.ndarray] = None,
        confidence_threshold: float = 0.989,
    ) -> List[BoardSection]:
        """Progressively update baseline frame for each section confirmed cleaned with >= 98.9% confidence."""
        if self._current_baseline is None or current_frame is None:
            return []

        h, w = current_frame.shape[:2]
        if self._current_baseline.shape[:2] != (h, w):
            return []

        h_ratio = h / max(1.0, self.section_grid.board_height_mm)
        w_ratio = w / max(1.0, self.section_grid.board_width_mm)
        refreshed: List[BoardSection] = []

        # If no residual mask provided, compute difference against current baseline
        if residual_mask is None:
            gray_curr = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY) if current_frame.ndim == 3 else current_frame
            gray_base = cv2.cvtColor(self._current_baseline, cv2.COLOR_BGR2GRAY) if self._current_baseline.ndim == 3 else self._current_baseline
            diff = cv2.absdiff(gray_curr, gray_base)
            _, residual_mask = cv2.threshold(diff, 18, 255, cv2.THRESH_BINARY)

        for sec in self.section_grid.get_sections_in_bbox(active_bbox_mm):
            x1_mm, y1_mm, x2_mm, y2_mm = sec.bbox_mm
            px1 = max(0, int(x1_mm * w_ratio))
            py1 = max(0, int(y1_mm * h_ratio))
            px2 = min(w, int(x2_mm * w_ratio))
            py2 = min(h, int(y2_mm * h_ratio))

            if px2 <= px1 or py2 <= py1:
                continue

            sec_mask = residual_mask[py1:py2, px1:px2]
            sec_pixels = float((px2 - px1) * (py2 - py1))
            res_pixels = float(np.count_nonzero(sec_mask))
            residual_frac = res_pixels / max(1.0, sec_pixels)

            confidence = 1.0 - residual_frac
            sec.clean_confidence = round(confidence, 4)

            # Confirm clean and refresh baseline slice if >= 98.9%
            if confidence >= confidence_threshold:
                sec.is_confirmed_clean = True
                sec.last_refreshed_timestamp = time.time()
                sec.refresh_count += 1

                # Update baseline frame in-place for this section
                self._current_baseline[py1:py2, px1:px2] = current_frame[py1:py2, px1:px2].copy()
                refreshed.append(sec)

        return refreshed


_DEFAULT_BASELINE_MANAGER: Optional[BaselineEpochManager] = None


def get_default_baseline_manager() -> BaselineEpochManager:
    """Singleton getter for the baseline manager."""
    global _DEFAULT_BASELINE_MANAGER
    if _DEFAULT_BASELINE_MANAGER is None:
        cfg = get_config()
        _DEFAULT_BASELINE_MANAGER = BaselineEpochManager(
            frames_to_accumulate=cfg.baseline.frames_to_accumulate,
            dirty_board_threshold=cfg.baseline.dirty_board_threshold,
        )
    return _DEFAULT_BASELINE_MANAGER
