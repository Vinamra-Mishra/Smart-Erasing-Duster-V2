import { useRef, useCallback, useState } from 'react';
import { useCanvasStore, DrawnStroke } from '../store/useCanvasStore';
import { useTwinStore } from '../store/useTwinStore';
import { useConfigStore } from '../store/useConfigStore';
import { api } from '../api/client';
import { InkObject } from '../types';

export function useCanvas() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const currentPointsRef = useRef<[number, number][]>([]);

  const activeTool = useCanvasStore((state) => state.activeTool);
  const brushSize = useCanvasStore((state) => state.brushSize);
  const strokeColor = useCanvasStore((state) => state.strokeColor);
  const addStroke = useCanvasStore((state) => state.addStroke);

  const boardWidth = useConfigStore((state) => state.config.board_width_mm);
  const boardHeight = useConfigStore((state) => state.config.board_height_mm);

  const setTwinDelta = useTwinStore((state) => state.setTwinDelta);
  const inkObjects = useTwinStore((state) => state.inkObjects);

  // Convert client viewport coordinates to FRAME_BOARD coordinates (mm)
  const clientToBoard = useCallback(
    (clientX: number, clientY: number): [number, number] | null => {
      if (!containerRef.current) return null;
      const rect = containerRef.current.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return null;

      const px = clientX - rect.left;
      const py = clientY - rect.top;

      // Board scale
      const bx = Math.max(0, Math.min(boardWidth, (px / rect.width) * boardWidth));
      const by = Math.max(0, Math.min(boardHeight, (py / rect.height) * boardHeight));

      return [Math.round(bx * 10) / 10, Math.round(by * 10) / 10];
    },
    [boardWidth, boardHeight]
  );

  const handlePointerDown = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (activeTool === 'select') return;
      const pt = clientToBoard(e.clientX, e.clientY);
      if (!pt) return;

      setIsDrawing(true);
      currentPointsRef.current = [pt];
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
    },
    [activeTool, clientToBoard]
  );

  const handlePointerMove = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (!isDrawing) return;
      const pt = clientToBoard(e.clientX, e.clientY);
      if (!pt) return;

      const last = currentPointsRef.current[currentPointsRef.current.length - 1];
      if (!last || Math.hypot(pt[0] - last[0], pt[1] - last[1]) > 3.0) {
        currentPointsRef.current.push(pt);
      }
    },
    [isDrawing, clientToBoard]
  );

  const handlePointerUp = useCallback(
    async (e: React.PointerEvent<HTMLDivElement>) => {
      if (!isDrawing) return;
      setIsDrawing(false);
      try {
        (e.target as HTMLElement).releasePointerCapture(e.pointerId);
      } catch {
        // Ignore if pointer capture already released
      }

      const pts = currentPointsRef.current;
      if (pts.length < 2) {
        currentPointsRef.current = [];
        return;
      }

      const strokeId = `stroke_${Date.now()}`;
      const newStroke: DrawnStroke = {
        id: strokeId,
        tool: activeTool,
        color: activeTool === 'occluder' ? '#f59e0b' : strokeColor,
        size: brushSize,
        points: [...pts],
      };

      addStroke(newStroke);

      if (activeTool === 'brush') {
        // Optimistically create an InkObject in the twin store
        const xs = pts.map((p) => p[0]);
        const ys = pts.map((p) => p[1]);
        const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
        const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
        const areaApprox = pts.length * brushSize * 4;

        const optimisticInk: InkObject = {
          id: strokeId,
          frame: 'FRAME_BOARD',
          geometry: pts,
          centroid: [cx, cy],
          area_mm2: areaApprox,
          state: 'NEW_INK',
          reclean_attempts: 0,
          confidence: 0.95,
          last_seen_frame: 1,
          is_defect: false,
          stroke_color: strokeColor,
        };

        setTwinDelta({ ...inkObjects, [strokeId]: optimisticInk });

        // Post to backend simulator
        try {
          await api.postDrawStroke({
            tool: activeTool,
            points: pts,
            color: strokeColor,
            size: brushSize,
          });
        } catch {
          // Backend offline - optimistic simulation state remains valid
        }
      } else if (activeTool === 'occluder') {
        // Trigger temporary occlusion
        setTwinDelta(inkObjects, true, false);
      }

      currentPointsRef.current = [];
    },
    [
      activeTool,
      addStroke,
      brushSize,
      inkObjects,
      isDrawing,
      setTwinDelta,
      strokeColor,
    ]
  );

  return {
    containerRef,
    isDrawing,
    handlePointerDown,
    handlePointerMove,
    handlePointerUp,
  };
}
