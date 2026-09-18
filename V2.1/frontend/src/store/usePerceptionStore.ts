import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';
import { PerceptionChannelInfo } from '../types';

export interface PerceptionStoreState {
  channels: PerceptionChannelInfo[];
  activeChannelId: string;
  channelHeatmaps: Record<string, string>;
  channelValues: Record<string, number>;
  rawScore: number;
  evidenceScore: number;
  glareDetected: boolean;
  shadowDetected: boolean;
  projectorLikelihood: number;
  streamConnected: boolean;
  streamFps: number;
}

export interface PerceptionStoreActions {
  setActiveChannel: (id: string) => void;
  updateChannelHeatmap: (channelId: string, url: string) => void;
  setChannelValues: (values: Record<string, number>) => void;
  setRawScore: (score: number) => void;
  setEvidenceScore: (score: number) => void;
  setDisturbances: (glare: boolean, shadow: boolean, projectorLikelihood: number) => void;
  setStreamStatus: (connected: boolean, fps?: number) => void;
}

export type PerceptionStore = PerceptionStoreState & PerceptionStoreActions;

export const DEFAULT_CHANNELS: PerceptionChannelInfo[] = [
  { id: 'ch_delta_r', name: 'dR', domain: 'RGB', weight: 0.083, description: '|R - R_ref| Red channel difference' },
  { id: 'ch_delta_g', name: 'dG', domain: 'RGB', weight: 0.083, description: '|G - G_ref| Green channel difference' },
  { id: 'ch_delta_b', name: 'dB', domain: 'RGB', weight: 0.083, description: '|B - B_ref| Blue channel difference' },
  { id: 'ch_delta_h', name: 'dH', domain: 'HSV', weight: 0.067, description: 'min(|H - H_ref|, 180 - |H - H_ref|) Hue difference' },
  { id: 'ch_delta_s', name: 'dS', domain: 'HSV', weight: 0.067, description: '|S - S_ref| Saturation difference' },
  { id: 'ch_delta_v', name: 'dV', domain: 'HSV', weight: 0.067, description: '|V - V_ref| Value/Luminance difference' },
  { id: 'ch_delta_l', name: 'dL*', domain: 'Lab', weight: 0.067, description: '|L* - L*_ref| Perceptual lightness difference' },
  { id: 'ch_delta_a', name: 'da*', domain: 'Lab', weight: 0.067, description: '|a* - a*_ref| Green-Red chrominance difference' },
  { id: 'ch_delta_b_lab', name: 'db*', domain: 'Lab', weight: 0.067, description: '|b* - b*_ref| Blue-Yellow chrominance difference' },
  { id: 'ch_delta_edge', name: 'dEdge', domain: 'Edge', weight: 0.20, description: '|grad(I) - grad(I_ref)| Gradient edge magnitude' },
  { id: 'ch_delta_contrast', name: 'dContrast', domain: 'Contrast', weight: 0.15, description: '|stddev(I) - stddev(I_ref)| Local variance texture difference' },
];

export const usePerceptionStore = create<PerceptionStore>()(
  subscribeWithSelector((set) => ({
    channels: DEFAULT_CHANNELS,
    activeChannelId: 'ch_delta_edge',
    channelHeatmaps: {},
    channelValues: {},
    rawScore: 0.0,
    evidenceScore: 0.0,
    glareDetected: false,
    shadowDetected: false,
    projectorLikelihood: 0.0,
    streamConnected: false,
    streamFps: 0,

    setActiveChannel: (id) => set({ activeChannelId: id }),

    updateChannelHeatmap: (channelId, url) =>
      set((state) => ({
        channelHeatmaps: { ...state.channelHeatmaps, [channelId]: url },
      })),

    setChannelValues: (values) =>
      set((state) => ({
        channelValues: { ...state.channelValues, ...values },
      })),

    setRawScore: (score) => set({ rawScore: score }),

    setEvidenceScore: (score) => set({ evidenceScore: score }),

    setDisturbances: (glare, shadow, projectorLikelihood) =>
      set({
        glareDetected: glare,
        shadowDetected: shadow,
        projectorLikelihood,
      }),

    setStreamStatus: (connected, fps) =>
      set((state) => ({
        streamConnected: connected,
        streamFps: fps !== undefined ? fps : state.streamFps,
      })),
  }))
);

