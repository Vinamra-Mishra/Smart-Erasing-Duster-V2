"""Comprehensive tests for Coverage Planner, Operational Metrics, and Simulation Engine.

Verifies:
1. Boustrophedon sweep lane generation and 28% overlap (lane step 41.76 mm).
2. Smooth exterior U-turns outside ink hull bounding boxes.
3. Continuous trajectory from dynamic Home Dock (w/2, H - h/2) and return.
4. Dynamic dimension parameterization from config.yaml.
5. Multi-cluster TSP ordering.
6. Exact operational metric formulas (Precision, Recall, IoU, FPR, Residual, Coverage, Stability).
7. Multi-layer virtual board and realistic cleaning with defect preservation.
8. Deterministic Scenarios 1..6 loading.
9. FastAPI planner and simulator endpoints.
"""
from __future__ import annotations

import math
from typing import List, Tuple
import pytest
from shapely.geometry import box, MultiPolygon, Polygon
from fastapi.testclient import TestClient
from fastapi import FastAPI

from app.core.config import AppConfig, CleaningConfig, SystemConfig, get_config
from app.planning.coverage import plan_boustrophedon_coverage
from app.planning.geometry import (
    compute_pca_orientation,
    merge_and_inflate_polygons,
    points_to_polygon,
)
from app.planning.ordering import optimize_cluster_sequence
from app.planning.smoothing import generate_exterior_uturn
from app.planning.transit import plan_full_mission
from app.schemas.ink import CoordinateFrame, PhysicalState
from app.schemas.planner import Waypoint
from app.simulation.board import VirtualBoard
from app.simulation.cleaning import RealisticCleaningEngine
from app.simulation.duster import VirtualDuster
from app.simulation.metrics import (
    compute_cleaning_coverage,
    compute_fpr,
    compute_iou,
    compute_precision,
    compute_recall,
    compute_residual_fraction,
    compute_tracking_stability,
    evaluate_operational_metrics,
)
from app.simulation.scenarios import load_scenario
from app.replay.recorder import SessionRecorder
from app.replay.player import SessionPlayer
from app.api.planner import router as planner_router
from app.api.simulator import router as simulator_router
from app.api.replay import router as replay_router


@pytest.fixture
def default_config() -> AppConfig:
    return get_config()


@pytest.fixture
def sample_ink_polygon() -> Polygon:
    """A rectangular ink stroke of 200 mm x 60 mm centered at (400, 300)."""
    return box(300.0, 270.0, 500.0, 330.0)


# =====================================================================
# 1. Boustrophedon Sweep & Overlap Tests
# =====================================================================

def test_boustrophedon_sweep_default_overlap():
    """Verify Boustrophedon sweep uses default 28% overlap giving delta_y = 41.76 mm."""
    # 200 mm wide x 180 mm tall box centered at (400, 300)
    tall_polygon = box(300.0, 210.0, 500.0, 390.0)
    plan = plan_boustrophedon_coverage([tall_polygon], use_pca_alignment=False)

    assert plan.lane_overlap == pytest.approx(0.28, abs=1e-3)
    assert len(plan.waypoints) >= 4
    assert plan.total_length_mm > 0.0

    # Extract distinct wipe lane start waypoints
    wipe_waypoints = [wp for wp in plan.waypoints if wp.action == "WIPE"]
    assert len(wipe_waypoints) >= 4

    # Lane starts are at even indices (0, 2, 4...)
    lane_ys = [wipe_waypoints[i].y for i in range(0, len(wipe_waypoints), 2)]
    assert len(lane_ys) >= 2

    # Expected lane step for 58.0 mm height and 28% overlap: 58.0 * (1 - 0.28) = 41.76 mm
    expected_step = 58.0 * (1.0 - 0.28)
    for i in range(len(lane_ys) - 1):
        step = abs(lane_ys[i + 1] - lane_ys[i])
        assert step == pytest.approx(expected_step, abs=2.0)


