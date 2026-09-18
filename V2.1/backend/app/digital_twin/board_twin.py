from __future__ import annotations

from dataclasses import dataclass, field
import math
import time
from typing import Dict, List, Optional, Tuple
import numpy as np
from shapely.geometry import MultiPoint, Polygon, box

from app.core.config import AppConfig, get_config
from app.schemas.ink import CoordinateFrame, InkObjectDTO, PhysicalState


@dataclass
class InkObject:
    """Authoritative physical entity on the whiteboard surface.

    INVARIANT:
        RESIDUAL_DETECTED is strictly an execution trigger flag in
        execution_state.py, NEVER a physical state in board_twin.py.
    """
    id: str
    state: PhysicalState
    frame_id: CoordinateFrame = CoordinateFrame.FRAME_BOARD
    points: List[List[float]] = field(default_factory=list)
    bbox: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)  # min_x, min_y, max_x, max_y
    centroid: Tuple[float, float] = (0.0, 0.0)
    confidence: float = 1.0
    reclean_attempts: int = 0
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    color_bgr: Tuple[int, int, int] = (0, 0, 0)
    area_mm2: float = 0.0
    is_occluded: bool = False
    holes: List[List[List[float]]] = field(default_factory=list)

    def to_dto(self) -> InkObjectDTO:
        return InkObjectDTO(
            id=self.id,
            state=self.state,
            frame_id=self.frame_id,
            points=self.points,
            bbox=self.bbox,
            centroid=self.centroid,
            confidence=self.confidence,
            reclean_attempts=self.reclean_attempts,
            first_seen=self.first_seen,
            last_seen=self.last_seen,
            color_bgr=self.color_bgr,
            area_mm2=self.area_mm2,
            is_occluded=self.is_occluded,
            holes=self.holes,
        )

    def to_shapely(self) -> Polygon:
        """Construct a Shapely polygon from points or bounding box."""
        if len(self.points) >= 3:
            try:
                poly = Polygon(self.points, holes=self.holes if self.holes else None)
                if poly.is_valid and poly.area > 0:
                    return poly
            except Exception:
                pass
        min_x, min_y, max_x, max_y = self.bbox
        if max_x > min_x and max_y > min_y:
            return box(min_x, min_y, max_x, max_y)
        # Point fallback
        cx, cy = self.centroid
        return box(cx - 1.0, cy - 1.0, cx + 1.0, cy + 1.0)

    def clone(self) -> InkObject:
        return InkObject(
            id=self.id,
            state=self.state,
            frame_id=self.frame_id,
            points=[list(p) for p in self.points],
            bbox=self.bbox,
            centroid=self.centroid,
            confidence=self.confidence,
            reclean_attempts=self.reclean_attempts,
            first_seen=self.first_seen,
            last_seen=self.last_seen,
            color_bgr=self.color_bgr,
            area_mm2=self.area_mm2,
            is_occluded=self.is_occluded,
            holes=[[list(p) for p in h] for h in self.holes],
        )


