'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

export interface MeetingSummary {
  id: string;
  title: string;
  status: 'queued' | 'processing' | 'complete' | 'failed';
  source_type: 'text' | 'audio';
  created_at: string;
}

const POLL_INTERVAL_MS = 3000;

const STATUS_CLASSES: Record<MeetingSummary['status'], string> = {
  queued: 'bg-slate-100 text-slate-700',
  processing: 'bg-amber-100 text-amber-800',
  complete: 'bg-emerald-100 text-emerald-800',
  failed: 'bg-rose-100 text-rose-800',
};

const formatDate = (iso: string): string => {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
};

export function MeetingTable() {
  const [meetings, setMeetings] = useState<MeetingSummary[] | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const res = await fetch('/api/meetings', { cache: 'no-store' });
        if (!res.ok) return;
        const data = (await res.json()) as MeetingSummary[];
        if (!cancelled) setMeetings(data);
      } catch {
        // Network errors leave the previous snapshot in place.
      }
    };

    load();
    const id = setInterval(load, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  if (meetings === null) {
    return <p className="text-sm text-slate-500">Loading meetings…</p>;
  }

  if (meetings.length === 0) {
    return <p className="text-sm text-slate-500">No meetings yet — upload one to get started.</p>;
  }

  return (
    <table className="min-w-full divide-y divide-slate-200 text-sm">
      <thead>
        <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
          <th className="py-2 pr-4">Title</th>
          <th className="py-2 pr-4">Created</th>
          <th className="py-2">Status</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-100">
        {meetings.map((m) => (
          <tr key={m.id}>
            <td className="py-2 pr-4 font-medium">
              <Link href={`/meetings/${m.id}`} className="text-slate-900 hover:underline">
                {m.title}
              </Link>
            </td>
            <td className="py-2 pr-4 text-slate-500">{formatDate(m.created_at)}</td>
            <td className="py-2">
              <span className={`inline-block rounded px-2 py-0.5 text-xs ${STATUS_CLASSES[m.status]}`}>
                {m.status}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
