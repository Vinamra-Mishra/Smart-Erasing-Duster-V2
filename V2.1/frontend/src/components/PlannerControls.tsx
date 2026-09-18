import React, { useState } from 'react';
import {
  CompassIcon,
  PlayIcon,
  PauseIcon,
  StepForwardIcon,
  HomeIcon,
  ActivityIcon,
} from './icons';
import { useExecutionStore } from '../store/useExecutionStore';
import { useConfigStore } from '../store/useConfigStore';
import { api } from '../api/client';
import { ResidualTier } from '../types';
import { sendWsEvent } from '../hooks/useWebSocket';

export const PlannerControls: React.FC = () => {
  const executionState = useExecutionStore((state) => state.executionState);
  const setExecutionState = useExecutionStore((state) => state.setExecutionState);
  const currentTrajectory = useExecutionStore((state) => state.currentTrajectory);
  const setTrajectory = useExecutionStore((state) => state.setTrajectory);
  const currentWaypointIndex = useExecutionStore((state) => state.currentWaypointIndex);
  const setWaypointIndex = useExecutionStore((state) => state.setWaypointIndex);
  const updateDusterPose = useExecutionStore((state) => state.updateDusterPose);
  const residualTier = useExecutionStore((state) => state.residualTier);
  const metrics = useExecutionStore((state) => state.metrics);
  const isPaused = useExecutionStore((state) => state.isPaused);
  const setIsPaused = useExecutionStore((state) => state.setIsPaused);

  const homeDock = useConfigStore((state) => state.homeDock);
  const config = useConfigStore((state) => state.config);

  const [isPlanning, setIsPlanning] = useState(false);

  // Generate synthetic or backend Boustrophedon sweep
  const handleGeneratePlan = async () => {
    setIsPlanning(true);
    try {
      // 1. Trigger via WebSocket
      sendWsEvent('GENERATE_PLAN', {
        lane_overlap: config.lane_overlap,
        use_full_transit: true,
      });

      // 2. Query backend planner endpoint for instant UI update
      const plan = await api.generatePlan();
      if (plan && plan.waypoints && plan.waypoints.length > 0) {
        setTrajectory(plan);
        setExecutionState('PLANNING');
      }
    } catch (err) {
      console.warn("Backend planner call error:", err);
    } finally {
      setIsPlanning(false);
    }
  };

  // Dispatch cleaning mission
  const handleDispatch = async () => {
    setIsPaused(false);
    setExecutionState('CLEANING_ACTIVE');

    // 1. Dispatch over WebSocket as primary
    sendWsEvent('DISPATCH_PLAN', {
      plan_id: currentTrajectory?.id,
      plan: currentTrajectory || undefined,
    });

    // 2. Also send via REST with full plan payload
    try {
      await api.dispatchPlan(currentTrajectory?.id, currentTrajectory || undefined);
    } catch (err) {
      console.warn("REST dispatch fallback:", err);
    }
  };

  // Single step forward
  const handleStep = async () => {
    if (!currentTrajectory) return;
    const nextIdx = currentWaypointIndex + 1;
    if (nextIdx < currentTrajectory.waypoints.length) {
      setWaypointIndex(nextIdx);
      const wp = currentTrajectory.waypoints[nextIdx];
      updateDusterPose({
        x: wp.x,
        y: wp.y,
        theta: wp.theta,
        is_contacting: wp.segment_type === 'sweep',
      });
    } else {
      setExecutionState('VERIFYING');
    }
  };

  const handleResetToHome = async () => {
    useExecutionStore.getState().resetDusterToHome(homeDock);
    try {
      await api.resetDuster();
    } catch {
      // Handled
    }
  };

  const getResidualBadge = (tier: ResidualTier) => {
    switch (tier) {
      case 'TIER_1_CLEANED':
        return 'bg-emerald-950 text-emerald-400 border-emerald-800';
      case 'TIER_2_FINE_RESIDUAL':
        return 'bg-amber-950 text-amber-400 border-amber-800';
      case 'TIER_3_MAJOR_RESIDUAL':
        return 'bg-rose-950 text-rose-400 border-rose-800 font-bold';
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-3 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
        <div className="flex items-center space-x-2">
          <CompassIcon className="w-4 h-4 text-cyan-400" />
          <h2 className="font-semibold text-xs text-slate-100 tracking-wide uppercase">
            Coverage Path Planner (28% Overlap)
          </h2>
        </div>
        {currentTrajectory && (
          <span className="font-mono text-[11px] text-slate-400">
            {currentWaypointIndex + 1} / {currentTrajectory.waypoints.length} WPs
          </span>
        )}
      </div>

      {/* Primary Action Buttons */}
      <div className="grid grid-cols-2 gap-2 text-xs font-mono">
        <button
          onClick={handleGeneratePlan}
          disabled={isPlanning}
          className="flex items-center justify-center space-x-1.5 px-3 py-2 bg-cyan-600 hover:bg-cyan-500 text-white font-semibold rounded transition shadow disabled:opacity-50"
        >
          <CompassIcon className="w-3.5 h-3.5" />
          <span>{isPlanning ? 'Planning...' : 'Generate Sweep'}</span>
        </button>

        <button
          onClick={handleDispatch}
          disabled={!currentTrajectory || executionState === 'CLEANING_ACTIVE'}
          className="flex items-center justify-center space-x-1.5 px-3 py-2 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold rounded transition shadow disabled:opacity-40"
        >
          <PlayIcon className="w-3.5 h-3.5" />
          <span>Dispatch Mission</span>
        </button>
      </div>

      {/* Stepping & Return Controls */}
      <div className="flex items-center space-x-2 text-xs font-mono">
        <button
          onClick={handleStep}
          disabled={!currentTrajectory}
          className="flex-1 flex items-center justify-center space-x-1 px-2.5 py-1.5 bg-slate-800 hover:bg-slate-750 text-slate-200 rounded border border-slate-700 disabled:opacity-40 transition"
        >
          <StepForwardIcon className="w-3.5 h-3.5" />
          <span>Step WP</span>
        </button>

        <button
          onClick={() => setIsPaused(!isPaused)}
          disabled={executionState !== 'CLEANING_ACTIVE'}
          className="flex-1 flex items-center justify-center space-x-1 px-2.5 py-1.5 bg-slate-800 hover:bg-slate-750 text-slate-200 rounded border border-slate-700 disabled:opacity-40 transition"
        >
          {isPaused ? <PlayIcon className="w-3.5 h-3.5" /> : <PauseIcon className="w-3.5 h-3.5" />}
          <span>{isPaused ? 'Resume' : 'Pause'}</span>
        </button>

        <button
          onClick={handleResetToHome}
          className="flex-1 flex items-center justify-center space-x-1 px-2.5 py-1.5 bg-slate-800 hover:bg-slate-750 text-slate-200 rounded border border-slate-700 transition"
          title="Return duster to dynamic home dock"
        >
          <HomeIcon className="w-3.5 h-3.5" />
          <span>Home</span>
        </button>
      </div>

      {/* Residual Tier Card */}
      <div className="bg-slate-850 p-2.5 rounded border border-slate-800 space-y-2 font-mono text-xs">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-1.5 text-slate-300">
            <ActivityIcon className="w-3.5 h-3.5 text-cyan-400" />
            <span>Residual Execution Tier:</span>
          </div>
          <span
            className={`px-2 py-0.5 rounded text-[10px] border font-bold ${getResidualBadge(
              residualTier
            )}`}
          >
            {residualTier}
          </span>
        </div>

        {/* Operational Metrics (IoU, Precision, Recall, Coverage) */}
        <div className="grid grid-cols-3 gap-1.5 pt-1 text-[11px]">
          <div className="bg-slate-900 p-1.5 rounded border border-slate-800 text-center">
            <span className="text-slate-400 text-[10px] block">IoU</span>
            <span className="font-bold text-cyan-400">{(metrics.iou * 100).toFixed(1)}%</span>
          </div>
          <div className="bg-slate-900 p-1.5 rounded border border-slate-800 text-center">
            <span className="text-slate-400 text-[10px] block">Precision</span>
            <span className="font-bold text-emerald-400">
              {(metrics.precision * 100).toFixed(1)}%
            </span>
          </div>
          <div className="bg-slate-900 p-1.5 rounded border border-slate-800 text-center">
            <span className="text-slate-400 text-[10px] block">Recall</span>
            <span className="font-bold text-emerald-400">
              {(metrics.recall * 100).toFixed(1)}%
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
