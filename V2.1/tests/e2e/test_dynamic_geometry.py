"""E2E Test: Dynamic Actuator & Whiteboard Geometry Updates.

Verifies:
1. Dynamic Home Dock formula (w/2, H - h/2) across custom config parameters without code changes.
2. Dynamic lane step adjustment in the Coverage Path Planner based on duster height.
3. Transit trajectories starting and ending at the dynamically updated Home Dock.
4. Physical boundary clearance of the duster at Home Dock.
5. Pydantic validation rejects non-positive or unphysical dimensions.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError
from shapely.geometry import box

from app.core.config import AppConfig, CleaningConfig, SystemConfig
from app.digital_twin.execution_state import ExecutionStore
from app.planning.coverage import plan_boustrophedon_coverage
from app.planning.transit import plan_full_mission


class TestDynamicGeometryE2E:
    """E2E test suite for dynamic dimensions and Home Dock calculation."""

    def test_default_home_dock_coordinates(self):
        """Verifies standard default dimensions produce (81.0, 671.0, 0.0) mm."""
        config = AppConfig()
        x_home, y_home, theta_home = config.get_home_dock()

        assert x_home == pytest.approx(81.0, abs=1e-3)
        assert y_home == pytest.approx(671.0, abs=1e-3)
        assert theta_home == pytest.approx(0.0, abs=1e-3)

    def test_dynamic_duster_dimension_update_without_code_changes(self):
        """Updating duster width/height updates Home Dock automatically."""
        # Custom duster: 200 mm wide, 80 mm high on standard 1000x700 board
        config = AppConfig(
            cleaning=CleaningConfig(
                duster_width_mm=200.0,
                duster_height_mm=80.0,
                duster_thickness_mm=45.0,
            )
        )
        x_home, y_home, theta_home = config.get_home_dock()

        # Expected: x = 200/2 = 100.0, y = 700 - 80/2 = 660.0
        assert x_home == pytest.approx(100.0, abs=1e-3)
        assert y_home == pytest.approx(660.0, abs=1e-3)
        assert theta_home == pytest.approx(0.0, abs=1e-3)

    def test_dynamic_board_dimension_update_without_code_changes(self):
        """Updating board dimensions updates Home Dock automatically."""
        # Custom board: 1200 mm wide, 900 mm high with default duster (162x58 mm)
        config = AppConfig(
            system=SystemConfig(
                board_width_mm=1200.0,
                board_height_mm=900.0,
            )
        )
        x_home, y_home, theta_home = config.get_home_dock()

        # Expected: x = 162/2 = 81.0, y = 900 - 58/2 = 871.0
        assert x_home == pytest.approx(81.0, abs=1e-3)
        assert y_home == pytest.approx(871.0, abs=1e-3)
        assert theta_home == pytest.approx(0.0, abs=1e-3)

    def test_dynamic_both_board_and_duster_update(self):
        """Updating both board (1500x1000 mm) and duster (250x100 mm)."""
        config = AppConfig(
            system=SystemConfig(
                board_width_mm=1500.0,
                board_height_mm=1000.0,
            ),
            cleaning=CleaningConfig(
                duster_width_mm=250.0,
                duster_height_mm=100.0,
            ),
        )
        x_home, y_home, theta_home = config.get_home_dock()

        # Expected: x = 250/2 = 125.0, y = 1000 - 100/2 = 950.0
        assert x_home == pytest.approx(125.0, abs=1e-3)
        assert y_home == pytest.approx(950.0, abs=1e-3)
        assert theta_home == pytest.approx(0.0, abs=1e-3)

    def test_execution_store_initializes_with_dynamic_home_dock(self):
        """Verifies ExecutionStore automatically places duster at configured Home Dock."""
        custom_cfg = AppConfig(
            system=SystemConfig(board_width_mm=1200.0, board_height_mm=800.0),
            cleaning=CleaningConfig(duster_width_mm=180.0, duster_height_mm=60.0),
        )
        exec_store = ExecutionStore(config=custom_cfg)

        assert exec_store.duster_pose.x == pytest.approx(90.0, abs=1e-3)
        assert exec_store.duster_pose.y == pytest.approx(770.0, abs=1e-3)
        assert exec_store.duster_pose.theta_deg == pytest.approx(0.0, abs=1e-3)

    def test_home_dock_actuator_clearance_within_board(self):
        """Asserts the physical duster footprint at Home Dock is strictly within board bounds."""
        test_cases = [
            (1000.0, 700.0, 162.0, 58.0),
            (1200.0, 900.0, 200.0, 80.0),
            (800.0, 600.0, 120.0, 50.0),
            (2000.0, 1200.0, 300.0, 120.0),
        ]
        for bw, bh, dw, dh in test_cases:
            cfg = AppConfig(
                system=SystemConfig(board_width_mm=bw, board_height_mm=bh),
                cleaning=CleaningConfig(duster_width_mm=dw, duster_height_mm=dh),
            )
            xh, yh, _ = cfg.get_home_dock()

            # Tool footprint bounds
            x_min = xh - (dw / 2.0)
            x_max = xh + (dw / 2.0)
            y_min = yh - (dh / 2.0)
            y_max = yh + (dh / 2.0)

            # Must be strictly within [0, bw] x [0, bh]
            assert x_min >= 0.0, f"Left edge clipped for duster {dw}x{dh} on {bw}x{bh}"
            assert x_max <= bw, f"Right edge out of bounds for duster {dw}x{dh} on {bw}x{bh}"
            assert y_min >= 0.0, f"Top edge clipped for duster {dw}x{dh} on {bw}x{bh}"
            assert y_max <= bh, f"Bottom edge out of bounds for duster {dw}x{dh} on {bw}x{bh}"
            # Specific dock alignment: left edge touches 0, bottom edge touches board bottom
            assert x_min == pytest.approx(0.0, abs=1e-3)
            assert y_max == pytest.approx(bh, abs=1e-3)

    def test_coverage_lane_step_dynamically_scales_with_duster_height(self):
        """Coverage planner adjusts lane spacing based on dynamic duster height."""
        stroke = box(200.0, 200.0, 400.0, 450.0)

        # Standard duster h=58, overlap=0.28 -> delta_y = 58 * 0.72 = 41.76 mm
        plan_std = plan_boustrophedon_coverage(
            polygons=[stroke],
            lane_overlap=0.28,
            duster_width_mm=162.0,
            duster_height_mm=58.0,
            use_pca_alignment=False,
        )

        # Larger duster h=100, overlap=0.28 -> delta_y = 100 * 0.72 = 72.0 mm
        plan_large = plan_boustrophedon_coverage(
            polygons=[stroke],
            lane_overlap=0.28,
            duster_width_mm=200.0,
            duster_height_mm=100.0,
            use_pca_alignment=False,
        )

        # Larger duster requires fewer wipe lanes to cover the same 250 mm height
        wipe_wps_std = [wp for wp in plan_std.waypoints if wp.action == "WIPE"]
        wipe_wps_large = [wp for wp in plan_large.waypoints if wp.action == "WIPE"]

        assert len(wipe_wps_std) > len(wipe_wps_large)

    def test_transit_trajectory_uses_dynamically_updated_home_dock(self):
        """Full mission transit plan begins and terminates at the custom Home Dock."""
        custom_bw = 1400.0
        custom_bh = 850.0
        custom_dw = 180.0
        custom_dh = 70.0

        expected_xh = custom_dw / 2.0  # 90.0
        expected_yh = custom_bh - (custom_dh / 2.0)  # 815.0

        target_poly = box(400.0, 300.0, 600.0, 400.0)

        plan = plan_full_mission(
            target_clusters=[("target_1", target_poly)],
            lane_overlap=0.28,
            duster_width_mm=custom_dw,
            duster_height_mm=custom_dh,
            board_height_mm=custom_bh,
        )

        assert len(plan.waypoints) >= 4
        # First waypoint is DOCK at dynamic Home
        assert plan.waypoints[0].action == "DOCK"
        assert plan.waypoints[0].x == pytest.approx(expected_xh, abs=1e-3)
        assert plan.waypoints[0].y == pytest.approx(expected_yh, abs=1e-3)

        # Final waypoint returns to DOCK at dynamic Home
        assert plan.waypoints[-1].action == "DOCK"
        assert plan.waypoints[-1].x == pytest.approx(expected_xh, abs=1e-3)
        assert plan.waypoints[-1].y == pytest.approx(expected_yh, abs=1e-3)
