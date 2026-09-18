import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';
import { InkObject, BaselineEpoch, ReconcilerEvent } from '../types';

export interface TwinState {
  inkObjects: Record<string, InkObject>;
  selectedObjectId: string | null;
  boardOccluded: boolean;
  uncertaintyActive: boolean;
  baselineEpoch: BaselineEpoch;
  reconcilerEvents: ReconcilerEvent[];
}

export interface TwinActions {
  setTwinDelta: (
    objects: Record<string, InkObject>,
    occluded?: boolean,
    uncertain?: boolean
  ) => void;
  updateInkObject: (id: string, partial: Partial<InkObject>) => void;
  selectObject: (id: string | null) => void;
  setBaselineEpoch: (epoch: BaselineEpoch) => void;
  addReconcilerEvent: (event: ReconcilerEvent) => void;
  clearTwin: () => void;
}

export type TwinStore = TwinState & TwinActions;

const INITIAL_EPOCH: BaselineEpoch = {
  epoch_id: 0,
  timestamp: '',
  edge_density: 0.0,
  is_valid: false,
  is_dirty_alert: false,
  defect_count: 0,
};


export const useTwinStore = create<TwinStore>()(
  subscribeWithSelector((set) => ({
    inkObjects: {},
    selectedObjectId: null,
    boardOccluded: false,
    uncertaintyActive: false,
    baselineEpoch: INITIAL_EPOCH,
    reconcilerEvents: [],

    setTwinDelta: (objects, occluded, uncertain) =>
      set((state) => ({
        inkObjects: objects,
        boardOccluded: occluded !== undefined ? occluded : state.boardOccluded,
        uncertaintyActive:
          uncertain !== undefined ? uncertain : state.uncertaintyActive,
      })),

    updateInkObject: (id, partial) =>
      set((state) => {
        const existing = state.inkObjects[id];
        if (!existing) return state;
        return {
          inkObjects: {
            ...state.inkObjects,
            [id]: { ...existing, ...partial },
          },
        };
      }),

    selectObject: (id) => set({ selectedObjectId: id }),

    setBaselineEpoch: (epoch) => set({ baselineEpoch: epoch }),

    addReconcilerEvent: (event) =>
      set((state) => ({
        reconcilerEvents: [event, ...state.reconcilerEvents].slice(0, 50),
      })),

    clearTwin: () =>
      set({
        inkObjects: {},
        selectedObjectId: null,
        boardOccluded: false,
        uncertaintyActive: false,
      }),
  }))
);