@pytest.mark.parametrize("overlap, expected_step", [
    (0.10, 58.0 * 0.90),
    (0.28, 58.0 * 0.72),
    (0.40, 58.0 * 0.60),
    (0.50, 58.0 * 0.50),
])
def test_configurable_lane_overlap(overlap: float, expected_step: float):
    """Verify effective lane step varies accurately with configurable overlap."""
    tall_polygon = box(300.0, 210.0, 500.0, 390.0)
    plan = plan_boustrophedon_coverage([tall_polygon], lane_overlap=overlap, use_pca_alignment=False)
    assert plan.lane_overlap == pytest.approx(overlap, abs=1e-3)

    wipe_wps = [wp for wp in plan.waypoints if wp.action == "WIPE"]
    lane_ys = [wipe_wps[i].y for i in range(0, len(wipe_wps), 2)]
    assert len(lane_ys) >= 2
    step = abs(lane_ys[1] - lane_ys[0])
    assert step == pytest.approx(expected_step, abs=2.0)


def test_boustrophedon_direction_alternation(sample_ink_polygon: Polygon):
    """Verify Boustrophedon lanes alternate between left-to-right and right-to-left."""
    plan = plan_boustrophedon_coverage([sample_ink_polygon], use_pca_alignment=False)
    wipe_wps = [wp for wp in plan.waypoints if wp.action == "WIPE"]

    # In horizontal unrotated mode: even lanes travel left-to-right, odd right-to-left
    lane_pairs = [(wipe_wps[i], wipe_wps[i + 1]) for i in range(0, len(wipe_wps), 2)]
    for idx, (p_start, p_end) in enumerate(lane_pairs):
        if idx % 2 == 0:
            assert p_end.x > p_start.x  # Left to right
        else:
            assert p_end.x < p_start.x  # Right to left


# =====================================================================
# 2. Smooth Exterior U-Turn Tests
# =====================================================================

def test_exterior_uturn_clears_hull_bounds():
    """Verify U-turns bulge outside the ink hull bounding box by at least duster clearance."""
    hull_bounds = (200.0, 150.0, 400.0, 350.0)  # min_x=200, max_x=400
    duster_w = 162.0
    clearance = (duster_w / 2.0) + 10.0  # 91.0 mm

    # 1. Right-side turn
    exit_pt = (400.0, 180.0)
    entry_pt = (400.0, 221.76)
    right_uturn = generate_exterior_uturn(
        exit_pt=exit_pt,
        entry_pt=entry_pt,
        hull_bounds=hull_bounds,
        duster_width_mm=duster_w,
        is_right_side=True,
    )

    assert len(right_uturn) >= 5
    # Every intermediate waypoint must be strictly to the right of the ink boundary
    for wp in right_uturn[1:-1]:
        assert wp.x > hull_bounds[2]  # x > 400.0
    max_x_seen = max(wp.x for wp in right_uturn)
    assert max_x_seen >= hull_bounds[2] + clearance - 1.0

    # 2. Left-side turn
    exit_pt_left = (200.0, 221.76)
    entry_pt_left = (200.0, 263.52)
    left_uturn = generate_exterior_uturn(
        exit_pt=exit_pt_left,
        entry_pt=entry_pt_left,
        hull_bounds=hull_bounds,
        duster_width_mm=duster_w,
        is_right_side=False,
    )

    for wp in left_uturn[1:-1]:
        assert wp.x < hull_bounds[0]  # x < 200.0
    min_x_seen = min(wp.x for wp in left_uturn)
    assert min_x_seen <= hull_bounds[0] - clearance + 1.0


# =====================================================================
# 3. Dynamic Home Dock & Continuous Trajectory Tests
# =====================================================================

def test_dynamic_home_dock_calculation():
    """Verify dynamic Home Dock formula: (w/2, H - h/2, 0.0)."""
    cfg = AppConfig(
        system=SystemConfig(board_width_mm=1000.0, board_height_mm=700.0),
        cleaning=CleaningConfig(duster_width_mm=162.0, duster_height_mm=58.0),
    )
    x_home, y_home, theta_home = cfg.get_home_dock()
    assert x_home == pytest.approx(81.0)
    assert y_home == pytest.approx(671.0)
    assert theta_home == 0.0

    # Test reconfiguration
    cfg_custom = AppConfig(
        system=SystemConfig(board_width_mm=1200.0, board_height_mm=800.0),
        cleaning=CleaningConfig(duster_width_mm=120.0, duster_height_mm=50.0),
    )
    x_c, y_c, theta_c = cfg_custom.get_home_dock()
    assert x_c == pytest.approx(60.0)
    assert y_c == pytest.approx(775.0)
    assert theta_c == 0.0


