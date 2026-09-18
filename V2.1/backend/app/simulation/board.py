"""Multi-layer virtual whiteboard simulation in FRAME_BOARD.

Maintains four distinct physical/optical layers:
1. Baseline Layer: Background whiteboard surface with subtle illumination.
2. Ink Layer: Physical dry-erase marker strokes.
3. Defect Layer: Permanent marks, scratches, or stains immune to erasing.
4. Projector Layer: Additive digital light projections (Mode A/B decoupling).
"""
from __future__ import annotations

import uuid
from typing import Dict, List, Sequence, Tuple
import cv2
import numpy as np
from shapely.geometry import MultiPolygon, Point, Polygon
from shapely.ops import unary_union

from app.core.config import get_config
from app.schemas.ink import CoordinateFrame, InkObjectDTO, PhysicalState


class VirtualBoard:
    """Virtual whiteboard maintaining layered ground-truth raster and vector states."""

    def __init__(
        self,
        width_mm: float | None = None,
        height_mm: float | None = None,
    ) -> None:
        config = get_config()
        self.width_mm = int(width_mm or config.system.board_width_mm)
        self.height_mm = int(height_mm or config.system.board_height_mm)

        # Layers (height x width x 3 for BGR or single-channel masks)
        self.baseline_bgr = np.full((self.height_mm, self.width_mm, 3), 245, dtype=np.uint8)
        self.ink_mask = np.zeros((self.height_mm, self.width_mm), dtype=np.float32)
        self.ink_color_map = np.zeros((self.height_mm, self.width_mm, 3), dtype=np.uint8)
        self.defect_mask = np.zeros((self.height_mm, self.width_mm), dtype=np.float32)
        self.defect_color_map = np.zeros((self.height_mm, self.width_mm, 3), dtype=np.uint8)
        self.projector_bgr = np.zeros((self.height_mm, self.width_mm, 3), dtype=np.uint8)

        # Vector object tracking
        self.ink_objects: Dict[str, InkObjectDTO] = {}
        self.defect_objects: Dict[str, Polygon] = {}

    def set_board_dimensions(self, width_mm: float, height_mm: float) -> None:
        """Dynamically update virtual board dimensions and resize simulation layers."""
        new_w = int(round(width_mm))
        new_h = int(round(height_mm))
        if new_w == self.width_mm and new_h == self.height_mm:
            return

        self.width_mm = new_w
        self.height_mm = new_h

        self.baseline_bgr = np.full((new_h, new_w, 3), 245, dtype=np.uint8)
        self.ink_mask = np.zeros((new_h, new_w), dtype=np.float32)
        self.ink_color_map = np.zeros((new_h, new_w, 3), dtype=np.uint8)
        self.defect_mask = np.zeros((new_h, new_w), dtype=np.float32)
        self.defect_color_map = np.zeros((new_h, new_w, 3), dtype=np.uint8)
        self.projector_bgr = np.zeros((new_h, new_w, 3), dtype=np.uint8)

    def clear(self) -> None:
        """Reset board to clean baseline."""
        self.ink_mask.fill(0.0)
        self.ink_color_map.fill(0)
        self.defect_mask.fill(0.0)
        self.defect_color_map.fill(0)
        self.projector_bgr.fill(0)
        self.ink_objects.clear()
        self.defect_objects.clear()

    def add_stroke(
        self,
        points: Sequence[Sequence[float]],
        width_mm: float = 6.0,
        color_bgr: Tuple[int, int, int] = (20, 20, 20),
        object_id: str | None = None,
    ) -> str:
        """Draw an ink stroke on the ink layer and register in ground truth."""
        if len(points) < 2:
            return ""

        oid = object_id or f"ink_{uuid.uuid4().hex[:8]}"
        pts = np.array(points, dtype=np.int32)
        int_width = max(1, int(round(width_mm)))

        # Draw on raster mask and color map
        cv2.polylines(self.ink_mask, [pts], isClosed=False, color=1.0, thickness=int_width)
        cv2.polylines(self.ink_color_map, [pts], isClosed=False, color=color_bgr, thickness=int_width)

        # Build polygon representation
        pts_list = [list(map(float, p)) for p in points]
        # Line buffer to polygon
        from shapely.geometry import LineString
        line = LineString(pts_list)
        poly = line.buffer(width_mm / 2.0)

        min_x, min_y, max_x, max_y = poly.bounds
        self.ink_objects[oid] = InkObjectDTO(
            id=oid,
            state=PhysicalState.STABLE_INK,
            frame_id=CoordinateFrame.FRAME_BOARD,
            points=list(poly.exterior.coords),
            bbox=(min_x, min_y, max_x, max_y),
            centroid=(poly.centroid.x, poly.centroid.y),
            confidence=1.0,
            color_bgr=color_bgr,
            area_mm2=poly.area,
        )
        return oid

    def add_defect(
        self,
        points: Sequence[Sequence[float]],
        width_mm: float = 4.0,
        color_bgr: Tuple[int, int, int] = (40, 40, 40),
        defect_id: str | None = None,
    ) -> str:
        """Add a permanent surface defect (scratch/stain) immune to wiping."""
        did = defect_id or f"defect_{uuid.uuid4().hex[:8]}"
        pts = np.array(points, dtype=np.int32)
        int_width = max(1, int(round(width_mm)))

        cv2.polylines(self.defect_mask, [pts], isClosed=False, color=1.0, thickness=int_width)
        cv2.polylines(self.defect_color_map, [pts], isClosed=False, color=color_bgr, thickness=int_width)

        from shapely.geometry import LineString
        poly = LineString([list(map(float, p)) for p in points]).buffer(width_mm / 2.0)
        self.defect_objects[did] = poly
        return did

    def set_projector_overlay(self, overlay_bgr: np.ndarray) -> None:
        """Set additive projector light overlay (Mode A/B simulation)."""
        if overlay_bgr.shape[:2] == (self.height_mm, self.width_mm):
            self.projector_bgr = overlay_bgr.copy()
        else:
            self.projector_bgr = cv2.resize(overlay_bgr, (self.width_mm, self.height_mm))

    def clear_projector(self) -> None:
        """Turn off digital projector light."""
        self.projector_bgr.fill(0)

    def render_composite(self) -> np.ndarray:
        """Composite all layers into an authentic BGR image representing camera view.

        Formula:
            Clean Baseline - Ink Layer - Defect Layer + Projector Light
        """
        composite = self.baseline_bgr.astype(np.float32)

        # Subtract ink
        ink_alpha = np.expand_dims(np.clip(self.ink_mask, 0.0, 1.0), axis=-1)
        ink_color = self.ink_color_map.astype(np.float32)
        composite = composite * (1.0 - ink_alpha) + ink_color * ink_alpha

        # Subtract permanent defects
        defect_alpha = np.expand_dims(np.clip(self.defect_mask, 0.0, 1.0), axis=-1)
        defect_color = self.defect_color_map.astype(np.float32)
        composite = composite * (1.0 - defect_alpha) + defect_color * defect_alpha

        # Add projector light (additive illumination)
        proj = self.projector_bgr.astype(np.float32)
        composite = np.clip(composite + proj, 0.0, 255.0)

        return composite.astype(np.uint8)

    def compute_edge_density(self) -> float:
        """Calculate high-frequency edge density for baseline validation."""
        gray = cv2.cvtColor(self.render_composite(), cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        edge_pixels = int(np.count_nonzero(edges))
        total_pixels = self.width_mm * self.height_mm
        return edge_pixels / float(total_pixels)

    def get_ground_truth_ink_polygon(self) -> Polygon | MultiPolygon:
        """Extract unified Shapely polygon representing ground-truth ink."""
        polys: List[Polygon] = []
        for obj in self.ink_objects.values():
            if len(obj.points) >= 3:
                p = Polygon(obj.points)
                if p.is_valid and not p.is_empty and p.area > 0.0:
                    polys.append(p)
        if not polys:
            return Polygon()
        return unary_union(polys)

    def get_ground_truth_defect_polygon(self) -> Polygon | MultiPolygon:
        """Extract unified Shapely polygon representing permanent defects."""
        if not self.defect_objects:
            return Polygon()
        return unary_union(list(self.defect_objects.values()))
