'use client';

import React from 'react';
import { VirtualBoardCanvas } from '../../components/VirtualBoardCanvas';
import { PlannerControls } from '../../components/PlannerControls';
import { VirtualDusterView } from '../../components/VirtualDusterView';

export default function PlannerPage() {
  return (
    <div className="flex-1 flex flex-col p-4 gap-4 overflow-y-auto">
      <div className="flex items-center justify-between border-b border-slate-800 pb-3">
        <div>
          <h1 className="text-lg font-bold font-mono text-cyan-400">
            Coverage Path Planner &amp; Kinematics
          </h1>
          <p className="text-xs text-slate-400">
            Config-driven Boustrophedon sweep planning with 28% overlap, exterior rounded U-turns, and dynamic Home Dock transit.
          </p>
        </div>
      </div>

      {/* Visualizer */}
      <div className="h-[420px] w-full">
        <VirtualBoardCanvas />
      </div>

      {/* Planner Controls & Kinematics */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <PlannerControls />
        <VirtualDusterView />
      </div>
    </div>
  );
}
