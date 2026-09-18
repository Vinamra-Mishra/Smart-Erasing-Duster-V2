import React, { useState } from 'react';
import {
  SparklesIcon,
  CameraIcon,
  ShieldAlertIcon,
} from './icons';
import { useTwinStore } from '../store/useTwinStore';
import { useConfigStore } from '../store/useConfigStore';
import { api } from '../api/client';
import { sendWsEvent } from '../hooks/useWebSocket';

function formatTimestamp(ts: string | number | undefined): string {
  if (!ts) return new Date().toLocaleTimeString();
  const num = Number(ts);
  if (!isNaN(num)) {
    return new Date(num < 1e12 ? num * 1000 : num).toLocaleTimeString();
  }
  const d = new Date(ts);
  return isNaN(d.getTime()) ? new Date().toLocaleTimeString() : d.toLocaleTimeString();
}

export const BaselineEpochView: React.FC = () => {

  const baselineEpoch = useTwinStore((state) => state.baselineEpoch);
  const setBaselineEpoch = useTwinStore((state) => state.setBaselineEpoch);
  const reconcilerEvents = useTwinStore((state) => state.reconcilerEvents);
  const dirtyThreshold = useConfigStore((state) => state.config.dirty_board_threshold);

  const [isCapturing, setIsCapturing] = useState(false);

  const handleCaptureBaseline = async () => {
    setIsCapturing(true);
    try {
      const sent = sendWsEvent('CAPTURE_BASELINE', {});
      if (!sent) {
        // Fallback to REST API if WebSocket is not open
        const epoch = await api.captureBaseline();
        setBaselineEpoch(epoch);
      }
    } catch (err) {
      console.error('Failed to capture baseline:', err);
    } finally {
      setTimeout(() => setIsCapturing(false), 600);
    }
  };

  const isDirtyAlert = baselineEpoch.epoch_id > 0 && baselineEpoch.edge_density > dirtyThreshold;

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-3 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
        <div className="flex items-center space-x-2">
          <SparklesIcon className="w-4 h-4 text-cyan-400" />
          <h2 className="font-semibold text-xs text-slate-100 tracking-wide uppercase">
            Baseline Epochs &amp; Truth Table Audit
          </h2>
        </div>
        <button
          onClick={handleCaptureBaseline}
          disabled={isCapturing}
          className="flex items-center space-x-1 px-2.5 py-1 bg-cyan-600/20 hover:bg-cyan-600/30 text-cyan-300 rounded border border-cyan-500/40 text-xs font-mono transition disabled:opacity-50"
        >
          <CameraIcon className="w-3.5 h-3.5" />
          <span>{isCapturing ? 'Capturing...' : 'Capture Baseline'}</span>
        </button>
      </div>

      {/* Epoch Metrics */}
      <div className="grid grid-cols-3 gap-2 font-mono text-xs">
        <div className="bg-slate-850 p-2 rounded border border-slate-800">
          <span className="text-slate-400 text-[10px] block">Epoch ID</span>
          <span className="text-cyan-400 font-bold block mt-0.5">
            {baselineEpoch.epoch_id > 0 ? `#${baselineEpoch.epoch_id}` : 'None'}
          </span>
        </div>

        <div className="bg-slate-850 p-2 rounded border border-slate-800">
          <span className="text-slate-400 text-[10px] block">Edge Density</span>
          <span
            className={`font-bold block mt-0.5 ${
              baselineEpoch.epoch_id === 0
                ? 'text-slate-500'
                : isDirtyAlert
                ? 'text-rose-400'
                : 'text-emerald-400'
            }`}
          >
            {baselineEpoch.epoch_id > 0 ? `${(baselineEpoch.edge_density * 100).toFixed(2)}%` : '--'}
          </span>
        </div>

        <div className="bg-slate-850 p-2 rounded border border-slate-800">
          <span className="text-slate-400 text-[10px] block">Validation</span>
          <span
            className={`text-[11px] font-bold block mt-0.5 ${
              baselineEpoch.epoch_id === 0
                ? 'text-slate-500'
                : baselineEpoch.is_valid
                ? 'text-emerald-400'
                : 'text-rose-400'
            }`}
          >
            {baselineEpoch.epoch_id === 0
              ? 'AWAITING CAPTURE'
              : baselineEpoch.is_valid
              ? 'VALIDATED'
              : 'DIRTY REJECT'}
          </span>
        </div>
      </div>


      {/* Dirty Board Alert if edge density > 4% */}
      {isDirtyAlert && (
        <div className="bg-rose-950/60 border border-rose-800 rounded p-2 text-xs text-rose-300 flex items-center space-x-2 font-mono">
          <ShieldAlertIcon className="w-4 h-4 text-rose-400 flex-shrink-0" />
          <span>
            DIRTY BOARD ALERT: Edge density &gt; {(dirtyThreshold * 100).toFixed(1)}%! Baseline
            capture aborted to prevent ghosting.
          </span>
        </div>
      )}

      {/* 21-Row Reconciler Event Bus Stream */}
      <div className="space-y-1 font-mono text-xs">
        <div className="flex items-center justify-between text-slate-400 text-[11px]">
          <span>Reconciler Event Stream:</span>
          <span>{reconcilerEvents.length} events logged</span>
        </div>

        <div className="bg-slate-950 rounded border border-slate-800 p-2 h-28 overflow-y-auto space-y-1 text-[10px]">
          {reconcilerEvents.length === 0 ? (
            <div className="text-slate-600 text-center py-6">
              Listening on /ws/events for Truth Table transitions...
            </div>
          ) : (
            reconcilerEvents.map((evt) => (
              <div
                key={evt.id}
                className="flex items-center justify-between py-0.5 border-b border-slate-900 last:border-0"
              >
                <div className="flex items-center space-x-1.5 truncate max-w-[260px]">
                  {evt.row_matched && (
                    <span className="px-1 py-0.2 bg-cyan-950 text-cyan-400 rounded border border-cyan-800/60 text-[9px] font-bold">
                      R{evt.row_matched}
                    </span>
                  )}
                  <span className="text-slate-300 truncate">{evt.summary}</span>
                </div>
                <span className="text-slate-500 text-[9px]">
                  {formatTimestamp(evt.timestamp)}
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
