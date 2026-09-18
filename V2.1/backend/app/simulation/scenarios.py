"""Deterministic test scenarios 1..6 for Digital Twin verification.

Presets:
1: Single Stroke
2: Multiple Clusters
3: Human Hand Occlusion (area >= 4.5%)
4: Projector Artifacts (Mode A additive light)
5: Stubborn Residual -> Cap Hit (promotion to PERMANENT_DEFECT)
6: Dirty Board Baseline Abort (edge density > dirty_board_threshold)
"""
from __future__ import annotations

from typing import Any, Dict
import cv2
import numpy as np

from app.simulation.board import VirtualBoard


def load_scenario_1_single_stroke(board: VirtualBoard) -> Dict[str, Any]:
    """Scenario 1: Single clean stroke in the board center."""
    board.clear()
    pts = [[400.0, 350.0], [500.0, 350.0], [600.0, 350.0]]
    oid = board.add_stroke(pts, width_mm=8.0, color_bgr=(30, 30, 30), object_id="ink_s1_stroke")
    return {
        "scenario_id": 1,
        "name": "Single Stroke",
        "description": "Single centered dry-erase stroke",
        "stroke_ids": [oid],
    }


def load_scenario_2_multiple_clusters(board: VirtualBoard) -> Dict[str, Any]:
    """Scenario 2: Three spatially separated ink clusters for TSP and multi-target test."""
    board.clear()
    # Cluster 1: Top-left
    c1 = board.add_stroke(
        [[200.0, 180.0], [250.0, 220.0], [280.0, 180.0]],
        width_mm=6.0,
        color_bgr=(180, 20, 20),
        object_id="ink_s2_c1",
    )
    # Cluster 2: Top-right
    c2 = board.add_stroke(
        [[720.0, 200.0], [780.0, 200.0], [800.0, 260.0]],
        width_mm=6.0,
        color_bgr=(20, 140, 20),
        object_id="ink_s2_c2",
    )
    # Cluster 3: Bottom-center
    c3 = board.add_stroke(
        [[450.0, 480.0], [520.0, 480.0], [550.0, 520.0]],
        width_mm=8.0,
        color_bgr=(20, 20, 180),
        object_id="ink_s2_c3",
    )
    return {
        "scenario_id": 2,
        "name": "Multiple Clusters",
        "description": "Three separated ink clusters across the whiteboard",
        "stroke_ids": [c1, c2, c3],
    }


def load_scenario_3_human_hand_occlusion(board: VirtualBoard) -> Dict[str, Any]:
    """Scenario 3: Ink stroke with an active occluder blob >= 4.5% of board area."""
    board.clear()
    oid = board.add_stroke(
        [[350.0, 300.0], [450.0, 300.0], [550.0, 300.0]],
        width_mm=8.0,
        color_bgr=(30, 30, 30),
        object_id="ink_s3_occluded",
    )
    # 4.5% of 1000x700 mm is 31,500 mm^2. We create an occluder ~ 35,000 mm^2 (e.g. 200 x 180 mm)
    occluder_poly = [
        [360.0, 220.0],
        [560.0, 220.0],
        [560.0, 400.0],
        [360.0, 400.0],
    ]
    # Draw occluding body directly on baseline to simulate physical arm/hand
    pts = np.array(occluder_poly, dtype=np.int32)
    cv2.fillPoly(board.baseline_bgr, [pts], (90, 120, 160))  # Arm skin/cloth tone

    return {
        "scenario_id": 3,
        "name": "Human Hand Occlusion",
        "description": "Large occluder (36,000 mm^2 >= 4.5% board area) covering ink stroke",
        "stroke_ids": [oid],
        "occluder_area_mm2": 36000.0,
        "occluder_polygon": occluder_poly,
    }


def load_scenario_4_projector_artifacts(board: VirtualBoard) -> Dict[str, Any]:
    """Scenario 4: Board with ink and additive digital projector overlay."""
    board.clear()
    oid = board.add_stroke(
        [[300.0, 200.0], [400.0, 200.0]],
        width_mm=6.0,
        color_bgr=(20, 20, 20),
        object_id="ink_s4_real",
    )
    # Additive projector overlay (Mode A/B light)
    proj_overlay = np.zeros((board.height_mm, board.width_mm, 3), dtype=np.uint8)
    # Projected bright blue-cyan grid and digital text box
    cv2.rectangle(proj_overlay, (500, 150), (850, 400), (220, 180, 50), -1)
    cv2.putText(
        proj_overlay,
        "PROJECTOR LIGHT",
        (520, 280),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.5,
        (255, 255, 255),
        3,
    )
    board.set_projector_overlay(proj_overlay)

    return {
        "scenario_id": 4,
        "name": "Projector Artifacts",
        "description": "Real ink accompanied by additive digital projector overlay",
        "stroke_ids": [oid],
        "projector_region": [500, 150, 850, 400],
    }


def load_scenario_5_stubborn_residual_cap_hit(board: VirtualBoard) -> Dict[str, Any]:
    """Scenario 5: Stubborn mark / permanent defect leading to 3 re-cleans and cap hit."""
    board.clear()
    # Real ink mark
    oid = board.add_stroke(
        [[480.0, 320.0], [540.0, 320.0]],
        width_mm=7.0,
        color_bgr=(20, 20, 20),
        object_id="ink_s5_stubborn",
    )
    # Underlying permanent defect that refuses to erase
    did = board.add_defect(
        [[490.0, 320.0], [530.0, 320.0]],
        width_mm=5.0,
        color_bgr=(15, 15, 15),
        defect_id="defect_s5_permanent",
    )
    return {
        "scenario_id": 5,
        "name": "Stubborn Residual -> Cap Hit",
        "description": "Ink over permanent defect; wiping leaves mark, triggering 3 re-cleans then cap hit",
        "stroke_ids": [oid],
        "defect_ids": [did],
    }


def load_scenario_6_dirty_board_baseline_abort(board: VirtualBoard) -> Dict[str, Any]:
    """Scenario 6: Board heavily scribbled with edge density > 4% (0.04), aborting baseline."""
    board.clear()
    stroke_ids = []
    # Scribble dense lines across entire board to exceed 4% Canny edge density
    for row in range(50, board.height_mm - 50, 25):
        oid = board.add_stroke(
            [[50.0, float(row)], [board.width_mm - 50.0, float(row)]],
            width_mm=4.0,
            color_bgr=(20, 20, 20),
            object_id=f"ink_s6_line_{row}",
        )
        stroke_ids.append(oid)

    edge_density = board.compute_edge_density()
    return {
        "scenario_id": 6,
        "name": "Dirty Board Baseline Abort",
        "description": "Excessive edge density > 0.04 causing baseline capture rejection",
        "stroke_count": len(stroke_ids),
        "edge_density": edge_density,
        "should_abort": edge_density > 0.04,
    }


def load_scenario(board: VirtualBoard, scenario_id: int) -> Dict[str, Any]:
    """Load deterministic test scenario 1..6."""
    dispatch = {
        1: load_scenario_1_single_stroke,
        2: load_scenario_2_multiple_clusters,
        3: load_scenario_3_human_hand_occlusion,
        4: load_scenario_4_projector_artifacts,
        5: load_scenario_5_stubborn_residual_cap_hit,
        6: load_scenario_6_dirty_board_baseline_abort,
    }
    if scenario_id not in dispatch:
        raise ValueError(f"Invalid scenario ID {scenario_id}, must be 1..6")
    return dispatch[scenario_id](board)
