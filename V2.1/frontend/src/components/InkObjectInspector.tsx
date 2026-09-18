import React from 'react';
import { TargetIcon, RefreshCwIcon, AlertTriangleIcon, ShieldAlertIcon } from './icons';
import { useTwinStore } from '../store/useTwinStore';
import { PhysicalTwinState } from '../types';

export const InkObjectInspector: React.FC = () => {
  const selectedObjectId = useTwinStore((state) => state.selectedObjectId);
  const inkObjects = useTwinStore((state) => state.inkObjects);
  const updateInkObject = useTwinStore((state) => state.updateInkObject);

  const selectedObject = selectedObjectId ? inkObjects[selectedObjectId] : null;

  const getStateBadge = (state: PhysicalTwinState) => {
    switch (state) {
      case 'NEW_INK':
        return 'bg-amber-950/70 text-amber-300 border-amber-800';
      case 'STABLE_INK':
        return 'bg-blue-950/70 text-blue-300 border-blue-800';
      case 'OCCLUDED':
        return 'bg-orange-950/70 text-orange-300 border-orange-800 animate-pulse';
      case 'PARTIALLY_CLEANED':
        return 'bg-pink-950/70 text-pink-300 border-pink-800';
      case 'CLEANED':
        return 'bg-emerald-950/70 text-emerald-300 border-emerald-800';
      case 'PERMANENT_DEFECT':
        return 'bg-rose-950/70 text-rose-300 border-rose-800 font-bold';
      default:
        return 'bg-slate-800 text-slate-400 border-slate-700';
    }
  };

  const handlePromoteToDefect = () => {
    if (!selectedObject) return;
    updateInkObject(selectedObject.id, {
      state: 'PERMANENT_DEFECT',
      is_defect: true,
    });
  };

  const handleIncrementReclean = () => {
    if (!selectedObject) return;
    const nextAttempts = selectedObject.reclean_attempts + 1;
    if (nextAttempts >= 3) {
      // Row 21 of commit truth table: force PERMANENT_DEFECT
      updateInkObject(selectedObject.id, {
        reclean_attempts: nextAttempts,
        state: 'PERMANENT_DEFECT',
        is_defect: true,
      });
    } else {
      updateInkObject(selectedObject.id, {
        reclean_attempts: nextAttempts,
        state: 'PARTIALLY_CLEANED',
      });
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-3 space-y-3">
      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
        <div className="flex items-center space-x-2">
          <TargetIcon className="w-4 h-4 text-cyan-400" />
          <h2 className="font-semibold text-xs text-slate-100 tracking-wide uppercase">
            Physical Twin Ink Inspector
          </h2>
        </div>
        {selectedObject && (
          <span className="font-mono text-xs text-cyan-400 font-bold">
            {selectedObject.id}
          </span>
        )}
      </div>

      {!selectedObject ? (
        <div className="py-6 text-center text-xs text-slate-500 font-mono">
          Click an ink object on the canvas to inspect physical state & re-clean history
        </div>
      ) : (
        <div className="space-y-2.5 text-xs">
          {/* Top Attributes */}
          <div className="grid grid-cols-2 gap-2 font-mono">
            <div className="bg-slate-850 p-2 rounded border border-slate-800">
              <span className="text-slate-400 text-[10px] block">Physical State</span>
              <span
                className={`inline-block mt-0.5 px-2 py-0.5 rounded text-[11px] border ${getStateBadge(
                  selectedObject.state
                )}`}
              >
                {selectedObject.state}
              </span>
            </div>

            <div className="bg-slate-850 p-2 rounded border border-slate-800">
              <span className="text-slate-400 text-[10px] block">Coordinate Frame</span>
              <span className="text-slate-200 text-[11px] font-bold block mt-0.5">
                {selectedObject.frame}
              </span>
            </div>

            <div className="bg-slate-850 p-2 rounded border border-slate-800">
              <span className="text-slate-400 text-[10px] block">Centroid (x, y)</span>
              <span className="text-slate-200 text-[11px] block mt-0.5">
                ({selectedObject.centroid[0].toFixed(1)}, {selectedObject.centroid[1].toFixed(1)}) mm
              </span>
            </div>

            <div className="bg-slate-850 p-2 rounded border border-slate-800">
              <span className="text-slate-400 text-[10px] block">Surface Area</span>
              <span className="text-slate-200 text-[11px] block mt-0.5">
                {selectedObject.area_mm2.toFixed(0)} mm&sup2;
              </span>
            </div>
          </div>

          {/* Re-Clean Attempt Progress & Safety Loop Cap (max 3) */}
          <div className="bg-slate-850 p-2.5 rounded border border-slate-800 space-y-1.5 font-mono">
            <div className="flex items-center justify-between text-xs">
              <div className="flex items-center space-x-1 text-slate-300">
                <RefreshCwIcon className="w-3.5 h-3.5 text-amber-400" />
                <span>Re-Clean Attempts:</span>
              </div>
              <span
                className={`font-bold ${
                  selectedObject.reclean_attempts >= 3
                    ? 'text-rose-400'
                    : 'text-amber-400'
                }`}
              >
                {selectedObject.reclean_attempts} / 3 (Cap)
              </span>
            </div>

            {/* 3-Step Bar */}
            <div className="grid grid-cols-3 gap-1.5 h-2">
              {[1, 2, 3].map((step) => (
                <div
                  key={`step-${step}`}
                  className={`rounded-sm transition ${
                    step <= selectedObject.reclean_attempts
                      ? step === 3
                        ? 'bg-rose-500 shadow-sm shadow-rose-500/50'
                        : 'bg-amber-500'
                      : 'bg-slate-800'
                  }`}
                />
              ))}
            </div>

            {selectedObject.reclean_attempts >= 3 && (
              <div className="flex items-center space-x-1.5 text-rose-400 text-[11px] pt-1">
                <ShieldAlertIcon className="w-3.5 h-3.5 flex-shrink-0" />
                <span>Max re-clean cap hit! Promoted to PERMANENT_DEFECT.</span>
              </div>
            )}
          </div>

          {/* Detection Confidence Bar */}
          <div className="bg-slate-850 p-2 rounded border border-slate-800 space-y-1 font-mono">
            <div className="flex justify-between text-[11px]">
              <span className="text-slate-400">Confidence Score:</span>
              <span className="text-cyan-400 font-bold">
                {(selectedObject.confidence * 100).toFixed(1)}%
              </span>
            </div>
            <div className="w-full bg-slate-800 h-1.5 rounded overflow-hidden">
              <div
                className="bg-cyan-500 h-full rounded transition-all"
                style={{ width: `${selectedObject.confidence * 100}%` }}
              />
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center space-x-2 pt-1 font-mono">
            <button
              onClick={handleIncrementReclean}
              disabled={selectedObject.reclean_attempts >= 3}
              className="flex-1 flex items-center justify-center space-x-1.5 px-2.5 py-1.5 bg-amber-600/20 hover:bg-amber-600/30 text-amber-300 rounded border border-amber-500/40 disabled:opacity-40 disabled:pointer-events-none transition"
            >
              <RefreshCwIcon className="w-3.5 h-3.5" />
              <span>Simulate Re-Clean</span>
            </button>

            <button
              onClick={handlePromoteToDefect}
              className="flex items-center justify-center space-x-1.5 px-2.5 py-1.5 bg-rose-600/20 hover:bg-rose-600/30 text-rose-300 rounded border border-rose-500/40 transition"
            >
              <AlertTriangleIcon className="w-3.5 h-3.5" />
              <span>Mark Defect</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