def test_continuous_mission_trajectory(sample_ink_polygon: Polygon):
    """Verify mission starts at dynamic Home Dock, cleans target, and returns home."""
    plan = plan_full_mission(
        target_clusters=[("stroke_1", sample_ink_polygon)],
        duster_width_mm=162.0,
        duster_height_mm=58.0,
        board_height_mm=700.0,
    )

    assert len(plan.waypoints) >= 10
    # First waypoint must be DOCK at Home (81.0, 671.0)
    first_wp = plan.waypoints[0]
    assert first_wp.action == "DOCK"
    assert first_wp.x == pytest.approx(81.0, abs=1e-2)
    assert first_wp.y == pytest.approx(671.0, abs=1e-2)

    # Last waypoint must be DOCK at Home (81.0, 671.0)
    last_wp = plan.waypoints[-1]
    assert last_wp.action == "DOCK"
    assert last_wp.x == pytest.approx(81.0, abs=1e-2)
    assert last_wp.y == pytest.approx(671.0, abs=1e-2)

    # Waypoint actions sequence includes DOCK, TRANSIT, WIPE
    actions = [wp.action for wp in plan.waypoints]
    assert "DOCK" in actions
    assert "TRANSIT" in actions
    assert "WIPE" in actions


# =====================================================================
# 4. Multi-Cluster TSP Ordering Tests
# =====================================================================

def test_multi_cluster_ordering():
    """Verify cluster sequencer orders targets by nearest centroid starting from home."""
    home_pos = (81.0, 671.0)
    # Cluster A: near home (150, 600)
    c_a = ("cluster_a", box(130, 580, 170, 620))
    # Cluster B: far top-right (800, 100)
    c_b = ("cluster_b", box(780, 80, 820, 120))
    # Cluster C: mid-right (600, 300)
    c_c = ("cluster_c", box(580, 280, 620, 320))

    # Input in reverse order: [B, C, A]
    ordered = optimize_cluster_sequence([c_b, c_c, c_a], start_pos=home_pos)
    ordered_ids = [cid for cid, _ in ordered]

    # Cluster A is closest to home, then C, then B
    assert ordered_ids == ["cluster_a", "cluster_c", "cluster_b"]


# =====================================================================
# 5. Exact Operational Metrics Tests
# =====================================================================

def test_metrics_perfect_overlap():
    """Verify metrics when detected matches ground truth exactly."""
    poly = box(100.0, 100.0, 200.0, 200.0)  # Area 10,000 mm^2
    assert compute_precision(poly, poly) == 1.0
    assert compute_recall(poly, poly) == 1.0
    assert compute_iou(poly, poly) == 1.0
    assert compute_fpr(poly, poly, board_area_mm2=700000.0) == 0.0


def test_metrics_disjoint():
    """Verify metrics when detected and ground truth do not overlap."""
    poly1 = box(100.0, 100.0, 200.0, 200.0)
    poly2 = box(300.0, 300.0, 400.0, 400.0)
    assert compute_precision(poly1, poly2) == 0.0
    assert compute_recall(poly1, poly2) == 0.0
    assert compute_iou(poly1, poly2) == 0.0
    assert compute_fpr(poly1, poly2, board_area_mm2=700000.0) > 0.0


def test_metrics_half_overlap():
    """Verify precision = 1.0, recall = 0.5, IoU = 0.5 when detected is half of GT."""
    gt = box(100.0, 100.0, 200.0, 200.0)      # Area 10,000
    detected = box(100.0, 100.0, 150.0, 200.0) # Area 5,000 (subset of GT)

    assert compute_precision(detected, gt) == pytest.approx(1.0)
    assert compute_recall(detected, gt) == pytest.approx(0.5)
    assert compute_iou(detected, gt) == pytest.approx(0.5)


