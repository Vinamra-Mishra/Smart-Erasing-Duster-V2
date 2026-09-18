"""4-Corner Homography Registration between FRAME_CAMERA and FRAME_BOARD.

Maps camera sensor pixels to metric physical board coordinates (1.0 px = 1.0 mm)
using ArUco marker detection or interactive 4-corner perspective calibration.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple
import cv2
import numpy as np
from pydantic import BaseModel, Field

from .frames import (
    CoordinateFrame,
    Point2D,
    Polygon2D,
    BoundingBox,
    validate_frame,
)
from ..core.config import get_config


class RegistrationError(RuntimeError):
    """Raised when homography calibration fails."""
    pass


class HomographyRegistrar:
    """Manages perspective transformation between FRAME_CAMERA and FRAME_BOARD."""

    def __init__(
        self,
        board_width_mm: float = 1000.0,
        board_height_mm: float = 700.0,
        aruco_dict_name: str = "DICT_4X4_50",
    ) -> None:
        self.board_width_mm = float(board_width_mm)
        self.board_height_mm = float(board_height_mm)
        self.aruco_dict_name = aruco_dict_name
        self._h_matrix: np.ndarray = np.eye(3, dtype=np.float64)
        self._h_inv: np.ndarray = np.eye(3, dtype=np.float64)
        self._is_calibrated: bool = False
        self._reprojection_error_px: float = 0.0
        self._detected_corners_cam: Optional[List[Tuple[float, float]]] = None

    @property
    def is_calibrated(self) -> bool:
        return self._is_calibrated

    @property
    def reprojection_error(self) -> float:
        return self._reprojection_error_px

    @property
    def homography_matrix(self) -> np.ndarray:
        return self._h_matrix.copy()

    @property
    def inverse_homography(self) -> np.ndarray:
        return self._h_inv.copy()

    @property
    def corners_cam(self) -> Optional[List[Tuple[float, float]]]:
        return list(self._detected_corners_cam) if self._detected_corners_cam else None

    def set_board_dimensions(self, width_mm: float, height_mm: float) -> None:
        """Update metric board dimensions and recompute homography if already calibrated."""
        self.board_width_mm = float(width_mm)
        self.board_height_mm = float(height_mm)
        if self._is_calibrated and self._detected_corners_cam is not None:
            self.calibrate_from_corners(self._detected_corners_cam)

    def get_destination_points(self) -> np.ndarray:
        """Physical board corner coordinates in FRAME_BOARD (TL, TR, BR, BL) in mm."""
        return np.array(
            [
                [0.0, 0.0],
                [self.board_width_mm, 0.0],
                [self.board_width_mm, self.board_height_mm],
                [0.0, self.board_height_mm],
            ],
            dtype=np.float32,
        )

    def calibrate_from_corners(
        self,
        corners_cam: Sequence[Tuple[float, float]],
    ) -> float:
        """Compute homography matrix H from 4 ordered camera corners [TL, TR, BR, BL]."""
        if len(corners_cam) != 4:
            raise RegistrationError(f"Expected 4 corners, received {len(corners_cam)}")

        src_pts = np.array(corners_cam, dtype=np.float32)
        dst_pts = self.get_destination_points()

        h_mat = cv2.getPerspectiveTransform(src_pts, dst_pts)
        if h_mat is None or np.isnan(h_mat).any():
            raise RegistrationError("Perspective transform computation yielded invalid matrix")

        self._h_matrix = h_mat.astype(np.float64)
        self._h_inv = np.linalg.inv(self._h_matrix)
        self._detected_corners_cam = [(float(pt[0]), float(pt[1])) for pt in src_pts]
        self._reprojection_error_px = self._compute_reprojection_error(src_pts, dst_pts)
        self._is_calibrated = True
        return self._reprojection_error_px

    def _compute_reprojection_error(
        self,
        src_pts: np.ndarray,
        dst_pts: np.ndarray,
    ) -> float:
        """Compute root-mean-square reprojection error in mm (board space)."""
        reprojected = cv2.perspectiveTransform(
            src_pts.reshape(-1, 1, 2),
            self._h_matrix,
        ).reshape(-1, 2)
        errors = np.linalg.norm(reprojected - dst_pts, axis=1)
        return float(np.mean(errors))

    def detect_aruco_corners(
        self,
        camera_frame: np.ndarray,
        corner_ids: Sequence[int] = (0, 1, 2, 3),
    ) -> Optional[List[Tuple[float, float]]]:
        """Detect ArUco markers 0 (TL), 1 (TR), 2 (BR), 3 (BL) and return their center points."""
        gray = cv2.cvtColor(camera_frame, cv2.COLOR_BGR2GRAY) if camera_frame.ndim == 3 else camera_frame

        dict_attr = getattr(cv2.aruco, self.aruco_dict_name, cv2.aruco.DICT_4X4_50)
        aruco_dict = cv2.aruco.getPredefinedDictionary(dict_attr)

        if hasattr(cv2.aruco, "ArucoDetector"):
            params = cv2.aruco.DetectorParameters()
            detector = cv2.aruco.ArucoDetector(aruco_dict, params)
            marker_corners, ids, _ = detector.detectMarkers(gray)
        else:
            params = cv2.aruco.DetectorParameters_create()
            marker_corners, ids, _ = cv2.aruco.detectMarkers(gray, aruco_dict, parameters=params)

        if ids is None or len(ids) < 4:
            return None

        flattened_ids = ids.flatten().tolist()
        centers_by_id: Dict[int, Tuple[float, float]] = {}
        for idx, marker_id in enumerate(flattened_ids):
            pts = marker_corners[idx][0]
            center = np.mean(pts, axis=0)
            centers_by_id[int(marker_id)] = (float(center[0]), float(center[1]))

        if not all(cid in centers_by_id for cid in corner_ids):
            return None

        return [centers_by_id[cid] for cid in corner_ids]

    @staticmethod
    def order_corners(pts: np.ndarray) -> List[Tuple[float, float]]:
        """Order 4 (x, y) coordinates into [TL, TR, BR, BL]."""
        pts = pts.reshape(-1, 2).astype(np.float32)
        rect = np.zeros((4, 2), dtype=np.float32)

        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]  # Top-left has min sum
        rect[2] = pts[np.argmax(s)]  # Bottom-right has max sum

        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]  # Top-right has min difference (y - x)
        rect[3] = pts[np.argmax(diff)]  # Bottom-left has max difference

        return [(float(p[0]), float(p[1])) for p in rect]

    def detect_whiteboard_corners(
        self,
        camera_frame: np.ndarray,
    ) -> Optional[List[Tuple[float, float]]]:
        """Auto-detect 4 whiteboard corners across front and angled perspective photos.

        Supports ArUco markers, metallic bezel frame contours, and high-luminance
        quadrilateral whiteboard surfaces under steep perspective distortion.
        """
        # 1. Try ArUco markers first
        aruco_corners = self.detect_aruco_corners(camera_frame)
        if aruco_corners is not None and len(aruco_corners) == 4:
            return aruco_corners

        # 2. Multi-scale Canny + morphological border reconstruction
        if camera_frame.ndim == 2:
            gray = camera_frame
        else:
            gray = cv2.cvtColor(camera_frame, cv2.COLOR_BGR2GRAY)

        h, w = gray.shape[:2]
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        candidates = []

        for low_th, high_th in [(30, 90), (40, 120), (20, 60), (50, 150)]:
            edges = cv2.Canny(blurred, low_th, high_th)
            # Mask out 6px border to avoid image boundary snapping
            edges[:6, :] = 0; edges[-6:, :] = 0; edges[:, :6] = 0; edges[:, -6:] = 0

            for k_size in [(5, 5), (7, 7), (9, 9), (13, 13)]:
                kernel = cv2.getStructuringElement(cv2.MORPH_RECT, k_size)
                dilated = cv2.dilate(edges, kernel, iterations=1)
                closed = cv2.morphologyEx(dilated, cv2.MORPH_CLOSE, kernel)

                for mode in [cv2.RETR_EXTERNAL, cv2.RETR_LIST]:
                    contours, _ = cv2.findContours(closed, mode, cv2.CHAIN_APPROX_SIMPLE)
                    for c in contours:
                        bx, by, bw, bh = cv2.boundingRect(c)
                        if bw > 0.98 * w and bh > 0.98 * h:
                            continue
                        hull = cv2.convexHull(c)
                        hull_area = cv2.contourArea(hull)
                        if hull_area < 0.10 * (w * h):
                            continue

                        peri = cv2.arcLength(hull, True)
                        for eps in (0.015, 0.02, 0.025, 0.035, 0.05, 0.07):
                            approx = cv2.approxPolyDP(hull, eps * peri, True)
                            if len(approx) == 4 and cv2.isContourConvex(approx):
                                pts = approx.reshape(4, 2)
                                ordered = self.order_corners(pts)
                                top_len = np.linalg.norm(np.array(ordered[1]) - np.array(ordered[0]))
                                bot_len = np.linalg.norm(np.array(ordered[2]) - np.array(ordered[3]))
                                left_len = np.linalg.norm(np.array(ordered[3]) - np.array(ordered[0]))
                                right_len = np.linalg.norm(np.array(ordered[2]) - np.array(ordered[1]))

                                if min(top_len, bot_len) < 0.15 * w or min(left_len, right_len) < 0.12 * h:
                                    continue

                                mask = np.zeros((h, w), dtype=np.uint8)
                                cv2.drawContours(mask, [approx], -1, 255, -1)
                                mean_val = float(cv2.mean(gray, mask=mask)[0])

                                # Bonus for dark perimeter frame border
                                dil_mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9)))
                                border_ring = cv2.subtract(dil_mask, mask)
                                border_val = float(cv2.mean(gray, mask=border_ring)[0])
                                frame_contrast = max(1.0, mean_val - border_val)

                                score = hull_area * (mean_val ** 1.1) * (frame_contrast ** 0.3)
                                candidates.append((score, ordered))
                                break

        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            return candidates[0][1]

        # 3. Fallback to bright canvas segmentation
        if camera_frame.ndim == 3:
            hsv = cv2.cvtColor(camera_frame, cv2.COLOR_BGR2HSV)
            val = hsv[:, :, 2]
            sat = hsv[:, :, 1]
            canvas_mask = ((val > 140) & (sat < 90)).astype(np.uint8) * 255
            clean_canvas = cv2.morphologyEx(canvas_mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (11, 11)))
            cnts, _ = cv2.findContours(clean_canvas, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if cnts:
                largest_c = max(cnts, key=cv2.contourArea)
                if cv2.contourArea(largest_c) >= 0.10 * (w * h):
                    hull = cv2.convexHull(largest_c)
                    rect = cv2.minAreaRect(hull)
                    box_pts = cv2.boxPoints(rect)
                    return self.order_corners(box_pts)

        return None

    @staticmethod
    def measure_board_dimensions_from_corners(
        corners: Sequence[Tuple[float, float]],
    ) -> Tuple[float, float]:
        """Compute physical board width and height (mm) from 4 camera-space corner points.

        Applies projective foreshortening correction for angled/oblique camera viewpoints
        so that angled photos are rectified and scaled to true physical aspect ratios.

        Args:
            corners: Ordered [TL, TR, BR, BL] corner points in camera pixel space.

        Returns:
            (width_mm, height_mm) — board dimensions, rounded to the nearest mm.
        """
        tl, tr, br, bl = [np.array(c, dtype=np.float64) for c in corners]

        top_w = float(np.linalg.norm(tr - tl))
        bottom_w = float(np.linalg.norm(br - bl))
        left_h = float(np.linalg.norm(bl - tl))
        right_h = float(np.linalg.norm(br - tr))

        calc_w = max(top_w, bottom_w)
        calc_h = max(left_h, right_h)

        # Perspective foreshortening correction for angled views:
        # If opposite sides differ by >20%, compensate horizontal or vertical perspective slant
        h_ratio = max(left_h, right_h) / max(1.0, min(left_h, right_h))
        if h_ratio > 1.20:
            calc_w = calc_w * np.sqrt(h_ratio)

        w_ratio = max(top_w, bottom_w) / max(1.0, min(top_w, bottom_w))
        if w_ratio > 1.20:
            calc_h = calc_h * np.sqrt(w_ratio)

        width_mm = round(calc_w)
        height_mm = round(calc_h)

        # Sanity-clamp: board must be at least 100 mm in each direction
        width_mm = max(100.0, float(width_mm))
        height_mm = max(100.0, float(height_mm))

        return width_mm, height_mm

    def auto_calibrate(
        self,
        camera_frame: np.ndarray,
    ) -> Tuple[bool, float, Optional[List[Tuple[float, float]]]]:
        """Automatically detect whiteboard corners, measure its physical dimensions,
        update board_width_mm / board_height_mm, then calibrate the homography.
        """
        corners = self.detect_whiteboard_corners(camera_frame)
        if corners is None:
            return False, 0.0, None
        try:
            # Measure actual board dimensions from the detected camera-space corner positions
            new_w, new_h = self.measure_board_dimensions_from_corners(corners)
            self.board_width_mm  = new_w
            self.board_height_mm = new_h

            err = self.calibrate_from_corners(corners)
            return True, err, corners
        except RegistrationError:
            return False, 0.0, None


    def calibrate_from_aruco(
        self,
        camera_frame: np.ndarray,
        corner_ids: Sequence[int] = (0, 1, 2, 3),
    ) -> Tuple[bool, float]:
        """Auto-calibrate homography using ArUco markers in frame."""
        corners = self.detect_aruco_corners(camera_frame, corner_ids)
        if corners is None:
            return False, 0.0
        error = self.calibrate_from_corners(corners)
        return True, error

    def warp_to_board(self, camera_frame: np.ndarray) -> np.ndarray:
        """Rectify camera frame to metric FRAME_BOARD (board_width x board_height)."""
        target_size = (int(round(self.board_width_mm)), int(round(self.board_height_mm)))
        return cv2.warpPerspective(
            camera_frame,
            self._h_matrix,
            target_size,
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )

    def warp_to_camera(
        self,
        board_frame: np.ndarray,
        camera_size: Tuple[int, int],
    ) -> np.ndarray:
        """Reproject FRAME_BOARD frame back into camera sensor space."""
        return cv2.warpPerspective(
            board_frame,
            self._h_inv,
            camera_size,
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )

    def point_cam_to_board(self, point: Point2D) -> Point2D:
        """Transform a single 2D point from FRAME_CAMERA to FRAME_BOARD."""
        validate_frame(point, CoordinateFrame.FRAME_CAMERA)
        vec = np.array([point.x, point.y, 1.0], dtype=np.float64)
        res = self._h_matrix @ vec
        if abs(res[2]) < 1e-9:
            raise RegistrationError("Point projection produced singularity (w ~ 0)")
        return Point2D(
            x=round(float(res[0] / res[2]), 4),
            y=round(float(res[1] / res[2]), 4),
            frame=CoordinateFrame.FRAME_BOARD,
        )

    def point_board_to_cam(self, point: Point2D) -> Point2D:
        """Transform a single 2D point from FRAME_BOARD to FRAME_CAMERA."""
        validate_frame(point, CoordinateFrame.FRAME_BOARD)
        vec = np.array([point.x, point.y, 1.0], dtype=np.float64)
        res = self._h_inv @ vec
        if abs(res[2]) < 1e-9:
            raise RegistrationError("Point inverse projection produced singularity (w ~ 0)")
        return Point2D(
            x=round(float(res[0] / res[2]), 4),
            y=round(float(res[1] / res[2]), 4),
            frame=CoordinateFrame.FRAME_CAMERA,
        )

    def polygon_cam_to_board(self, polygon: Polygon2D) -> Polygon2D:
        """Transform a polygon boundary from FRAME_CAMERA to FRAME_BOARD."""
        validate_frame(polygon, CoordinateFrame.FRAME_CAMERA)
        transformed_points: List[Tuple[float, float]] = []
        for pt in polygon.points:
            pt_board = self.point_cam_to_board(
                Point2D(x=pt[0], y=pt[1], frame=CoordinateFrame.FRAME_CAMERA)
            )
            transformed_points.append((pt_board.x, pt_board.y))
        return Polygon2D(points=transformed_points, frame=CoordinateFrame.FRAME_BOARD)

    def polygon_board_to_cam(self, polygon: Polygon2D) -> Polygon2D:
        """Transform a polygon boundary from FRAME_BOARD to FRAME_CAMERA."""
        validate_frame(polygon, CoordinateFrame.FRAME_BOARD)
        transformed_points: List[Tuple[float, float]] = []
        for pt in polygon.points:
            pt_cam = self.point_board_to_cam(
                Point2D(x=pt[0], y=pt[1], frame=CoordinateFrame.FRAME_BOARD)
            )
            transformed_points.append((pt_cam.x, pt_cam.y))
        return Polygon2D(points=transformed_points, frame=CoordinateFrame.FRAME_CAMERA)


_DEFAULT_REGISTRAR: Optional[HomographyRegistrar] = None


def get_default_registrar() -> HomographyRegistrar:
    """Singleton getter for the system homography registrar."""
    global _DEFAULT_REGISTRAR
    if _DEFAULT_REGISTRAR is None:
        cfg = get_config()
        _DEFAULT_REGISTRAR = HomographyRegistrar(
            board_width_mm=cfg.system.board_width_mm,
            board_height_mm=cfg.system.board_height_mm,
            aruco_dict_name=cfg.calibration.aruco_dict,
        )
    return _DEFAULT_REGISTRAR
