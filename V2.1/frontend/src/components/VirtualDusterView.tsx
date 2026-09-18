import React from 'react';
import { DusterIcon, SlidersIcon, CheckCircleIcon } from './icons';
import { useConfigStore } from '../store/useConfigStore';
import { useExecutionStore } from '../store/useExecutionStore';

export const VirtualDusterView: React.FC = () => {
  const config = useConfigStore((state) => state.config);
  const homeDock = useConfigStore((state) => state.homeDock);
  const updateConfig = useConfigStore((state) => state.updateConfig);

  const dusterPose = useExecutionStore((state) => state.dusterPose);

  const handleWidthChange = (val: number) => {
    updateConfig({ duster_width_mm: val });
    useExecutionStore.getState().updateDusterPose({ swept_width_mm: val });
  };

  const handleHeightChange = (val: number) => {
    updateConfig({ duster_height_mm: val });
    useExecutionStore.getState().updateDusterPose({ swept_height_mm: val });
  };

  const handleOverlapChange = (val: number) => {
    updateConfig({ lane_overlap: val });
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-3 space-y-3">
      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
        <div className="flex items-center space-x-2">
          <DusterIcon className="w-4 h-4 text-cyan-400" />
          <h2 className="font-semibold text-xs text-slate-100 tracking-wide uppercase">
            Actuator Geometry &amp; Dynamic Dock
          </h2>
        </div>
        <span className="font-mono text-xs text-emerald-400 font-bold flex items-center space-x-1">
          <CheckCircleIcon className="w-3.5 h-3.5" />
          <span>Config-Driven</span>
        </span>
      </div>

      {/* Actuator Dimensions Display */}
      <div className="grid grid-cols-3 gap-2 font-mono text-xs">
        <div className="bg-slate-850 p-2 rounded border border-slate-800 text-center">
          <span className="text-slate-400 text-[10px] block">Width (w)</span>
          <span className="text-cyan-400 font-bold text-sm block mt-0.5">
            {config.duster_width_mm} mm
          </span>
        </div>

        <div className="bg-slate-850 p-2 rounded border border-slate-800 text-center">
          <span className="text-slate-400 text-[10px] block">Height (h)</span>
          <span className="text-cyan-400 font-bold text-sm block mt-0.5">
            {config.duster_height_mm} mm
          </span>
        </div>

        <div className="bg-slate-850 p-2 rounded border border-slate-800 text-center">
          <span className="text-slate-400 text-[10px] block">Thickness (t)</span>
          <span className="text-slate-300 font-bold text-sm block mt-0.5">
            {config.duster_thickness_mm} mm
          </span>
        </div>
      </div>

      {/* Dynamic Home Dock Invariant Calculation */}
      <div className="bg-slate-850 p-2.5 rounded border border-slate-800 space-y-1 font-mono text-xs">
        <div className="flex justify-between text-slate-300">
          <span className="text-slate-400">Dynamic Home Dock:</span>
          <span className="text-cyan-300 font-bold">
            ({homeDock.x.toFixed(1)}, {homeDock.y.toFixed(1)}) mm
          </span>
        </div>
        <div className="flex justify-between text-slate-300">
          <span className="text-slate-400">Current Pose:</span>
          <span className="text-slate-200">
            ({dusterPose.x.toFixed(1)}, {dusterPose.y.toFixed(1)}) mm | {dusterPose.theta.toFixed(0)} deg
          </span>
        </div>
        <div className="text-[10px] text-slate-400">
          x_home = w/2 = {(config.duster_width_mm / 2).toFixed(1)} | y_home = H - h/2 ={' '}
          {(config.board_height_mm - config.duster_height_mm / 2).toFixed(1)}
        </div>
      </div>

      {/* Live Sliders for Dynamic Sizing Validation */}
      <div className="space-y-2 font-mono text-xs pt-1">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-1 text-slate-400">
            <SlidersIcon className="w-3.5 h-3.5" />
            <span>Lane Overlap:</span>
          </div>
          <span className="text-cyan-400 font-bold">
            {(config.lane_overlap * 100).toFixed(0)}% (
            {(config.duster_height_mm * (1 - config.lane_overlap)).toFixed(1)} mm step)
          </span>
        </div>
        <input
          type="range"
          min="0.10"
          max="0.50"
          step="0.01"
          value={config.lane_overlap}
          onChange={(e) => handleOverlapChange(Number(e.target.value))}
          className="w-full h-1 bg-slate-700 rounded appearance-none cursor-pointer accent-cyan-400"
        />

        <div className="grid grid-cols-2 gap-2 pt-1 text-[11px]">
          <div>
            <span className="text-slate-400 block mb-1">Duster Width:</span>
            <input
              type="range"
              min="100"
              max="240"
              value={config.duster_width_mm}
              onChange={(e) => handleWidthChange(Number(e.target.value))}
              className="w-full h-1 bg-slate-700 rounded appearance-none cursor-pointer accent-cyan-400"
            />
          </div>
          <div>
            <span className="text-slate-400 block mb-1">Duster Height:</span>
            <input
              type="range"
              min="30"
              max="90"
              value={config.duster_height_mm}
              onChange={(e) => handleHeightChange(Number(e.target.value))}
              className="w-full h-1 bg-slate-700 rounded appearance-none cursor-pointer accent-cyan-400"
            />
          </div>
        </div>
      </div>
    </div>
  );
};
