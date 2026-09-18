'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { CropIcon, ActivityIcon } from './icons';
import { useConfigStore } from '../store/useConfigStore';
import { usePerceptionStore } from '../store/usePerceptionStore';

const getStreamUrl = () => {
  if (process.env.NEXT_PUBLIC_BACKEND_URL) {
    return `${process.env.NEXT_PUBLIC_BACKEND_URL.replace(/\/$/, '')}/api/camera/stream`;
  }
  if (typeof window === 'undefined') return '/api/camera/stream';
  if (window.location.port === '3000') {
    return 'http://127.0.0.1:8000/api/camera/stream';
  }
  return '/api/camera/stream';
};

interface RtpCameraStreamViewProps {
  onOpenCalibration?: () => void;
}

export const RtpCameraStreamView: React.FC<RtpCameraStreamViewProps> = ({
  onOpenCalibration,
}) => {
  const [streamKey, setStreamKey] = useState(0);
  const [streamError, setStreamError] = useState(false);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const config = useConfigStore((state) => state.config);
  const boardWidth = config.board_width_mm || 1919;
  const boardHeight = config.board_height_mm || 993;
  const streamConnected = usePerceptionStore((state) => state.streamConnected);

  const handleStreamError = useCallback(() => {
    setStreamError(true);
    if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
    retryTimerRef.current = setTimeout(() => {
      setStreamError(false);
      setStreamKey((k) => k + 1); // remount img -> reconnects stream
    }, 2500);
  }, []);

  useEffect(() => () => {
    if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
  }, []);

  return (
    <div className="flex flex-col h-full bg-slate-900 border border-slate-800 rounded-lg overflow-hidden shadow-lg">
      {/* Top Header Bar */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-slate-950 border-b border-slate-800 text-xs select-none">
        {/* Left: Stream Info */}
        <div className="flex items-center space-x-2">
          <span className="font-semibold text-emerald-400 font-mono tracking-wider uppercase text-[11px]">
            Live Camera / RTP Feed
          </span>
          <span className="inline-flex items-center space-x-1 px-1.5 py-0.5 rounded bg-emerald-950/60 border border-emerald-800/60 text-[10px] text-emerald-300 font-mono">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            <span>RTP :5004</span>
          </span>
          <span className="text-[10px] text-slate-400 font-mono hidden sm:inline">
            OBS Virtual Cam (1080p)
          </span>
        </div>

        {/* Right: Controls & Crop Action */}
        <div className="flex items-center space-x-2">
          <span className="font-mono text-[10px] text-slate-400">
            {Math.round(boardWidth)}x{Math.round(boardHeight)} mm
          </span>

          {onOpenCalibration && (
            <button
              onClick={onOpenCalibration}
              className="flex items-center space-x-1 px-2 py-0.5 bg-cyan-950/70 hover:bg-cyan-900/80 text-cyan-300 hover:text-cyan-100 rounded border border-cyan-800/70 text-[11px] font-mono transition"
              title="Open Whiteboard Crop & Corner Calibration"
            >
              <CropIcon className="w-3 h-3" />
              <span>Crop Board</span>
            </button>
          )}
        </div>
      </div>

      {/* Stream Display Viewport */}
      <div className="relative flex-1 w-full overflow-hidden bg-slate-950 flex items-center justify-center select-none">
        <div
          className="relative w-full h-full flex items-center justify-center"
          style={{ aspectRatio: `${boardWidth} / ${boardHeight}` }}
        >
          {/* Live Video Stream Feed from Camera Streamer */}
          {!streamError ? (
            <img
              key={streamKey}
              src={`${getStreamUrl()}?t=${streamKey}`}
              alt="Live Board Camera Stream"
              onError={handleStreamError}
              className="w-full h-full object-contain rounded"
            />
          ) : (
            <div className="flex flex-col items-center justify-center p-6 text-slate-500 space-y-2">
              <ActivityIcon className="w-8 h-8 text-amber-500/60 animate-pulse" />
              <span className="text-xs font-mono text-slate-400">
                Connecting to Camera Stream...
              </span>
              <span className="text-[10px] text-slate-600 font-mono">
                Reconnecting in 2.5s
              </span>
            </div>
          )}

          {/* Clean HUD Corner Markers for Verification */}
          <div className="absolute inset-0 pointer-events-none p-1.5 flex flex-col justify-between">
            <div className="flex justify-between items-start">
              <span className="px-1 py-0.5 bg-black/60 rounded text-[9px] font-mono text-slate-400 border border-slate-800">
                TL [0, 0]
              </span>
              <span className="px-1 py-0.5 bg-black/60 rounded text-[9px] font-mono text-slate-400 border border-slate-800">
                TR [{Math.round(boardWidth)}, 0]
              </span>
            </div>
            <div className="flex justify-between items-end">
              <span className="px-1 py-0.5 bg-black/60 rounded text-[9px] font-mono text-slate-400 border border-slate-800">
                BL [0, {Math.round(boardHeight)}]
              </span>
              <span className="px-1 py-0.5 bg-black/60 rounded text-[9px] font-mono text-slate-400 border border-slate-800">
                BR [{Math.round(boardWidth)}, {Math.round(boardHeight)}]
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
export default RtpCameraStreamView;
