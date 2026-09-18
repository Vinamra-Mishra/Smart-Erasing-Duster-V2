export type PhysicalTwinState =
  | 'UNKNOWN'
  | 'NEW_INK'
  | 'STABLE_INK'
  | 'OCCLUDED'
  | 'PARTIALLY_CLEANED'
  | 'CLEANED'
  | 'PERMANENT_DEFECT';

export type ResidualTier =
  | 'TIER_1_CLEANED'
  | 'TIER_2_FINE_RESIDUAL'
  | 'TIER_3_MAJOR_RESIDUAL';

export type ExecutionState =
  | 'IDLE'
  | 'PLANNING'
  | 'CLEANING_ACTIVE'
  | 'VERIFYING'
  | 'RECLEAN_PENDING'
  | 'STOPPED'
  | 'SAFETY_LOCK';

export type CoordinateFrame =
  | 'FRAME_CAMERA'
  | 'FRAME_BOARD'
  | 'FRAME_DUSTER'
  | 'FRAME_PATH';

export type ObservationEvidence =
  | 'OBS_ABSENT'
  | 'OBS_INK'
  | 'OBS_OCCLUDED'
  | 'OBS_SHADOW'
  | 'OBS_PROJECTOR'
  | 'OBS_UNCERTAIN';

export interface Point2D {
  x: number;
  y: number;
}

export interface InkObject {
  id: string;
  frame?: CoordinateFrame;
  frame_id?: CoordinateFrame;
  geometry?: [number, number][]; // Polygon vertices in FRAME_BOARD (mm)
  points?: [number, number][];
  bbox?: [number, number, number, number];
  centroid: [number, number];
  area_mm2: number;
  state: PhysicalTwinState;
  reclean_attempts: number; // 0..3 (re-clean cap)
  confidence: number; // 0.0 .. 1.0
  last_seen_frame?: number;
  is_defect?: boolean;
  stroke_color?: string;
  color_bgr?: [number, number, number];
  holes?: [number, number][][];
}

export interface CameraDevice {
  index: number;
  name: string;
  is_opened: boolean;
  width: number;
  height: number;
  mean_brightness: number;
  std_dev: number;
  is_active: boolean;
  is_obs_candidate: boolean;
}

export interface DusterPose {
  x: number; // mm in FRAME_BOARD
  y: number; // mm in FRAME_BOARD
  theta: number; // degrees
  theta_deg?: number;
  swept_width_mm: number;
  swept_height_mm: number;
  is_contacting: boolean;
}

export interface Waypoint {
  x: number;
  y: number;
  theta: number;
  v: number;
  segment_type: 'transit' | 'sweep' | 'uturn' | 'dock';
}

export interface TrajectoryPlan {
  id: string;
  waypoints: Waypoint[];
  total_length_mm: number;
  estimated_duration_sec: number;
  created_at: string;
}

export interface OperationalMetrics {
  precision: number;
  recall: number;
  iou: number;
  fpr: number;
  residual_fraction: number;
  cleaning_coverage: number;
  tracking_stability: number;
}

export interface PerceptionChannelInfo {
  id: string;
  name: string;
  domain: string;
  weight: number;
  description: string;
  sample_value?: number;
}

export interface BaselineEpoch {
  epoch_id: number;
  timestamp: string;
  edge_density: number;
  is_valid: boolean;
  is_dirty_alert: boolean;
  defect_count: number;
}

export interface ReconcilerEvent {
  id: string;
  timestamp: string;
  event_type: string;
  row_matched?: number;
  object_id?: string;
  previous_state?: string;
  next_state?: string;
  summary: string;
}

export interface SystemConfig {
  board_width_mm: number;
  board_height_mm: number;
  duster_width_mm: number;
  duster_height_mm: number;
  duster_thickness_mm: number;
  lane_overlap: number;
  clean_threshold: number;
  residual_major_threshold: number;
  max_reclean_attempts: number;
  dirty_board_threshold: number;
}

export interface ScenarioDefinition {
  id: number;
  title: string;
  subtitle: string;
  description: string;
}

export interface CalibrationStatus {
  is_calibrated: boolean;
  reprojection_error_px: number;
  homography_matrix: number[][];
  board_width_mm: number;
  board_height_mm: number;
  corners?: {
    top_left: [number, number];
    top_right: [number, number];
    bottom_right: [number, number];
    bottom_left: [number, number];
  };
  sensor_width?: number;
  sensor_height?: number;
}

