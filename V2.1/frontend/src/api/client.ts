import axios from 'axios';
import { SystemConfig, TrajectoryPlan, BaselineEpoch } from '../types';

const BACKEND_BASE = process.env.NEXT_PUBLIC_BACKEND_URL
  ? `${process.env.NEXT_PUBLIC_BACKEND_URL.replace(/\/$/, '')}/api`
  : '/api';

const apiClient = axios.create({
  baseURL: BACKEND_BASE,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const api = {
  async getConfig(): Promise<SystemConfig> {
    try {
      const response = await apiClient.get<any>('/config');
      const data = response.data;
      if (data && data.config) {
        const sys = data.config.system || {};
        const clean = data.config.cleaning || {};
        return {
          board_width_mm: sys.board_width_mm ?? 1000.0,
          board_height_mm: sys.board_height_mm ?? 700.0,
          duster_width_mm: clean.duster_width_mm ?? 162.0,
          duster_height_mm: clean.duster_height_mm ?? 58.0,
          duster_thickness_mm: clean.duster_thickness_mm ?? 42.0,
          lane_overlap: clean.lane_overlap ?? 0.28,
          clean_threshold: clean.clean_threshold ?? 0.01,
          residual_major_threshold: clean.residual_major_threshold ?? 0.05,
          max_reclean_attempts: clean.max_reclean_attempts ?? 3,
          dirty_board_threshold: data.config.baseline?.dirty_board_threshold ?? 0.04,
        };
      }
      return data;
    } catch {
      // Fallback default config if backend is initializing
      return {
        board_width_mm: 1000.0,
        board_height_mm: 700.0,
        duster_width_mm: 162.0,
        duster_height_mm: 58.0,
        duster_thickness_mm: 42.0,
        lane_overlap: 0.28,
        clean_threshold: 0.01,
        residual_major_threshold: 0.05,
        max_reclean_attempts: 3,
        dirty_board_threshold: 0.04,
      };
    }
  },

  async captureBaseline(): Promise<BaselineEpoch> {
    const response = await apiClient.post<BaselineEpoch>('/reference/capture');
    return response.data;
  },

  async generatePlan(targetObjectIds?: string[]): Promise<TrajectoryPlan> {
    const response = await apiClient.post<TrajectoryPlan>('/planner/generate', {
      target_ids: targetObjectIds,
    });
    return response.data;
  },

  async dispatchPlan(planId?: string, plan?: TrajectoryPlan): Promise<{ status: string }> {
    const response = await apiClient.post<{ status: string }>('/planner/dispatch', {
      plan_id: planId,
      plan: plan,
    });
    return response.data;
  },

  async stepPlan(): Promise<{ status: string; waypoint_index: number }> {
    const response = await apiClient.post<{ status: string; waypoint_index: number }>(
      '/planner/step'
    );
    return response.data;
  },

  async emergencyStop(): Promise<{ status: string }> {
    const response = await apiClient.post<{ status: string }>('/planner/stop');
    return response.data;
  },

  async resetDuster(): Promise<{ status: string }> {
    const response = await apiClient.post<{ status: string }>('/planner/reset');
    return response.data;
  },

  async injectScenario(scenarioId: number): Promise<{ status: string; scenario: string }> {
    const response = await apiClient.post<{ status: string; scenario: string }>(
      `/simulator/scenario/${scenarioId}`
    );
    return response.data;
  },

  async postDrawStroke(stroke: {
    tool: string;
    points: [number, number][];
    color: string;
    size: number;
  }): Promise<{ status: string; object_id?: string }> {
    const response = await apiClient.post<{ status: string; object_id?: string }>(
      '/simulator/draw',
      stroke
    );
    return response.data;
  },

  async clearBoard(): Promise<{ status: string }> {
    const response = await apiClient.post<{ status: string }>('/simulator/clear');
    return response.data;
  },

  async getCalibrationStatus(): Promise<any> {
    const response = await apiClient.get('/calibration/status');
    return response.data;
  },

  async setManualCorners(
    corners: {
      top_left: [number, number];
      top_right: [number, number];
      bottom_right: [number, number];
      bottom_left: [number, number];
    },
    boardSize?: {
      board_width_mm: number;
      board_height_mm: number;
    }
  ): Promise<any> {
    const payload: any = { corners };
    if (boardSize) {
      payload.board_width_mm = boardSize.board_width_mm;
      payload.board_height_mm = boardSize.board_height_mm;
    }
    const response = await apiClient.post('/calibration/set-corners', payload);
    return response.data;
  },

  async setBoardSize(board_width_mm: number, board_height_mm: number): Promise<any> {
    const response = await apiClient.post('/calibration/board-size', {
      board_width_mm,
      board_height_mm,
    });
    return response.data;
  },

  async autoDetectCorners(): Promise<any> {
    const response = await apiClient.post('/calibration/auto-detect');
    return response.data;
  },

  async resetCalibration(): Promise<any> {
    const response = await apiClient.post('/calibration/reset');
    return response.data;
  },

  async getCameraDevices(): Promise<{
    current_source: number | string;
    is_opened: boolean;
    devices: any[];
    sensor_width?: number;
    sensor_height?: number;
  }> {
    const response = await apiClient.get('/camera/devices');
    return response.data;
  },

  async setCameraSource(source: number | string): Promise<{
    success: boolean;
    source: number | string;
    is_opened: boolean;
    sensor_width?: number;
    sensor_height?: number;
  }> {
    const safeSource = source === 0 || String(source).trim() === '0' || !source ? 1 : source;
    const response = await apiClient.post('/camera/source', { source: safeSource });
    return response.data;
  },

  async autoDetectCameraSource(): Promise<{
    success: boolean;
    source: number | string;
    message: string;
    is_opened: boolean;
    sensor_width?: number;
    sensor_height?: number;
  }> {
    const response = await apiClient.post('/camera/auto-detect-source');
    return response.data;
  },

  async getCameraSource(): Promise<{
    source: number | string;
    is_opened: boolean;
    is_calibrated: boolean;
    sensor_width?: number;
    sensor_height?: number;
  }> {
    const response = await apiClient.get('/camera/source');
    return response.data;
  },
};

