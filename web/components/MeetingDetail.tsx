'use client';

import { useCallback, useEffect, useState } from 'react';

import { ActionItemTable } from '@/components/ActionItemTable';
import { DecisionCard } from '@/components/DecisionCard';
import { DispatchModal, type DispatchMode } from '@/components/DispatchModal';
import { SummaryPanel } from '@/components/SummaryPanel';
import type { MeetingDetail as MeetingDetailPayload } from '@/lib/meeting-detail';

interface MeetingDetailProps {
  meetingId: string;
}

const POLL_INTERVAL_MS = 3000;

const STATUS_CLASSES = {
  queued: 'bg-slate-100 text-slate-700',
  processing: 'bg-amber-100 text-amber-800',
  complete: 'bg-emerald-100 text-emerald-800',
  failed: 'bg-rose-100 text-rose-800',
} as const;

function Skeleton(): JSX.Element {
  return (
    <div
      data-testid="agent-skeleton"
      className="h-20 animate-pulse rounded border border-slate-200 bg-slate-100"
    />
  );
}

export function MeetingDetail({ meetingId }: MeetingDetailProps): JSX.Element {
  const [meeting, setMeeting] = useState<MeetingDetailPayload | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [retryBusy, setRetryBusy] = useState(false);
  const [dispatchMode, setDispatchMode] = useState<DispatchMode | null>(null);

  const load = useCallback(async (): Promise<MeetingDetailPayload | null> => {
    try {
      const res = await fetch(`/api/meetings/${meetingId}`, { cache: 'no-store' });
      if (!res.ok) {
        setLoadError(`Failed to load meeting (HTTP ${res.status})`);
        return null;
      }
      const data = (await res.json()) as MeetingDetailPayload;
      setMeeting(data);
      setLoadError(null);
      return data;
    } catch {
      setLoadError('Network error — retrying…');
      return null;
    }
  }, [meetingId]);

  useEffect(() => {
    let cancelled = false;
    let intervalId: ReturnType<typeof setInterval> | null = null;

    const run = async () => {
      const snapshot = await load();
      if (cancelled) return;
      const activeStatus = snapshot?.status ?? 'queued';
      if (activeStatus === 'queued' || activeStatus === 'processing') {
        intervalId = setInterval(async () => {
          const next = await load();
          if (next && next.status !== 'queued' && next.status !== 'processing' && intervalId) {
            clearInterval(intervalId);
            intervalId = null;
          }
        }, POLL_INTERVAL_MS);
      }
    };
    run();

    return () => {
      cancelled = true;
      if (intervalId) clearInterval(intervalId);
    };
  }, [load]);

  const onRetry = async () => {
    setRetryBusy(true);
    try {
      await fetch(`/api/meetings/${meetingId}/retry`, { method: 'POST' });
      await load();
    } finally {
      setRetryBusy(false);
    }
  };

  if (meeting === null) {
    return (
      <p className="text-sm text-slate-500">
        {loadError ?? 'Loading meeting…'}
      </p>
    );
  }

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">{meeting.title}</h1>
          <p className="text-xs text-slate-500">{meeting.source_filename}</p>
        </div>
        <span
          className={`inline-block rounded px-2 py-0.5 text-xs ${STATUS_CLASSES[meeting.status]}`}
        >
          {meeting.status}
        </span>
      </header>

      {meeting.status === 'failed' && (
        <section className="rounded border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
          <p className="font-medium">Processing failed.</p>
          <p className="mt-1">{meeting.error_message ?? 'Unknown error'}</p>
          <button
            type="button"
            onClick={onRetry}
            disabled={retryBusy}
            className="mt-3 rounded bg-rose-600 px-3 py-1 text-white disabled:opacity-60"
          >
            {retryBusy ? 'Retrying…' : 'Retry'}
          </button>
        </section>
      )}

      <section>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
          Decisions
        </h2>
        {meeting.status === 'processing' || meeting.status === 'queued' ? (
          <Skeleton />
        ) : meeting.decisions.length === 0 ? (
          <p className="text-sm text-slate-500">No decisions recorded.</p>
        ) : (
          <div className="grid gap-3">
            {meeting.decisions.map((d) => (
              <DecisionCard key={d.id} decision={d} />
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
          Action Items
        </h2>
        {meeting.status === 'processing' || meeting.status === 'queued' ? (
          <Skeleton />
        ) : (
          <>
            <ActionItemTable items={meeting.action_items} />
            {meeting.status === 'complete' && meeting.action_items.length > 0 && (
              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  onClick={() => setDispatchMode('linear')}
                  className="rounded border border-slate-300 bg-white px-3 py-1 text-sm hover:bg-slate-50"
                >
                  Create Linear tickets
                </button>
                <button
                  type="button"
                  onClick={() => setDispatchMode('gmail')}
                  className="rounded border border-slate-300 bg-white px-3 py-1 text-sm hover:bg-slate-50"
                >
                  Draft Gmail follow-up
                </button>
              </div>
            )}
          </>
        )}
      </section>

      {dispatchMode !== null && (
        <DispatchModal
          mode={dispatchMode}
          meetingId={meeting.id}
          actionItems={meeting.action_items}
          isOpen
          onClose={() => setDispatchMode(null)}
        />
      )}

      <section>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
          Summary
        </h2>
        {meeting.status === 'processing' || meeting.status === 'queued' ? (
          <Skeleton />
        ) : (
          <SummaryPanel summary={meeting.summary} />
        )}
      </section>
    </div>
  );
}
