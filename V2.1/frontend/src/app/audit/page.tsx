'use client';

import React, { useEffect, useState } from 'react';
import { api } from '../../api/client';
import { useTwinStore } from '../../store/useTwinStore';
import { LayersIcon, ActivityIcon } from '../../components/icons';

function formatTimestamp(ts: string | number | undefined): string {
  if (!ts) return new Date().toLocaleTimeString();
  const num = Number(ts);
  if (!isNaN(num)) {
    return new Date(num < 1e12 ? num * 1000 : num).toLocaleTimeString();
  }
  const d = new Date(ts);
  return isNaN(d.getTime()) ? new Date().toLocaleTimeString() : d.toLocaleTimeString();
}

export default function AuditPage() {
  const reconcilerEvents = useTwinStore((state) => state.reconcilerEvents);
  const [history, setHistory] = useState<any[]>([]);

  useEffect(() => {
    fetch('/api/twin/history?limit=30')
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => setHistory(data))
      .catch(() => setHistory([]));
  }, []);

  return (
    <div className="flex-1 flex flex-col p-4 gap-4 overflow-y-auto">
      <div className="flex items-center justify-between border-b border-slate-800 pb-3">
        <div>
          <h1 className="text-lg font-bold font-mono text-cyan-400">
            Reconciler Audit Bus &amp; Session History
          </h1>
          <p className="text-xs text-slate-400">
            Immutable event log tracking all 21-row Commit Truth Table state transitions, physical twin deltas, and execution action triggers.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Real-time Reconciler Event Stream */}
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 flex flex-col space-y-3">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <div className="flex items-center space-x-2">
              <ActivityIcon className="w-4 h-4 text-cyan-400" />
              <h2 className="font-semibold text-xs text-slate-200 tracking-wide uppercase">
                Real-Time Reconciler Events ({reconcilerEvents.length})
              </h2>
            </div>
            <span className="font-mono text-[10px] text-cyan-400 bg-cyan-950/60 px-2 py-0.5 rounded border border-cyan-800/50">
              /ws/events
            </span>
          </div>

          <div className="flex-1 overflow-y-auto max-h-[500px] space-y-2 pr-1 font-mono text-xs">
            {reconcilerEvents.length === 0 ? (
              <div className="text-slate-500 text-center py-8">
                Listening on /ws/events for Truth Table transitions...
              </div>
            ) : (
              reconcilerEvents.map((evt, idx) => (
                <div
                  key={`evt-${idx}`}
                  className="p-2.5 bg-slate-950/70 border border-slate-800/80 rounded flex flex-col space-y-1"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      {evt.row_matched && (
                        <span className="px-1.5 py-0.5 bg-cyan-950 text-cyan-400 rounded border border-cyan-800/60 text-[10px] font-bold">
                          Row {evt.row_matched}
                        </span>
                      )}
                      <span className="text-cyan-400 font-bold">{evt.event_type}</span>
                    </div>
                    <span className="text-[10px] text-slate-500">
                      {formatTimestamp(evt.timestamp)}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-300">{evt.summary}</p>
                  {(evt.previous_state || evt.next_state) && (
                    <div className="text-[10px] text-slate-400 flex items-center space-x-1.5">
                      <span className="text-slate-500">Transition:</span>
                      <span className="text-amber-400">{evt.previous_state || 'None'}</span>
                      <span>→</span>
                      <span className="text-emerald-400">{evt.next_state || 'None'}</span>
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>

        {/* Digital Twin State History */}
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 flex flex-col space-y-3">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <div className="flex items-center space-x-2">
              <LayersIcon className="w-4 h-4 text-purple-400" />
              <h2 className="font-semibold text-xs text-slate-200 tracking-wide uppercase">
                Authoritative Twin Snapshots ({history.length})
              </h2>
            </div>
            <span className="font-mono text-[10px] text-purple-400 bg-purple-950/60 px-2 py-0.5 rounded border border-purple-800/50">
              SQLite History
            </span>
          </div>

          <div className="flex-1 overflow-y-auto max-h-[500px] space-y-2 pr-1 font-mono text-xs">
            {history.length === 0 ? (
              <div className="text-slate-500 text-center py-8">
                No historical snapshots recorded yet.
              </div>
            ) : (
              history.map((snap, idx) => (
                <div
                  key={`snap-${idx}`}
                  className="p-2 bg-slate-950/70 border border-slate-800/80 rounded flex flex-col space-y-1"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-purple-300 font-bold">
                      Snapshot #{snap.snapshot_id || idx + 1}
                    </span>
                    <span className="text-[10px] text-slate-500">
                      {snap.timestamp ? new Date(snap.timestamp * 1000).toLocaleTimeString() : ''}
                    </span>
                  </div>
                  <div className="text-[11px] text-slate-300">
                    Active Objects: {snap.active_objects_count ?? (snap.ink_objects ? Object.keys(snap.ink_objects).length : 0)}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
