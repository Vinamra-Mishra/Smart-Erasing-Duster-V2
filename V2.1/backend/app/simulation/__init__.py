"""Simulation engine exports for Smart Erasing Duster V2.1."""
from app.simulation.board import VirtualBoard
from app.simulation.duster import VirtualDuster
from app.simulation.cleaning import RealisticCleaningEngine
from app.simulation.metrics import (
    OperationalMetrics,
    compute_precision,
    compute_recall,
    compute_iou,
    compute_fpr,
    compute_residual_fraction,
    compute_cleaning_coverage,
    compute_tracking_stability,
    evaluate_operational_metrics,
)
from app.simulation.scenarios import load_scenario

__all__ = [
    "VirtualBoard",
    "VirtualDuster",
    "RealisticCleaningEngine",
    "OperationalMetrics",
    "compute_precision",
    "compute_recall",
    "compute_iou",
    "compute_fpr",
    "compute_residual_fraction",
    "compute_cleaning_coverage",
    "compute_tracking_stability",
    "evaluate_operational_metrics",
    "load_scenario",
]
