import React, { useState } from 'react';
import { EyeIcon, SunIcon, ProjectorIcon, ActivityIcon, Maximize2Icon, XCircleIcon } from './icons';
import { usePerceptionStore } from '../store/usePerceptionStore';
import { useConfigStore } from '../store/useConfigStore';
import { PerceptionChannelInfo } from '../types';

export const PerceptionDebugger: React.FC = () => {
  const channels = usePerceptionStore((state) => state.channels);
  const activeChannelId = usePerceptionStore((state) => state.activeChannelId);
  const setActiveChannel = usePerceptionStore((state) => state.setActiveChannel);
  const channelValues = usePerceptionStore((state) => state.channelValues);
  const rawScore = usePerceptionStore((state) => state.rawScore);
  const evidenceScore = usePerceptionStore((state) => state.evidenceScore);
  const shadowDetected = usePerceptionStore((state) => state.shadowDetected);
  const glareDetected = usePerceptionStore((state) => state.glareDetected);
  const projectorLikelihood = usePerceptionStore((state) => state.projectorLikelihood);
  const boardWidth = useConfigStore((state) => state.config.board_width_mm);
  const boardHeight = useConfigStore((state) => state.config.board_height_mm);

  const [inspectChannel, setInspectChannel] = useState<PerceptionChannelInfo | null>(null);

  const getDomainBadge = (domain: string) => {
    switch (domain) {
      case 'RGB':
        return 'bg-red-950/60 text-red-400 border-red-800/60';
      case 'HSV':
        return 'bg-amber-950/60 text-amber-400 border-amber-800/60';
      case 'Lab':
        return 'bg-blue-950/60 text-blue-400 border-blue-800/60';
      case 'Edge':
        return 'bg-cyan-950/60 text-cyan-400 border-cyan-800/60';
      case 'Contrast':
        return 'bg-purple-950/60 text-purple-400 border-purple-800/60';
      default:
        return 'bg-slate-800 text-slate-300 border-slate-700';
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-3 space-y-3">
      {/* Header & Overall Evidence Fusion Score */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
        <div className="flex items-center space-x-2">
          <EyeIcon className="w-4 h-4 text-cyan-400" />
          <h2 className="font-semibold text-xs text-slate-100 tracking-wide uppercase">
            11-Channel Perception Diff Engine
          </h2>
        </div>
        <div className="flex items-center space-x-2 font-mono text-xs">
          <span className="text-slate-400">Fusion Score:</span>
          <span
            className={`px-2 py-0.5 rounded font-bold border ${
              evidenceScore >= 0.8
                ? 'bg-emerald-950 text-emerald-400 border-emerald-800'
                : evidenceScore >= 0.5
                ? 'bg-amber-950 text-amber-400 border-amber-800'
                : 'bg-slate-800 text-slate-400 border-slate-700'
            }`}
          >
            {(evidenceScore * 100).toFixed(1)}%
          </span>
        </div>
      </div>

      {/* Disturbance Filters & Likelihoods */}
      <div className="grid grid-cols-3 gap-2 text-xs font-mono">
        {/* Shadow Rejection */}
        <div className="bg-slate-850 p-2 rounded border border-slate-800 flex items-center justify-between">
          <div className="flex items-center space-x-1.5 text-slate-300">
            <SunIcon className="w-3.5 h-3.5 text-amber-400" />
            <span className="text-[11px]">Shadow Filter</span>
          </div>
          <span
            className={`px-1.5 py-0.5 text-[10px] rounded border ${
              shadowDetected
                ? 'bg-amber-950 text-amber-300 border-amber-800'
                : 'bg-slate-800 text-slate-400 border-slate-700'
            }`}
          >
            {shadowDetected ? 'REJECTED' : 'CLEAR'}
          </span>
        </div>

        {/* Specular Glare */}
        <div className="bg-slate-850 p-2 rounded border border-slate-800 flex items-center justify-between">
          <div className="flex items-center space-x-1.5 text-slate-300">
            <ActivityIcon className="w-3.5 h-3.5 text-cyan-400" />
            <span className="text-[11px]">Specular Glare</span>
          </div>
          <span
            className={`px-1.5 py-0.5 text-[10px] rounded border ${
              glareDetected
                ? 'bg-rose-950 text-rose-300 border-rose-800'
                : 'bg-slate-800 text-slate-400 border-slate-700'
            }`}
          >
            {glareDetected ? 'SATURATED' : 'NOMINAL'}
          </span>
        </div>

        {/* Projector Mode A Likelihood */}
        <div className="bg-slate-850 p-2 rounded border border-slate-800 flex items-center justify-between">
          <div className="flex items-center space-x-1.5 text-slate-300">
            <ProjectorIcon className="w-3.5 h-3.5 text-purple-400" />
            <span className="text-[11px]">Mode A Proj</span>
          </div>
          <span
            className={`px-1.5 py-0.5 text-[10px] rounded border ${
              projectorLikelihood >= 0.8
                ? 'bg-purple-950 text-purple-300 border-purple-800 font-bold'
                : projectorLikelihood >= 0.3
                ? 'bg-amber-950 text-amber-300 border-amber-800'
                : 'bg-slate-800 text-slate-400 border-slate-700'
            }`}
          >
            {(projectorLikelihood * 100).toFixed(0)}%
          </span>
        </div>
      </div>

      {/* 11-Channel Difference Heatmap Grid (3 columns x 4 rows) */}
      <div className="grid grid-cols-3 gap-2">
        {channels.map((ch) => {
          const isActive = activeChannelId === ch.id;
          const channelKey = ch.id.replace('ch_', '');
          const val = channelValues[ch.id] ?? channelValues[channelKey] ?? 0;
          return (
            <div
              key={ch.id}
              onClick={() => setActiveChannel(ch.id)}
              className={`p-2 rounded-md border text-left cursor-pointer transition flex flex-col justify-between ${
                isActive
                  ? 'bg-cyan-950/40 border-cyan-500 shadow-md'
                  : 'bg-slate-850 border-slate-800 hover:border-slate-700'
              }`}
            >
              <div className="flex items-center justify-between mb-1.5">
                <span className="font-mono font-bold text-xs text-slate-200">{ch.name}</span>
                <span
                  className={`text-[9px] font-mono px-1 py-0.5 rounded border ${getDomainBadge(
                    ch.domain
                  )}`}
                >
                  {ch.domain}
                </span>
              </div>

              {/* Heatmap preview canvas simulation with live diff */}
              <div className="w-full h-10 rounded bg-slate-950 border border-slate-800 relative overflow-hidden flex items-center justify-center mb-1">
                {/* Intensity gradient opacity tied to live value */}
                <div
                  className="w-full h-full transition-opacity duration-300"
                  style={{
                    opacity: Math.max(0.15, Math.min(1.0, val * 2.5)),
                    background:
                      ch.domain === 'RGB'
                        ? 'radial-gradient(circle at 40% 50%, #dc2626 0%, #1e1b4b 70%)'
                        : ch.domain === 'HSV'
                        ? 'radial-gradient(circle at 60% 40%, #f59e0b 0%, #064e3b 70%)'
                        : ch.domain === 'Lab'
                        ? 'radial-gradient(circle at 50% 50%, #3b82f6 0%, #0f172a 70%)'
                        : ch.domain === 'Edge'
                        ? 'radial-gradient(circle at 45% 55%, #06b6d4 0%, #09090b 70%)'
                        : 'radial-gradient(circle at 55% 45%, #a855f7 0%, #0f172a 70%)',
                  }}
                />
                <span className="absolute top-1 left-1 text-[8px] font-mono text-white/70 bg-black/60 px-1 rounded">
                  w={ch.weight}
                </span>
                <span className="absolute bottom-1 right-1 text-[9px] font-mono font-bold text-cyan-300 bg-black/75 px-1 rounded border border-cyan-900/50">
                  {(val * 100).toFixed(1)}%
                </span>
              </div>

              <div className="flex items-center justify-between text-[10px] text-slate-400">
                <span className="truncate max-w-[80px]" title={ch.description}>
                  {ch.description.split(' ')[0]}
                </span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setInspectChannel(ch);
                  }}
                  className="hover:text-cyan-300 p-0.5 rounded"
                  title="Inspect Channel Full View"
                >
                  <Maximize2Icon className="w-3 h-3" />
                </button>
              </div>
            </div>
          );
        })}

        {/* 12th Card: Evidence Fusion Score Map */}
        <div
          onClick={() => setActiveChannel('fusion_composite')}
          className={`p-2 rounded-md border text-left cursor-pointer transition flex flex-col justify-between ${
            activeChannelId === 'fusion_composite'
              ? 'bg-cyan-950/40 border-cyan-500 shadow-md'
              : 'bg-slate-850 border-slate-800 hover:border-slate-700'
          }`}
        >
          <div className="flex items-center justify-between mb-1.5">
            <span className="font-mono font-bold text-xs text-emerald-400">S_raw</span>
            <span className="text-[9px] font-mono px-1 py-0.5 rounded border bg-emerald-950 text-emerald-400 border-emerald-800">
              Fusion
            </span>
          </div>
          <div className="w-full h-10 rounded bg-slate-950 border border-slate-800 relative overflow-hidden flex items-center justify-center mb-1">
            <div
              className="w-full h-full transition-opacity duration-300"
              style={{
                opacity: Math.max(0.2, evidenceScore),
                background:
                  'radial-gradient(circle at 50% 50%, #10b981 0%, #064e3b 50%, #022c22 90%)',
              }}
            />
            <span className="absolute text-[9px] font-mono font-bold text-emerald-300 bg-black/75 px-1.5 py-0.5 rounded border border-emerald-900/50">
              {(rawScore * 100).toFixed(0)}%
            </span>
          </div>
          <div className="flex items-center justify-between text-[10px] text-slate-400">
            <span>Fused Score</span>
            <span className="font-mono font-bold text-emerald-400">{(evidenceScore * 100).toFixed(0)}%</span>
          </div>
        </div>
      </div>


      {/* Inspect Modal */}
      {inspectChannel && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-lg max-w-lg w-full p-4 space-y-3 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-2">
              <div className="flex items-center space-x-2">
                <span className="font-mono font-bold text-base text-cyan-400">
                  {inspectChannel.name}
                </span>
                <span
                  className={`text-xs font-mono px-2 py-0.5 rounded border ${getDomainBadge(
                    inspectChannel.domain
                  )}`}
                >
                  {inspectChannel.domain} Channel
                </span>
              </div>
              <button
                onClick={() => setInspectChannel(null)}
                className="text-slate-400 hover:text-white"
                title="Close"
              >
                <XCircleIcon className="w-5 h-5" />
              </button>
            </div>

            <div
              className="w-full bg-slate-950 rounded border border-slate-800 relative overflow-hidden flex items-center justify-center"
              style={{ aspectRatio: `${boardWidth} / ${boardHeight}` }}
            >
              <div
                className="w-full h-full opacity-80"
                style={{
                  background:
                    inspectChannel.domain === 'RGB'
                      ? 'radial-gradient(circle at 40% 50%, #dc2626 0%, #1e1b4b 80%)'
                      : inspectChannel.domain === 'HSV'
                      ? 'radial-gradient(circle at 60% 40%, #f59e0b 0%, #064e3b 80%)'
                      : inspectChannel.domain === 'Lab'
                      ? 'radial-gradient(circle at 50% 50%, #3b82f6 0%, #0f172a 80%)'
                      : 'radial-gradient(circle at 45% 55%, #06b6d4 0%, #09090b 80%)',
                }}
              />
              <div className="absolute top-2 left-2 bg-slate-900/80 px-2 py-1 rounded text-xs font-mono text-slate-300 border border-slate-700">
                FRAME_BOARD Rectified Diff
              </div>
            </div>

            <div className="space-y-1.5 text-xs text-slate-300">
              <div className="flex justify-between font-mono">
                <span className="text-slate-400">Mathematical Formulation:</span>
                <span className="text-cyan-300">{inspectChannel.description}</span>
              </div>
              <div className="flex justify-between font-mono">
                <span className="text-slate-400">Fusion Weight (w_i):</span>
                <span className="text-slate-200">{inspectChannel.weight}</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
