from __future__ import annotations

import asyncio
import logging
import socket
import struct
import time
from typing import AsyncGenerator, Optional, Tuple
import cv2
import numpy as np

from app.core.config import AppConfig, get_config
from app.digital_twin.board_twin import BoardTwinStore
from app.digital_twin.execution_state import ExecutionStore
from app.digital_twin.reconciler import ReconcilerEvent, reconcile
from app.perception.reference import get_default_baseline_manager
from app.perception.difference import compute_difference_maps
from app.perception.shadow import detect_shadow_mask
from app.perception.glare import SpecularGlareFilter
from app.perception.projector import ProjectorDecoupler
from app.perception.occlusion import TemporalOcclusionDetector
from app.perception.fusion import EvidenceFusionEngine
from app.perception.registration import get_default_registrar, HomographyRegistrar
from app.perception.strokes import StrokeExtractor, DetectedStroke
from app.schemas.events import BusEvent, EventType
from app.schemas.ink import PhysicalState
from app.schemas.perception import ObservationType


logger = logging.getLogger(__name__)


class RtpVideoPacketizer:
    """Pure-Python UDP RTP Packetizer for Motion JPEG (RFC 3550 & RFC 2435).

    Transmits video frames as RTP packets over UDP to target host and port (default 127.0.0.1:5004).
    Zero external native dependencies required.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 5004, fps: int = 30, ssrc: int = 0x12345678):
        self.host = host
        self.port = port
        self.fps = fps
        self.ssrc = ssrc
        self.seq_num = 0
        self.timestamp = 0
        self.clock_rate = 90000  # Standard 90 kHz clock for video
        self.timestamp_increment = int(self.clock_rate / self.fps)
        self.max_chunk_size = 1400  # Safe UDP MTU size

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)

    def send_frame(self, jpeg_bytes: bytes, width: int = 1000, height: int = 700) -> int:
        """Packetize and transmit a JPEG frame over UDP via RTP."""
        total_len = len(jpeg_bytes)
        offset = 0
        packets_sent = 0

        # Width and height encodings for RFC 2435 (multiples of 8)
        w_enc = min(255, width // 8)
        h_enc = min(255, height // 8)

        while offset < total_len:
            remaining = total_len - offset
            chunk_size = min(remaining, self.max_chunk_size)
            is_last = (offset + chunk_size) >= total_len

            # RFC 3550 RTP Header (12 bytes)
            # Byte 0: V=2, P=0, X=0, CC=0 -> 0x80
            # Byte 1: M=(1 if is_last else 0) | PT=26 (MJPEG)
            marker = 0x80 if is_last else 0x00
            pt_byte = marker | 26
            rtp_header = struct.pack(
                "!BBHII",
                0x80,
                pt_byte,
                self.seq_num & 0xFFFF,
                self.timestamp & 0xFFFFFFFF,
                self.ssrc,
            )

            # RFC 2435 JPEG Payload Header (8 bytes)
            # Type-specific=0, Fragment Offset (24-bit), Type=1, Q=255, Width/8, Height/8
            offset_b0 = (offset >> 16) & 0xFF
            offset_b1 = (offset >> 8) & 0xFF
            offset_b2 = offset & 0xFF
            jpeg_header = struct.pack(
                "!BBBBBBBB",
                0,
                offset_b0,
                offset_b1,
                offset_b2,
                1,
                255,
                w_enc,
                h_enc,
            )

            chunk = jpeg_bytes[offset : offset + chunk_size]
            packet = rtp_header + jpeg_header + chunk

            try:
                self.sock.sendto(packet, (self.host, self.port))
                packets_sent += 1
            except BlockingIOError:
                pass
            except Exception as e:
                logger.debug("RTP packet send error: %s", e)

            self.seq_num = (self.seq_num + 1) & 0xFFFF
            offset += chunk_size

        self.timestamp = (self.timestamp + self.timestamp_increment) & 0xFFFFFFFF
        return packets_sent

    def close(self) -> None:
        try:
            self.sock.close()
        except Exception:
            pass


def draw_hud_overlays(
    canvas: np.ndarray,
    twin_store: BoardTwinStore,
    exec_store: ExecutionStore,
    config: AppConfig,
) -> np.ndarray:
    """Render HUD debug overlays: coordinate axes, duster footprint, target polygons, home dock."""
    h, w = canvas.shape[:2]

    # 1. Outer Bezel
    cv2.rectangle(canvas, (0, 0), (w - 1, h - 1), (180, 180, 180), 2)

    # 2. Coordinate Axes at (0, 0)
    # X-axis (Red in BGR: 0, 0, 255)
    cv2.arrowedLine(canvas, (10, 10), (90, 10), (0, 0, 220), 2, tipLength=0.2)
    cv2.putText(canvas, "X (mm)", (95, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 220), 1, cv2.LINE_AA)
    # Y-axis (Green in BGR: 0, 255, 0)
    cv2.arrowedLine(canvas, (10, 10), (10, 90), (0, 180, 0), 2, tipLength=0.2)
    cv2.putText(canvas, "Y (mm)", (15, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 180, 0), 1, cv2.LINE_AA)

    # 3. Dynamic Home Dock Parking Zone (Dashed/Outlined)
    x_home, y_home, _ = config.get_home_dock()
    dw = config.cleaning.duster_width_mm
    dh = config.cleaning.duster_height_mm
    hx1 = int(x_home - dw / 2)
    hy1 = int(y_home - dh / 2)
    hx2 = int(x_home + dw / 2)
    hy2 = int(y_home + dh / 2)
    cv2.rectangle(canvas, (hx1, hy1), (hx2, hy2), (200, 220, 200), 1)
    cv2.putText(canvas, "HOME DOCK", (hx1 + 5, hy1 + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (100, 150, 100), 1, cv2.LINE_AA)

    # 4. Target Ink Objects & States
    state_colors = {
        PhysicalState.STABLE_INK: (220, 60, 20),      # Blue
        PhysicalState.NEW_INK: (240, 120, 40),        # Light Blue
        PhysicalState.PARTIALLY_CLEANED: (30, 140, 255), # Orange
        PhysicalState.CLEANED: (60, 200, 60),         # Green
        PhysicalState.PERMANENT_DEFECT: (20, 20, 220),# Red
        PhysicalState.UNKNOWN: (40, 200, 220),        # Yellow
        PhysicalState.OCCLUDED: (160, 80, 160),       # Purple
    }

    for obj in twin_store.get_all_objects():
        color = state_colors.get(obj.state, (100, 100, 100))
        if len(obj.points) >= 2:
            pts = np.array(obj.points, dtype=np.int32)
            cv2.polylines(canvas, [pts], False, color, 2, cv2.LINE_AA)
        elif obj.bbox != (0.0, 0.0, 0.0, 0.0):
            bx1, by1, bx2, by2 = (int(v) for v in obj.bbox)
            cv2.rectangle(canvas, (bx1, by1), (bx2, by2), color, 2)

        cx, cy = int(obj.centroid[0]), int(obj.centroid[1])
        cv2.putText(
            canvas,
            f"{obj.id[:6]}:{obj.state.value[:4]}",
            (max(5, cx - 20), max(12, cy - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.35,
            color,
            1,
            cv2.LINE_AA,
        )

    # 5. Dynamic Duster Footprint
    dp = exec_store.duster_pose
    dx, dy = dp.x, dp.y
    angle_rad = np.radians(dp.theta_deg)
    cos_a, sin_a = np.cos(angle_rad), np.sin(angle_rad)

    hw = dw / 2.0
    hh = dh / 2.0
    corners = [
        (-hw, -hh),
        (hw, -hh),
        (hw, hh),
        (-hw, hh),
    ]
    rotated_corners = []
    for cx, cy in corners:
        rx = dx + (cx * cos_a - cy * sin_a)
        ry = dy + (cx * sin_a + cy * cos_a)
        rotated_corners.append([int(rx), int(ry)])

    duster_poly = np.array(rotated_corners, dtype=np.int32)
    # Fill duster with semi-transparent tint
    overlay = canvas.copy()
    fill_color = (180, 220, 255) if dp.is_contacting else (220, 220, 220)
    border_color = (0, 100, 240) if dp.is_contacting else (100, 100, 100)
    cv2.fillPoly(overlay, [duster_poly], fill_color)
    cv2.addWeighted(overlay, 0.4, canvas, 0.6, 0, canvas)
    cv2.polylines(canvas, [duster_poly], True, border_color, 2, cv2.LINE_AA)

    # Center marker & heading
    cv2.circle(canvas, (int(dx), int(dy)), 3, (0, 0, 255), -1)

    # 6. Status Telemetry Bar
    status_text = f"STATE: {exec_store.state.value} | DUSTER: ({dx:.1f}, {dy:.1f}) | OBJS: {len(twin_store.objects)}"
    cv2.putText(canvas, status_text, (150, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (40, 40, 40), 1, cv2.LINE_AA)

    return canvas


class FrameStreamer:
    """Central frame generator serving HTTP MJPEG bridge and RTP UDP socket."""

    def __init__(
        self,
        config: AppConfig,
        twin_store: BoardTwinStore,
        exec_store: ExecutionStore,
        manager: Optional[Any] = None,
    ):
        self.config = config
        self.twin_store = twin_store
        self.exec_store = exec_store
        self.manager = manager
        self.width = int(config.system.board_width_mm)
        self.height = int(config.system.board_height_mm)
        self.cap: Optional[cv2.VideoCapture] = None
        self.registrar: HomographyRegistrar = get_default_registrar()
        self.stroke_extractor: StrokeExtractor = StrokeExtractor(min_area_mm2=15.0, max_thickness_mm=14.0)
        self.last_raw_frame: Optional[np.ndarray] = None
        self.frame_count: int = 0
        self.rtp = RtpVideoPacketizer(
            host=config.system.transport.rtp_host,
            port=config.system.transport.rtp_port,
            fps=config.system.fps,
        )
        # 11-Channel Perception Diff & Disturbance Engines
        self._glare_filter = SpecularGlareFilter()
        self._proj_decoupler = ProjectorDecoupler()
        self._occlusion_detector = TemporalOcclusionDetector(
            board_width_mm=self.width,
            board_height_mm=self.height,
        )
        self._fusion_engine = EvidenceFusionEngine()
        self._prev_canvas: Optional[np.ndarray] = None
        self._last_perception: dict = {
            "raw_score_mean": 0.0,
            "fused_score_mean": 0.0,
            "channels": {},
            "glare": False,
            "shadow": False,
            "projector_likelihood": 0.0,
            "is_occluded": False,
        }
        # Thread-safe frame caching to eliminate DirectShow contention
        import threading
        self._capture_lock = threading.Lock()
        self._cached_canvas: Optional[np.ndarray] = None
        self._cached_jpeg: bytes = b""
        self._cached_raw_frame: Optional[np.ndarray] = None
        self._cached_raw_jpeg: bytes = b""
        self._last_capture_time: float = 0.0
        self._last_raw_capture_time: float = 0.0
        self.measured_fps: int = 30
        self._fps_counter: int = 0
        self._last_fps_calc: float = time.time()

        # Attempt to initialize video source if configured
        self._init_capture(config.system.camera_index)


    def _init_capture(self, source: int | str) -> bool:
        """Attempt to open physical webcam, OBS Virtual Camera, or video stream URL."""
        if self.cap is not None:
            self.cap.release()
            self.cap = None

        if source is None or source == 0 or str(source).strip() in ("0", ""):
            logger.info("Camera source 0 (webcam) is blocked by user; exclusively using virtual camera source 1")
            source = 1
        elif isinstance(source, str) and source.strip().isdigit():
            val = int(source.strip())
            source = 1 if val == 0 else val

        if self.config.system.camera_index in (0, "0", None, ""):
            self.config.system.camera_index = source

        try:
            if isinstance(source, int):
                # On Windows, cv2.CAP_DSHOW is required for DirectShow (OBS Virtual Camera)
                cap = cv2.VideoCapture(source, cv2.CAP_DSHOW)
            elif isinstance(source, str) and source.strip() and source.strip().lower() != "virtual":
                if source.isdigit():
                    num = int(source)
                    if num == 0:
                        num = 1
                    cap = cv2.VideoCapture(num, cv2.CAP_DSHOW)
                else:
                    cap = cv2.VideoCapture(source)
            else:
                return False

            if cap.isOpened():
                # Configure 1080p resolution on DirectShow
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
                self.cap = cap
                logger.info("Video capture opened successfully on source: %s (1080p requested)", source)
                try:
                    ret, frame = cap.read()
                    if ret and frame is not None and frame.size > 0:
                        self.last_raw_frame = frame.copy()
                except Exception:
                    pass
                return True
            else:
                logger.info("Video source %s could not be opened, defaulting to virtual canvas", source)
                return False
        except Exception as e:
            logger.warning("Error initializing video capture %s: %s", source, e)
            return False

    def set_camera_source(self, source: int | str) -> bool:
        """Dynamically switch video source (e.g. OBS Virtual Camera index or stream URL)."""
        if source is None or source == 0 or str(source).strip() in ("0", ""):
            source = 1
        elif isinstance(source, str) and source.strip().isdigit():
            val = int(source.strip())
            source = 1 if val == 0 else val
        self.config.system.camera_index = source
        success = self._init_capture(source)
        if success:
            # Reset calibration check on new source
            self.registrar._is_calibrated = False
        return success

    @classmethod
    def list_available_cameras(
        cls,
        active_cap: Optional[cv2.VideoCapture] = None,
        active_idx: Optional[int] = None,
        active_last_frame: Optional[np.ndarray] = None,
    ) -> List[dict]:
        """Probe DirectShow camera devices (exclusively virtual camera index 1, avoiding blocked webcam 0 and non-existent indices)."""
        # If camera is ALREADY actively open in this process, reuse its handle immediately
        if active_cap is not None and active_cap.isOpened():
            w = int(active_cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
            h = int(active_cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080
            mean_val = float(np.mean(active_last_frame)) if active_last_frame is not None else 128.0
            std_val = float(np.std(active_last_frame)) if active_last_frame is not None else 30.0
            idx = active_idx if active_idx is not None else 1
            return [{
                "index": idx,
                "name": f"Camera {idx} (OBS Virtual Camera)",
                "is_opened": True,
                "width": w,
                "height": h,
                "mean_brightness": round(mean_val, 1),
                "std_dev": round(std_val, 1),
                "is_active": True,
                "is_obs_candidate": True,
            }]

        devices = []
        # Probe exclusively index 1 (OBS Virtual Camera) to avoid DirectShow index errors on indices 2+
        for idx in [1]:
            try:
                cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
                if cap.isOpened():
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
                    ret, frame = cap.read()
                    if ret and frame is not None and frame.size > 0:
                        h, w = frame.shape[:2]
                        mean_val = float(np.mean(frame))
                        std_val = float(np.std(frame))
                        devices.append({
                            "index": idx,
                            "name": f"Camera {idx} (OBS Virtual Camera)",
                            "is_opened": True,
                            "width": w,
                            "height": h,
                            "mean_brightness": round(mean_val, 1),
                            "std_dev": round(std_val, 1),
                            "is_active": True,
                            "is_obs_candidate": True,
                        })
                    cap.release()
            except Exception as e:
                logger.debug("Camera probe error on index %d: %s", idx, e)
        return devices


    def get_available_cameras(self) -> List[dict]:
        """Instance method that safely queries available devices without interrupting the active video capture."""
        try:
            curr_idx = int(self.config.system.camera_index)
        except (TypeError, ValueError):
            curr_idx = 1
        return self.list_available_cameras(
            active_cap=self.cap,
            active_idx=curr_idx,
            active_last_frame=self.last_raw_frame,
        )

    def auto_detect_virtual_camera(self) -> Tuple[bool, int | str, str]:
        """Automatically find and switch to an active virtual/OBS camera stream."""
        raw_devices = self.get_available_cameras()

        # Strictly exclude index 0 (blocked physical webcam)
        devices = [d for d in raw_devices if d.get("index") not in (0, "0")]
        if not devices:
            fallback = self.config.system.camera_index
            if fallback in (0, "0", None, ""):
                fallback = 1
            return False, fallback, "No camera devices detected."

        # Prioritize candidate devices (high variance/brightness typical for OBS)
        obs_candidates = [d for d in devices if d.get("is_obs_candidate")]
        best_device = obs_candidates[0] if obs_candidates else devices[0]
        target_idx = best_device["index"]
        if target_idx in (0, "0"):
            target_idx = 1
        success = self.set_camera_source(target_idx)
        if success and self.cap is not None:
            ret, frame = self.cap.read()
            if ret and frame is not None:
                self.last_raw_frame = frame.copy()
                self.registrar.auto_calibrate(frame)
        return success, target_idx, f"Connected to {best_device['name']}."

    def _sync_strokes_with_twin(self, detected_strokes: List[DetectedStroke]) -> None:
        """Reconcile extracted strokes with authoritative twin store using Commit Truth Table."""
        twin = self.manager.twin_store if self.manager is not None else self.twin_store
        exec_store = self.manager.execution_store if self.manager is not None else self.exec_store
        changed = False

        for stroke in detected_strokes:
            bbox_tuple = stroke.bounding_box.to_tlbr()
            centroid_tuple = stroke.centroid
            cx, cy = centroid_tuple

            # Strictly reject strokes within fixed UI docks (header, left tool palette, floating bottom pen dock, corner controls)
            if cx < 120.0 or cy < 120.0:
                continue
            if cy > (self.height - 110.0) and (0.22 * self.width <= cx <= 0.78 * self.width):
                continue
            if cy > (self.height - 85.0) and (cx < 200.0 or cx > (self.width - 260.0)):
                continue

            # Spatial match search
            best_match = None
            for obj_id, obj in list(twin.objects.items()):
                if obj.state in (PhysicalState.STABLE_INK, PhysicalState.NEW_INK):
                    dist = np.hypot(obj.centroid[0] - centroid_tuple[0], obj.centroid[1] - centroid_tuple[1])
                    if dist <= self.config.perception.matching_centroid_dist_mm:
                        best_match = obj
                        break

            if best_match is not None:
                event = ReconcilerEvent(
                    event_type=EventType.OBSERVATION_FRAME_EVALUATED,
                    target_object_id=best_match.id,
                    evidence_type=ObservationType.OBS_INK,
                    spatial_match=True,
                    points=stroke.polygon.points,
                    holes=stroke.polygon.holes,
                    bbox=bbox_tuple,
                    centroid=centroid_tuple,
                    confidence=0.95,
                    color_bgr=stroke.color_estimate_bgr,
                    area_mm2=stroke.area_mm2,
                )
            else:
                new_id = f"ink_cam_{stroke.stroke_id}_{int(centroid_tuple[0])}_{int(centroid_tuple[1])}"
                event = ReconcilerEvent(
                    event_type=EventType.OBSERVATION_FRAME_EVALUATED,
                    target_object_id=new_id,
                    evidence_type=ObservationType.OBS_INK,
                    spatial_match=False,
                    points=stroke.polygon.points,
                    holes=stroke.polygon.holes,
                    bbox=bbox_tuple,
                    centroid=centroid_tuple,
                    confidence=0.95,
                    color_bgr=stroke.color_estimate_bgr,
                    area_mm2=stroke.area_mm2,
                )
                changed = True

            new_twin, _, actions = reconcile(twin, exec_store, event, self.config)
            # Only update camera-related objects or new detections, preserving manual/simulated strokes
            for k, v in new_twin.objects.items():
                twin.objects[k] = v

        if actions and self.manager is not None and hasattr(self.manager, "event_bus"):
            for act in actions:
                row_matched = act.payload.get("row_matched", 1)
                summary = f"Truth Table Row #{row_matched}: {act.action_type} on {act.object_id or 'surface'}"
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(
                            self.manager.event_bus.broadcast_event(
                                BusEvent(
                                    type=EventType.RECONCILER_ACTION_DISPATCHED,
                                    payload={
                                        "row_matched": row_matched,
                                        "object_id": act.object_id,
                                        "summary": summary,
                                        "action_type": act.action_type,
                                    },
                                )
                            )
                        )
                except Exception:
                    pass

        # Broadcast state update to WebSocket clients only if new ink was discovered
        if changed and self.manager is not None and hasattr(self.manager, "event_bus"):
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(
                        self.manager.event_bus.broadcast_event(
                            BusEvent(
                                type=EventType.PHYSICAL_TWIN_UPDATED,
                                payload=twin.to_dict(),
                            )
                        )
                    )
            except Exception as e:
                logger.debug("Error broadcasting twin update: %s", e)

    def generate_frame(self, draw_hud: bool = False) -> Tuple[np.ndarray, bytes]:
        """Produce video frame, apply homography crop, detect ink, render HUD, and return JPEG."""
        now = time.time()
        # Fast path: Return cached frame if called within 25ms and not drawing custom HUD
        if not draw_hud and self._cached_canvas is not None and (now - self._last_capture_time) < 0.025:
            return self._cached_canvas, self._cached_jpeg

        with self._capture_lock:
            # Check cache again inside lock
            if not draw_hud and self._cached_canvas is not None and (time.time() - self._last_capture_time) < 0.025:
                return self._cached_canvas, self._cached_jpeg

            frame_captured = False
            canvas = None
            self.frame_count += 1
            self._fps_counter += 1
            if now - self._last_fps_calc >= 1.0:
                self.measured_fps = max(1, int(self._fps_counter / max(0.001, now - self._last_fps_calc)))
                self._fps_counter = 0
                self._last_fps_calc = now

            if self.cap is not None and self.cap.isOpened():
                try:
                    ret, frame = self.cap.read()
                    if ret and frame is not None and frame.size > 0:
                        self.last_raw_frame = frame.copy()
                        frame_captured = True

                        # 1. Perspective Crop & Rectification
                        if self.registrar.is_calibrated:
                            canvas = self.registrar.warp_to_board(frame)
                        else:
                            # Attempt auto-detection periodically until calibrated
                            if self.frame_count % 15 == 0 or self.frame_count <= 5:
                                success, _, _ = self.registrar.auto_calibrate(frame)
                                if success:
                                    # Sync dynamically measured board dimensions into streamer + config
                                    new_w = int(round(self.registrar.board_width_mm))
                                    new_h = int(round(self.registrar.board_height_mm))
                                    if (new_w, new_h) != (self.width, self.height):
                                        self.width  = new_w
                                        self.height = new_h
                                        self.config.system.board_width_mm  = float(new_w)
                                        self.config.system.board_height_mm = float(new_h)
                                        self.twin_store.set_board_dimensions(new_w, new_h)
                                        if self.manager is not None:
                                            self.manager.twin_store.set_board_dimensions(new_w, new_h)
                                        logger.info(
                                            "Board dimensions auto-measured from camera: %d x %d mm",
                                            new_w, new_h,
                                        )
                                    canvas = self.registrar.warp_to_board(frame)
                                else:
                                    canvas = cv2.resize(frame, (self.width, self.height))
                            else:
                                canvas = cv2.resize(frame, (self.width, self.height))

                        # 2. Real-Time Ink & Text Detection (runs every 3 frames for 10 Hz perception)
                        if self.frame_count % 3 == 0 and canvas is not None:
                            baseline_mgr = get_default_baseline_manager()
                            ref = baseline_mgr.current_baseline

                            strokes = self.stroke_extractor.detect_whiteboard_ink(
                                canvas,
                                baseline_frame=ref,
                            )
                            self._sync_strokes_with_twin(strokes)

                            # 11-Channel Perception Pipeline against Reference Baseline
                            if ref is not None:
                                try:
                                    if ref.shape[:2] != canvas.shape[:2]:
                                        ref = cv2.resize(ref, (canvas.shape[1], canvas.shape[0]))
                                    diff_maps = compute_difference_maps(canvas, ref)
                                    shadow_mask = detect_shadow_mask(canvas, ref)
                                    glare_mask = self._glare_filter.detect_glare_mask(canvas, ref)
                                    proj_likelihood = self._proj_decoupler.compute_likelihood(canvas, ref)
                                    if self._prev_canvas is None or self._prev_canvas.shape != canvas.shape:
                                        self._prev_canvas = canvas.copy()
                                    is_occluded, occlusion_mask, _ = self._occlusion_detector.evaluate_frame(
                                        canvas, self._prev_canvas
                                    )
                                    self._prev_canvas = canvas.copy()
                                    result = self._fusion_engine.fuse(
                                        diff_maps, shadow_mask, glare_mask, proj_likelihood, occlusion_mask
                                    )
                                    channel_means = {
                                        name: round(float(np.mean(getattr(diff_maps, name))), 4)
                                        for name in diff_maps.channel_names()
                                    }
                                    raw_mean = float(np.mean(result.raw_score))
                                    fused_mean = float(np.mean(result.fused_score))
                                    self._last_perception = {
                                        "raw_score_mean": round(raw_mean, 4),
                                        "fused_score_mean": round(fused_mean, 4),
                                        "channels": channel_means,
                                        "glare": bool(np.any(glare_mask)),
                                        "shadow": bool(np.any(shadow_mask)),
                                        "projector_likelihood": round(float(np.mean(proj_likelihood)), 4),
                                        "is_occluded": is_occluded,
                                    }
                                except Exception as pe:
                                    logger.debug("Perception pipeline error: %s", pe)
                except Exception as e:
                    logger.debug("Frame read or perception error: %s", e)

            if not frame_captured or canvas is None:
                # Synthetic Whiteboard surface background (light off-white)
                canvas = np.full((self.height, self.width, 3), 248, dtype=np.uint8)

            # 3. Composite HUD debug overlays only when explicitly requested
            if draw_hud:
                canvas_hud = draw_hud_overlays(canvas.copy(), self.twin_store, self.exec_store, self.config)
                success, jpeg_buf = cv2.imencode(".jpg", canvas_hud, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                return canvas_hud, jpeg_buf.tobytes() if success else b""

            # Encode to JPEG
            success, jpeg_buf = cv2.imencode(".jpg", canvas, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            jpeg_bytes = jpeg_buf.tobytes() if success else b""

            # Cache the generated frame
            self._cached_canvas = canvas
            self._cached_jpeg = jpeg_bytes
            self._last_capture_time = time.time()
            return canvas, jpeg_bytes

    def get_sensor_dimensions(self) -> Tuple[int, int]:
        """Return camera sensor frame dimensions (width, height), defaulting to 1080p (1920, 1080)."""
        if self.last_raw_frame is not None and self.last_raw_frame.size > 0:
            h, w = self.last_raw_frame.shape[:2]
            return (int(w), int(h))
        if self.cap is not None and self.cap.isOpened():
            w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if w > 0 and h > 0:
                return (w, h)
        return (1920, 1080)

    def generate_raw_frame(self) -> Tuple[np.ndarray, bytes]:
        """Return the un-warped raw camera sensor frame (for calibration / crop handle dragging)."""
        now = time.time()
        if self._cached_raw_frame is not None and (now - self._last_raw_capture_time) < 0.035:
            return self._cached_raw_frame, self._cached_raw_jpeg

        with self._capture_lock:
            if self._cached_raw_frame is not None and (time.time() - self._last_raw_capture_time) < 0.035:
                return self._cached_raw_frame, self._cached_raw_jpeg

            raw = None
            if self.cap is not None and self.cap.isOpened():
                try:
                    ret, frame = self.cap.read()
                    if ret and frame is not None and frame.size > 0:
                        self.last_raw_frame = frame.copy()
                        raw = frame.copy()
                except Exception:
                    pass

            if raw is None:
                if self.last_raw_frame is not None and self.last_raw_frame.size > 0:
                    raw = self.last_raw_frame.copy()
                else:
                    raw = np.full((1080, 1920, 3), 40, dtype=np.uint8)
                    cv2.putText(raw, "NO CAMERA ATTACHED (VIRTUAL MODE)", (500, 540), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (200, 200, 200), 2)

            success, jpeg_buf = cv2.imencode(".jpg", raw, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            jpeg_bytes = jpeg_buf.tobytes() if success else b""
            self._cached_raw_frame = raw
            self._cached_raw_jpeg = jpeg_bytes
            self._last_raw_capture_time = time.time()
            return raw, jpeg_bytes

    def broadcast_rtp(self, jpeg_bytes: bytes) -> int:
        """Send frame through UDP RTP packetizer."""
        return self.rtp.send_frame(jpeg_bytes, self.width, self.height)

    async def mjpeg_stream_generator(self) -> AsyncGenerator[bytes, None]:
        """HTTP multipart/x-mixed-replace MJPEG generator for browser clients."""
        interval = 1.0 / self.config.system.fps
        while True:
            t0 = time.time()
            _, jpeg_bytes = self.generate_frame()

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + jpeg_bytes + b"\r\n"
            )
            elapsed = time.time() - t0
            await asyncio.sleep(max(0.005, interval - elapsed))

    async def raw_mjpeg_stream_generator(self) -> AsyncGenerator[bytes, None]:
        """Raw un-warped camera MJPEG generator for manual calibration modal."""
        interval = 1.0 / 15.0  # 15 fps for calibration preview
        while True:
            t0 = time.time()
            _, jpeg_bytes = self.generate_raw_frame()
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + jpeg_bytes + b"\r\n"
            )
            elapsed = time.time() - t0
            await asyncio.sleep(max(0.005, interval - elapsed))

    def close(self) -> None:
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        self.rtp.close()
