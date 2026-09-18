'use client';

import React, { useEffect } from 'react';
import { useWebSocket } from '../hooks/useWebSocket';
import { api } from '../api/client';
import { useConfigStore } from '../store/useConfigStore';

export const ClientWebSocketProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // Connect WebSocket bus for real-time telemetry & events
  useWebSocket();

  useEffect(() => {
    // Flush persisted ink objects on first page mount
    const resetUrl = process.env.NEXT_PUBLIC_BACKEND_URL
      ? `${process.env.NEXT_PUBLIC_BACKEND_URL.replace(/\/$/, '')}/api/twin/reset`
      : '/api/twin/reset';
    fetch(resetUrl, { method: 'POST' }).catch(() => {
      // Backend may be starting up
    });

    // Sync system config & calibration status
    Promise.all([
      api.getConfig().catch(() => null),
      api.getCalibrationStatus().catch(() => null),
    ]).then(([cfg, cal]) => {
      if (cfg) {
        useConfigStore.getState().updateConfig(cfg);
      }
      if (cal && cal.board_width_mm && cal.board_height_mm) {
        useConfigStore.getState().updateConfig({
          board_width_mm: cal.board_width_mm,
          board_height_mm: cal.board_height_mm,
        });
      }
    });
  }, []);

  return <>{children}</>;
};
export default ClientWebSocketProvider;
