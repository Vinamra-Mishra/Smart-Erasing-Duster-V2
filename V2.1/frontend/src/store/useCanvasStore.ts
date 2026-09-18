import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';

export type CanvasTool = 'brush' | 'eraser' | 'occluder' | 'projector' | 'select';

export interface DrawnStroke {
  id: string;
  tool: CanvasTool;
  color: string;
  size: number;
  points: [number, number][]; // in FRAME_BOARD mm coordinates
}

export interface CanvasStoreState {
  activeTool: CanvasTool;
  brushSize: number;
  strokeColor: string;
  drawnStrokes: DrawnStroke[];
  showAxes: boolean;
  showBoundingBoxes: boolean;
  showTrajectories: boolean;
  showSweptFootprint: boolean;
  showDiffOverlay: boolean;
}

export interface CanvasStoreActions {
  setActiveTool: (tool: CanvasTool) => void;
  setBrushSize: (size: number) => void;
  setStrokeColor: (color: string) => void;
  addStroke: (stroke: DrawnStroke) => void;
  clearStrokes: () => void;
  toggleLayer: (
    layer:
      | 'showAxes'
      | 'showBoundingBoxes'
      | 'showTrajectories'
      | 'showSweptFootprint'
      | 'showDiffOverlay'
  ) => void;
}

export type CanvasStore = CanvasStoreState & CanvasStoreActions;

export const useCanvasStore = create<CanvasStore>()(
  subscribeWithSelector((set) => ({
    activeTool: 'brush',
    brushSize: 10,
    strokeColor: '#2563eb', // Clean blue marker
    drawnStrokes: [],
    showAxes: true,
    showBoundingBoxes: true,
    showTrajectories: true,
    showSweptFootprint: true,
    showDiffOverlay: false,

    setActiveTool: (activeTool) => set({ activeTool }),
    setBrushSize: (brushSize) => set({ brushSize }),
    setStrokeColor: (strokeColor) => set({ strokeColor }),
    addStroke: (stroke) =>
      set((state) => ({
        drawnStrokes: [...state.drawnStrokes, stroke],
      })),
    clearStrokes: () => set({ drawnStrokes: [] }),
    toggleLayer: (layer) =>
      set((state) => ({
        [layer]: !state[layer],
      })),
  }))
);
