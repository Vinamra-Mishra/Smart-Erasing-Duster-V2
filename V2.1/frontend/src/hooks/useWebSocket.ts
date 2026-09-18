import { useEffect, useRef, useCallback } from 'react';
import { useTwinStore } from '../store/useTwinStore';
import { useExecutionStore } from '../store/useExecutionStore';
import { usePerceptionStore } from '../store/usePerceptionStore';
import { useConfigStore } from '../store/useConfigStore';
import { InkObject, ReconcilerEvent } from '../types';

let globalEventsWs: WebSocket | null = null;

export function sendWsEvent(type: string, payload: Record<string, unknown> = {}): boolean {
  if (globalEventsWs && globalEventsWs.readyState === WebSocket.OPEN) {
    globalEventsWs.send(
      JSON.stringify({
        type,
        timestamp: Date.now() / 1000,
        payload,
      })
    );
    return true;
  }
  return false;
}

export function useWebSocket() {
  const eventsWsRef = useRef<WebSocket | null>(null);
  const telemetryWsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const pollingTimerRef = useRef<number | null>(null);

  const setTwinDelta = useTwinStore((state) => state.setTwinDelta);
  const addReconcilerEvent = useTwinStore((state) => state.addReconcilerEvent);
  const updateDusterPose = useExecutionStore((state) => state.updateDusterPose);
  const setExecutionState = useExecutionStore((state) => state.setExecutionState);
  const setResidualTier = useExecutionStore((state) => state.setResidualTier);
  const setWaypointIndex = useExecutionStore((state) => state.setWaypointIndex);
  const setMetrics = useExecutionStore((state) => state.setMetrics);
  const setEvidenceScore = usePerceptionStore((state) => state.setEvidenceScore);
  const setDisturbances = usePerceptionStore((state) => state.setDisturbances);
  const setStreamStatus = usePerceptionStore((state) => state.setStreamStatus);

  const stopHttpPolling = useCallback(() => {
    if (pollingTimerRef.current !== null) {
      window.clearInterval(pollingTimerRef.current);
      pollingTimerRef.current = null;
    }
  }, []);

  const startHttpPolling = useCallback(() => {
    if (pollingTimerRef.current !== null) return;

    const poll = async () => {
      try {
        const [stateRes, execRes] = await Promise.all([
          fetch('/api/twin/state').catch(() => null),
          fetch('/api/twin/execution').catch(() => null),
        ]);
        if (stateRes && stateRes.ok) {
          const stateData = await stateRes.json();
          if (stateData && stateData.objects) {
            setTwinDelta(stateData.objects, stateData.occluded, stateData.uncertain);
          }
          setStreamStatus(true, 30);
        }
        if (execRes && execRes.ok) {
          const execData = await execRes.json();
          if (execData.state) setExecutionState(execData.state);
          if (execData.residual_tier) setResidualTier(execData.residual_tier);
          if (execData.duster_pose) updateDusterPose(execData.duster_pose);
        }
      } catch {
        // Retry next tick
      }
    };

    poll();
    pollingTimerRef.current = window.setInterval(poll, 1500);
  }, [setTwinDelta, setStreamStatus, setExecutionState, setResidualTier, updateDusterPose]);

  const connect = useCallback(() => {
    if (typeof window === 'undefined') return;

    const normalizeWs = (url: string | undefined): string => {
      if (!url) return '';
      const s = url.trim();
      if (!s) return '';
      if (/^wss?:\/\//i.test(s)) return s.replace(/\/$/, '');
      if (/^https:\/\//i.test(s)) return s.replace(/^https:\/\//i, 'wss://').replace(/\/$/, '');
      if (/^http:\/\//i.test(s)) return s.replace(/^http:\/\//i, 'ws://').replace(/\/$/, '');
      return `ws://${s}`.replace(/\/$/, '');
    };

    let eventsUrl = '';
    let telemetryUrl = '';

    const customWs = process.env.NEXT_PUBLIC_WS_URL || process.env.NEXT_PUBLIC_BACKEND_URL;
    if (customWs) {
      const baseWs = normalizeWs(customWs);
      eventsUrl = `${baseWs}/ws/events`;
      telemetryUrl = `${baseWs}/ws/telemetry`;
    } else {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.hostname || '127.0.0.1';
      const defaultPort = window.location.port === '3000' ? '8000' : (window.location.port || '8000');
      const port = process.env.NEXT_PUBLIC_WS_PORT || defaultPort;
      const portSuffix = port ? `:${port}` : '';
      eventsUrl = `${protocol}//${host}${portSuffix}/ws/events`;
      telemetryUrl = `${protocol}//${host}${portSuffix}/ws/telemetry`;
    }

    try {
      const eventsWs = new WebSocket(eventsUrl);
      const telemetryWs = new WebSocket(telemetryUrl);

      eventsWsRef.current = eventsWs;
      globalEventsWs = eventsWs;
      telemetryWsRef.current = telemetryWs;

      eventsWs.onopen = () => {
        globalEventsWs = eventsWs;
        setStreamStatus(true);
        stopHttpPolling();
      };

      eventsWs.onerror = () => {
        startHttpPolling();
      };


      eventsWs.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          // Support BusEvent payload or twin_delta payload
          if (data.type === 'PHYSICAL_TWIN_UPDATED' && data.payload?.objects) {
            const rawObjs = data.payload.objects as Record<string, any>;
            const mapped: Record<string, InkObject> = {};
            for (const [id, obj] of Object.entries(rawObjs)) {
              mapped[id] = {
                ...obj,
                geometry: obj.geometry || obj.points || [],
                points: obj.points || obj.geometry || [],
                holes: obj.holes || [],
              };
            }
            setTwinDelta(mapped, data.payload.occluded, data.payload.uncertain);
            if (data.payload.width_mm && data.payload.height_mm) {
              useConfigStore.getState().updateConfig({
                board_width_mm: Number(data.payload.width_mm),
                board_height_mm: Number(data.payload.height_mm),
              });
            }
          } else if (data.twin_delta?.objects) {
            const rawObjs = data.twin_delta.objects as Record<string, any>;
            const mapped: Record<string, InkObject> = {};
            for (const [id, obj] of Object.entries(rawObjs)) {
              mapped[id] = {
                ...obj,
                geometry: obj.geometry || obj.points || [],
                points: obj.points || obj.geometry || [],
                holes: obj.holes || [],
              };
            }
            setTwinDelta(
              mapped,
              data.twin_delta.occluded,
              data.twin_delta.uncertain
            );
            if (data.twin_delta.width_mm && data.twin_delta.height_mm) {
              useConfigStore.getState().updateConfig({
                board_width_mm: Number(data.twin_delta.width_mm),
                board_height_mm: Number(data.twin_delta.height_mm),
              });
            }
          }

          // Handle EXECUTION_STATE_CHANGED
          if (data.type === 'EXECUTION_STATE_CHANGED' && data.payload) {
            if (data.payload.state) setExecutionState(data.payload.state);
            if (data.payload.residual_tier) setResidualTier(data.payload.residual_tier);
            if (data.payload.duster_pose) updateDusterPose(data.payload.duster_pose);
          }

          // Handle BASELINE_EPOCH_ROLLED
          if (data.type === 'BASELINE_EPOCH_ROLLED' && data.payload) {
            useTwinStore.getState().setBaselineEpoch({
              epoch_id: data.payload.epoch_id ?? 1,
              timestamp: data.payload.timestamp
                ? new Date(data.payload.timestamp * 1000).toISOString()
                : new Date().toISOString(),
              edge_density: data.payload.edge_density ?? 0,
              is_valid: data.payload.is_clean_verified ?? true,
              is_dirty_alert: !(data.payload.is_clean_verified ?? true),
              defect_count: data.payload.permanent_defect_count ?? 0,
            });
          }

          if (data.type === 'PLAN_GENERATED' && data.payload?.waypoints) {
            useExecutionStore.getState().setTrajectory(data.payload);
            useExecutionStore.getState().setExecutionState('PLANNING');
          }

          const eventType = data.event_type || data.type;
          if (
            eventType &&
            eventType !== 'PHYSICAL_TWIN_UPDATED' &&
            eventType !== 'EXECUTION_STATE_CHANGED'
          ) {
            const reconcilerEvent: ReconcilerEvent = {
              id: `${Date.now()}-${Math.random().toString(36).substring(2, 7)}`,
              timestamp: data.timestamp ? String(data.timestamp) : new Date().toISOString(),
              event_type: eventType,
              row_matched: data.row_matched ?? data.payload?.row_matched,
              object_id: data.object_id ?? data.payload?.object_id,
              summary: data.summary ?? data.payload?.summary ?? `Event: ${eventType}`,
            };
            addReconcilerEvent(reconcilerEvent);
          }
        } catch {
          // Ignore parse errors on malformed payloads
        }
      };

      eventsWs.onclose = () => {
        if (globalEventsWs === eventsWs) globalEventsWs = null;
        setStreamStatus(false);
        scheduleReconnect();
      };

      eventsWs.onerror = () => {
        setStreamStatus(false);
      };

      telemetryWs.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          const pose = data.pose || data.duster_pose;
          if (pose) {
            updateDusterPose({
              x: pose.x,
              y: pose.y,
              theta: pose.theta ?? pose.theta_deg ?? 0,
              swept_width_mm: pose.swept_width_mm ?? 162,
              swept_height_mm: pose.swept_height_mm ?? 58,
              is_contacting: pose.is_contacting ?? false,
            });
          }
          const execState = data.execution_state || data.mission?.state;
          if (execState) setExecutionState(execState);
          if (data.residual_tier) setResidualTier(data.residual_tier);
          if (typeof data.waypoint_index === 'number') setWaypointIndex(data.waypoint_index);
          if (data.metrics) setMetrics(data.metrics);
          if (typeof data.evidence_score === 'number') setEvidenceScore(data.evidence_score);

          if (data.perception) {
            const p = data.perception;
            if (typeof p.fused_score_mean === 'number') {
              setEvidenceScore(p.fused_score_mean);
            }
            if (typeof p.raw_score_mean === 'number') {
              usePerceptionStore.getState().setRawScore(p.raw_score_mean);
            }
            if (p.channels && typeof p.channels === 'object') {
              usePerceptionStore.getState().setChannelValues(p.channels);
            }
            if (p.glare !== undefined || p.shadow !== undefined || p.projector_likelihood !== undefined) {
              setDisturbances(
                Boolean(p.glare),
                Boolean(p.shadow),
                typeof p.projector_likelihood === 'number' ? p.projector_likelihood : 0.0
              );
            }
          } else if (data.glare !== undefined || data.shadow !== undefined || data.projector_likelihood !== undefined) {
            setDisturbances(
              Boolean(data.glare),
              Boolean(data.shadow),
              data.projector_likelihood ?? 0.0
            );
          }

          if (typeof data.fps === 'number') {
            setStreamStatus(true, data.fps);
          }
        } catch {
          // Ignore parse errors on telemetry
        }
      };


      eventsWs.onclose = () => {
        startHttpPolling();
        scheduleReconnect();
      };

      telemetryWs.onclose = () => {
        // Will reconnect together
      };
    } catch {
      startHttpPolling();
      scheduleReconnect();
    }
  }, [
    addReconcilerEvent,
    setDisturbances,
    setEvidenceScore,
    setExecutionState,
    setMetrics,
    setResidualTier,
    setStreamStatus,
    setTwinDelta,
    setWaypointIndex,
    updateDusterPose,
    startHttpPolling,
    stopHttpPolling,
  ]);

  const scheduleReconnect = useCallback(() => {
    if (reconnectTimerRef.current !== null) return;
    reconnectTimerRef.current = window.setTimeout(() => {
      reconnectTimerRef.current = null;
      connect();
    }, 3000);
  }, [connect]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
      }
      stopHttpPolling();
      eventsWsRef.current?.close();
      telemetryWsRef.current?.close();
    };
  }, [connect, stopHttpPolling]);

  const sendEvent = useCallback((type: string, payload: Record<string, unknown>) => {
    if (eventsWsRef.current && eventsWsRef.current.readyState === WebSocket.OPEN) {
      eventsWsRef.current.send(
        JSON.stringify({
          type,
          timestamp: new Date().toISOString(),
          ...payload,
        })
      );
    }
  }, []);

  return { sendEvent };
}
