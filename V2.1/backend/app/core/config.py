from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Tuple
import yaml
from pydantic import BaseModel, Field, field_validator


class TransportConfig(BaseModel):
    rtp_host: str = "127.0.0.1"
    rtp_port: int = 5004
    ws_port: int = 8000


class SystemConfig(BaseModel):
    board_width_mm: float = 1000.0
    board_height_mm: float = 700.0
    camera_index: int | str = 1
    fps: int = 30
    transport: TransportConfig = Field(default_factory=TransportConfig)

    @field_validator("camera_index", mode="after")
    @classmethod
    def validate_camera_index(cls, v: int | str) -> int | str:
        if v == 0 or str(v).strip() in ("0", ""):
            return 1
        return v


class CalibrationConfig(BaseModel):
    aruco_dict: str = "DICT_4X4_50"
    corner_ids: list[int] = Field(default_factory=lambda: [0, 1, 2, 3])


class BaselineConfig(BaseModel):
    frames_to_accumulate: int = 20
    dirty_board_threshold: float = 0.04
    allow_dirty_board_override: bool = False


class EvidenceWeights(BaseModel):
    w_rgb: float = 0.25
    w_hsv: float = 0.20
    w_lab: float = 0.20
    w_edge: float = 0.20
    w_contrast: float = 0.15


class DisturbancePenalties(BaseModel):
    w_shadow: float = 0.40
    w_glare: float = 0.50
    w_occlusion: float = 0.80
    w_projector: float = 0.60


class PerceptionConfig(BaseModel):
    evidence_weights: EvidenceWeights = Field(default_factory=EvidenceWeights)
    disturbance_penalties: DisturbancePenalties = Field(default_factory=DisturbancePenalties)
    stroke_min_area: float = 15.0
    stroke_max_expected_thickness_mm: float = 12.0
    matching_iou_threshold: float = 0.40
    matching_centroid_dist_mm: float = 30.0


class OcclusionConfig(BaseModel):
    min_area_fraction: float = 0.045
    min_displacement_px: int = 12
    confirmation_frames: int = 3


class CleaningConfig(BaseModel):
    duster_width_mm: float = 162.0
    duster_height_mm: float = 58.0
    duster_thickness_mm: float = 42.0
    lane_overlap: float = 0.28
    nominal_efficiency: float = 0.85
    clean_threshold: float = 0.01
    residual_major_threshold: float = 0.05
    max_reclean_attempts: int = 3
    max_mission_duration_sec: float = 180.0
    residual_trigger_timeout_sec: float = 5.0


class AppConfig(BaseModel):
    system: SystemConfig = Field(default_factory=SystemConfig)
    calibration: CalibrationConfig = Field(default_factory=CalibrationConfig)
    baseline: BaselineConfig = Field(default_factory=BaselineConfig)
    perception: PerceptionConfig = Field(default_factory=PerceptionConfig)
    occlusion: OcclusionConfig = Field(default_factory=OcclusionConfig)
    cleaning: CleaningConfig = Field(default_factory=CleaningConfig)

    def get_home_dock(self) -> Tuple[float, float, float]:
        """Compute home dock (x, y, theta) dynamically in FRAME_BOARD (mm).

        Invariant:
            x_home = w_duster / 2
            y_home = H_board - h_duster / 2
            theta_home = 0.0 degrees
        """
        x_home = round(self.cleaning.duster_width_mm / 2.0, 4)
        y_home = round(self.system.board_height_mm - (self.cleaning.duster_height_mm / 2.0), 4)
        return (x_home, y_home, 0.0)


_CONFIG_CACHE: AppConfig | None = None


def resolve_config_path(config_path: str | Path | None = None) -> Path:
    """Find the configuration file path across common working directories."""
    if config_path is not None:
        p = Path(config_path)
        if p.exists():
            return p

    search_paths = [
        Path("config.yaml"),
        Path("../config.yaml"),
        Path("V2.1/config.yaml"),
        Path(__file__).resolve().parent.parent.parent.parent / "config.yaml",
        Path(__file__).resolve().parent.parent.parent / "config.yaml",
    ]
    for path in search_paths:
        if path.exists():
            return path.resolve()

    return Path("config.yaml")


def load_config(config_path: str | Path | None = None) -> AppConfig:
    """Load configuration from YAML file or fallback to defaults."""
    resolved = resolve_config_path(config_path)
    if resolved.exists():
        with open(resolved, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f) or {}
        cfg = AppConfig.model_validate(raw_data)
    else:
        cfg = AppConfig()

    # Cloud environment variable overrides (e.g. HidenCloud, Docker, Heroku)
    if "RTP_HOST" in os.environ:
        cfg.system.transport.rtp_host = os.environ["RTP_HOST"]
    if "RTP_PORT" in os.environ:
        try:
            cfg.system.transport.rtp_port = int(os.environ["RTP_PORT"])
        except ValueError:
            pass
    primary_port = os.environ.get("SERVER_PORT") or os.environ.get("PORT")
    if primary_port:
        try:
            cfg.system.transport.ws_port = int(primary_port)
        except ValueError:
            pass

    return cfg


def get_config() -> AppConfig:
    """Singleton getter for cached configuration."""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is None:
        _CONFIG_CACHE = load_config()
    return _CONFIG_CACHE
