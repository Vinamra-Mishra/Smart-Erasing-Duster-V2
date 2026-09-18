'use client';

import React, { useState } from 'react';
import {
  CompassIcon,
  ActivityIcon,
  LayersIcon,
  GridIcon,
} from './icons';
import { PlannerControls } from './PlannerControls';
import { VirtualDusterView } from './VirtualDusterView';
import { PerceptionDebugger } from './PerceptionDebugger';
import { BaselineEpochView } from './BaselineEpochView';
import { InkObjectInspector } from './InkObjectInspector';
import { ScenarioBar } from './ScenarioBar';

type DockTab = 'planner' | 'perception' | 'twin' | 'all';

export const BottomControlDock: React.FC = () => {
  const [activeTab, setActiveTab] = useState<DockTab>('planner');

  return (
    <div className="flex flex-col bg-slate-900 border border-slate-800 rounded-lg overflow-hidden shadow-xl min-h-[300px] max-h-[380px]">
      {/* Dock Navigation Bar */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-slate-950 border-b border-slate-800 select-none flex-shrink-0">
        <div className="flex items-center space-x-1">
          <span className="font-mono text-[11px] text-slate-400 font-semibold tracking-wider uppercase mr-2">
            Control Dock
          </span>

          <button
            onClick={() => setActiveTab('planner')}
            className={`flex items-center space-x-1.5 px-3 py-1 rounded text-xs font-mono transition ${
              activeTab === 'planner'
                ? 'bg-cyan-950/70 text-cyan-300 border border-cyan-800/80'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-850'
            }`}
          >
            <CompassIcon className="w-3.5 h-3.5 text-cyan-400" />
            <span>Path Planner &amp; Motion</span>
          </button>

          <button
            onClick={() => setActiveTab('perception')}
            className={`flex items-center space-x-1.5 px-3 py-1 rounded text-xs font-mono transition ${
              activeTab === 'perception'
                ? 'bg-cyan-950/70 text-cyan-300 border border-cyan-800/80'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-850'
            }`}
          >
            <ActivityIcon className="w-3.5 h-3.5 text-emerald-400" />
            <span>11-Ch Perception Engine</span>
          </button>

          <button
            onClick={() => setActiveTab('twin')}
            className={`flex items-center space-x-1.5 px-3 py-1 rounded text-xs font-mono transition ${
              activeTab === 'twin'
                ? 'bg-cyan-950/70 text-cyan-300 border border-cyan-800/80'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-850'
            }`}
          >
            <LayersIcon className="w-3.5 h-3.5 text-purple-400" />
            <span>Twin Inspector &amp; Scenarios</span>
          </button>

          <button
            onClick={() => setActiveTab('all')}
            className={`flex items-center space-x-1.5 px-3 py-1 rounded text-xs font-mono transition ${
              activeTab === 'all'
                ? 'bg-cyan-950/70 text-cyan-300 border border-cyan-800/80'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-850'
            }`}
          >
            <GridIcon className="w-3.5 h-3.5 text-amber-400" />
            <span>Grid View (All)</span>
          </button>
        </div>
      </div>

      {/* Dock Content Body */}
      <div className="flex-1 overflow-y-auto p-3">
        {activeTab === 'planner' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 h-full">
            <PlannerControls />
            <VirtualDusterView />
          </div>
        )}

        {activeTab === 'perception' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 h-full">
            <PerceptionDebugger />
            <BaselineEpochView />
          </div>
        )}

        {activeTab === 'twin' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 h-full">
            <InkObjectInspector />
            <div className="flex flex-col space-y-3">
              <ScenarioBar />
            </div>
          </div>
        )}

        {activeTab === 'all' && (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            <PlannerControls />
            <PerceptionDebugger />
            <VirtualDusterView />
            <InkObjectInspector />
            <BaselineEpochView />
            <ScenarioBar />
          </div>
        )}
      </div>
    </div>
  );
};
export default BottomControlDock;
