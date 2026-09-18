'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  DusterIcon,
  ActivityIcon,
  StopIcon,
  SparklesIcon,
  EyeOffIcon,
  CropIcon,
  CompassIcon,
  LayersIcon,
} from './icons';
import { useExecutionStore } from '../store/useExecutionStore';
import { useTwinStore } from '../store/useTwinStore';
import { usePerceptionStore } from '../store/usePerceptionStore';
import { api } from '../api/client';

interface NavbarProps {
  onOpenCalibration?: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({ onOpenCalibration }) => {
  const pathname = usePathname();
  const executionState = useExecutionStore((state) => state.executionState);
  const setExecutionState = useExecutionStore((state) => state.setExecutionState);
  const streamConnected = usePerceptionStore((state) => state.streamConnected);
  const streamFps = usePerceptionStore((state) => state.streamFps);
  const inkObjects = useTwinStore((state) => state.inkObjects);
  const boardOccluded = useTwinStore((state) => state.boardOccluded);
  const baselineEpoch = useTwinStore((state) => state.baselineEpoch);

  const activeInkCount = Object.values(inkObjects).filter(
    (obj) => obj.state !== 'CLEANED'
  ).length;

  const handleEmergencyStop = async () => {
    setExecutionState('STOPPED');
    try {
      await api.emergencyStop();
    } catch {
      // Local state already updated
    }
  };

  const getExecutionBadgeColor = () => {
    switch (executionState) {
      case 'CLEANING_ACTIVE':
        return 'bg-emerald-900/60 text-emerald-300 border-emerald-500/40 animate-pulse';
      case 'PLANNING':
      case 'VERIFYING':
        return 'bg-cyan-900/60 text-cyan-300 border-cyan-500/40';
      case 'RECLEAN_PENDING':
        return 'bg-amber-900/60 text-amber-300 border-amber-500/40';
      case 'STOPPED':
      case 'SAFETY_LOCK':
        return 'bg-rose-900/60 text-rose-300 border-rose-500/40';
      default:
        return 'bg-slate-800 text-slate-300 border-slate-700';
    }
  };

  const navLinks = [
    { href: '/', label: 'Mission Control', icon: DusterIcon },
    { href: '/calibration', label: 'Crop & Geometry', icon: CropIcon },
    { href: '/perception', label: '11-Ch Perception', icon: ActivityIcon },
    { href: '/planner', label: 'Path Planner', icon: CompassIcon },
    { href: '/audit', label: 'Replay & Audit', icon: LayersIcon },
  ];

  return (
    <header className="bg-slate-900 border-b border-slate-800 px-3 py-2 flex items-center justify-between select-none flex-wrap gap-2">
      {/* Brand & System Title */}
      <div className="flex items-center space-x-3">
        <Link href="/" className="flex items-center space-x-2.5 group">
          <div className="w-8 h-8 rounded-lg bg-cyan-600/20 border border-cyan-500/40 flex items-center justify-center text-cyan-400 group-hover:border-cyan-400 transition">
            <DusterIcon className="w-4 h-4" strokeWidth={1.75} />
          </div>
          <div>
            <div className="flex items-center space-x-1.5">
              <h1 className="font-semibold text-xs tracking-wide text-slate-100 group-hover:text-cyan-300 transition">
                SMART ERASING DUSTER
              </h1>
              <span className="px-1 py-0.2 text-[9px] font-mono font-medium rounded bg-cyan-950 text-cyan-400 border border-cyan-800/60">
                V2.1 TWIN
              </span>
            </div>
            <p className="text-[10px] text-slate-400">
              Multi-Signal Perception | Coverage Planner | Dual-Channel Twin
            </p>
          </div>
        </Link>
      </div>

      {/* Center Navigation Links (Multi-Page App Router) */}
      <nav className="flex items-center space-x-1 bg-slate-950/80 p-1 rounded-lg border border-slate-800">
        {navLinks.map((link) => {
          const Icon = link.icon;
          const isActive = pathname === link.href;
          return (
            <Link
              key={link.href}
              href={link.href}
              className={`flex items-center space-x-1.5 px-2.5 py-1 rounded text-xs font-mono transition ${
                isActive
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 font-semibold shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-850'
              }`}
            >
              <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-cyan-400' : 'text-slate-400'}`} />
              <span>{link.label}</span>
            </Link>
          );
        })}
      </nav>

      {/* Real-time Status Badges & Emergency Stop */}
      <div className="flex items-center space-x-2 text-xs">
        {/* Stream Health */}
        <div
          className={`flex items-center space-x-1.5 px-2 py-0.5 rounded border font-mono text-[11px] ${
            streamConnected
              ? 'bg-emerald-950/50 text-emerald-400 border-emerald-800/50'
              : 'bg-rose-950/50 text-rose-400 border-rose-800/50'
          }`}
        >
          <span
            className={`w-1.5 h-1.5 rounded-full ${
              streamConnected ? 'bg-emerald-400 animate-ping' : 'bg-rose-500'
            }`}
          />
          <span>{streamConnected ? `RTP ${streamFps} FPS` : 'OFFLINE'}</span>
        </div>

        {/* Baseline Epoch */}
        <div className="hidden xl:flex items-center space-x-1 px-2 py-0.5 rounded border bg-slate-850 text-slate-300 border-slate-700 font-mono text-[11px]">
          <SparklesIcon className="w-3 h-3 text-cyan-400" />
          <span>Epoch #{baselineEpoch.epoch_id}</span>
        </div>

        {/* Occlusion Warning */}
        {boardOccluded && (
          <div className="flex items-center space-x-1 px-2 py-0.5 rounded border bg-amber-950/70 text-amber-300 border-amber-800 animate-pulse font-medium text-[11px]">
            <EyeOffIcon className="w-3 h-3" />
            <span>OCCLUDED</span>
          </div>
        )}

        {/* Active Ink Count */}
        <div className="hidden lg:flex items-center space-x-1 px-2 py-0.5 rounded border bg-slate-850 text-slate-300 border-slate-700 font-mono text-[11px]">
          <ActivityIcon className="w-3 h-3 text-indigo-400" />
          <span>Ink: {activeInkCount}</span>
        </div>

        {/* Execution State */}
        <div
          className={`px-2.5 py-0.5 rounded border font-mono font-semibold tracking-wide text-[11px] ${getExecutionBadgeColor()}`}
        >
          {executionState}
        </div>

        {/* Camera Crop Modal Quick Trigger */}
        {onOpenCalibration && (
          <button
            onClick={onOpenCalibration}
            className="flex items-center space-x-1 px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-750 text-cyan-400 border border-cyan-800/60 font-mono text-[11px] transition shadow-sm"
            title="Auto-Crop Whiteboard or Adjust Corners"
          >
            <CropIcon className="w-3 h-3" />
            <span>Crop</span>
          </button>
        )}

        {/* Emergency Stop Button */}
        <button
          onClick={handleEmergencyStop}
          className="flex items-center space-x-1 px-2.5 py-0.5 bg-rose-600 hover:bg-rose-700 text-white rounded font-semibold text-xs transition shadow-sm active:scale-95 border border-rose-500"
          title="Emergency Stop All Actuators"
          aria-label="Emergency Stop"
        >
          <StopIcon className="w-3 h-3 fill-current" />
          <span>E-STOP</span>
        </button>
      </div>
    </header>
  );
};
export default Navbar;
