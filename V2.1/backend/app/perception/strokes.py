"""Stroke Geometry Extraction and Analysis.

Segments candidate ink masks into distinct stroke polygons with geometric properties:
bounding boxes, centroids, area, contour vertices, and estimated pen thickness.
"""
from __future__ import annotations

from typing import List, Optional, Tuple
import cv2
import numpy as np
from pydantic import BaseModel, Field

from .frames import CoordinateFrame, Point2D, Polygon2D, BoundingBox


class DetectedStroke(BaseModel):
    """Extracted physical ink stroke with geometric measurements in FRAME_BOARD."""
    stroke_id: int
    polygon: Polygon2D
    bounding_box: BoundingBox
    centroid: Tuple[float, float]
    area_mm2: float
    estimated_thickness_mm: float
    mean_evidence_score: float
    color_estimate_bgr: Tuple[int, int, int] = (0, 0, 0)


class StrokeExtractor:
    """Extracts stroke contours and geometrical attributes from fused evidence masks."""

    def __init__(
        self,
        min_area_mm2: float = 15.0,
        max_thickness_mm: float = 12.0,
        approx_epsilon_mm: float = 1.5,
    ) -> None:
        self.min_area = min_area_mm2
        self.max_thickness = max_thickness_mm
        self.approx_epsilon = approx_epsilon_mm

    def estimate_stroke_thickness(self, binary_mask: np.ndarray) -> float:
        """Estimate median stroke thickness using Euclidean distance transform."""
        if not np.any(binary_mask):
            return 0.0
        dist = cv2.distanceTransform(binary_mask.astype(np.uint8), cv2.DIST_L2, 5)
        # Stroke radius is distance to nearest background; thickness is 2 * radius
        foreground_radii = dist[binary_mask > 0]
        if len(foreground_radii) == 0:
            return 0.0
        median_radius = float(np.median(foreground_radii))
        return round(median_radius * 2.0, 2)

    def extract_strokes(
        self,
        candidate_mask: np.ndarray,
        evidence_score_map: np.ndarray,
        current_bgr: Optional[np.ndarray] = None,
    ) -> List[DetectedStroke]:
        """Convert binary candidate mask into a list of DetectedStroke geometries."""
        clean_mask = candidate_mask.astype(np.uint8)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        clean_mask = cv2.morphologyEx(clean_mask, cv2.MORPH_OPEN, kernel)

        contours, hierarchy = cv2.findContours(clean_mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        strokes: List[DetectedStroke] = []

        if contours is None or len(contours) == 0:
            return []

        hier = hierarchy[0] if hierarchy is not None and len(hierarchy) > 0 else []
        stroke_counter = 0

        for i, cnt in enumerate(contours):
            # Only process outer boundaries (parent == -1)
            if len(hier) > 0 and hier[i][3] != -1:
                continue

            area = cv2.contourArea(cnt)
            if area < self.min_area:
                continue

            # Simplify outer contour polygon
            approx = cv2.approxPolyDP(cnt, self.approx_epsilon, closed=True)
            if len(approx) < 3:
                continue

            pts = [(float(p[0][0]), float(p[0][1])) for p in approx]

            # Extract child hole contours if present (e.g. inner holes of looped lines)
            holes: List[List[Tuple[float, float]]] = []
            hole_area_sum = 0.0
            if len(hier) > 0:
                child_idx = hier[i][2]
                while child_idx != -1:
                    hole_cnt = contours[child_idx]
                    h_area = cv2.contourArea(hole_cnt)
                    if h_area >= 6.0:  # Ignore microscopic 1-2px noise holes
                        hole_approx = cv2.approxPolyDP(hole_cnt, self.approx_epsilon, closed=True)
                        if len(hole_approx) >= 3:
                            hole_pts = [(float(p[0][0]), float(p[0][1])) for p in hole_approx]
                            holes.append(hole_pts)
                            hole_area_sum += h_area
                    child_idx = hier[child_idx][0]

            poly = Polygon2D(points=pts, holes=holes, frame=CoordinateFrame.FRAME_BOARD)
            bbox = poly.bounding_box()

            # Create individual stroke mask for thickness and evidence calculation (subtracting holes)
            stroke_mask = np.zeros_like(clean_mask)
            cv2.drawContours(stroke_mask, [cnt], -1, 1, thickness=cv2.FILLED)
            if holes:
                for h_pts in holes:
                    h_cnt = np.array([[[int(p[0]), int(p[1])]] for p in h_pts], dtype=np.int32)
                    cv2.drawContours(stroke_mask, [h_cnt], -1, 0, thickness=cv2.FILLED)

            thickness = self.estimate_stroke_thickness(stroke_mask)
            mean_score = float(np.mean(evidence_score_map[stroke_mask > 0])) if np.any(stroke_mask) else 0.0

            # Color estimation
            mean_bgr = (0, 0, 0)
            if current_bgr is not None and np.any(stroke_mask):
                b_val = int(np.mean(current_bgr[:, :, 0][stroke_mask > 0]))
                g_val = int(np.mean(current_bgr[:, :, 1][stroke_mask > 0]))
                r_val = int(np.mean(current_bgr[:, :, 2][stroke_mask > 0]))
                mean_bgr = (b_val, g_val, r_val)

            stroke_counter += 1
            strokes.append(
                DetectedStroke(
                    stroke_id=stroke_counter,
                    polygon=poly,
                    bounding_box=bbox,
                    centroid=poly.compute_centroid(),
                    area_mm2=max(0.0, round(area - hole_area_sum, 2)),
                    estimated_thickness_mm=thickness,
                    mean_evidence_score=round(mean_score, 4),
                    color_estimate_bgr=mean_bgr,
                )
            )

        return strokes

    def detect_whiteboard_ink(
        self,
        board_frame: np.ndarray,
        baseline_frame: Optional[np.ndarray] = None,
        contrast_threshold: float = 24.0,
        mask_browser_ui: bool = False,
    ) -> List[DetectedStroke]:
        """Detect handwritten marker text, drawings, and strokes on the whiteboard surface.

        Args:
            board_frame: Rectified BGR or grayscale board image in FRAME_BOARD.
            baseline_frame: Optional clean reference baseline image.
            contrast_threshold: Sensitivity threshold for differential ink changes.
            mask_browser_ui: When True, filters fixed browser toolbars/tabs (for web whiteboard testing).

        Returns:
            List of DetectedStroke objects with contours, centroids, and areas.
        """
        if board_frame is None or board_frame.size == 0:
            return []

        if board_frame.ndim == 2:
            gray = board_frame
            bgr = cv2.cvtColor(board_frame, cv2.COLOR_GRAY2BGR)
        else:
            gray = cv2.cvtColor(board_frame, cv2.COLOR_BGR2GRAY)
            bgr = board_frame

        h, w = gray.shape[:2]
        total_board_area = float(h * w)

        if baseline_frame is not None:
            # --- Differential Baseline Detection Mode ---
            if baseline_frame.shape[:2] != (h, w):
                baseline_frame = cv2.resize(baseline_frame, (w, h))

            if baseline_frame.ndim == 2:
                base_gray = baseline_frame
                base_bgr = cv2.cvtColor(baseline_frame, cv2.COLOR_GRAY2BGR)
            else:
                base_gray = cv2.cvtColor(baseline_frame, cv2.COLOR_BGR2GRAY)
                base_bgr = baseline_frame

            # Multi-channel color diff captures all ink colors (black, blue, red, green, etc.)
            diff_bgr = cv2.absdiff(bgr, base_bgr)
            diff_color = np.max(diff_bgr, axis=2)

            # Luminance darkening: ink is darker than baseline board surface
            diff_dark = cv2.subtract(base_gray, gray)

            # Combined difference metric
            diff = cv2.max(diff_color, diff_dark)

            # Smooth slight sensor noise
            diff_smooth = cv2.GaussianBlur(diff, (3, 3), 0)

            # Threshold differential changes
            _, ink_raw = cv2.threshold(diff_smooth, int(contrast_threshold), 255, cv2.THRESH_BINARY)
            candidate_mask = ink_raw

        else:
            # --- Standalone High-Precision Ink Detection (Adaptive + Chromatic + Morphological) ---
            # 1. High-precision local adaptive Gaussian thresholding (preserves text under non-uniform illumination)
            blurred = cv2.GaussianBlur(gray, (3, 3), 0)
            adaptive_ink = cv2.adaptiveThreshold(
                blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 27, 5
            )

            # 2. Chromatic dip for blue and colored markers: (B - R) contrast
            b, g, r = cv2.split(bgr)
            diff_br = cv2.subtract(b, r)
            _, blue_ink = cv2.threshold(diff_br, 15, 255, cv2.THRESH_BINARY)

            # 3. Morphological black-hat for broad strokes
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21))
            bg = cv2.morphologyEx(gray, cv2.MORPH_DILATE, kernel)
            diff_bg = cv2.subtract(bg, gray)
            blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, kernel)
            diff_morph = cv2.max(diff_bg, blackhat)

            wb_mask = (bg > 75).astype(np.uint8) * 255
            _, morph_ink = cv2.threshold(diff_morph, int(contrast_threshold), 255, cv2.THRESH_BINARY)
            morph_ink = cv2.bitwise_and(morph_ink, wb_mask)

            # Combine signals
            candidate_mask = cv2.bitwise_or(adaptive_ink, blue_ink)
            candidate_mask = cv2.bitwise_or(candidate_mask, morph_ink)
            diff = cv2.max(diff_morph, diff_br)

        # Zero out only the outermost physical edge (4px) to avoid border bezel snapping
        candidate_mask[:4, :] = 0
        candidate_mask[-4:, :] = 0
        candidate_mask[:, :4] = 0
        candidate_mask[:, -4:] = 0

        # Optional browser UI zone exclusion (only when requested for web whiteboard testing)
        if mask_browser_ui and h >= 400 and w >= 600:
            # Top browser chrome / tab bar & header
            candidate_mask[:120, :] = 0
            # Left tool palette dock
            candidate_mask[:, :120] = 0
            # Floating bottom pen toolbar (centered horizontally, ~bottom 110px)
            dock_x1 = int(w * 0.22)
            dock_x2 = int(w * 0.78)
            candidate_mask[max(0, h - 110):, dock_x1:dock_x2] = 0
            # Bottom-left undo/redo and page controls
            candidate_mask[max(0, h - 85):, :200] = 0
            # Bottom-right zoom and fit controls
            candidate_mask[max(0, h - 85):, max(0, w - 260):] = 0

        # Filter out massive connected components (human presenter / clothes / broad shadows)
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(candidate_mask, connectivity=8)
        filtered_mask = np.zeros_like(candidate_mask)

        # Max area for an individual stroke/word cluster is ~8% of board area
        max_stroke_area = 0.08 * total_board_area

        for label in range(1, num_labels):
            area = stats[label, cv2.CC_STAT_AREA]
            w_comp = stats[label, cv2.CC_STAT_WIDTH]
            h_comp = stats[label, cv2.CC_STAT_HEIGHT]

            # Reject massive objects (e.g. human body, full board occluders)
            if area > max_stroke_area or w_comp > 0.7 * w or h_comp > 0.7 * h:
                continue

            # Reject tiny dust/noise
            if area < self.min_area:
                continue

            filtered_mask[labels == label] = 255

        # Extract strokes with geometric properties
        evidence_score_map = (diff.astype(np.float32) / 255.0)
        return self.extract_strokes(filtered_mask, evidence_score_map, current_bgr=bgr)

