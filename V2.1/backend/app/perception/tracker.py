"""Spatial Matching and Ink Object Tracker.

Implements the authoritative spatial matching criteria:
Match exists IF AND ONLY IF:
    IoU(geom_obs, geom_twin) >= matching_iou_threshold (default 0.40)
    AND
    ||centroid_obs - centroid_twin||_2 <= matching_centroid_dist_mm (default 30.0 mm)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple
from pydantic import BaseModel, Field

from .frames import BoundingBox, CoordinateFrame, Polygon2D, validate_frame
from .strokes import DetectedStroke
from ..core.config import get_config


class SpatialMatchCriteria:
    """Config-driven spatial matching validator between observation and twin object."""

    def __init__(
        self,
        iou_threshold: float = 0.40,
        centroid_distance_mm: float = 30.0,
    ) -> None:
        self.iou_threshold = iou_threshold
        self.centroid_distance_mm = centroid_distance_mm

    def is_match(
        self,
        obs_bbox: BoundingBox,
        twin_bbox: BoundingBox,
        obs_centroid: Tuple[float, float],
        twin_centroid: Tuple[float, float],
    ) -> Tuple[bool, float, float]:
        """Evaluate matching criteria. Returns (matched, computed_iou, computed_dist)."""
        dist = (
            (obs_centroid[0] - twin_centroid[0]) ** 2
            + (obs_centroid[1] - twin_centroid[1]) ** 2
        ) ** 0.5
        iou = obs_bbox.iou(twin_bbox)

        matched = bool((iou >= self.iou_threshold) and (dist <= self.centroid_distance_mm))
        return matched, round(iou, 4), round(dist, 2)


class TrackedInkObject(BaseModel):
    """An active tracked ink object in FRAME_BOARD."""
    object_id: int
    polygon: Polygon2D
    bounding_box: BoundingBox
    centroid: Tuple[float, float]
    area_mm2: float
    confidence: float = 1.0
    frames_tracked: int = 1
    unplanned_id_switches: int = 0


class PerceptionSpatialTracker:
    """Perception-level object tracker maintaining IDs and spatial continuity."""

    def __init__(
        self,
        iou_threshold: float = 0.40,
        centroid_distance_mm: float = 30.0,
    ) -> None:
        self.matcher = SpatialMatchCriteria(
            iou_threshold=iou_threshold,
            centroid_distance_mm=centroid_distance_mm,
        )
        self._tracked_objects: Dict[int, TrackedInkObject] = {}
        self._next_id: int = 1

    @property
    def tracked_objects(self) -> Dict[int, TrackedInkObject]:
        return dict(self._tracked_objects)

    def reset(self) -> None:
        self._tracked_objects.clear()
        self._next_id = 1

    def match_and_update(
        self,
        detected_strokes: Sequence[DetectedStroke],
    ) -> List[Tuple[DetectedStroke, Optional[TrackedInkObject]]]:
        """Associate detections with existing tracks using strict IoU + centroid criteria."""
        results: List[Tuple[DetectedStroke, Optional[TrackedInkObject]]] = []
        unmatched_strokes = list(detected_strokes)
        matched_track_ids = set()

        for stroke in unmatched_strokes:
            best_track_id: Optional[int] = None
            best_iou = -1.0

            for track_id, track in self._tracked_objects.items():
                if track_id in matched_track_ids:
                    continue

                matched, iou, dist = self.matcher.is_match(
                    obs_bbox=stroke.bounding_box,
                    twin_bbox=track.bounding_box,
                    obs_centroid=stroke.centroid,
                    twin_centroid=track.centroid,
                )

                if matched and iou > best_iou:
                    best_iou = iou
                    best_track_id = track_id

            if best_track_id is not None:
                matched_track = self._tracked_objects[best_track_id]
                matched_track.polygon = stroke.polygon
                matched_track.bounding_box = stroke.bounding_box
                matched_track.centroid = stroke.centroid
                matched_track.area_mm2 = stroke.area_mm2
                matched_track.confidence = stroke.mean_evidence_score
                matched_track.frames_tracked += 1
                matched_track_ids.add(best_track_id)
                results.append((stroke, matched_track))
            else:
                # Create new track
                new_track = TrackedInkObject(
                    object_id=self._next_id,
                    polygon=stroke.polygon,
                    bounding_box=stroke.bounding_box,
                    centroid=stroke.centroid,
                    area_mm2=stroke.area_mm2,
                    confidence=stroke.mean_evidence_score,
                    frames_tracked=1,
                )
                self._tracked_objects[self._next_id] = new_track
                self._next_id += 1
                results.append((stroke, None))

        return results
