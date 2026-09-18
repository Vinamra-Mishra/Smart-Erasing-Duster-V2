import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  BrushIcon,
  EraserIcon,
  HandIcon,
  ProjectorIcon,
  TargetIcon,
  Trash2Icon,
  LayersIcon,
  CropIcon,
} from './icons';
import { useTwinStore } from '../store/useTwinStore';
import { useExecutionStore } from '../store/useExecutionStore';
import { useCanvasStore } from '../store/useCanvasStore';
import { useConfigStore } from '../store/useConfigStore';
import { useCanvas } from '../hooks/useCanvas';
import { api } from '../api/client';
import { PhysicalTwinState } from '../types';

const getStreamUrl = () => {
  if (typeof window === 'undefined') return '/api/camera/stream';
  if (window.location.port === '3000') {
    return `${window.location.protocol}//127.0.0.1:8000/api/camera/stream`;
  }
  return '/api/camera/stream';
};

interface VideoOverlayCanvasProps {
  onOpenCalibration?: () => void;
}

export const VideoOverlayCanvas: React.FC<VideoOverlayCanvasProps> = ({ onOpenCalibration }) => {
  const {
    containerRef,
    handlePointerDown,
    handlePointerMove,
    handlePointerUp,
  } = useCanvas();

  const [streamKey, setStreamKey] = useState(0);
  const [streamError, setStreamError] = useState(false);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleStreamError = useCallback(() => {
    setStreamError(true);
    if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
    retryTimerRef.current = setTimeout(() => {
      setStreamError(false);
      setStreamKey((k) => k + 1); // remount img → reconnects stream
    }, 3000);
  }, []);

  useEffect(() => () => {
    if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
  }, []);

  const [showLayerMenu, setShowLayerMenu] = useState(false);


  // Store bindings
  const inkObjects = useTwinStore((state) => state.inkObjects);
  const selectedObjectId = useTwinStore((state) => state.selectedObjectId);
  const selectObject = useTwinStore((state) => state.selectObject);
  const boardOccluded = useTwinStore((state) => state.boardOccluded);

  const dusterPose = useExecutionStore((state) => state.dusterPose);
  const currentTrajectory = useExecutionStore((state) => state.currentTrajectory);
  const currentWaypointIndex = useExecutionStore((state) => state.currentWaypointIndex);
  const executionState = useExecutionStore((state) => state.executionState);

  const activeTool = useCanvasStore((state) => state.activeTool);
  const setActiveTool = useCanvasStore((state) => state.setActiveTool);
  const brushSize = useCanvasStore((state) => state.brushSize);
  const setBrushSize = useCanvasStore((state) => state.setBrushSize);
  const strokeColor = useCanvasStore((state) => state.strokeColor);
  const setStrokeColor = useCanvasStore((state) => state.setStrokeColor);
  const drawnStrokes = useCanvasStore((state) => state.drawnStrokes);
  const clearStrokes = useCanvasStore((state) => state.clearStrokes);

  const showAxes = useCanvasStore((state) => state.showAxes);
  const showBoundingBoxes = useCanvasStore((state) => state.showBoundingBoxes);
  const showTrajectories = useCanvasStore((state) => state.showTrajectories);
  const showSweptFootprint = useCanvasStore((state) => state.showSweptFootprint);
  const toggleLayer = useCanvasStore((state) => state.toggleLayer);

  const config = useConfigStore((state) => state.config);
  const homeDock = useConfigStore((state) => state.homeDock);

  const boardW = config.board_width_mm;
  const boardH = config.board_height_mm;

  // Clear board handler
  const handleClearBoard = async () => {
    clearStrokes();
    useTwinStore.getState().clearTwin();
    try {
      await api.clearBoard();
    } catch {
      // Offline fallback
    }
  };

  const getStrokeStateColor = (state: PhysicalTwinState): string => {
    switch (state) {
      case 'NEW_INK':
        return '#eab308'; // yellow/amber
      case 'STABLE_INK':
        return '#3b82f6'; // blue
      case 'OCCLUDED':
        return '#f97316'; // orange
      case 'PARTIALLY_CLEANED':
        return '#ec4899'; // pink/purple
      case 'CLEANED':
        return '#10b981'; // emerald
      case 'PERMANENT_DEFECT':
        return '#ef4444'; // crimson red
      default:
        return '#94a3b8'; // slate
    }
  };

  return (
    <div className="flex flex-col h-full bg-slate-900 border border-slate-800 rounded-lg overflow-hidden shadow-lg">
      {/* Top Canvas Toolbar */}
      <div className="bg-slate-850 px-3 py-2 border-b border-slate-800 flex items-center justify-between text-xs select-none">
        {/* Drawing Tools */}
        <div className="flex items-center space-x-1.5">
          <span className="text-slate-400 font-mono text-[11px] mr-1">FRAME_BOARD:</span>

          <button
            onClick={() => setActiveTool('brush')}
            className={`flex items-center space-x-1 px-2 py-1 rounded transition ${
              activeTool === 'brush'
                ? 'bg-cyan-600 text-white font-medium shadow'
                : 'text-slate-300 hover:bg-slate-800'
            }`}
            title="Brush Tool (Draw Physical Ink)"
          >
            <BrushIcon className="w-3.5 h-3.5" />
            <span>Brush</span>
          </button>

          <button
            onClick={() => setActiveTool('eraser')}
            className={`flex items-center space-x-1 px-2 py-1 rounded transition ${
              activeTool === 'eraser'
                ? 'bg-cyan-600 text-white font-medium shadow'
                : 'text-slate-300 hover:bg-slate-800'
            }`}
            title="Manual Eraser"
          >
            <EraserIcon className="w-3.5 h-3.5" />
            <span>Eraser</span>
          </button>

          <button
            onClick={() => setActiveTool('occluder')}
            className={`flex items-center space-x-1 px-2 py-1 rounded transition ${
              activeTool === 'occluder'
                ? 'bg-amber-600 text-white font-medium shadow'
                : 'text-slate-300 hover:bg-slate-800'
            }`}
            title="Simulate Hand / Body Occlusion"
          >
            <HandIcon className="w-3.5 h-3.5" />
            <span>Occluder</span>
          </button>

          <button
            onClick={() => setActiveTool('projector')}
            className={`flex items-center space-x-1 px-2 py-1 rounded transition ${
              activeTool === 'projector'
                ? 'bg-purple-600 text-white font-medium shadow'
                : 'text-slate-300 hover:bg-slate-800'
            }`}
            title="Simulate Digital Projector Overlay"
          >
            <ProjectorIcon className="w-3.5 h-3.5" />
            <span>Projector</span>
          </button>

          <button
            onClick={() => setActiveTool('select')}
            className={`flex items-center space-x-1 px-2 py-1 rounded transition ${
              activeTool === 'select'
                ? 'bg-cyan-600 text-white font-medium shadow'
                : 'text-slate-300 hover:bg-slate-800'
            }`}
            title="Select & Inspect Objects"
          >
            <TargetIcon className="w-3.5 h-3.5" />
            <span>Select</span>
          </button>

          {/* Marker Colors */}
          {activeTool === 'brush' && (
            <div className="flex items-center space-x-1 ml-2 pl-2 border-l border-slate-700">
              {['#2563eb', '#dc2626', '#16a34a', '#0f172a'].map((color) => (
                <button
                  key={color}
                  onClick={() => setStrokeColor(color)}
                  style={{ backgroundColor: color }}
                  className={`w-4 h-4 rounded-full border transition ${
                    strokeColor === color
                      ? 'border-white scale-110 shadow-sm'
                      : 'border-slate-600 hover:scale-105'
                  }`}
                  title={`Color ${color}`}
                />
              ))}
            </div>
          )}

          {/* Brush Size Slider */}
          <div className="flex items-center space-x-1.5 ml-2 pl-2 border-l border-slate-700">
            <span className="text-[10px] text-slate-400">Size:</span>
            <input
              type="range"
              min="4"
              max="32"
              value={brushSize}
              onChange={(e) => setBrushSize(Number(e.target.value))}
              className="w-16 h-1 bg-slate-700 rounded appearance-none cursor-pointer accent-cyan-400"
            />
            <span className="font-mono text-[10px] text-slate-300">{brushSize}mm</span>
          </div>
        </div>

        {/* Layer Controls & Clear */}
        <div className="flex items-center space-x-2 relative">
          <button
            onClick={() => setShowLayerMenu(!showLayerMenu)}
            className="flex items-center space-x-1 px-2 py-1 bg-slate-800 hover:bg-slate-750 text-slate-300 rounded border border-slate-700 transition"
            title="Toggle Canvas Overlay Layers"
          >
            <LayersIcon className="w-3.5 h-3.5 text-cyan-400" />
            <span>Layers</span>
          </button>

          {showLayerMenu && (
            <div className="absolute right-12 top-8 z-30 bg-slate-850 border border-slate-700 rounded-lg p-2.5 shadow-xl w-48 space-y-1.5">
              <label className="flex items-center justify-between text-slate-300 hover:text-white cursor-pointer text-xs">
                <span>Coordinate Axes</span>
                <input
                  type="checkbox"
                  checked={showAxes}
                  onChange={() => toggleLayer('showAxes')}
                  className="rounded border-slate-700 text-cyan-500"
                />
              </label>
              <label className="flex items-center justify-between text-slate-300 hover:text-white cursor-pointer text-xs">
                <span>Target Bounding Boxes</span>
                <input
                  type="checkbox"
                  checked={showBoundingBoxes}
                  onChange={() => toggleLayer('showBoundingBoxes')}
                  className="rounded border-slate-700 text-cyan-500"
                />
              </label>
              <label className="flex items-center justify-between text-slate-300 hover:text-white cursor-pointer text-xs">
                <span>Planned Trajectory</span>
                <input
                  type="checkbox"
                  checked={showTrajectories}
                  onChange={() => toggleLayer('showTrajectories')}
                  className="rounded border-slate-700 text-cyan-500"
                />
              </label>
              <label className="flex items-center justify-between text-slate-300 hover:text-white cursor-pointer text-xs">
                <span>Swept Footprint</span>
                <input
                  type="checkbox"
                  checked={showSweptFootprint}
                  onChange={() => toggleLayer('showSweptFootprint')}
                  className="rounded border-slate-700 text-cyan-500"
                />
              </label>
            </div>
          )}

          {onOpenCalibration && (
            <button
              onClick={onOpenCalibration}
              className="flex items-center space-x-1 px-2 py-1 bg-slate-800 hover:bg-slate-750 text-cyan-300 rounded border border-cyan-800/60 transition"
              title="Crop whiteboard or switch camera source"
            >
              <CropIcon className="w-3.5 h-3.5 text-cyan-400" />
              <span>Crop / Camera</span>
            </button>
          )}

          <button
            onClick={handleClearBoard}
            className="flex items-center space-x-1 px-2 py-1 bg-rose-950/40 hover:bg-rose-900/60 text-rose-300 rounded border border-rose-800/50 transition"
            title="Clear all strokes and reset twin"
          >
            <Trash2Icon className="w-3.5 h-3.5" />
            <span>Clear</span>
          </button>
        </div>
      </div>

      {/* Main Board Viewport with Dynamic Aspect Ratio */}
      <div
        className="relative flex-1 flex items-center justify-center p-3 bg-slate-950 overflow-hidden"
        style={{ minHeight: '380px' }}
      >
        <div
          ref={containerRef}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          style={{ aspectRatio: `${boardW} / ${boardH}` }}
          className="relative w-full max-w-full max-h-full bg-slate-900 border border-slate-700 rounded shadow-2xl overflow-hidden cursor-crosshair select-none"
        >
          {/* Background Layer: Camera MJPEG stream or High-Fidelity Whiteboard simulation canvas */}
          {!streamError ? (
            <img
              key={streamKey}
              src={getStreamUrl()}
              alt="Live Board Stream"
              onError={handleStreamError}
              className="absolute inset-0 w-full h-full object-cover pointer-events-none opacity-90"
            />
          ) : (
            <div className="absolute inset-0 w-full h-full bg-[#f8fafc] pointer-events-none">
              {/* Subtle whiteboard grid (100mm = 10% step) */}
              <svg className="w-full h-full opacity-15" xmlns="http://www.w3.org/2000/svg" viewBox={`0 0 ${boardW} ${boardH}`}>
                <defs>
                  <pattern
                    id="grid-100"
                    width="100"
                    height="100"
                    patternUnits="userSpaceOnUse"
                  >
                    <path
                      d="M 100 0 L 0 0 0 100"
                      fill="none"
                      stroke="#475569"
                      strokeWidth="0.8"
                    />
                  </pattern>
                </defs>
                <rect width={boardW} height={boardH} fill="url(#grid-100)" />
              </svg>
            </div>
          )}

          {/* SVG Overlays Scaled Directly in FRAME_BOARD mm coordinates */}
          <svg
            viewBox={`0 0 ${boardW} ${boardH}`}
            className="absolute inset-0 w-full h-full pointer-events-none"
          >
            {/* Coordinate Grid & Millimeter Rulers */}
            {showAxes && (
              <g className="text-slate-400 font-mono text-[14px]">
                {/* Board Boundary */}
                <rect
                  x="0"
                  y="0"
                  width={boardW}
                  height={boardH}
                  fill="none"
                  stroke="#38bdf8"
                  strokeWidth="2"
                  strokeDasharray="6 4"
                  opacity="0.6"
                />
                {/* Horizontal Axis Ticks (every 100mm) */}
                {Array.from({ length: Math.floor(boardW / 100) + 1 }).map((_, i) => (
                  <g key={`x-tick-${i}`}>
                    <line
                      x1={i * 100}
                      y1="0"
                      x2={i * 100}
                      y2="12"
                      stroke="#38bdf8"
                      strokeWidth="1.5"
                    />
                    <text x={i * 100 + 4} y="16" fill="#38bdf8" fontSize="12">
                      {i * 100}
                    </text>
                  </g>
                ))}
                {/* Vertical Axis Ticks (every 100mm) */}
                {Array.from({ length: Math.floor(boardH / 100) + 1 }).map((_, i) => (
                  <g key={`y-tick-${i}`}>
                    <line
                      x1="0"
                      y1={i * 100}
                      x2="12"
                      y2={i * 100}
                      stroke="#38bdf8"
                      strokeWidth="1.5"
                    />
                    <text x="14" y={i * 100 + 12} fill="#38bdf8" fontSize="12">
                      {i * 100}
                    </text>
                  </g>
                ))}
              </g>
            )}

            {/* Dynamic Home Dock Footprint */}
            <g>
              <rect
                x={homeDock.x - config.duster_width_mm / 2}
                y={homeDock.y - config.duster_height_mm / 2}
                width={config.duster_width_mm}
                height={config.duster_height_mm}
                rx="4"
                fill="none"
                stroke="#64748b"
                strokeWidth="1.5"
                strokeDasharray="4 4"
                opacity="0.7"
              />
              <text
                x={homeDock.x}
                y={homeDock.y + 4}
                textAnchor="middle"
                fill="#94a3b8"
                fontSize="11"
                fontFamily="monospace"
              >
                HOME DOCK ({homeDock.x.toFixed(0)}, {homeDock.y.toFixed(0)})
              </text>
            </g>

            {/* Drawn Strokes (Simulated writing) */}
            {drawnStrokes.map((stroke) => {
              if (stroke.points.length < 2) return null;
              const pathData = stroke.points.reduce(
                (acc, pt, idx) => (idx === 0 ? `M ${pt[0]} ${pt[1]}` : `${acc} L ${pt[0]} ${pt[1]}`),
                ''
              );
              return (
                <path
                  key={stroke.id}
                  d={pathData}
                  fill="none"
                  stroke={stroke.color}
                  strokeWidth={stroke.size}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  opacity={stroke.tool === 'projector' ? 0.7 : 0.95}
                />
              );
            })}

            {/* Target Ink Polygons & Bounding Boxes */}
            {showBoundingBoxes &&
              Object.values(inkObjects).map((obj) => {
                const isSelected = selectedObjectId === obj.id;
                const stateColor = getStrokeStateColor(obj.state);

                // Compute points and bounding box
                const pts = (obj.geometry && obj.geometry.length > 0) ? obj.geometry : (obj.points || []);
                if (pts.length === 0 && !obj.bbox) return null;

                let minX = 0, maxX = 0, minY = 0, maxY = 0;
                if (pts.length > 0) {
                  const xs = pts.map((p) => p[0]);
                  const ys = pts.map((p) => p[1]);
                  minX = Math.min(...xs) - 4;
                  maxX = Math.max(...xs) + 4;
                  minY = Math.min(...ys) - 4;
                  maxY = Math.max(...ys) + 4;
                } else if (obj.bbox) {
                  minX = obj.bbox[0] - 4;
                  minY = obj.bbox[1] - 4;
                  maxX = obj.bbox[2] + 4;
                  maxY = obj.bbox[3] + 4;
                }

                let polyPath: string | null = null;
                if (pts.length >= 3) {
                  polyPath = `M ${pts[0][0]} ${pts[0][1]} ` + pts.slice(1).map((p) => `L ${p[0]} ${p[1]}`).join(' ') + ' Z';
                  if (obj.holes && obj.holes.length > 0) {
                    for (const hole of obj.holes) {
                      if (hole.length >= 2) {
                        polyPath += ` M ${hole[0][0]} ${hole[0][1]} ` + hole.slice(1).map((p) => `L ${p[0]} ${p[1]}`).join(' ') + ' Z';
                      }
                    }
                  }
                }

                return (
                  <g
                    key={obj.id}
                    className="cursor-pointer pointer-events-auto"
                    onClick={() => selectObject(obj.id)}
                  >
                    {/* Stroke polygon outline if available */}
                    {polyPath && (
                      <path
                        d={polyPath}
                        fill={`${stateColor}15`}
                        fillRule="evenodd"
                        stroke={stateColor}
                        strokeWidth="1.2"
                        strokeLinejoin="round"
                      />
                    )}
                    {/* Bounding Box */}
                    <rect
                      x={minX}
                      y={minY}
                      width={Math.max(16, maxX - minX)}
                      height={Math.max(16, maxY - minY)}
                      rx="3"
                      fill={isSelected ? `${stateColor}22` : 'none'}
                      stroke={stateColor}
                      strokeWidth={isSelected ? '2.5' : '1.5'}
                      strokeDasharray={
                        obj.state === 'OCCLUDED'
                          ? '6 4'
                          : obj.state === 'NEW_INK'
                          ? '4 2'
                          : undefined
                      }
                    />

                    {/* Tag Badge */}
                    <rect
                      x={minX}
                      y={minY - 18}
                      width={Math.max(60, obj.id.length * 7 + 10)}
                      height="16"
                      rx="2"
                      fill="#0f172a"
                      stroke={stateColor}
                      strokeWidth="1"
                    />
                    <text
                      x={minX + 4}
                      y={minY - 6}
                      fill={stateColor}
                      fontSize="10"
                      fontFamily="monospace"
                      fontWeight="bold"
                    >
                      {obj.id} [{obj.state}]
                    </text>

                    {/* Re-clean counter badge if attempts > 0 */}
                    {obj.reclean_attempts > 0 && (
                      <text
                        x={maxX}
                        y={minY - 6}
                        textAnchor="end"
                        fill="#f43f5e"
                        fontSize="10"
                        fontFamily="monospace"
                        fontWeight="bold"
                      >
                        {obj.reclean_attempts}/3
                      </text>
                    )}
                  </g>
                );
              })}

            {/* Planned Trajectory & Waypoint Splines */}
            {showTrajectories && currentTrajectory && (
              <g>
                {/* Waypoint Path Lines */}
                {currentTrajectory.waypoints.map((wp, idx) => {
                  if (idx === 0) return null;
                  const prev = currentTrajectory.waypoints[idx - 1];
                  const isSweep = wp.segment_type === 'sweep';
                  const isUturn = wp.segment_type === 'uturn';
                  const isPassed = idx <= currentWaypointIndex;

                  return (
                    <line
                      key={`traj-${idx}`}
                      x1={prev.x}
                      y1={prev.y}
                      x2={wp.x}
                      y2={wp.y}
                      stroke={
                        isPassed
                          ? '#10b981'
                          : isSweep
                          ? '#06b6d4'
                          : isUturn
                          ? '#a855f7'
                          : '#94a3b8'
                      }
                      strokeWidth={isSweep ? '2.5' : '1.5'}
                      strokeDasharray={isUturn ? '3 3' : isSweep ? undefined : '5 4'}
                      opacity={isPassed ? 0.4 : 0.85}
                    />
                  );
                })}

                {/* Waypoint dots */}
                {currentTrajectory.waypoints.map((wp, idx) => (
                  <circle
                    key={`wp-${idx}`}
                    cx={wp.x}
                    cy={wp.y}
                    r={idx === currentWaypointIndex ? '4' : '2'}
                    fill={idx === currentWaypointIndex ? '#f43f5e' : '#06b6d4'}
                  />
                ))}
              </g>
            )}

            {/* Duster Actuator Footprint (Dynamically Sized: 162 x 58 mm default) */}
            <g
              transform={`translate(${dusterPose.x}, ${dusterPose.y}) rotate(${dusterPose.theta})`}
              style={{
                transition: executionState === 'CLEANING_ACTIVE' ? 'transform 40ms linear' : 'none',
                willChange: 'transform',
              }}
            >
              {/* Swept Contact Shadow */}
              {showSweptFootprint && (
                <rect
                  x={-dusterPose.swept_width_mm / 2}
                  y={-dusterPose.swept_height_mm / 2}
                  width={dusterPose.swept_width_mm}
                  height={dusterPose.swept_height_mm}
                  rx="6"
                  fill="rgba(6, 182, 212, 0.15)"
                  stroke="#06b6d4"
                  strokeWidth="2"
                  strokeDasharray="4 2"
                />
              )}

              {/* Physical Duster Chassis */}
              <rect
                x={-dusterPose.swept_width_mm / 2 + 4}
                y={-dusterPose.swept_height_mm / 2 + 4}
                width={dusterPose.swept_width_mm - 8}
                height={dusterPose.swept_height_mm - 8}
                rx="4"
                fill="#1e293b"
                stroke="#38bdf8"
                strokeWidth="2"
              />

              {/* Center Tool Reference Crosshair */}
              <line x1="-8" y1="0" x2="8" y2="0" stroke="#f43f5e" strokeWidth="1.5" />
              <line x1="0" y1="-8" x2="0" y2="8" stroke="#f43f5e" strokeWidth="1.5" />

              {/* Forward Heading Arrow */}
              <polygon points="12,0 4,-5 4,5" fill="#38bdf8" />

              {/* Label */}
              <text
                x="0"
                y="14"
                textAnchor="middle"
                fill="#38bdf8"
                fontSize="9"
                fontFamily="monospace"
                fontWeight="bold"
              >
                DUSTER ({dusterPose.swept_width_mm}x{dusterPose.swept_height_mm})
              </text>
            </g>
          </svg>

          {/* Occlusion Alert Watermark if occluded */}
          {boardOccluded && (
            <div className="absolute inset-0 bg-amber-950/30 backdrop-blur-[1px] flex items-center justify-center pointer-events-none">
              <div className="bg-slate-900/90 border border-amber-500/60 rounded-lg px-4 py-2 text-amber-300 font-mono text-sm tracking-wider shadow-2xl flex items-center space-x-2">
                <span className="w-2.5 h-2.5 rounded-full bg-amber-400 animate-ping" />
                <span>DYNAMIC OCCLUDER ACTIVE -- TWIN INK PRESERVED</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Bottom Coordinates & Scale Status */}
      <div className="bg-slate-850 px-3 py-1.5 border-t border-slate-800 flex items-center justify-between text-[11px] font-mono text-slate-400 select-none">
        <div>
          <span>BOARD: </span>
          <span className="text-slate-200">
            {boardW}x{boardH} mm
          </span>
          <span className="mx-2">|</span>
          <span>SCALE: </span>
          <span className="text-cyan-400">1.0 px = 1.0 mm</span>
        </div>
        <div>
          <span>DUSTER POSE: </span>
          <span className="text-slate-200">
            ({dusterPose.x.toFixed(1)}, {dusterPose.y.toFixed(1)}) mm, theta={' '}
            {dusterPose.theta.toFixed(1)} deg
          </span>
        </div>
      </div>
    </div>
  );
};
