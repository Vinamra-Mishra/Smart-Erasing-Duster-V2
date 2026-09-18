'use client';

import React from 'react';
import { PerceptionDebugger } from '../../components/PerceptionDebugger';
import { BaselineEpochView } from '../../components/BaselineEpochView';
import { RtpCameraStreamView } from '../../components/RtpCameraStreamView';

export default function PerceptionLabPage() {
  return (
    <div className="flex-1 flex flex-col p-4 gap-4 overflow-y-auto">
      {/* Header Info */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-3">
        <div>
          <h1 className="text-lg font-bold font-mono text-cyan-400">
            11-Channel Perception &amp; Baseline Diff Lab
          </h1>
          <p className="text-xs text-slate-400">
            Multi-space difference maps (RGB, HSV, Lab), shadow chrominance filtering, specular glare rejection &amp; baseline epoch auditor.
          </p>
        </div>
      </div>

      {/* Main Grid: Stream on top / side and Perception debuggers */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        {/* Left Column (2 cols): 11-Channel Diff Engine & Baseline Auditor */}
        <div className="xl:col-span-2 flex flex-col gap-4">
          <PerceptionDebugger />
          <BaselineEpochView />
        </div>

        {/* Right Column: Live Camera Feed for Real-time Diff Verification */}
        <div className="flex flex-col gap-4">
          <div className="h-[360px]">
            <RtpCameraStreamView />
          </div>
          <div className="bg-slate-900 border border-slate-800 rounded-lg p-3 text-xs space-y-2">
            <h3 className="font-mono text-cyan-400 font-semibold uppercase text-[11px]">
              Perception Filter Invariants
            </h3>
            <ul className="list-disc list-inside space-y-1 text-slate-400 text-[11px]">
              <li><strong className="text-slate-200">Shadow Filter:</strong> Evaluates chrominance ratios to suppress soft shadows without rejecting colored ink strokes.</li>
              <li><strong className="text-slate-200">Specular Glare:</strong> Rejects local white saturation regions without deleting valid physical twin marks.</li>
              <li><strong className="text-slate-200">Mode A Projector:</strong> Computes continuous likelihood $[0.0, 1.0]$. Ambiguous projections are tagged UNKNOWN, never ink.</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
