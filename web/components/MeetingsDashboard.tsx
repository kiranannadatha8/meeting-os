'use client';

import { useState } from 'react';

import { MeetingTable } from '@/components/MeetingTable';
import { UploadButton } from '@/components/UploadButton';

export function MeetingsDashboard() {
  const [refreshKey, setRefreshKey] = useState(0);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-medium">Your meetings</h2>
        <UploadButton onUploaded={() => setRefreshKey((k) => k + 1)} />
      </div>
      <MeetingTable key={refreshKey} />
    </div>
  );
}
