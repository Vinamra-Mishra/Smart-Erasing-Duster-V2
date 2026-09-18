'use client';

import React, { useState } from 'react';
import {
  BrushIcon,
  EraserIcon,
  HandIcon,
  Trash2Icon,
  LayersIcon,
  TargetIcon,
} from './icons';
import { useTwinStore } from '../store/useTwinStore';
import { useExecutionStore } from '../store/useExecutionStore';
import { useCanvasStore } from '../store/useCanvasStore';
import { useConfigStore } from '../store/useConfigStore';
import { useCanvas } from '../hooks/useCanvas';
import { api } from '../api/client';
import { PhysicalTwinState } from '../types';

export const VirtualBoardCanvas: React.FC = () => {
  const {
    containerRef,
    handlePointerDown,
    handlePointerMove,
    handlePointerUp,
  } = useCanvas();

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
  const toggleLayer = useCanvasStore((state) => state.toggleLayer);

  const config = useConfigStore((state) => state.config);
  const boardWidth = config.board_width_mm || 1919;
  const boardHeight = config.board_height_mm || 993;
  const dusterWidth = config.duster_width_mm || 162;
  const dusterHeight = config.duster_height_mm || 58;
  const homeDock = useConfigStore((state) => state.homeDock);

  const handleClearBoard = async () => {
    clearStrokes();
    useTwinStore.getState().clearTwin();
    try {
      await api.clearBoard();
    } catch {
      // Handled
    }
  };

  const getObjectColor = (state: PhysicalTwinState): string => {
    switch (state) {
      case 'NEW_INK':
        return '#06b6d4'; // Cyan
      case 'STABLE_INK':
        return '#38bdf8'; // Sky blue
      case 'PARTIALLY_CLEANED':
        return '#f59e0b'; // Amber
      case 'CLEANED':
        return '#10b981'; // Emerald
      case 'PERMANENT_DEFECT':
        return '#f43f5e'; // Rose
      case 'OCCLUDED':
        return '#eab308'; // Yellow
      case 'UNKNOWN':
      default:
        return '#a855f7'; // Purple
    }
  };

  return (
    <div className="flex flex-col h-full bg-slate-900 border border-slate-800 rounded-lg overflow-hidden shadow-lg">
      {/* Top Toolbar */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-slate-950 border-b border-slate-800 text-xs select-none">
        {/* Left: Tools */}
        <div className="flex items-center space-x-1">
          <div className="flex items-center space-x-1.5 mr-2">
            <span className="font-semibold text-cyan-400 font-mono tracking-wider uppercase text-[11px]">
              Virtual Digital Board
            </span>
            <span className="text-[10px] text-slate-400 font-mono">
              ({Math.round(boardWidth)}x{Math.round(boardHeight)} mm)
            </span>
          </div>

          <button
            onClick={() => setActiveTool('select')}
            className={`p-1.5 rounded transition ${
              activeTool === 'select'
                ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/50'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
            title="Select & Inspect Ink Objects"
          >
            <TargetIcon className="w-3.5 h-3.5" />
          </button>

          <button
            onClick={() => setActiveTool('brush')}
            className={`p-1.5 rounded transition ${
              activeTool === 'brush'
                ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/50'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
            title="Marker Brush (Draw Ink)"
          >
            <BrushIcon className="w-3.5 h-3.5" />
          </button>

          <button
            onClick={() => setActiveTool('eraser')}
            className={`p-1.5 rounded transition ${
              activeTool === 'eraser'
                ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/50'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
            title="Manual Eraser"
          >
            <EraserIcon className="w-3.5 h-3.5" />
          </button>

          <button
            onClick={() => setActiveTool('occluder')}
            className={`p-1.5 rounded transition ${
              activeTool === 'occluder'
                ? 'bg-amber-500/20 text-amber-400 border border-amber-500/50'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
            title="Simulate Hand / Arm Occlusion"
          >
            <HandIcon className="w-3.5 h-3.5" />
          </button>

          {/* Marker Colors */}
          {activeTool === 'brush' && (
            <div className="flex items-center space-x-1 ml-1 pl-1 border-l border-slate-800">
              {['#2563eb', '#dc2626', '#16a34a', '#0f172a'].map((color) => (
                <button
                  key={color}
                  onClick={() => setStrokeColor(color)}
                  style={{ backgroundColor: color }}
                  className={`w-3.5 h-3.5 rounded-full border transition ${
                    strokeColor === color
                      ? 'border-white scale-110 shadow-sm'
                      : 'border-slate-700 hover:scale-105'
                  }`}
                  title={`Color ${color}`}
                />
              ))}
            </div>
          )}

          {/* Brush Size Slider */}
          <div className="flex items-center space-x-1 ml-1 pl-1 border-l border-slate-800 text-[10px]">
            <span className="text-slate-500">Size:</span>
            <input
              type="range"
              min="4"
              max="24"
              value={brushSize}
              onChange={(e) => setBrushSize(Number(e.target.value))}
              className="w-12 h-1 bg-slate-800 rounded appearance-none cursor-pointer accent-cyan-400"
            />
            <span className="font-mono text-slate-400">{brushSize}mm</span>
          </div>
        </div>

        {/* Right: Layers & Clear */}
        <div className="flex items-center space-x-1.5 relative">
          <button
            onClick={() => setShowLayerMenu(!showLayerMenu)}
            className="flex items-center space-x-1 px-2 py-0.5 bg-slate-850 hover:bg-slate-800 text-slate-300 rounded border border-slate-700 text-[11px] transition"
            title="Toggle Canvas Overlay Layers"
          >
            <LayersIcon className="w-3 h-3 text-cyan-400" />
            <span>Layers</span>
          </button>

          {showLayerMenu && (
            <div className="absolute right-10 top-7 z-30 bg-slate-900 border border-slate-700 rounded-lg p-2.5 shadow-xl w-44 space-y-1.5 text-[11px]">
              <label className="flex items-center justify-between text-slate-300 hover:text-white cursor-pointer">
                <span>Coordinate Axes</span>
                <input
                  type="checkbox"
                  checked={showAxes}
                  onChange={() => toggleLayer('showAxes')}
                  className="rounded border-slate-700 text-cyan-500"
                />
              </label>
              <label className="flex items-center justify-between text-slate-300 hover:text-white cursor-pointer">
                <span>Target Bounds</span>
                <input
                  type="checkbox"
                  checked={showBoundingBoxes}
                  onChange={() => toggleLayer('showBoundingBoxes')}
                  className="rounded border-slate-700 text-cyan-500"
                />
              </label>
              <label className="flex items-center justify-between text-slate-300 hover:text-white cursor-pointer">
                <span>Planned Trajectory</span>
                <input
                  type="checkbox"
                  checked={showTrajectories}
                  onChange={() => toggleLayer('showTrajectories')}
                  className="rounded border-slate-700 text-cyan-500"
                />
              </label>
            </div>
          )}

          <button
            onClick={handleClearBoard}
            className="flex items-center space-x-1 px-2 py-0.5 bg-rose-950/40 hover:bg-rose-900/60 text-rose-300 rounded border border-rose-800 text-[11px] transition"
            title="Clear all ink strokes"
          >
            <Trash2Icon className="w-3 h-3" />
            <span>Clear</span>
          </button>
        </div>
      </div>

      {/* Canvas Viewport */}
      <div
        ref={containerRef}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        className="relative flex-1 w-full overflow-hidden bg-slate-950 flex items-center justify-center cursor-crosshair touch-none select-none"
      >
        <div
          className="relative w-full h-full flex items-center justify-center"
          style={{ aspectRatio: `${boardWidth} / ${boardHeight}` }}
        >
          {/* SVG Digital Twin Board Surface */}
          <svg
            viewBox={`0 0 ${boardWidth} ${boardHeight}`}
            className="absolute inset-0 w-full h-full"
            style={{ shapeRendering: 'geometricPrecision' }}
          >
            <defs>
              {/* Subtle Grid Pattern */}
              <pattern
                id="digital-twin-grid"
                width="100"
                height="100"
                patternUnits="userSpaceOnUse"
              >
                <path
                  d="M 100 0 L 0 0 0 100"
                  fill="none"
                  stroke="#1e293b"
                  strokeWidth="0.8"
                  strokeDasharray="2,4"
                />
              </pattern>

              {/* Duster Contact Glow Filter */}
              <filter id="duster-glow" x="-20%" y="-20%" width="140%" height="140%">
                <feGaussianBlur stdDeviation="6" result="blur" />
                <feComposite in="SourceGraphic" in2="blur" operator="over" />
              </filter>
            </defs>

            {/* Background Grid Surface */}
            <rect
              x="0"
              y="0"
              width={boardWidth}
              height={boardHeight}
              fill="#030712"
            />
            <rect
              x="0"
              y="0"
              width={boardWidth}
              height={boardHeight}
              fill="url(#digital-twin-grid)"
            />

            {/* Coordinate Axes & Ruler */}
            {showAxes && (
              <g id="coordinate-axes" opacity="0.6">
                <line
                  x1="0"
                  y1="0"
                  x2={boardWidth}
                  y2="0"
                  stroke="#06b6d4"
                  strokeWidth="2"
                />
                <line
                  x1="0"
                  y1="0"
                  x2="0"
                  y2={boardHeight}
                  stroke="#06b6d4"
                  strokeWidth="2"
                />
                {/* Ticks along X */}
                {Array.from({ length: Math.floor(boardWidth / 200) + 1 }).map((_, i) => (
                  <g key={`xtick-${i}`} transform={`translate(${i * 200}, 0)`}>
                    <line x1="0" y1="0" x2="0" y2="10" stroke="#06b6d4" strokeWidth="1.5" />
                    <text
                      x="4"
                      y="16"
                      fill="#06b6d4"
                      fontSize="10"
                      fontFamily="monospace"
                    >
                      {i * 200}
                    </text>
                  </g>
                ))}
                {/* Ticks along Y */}
                {Array.from({ length: Math.floor(boardHeight / 200) + 1 }).map((_, i) => (
                  <g key={`ytick-${i}`} transform={`translate(0, ${i * 200})`}>
                    <line x1="0" y1="0" x2="10" y2="0" stroke="#06b6d4" strokeWidth="1.5" />
                    <text
                      x="12"
                      y="12"
                      fill="#06b6d4"
                      fontSize="10"
                      fontFamily="monospace"
                    >
                      {i * 200}
                    </text>
                  </g>
                ))}
                <text
                  x="10"
                  y="26"
                  fill="#06b6d4"
                  fontSize="11"
                  fontFamily="monospace"
                  fontWeight="bold"
                >
                  FRAME_BOARD (mm) [0,0]
                </text>
              </g>
            )}

            {/* Home Dock Parking Indicator */}
            <g
              id="home-dock"
              transform={`translate(${homeDock.x}, ${homeDock.y}) rotate(${homeDock.theta})`}
              opacity="0.75"
            >
              <rect
                x={-dusterWidth / 2}
                y={-dusterHeight / 2}
                width={dusterWidth}
                height={dusterHeight}
                fill="none"
                stroke="#10b981"
                strokeWidth="1.5"
                strokeDasharray="4,4"
                rx="4"
              />
              <text
                x="0"
                y="3"
                textAnchor="middle"
                fill="#10b981"
                fontSize="9"
                fontFamily="monospace"
                fontWeight="bold"
              >
                HOME DOCK
              </text>
            </g>

            {/* Drawn Local Strokes */}
            {drawnStrokes.map((stroke) => {
              if (stroke.points.length < 2) return null;
              const d = stroke.points.reduce((acc, pt, idx) => {
                return idx === 0 ? `M ${pt[0]} ${pt[1]}` : `${acc} L ${pt[0]} ${pt[1]}`;
              }, '');
              return (
                <path
                  key={stroke.id}
                  d={d}
                  fill="none"
                  stroke={stroke.color}
                  strokeWidth={stroke.size}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  opacity={stroke.tool === 'occluder' ? 0.7 : 0.95}
                />
              );
            })}

            {/* Authoritative Physical Twin Ink Objects */}
            {Object.values(inkObjects).map((obj) => {
              const isSelected = selectedObjectId === obj.id;
              const col = getObjectColor(obj.state);

              // Render geometry contour if available (supporting inner holes for hollow loops)
              const pts = obj.geometry;
              let pathD = '';
              if (pts && pts.length >= 2) {
                pathD = `M ${pts[0][0]} ${pts[0][1]} ` + pts.slice(1).map((p) => `L ${p[0]} ${p[1]}`).join(' ') + ' Z';
                if (obj.holes && obj.holes.length > 0) {
                  for (const hole of obj.holes) {
                    if (hole.length >= 2) {
                      pathD += ` M ${hole[0][0]} ${hole[0][1]} ` + hole.slice(1).map((p) => `L ${p[0]} ${p[1]}`).join(' ') + ' Z';
                    }
                  }
                }
              }

              return (
                <g
                  key={obj.id}
                  onClick={(e) => {
                    e.stopPropagation();
                    selectObject(obj.id);
                  }}
                  className="cursor-pointer"
                >
                  {/* SVG Path with hole cutout support via evenodd */}
                  {pathD && (
                    <path
                      d={pathD}
                      fill={col}
                      fillOpacity={obj.state === 'OCCLUDED' ? 0.2 : 0.4}
                      fillRule="evenodd"
                      stroke={col}
                      strokeWidth={isSelected ? 2.5 : 1.5}
                      strokeLinejoin="round"
                      strokeLinecap="round"
                      strokeDasharray={obj.state === 'OCCLUDED' ? '4,4' : undefined}
                    />
                  )}

                  {/* Bounding Box Overlay */}
                  {showBoundingBoxes && obj.centroid && (
                    <circle
                      cx={obj.centroid[0]}
                      cy={obj.centroid[1]}
                      r="4"
                      fill={col}
                      stroke="#0f172a"
                      strokeWidth="1"
                    />
                  )}

                  {/* Label badge */}
                  {isSelected && obj.centroid && (
                    <g transform={`translate(${obj.centroid[0]}, ${obj.centroid[1] - 12})`}>
                      <rect
                        x="-30"
                        y="-12"
                        width="60"
                        height="14"
                        fill="#020617"
                        stroke={col}
                        strokeWidth="1"
                        rx="2"
                      />
                      <text
                        x="0"
                        y="-2"
                        textAnchor="middle"
                        fill={col}
                        fontSize="9"
                        fontFamily="monospace"
                        fontWeight="bold"
                      >
                        {obj.state}
                      </text>
                    </g>
                  )}
                </g>
              );
            })}

            {/* Planned Trajectory Waypoints & Sweep Path */}
            {showTrajectories && currentTrajectory && currentTrajectory.waypoints.length > 0 && (
              <g id="planned-trajectory">
                {/* Continuous Trajectory Path */}
                {(() => {
                  const wps = currentTrajectory.waypoints;
                  let pathD = `M ${wps[0].x} ${wps[0].y}`;
                  for (let i = 1; i < wps.length; i++) {
                    pathD += ` L ${wps[i].x} ${wps[i].y}`;
                  }
                  return (
                    <path
                      d={pathD}
                      fill="none"
                      stroke="#06b6d4"
                      strokeWidth="1.5"
                      strokeDasharray="4,4"
                      opacity="0.8"
                    />
                  );
                })()}

                {/* Waypoint Nodes */}
                {currentTrajectory.waypoints.map((wp, idx) => {
                  const isCurrent = idx === currentWaypointIndex;
                  const isSweep = wp.segment_type === 'sweep';
                  return (
                    <circle
                      key={`wp-${idx}`}
                      cx={wp.x}
                      cy={wp.y}
                      r={isCurrent ? '4.5' : isSweep ? '2.5' : '2'}
                      fill={isCurrent ? '#38bdf8' : isSweep ? '#06b6d4' : '#64748b'}
                      stroke="#020617"
                      strokeWidth="1"
                    />
                  );
                })}
              </g>
            )}

            {/* Real-Time Actuator Duster Footprint */}
            <g
              id="actuator-duster"
              transform={`translate(${dusterPose.x}, ${dusterPose.y}) rotate(${dusterPose.theta})`}
              filter={dusterPose.is_contacting ? 'url(#duster-glow)' : undefined}
              style={{
                transition: executionState === 'CLEANING_ACTIVE' ? 'transform 40ms linear' : 'none',
                willChange: 'transform',
              }}
            >
              {/* Outer Housing */}
              <rect
                x={-dusterWidth / 2}
                y={-dusterHeight / 2}
                width={dusterWidth}
                height={dusterHeight}
                fill={dusterPose.is_contacting ? '#0891b2' : '#1e293b'}
                fillOpacity={dusterPose.is_contacting ? '0.6' : '0.85'}
                stroke={dusterPose.is_contacting ? '#22d3ee' : '#64748b'}
                strokeWidth={dusterPose.is_contacting ? '2.5' : '1.5'}
                rx="4"
              />

              {/* Center Coordinate Mark */}
              <circle cx="0" cy="0" r="3" fill="#ffffff" />
              {/* Heading Indicator Arrow */}
              <line
                x1="0"
                y1="0"
                x2={dusterWidth / 2 + 10}
                y2="0"
                stroke="#22d3ee"
                strokeWidth="2"
              />
              <polygon
                points={`${dusterWidth / 2 + 16},0 ${dusterWidth / 2 + 10},-4 ${dusterWidth / 2 + 10},4`}
                fill="#22d3ee"
              />

              {/* Status Text on Duster */}
              <text
                x="0"
                y="3"
                textAnchor="middle"
                fill="#ffffff"
                fontSize="8"
                fontFamily="monospace"
                fontWeight="bold"
              >
                {dusterPose.is_contacting ? 'WIPING' : 'TRANSIT'}
              </text>
            </g>

            {/* Board Occlusion Mask Indicator */}
            {boardOccluded && (
              <g id="occlusion-alert">
                <rect
                  x="0"
                  y="0"
                  width={boardWidth}
                  height={boardHeight}
                  fill="#f59e0b"
                  fillOpacity="0.1"
                  stroke="#f59e0b"
                  strokeWidth="2"
                  strokeDasharray="6,6"
                />
                <text
                  x={boardWidth / 2}
                  y="30"
                  textAnchor="middle"
                  fill="#f59e0b"
                  fontSize="14"
                  fontFamily="monospace"
                  fontWeight="bold"
                >
                  TEMPORAL OCCLUSION ACTIVE (PRESERVING TWIN INK)
                </text>
              </g>
            )}
          </svg>
        </div>
      </div>
    </div>
  );
};
export default VirtualBoardCanvas;
