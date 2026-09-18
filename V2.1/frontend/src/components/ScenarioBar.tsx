import React, { useState } from 'react';
import {
  SparklesIcon,
  BrushIcon,
  SunIcon,
  HandIcon,
  ShieldAlertIcon,
  ProjectorIcon,
} from './icons';
import { useExecutionStore } from '../store/useExecutionStore';
import { useTwinStore } from '../store/useTwinStore';
import { usePerceptionStore } from '../store/usePerceptionStore';
import { api } from '../api/client';
import { InkObject, ScenarioDefinition } from '../types';

export const SCENARIOS: ScenarioDefinition[] = [
  {
    id: 1,
    title: 'Baseline Capture',
    subtitle: 'Empty Board',
    description: 'Clean surface calibration with edge density < 0.04 check.',
  },
  {
    id: 2,
    title: 'Standard Ink',
    subtitle: 'Sweep Mission',
    description: 'Single stroke writing with 28% overlap Boustrophedon sweep.',
  },
  {
    id: 3,
    title: 'Shadow Disturbance',
    subtitle: 'Chroma Invariant',
    description: 'Illumination drop with stable chrominance rejected from ink.',
  },
  {
    id: 4,
    title: 'Presenter Occlusion',
    subtitle: 'No MOG2',
    description: 'Human hand/body occlusion preserves underlying twin ink.',
  },
  {
    id: 5,
    title: 'Stubborn Defect',
    subtitle: 'Cap Hit (3/3)',
    description: 'Residual ink exceeds 3 re-cleans and promotes to permanent defect.',
  },
  {
    id: 6,
    title: 'Projector Decoupling',
    subtitle: 'Mode A Heuristic',
    description: 'Digital projector overlay decoupled via continuous likelihood.',
  },
];