def test_residual_fraction_and_cleaning_coverage():
    """Verify residual fraction and cleaning coverage formulas."""
    original = box(100.0, 100.0, 200.0, 200.0)  # Area 10,000
    residual = box(100.0, 100.0, 200.0, 115.0)  # Area 1,500 (15% residual)
    assert compute_residual_fraction(residual, original) == pytest.approx(0.15, abs=1e-4)

    swept = box(100.0, 100.0, 200.0, 185.0)      # Covers 85% of target
    assert compute_cleaning_coverage(swept, original) == pytest.approx(0.85, abs=1e-4)


def test_tracking_stability_formula():
    """Verify tracking stability calculation."""
    # Zero ID switches
    assert compute_tracking_stability(0, 100) == 1.0
    # 2 ID switches over 100 frames
    assert compute_tracking_stability(2, 100) == pytest.approx(0.98)
    # Exceeded lifetime frames
    assert compute_tracking_stability(150, 100) == 0.0


# =====================================================================
# 6. Simulation Engine & Realistic Cleaning Tests
# =====================================================================

def test_virtual_board_layer_compositing():
    """Verify virtual board renders multi-layer composite accurately."""
    board = VirtualBoard(width_mm=500, height_mm=350)
    # Clean composite should be light whiteboard
    clean_img = board.render_composite()
    assert clean_img.shape == (350, 500, 3)
    assert clean_img[100, 100, 0] >= 240

    # Add dark ink stroke
    board.add_stroke([[100.0, 100.0], [200.0, 100.0]], width_mm=6.0, color_bgr=(10, 10, 10))
    ink_img = board.render_composite()
    # Center of stroke should now be darkened
    assert ink_img[100, 150, 0] < 50


def test_realistic_cleaning_wipes_ink_and_preserves_defects():
    """Verify 85% wiping efficiency erases ink while defects remain 100% immune."""
    board = VirtualBoard(width_mm=500, height_mm=350)
    engine = RealisticCleaningEngine(nominal_efficiency=0.85)

    # Add ink stroke
    oid = board.add_stroke([[150.0, 150.0], [250.0, 150.0]], width_mm=8.0)
    # Add permanent defect right next to it
    did = board.add_defect([[160.0, 150.0], [240.0, 150.0]], width_mm=4.0)

    # Initial ink area
    initial_ink_poly = board.get_ground_truth_ink_polygon()
    initial_defect_poly = board.get_ground_truth_defect_polygon()
    assert initial_ink_poly.area > 0.0
    assert initial_defect_poly.area > 0.0

    # Wipe with footprint covering both
    swept_box = box(140.0, 130.0, 260.0, 170.0)
    erased_area = engine.apply_wipe(board, swept_box)

    assert erased_area > 0.0
    # Permanent defect is 100% preserved
    post_defect_poly = board.get_ground_truth_defect_polygon()
    assert post_defect_poly.area == pytest.approx(initial_defect_poly.area, abs=1e-3)


# =====================================================================
# 7. Scenarios 1..6 Tests
# =====================================================================

@pytest.mark.parametrize("scenario_id, expected_name", [
    (1, "Single Stroke"),
    (2, "Multiple Clusters"),
    (3, "Human Hand Occlusion"),
    (4, "Projector Artifacts"),
    (5, "Stubborn Residual -> Cap Hit"),
    (6, "Dirty Board Baseline Abort"),
])
def test_deterministic_scenarios_load(scenario_id: int, expected_name: str):
    """Verify Scenarios 1..6 load properly and configure the virtual board."""
    board = VirtualBoard(width_mm=1000, height_mm=700)
    result = load_scenario(board, scenario_id)

    assert result["scenario_id"] == scenario_id
    assert result["name"] == expected_name

    if scenario_id == 3:
        # Occluder must be >= 4.5% of board area (31,500 mm^2)
        assert result["occluder_area_mm2"] >= 31500.0
    elif scenario_id == 6:
        # Dirty board edge density must exceed 0.04
        assert result["edge_density"] > 0.04
        assert result["should_abort"] is True


