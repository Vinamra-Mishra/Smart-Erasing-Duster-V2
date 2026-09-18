import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  CameraIcon,
  CheckCircleIcon,
  XCircleIcon,
  CropIcon,
  RefreshCwIcon,
  AlertTriangleIcon,
  SlidersIcon,
} from './icons';
import { api } from '../api/client';
import { CameraDevice } from '../types';
import { useConfigStore } from '../store/useConfigStore';

interface CalibrationModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const CalibrationModal: React.FC<CalibrationModalProps> = ({ isOpen, onClose }) => {
  const storeConfig = useConfigStore((state) => state.config);

  // Sensor resolution defaults to 1920x1080 standard (1080p)
  const [camWidth, setCamWidth] = useState(1920);
  const [camHeight, setCamHeight] = useState(1080);

  // Dynamic physical whiteboard dimensions (mm)
  const [boardWidth, setBoardWidth] = useState(storeConfig.board_width_mm || 1000);
  const [boardHeight, setBoardHeight] = useState(storeConfig.board_height_mm || 700);
  const [widthInput, setWidthInput] = useState(String(storeConfig.board_width_mm || 1000));
  const [heightInput, setHeightInput] = useState(String(storeConfig.board_height_mm || 700));

  // 4 ordered corners in FRAME_CAMERA: TL, TR, BR, BL
  const [corners, setCorners] = useState<[number, number][]>([
    [20, 20],
    [1900, 20],
    [1900, 1060],
    [20, 1060],
  ]);

  const [activeCornerIdx, setActiveCornerIdx] = useState<number | null>(null);
  const [devices, setDevices] = useState<CameraDevice[]>([]);
  const [currentSource, setCurrentSource] = useState<number | string>(1);
  const [isOpened, setIsOpened] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [reprojectionError, setReprojectionError] = useState<number | null>(null);
  const [streamKey, setStreamKey] = useState(Date.now());

  const svgRef = useRef<SVGSVGElement | null>(null);

  // Load status and available camera devices when opened
  const loadData = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const [devData, calData] = await Promise.all([
        api.getCameraDevices().catch(() => null),
        api.getCalibrationStatus().catch(() => null),
      ]);

      if (devData) {
        // Filter out index 0 (blocked webcam) so only virtual cameras (OBS) are shown
        const filteredDevices = (devData.devices || []).filter(
          (d: CameraDevice) => d.index !== 0 && String(d.index) !== '0'
        );
        setDevices(filteredDevices);
        const resolvedSource =
          devData.current_source === 0 || String(devData.current_source) === '0'
            ? 1
            : (devData.current_source ?? 1);
        setCurrentSource(resolvedSource);
        setIsOpened(Boolean(devData.is_opened));
        if (devData.sensor_width && devData.sensor_height) {
          setCamWidth(devData.sensor_width);
          setCamHeight(devData.sensor_height);
        } else if (filteredDevices.length > 0) {
          const curDev =
            filteredDevices.find((d: any) => d.index === resolvedSource) ||
            filteredDevices[0];
          if (curDev?.width && curDev?.height) {
            setCamWidth(curDev.width);
            setCamHeight(curDev.height);
          }
        }
      }

