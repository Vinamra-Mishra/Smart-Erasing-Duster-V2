"""Temporal Persistence and Stroke Candidate Verification.

Filters out transient frame jitter, camera sensor noise, and fleeting motions
by requiring consistent spatial persistence over multiple consecutive frames.
"""
from __future__ import annotations

from typing import Dict, List, Tuple
import numpy as np

from .strokes import DetectedStroke


class CandidateTrack:
    """Internal tracker record for a candidate ink stroke."""

    def __init__(self, track_id: int, initial_stroke: DetectedStroke) -> None:
        self.track_id = track_id
        self.latest_stroke = initial_stroke
        self.hit_streak: int = 1
        self.miss_count: int = 0
        self.first_seen_frame: int = 0
        self.last_seen_frame: int = 0

    @property
    def centroid(self) -> Tuple[float, float]:
        return self.latest_stroke.centroid

    @property
    def area(self) -> float:
        return self.latest_stroke.area_mm2


class TemporalPersistenceFilter:
    """Tracks candidate strokes across consecutive frames to confirm real ink."""

    def __init__(
        self,
        persistence_threshold_frames: int = 2,
        max_miss_frames: int = 3,
        centroid_tolerance_mm: float = 30.0,
    ) -> None:
        self.persistence_threshold = persistence_threshold_frames
        self.max_miss_frames = max_miss_frames
        self.centroid_tolerance = centroid_tolerance_mm
        self._tracks: Dict[int, CandidateTrack] = {}
        self._next_track_id: int = 1
        self._frame_counter: int = 0

    def reset(self) -> None:
        """Clear all active tracks."""
        self._tracks.clear()
        self._next_track_id = 1
        self._frame_counter = 0

    def update(
        self,
        observed_strokes: List[DetectedStroke],
    ) -> Tuple[List[DetectedStroke], List[DetectedStroke]]:
        """Update tracks with new observations.

        Returns:
            Tuple[confirmed_strokes, pending_candidate_strokes]
        """
        self._frame_counter += 1
        unmatched_strokes = list(observed_strokes)
        matched_track_ids = set()

        # Associate observations with existing candidate tracks
        for track_id, track in list(self._tracks.items()):
            best_match_idx = -1
            min_dist = float("inf")

            for idx, stroke in enumerate(unmatched_strokes):
                dist = (
                    (stroke.centroid[0] - track.centroid[0]) ** 2
                    + (stroke.centroid[1] - track.centroid[1]) ** 2
                ) ** 0.5
                if dist <= self.centroid_tolerance and dist < min_dist:
                    min_dist = dist
                    best_match_idx = idx

            if best_match_idx >= 0:
                matched_stroke = unmatched_strokes.pop(best_match_idx)
                track.latest_stroke = matched_stroke
                track.hit_streak += 1
                track.miss_count = 0
                track.last_seen_frame = self._frame_counter
                matched_track_ids.add(track_id)
            else:
                track.miss_count += 1

        # Delete expired tracks
        for track_id, track in list(self._tracks.items()):
            if track.miss_count > self.max_miss_frames:
                del self._tracks[track_id]

        # Register new candidate tracks for remaining unmatched observations
        for stroke in unmatched_strokes:
            new_track = CandidateTrack(self._next_track_id, stroke)
            new_track.first_seen_frame = self._frame_counter
            new_track.last_seen_frame = self._frame_counter
            self._tracks[self._next_track_id] = new_track
            self._next_track_id += 1

        # Partition into confirmed and pending
        confirmed: List[DetectedStroke] = []
        pending: List[DetectedStroke] = []

        for track in self._tracks.values():
            if track.hit_streak >= self.persistence_threshold and track.miss_count == 0:
                confirmed.append(track.latest_stroke)
            elif track.miss_count == 0:
                pending.append(track.latest_stroke)

        return confirmed, pending
