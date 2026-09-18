'use client';

import React from 'react';
import { CalibrationModal } from '../../components/CalibrationModal';
import { useRouter } from 'next/navigation';

export default function CalibrationPage() {
  const router = useRouter();

  return (
    <div className="flex-1 flex flex-col p-4">
      <CalibrationModal
        isOpen={true}
        onClose={() => router.push('/')}
      />
    </div>
  );
}