      if (calData) {
        const sw = calData.sensor_width || 1920;
        const sh = calData.sensor_height || 1080;
        if (calData.sensor_width && calData.sensor_height) {
          setCamWidth(sw);
          setCamHeight(sh);
        }
        if (calData.board_width_mm) {
          setBoardWidth(calData.board_width_mm);
          setWidthInput(String(calData.board_width_mm));
        }
        if (calData.board_height_mm) {
          setBoardHeight(calData.board_height_mm);
          setHeightInput(String(calData.board_height_mm));
        }
        if (calData.reprojection_error_px !== undefined) {
          setReprojectionError(calData.reprojection_error_px);
        }
        if (calData.corners) {
          setCorners([
            calData.corners.top_left,
            calData.corners.top_right,
            calData.corners.bottom_right,
            calData.corners.bottom_left,
          ]);
        } else {
          setCorners([
            [20, 20],
            [sw - 20, 20],
            [sw - 20, sh - 20],
            [20, sh - 20],
          ]);
        }
      }
    } catch {
      setErrorMessage('Failed loading camera devices or calibration parameters.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      loadData();
      setStreamKey(Date.now());
    }
  }, [isOpen, loadData]);

  // Handle camera device switch
  const handleSelectSource = async (src: number | string) => {
    const targetSource = src === 0 || String(src) === '0' ? 1 : src;
    setIsLoading(true);
    setStatusMessage(null);
    setErrorMessage(null);
    try {
      const res = await api.setCameraSource(targetSource);
      setCurrentSource(targetSource);
      setIsOpened(Boolean(res.is_opened));
      if (res.sensor_width && res.sensor_height) {
        setCamWidth(res.sensor_width);
        setCamHeight(res.sensor_height);
      }
      setStreamKey(Date.now());
      setStatusMessage(`Switched to Camera source ${targetSource}.`);
      await loadData();
    } catch {
      setErrorMessage('Failed switching camera source.');
    } finally {
      setIsLoading(false);
    }
  };

  // Auto detect OBS Virtual Camera
  const handleAutoFindOBS = async () => {
    setIsLoading(true);
    setStatusMessage(null);
    setErrorMessage(null);
    try {
      const res = await api.autoDetectCameraSource();
      if (res.success) {
        const detectedSource = res.source === 0 || String(res.source) === '0' ? 1 : res.source;
        setCurrentSource(detectedSource);
        setIsOpened(Boolean(res.is_opened));
        if (res.sensor_width && res.sensor_height) {
          setCamWidth(res.sensor_width);
          setCamHeight(res.sensor_height);
        }
        setStreamKey(Date.now());
        setStatusMessage(res.message || 'Connected to OBS Virtual Camera feed.');
        await loadData();
      } else {
        setErrorMessage(res.message || 'OBS Virtual Camera feed could not be identified automatically.');
      }
    } catch {
      setErrorMessage('Error querying OBS Virtual Camera.');
    } finally {
      setIsLoading(false);
    }
  };

  // Auto-Crop Whiteboard (calls /api/calibration/auto-detect)
  const handleAutoCrop = async () => {
    setIsLoading(true);
    setStatusMessage(null);
    setErrorMessage(null);
    try {
      const res = await api.autoDetectCorners();
      if (res.sensor_width && res.sensor_height) {
        setCamWidth(res.sensor_width);
        setCamHeight(res.sensor_height);
      }
      if (res.corners) {
        setCorners([
          res.corners.top_left,
          res.corners.top_right,
          res.corners.bottom_right,
          res.corners.bottom_left,
        ]);
      }
      setReprojectionError(res.reprojection_error_px ?? 0.0);
      setStatusMessage('Whiteboard perimeter automatically detected and cropped!');
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setErrorMessage(
        detail || 'Could not automatically detect whiteboard. Drag the 4 corner handles manually.'
      );
    } finally {
      setIsLoading(false);
    }
  };

  // Dynamically update physical whiteboard dimensions
  const handleApplyBoardSize = async () => {
    const w = parseFloat(widthInput);
    const h = parseFloat(heightInput);
    if (isNaN(w) || isNaN(h) || w < 100 || w > 10000 || h < 100 || h > 10000) {
      setErrorMessage('Board dimensions must be between 100 mm and 10000 mm.');
      return;
    }
    setIsLoading(true);
    setStatusMessage(null);
    setErrorMessage(null);
    try {
      const res = await api.setBoardSize(w, h);
      if (res.board_width_mm && res.board_height_mm) {
        setBoardWidth(res.board_width_mm);
        setBoardHeight(res.board_height_mm);
        setWidthInput(String(res.board_width_mm));
        setHeightInput(String(res.board_height_mm));
        useConfigStore.getState().updateConfig({
          board_width_mm: res.board_width_mm,
          board_height_mm: res.board_height_mm,
        });
      }
      if (res.sensor_width && res.sensor_height) {
        setCamWidth(res.sensor_width);
        setCamHeight(res.sensor_height);
      }
      if (res.reprojection_error_px !== undefined) {
        setReprojectionError(res.reprojection_error_px);
      }
      setStatusMessage(`Board physical dimensions updated to ${w}x${h} mm.`);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setErrorMessage(detail || 'Failed to update board dimensions.');
    } finally {
      setIsLoading(false);
    }
  };

  // Apply manual corner calibration
  const handleApplyCalibration = async () => {
    const w = parseFloat(widthInput) || boardWidth;
    const h = parseFloat(heightInput) || boardHeight;
    setIsLoading(true);
    setStatusMessage(null);
    setErrorMessage(null);
    try {
      const res = await api.setManualCorners(
        {
          top_left: corners[0],
          top_right: corners[1],
          bottom_right: corners[2],
          bottom_left: corners[3],
        },
        {
          board_width_mm: w,
          board_height_mm: h,
        }
      );
      if (res.board_width_mm && res.board_height_mm) {
        setBoardWidth(res.board_width_mm);
        setBoardHeight(res.board_height_mm);
        setWidthInput(String(res.board_width_mm));
        setHeightInput(String(res.board_height_mm));
        useConfigStore.getState().updateConfig({
          board_width_mm: res.board_width_mm,
          board_height_mm: res.board_height_mm,
        });
      }
      if (res.sensor_width && res.sensor_height) {
        setCamWidth(res.sensor_width);
        setCamHeight(res.sensor_height);
      }
      setReprojectionError(res.reprojection_error_px ?? 0.0);
      setStatusMessage('Whiteboard perspective homography applied successfully!');
      setTimeout(() => {
        onClose();
      }, 700);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setErrorMessage(detail || 'Failed to compute perspective transform from selected corners.');
    } finally {
      setIsLoading(false);
    }
  };

  // Reset calibration
  const handleResetCalibration = async () => {
    setIsLoading(true);
    setStatusMessage(null);
    setErrorMessage(null);
    try {
      const res = await api.resetCalibration();
      const sw = res.sensor_width || camWidth;
      const sh = res.sensor_height || camHeight;
      if (res.sensor_width && res.sensor_height) {
        setCamWidth(sw);
        setCamHeight(sh);
      }
      setCorners([
        [20, 20],
        [sw - 20, 20],
        [sw - 20, sh - 20],
        [20, sh - 20],
      ]);
      setReprojectionError(0.0);
      setStatusMessage('Calibration reset to default full frame.');
    } catch {
      setErrorMessage('Failed resetting calibration.');
    } finally {
      setIsLoading(false);
    }
  };

  // Pointer drag handling for SVG corner coordinates
  const handlePointerDown = (idx: number, e: React.PointerEvent) => {
    e.preventDefault();
    (e.target as Element).setPointerCapture(e.pointerId);
    setActiveCornerIdx(idx);
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (activeCornerIdx === null || !svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;

    const scaleX = camWidth / rect.width;
    const scaleY = camHeight / rect.height;

    const rawX = (e.clientX - rect.left) * scaleX;
    const rawY = (e.clientY - rect.top) * scaleY;

    const clampedX = Math.round(Math.max(0, Math.min(camWidth, rawX)));
    const clampedY = Math.round(Math.max(0, Math.min(camHeight, rawY)));

    setCorners((prev) => {
      const next = [...prev] as [number, number][];
      next[activeCornerIdx] = [clampedX, clampedY];
      return next;
    });
  };

  const handlePointerUp = () => {
    setActiveCornerIdx(null);
  };

  if (!isOpen) return null;

  const cornerLabels = ['TL (0)', 'TR (1)', 'BR (2)', 'BL (3)'];
  const polygonPointsStr = corners.map((p) => `${p[0]},${p[1]}`).join(' ');

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-xl max-w-4xl w-full p-4 space-y-3.5 shadow-2xl flex flex-col max-h-[92vh] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
          <div className="flex items-center space-x-2.5">
            <div className="w-8 h-8 rounded bg-cyan-950 border border-cyan-700/60 flex items-center justify-center text-cyan-400">
              <CropIcon className="w-4 h-4" />
            </div>
            <div>
              <h2 className="font-semibold text-sm text-slate-100 tracking-wide uppercase">
                Whiteboard Auto-Crop &amp; Perspective Calibration
              </h2>
              <p className="text-xs text-slate-400">
                Align 4 corners to crop whiteboard from OBS Virtual Camera or Webcam (FRAME_CAMERA to FRAME_BOARD)
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white p-1 rounded hover:bg-slate-800 transition"
            aria-label="Close Calibration Modal"
          >
            <XCircleIcon className="w-5 h-5" />
          </button>
        </div>

        {/* Toolbar: Camera Selection & Actions */}
        <div className="flex flex-wrap items-center justify-between gap-2 bg-slate-850 p-2.5 rounded-lg border border-slate-800 text-xs">
          {/* Camera Device Selector */}
          <div className="flex items-center space-x-2">
            <span className="text-slate-400 font-mono">Camera:</span>
            <select
              value={String(currentSource)}
              onChange={(e) => {
                const val = e.target.value;
                handleSelectSource(val.match(/^\d+$/) ? parseInt(val, 10) : val);
              }}
              disabled={isLoading}
              className="bg-slate-900 border border-slate-700 rounded px-2.5 py-1 text-slate-200 font-mono focus:outline-none focus:border-cyan-500 text-xs"
            >
              {devices.length > 0 ? (
                devices.map((d) => (
                  <option key={`cam-${d.index}`} value={String(d.index)}>
                    {d.name}{d.is_obs_candidate ? ' [OBS Candidate]' : ''} ({d.width}x{d.height})
                  </option>
                ))
              ) : (
                <>
                  <option value="1">Camera 1 (OBS Virtual Camera)</option>
                </>
              )}
            </select>

            {/* Auto-Find OBS Button */}
            <button
              onClick={handleAutoFindOBS}
              disabled={isLoading}
              className="flex items-center space-x-1.5 px-3 py-1 rounded bg-indigo-600/30 hover:bg-indigo-600/50 text-indigo-200 border border-indigo-500/40 font-mono transition"
              title="Automatically detect active OBS Virtual Camera feed"
            >
              <CameraIcon className="w-3.5 h-3.5" />
              <span>Find OBS Cam</span>
            </button>
          </div>

          {/* Crop Control Buttons */}
          <div className="flex items-center space-x-2 font-mono">
            {/* Auto-Crop Button */}
            <button
              onClick={handleAutoCrop}
              disabled={isLoading || !isOpened}
              className="flex items-center space-x-1.5 px-3 py-1 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-semibold transition shadow-sm disabled:opacity-50"
              title="Auto-detect whiteboard boundary using convex hull quadrilateral segmentation"
            >
              <CropIcon className="w-3.5 h-3.5" />
              <span>Auto-Crop Whiteboard</span>
            </button>

            {/* Reset Crop Button */}
            <button
              onClick={handleResetCalibration}
              disabled={isLoading}
              className="flex items-center space-x-1 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-750 text-slate-300 border border-slate-700 transition"
              title="Reset corners to full camera image"
            >
              <RefreshCwIcon className="w-3 h-3 text-slate-400" />
              <span>Reset</span>
            </button>
          </div>
        </div>

        {/* Dynamic Board Dimensions Bar */}
        <div className="flex flex-wrap items-center justify-between gap-2.5 bg-slate-850 p-2.5 rounded-lg border border-slate-800 text-xs font-mono">
          <div className="flex items-center space-x-2.5">
            <span className="text-slate-400 flex items-center space-x-1.5">
              <SlidersIcon className="w-3.5 h-3.5 text-cyan-400" />
              <span>Board Dimensions:</span>
            </span>
            <div className="flex items-center space-x-1">
              <label htmlFor="board-width-input" className="text-slate-400 text-[11px]">Width (mm):</label>
              <input
                id="board-width-input"
                type="number"
                min="100"
                max="10000"
                step="10"
                value={widthInput}
                onChange={(e) => {
                  setWidthInput(e.target.value);
                  const val = parseFloat(e.target.value);
                  if (!isNaN(val) && val >= 100 && val <= 10000) {
                    setBoardWidth(val);
                  }
                }}
                onBlur={() => {
                  const val = parseFloat(widthInput);
                  if (isNaN(val) || val < 100) {
                    setWidthInput('100');
                    setBoardWidth(100);
                  } else if (val > 10000) {
                    setWidthInput('10000');
                    setBoardWidth(10000);
                  } else {
                    setBoardWidth(val);
                  }
                }}
                disabled={isLoading}
                className="w-20 bg-slate-900 border border-slate-700 rounded px-2 py-0.5 text-cyan-300 font-mono text-xs focus:outline-none focus:border-cyan-500"
              />
            </div>
            <div className="flex items-center space-x-1">
              <label htmlFor="board-height-input" className="text-slate-400 text-[11px]">Height (mm):</label>
              <input
                id="board-height-input"
                type="number"
                min="100"
                max="10000"
                step="10"
                value={heightInput}
                onChange={(e) => {
                  setHeightInput(e.target.value);
                  const val = parseFloat(e.target.value);
                  if (!isNaN(val) && val >= 100 && val <= 10000) {
                    setBoardHeight(val);
                  }
                }}
                onBlur={() => {
                  const val = parseFloat(heightInput);
                  if (isNaN(val) || val < 100) {
                    setHeightInput('100');
                    setBoardHeight(100);
                  } else if (val > 10000) {
                    setHeightInput('10000');
                    setBoardHeight(10000);
                  } else {
                    setBoardHeight(val);
                  }
                }}
                disabled={isLoading}
                className="w-20 bg-slate-900 border border-slate-700 rounded px-2 py-0.5 text-cyan-300 font-mono text-xs focus:outline-none focus:border-cyan-500"
              />
            </div>
            <button
              onClick={handleApplyBoardSize}
              disabled={isLoading}
              className="flex items-center space-x-1 px-2.5 py-0.5 rounded bg-slate-800 hover:bg-slate-750 text-cyan-300 border border-cyan-700/50 transition disabled:opacity-50"
              title="Apply dynamic whiteboard physical dimensions"
            >
              <span>Set Dimensions</span>
            </button>
          </div>
          <div className="text-[11px] text-slate-400">
            Dock: <span className="text-slate-200">({(storeConfig.duster_width_mm / 2.0).toFixed(1)}, {(boardHeight - storeConfig.duster_height_mm / 2.0).toFixed(1)}) mm</span>
          </div>
        </div>

        {/* Feedback Notifications */}
        {statusMessage && (
          <div className="px-3 py-1.5 rounded bg-emerald-950/70 border border-emerald-800/80 text-emerald-300 text-xs flex items-center space-x-2">
            <CheckCircleIcon className="w-4 h-4 text-emerald-400 flex-shrink-0" />
            <span>{statusMessage}</span>
          </div>
        )}

        {errorMessage && (
          <div className="px-3 py-1.5 rounded bg-rose-950/70 border border-rose-800/80 text-rose-300 text-xs flex items-center space-x-2">
            <AlertTriangleIcon className="w-4 h-4 text-rose-400 flex-shrink-0" />
            <span>{errorMessage}</span>
          </div>
        )}

        {/* Interactive Viewport Container */}
        <div className="relative flex-1 min-h-[320px] max-h-[500px] bg-slate-950 rounded-lg border border-slate-800 overflow-hidden flex items-center justify-center select-none">
          {/* Live Un-warped Camera MJPEG Feed */}
          <img
            src={`/api/camera/raw-stream?t=${streamKey}`}
            alt="Raw Camera Feed"
            className="w-full h-full object-contain pointer-events-none"

            onLoad={(e) => {
              const target = e.target as HTMLImageElement;
              if (target.naturalWidth > 0 && target.naturalHeight > 0) {
                if (target.naturalWidth !== camWidth || target.naturalHeight !== camHeight) {
                  const oldW = camWidth;
                  const oldH = camHeight;
                  const newW = target.naturalWidth;
                  const newH = target.naturalHeight;
                  setCamWidth(newW);
                  setCamHeight(newH);
                  setCorners((prev) => {
                    const isDefault = prev[1][0] === oldW - 20 && prev[2][1] === oldH - 20;
                    if (isDefault) {
                      return [
                        [20, 20],
                        [newW - 20, 20],
                        [newW - 20, newH - 20],
                        [20, newH - 20],
                      ];
                    }
                    const sx = newW / oldW;
                    const sy = newH / oldH;
                    return prev.map(([x, y]) => [
                      Math.round(Math.max(0, Math.min(newW, x * sx))),
                      Math.round(Math.max(0, Math.min(newH, y * sy))),
                    ]) as [number, number][];
                  });
                }
              }
            }}
            onError={(e) => {
              // Fallback placeholder if stream fails
              (e.target as HTMLElement).style.display = 'none';
            }}
          />

          {/* Interactive SVG Overlay */}
          <svg
            ref={svgRef}
            viewBox={`0 0 ${camWidth} ${camHeight}`}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            className="absolute inset-0 w-full h-full cursor-crosshair touch-none"
          >
            {/* Semi-transparent crop quadrilateral mask */}
            <polygon
              points={polygonPointsStr}
              fill="rgba(6, 182, 212, 0.16)"
              stroke="#06b6d4"
              strokeWidth="2"
              strokeDasharray="6 3"
            />

            {/* Corner diagonal guides */}
            <line
              x1={corners[0][0]}
              y1={corners[0][1]}
              x2={corners[2][0]}
              y2={corners[2][1]}
              stroke="#06b6d4"
              strokeWidth="0.8"
              strokeDasharray="4 4"
              opacity="0.3"
            />
            <line
              x1={corners[1][0]}
              y1={corners[1][1]}
              x2={corners[3][0]}
              y2={corners[3][1]}
              stroke="#06b6d4"
              strokeWidth="0.8"
              strokeDasharray="4 4"
              opacity="0.3"
            />

            {/* Draggable Corner Handles */}
            {corners.map(([x, y], idx) => {
              const isActive = activeCornerIdx === idx;
              return (
                <g
                  key={`handle-${idx}`}
                  onPointerDown={(e) => handlePointerDown(idx, e)}
                  className="cursor-grab active:cursor-grabbing pointer-events-auto"
                >
                  {/* Outer glow ring */}
                  <circle
                    cx={x}
                    cy={y}
                    r={isActive ? '22' : '16'}
                    fill={isActive ? 'rgba(56, 189, 248, 0.35)' : 'rgba(14, 116, 144, 0.25)'}
                    className="transition-all"
                  />
                  {/* Solid Handle Circle */}
                  <circle
                    cx={x}
                    cy={y}
                    r="10"
                    fill={isActive ? '#38bdf8' : '#0284c7'}
                    stroke="#ffffff"
                    strokeWidth="2"
                  />
                  {/* Corner Name Label */}
                  <text
                    x={x}
                    y={y - 14}
                    textAnchor="middle"
                    fill="#38bdf8"
                    fontSize="11"
                    fontFamily="monospace"
                    fontWeight="bold"
                    filter="drop-shadow(0px 1px 2px rgba(0,0,0,0.9))"
                  >
                    {cornerLabels[idx]} ({x}, {y})
                  </text>
                </g>
              );
            })}
          </svg>
        </div>

        {/* Footer Info & Final Actions */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-800 font-mono text-xs">
          <div className="flex items-center space-x-3 text-slate-400">
            <span>
              Sensor: <strong className="text-slate-200">{camWidth}x{camHeight} px</strong>
            </span>
            <span className="text-slate-600">|</span>
            <span>
              Board: <strong className="text-cyan-400">{boardWidth}x{boardHeight} mm</strong> (1.0 px = 1.0 mm)
            </span>
            {reprojectionError !== null && (
              <>
                <span className="text-slate-600">|</span>
                <span className="text-emerald-400">
                  Reprojection Error: <strong>{reprojectionError.toFixed(2)} mm</strong>
                </span>
              </>
            )}
          </div>

          <div className="flex items-center space-x-2">
            <button
              onClick={onClose}
              className="px-4 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 transition"
            >
              Cancel
            </button>
            <button
              onClick={handleApplyCalibration}
              disabled={isLoading}
              className="flex items-center space-x-1.5 px-4 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-semibold transition shadow-md disabled:opacity-50"
            >
              <CheckCircleIcon className="w-4 h-4" />
              <span>Apply Crop (Save)</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
