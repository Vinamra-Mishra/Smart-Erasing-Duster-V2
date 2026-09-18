"""Exact operational metrics in physical whiteboard coordinates (FRAME_BOARD).

Implements precision, recall, IoU, false positive rate, residual fraction,
cleaning coverage, and tracking stability formulas according to the V2.1 specification.
"""
from __future__ import annotations

from typing import Union
from pydantic import BaseModel, Field
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry


class OperationalMetrics(BaseModel):
    """Operational metrics report evaluated in physical board coordinates."""
    precision: float = Field(default=1.0, ge=0.0, le=1.0)
    recall: float = Field(default=1.0, ge=0.0, le=1.0)
    iou: float = Field(default=1.0, ge=0.0, le=1.0)
    fpr: float = Field(default=0.0, ge=0.0, le=1.0)
    residual_fraction: float = Field(default=0.0, ge=0.0)
    cleaning_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    tracking_stability: float = Field(default=1.0, ge=0.0, le=1.0)


def _geom_area(geom: BaseGeometry | None) -> float:
    """Safely return geometry area in mm^2."""
    if geom is None or geom.is_empty:
        return 0.0
    return float(geom.area)


def compute_precision(
    detected_geom: BaseGeometry | None,
    ground_truth_geom: BaseGeometry | None,
) -> float:
    """Precision = Area(Detected ∩ GroundTruth) / Area(Detected).

    Returns 1.0 if both are empty. Returns 0.0 if detected exists but GT is empty.
    """
    area_det = _geom_area(detected_geom)
    area_gt = _geom_area(ground_truth_geom)

    if area_det == 0.0 and area_gt == 0.0:
        return 1.0
    if area_det == 0.0:
        return 0.0

    intersection = detected_geom.intersection(ground_truth_geom)
    area_intersection = _geom_area(intersection)
    return round(min(1.0, max(0.0, area_intersection / area_det)), 6)


def compute_recall(
    detected_geom: BaseGeometry | None,
    ground_truth_geom: BaseGeometry | None,
) -> float:
    """Recall = Area(Detected ∩ GroundTruth) / Area(GroundTruth).

    Returns 1.0 if both are empty. Returns 0.0 if GT exists but detected is empty.
    """
    area_det = _geom_area(detected_geom)
    area_gt = _geom_area(ground_truth_geom)

    if area_det == 0.0 and area_gt == 0.0:
        return 1.0
    if area_gt == 0.0:
        return 1.0 if area_det == 0.0 else 0.0

    intersection = detected_geom.intersection(ground_truth_geom)
    area_intersection = _geom_area(intersection)
    return round(min(1.0, max(0.0, area_intersection / area_gt)), 6)


def compute_iou(
    detected_geom: BaseGeometry | None,
    ground_truth_geom: BaseGeometry | None,
) -> float:
    """IoU = Area(Detected ∩ GroundTruth) / Area(Detected ∪ GroundTruth).

    Returns 1.0 if both are empty.
    """
    area_det = _geom_area(detected_geom)
    area_gt = _geom_area(ground_truth_geom)

    if area_det == 0.0 and area_gt == 0.0:
        return 1.0
    if area_det == 0.0 or area_gt == 0.0:
        return 0.0

    intersection = detected_geom.intersection(ground_truth_geom)
    union = detected_geom.union(ground_truth_geom)
    area_int = _geom_area(intersection)
    area_union = _geom_area(union)

    if area_union == 0.0:
        return 1.0
    return round(min(1.0, max(0.0, area_int / area_union)), 6)


def compute_fpr(
    detected_geom: BaseGeometry | None,
    ground_truth_geom: BaseGeometry | None,
    board_area_mm2: float,
) -> float:
    """False Positive Rate = Area(Detected \\ GroundTruth) / Area(CleanBoard).

    where Area(CleanBoard) = Area(Board) - Area(GroundTruth).
    """
    if board_area_mm2 <= 0.0:
        raise ValueError("Board area must be positive")

    area_gt = _geom_area(ground_truth_geom)
    clean_board_area = max(1e-6, board_area_mm2 - area_gt)

    if detected_geom is None or detected_geom.is_empty:
        return 0.0

    if ground_truth_geom is None or ground_truth_geom.is_empty:
        diff_area = _geom_area(detected_geom)
    else:
        diff = detected_geom.difference(ground_truth_geom)
        diff_area = _geom_area(diff)

    return round(min(1.0, max(0.0, diff_area / clean_board_area)), 6)


def compute_residual_fraction(
    residual_post_clean: BaseGeometry | None,
    original_pre_clean: BaseGeometry | None,
) -> float:
    """Residual Fraction = Area(Residual Post-Clean) / Area(Original Pre-Clean)."""
    orig_area = _geom_area(original_pre_clean)
    if orig_area == 0.0:
        return 0.0

    res_area = _geom_area(residual_post_clean)
    return round(max(0.0, res_area / orig_area), 6)


def compute_cleaning_coverage(
    swept_footprint: BaseGeometry | None,
    target_geom: BaseGeometry | None,
) -> float:
    """Cleaning Coverage = Area(Swept Footprint ∩ Target) / Area(Target)."""
    target_area = _geom_area(target_geom)
    if target_area == 0.0:
        return 1.0
    if swept_footprint is None or swept_footprint.is_empty:
        return 0.0

    covered = swept_footprint.intersection(target_geom)
    covered_area = _geom_area(covered)
    return round(min(1.0, max(0.0, covered_area / target_area)), 6)


def compute_tracking_stability(
    unplanned_id_switches: int,
    lifetime_frames: int,
) -> float:
    """Tracking Stability = 1.0 - (Unplanned ID switches / Lifetime frames)."""
    if lifetime_frames <= 0:
        return 1.0
    ratio = max(0, unplanned_id_switches) / float(lifetime_frames)
    return round(min(1.0, max(0.0, 1.0 - ratio)), 6)


def evaluate_operational_metrics(
    detected_geom: BaseGeometry | None,
    ground_truth_geom: BaseGeometry | None,
    board_area_mm2: float = 700000.0,  # default 1000 * 700 mm
    residual_geom: BaseGeometry | None = None,
    swept_footprint: BaseGeometry | None = None,
    unplanned_id_switches: int = 0,
    lifetime_frames: int = 100,
) -> OperationalMetrics:
    """Compute complete suite of operational metrics."""
    return OperationalMetrics(
        precision=compute_precision(detected_geom, ground_truth_geom),
        recall=compute_recall(detected_geom, ground_truth_geom),
        iou=compute_iou(detected_geom, ground_truth_geom),
        fpr=compute_fpr(detected_geom, ground_truth_geom, board_area_mm2),
        residual_fraction=compute_residual_fraction(residual_geom, ground_truth_geom),
        cleaning_coverage=compute_cleaning_coverage(swept_footprint, ground_truth_geom),
        tracking_stability=compute_tracking_stability(unplanned_id_switches, lifetime_frames),
    )