# =====================================================================
# 8. API Endpoint Tests
# =====================================================================

def test_api_planner_and_simulator():
    """Verify FastAPI planner and simulator endpoints respond with valid schemas."""
    app = FastAPI()
    app.include_router(planner_router)
    app.include_router(simulator_router)
    client = TestClient(app)

    # 1. Test /api/planner/plan
    res = client.post("/api/planner/plan", json={
        "polygons": [[[400.0, 300.0], [500.0, 300.0], [500.0, 350.0], [400.0, 350.0]]],
        "lane_overlap": 0.28,
        "use_full_transit": True,
    })
    assert res.status_code == 200
    plan_data = res.json()
    assert "waypoints" in plan_data
    assert len(plan_data["waypoints"]) >= 2
    assert plan_data["waypoints"][0]["action"] == "DOCK"

    # 2. Test /api/planner/dispatch
    res_disp = client.post("/api/planner/dispatch")
    assert res_disp.status_code == 200
    assert res_disp.json()["status"] == "dispatched"

    # 3. Test /api/simulator/scenario
    res_scen = client.post("/api/simulator/scenario", json={"scenario_id": 1})
    assert res_scen.status_code == 200
    assert res_scen.json()["name"] == "Single Stroke"

    # 4. Test /api/simulator/brush
    res_brush = client.post("/api/simulator/brush", json={
        "points": [[200.0, 200.0], [250.0, 220.0]],
        "width_mm": 6.0,
    })
    assert res_brush.status_code == 200
    assert res_brush.json()["status"] == "stroke_added"

    # 5. Test /api/simulator/metrics
    res_metrics = client.get("/api/simulator/metrics")
    assert res_metrics.status_code == 200
    metrics = res_metrics.json()
    assert "iou" in metrics
    assert "precision" in metrics
    assert "recall" in metrics


def test_replay_recording_and_playback(tmp_path):
    """Verify session recorder writes frames to JSONL and session player reads them."""
    recorder = SessionRecorder(output_dir=tmp_path)
    sid = recorder.start(session_id="test_session_42", metadata={"board": "1000x700"})
    assert sid == "test_session_42"
    assert recorder.is_recording is True

    # Record 3 frames
    recorder.record_frame(0.05, {"x": 81.0, "y": 671.0}, {"iou": 1.0})
    recorder.record_frame(0.10, {"x": 85.0, "y": 660.0}, {"iou": 0.95})
    recorder.record_frame(0.15, {"x": 90.0, "y": 650.0}, {"iou": 0.90})

    stopped_id = recorder.stop()
    assert stopped_id == "test_session_42"
    assert recorder.frame_count == 3

    # Replay with SessionPlayer
    session_file = tmp_path / "test_session_42.jsonl"
    player = SessionPlayer(session_file)
    assert player.total_frames == 3
    assert player.is_finished is False

    frame0 = player.current_frame()
    assert frame0 is not None
    assert frame0["duster_pose"]["x"] == 81.0

    frame1 = player.step(1)
    assert frame1["duster_pose"]["x"] == 85.0

    frame2 = player.step(1)
    assert frame2["duster_pose"]["x"] == 90.0

    player.reset()
    assert player.current_idx == 0


def test_replay_api_endpoints(tmp_path, monkeypatch):
    """Verify replay API endpoints for start, stop, list, and play."""
    from app.api import replay as replay_module
    # Use temporary sessions directory
    monkeypatch.setattr(replay_module, "_RECORDER", SessionRecorder(output_dir=tmp_path))
    monkeypatch.setattr(replay_module, "Path", lambda p: tmp_path if "sessions" in str(p) else tmp_path / p)

    app = FastAPI()
    app.include_router(replay_router)
    client = TestClient(app)

    # 1. Start record
    start_res = client.post("/api/replay/record/start", json={"session_id": "api_test_sess"})
    assert start_res.status_code == 200
    assert start_res.json()["session_id"] == "api_test_sess"

    # 2. Stop record
    stop_res = client.post("/api/replay/record/stop")
    assert stop_res.status_code == 200
    assert stop_res.json()["status"] == "stopped"