export const ScenarioBar: React.FC = () => {
  const activeScenarioId = useExecutionStore((state) => state.activeScenarioId);
  const setActiveScenario = useExecutionStore((state) => state.setActiveScenario);
  const [injectingId, setInjectingId] = useState<number | null>(null);

  const setTwinDelta = useTwinStore((state) => state.setTwinDelta);
  const addReconcilerEvent = useTwinStore((state) => state.addReconcilerEvent);
  const setDisturbances = usePerceptionStore((state) => state.setDisturbances);

  const handleInjectScenario = async (scenario: ScenarioDefinition) => {
    setInjectingId(scenario.id);
    setActiveScenario(scenario.id);

    try {
      await api.injectScenario(scenario.id);
    } catch {
      // Local deterministic state injection fallback
      injectLocalScenario(scenario.id);
    } finally {
      setInjectingId(null);
    }
  };

  const injectLocalScenario = (id: number) => {
    const timestamp = new Date().toISOString();

    if (id === 1) {
      // Scenario 1: Clean board
      useTwinStore.getState().clearTwin();
      usePerceptionStore.getState().setDisturbances(false, false, 0.0);
      addReconcilerEvent({
        id: `evt_${Date.now()}`,
        timestamp,
        event_type: 'BASELINE_EPOCH_COMMITTED',
        row_matched: 1,
        summary: 'Scenario 1: Clean baseline validated (edge density 0.8%)',
      });
    } else if (id === 2) {
      // Scenario 2: Standard ink
      const ink1: InkObject = {
        id: 'ink_eqn_01',
        frame: 'FRAME_BOARD',
        geometry: [
          [250, 180],
          [480, 180],
          [480, 320],
          [250, 320],
        ],
        centroid: [365, 250],
        area_mm2: 1250,
        state: 'STABLE_INK',
        reclean_attempts: 0,
        confidence: 0.98,
        last_seen_frame: 10,
        is_defect: false,
        stroke_color: '#2563eb',
      };
      setTwinDelta({ ink_eqn_01: ink1 }, false, false);
      addReconcilerEvent({
        id: `evt_${Date.now()}`,
        timestamp,
        event_type: 'INK_DETECTED_PERSISTENT',
        row_matched: 2,
        object_id: 'ink_eqn_01',
        summary: 'Scenario 2: Stable ink detected and registered in twin',
      });
    } else if (id === 3) {
      // Scenario 3: Shadow disturbance
      setDisturbances(false, true, 0.05);
      addReconcilerEvent({
        id: `evt_${Date.now()}`,
        timestamp,
        event_type: 'OBS_SHADOW_REJECTED',
        row_matched: 1,
        summary: 'Scenario 3: Multiplicative shadow rejected via chroma invariance',
      });
    } else if (id === 4) {
      // Scenario 4: Occlusion
      const existing = useTwinStore.getState().inkObjects;
      const occludedDelta: Record<string, InkObject> = {};
      for (const [key, obj] of Object.entries(existing)) {
        occludedDelta[key] = { ...obj, state: 'OCCLUDED' };
      }
      setTwinDelta(occludedDelta, true, false);
      addReconcilerEvent({
        id: `evt_${Date.now()}`,
        timestamp,
        event_type: 'TWIN_STATE_OCCLUDED',
        row_matched: 10,
        summary: 'Scenario 4: Presenter occlusion detected -- underlying ink preserved',
      });
    } else if (id === 5) {
      // Scenario 5: Stubborn permanent defect
      const stubbornInk: InkObject = {
        id: 'ink_stubborn_01',
        frame: 'FRAME_BOARD',
        geometry: [
          [600, 350],
          [720, 350],
          [720, 440],
          [600, 440],
        ],
        centroid: [660, 395],
        area_mm2: 850,
        state: 'PERMANENT_DEFECT',
        reclean_attempts: 3,
        confidence: 0.99,
        last_seen_frame: 45,
        is_defect: true,
        stroke_color: '#ef4444',
      };
      setTwinDelta({ ink_stubborn_01: stubbornInk }, false, false);
      addReconcilerEvent({
        id: `evt_${Date.now()}`,
        timestamp,
        event_type: 'RECLEAN_CAP_HIT',
        row_matched: 21,
        object_id: 'ink_stubborn_01',
        summary: 'Scenario 5: 3 re-clean attempts failed -> forced PERMANENT_DEFECT',
      });
    } else if (id === 6) {
      // Scenario 6: Projector decoupling
      setDisturbances(false, false, 0.92);
      addReconcilerEvent({
        id: `evt_${Date.now()}`,
        timestamp,
        event_type: 'PROJECTOR_LIKELIHOOD_ELEVATED',
        row_matched: 4,
        summary: 'Scenario 6: Mode A projector likelihood 92% -> suppressed candidate',
      });
    }
  };

  const getScenarioIcon = (id: number) => {
    switch (id) {
      case 1:
        return <SparklesIcon className="w-4 h-4 text-cyan-400" />;
      case 2:
        return <BrushIcon className="w-4 h-4 text-blue-400" />;
      case 3:
        return <SunIcon className="w-4 h-4 text-amber-400" />;
      case 4:
        return <HandIcon className="w-4 h-4 text-orange-400" />;
      case 5:
        return <ShieldAlertIcon className="w-4 h-4 text-rose-400" />;
      case 6:
        return <ProjectorIcon className="w-4 h-4 text-purple-400" />;
      default:
        return <SparklesIcon className="w-4 h-4 text-cyan-400" />;
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-3 space-y-2">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-xs text-slate-100 tracking-wide uppercase">
          Closed-Loop Scenario Injections (1..6)
        </h2>
        <span className="text-[10px] font-mono text-slate-400">Deterministic Presets</span>
      </div>

      <div className="grid grid-cols-6 gap-2">
        {SCENARIOS.map((sc) => {
          const isActive = activeScenarioId === sc.id;
          const isInjecting = injectingId === sc.id;

          return (
            <button
              key={sc.id}
              onClick={() => handleInjectScenario(sc)}
              disabled={isInjecting}
              className={`p-2 rounded-md border text-left transition flex flex-col justify-between ${
                isActive
                  ? 'bg-cyan-950/60 border-cyan-500 shadow-md ring-1 ring-cyan-500'
                  : 'bg-slate-850 border-slate-800 hover:border-slate-700'
              }`}
            >
              <div className="flex items-center justify-between w-full mb-1">
                <span className="font-mono font-bold text-xs text-slate-200">S{sc.id}</span>
                {getScenarioIcon(sc.id)}
              </div>
              <div>
                <div className="text-[11px] font-semibold text-slate-200 truncate">{sc.title}</div>
                <div className="text-[10px] text-slate-400 truncate">{sc.subtitle}</div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};
