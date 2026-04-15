/**
 * Subscribes to the meeting's SSE status stream.
 *
 * The stream emits `status` events shaped like `{ status, error_message }`
 * and closes once the status is terminal (`complete` or `failed`). The
 * browser's EventSource handles transient reconnects transparently; we
 * only tear it down on unmount or when `enabled` is false.
 *
 * Returns the most recent payload observed (or null before the first
 * event arrives). Callers typically re-fetch their detail resource
 * whenever this changes.
 */
import { useEffect, useState } from 'react';

export type MeetingStatus = 'queued' | 'processing' | 'complete' | 'failed';

export interface SSEStatus {
  status: MeetingStatus;
  error_message: string | null;
}

interface UseSSEOptions {
  enabled?: boolean;
}

export function useSSE(
  meetingId: string,
  options: UseSSEOptions = {},
): SSEStatus | null {
  const { enabled = true } = options;
  const [latest, setLatest] = useState<SSEStatus | null>(null);

  useEffect(() => {
    if (!enabled) return;
    if (typeof EventSource === 'undefined') return;

    const source = new EventSource(`/api/meetings/${meetingId}/events`);
    const onStatus = (event: MessageEvent): void => {
      try {
        const data = JSON.parse(event.data) as SSEStatus;
        setLatest(data);
      } catch {
        // Ignore malformed frames — next event will supersede anyway.
      }
    };

    source.addEventListener('status', onStatus);

    return () => {
      source.removeEventListener('status', onStatus);
      source.close();
    };
  }, [meetingId, enabled]);

  return latest;
}
