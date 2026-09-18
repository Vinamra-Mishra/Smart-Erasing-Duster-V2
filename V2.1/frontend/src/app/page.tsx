'use client';

import React, { useState } from 'react';
import { VirtualBoardCanvas } from '../components/VirtualBoardCanvas';
import { RtpCameraStreamView } from '../components/RtpCameraStreamView';
import { BottomControlDock } from '../components/BottomControlDock';
import { CalibrationModal } from '../components/CalibrationModal';

export default function MissionControlPage() {
  const [isCalibrating, setIsCalibrating] = useState(false);

  return (
    <div className="flex-1 flex flex-col p-3 gap-3 min-h-0 overflow-y-auto">
      {/* Top Split-Screen Workspace (Left: Virtual Board | Right: RTP Camera) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 min-h-[380px] lg:min-h-[440px] flex-shrink-0">
        {/* Left: Authoritative Virtual Digital Twin Board */}
        <div className="h-full min-h-[360px]">
          <VirtualBoardCanvas />
        </div>

        {/* Right: Live Camera & RTP Video Feed */}
        <div className="h-full min-h-[360px]">
          <RtpCameraStreamView onOpenCalibration={() => setIsCalibrating(true)} />
        </div>
      </div>

      {/* Bottom Control Dock (Planner, Perception, Inspector, Scenarios) */}
      <div className="flex-1 min-h-[320px]">
        <BottomControlDock />
      </div>

      {/* Calibration & 4-Corner Crop Modal */}
      <CalibrationModal
        isOpen={isCalibrating}
        onClose={() => setIsCalibrating(false)}
      />
    </div>
  );
}
