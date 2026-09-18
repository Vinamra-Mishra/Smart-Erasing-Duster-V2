import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';
import {
  ExecutionState,
  DusterPose,
  TrajectoryPlan,
  ResidualTier,
  OperationalMetrics,
} from '../types';

export interface ExecutionStoreState {
  executionState: ExecutionState;
  dusterPose: DusterPose;
  currentTrajectory: TrajectoryPlan | null;
  currentWaypointIndex: number;
  residualTier: ResidualTier;
  metrics: OperationalMetrics;
  isPaused: boolean;
  activeScenarioId: number | null;
}

export interface ExecutionStoreActions {
  setExecutionState: (executionState: ExecutionState) => void;
  updateDusterPose: (pose: Partial<DusterPose>) => void;
  setTrajectory: (plan: TrajectoryPlan | null) => void;
  setWaypointIndex: (idx: number) => void;
  setResidualTier: (tier: ResidualTier) => void;
  setMetrics: (metrics: Partial<OperationalMetrics>) => void;
  setIsPaused: (paused: boolean) => void;
  setActiveScenario: (id: number | null) => void;
  resetDusterToHome: (homeDock: { x: number; y: number; theta: number }) => void;
}

export type ExecutionStore = ExecutionStoreState & ExecutionStoreActions;

const INITIAL_POSE: DusterPose = {
  x: 81.0,
  y: 671.0,
  theta: 0.0,
  swept_width_mm: 162.0,
  swept_height_mm: 58.0,
  is_contacting: false,
};

const INITIAL_METRICS: OperationalMetrics = {
  precision: 0.985,
  recall: 0.978,
  iou: 0.964,
  fpr: 0.002,
  residual_fraction: 0.0,
  cleaning_coverage: 1.0,
  tracking_stability: 0.995,
};

export const useExecutionStore = create<ExecutionStore>()(
  subscribeWithSelector((set) => ({
    executionState: 'IDLE',
    dusterPose: INITIAL_POSE,
    currentTrajectory: null,
    currentWaypointIndex: 0,
    residualTier: 'TIER_1_CLEANED',
    metrics: INITIAL_METRICS,
    isPaused: false,
    activeScenarioId: null,

    setExecutionState: (executionState) => set({ executionState }),

    updateDusterPose: (pose) =>
      set((state) => ({
        dusterPose: { ...state.dusterPose, ...pose },
      })),

    setTrajectory: (plan) =>
      set({
        currentTrajectory: plan,
        currentWaypointIndex: 0,
      }),

    setWaypointIndex: (idx) => set({ currentWaypointIndex: idx }),

    setResidualTier: (tier) => set({ residualTier: tier }),

    setMetrics: (partial) =>
      set((state) => ({
        metrics: { ...state.metrics, ...partial },
      })),

    setIsPaused: (paused) => set({ isPaused: paused }),

    setActiveScenario: (id) => set({ activeScenarioId: id }),

    resetDusterToHome: (homeDock) =>
      set((state) => ({
        dusterPose: {
          ...state.dusterPose,
          x: homeDock.x,
          y: homeDock.y,
          theta: homeDock.theta,
          is_contacting: false,
        },
        currentTrajectory: null,
        currentWaypointIndex: 0,
        executionState: 'IDLE',
      })),
  }))
);
