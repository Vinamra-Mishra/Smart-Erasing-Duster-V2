"""Realistic physical wiping simulation with imperfect efficiency and residual generation.

Simulates eraser pad interaction on the multi-layer virtual board:
- Erases ink under footprint with configurable nominal efficiency (default 0.85).
- Generates fine residual ink (1 - efficiency) on initial wipe passes.
- Preserves permanent surface defects 100% (immune to wiping).
"""
from __future__ import annotations

from typing import List, Tuple
import cv2
import numpy as np
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

from app.core.config import get_config
from app.schemas.ink import PhysicalState
from app.simulation.board import VirtualBoard


class RealisticCleaningEngine:
    """Simulates physical wiping of dry-erase ink and residual dynamics."""

    def __init__(
        self,
        nominal_efficiency: float | None = None,
        clean_threshold: float | None = None,
    ) -> None:
        config = get_config()
        self.nominal_efficiency = (
            nominal_efficiency if nominal_efficiency is not None else config.cleaning.nominal_efficiency
        )
        self.clean_threshold = (
            clean_threshold if clean_threshold is not None else config.cleaning.clean_threshold
        )

    def apply_wipe(
        self,
        board: VirtualBoard,
        swept_footprint: Polygon | MultiPolygon,
        efficiency_override: float | None = None,
    ) -> float:
        """Apply a wiping pass over the virtual board.

        Args:
            board: Target VirtualBoard instance.
            swept_footprint: Contact polygon swept by duster actuator.
            efficiency_override: Optional pass efficiency (e.g. 0.85).

        Returns:
            Erased ink area in mm^2 during this pass.
        """
        if swept_footprint is None or swept_footprint.is_empty:
            return 0.0

        eff = efficiency_override if efficiency_override is not None else self.nominal_efficiency
        eff = min(1.0, max(0.0, eff))

        # 1. Raster wipe
        # Create binary mask of swept footprint
        footprint_mask = np.zeros((board.height_mm, board.width_mm), dtype=np.uint8)
        if isinstance(swept_footprint, Polygon):
            polys = [swept_footprint]
        else:
            polys = list(swept_footprint.geoms)

        for poly in polys:
            coords = np.array(poly.exterior.coords, dtype=np.int32)
            cv2.fillPoly(footprint_mask, [coords], 255)

        # Apply imperfect erasing to ink layer
        contact_pixels = (footprint_mask > 0)
        initial_ink_sum = float(np.sum(board.ink_mask[contact_pixels]))

        # Reduce ink density by efficiency: ink = ink * (1 - eff)
        board.ink_mask[contact_pixels] *= (1.0 - eff)
        # Drop negligible residual flecks below threshold
        board.ink_mask[board.ink_mask < 0.02] = 0.0

        post_ink_sum = float(np.sum(board.ink_mask[contact_pixels]))
        erased_area_approx = initial_ink_sum - post_ink_sum

        # NOTE: Defect layer is strictly NOT modified (100% preserved)

        # 2. Vector update for ink objects
        self._update_vector_ink_objects(board, swept_footprint, eff)

        return erased_area_approx

    def _update_vector_ink_objects(
        self,
        board: VirtualBoard,
        swept_footprint: Polygon | MultiPolygon,
        eff: float,
    ) -> None:
        """Update geometric boundaries and physical states of tracked ink objects."""
        for oid, obj in list(board.ink_objects.items()):
            if len(obj.points) < 3:
                continue

            orig_poly = Polygon(obj.points)
            if not orig_poly.is_valid:
                orig_poly = orig_poly.buffer(0)

            if not orig_poly.intersects(swept_footprint):
                continue

            # Calculate remaining geometry
            if eff >= 0.99:
                remaining = orig_poly.difference(swept_footprint)
            else:
                # Retain a fine boundary residual fringe proportional to (1 - eff)
                diff = orig_poly.difference(swept_footprint)
                overlap = orig_poly.intersection(swept_footprint)
                fringe_width = max(0.2, (1.0 - eff) * 1.5)
                residual_fringe = overlap.buffer(-fringe_width)
                remaining = diff.union(residual_fringe)

            if remaining.is_empty or remaining.area < 5.0:
                obj.state = PhysicalState.CLEANED
                obj.area_mm2 = 0.0
                obj.points = []
            else:
                obj.state = PhysicalState.PARTIALLY_CLEANED
                obj.area_mm2 = round(remaining.area, 2)
                # Pick largest polygon if multipolygon
                if isinstance(remaining, MultiPolygon):
                    largest = max(remaining.geoms, key=lambda p: p.area)
                    obj.points = list(largest.exterior.coords)
                    obj.centroid = (largest.centroid.x, largest.centroid.y)
                    obj.bbox = largest.bounds
                else:
                    obj.points = list(remaining.exterior.coords)
                    obj.centroid = (remaining.centroid.x, remaining.centroid.y)
                    obj.bbox = remaining.bounds