class BoardTwinStore:
    """Authoritative physical whiteboard store."""

    def __init__(self, config: Optional[AppConfig] = None):
        self.config = config or get_config()
        self.width_mm = int(self.config.system.board_width_mm)
        self.height_mm = int(self.config.system.board_height_mm)

        self.objects: Dict[str, InkObject] = {}
        self.uncertainty_mask: np.ndarray = np.zeros((self.height_mm, self.width_mm), dtype=np.uint8)
        self.board_occlusion_mask: np.ndarray = np.zeros((self.height_mm, self.width_mm), dtype=np.uint8)
        self.permanent_defect_mask: np.ndarray = np.zeros((self.height_mm, self.width_mm), dtype=np.uint8)
        self.epoch_id: int = 1

    def set_board_dimensions(self, width_mm: float, height_mm: float) -> None:
        """Dynamically update metric board dimensions and resize physical masks."""
        new_w = int(round(width_mm))
        new_h = int(round(height_mm))
        if new_w == self.width_mm and new_h == self.height_mm:
            return

        old_unc = self.uncertainty_mask
        old_occ = self.board_occlusion_mask
        old_def = self.permanent_defect_mask

        self.width_mm = new_w
        self.height_mm = new_h

        new_unc = np.zeros((new_h, new_w), dtype=np.uint8)
        new_occ = np.zeros((new_h, new_w), dtype=np.uint8)
        new_def = np.zeros((new_h, new_w), dtype=np.uint8)

        min_h = min(old_unc.shape[0], new_h)
        min_w = min(old_unc.shape[1], new_w)
        new_unc[:min_h, :min_w] = old_unc[:min_h, :min_w]
        new_occ[:min_h, :min_w] = old_occ[:min_h, :min_w]
        new_def[:min_h, :min_w] = old_def[:min_h, :min_w]

        self.uncertainty_mask = new_unc
        self.board_occlusion_mask = new_occ
        self.permanent_defect_mask = new_def

    def add_object(self, obj: InkObject) -> None:
        self.objects[obj.id] = obj

    def add_or_update_object(self, obj: InkObject) -> None:
        self.objects[obj.id] = obj

    def get_object(self, obj_id: str) -> Optional[InkObject]:
        return self.objects.get(obj_id)

    def update_object(self, obj: InkObject) -> None:
        self.objects[obj.id] = obj

    def remove_object(self, obj_id: str) -> None:
        self.objects.pop(obj_id, None)

    def get_state(self, obj_id: str) -> Optional[PhysicalState]:
        obj = self.get_object(obj_id)
        return obj.state if obj else None

    def get_all_objects(self) -> List[InkObject]:
        return list(self.objects.values())

    def get_active_ink_objects(self) -> List[InkObject]:
        """Objects that require wiping (excludes CLEANED, PERMANENT_DEFECT)."""
        active_states = {
            PhysicalState.NEW_INK,
            PhysicalState.STABLE_INK,
            PhysicalState.PARTIALLY_CLEANED,
            PhysicalState.UNKNOWN,
        }
        return [obj for obj in self.objects.values() if obj.state in active_states]

    def find_spatial_match(
        self,
        geom_points: List[List[float]],
        bbox: Optional[Tuple[float, float, float, float]] = None,
        centroid: Optional[Tuple[float, float]] = None,
        iou_thresh: Optional[float] = None,
        dist_thresh: Optional[float] = None,
    ) -> Tuple[Optional[InkObject], float, float]:
        """Spatial match test against existing objects.

        Match condition:
            IoU >= matching_iou_threshold AND centroid_dist <= matching_centroid_dist_mm
        """
        if not self.objects:
            return None, 0.0, float("inf")

        iou_threshold = (
            iou_thresh
            if iou_thresh is not None
            else self.config.perception.matching_iou_threshold
        )
        dist_threshold = (
            dist_thresh
            if dist_thresh is not None
            else self.config.perception.matching_centroid_dist_mm
        )

        # Construct candidate shape
        obs_poly: Polygon
        if len(geom_points) >= 3:
            try:
                obs_poly = Polygon(geom_points)
                if not obs_poly.is_valid:
                    obs_poly = obs_poly.buffer(0)
            except Exception:
                obs_poly = None
        else:
            obs_poly = None

        if obs_poly is None or obs_poly.is_empty:
            if bbox:
                min_x, min_y, max_x, max_y = bbox
                obs_poly = box(min_x, min_y, max_x, max_y)
            elif centroid:
                cx, cy = centroid
                obs_poly = box(cx - 5.0, cy - 5.0, cx + 5.0, cy + 5.0)
            else:
                return None, 0.0, float("inf")

        obs_centroid = centroid or (obs_poly.centroid.x, obs_poly.centroid.y)

        best_match: Optional[InkObject] = None
        best_iou = 0.0
        best_dist = float("inf")

        for obj in self.objects.values():
            twin_poly = obj.to_shapely()
            try:
                intersection = obs_poly.intersection(twin_poly).area
                union = obs_poly.union(twin_poly).area
                iou = intersection / union if union > 0 else 0.0
            except Exception:
                iou = 0.0

            twin_cx, twin_cy = obj.centroid
            dist = math.hypot(obs_centroid[0] - twin_cx, obs_centroid[1] - twin_cy)

            if iou >= iou_threshold and dist <= dist_threshold:
                if iou > best_iou:
                    best_match = obj
                    best_iou = iou
                    best_dist = dist

        return best_match, best_iou, best_dist

    def clone(self) -> BoardTwinStore:
        """Create an independent deep copy of the twin store."""
        new_store = BoardTwinStore(self.config)
        new_store.width_mm = self.width_mm
        new_store.height_mm = self.height_mm
        new_store.epoch_id = self.epoch_id
        new_store.uncertainty_mask = self.uncertainty_mask.copy()
        new_store.board_occlusion_mask = self.board_occlusion_mask.copy()
        new_store.permanent_defect_mask = self.permanent_defect_mask.copy()
        new_store.objects = {obj_id: obj.clone() for obj_id, obj in self.objects.items()}
        return new_store

    def garbage_collect_cleaned(self) -> int:
        """Remove objects marked CLEANED upon epoch roll."""
        to_remove = [obj_id for obj_id, obj in self.objects.items() if obj.state == PhysicalState.CLEANED]
        for obj_id in to_remove:
            del self.objects[obj_id]
        return len(to_remove)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "epoch_id": self.epoch_id,
            "width_mm": self.width_mm,
            "height_mm": self.height_mm,
            "objects": {obj_id: obj.to_dto().model_dump() for obj_id, obj in self.objects.items()},
            "active_count": len(self.get_active_ink_objects()),
            "total_count": len(self.objects),
        }
