import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';
import { SystemConfig } from '../types';

export interface ConfigState {
  config: SystemConfig;
  homeDock: { x: number; y: number; theta: number };
}

export interface ConfigActions {
  updateConfig: (partial: Partial<SystemConfig>) => void;
}

export type ConfigStore = ConfigState & ConfigActions;

const INITIAL_CONFIG: SystemConfig = {
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

function computeHomeDock(config: SystemConfig) {
  return {
    x: config.duster_width_mm / 2.0,
    y: config.board_height_mm - config.duster_height_mm / 2.0,
    theta: 0.0,
  };
}

export const useConfigStore = create<ConfigStore>()(
  subscribeWithSelector((set) => ({
    config: INITIAL_CONFIG,
    homeDock: computeHomeDock(INITIAL_CONFIG),
    updateConfig: (partial) =>
      set((state) => {
        const nextConfig = { ...state.config, ...partial };
        return {
          config: nextConfig,
          homeDock: computeHomeDock(nextConfig),
        };
      }),
  }))
);
